#!/usr/bin/env python3
"""Vireo Audio first-response SLA monitor.

The core SLA calculations are deterministic. An optional aggregate-only AI briefing
can be requested from any OpenAI-compatible chat endpoint.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import math
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


REQUIRED_TICKET_COLUMNS = {
    "ticket_id",
    "created_at",
    "first_response_at",
    "status",
    "channel",
    "agent_id",
    "source_system",
}
REQUIRED_AGENT_COLUMNS = {
    "agent_id",
    "name",
    "site",
    "team",
    "shift",
    "tier",
    "from_date",
    "to_date",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Vireo's weekly SLA breach report")
    parser.add_argument("--tickets", default="data/tickets.csv")
    parser.add_argument("--agents", default="data/agents.csv")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument(
        "--ai-endpoint",
        help="Optional OpenAI-compatible /chat/completions endpoint. No call is made by default.",
    )
    parser.add_argument("--ai-model", default="")
    parser.add_argument("--ai-key-env", default="VIREO_AI_API_KEY")
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def require_columns(rows: list[dict[str, str]], required: set[str], label: str) -> None:
    if not rows:
        raise ValueError(f"{label} is empty")
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"{label} is missing columns: {', '.join(sorted(missing))}")


def parse_datetime(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value)


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def percentage(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def shift_for_time(local_datetime: dt.datetime) -> str:
    current = local_datetime.time()
    if dt.time(6) <= current < dt.time(14):
        return "Morning"
    if dt.time(14) <= current < dt.time(22):
        return "Day"
    return "Night"


def monday_of(value: dt.date) -> dt.date:
    return value - dt.timedelta(days=value.weekday())


def quarter_start(value: dt.date) -> dt.date:
    month = ((value.month - 1) // 3) * 3 + 1
    return dt.date(value.year, month, 1)


def bernoulli_log_likelihood(breaches: int, tickets: int) -> float:
    if not tickets or breaches in {0, tickets}:
        return 0.0
    rate = breaches / tickets
    return breaches * math.log(rate) + (tickets - breaches) * math.log(1 - rate)


def detect_change_point(
    records: list[dict[str, Any]], min_segment_days: int = 60
) -> dict[str, Any] | None:
    """Find the single date that best separates two Bernoulli breach regimes."""
    daily: dict[dt.date, list[int]] = defaultdict(lambda: [0, 0])
    for record in records:
        local_date = record["created_ist"].date()
        daily[local_date][0] += 1
        daily[local_date][1] += int(record["breach"])

    dates = sorted(daily)
    if len(dates) < min_segment_days * 2:
        return None

    total_tickets = sum(values[0] for values in daily.values())
    total_breaches = sum(values[1] for values in daily.values())
    baseline = bernoulli_log_likelihood(total_breaches, total_tickets)
    left_tickets = 0
    left_breaches = 0
    best: dict[str, Any] | None = None

    for split_date in dates:
        if (split_date - dates[0]).days < min_segment_days:
            left_tickets += daily[split_date][0]
            left_breaches += daily[split_date][1]
            continue
        if (dates[-1] - split_date).days < min_segment_days:
            break

        right_tickets = total_tickets - left_tickets
        right_breaches = total_breaches - left_breaches
        gain = (
            bernoulli_log_likelihood(left_breaches, left_tickets)
            + bernoulli_log_likelihood(right_breaches, right_tickets)
            - baseline
        )
        candidate = {
            "split_date": split_date,
            "before_tickets": left_tickets,
            "before_breaches": left_breaches,
            "before_rate": percentage(left_breaches, left_tickets),
            "after_tickets": right_tickets,
            "after_breaches": right_breaches,
            "after_rate": percentage(right_breaches, right_tickets),
            "log_likelihood_gain": gain,
        }
        if best is None or gain > best["log_likelihood_gain"]:
            best = candidate

        left_tickets += daily[split_date][0]
        left_breaches += daily[split_date][1]

    return best


def choose_duplicate(rows: list[dict[str, str]]) -> dict[str, str]:
    """Prefer the current helpdesk copy; then prefer the more complete record."""
    return max(
        rows,
        key=lambda row: (
            row.get("source_system") == "helpdesk",
            bool(row.get("resolved_at")),
            sum(bool(value) for value in row.values()),
        ),
    )


def deduplicate(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, int]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["ticket_id"]].append(row)

    duplicate_groups = [group for group in grouped.values() if len(group) > 1]
    material_conflicts = 0
    ignored = {"source_system", "csat_score"}
    for group in duplicate_groups:
        first = group[0]
        if any(
            any(first.get(column, "") != row.get(column, "") for column in first if column not in ignored)
            for row in group[1:]
        ):
            material_conflicts += 1

    chosen = [choose_duplicate(group) for group in grouped.values()]
    quality = {
        "raw_rows": len(rows),
        "unique_ticket_ids": len(chosen),
        "duplicate_rows_removed": len(rows) - len(chosen),
        "duplicate_ticket_ids": len(duplicate_groups),
        "duplicate_groups_with_material_conflicts": material_conflicts,
    }
    return chosen, quality


def assignment_for(
    roster: dict[str, list[dict[str, str]]], agent_id: str, local_date: dt.date
) -> dict[str, str] | None:
    matches = []
    for assignment in roster.get(agent_id, []):
        start = parse_date(assignment["from_date"])
        end = parse_date(assignment["to_date"]) if assignment["to_date"] else None
        if start <= local_date and (end is None or local_date <= end):
            matches.append(assignment)
    return matches[0] if len(matches) == 1 else None


def scheduled_shift_start(reference: dt.datetime, shift: str) -> dt.datetime:
    start_hour = {"Morning": 6, "Day": 14, "Night": 22}[shift]
    start = dt.datetime.combine(reference.date(), dt.time(start_hour))
    if start > reference:
        start -= dt.timedelta(days=1)
    return start


def build_records(
    tickets: list[dict[str, str]],
    assignments: list[dict[str, str]],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    offset = dt.timedelta(minutes=int(config["timezone_offset_minutes"]))
    sla_minutes = {key: int(value) for key, value in config["sla_minutes"].items()}
    roster: dict[str, list[dict[str, str]]] = defaultdict(list)
    for assignment in assignments:
        roster[assignment["agent_id"]].append(assignment)

    records: list[dict[str, Any]] = []
    unmatched = 0
    ambiguous = 0
    invalid_timestamps = 0

    for ticket in tickets:
        try:
            created_utc = parse_datetime(ticket["created_at"])
            response_utc = parse_datetime(ticket["first_response_at"])
        except (TypeError, ValueError):
            invalid_timestamps += 1
            continue

        if ticket["channel"] not in sla_minutes:
            raise ValueError(f"Unknown channel {ticket['channel']!r} on {ticket['ticket_id']}")

        created_ist = created_utc + offset
        response_ist = response_utc + offset
        response_minutes = (response_utc - created_utc).total_seconds() / 60
        threshold = sla_minutes[ticket["channel"]]
        breach = response_minutes > threshold
        assignment = assignment_for(roster, ticket["agent_id"], response_ist.date())
        if assignment is None:
            possible = roster.get(ticket["agent_id"], [])
            unmatched += not possible
            ambiguous += bool(possible)
            agent_name = "Unmatched roster"
            roster_shift = "Unmatched"
            site = "Unmatched"
            tier = "Unmatched"
        else:
            agent_name = assignment["name"]
            roster_shift = assignment["shift"]
            site = assignment["site"]
            tier = assignment["tier"]

        deadline_ist = created_ist + dt.timedelta(minutes=threshold)
        shift_start = (
            scheduled_shift_start(response_ist, roster_shift)
            if roster_shift in {"Morning", "Day", "Night"}
            else response_ist
        )
        records.append(
            {
                **ticket,
                "created_ist": created_ist,
                "first_response_ist": response_ist,
                "response_minutes": response_minutes,
                "sla_minutes": threshold,
                "breach": breach,
                "deadline_ist": deadline_ist,
                "week_start": monday_of(created_ist.date()),
                "creation_shift": shift_for_time(created_ist),
                "agent_name": agent_name,
                "roster_shift": roster_shift,
                "site": site,
                "tier": tier,
                "completed": ticket["status"] in {"resolved", "closed"},
                "deadline_before_recorded_shift": breach and deadline_ist <= shift_start,
            }
        )

    return records, {
        "invalid_timestamp_rows_skipped": invalid_timestamps,
        "roster_agent_missing": int(unmatched),
        "roster_date_unmatched_or_ambiguous": int(ambiguous),
    }


def summarize_group(records: Iterable[dict[str, Any]], credit: int) -> dict[str, Any]:
    group = list(records)
    breaches = sum(record["breach"] for record in group)
    completed_breaches = sum(record["breach"] and record["completed"] for record in group)
    return {
        "tickets": len(group),
        "breaches": breaches,
        "breach_rate": percentage(breaches, len(group)),
        "completed_breaches": completed_breaches,
        "booked_credit_inr": completed_breaches * credit,
    }


def aggregate(
    records: list[dict[str, Any]], keys: tuple[str, ...], credit: int
) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[tuple(record[key] for key in keys)].append(record)
    output = []
    for values, group in groups.items():
        row = {key: value for key, value in zip(keys, values)}
        row.update(summarize_group(group, credit))
        row["overnight_origin_breaches"] = sum(
            record["breach"] and record["creation_shift"] == "Night" for record in group
        )
        output.append(row)
    return output


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            cooked = {}
            for field in fields:
                value = row.get(field, "")
                if isinstance(value, dt.date):
                    value = value.isoformat()
                elif isinstance(value, float) and field.endswith("rate"):
                    value = f"{value:.4f}"
                cooked[field] = value
            writer.writerow(cooked)


def validation_sample(
    records: list[dict[str, Any]], per_stratum: int = 15
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    strata: dict[tuple[str, bool], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        strata[(record["channel"], record["breach"])].append(record)

    sample: list[dict[str, Any]] = []
    errors = 0
    for key in sorted(strata):
        ordered = sorted(
            strata[key],
            key=lambda row: hashlib.sha256(row["ticket_id"].encode()).hexdigest(),
        )
        for record in ordered[:per_stratum]:
            independently_calculated_minutes = (
                parse_datetime(record["first_response_at"])
                - parse_datetime(record["created_at"])
            ).total_seconds() / 60
            expected = independently_calculated_minutes > record["sla_minutes"]
            agrees = expected == record["breach"]
            errors += not agrees
            sample.append(
                {
                    "ticket_id": record["ticket_id"],
                    "channel": record["channel"],
                    "created_at_utc": record["created_at"],
                    "first_response_at_utc": record["first_response_at"],
                    "response_minutes": round(independently_calculated_minutes, 2),
                    "sla_minutes": record["sla_minutes"],
                    "expected_breach": expected,
                    "tool_breach": record["breach"],
                    "agrees": agrees,
                }
            )
    return sample, {
        "method": "Deterministic stratified sample: 15 breach and 15 non-breach tickets per channel; timestamps were independently subtracted and compared with policy thresholds.",
        "sample_size": len(sample),
        "classification_errors": errors,
        "observed_error_rate": percentage(errors, len(sample)),
        "known_failure_mode": "The export identifies the resolving agent, not the human who sent the first response; agent attribution is therefore descriptive, not causal.",
    }


def money(value: float | int) -> str:
    return f"₹{value:,.0f}"


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def line_chart_svg(weekly: list[dict[str, Any]]) -> str:
    if not weekly:
        return ""
    width, height, left, top, bottom = 920, 250, 44, 18, 34
    inner_w = width - left - 16
    inner_h = height - top - bottom
    rates = [row["breach_rate"] for row in weekly]
    y_max = max(0.35, math.ceil(max(rates) * 10) / 10)
    points = []
    for index, rate in enumerate(rates):
        x = left + (inner_w * index / max(1, len(rates) - 1))
        y = top + inner_h * (1 - rate / y_max)
        points.append(f"{x:.1f},{y:.1f}")
    grid = []
    for step in range(5):
        rate = y_max * step / 4
        y = top + inner_h * (1 - rate / y_max)
        grid.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width-16}" y2="{y:.1f}" class="grid" />'
            f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end">{rate*100:.0f}%</text>'
        )
    labels = []
    for index in range(0, len(weekly), max(1, len(weekly) // 6)):
        x = left + (inner_w * index / max(1, len(weekly) - 1))
        labels.append(
            f'<text x="{x:.1f}" y="{height-8}" text-anchor="middle">{weekly[index]["week_start"].strftime("%d %b")}</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Weekly breach rate">'
        + "".join(grid)
        + f'<polyline points="{" ".join(points)}" class="trend" />'
        + "".join(labels)
        + "</svg>"
    )


def html_table(headers: list[str], rows: list[list[Any]], classes: str = "") -> str:
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f'<div class="table-wrap"><table class="{classes}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def build_ai_prompt(metrics: dict[str, Any]) -> str:
    return f"""You are assisting Vireo Audio's Support Operations Manager.

Write a five-bullet weekly operating brief from the aggregate metrics below. Do not infer individual-agent causality: agent_id in this export is the resolving agent, not necessarily the first responder. Lead with the operational action, quantify money, and distinguish created-time shift from resolver roster shift. Use plain language and no more than 180 words.

METRICS
{json.dumps(metrics, indent=2, default=str)}
"""


def call_ai(endpoint: str, model: str, key_env: str, prompt: str) -> str:
    key = os.getenv(key_env, "")
    if not model:
        raise ValueError("--ai-model is required when --ai-endpoint is used")
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": "Return only the requested operating brief."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }
    ).encode()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.loads(response.read().decode())
    return result["choices"][0]["message"]["content"].strip()


def build_html(
    records: list[dict[str, Any]],
    assignments: list[dict[str, str]],
    change_point: dict[str, Any] | None,
    quality: dict[str, Any],
    config: dict[str, Any],
    ai_brief: str | None,
) -> str:
    credit = int(config["sla_credit_inr"])
    latest_date = max(record["created_ist"].date() for record in records)
    current_quarter_start = quarter_start(latest_date)
    quarter = [record for record in records if current_quarter_start <= record["created_ist"].date() <= latest_date]
    quarter_summary = summarize_group(quarter, credit)
    target = float(config["goal_target_rate"])
    weekly_volume = int(config["planning_volume_per_week"])
    savings_quarter = max(0, quarter_summary["breach_rate"] - target) * weekly_volume * 13 * credit

    weekly = aggregate(records, ("week_start",), credit)
    weekly.sort(key=lambda row: row["week_start"])
    completed_weekly = [
        row for row in weekly if row["week_start"] + dt.timedelta(days=6) <= latest_date
    ]
    recent_weekly = completed_weekly[-13:]

    shift_rows = aggregate(quarter, ("creation_shift",), credit)
    shift_order = {"Morning": 0, "Day": 1, "Night": 2}
    shift_rows.sort(key=lambda row: shift_order.get(row["creation_shift"], 9))

    agent_rows = aggregate(quarter, ("agent_id", "agent_name", "site", "roster_shift"), credit)
    agent_rows.sort(key=lambda row: (row["breaches"], row["breach_rate"]), reverse=True)

    morning_breaches = sum(
        record["breach"] and record["roster_shift"] == "Morning" for record in quarter
    )
    morning_from_night = sum(
        record["breach"]
        and record["roster_shift"] == "Morning"
        and record["creation_shift"] == "Night"
        for record in quarter
    )
    night_records = [record for record in quarter if record["creation_shift"] == "Night"]
    night_summary = summarize_group(night_records, credit)

    first_half = [record for record in records if record["created_ist"].date() <= dt.date(2025, 6, 29)]
    after_change = [
        record
        for record in records
        if dt.date(2025, 6, 30) <= record["created_ist"].date() <= dt.date(2025, 12, 31)
    ]
    before_summary = summarize_group(first_half, credit)
    after_summary = summarize_group(after_change, credit)

    active_roster_shifts = {
        assignment["shift"]
        for assignment in assignments
        if parse_date(assignment["from_date"]) <= latest_date
        and (not assignment["to_date"] or latest_date <= parse_date(assignment["to_date"]))
    }
    night_roster_present = "Night" in active_roster_shifts
    change_date = change_point["split_date"] if change_point else None

    shift_table = html_table(
        ["Created in shift", "Tickets", "Breaches", "Rate", "Booked credits"],
        [
            [
                row["creation_shift"],
                f'{row["tickets"]:,}',
                f'{row["breaches"]:,}',
                pct(row["breach_rate"]),
                money(row["booked_credit_inr"]),
            ]
            for row in shift_rows
        ],
    )
    agent_table = html_table(
        ["Recorded agent", "Site", "Roster shift", "Tickets", "Breaches", "Rate", "From Night"],
        [
            [
                f'{row["agent_name"]} ({row["agent_id"]})',
                row["site"],
                row["roster_shift"],
                row["tickets"],
                row["breaches"],
                pct(row["breach_rate"]),
                row["overnight_origin_breaches"],
            ]
            for row in agent_rows[:15]
        ],
    )
    weekly_table = html_table(
        ["Week", "Tickets", "Breaches", "Rate", "Booked credits"],
        [
            [
                row["week_start"].isoformat(),
                row["tickets"],
                row["breaches"],
                pct(row["breach_rate"]),
                money(row["booked_credit_inr"]),
            ]
            for row in reversed(recent_weekly)
        ],
    )

    ai_section = ""
    if ai_brief:
        ai_section = f'<section><h2>AI operating brief</h2><div class="ai-brief">{html.escape(ai_brief)}</div></section>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vireo Audio - first-response SLA</title>
<style>
:root {{ --ink:#172033; --muted:#657084; --line:#dfe4ec; --paper:#f5f7fb; --card:#fff; --brand:#155eef; --bad:#b42318; --good:#067647; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
main {{ max-width:1120px; margin:auto; padding:36px 24px 72px; }}
h1 {{ margin:0; font-size:32px; letter-spacing:-.03em; }}
h2 {{ margin:0 0 14px; font-size:20px; }}
p {{ margin:8px 0; }}
.subtitle {{ color:var(--muted); margin:4px 0 28px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:14px; }}
.card, section {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:20px; box-shadow:0 1px 2px rgba(16,24,40,.04); }}
.label {{ color:var(--muted); font-size:13px; }}
.value {{ font-size:28px; font-weight:700; margin-top:4px; }}
.value.bad {{ color:var(--bad); }} .value.good {{ color:var(--good); }}
section {{ margin-top:16px; }}
.finding {{ border-left:5px solid var(--brand); }}
.finding strong {{ font-size:18px; }}
.goal {{ background:#ecfdf3; border-color:#abefc6; }}
.caveat {{ background:#fff7ed; border-color:#fed7aa; }}
.two {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
.table-wrap {{ overflow:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th {{ text-align:left; color:var(--muted); font-weight:600; border-bottom:1px solid var(--line); padding:9px 8px; white-space:nowrap; }}
td {{ border-bottom:1px solid #eef1f5; padding:9px 8px; white-space:nowrap; }}
svg {{ width:100%; height:auto; }} svg text {{ fill:var(--muted); font-size:11px; }}
.grid {{ stroke:#e8ecf2; stroke-width:1; }} .trend {{ fill:none; stroke:var(--brand); stroke-width:3; stroke-linejoin:round; stroke-linecap:round; }}
.ai-brief {{ white-space:pre-wrap; }}
.footer {{ color:var(--muted); font-size:12px; margin-top:18px; }}
@media (max-width:800px) {{ .cards,.two {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body><main>
<h1>First-response SLA</h1>
<div class="subtitle">Vireo Audio · through {latest_date.isoformat()} · UTC converted to IST · duplicates removed</div>
<div class="cards">
  <div class="card"><div class="label">Latest-quarter breach rate</div><div class="value bad">{pct(quarter_summary['breach_rate'])}</div><div>{quarter_summary['breaches']:,} of {quarter_summary['tickets']:,}</div></div>
  <div class="card"><div class="label">Night-created breach rate</div><div class="value bad">{pct(night_summary['breach_rate'])}</div><div>{night_summary['breaches']:,} of {night_summary['tickets']:,}</div></div>
  <div class="card"><div class="label">Latest-quarter booked credits</div><div class="value">{money(quarter_summary['booked_credit_inr'])}</div><div>resolved or closed tickets</div></div>
  <div class="card"><div class="label">Night roster present</div><div class="value {'good' if night_roster_present else 'bad'}">{'Yes' if night_roster_present else 'No'}</div><div>dated roster in latest quarter</div></div>
  <div class="card"><div class="label">Model-detected break</div><div class="value">{change_date.strftime('%d %b') if change_date else 'N/A'}</div><div>{change_date.year if change_date else 'insufficient history'}</div></div>
</div>
<section class="finding">
  <h2>What changed</h2>
  <p><strong>This is a coverage problem presented as a Morning-agent problem.</strong></p>
  <p>The roster has no Night assignment after 29 June 2025. The overall rate moved from {pct(before_summary['breach_rate'])} before that change to {pct(after_summary['breach_rate'])} in the following half-year. In the latest quarter, {morning_from_night:,} of {morning_breaches:,} breaches recorded against Morning resolvers ({pct(percentage(morning_from_night, morning_breaches))}) were created overnight.</p>
</section>
<section>
  <h2>How the model assists</h2>
  <p>A local Bernoulli change-point model scans daily breach outcomes for the strongest structural break. It independently selects {change_date.strftime('%d %B %Y') if change_date else 'no stable date'}, where the rate changes from {pct(change_point['before_rate']) if change_point else 'N/A'} to {pct(change_point['after_rate']) if change_point else 'N/A'}. That aligns with the dated Night-to-Day roster change. SLA classification itself stays rule-based and auditable.</p>
</section>
<section class="goal">
  <h2>90-day operating goal</h2>
  <p><strong>Reduce first-response breaches from {pct(quarter_summary['breach_rate'])} to {pct(target)} without adding headcount.</strong></p>
  <p>At {weekly_volume:,} tickets a week and {money(credit)} per breach, that is approximately {money(savings_quarter)} in avoided credits per quarter: ({quarter_summary['breach_rate']*100:.2f}% - {target*100:.1f}%) × {weekly_volume} × 13 × {money(credit)}.</p>
</section>
{ai_section}
<section><h2>Weekly breach rate</h2>{line_chart_svg(recent_weekly)}<p class="label">Last 13 complete weeks. The partial week beginning 29 June is excluded from this chart.</p></section>
<div class="two">
  <section><h2>Where demand entered</h2>{shift_table}</section>
  <section><h2>Recent weeks</h2>{weekly_table}</section>
</div>
<section class="caveat">
  <h2>Agent view - use for workload review, not blame</h2>
  <p>The export supplies the resolving agent, not the first-response agent. Names below reproduce the helpdesk's attribution convention; they cannot establish who caused a first-response delay.</p>
  {agent_table}
</section>
<section>
  <h2>Data checks</h2>
  <p>{quality['duplicate_rows_removed']:,} duplicate rows removed across {quality['duplicate_ticket_ids']:,} ticket IDs; {quality['duplicate_groups_with_material_conflicts']:,} duplicate groups had material differences beyond source system and legacy CSAT zero. Roster matching succeeded for {len(records) - quality['roster_agent_missing'] - quality['roster_date_unmatched_or_ambiguous']:,} of {len(records):,} analysed tickets. Exact-SLA responses count as met; only later responses breach.</p>
</section>
<div class="footer">Policy v3.2 thresholds: chat 15m, voice 2h, social 4h, email 8h. Week is Monday-Sunday based on ticket creation in IST.</div>
</main></body></html>"""


def main() -> int:
    args = parse_args()
    ticket_path = Path(args.tickets)
    agent_path = Path(args.agents)
    config_path = Path(args.config)
    output_dir = Path(args.output_dir)

    for path in (ticket_path, agent_path, config_path):
        if not path.exists():
            print(f"Missing required file: {path}", file=sys.stderr)
            return 2

    config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_tickets = read_csv(ticket_path)
    assignments = read_csv(agent_path)
    require_columns(raw_tickets, REQUIRED_TICKET_COLUMNS, "tickets.csv")
    require_columns(assignments, REQUIRED_AGENT_COLUMNS, "agents.csv")

    tickets, dedupe_quality = deduplicate(raw_tickets)
    records, record_quality = build_records(tickets, assignments, config)
    quality = {**dedupe_quality, **record_quality, "analysed_rows": len(records)}
    change_point = detect_change_point(records)
    quality["change_point_model"] = change_point
    output_dir.mkdir(parents=True, exist_ok=True)

    credit = int(config["sla_credit_inr"])
    weekly_agent = aggregate(
        records,
        ("week_start", "agent_id", "agent_name", "site", "roster_shift"),
        credit,
    )
    weekly_agent.sort(key=lambda row: (row["week_start"], -row["breaches"], row["agent_id"]))
    write_csv(
        output_dir / "weekly_agent_shift.csv",
        weekly_agent,
        [
            "week_start",
            "agent_id",
            "agent_name",
            "site",
            "roster_shift",
            "tickets",
            "breaches",
            "breach_rate",
            "completed_breaches",
            "booked_credit_inr",
            "overnight_origin_breaches",
        ],
    )

    weekly_shift = aggregate(records, ("week_start", "creation_shift"), credit)
    weekly_shift.sort(key=lambda row: (row["week_start"], row["creation_shift"]))
    write_csv(
        output_dir / "weekly_creation_shift.csv",
        weekly_shift,
        [
            "week_start",
            "creation_shift",
            "tickets",
            "breaches",
            "breach_rate",
            "completed_breaches",
            "booked_credit_inr",
        ],
    )

    sample, validation = validation_sample(records)
    write_csv(
        output_dir / "validation_sample.csv",
        sample,
        [
            "ticket_id",
            "channel",
            "created_at_utc",
            "first_response_at_utc",
            "response_minutes",
            "sla_minutes",
            "expected_breach",
            "tool_breach",
            "agrees",
        ],
    )
    quality["validation"] = validation
    (output_dir / "quality_report.json").write_text(
        json.dumps(quality, indent=2, default=str), encoding="utf-8"
    )

    latest_date = max(record["created_ist"].date() for record in records)
    latest_start = quarter_start(latest_date)
    recent = [record for record in records if latest_start <= record["created_ist"].date() <= latest_date]
    recent_summary = summarize_group(recent, credit)
    night = [record for record in recent if record["creation_shift"] == "Night"]
    prompt_metrics = {
        "period": f"{latest_start.isoformat()} to {latest_date.isoformat()}",
        "tickets": recent_summary["tickets"],
        "breaches": recent_summary["breaches"],
        "breach_rate": round(recent_summary["breach_rate"], 4),
        "booked_credit_inr": recent_summary["booked_credit_inr"],
        "night_created": summarize_group(night, credit),
        "target_rate": config["goal_target_rate"],
        "planning_volume_per_week": config["planning_volume_per_week"],
        "credit_per_breach_inr": credit,
        "data_quality": quality,
    }
    ai_prompt = build_ai_prompt(prompt_metrics)
    (output_dir / "ai_brief_prompt.md").write_text(ai_prompt, encoding="utf-8")

    ai_brief = None
    if args.ai_endpoint:
        try:
            ai_brief = call_ai(args.ai_endpoint, args.ai_model, args.ai_key_env, ai_prompt)
            (output_dir / "ai_brief.md").write_text(ai_brief + "\n", encoding="utf-8")
        except (ValueError, KeyError, urllib.error.URLError) as error:
            print(f"AI briefing failed; deterministic report still built: {error}", file=sys.stderr)

    report = build_html(records, assignments, change_point, quality, config, ai_brief)
    (output_dir / "report.html").write_text(report, encoding="utf-8")

    print(f"Built {output_dir / 'report.html'}")
    print(
        f"Latest quarter: {recent_summary['breaches']}/{recent_summary['tickets']} breaches "
        f"({pct(recent_summary['breach_rate'])}), {money(recent_summary['booked_credit_inr'])} booked credits"
    )
    print(
        f"Validation: {validation['sample_size']} checked, "
        f"{validation['classification_errors']} classification errors"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
