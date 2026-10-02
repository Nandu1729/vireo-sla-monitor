# AI use and iterations

## Tools used

Codex with GPT-5 was used to inspect the supplied files, test interpretations of the policy, write and revise the Python implementation, create tests, and edit the final memo. No paid API calls were made by the submitted tool.

## Prompts used

The main working instruction was:

> Build the smallest reproducible weekly first-response SLA report. Read the email and policy first. Convert UTC to IST, use dated roster assignments, test migration duplicates, state a numeric business goal, and do not claim causality the export cannot support.

The main analytical follow-up was:

> Stress-test the claim that the Morning team is the source of most breaches. Compare the resolving agent's roster shift with the shift in which the ticket entered the queue, find structural change points, and quantify the SLA-credit impact.

## Version changes

### Initial version

The first interpretation followed the request literally: a weekly table grouped by resolving agent and roster shift.

### Data-correct version

UTC timestamps were converted to IST before assigning weeks and shifts. Migration duplicates were removed, and the roster was joined using its dated assignments.

### Operational version

The schema showed that `agent_id` identifies the resolving agent, not necessarily the person who sent the first response. The agent table was therefore relabelled as a recorded-owner view. A second view was added for the shift in which the ticket entered the queue. This changed the main conclusion from individual Morning-agent coaching to restoring Night coverage.

### Final version

A local Bernoulli change-point model was added to make the model-assisted diagnosis reproducible. Without receiving the roster-change date, it identifies 30 June 2025 as the strongest break in breach outcomes. Individual SLA classification remains deterministic and policy-based. An optional generative-AI briefing mode receives aggregate metrics only.

## Work discarded

A free-text Naive Bayes classifier was tested against the ticket category field. It achieved 80.6% held-out accuracy, but its disagreements were not associated with higher breach rates or transfer counts. It was removed because it added model risk without improving the operational decision.

A hosted dashboard, customer-level analysis, and a prescriptive agent score were also excluded. They either exceeded the time limit, increased privacy risk, or were not supported by the available attribution data.

## Where AI helped and where it did not

AI was useful for generating and checking implementation alternatives and for challenging the initial interpretation of the agent leaderboard. The final business conclusion comes from reproducible calculations and a tested statistical model, not from an unsupported model-generated assertion.

AI did not resolve the missing first-response-agent identity. That remains a source-data limitation and is stated throughout the report.
