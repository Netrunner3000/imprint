# Uncertainty and decisions

> **Outcome:** distinguish descriptive noise from comparable/replicated evidence
> and choose one action: stop, repair, repeat, or scale.

## Prerequisites

- Raw counts and stable stage definitions.
- Pre-registered primary metric, minimum meaningful change, window, and rules.
- Comparable baseline/treatment or an explicitly observational cohort.

## Read rates with uncertainty

Always display `events / eligible total` beside a rate. For proportions, a 95%
interval communicates the range compatible with the observed sample under its
assumptions. For skewed revenue/time, show count, median, and range or a suitable
bootstrap interval. An interval does not repair biased targeting, missing data,
seasonality, or a confounded comparison.

**No evidence of improvement** is not the same as **evidence of no meaningful
improvement**. A small sample can be compatible with both benefit and harm.

## Decision table

| Decision | Evidence pattern | Next action |
|---|---|---|
| Stop | Prewritten stop rule, negative economics, unacceptable harm/risk | Archive hypothesis and preserve learning |
| Repair | A specific funnel/fulfilment stage fails | Change that variable; create a new cohort |
| Repeat | Direction is promising but uncertainty/design is insufficient | Repeat same comparison in a fixed new window |
| Scale | Meaningful positive economics and quality repeat | Increase one resource/automation level, then remeasure |

## Worked example

Baseline: 8/200 signups. Variant: 12/200. Observed difference: 2 percentage
points. Minimum meaningful change was 2 points, but the intervals overlap widely
and this is the first window.

Tempting wrong conclusion: “A 50% relative lift proves the variant.”

Correct next decision: **Repeat** the same comparison with comparable allocation.
If the variant repeats, economics and quality still must pass before scaling.

## Decision record

```text
Decision: [stop / repair / repeat / scale]
Evidence type and sufficiency:
Raw counts, rates, intervals, and cutoff:
Cash/economic contribution and human time:
Quality/harm guardrails:
Constraint:
Alternative explanations:
One next change:
Next window and prewritten rules:
```

## Bias checks

- Did we peek repeatedly and stop at a flattering moment?
- Were variants allocated to comparable people/times?
- Did seasonality, price, channel, or audience change simultaneously?
- Were zero-result campaigns, refunds, failures, and missing rows kept?
- Were many variants examined and only the best reported?
- Is the observed difference large enough to matter economically?

## Verification

- [ ] Decision follows the prewritten rule or deviation is documented.
- [ ] Language matches observational versus controlled design.
- [ ] Raw counts and uncertainty remain visible.
- [ ] Scaling requires replication, positive economic contribution, and quality.

## Common failures

**Highest observed rate = winner:** compare uncertainty and meaningful effect.  
**More volume fixes conversion:** repair the constrained stage first.  
**One exceptional day:** separate and repeat the cohort.

## Next action

Test promotion against [Automation maturity and review](36-automation-review.md).
