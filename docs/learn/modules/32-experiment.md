# Design a fair experiment

> **Outcome:** pre-register one comparison, primary metric, minimum meaningful
> change, fixed sample/window, guardrails, and decision rules before results.

## Prerequisites

- One stable offer and qualified-opportunity definition.
- Baseline evidence or an explicit manual-proof cohort.
- A data collection plan that keeps failures and missing values.

## Experiment card

```text
Experiment ID and owner:
Question / hypothesis:
Evidence passport used:
Buyer, offer, channel, geography:
Baseline/control:
Treatment/one changed variable:
Assignment or matched-comparison method:
Primary metric (numerator / denominator):
Quality or harm guardrail:
Minimum meaningful change:
Fixed sample and/or window:
Missing-data and exclusion rules:
Full cost and human-time fields:
Stop rule:
Repair rule:
Repeat rule:
Scale rule:
Next review date:
```

## Design rules

1. Change one main variable: audience, offer, price, creative, or channel.
2. Use random assignment when practical; otherwise match timing/audience and
   label the comparison observational.
3. Choose one primary metric before seeing results. Additional cuts are
   exploratory and require a fresh test.
4. Set the smallest difference that would matter economically; statistical
   difference alone may be too small to act on.
5. Fix the window/sample and avoid repeated peeking followed by stopping at the
   most flattering moment.
6. Keep zero-result rows, refunds, rejections, retries, and exclusions.

## Worked example

Two content angles receive 200 qualified destination visits each. Baseline gets
8 signups; variant gets 12.

```text
Baseline observed rate = 8 / 200  = 4%
Variant observed rate  = 12 / 200 = 6%
Observed difference    = 2 percentage points
```

Tempting wrong conclusion: “Variant wins by 50%.” The relative difference is
large-looking, but only twenty total actions occurred and uncertainty is wide.

Correct next decision: if the prewritten minimum effect was two points and the
quality guardrail passed, repeat the same allocation in another fixed window;
do not scale broadly or test five new variants simultaneously.

## Verification

- [ ] Experiment card was timestamped before results.
- [ ] Primary metric and qualified denominator are stable.
- [ ] One main variable changes and assignment/comparison limits are stated.
- [ ] Minimum meaningful change and stop/repair/repeat/scale rules are written.
- [ ] Failures, missing data, cost, and human time remain in the dataset.

## Common failures

**Many variants, one winner:** account for multiple comparisons or treat it as
exploration and confirm separately.  
**Seasonality/channel changed too:** comparison is confounded; do not use causal
language.  
**Stopping when the chart peaks:** follow the pre-registered window.

## Next action

Calculate the observed economics in [Unit economics](33-unit-economics.md).
