# Funnels, attribution, and cohorts

> **Outcome:** build a raw-count funnel without invented attribution, mixed
> periods, incompatible currencies, or aggregate values presented as cohorts.

## Prerequisites

- Stable stage definitions and source tags.
- One observation window, population, offer, and channel per cohort.
- Owned reports retained with import filename and cutoff time.

## Minimum funnel

```text
Reach / eligible audience
  → qualified visit or opportunity
  → intended action
  → completed paid action
  → accepted or retained outcome
  → positive economic contribution
```

For every arrow, retain the raw numerator and denominator:

```text
Stage conversion = people/events reaching next stage ÷ prior-stage eligible count
Cumulative conversion = completed outcome ÷ original qualified count
Drop-off = prior stage − next stage
```

## Attribution rules

- Source-tag what you control; retain `unknown` when a platform report cannot
  connect the outcome.
- An assisted journey is not single-touch causation. Describe the observed path.
- Do not join impressions from one window to purchases from another.
- Do not combine a changed offer, price, audience, or channel into the old cohort.
- Do not infer retention from current/peak subscriber count. Use starts and
  still-paying members from the same cohort and period.
- Detect overlapping statement periods before summing imports.

## Collection sheet

```text
Cohort ID / variant:
Offer / audience / channel:
Window and cutoff:
Source tags and report files:
Eligible reach:
Qualified visits/opportunities:
Intended actions:
Completed purchases:
Accepted outcomes:
Refunds:
Retained at each defined period:
Unknown attribution count:
Currency / FX rate and date:
Missing, late, or excluded rows:
```

## Worked example

Raw rows: 1,000 platform impressions; 120 source-tagged page visits; 18 checkout
starts; 5 purchases. Two additional purchases appear in the store report with
unknown source. One statement is USD; Imprint API cost is EUR.

```text
Known visit → checkout rate = 18 / 120
Known visit → purchase rate = 5 / 120
Total purchases observed   = 7
Attributed-to-campaign     = 5, not 7
Combined contribution      = unavailable until FX rate/date and costs match
```

Tempting wrong conclusion: “The campaign generated seven sales and a 5.8%
conversion rate.”

Correct next decision: report five attributed and two unknown purchases, use
5/120 for the tagged path, reconcile currency/period/cost, and improve source
capture in the next cohort.

## Verification

- [ ] Every rate shows raw counts and matching eligible denominator.
- [ ] Cohort definition and cutoff are stable.
- [ ] Unknown attribution stays unknown.
- [ ] Currency conversion and overlapping periods are explicit.
- [ ] Retention uses cohort starts, not current aggregate subscribers.

## Common failures

**Posted = reached:** operational status is not exposure.  
**Average revenue per asset = conversion:** assets are not buyers/exposures.  
**Duplicate imports:** filename deduplication does not prove non-overlapping periods.

## Next action

Interpret the rates without overclaiming in [Uncertainty and decisions](35-uncertainty-decisions.md).
