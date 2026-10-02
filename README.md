# Vireo SLA Monitor

A small weekly first-response SLA report for Vireo Audio. It converts the API export from UTC to IST, removes migration duplicates, applies the policy's channel-specific targets, joins the dated agent roster, and produces a browser report plus auditable CSVs.

The SLA calculations are deterministic. A lightweight local change-point model assists diagnosis by finding the strongest structural break in daily breach outcomes. An optional AI call can turn aggregate metrics into a short operating brief; raw customer messages and agent notes are never sent.

## Start on a clean machine

Requirements: Python 3.11 or newer. There are no Python packages to install.

1. Put the supplied files here:

   ```text
   data/tickets.csv
   data/agents.csv
   ```

2. Run:

   ```bash
   python3 app.py
   ```

3. Open `output/report.html` in a browser.

To use files elsewhere:

```bash
python3 app.py --tickets /path/to/tickets.csv --agents /path/to/agents.csv --output-dir output
```

## Outputs

- `output/report.html`: management view with the latest-quarter goal, weekly trend, shift view, and recorded-agent view.
- `output/weekly_agent_shift.csv`: one row per week and resolving agent assignment.
- `output/weekly_creation_shift.csv`: one row per week and ticket-created shift.
- `output/validation_sample.csv`: 120-ticket stratified arithmetic check.
- `output/quality_report.json`: duplicates, roster matching, skipped rows, and observed validation error rate.
- `output/ai_brief_prompt.md`: aggregate-only prompt that can be reviewed before any model call.

## Repository layout

```text
.
├── app.py
├── config.json
├── README.md
├── submission-form.md
├── docs/
│   ├── ai-use-and-iterations.md
│   ├── decisions-and-limitations.md
│   ├── memo-to-neha.md
│   └── validation.md
└── tests/
    └── test_app.py
```

The supplied source data and generated agent-level outputs are intentionally not committed.

## How AI assists

The default run includes a local Bernoulli change-point model. It requires no package, model download, or API key. On the supplied pack it independently detects **30 June 2025** as the strongest regime change: breach rate moves from 9.2% before the split to 25.0% after it. The dated roster separately shows Night coverage ending at the same point.

SLA classification remains explicit policy logic, so a model cannot silently redefine a breach.

### Optional AI briefing

No AI API is called by default. To add a model-written brief, use an OpenAI-compatible chat endpoint:

```bash
export VIREO_AI_API_KEY='your-key'
python3 app.py \
  --ai-endpoint 'https://your-provider.example/v1/chat/completions' \
  --ai-model 'your-model'
```

The API receives only aggregate metrics and validation metadata. The deterministic report is still produced if the optional call fails.

## Test

```bash
python3 -m unittest discover -s tests -v
```

For the supplied pack, the run also performs a deterministic stratified audit of 120 tickets: 15 breached and 15 met tickets for each of the four channels. The observed SLA-classification error rate is 0/120. This does not validate causal agent attribution because the export contains the resolving agent, not the first-response agent.

## Reporting decisions

- Timestamps are parsed as UTC and shifted by +05:30 before week and shift assignment.
- A response exactly at the target is met; only a response later than the target breaches.
- Duplicate `ticket_id` rows prefer the current `helpdesk` record. The supplied pack contains 616 migration duplicates and no material conflicts beyond source system and legacy CSAT zero.
- The roster is joined on the first-response date in IST, using inclusive `from_date` and `to_date`.
- Weeks start Monday and are assigned from the ticket-created date in IST.
- The requested agent view is labelled **recorded agent**. It reproduces the policy's standard attribution to the resolving agent but does not claim that person caused the delay.
- Shift is shown two ways: the resolving agent's roster shift and the shift in which demand entered the queue. The second view is the actionable one for coverage.
- Breach rate uses all tickets with a first response. Booked credit uses only resolved or closed breached tickets because policy says the credit issues on resolution.

See `docs/decisions-and-limitations.md` for rationale and known limitations.

## Cost

Default mode uses a local model and no paid calls: ₹0 per run and ₹0 per month. At Vireo's stated volume, `650 × 52 ÷ 12 ≈ 2,817` tickets per month are processed locally for ₹0. Optional generative-AI cost depends on the endpoint and model selected.

## Data handling

`data/` and `output/` are intentionally excluded from Git. Do not publish the source exports or derived agent-level reports in a public repository.
