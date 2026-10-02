# Submission form answers

## What did you build, and what business outcome does it move? State the number and the money.

I built an AI-assisted weekly first-response SLA monitor that converts UTC to IST, removes migration duplicates, joins dated roster assignments, applies each channel's policy target, and separates the resolving-agent view from the shift in which demand entered the queue. A local change-point model independently detects 30 June 2025 as the structural break in breach outcomes. The latest quarter is 563 breaches out of 2,230 tickets (25.2%). The goal is 15.0% in 90 days without adding headcount. At 650 tickets/week and ₹350 per breach, the gross opportunity is `(25.2466% - 15%) × 650 × 13 × ₹350 = approximately ₹303,000 per quarter`.

## What does one run cost, and what would a month cost at Vireo's volume (roughly 650 tickets a week)? Show the arithmetic. If you used no paid calls, say so.

₹0 per run and ₹0 per month in the default mode. The change-point model runs locally and no paid model/API calls were used. `650 × 52 ÷ 12 ≈ 2,817 tickets/month`; all are processed locally with Python's standard library, so `2,817 × ₹0 = ₹0`. An optional aggregate-only generative-AI endpoint is supported, but it was not used and its provider-specific cost is excluded.

## How do you know it works? Sample size, how you checked, error rate, and the kind of case it gets wrong.

I checked a deterministic stratified sample of 120 tickets: 15 breached and 15 met tickets for each of chat, email, voice, and social. I independently subtracted the UTC timestamps and compared the result with the policy threshold. The tool agreed on 120/120, an observed SLA-classification error rate of 0.0%. Unit tests cover UTC-to-IST conversion, all shift boundaries, duplicate preference, the exact-threshold rule, and a synthetic 10%-to-80% regime change that the model locates exactly. All 11,200 deduplicated tickets matched exactly one dated roster row. The known failure is causal agent attribution: the export identifies the resolving agent, not the first-response agent, so the tool cannot tell which person caused a delay.

## Did you change, narrow, or push back on the client's ask? What, when, and why.

Yes. I kept Neha's weekly agent and shift output but relabelled the agent table as “recorded agent,” not an individual performance score. I made that change after reading the schema and policy: `agent_id` is the resolver while the SLA concerns the first reply. I added a created-shift view because it is operationally actionable. That view shows the Morning team is inheriting an overnight problem: 394 of 482 Morning-recorded breaches in the latest quarter were created during Night. This avoids an unsupported disciplinary conclusion.

## What is wrong with what you are handing us? Be specific: bugs, shortcuts, things you know are off.

The data cannot identify the first-response agent, so individual causality is unknowable. The 15% target is not a staffing simulation; it is supported by the historical 9.2% baseline and should be tested with a two-week pilot. The tool does not model leave, concurrency, occupancy, callback attempts, or queue depth because those fields are absent. Open/pending breached tickets count in the breach rate but not booked credits. The optional AI integration uses a common chat-completions request shape but was not called against a provider, so provider compatibility and cost are unverified.

## What did you deliberately leave out, and why that rather than something else?

I left out customer/order/product analysis, refund and replacement audits, live helpdesk integration, hosting, login, and scheduled email. Those do not change the immediate first-response coverage decision and would consume the five-hour cap while adding privacy and deployment risk. I also left out a prescriptive agent score because the data cannot support it.

## Anything you built or found that nobody asked for?

The dated roster has no Night assignment after 29 June 2025 even though policy says Indore covers overnight. Night-created breaches rose from 10.3% before that change to about 79% afterward. SLA credits rose from ₹10,500 in June 2025 to ₹36,400 in July and then roughly ₹60,000-₹70,000 a month at higher volume. I also found 616 migration duplicates; failing to remove them overstates completed breach credits by ₹37,800 across the pack.

## What did you use AI for? Which tools and models, where they helped, where they wasted your time, what you threw away. Link your three-minute screen recording here.

I used Codex with GPT-5 to inspect the pack, challenge the initial agent-blame framing, write the Python/report code, draft tests, and compress the findings into the memo. The shipped tool uses a local Bernoulli change-point model to detect the strongest regime change, and can optionally use a generative model for an aggregate-only brief. AI helped most with tracing the contradiction between UTC timestamps, IST shifts, dated roster changes, and resolving-agent attribution. A free-text Naive Bayes experiment was wasted effort: it achieved 80.6% held-out category accuracy, but its disagreements did not predict breaches or transfers, so I discarded it. No paid API calls were made.

Screen recording: https://drive.google.com/file/d/1LqTUAcqli9p1YGzSmxwQgyq9TlERfiaW/view?usp=sharing

## Someone picks this up on Monday and you are unreachable. The three things they need to know.

1. Run `python3 app.py` after placing `tickets.csv` and `agents.csv` in `data/`; no packages or API key are required. 2. Use `weekly_creation_shift.csv` for operational action; the agent file names resolvers and must not be treated as proof of who caused a late first response. 3. Keep `data/` and `output/` out of the public repository because both contain internal and agent-level information.

## Honest hours spent. One number.

5

## Github Repo Link

https://github.com/Nandu1729/vireo-sla-monitor
