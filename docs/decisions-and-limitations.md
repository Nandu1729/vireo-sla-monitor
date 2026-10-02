# Decisions and limitations

## What I changed in the ask

Neha asked for a weekly agent and shift breach report. The tool provides it, but I changed the interpretation of the agent ranking: it is a **recorded-owner view**, not a performance or disciplinary view.

The reason is structural. `agent_id` identifies the agent who resolved the ticket, while first-response SLA measures a different event. The export has no first-response agent ID. Treating the resolver as the person who caused the first-response delay would create false precision and reinforce the Morning team's concern in the email thread.

I added a second, operational shift view based on when the ticket entered the queue in IST. It reveals the coverage problem hidden by the standard attribution.

## Main finding

- The dated roster has two Night assignments through 29 June 2025 and none after that date.
- Before the change, the overall breach rate was 9.2%; in the following half-year it was 24.8%.
- In April-June 2026, 563 of 2,230 tickets breached: 25.2%.
- Tickets created during Night breached at 80.4% (405 of 504).
- Morning resolvers were recorded against 482 breaches; 394 of them, or 81.7%, entered the queue during Night.
- Completed-ticket SLA credits were ₹186,900 in the latest quarter.

The evidence supports a cost-neutral coverage pilot, not individual coaching as the first intervention.

The default tool also runs a Bernoulli change-point model over daily breach outcomes. Without being told the roster date, it selects 30 June 2025 as the strongest split, moving from 9.2% before to 25.0% after. The model is used for diagnosis; policy rules still determine whether each ticket breached.

## Business goal

Reduce the breach rate from 25.2% to 15.0% in 90 days without adding headcount by restoring overnight coverage and monitoring created-shift performance weekly.

At 650 tickets per week and ₹350 per breach:

```text
(25.2466% - 15.0%) × 650 × 13 × ₹350 = approximately ₹303,000 per quarter
```

This is gross avoided-credit run rate, not a forecast of cash collected. It assumes the volume and channel mix remain similar and breached tickets eventually resolve.

## Known limitations

- The export cannot identify the human who sent the first response. Agent causality is unknowable from this pack.
- The 15% target is an operating target, not a staffing simulation. The historical 9.2% baseline shows it is plausible, but a two-week pilot should confirm capacity.
- Fixed +05:30 conversion is correct for IST, which has no daylight-saving time.
- Future roster gaps or overlapping assignments are reported as data-quality failures; the tool does not guess.
- Open and pending breached tickets count in breach rate but not booked credits.
- The local change-point model finds one dominant structural break and does not explain causality by itself. The optional generative-AI endpoint follows the common chat-completions shape and was not called in this analysis. Provider-specific compatibility and cost are not validated.
- The report does not model queue concurrency, agent leave, occupancy, callback attempts, or channel-specific staffing requirements because those fields are absent.

## Deliberately left out

- Customer-, order-, product-, refund-, and replacement-level analysis. Those are useful but do not change the first-response coverage decision and increase privacy and scope risk.
- A free-text category classifier. A quick held-out experiment reached 80.6% accuracy, and its disagreements did not have a higher breach rate or transfer count. It was not reliable or useful enough to ship.
- A hosted database, login, scheduled email, or live helpdesk integration. A local, auditable run is more valuable within the five-hour cap.
- A prescriptive individual-agent score. The data cannot support it.
