# Evidence before production

> **Outcome:** complete an evidence passport and know exactly which claim or
> next action the underlying data permits.

## Prerequisites

- One candidate buyer problem or opportunity.
- Access to its original source, date, population/geography, and raw counts.
- Willingness to write `UNAVAILABLE` instead of filling gaps with a model.

## Evidence type

| Label | Definition | What it permits |
|---|---|---|
| `OBSERVED` | Direct owned event or transaction | Describe that event in its source/window |
| `DERIVED` | Arithmetic from observed inputs | Report the calculation with raw inputs |
| `ESTIMATE` | Cost/time approximation with assumptions | Budget or compare scenarios cautiously |
| `PROXY` | External behavior related to—but not equal to—purchase intent | Prioritise a small test |
| `HYPOTHESIS` | Proposed explanation, offer, price, or test | Collect evidence; do not assert it |
| `MODEL-GENERATED` | AI-produced idea or interpretation | Generate candidates only |
| `DEMO` | Illustrative interface data | Learn the screen only |
| `UNAVAILABLE` | A required field is missing | Withhold the dependent conclusion |

## Data sufficiency

Use a second, independent label:

- **Incomplete:** source, denominator, period, population, currency, or material
  cost is missing.
- **Descriptive only:** observed but too thin or uncontrolled for comparison.
- **Comparable:** same definition/window with a valid baseline or allocation.
- **Replicated:** the result repeated in another predefined comparable cohort.

A generic confidence badge based on five rows is not scientific. State the
count and the missing design information instead.

Observed transactions are the strongest direct income evidence, but even
observed transactions need matching qualified opportunities, period, refunds,
costs, and acceptance state before they support conversion or contribution.

## Evidence passport

```text
Metric or claim:
Evidence type:
Data sufficiency:
Source and source file:
Observed at:
Window:
Population / geography:
Numerator:
Denominator:
Currency and FX rate/date:
Missing or excluded records:
Comparison/baseline:
Interpretation allowed:
Interpretation not allowed:
```

## Worked example

Raw input: an OnlyFans demonstration table shows Demand 76, Competition 54,
Revenue fit 84, observed on a displayed date. No account exposures, profile
visits, purchases, receipts, or costs exist.

- Evidence type: `DEMO` (or `PROXY` only if backed by a configured real source).
- Sufficiency: **Incomplete** for demand, conversion, revenue, or profit.
- Allowed: “This row can be prioritised for a bounded test.”
- Tempting wrong conclusion: “This niche has 84% monetization potential.”
- Correct next decision: define one offer and collect owned denominated behavior.

## Verification

- [ ] The original source, date, window, and population are preserved.
- [ ] Every rate has numerator and denominator.
- [ ] Demo/proxy/model output has not been relabelled observed.
- [ ] The allowed and prohibited interpretations are explicit.

## Common failures

**A number looks objective:** precision does not determine evidence type.  
**Unknown becomes zero:** use `UNAVAILABLE`; zero is an observed value.  
**Net receipts become profit:** costs and matching periods are still required.

## Next action

Turn the supported problem into [one measurable offer](31-offer.md).
