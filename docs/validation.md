# Validation

## What was checked

The supplied export contains 11,816 rows and 11,200 unique ticket IDs. The tool removes 616 migration duplicates before reporting. Every deduplicated ticket matched exactly one dated roster assignment, and no ticket was skipped for an invalid timestamp.

## SLA classification sample

A deterministic stratified sample contains 120 tickets:

- 15 breached and 15 met chat tickets
- 15 breached and 15 met email tickets
- 15 breached and 15 met social tickets
- 15 breached and 15 met voice tickets

For each sampled ticket, response time was independently recalculated by subtracting `created_at` from `first_response_at` in UTC and then compared with the policy threshold. The recalculation agreed with the tool for 120 of 120 tickets.

**Observed classification error rate: 0/120, or 0.0%.**

This does not prove the true error rate is zero. With no observed errors in 120 checks, the rule-of-three approximate 95% upper bound is 3/120, or 2.5%.

The generated row-level evidence is written to `output/validation_sample.csv`, and the summary is written to `output/quality_report.json`.

## Automated tests

Run:

```bash
python3 -m unittest discover -s tests -v
```

The five tests cover:

- UTC-to-IST conversion
- 06:00, 14:00, and 22:00 shift boundaries
- preference for the current helpdesk copy of a migration duplicate
- exact SLA threshold counted as met and one minute late counted as breached
- a synthetic 10%-to-80% regime change located exactly by the change-point model

## Model cross-check

The local Bernoulli change-point model was not given the roster-change date. It independently selected 30 June 2025 as the strongest split, with breach rates of 9.2% before and 25.0% after. The roster separately shows the two Night assignments ending on 29 June 2025.

## Known cases the tool cannot resolve

The ticket export identifies the resolving agent, not necessarily the human who sent the first response. The agent view can therefore reproduce Vireo's reporting convention but cannot establish individual causality. That limitation is not included in the 0/120 SLA-classification error rate.

The tool also cannot model leave, concurrency, queue depth, callback attempts, or occupancy because those fields are absent from the pack.
