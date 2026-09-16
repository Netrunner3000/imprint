# Unit economics

> **Outcome:** calculate cash and economic contribution for one comparable
> cohort, including failed output and owner time.

## Prerequisites

- Completed transactions and matching observation window.
- Refund, fee, provider, fulfilment, acquisition, contractor, and human-time data.
- One currency, or an explicit FX rate/date for every conversion.

## Core calculations

```text
Revenue = completed sales × average collected revenue per sale

Cash contribution = revenue − refunds − platform/payment fees
                    − AI/media cost − direct fulfilment cost
                    − paid acquisition − contractor cost

Economic contribution = cash contribution
                        − owner hours × chosen hourly value

Contribution margin = cash contribution ÷ revenue
Contribution per human hour = cash contribution ÷ hands-on hours
Effective cost per accepted output = all production/retry/correction cost
                                     ÷ accepted outputs
```

Do not call either contribution “profit” without handling fixed costs, tax,
equipment, financing, and the accounting definition required for that claim.

## Contribution worksheet

```text
Cohort / period / currency:
Completed sales:             ____
Collected revenue:           ____
Refunds / chargebacks:      −____
Platform + payment fees:    −____
AI / image / speech / video:−____
Retries / discarded output: −____
Direct fulfilment:          −____
Paid acquisition:          −____
Contractors:               −____
Cash contribution:          ____
Owner hours:                ____
Chosen hourly value:        ____
Owner-time cost:            ____
Economic contribution:      ____
Accepted outcomes:          ____
Quality failures/revisions: ____
```

## Worked example — hypothetical scenario, not a forecast

Thirty qualified enquiries produce three €180 sales. One €30 refund, €54 fees,
€12 API spend, €45 other direct cost, and 7.5 owner hours valued at €30/hour:

```text
Revenue               = 3 × €180                         = €540
Cash contribution     = 540 − 30 − 54 − 12 − 45         = €399
Owner-time cost       = 7.5 × 30                         = €225
Economic contribution = 399 − 225                        = €174
Cash margin           = 399 / 540                        = 73.9%
Cash contribution/hour= 399 / 7.5                        = €53.20
```

Tempting wrong conclusion: “The margin is 74%, so automate and scale.”

Correct next decision: check whether acquisition, revisions, quality, and owner
hours repeat in another cohort; the economic cushion is much smaller than the
cash margin suggests.

## Break-even checks

```text
Unit cash contribution before acquisition
  = price − refunds/unit − percentage fees − direct unit costs

Maximum affordable acquisition cost
  = unit cash contribution before acquisition − required safety margin
```

## Verification

- [ ] Revenue is collected and periods/currencies match.
- [ ] Failed generations, retries, refunds, revisions, and owner time are included.
- [ ] Cash and economic contribution are reported separately.
- [ ] The result is descriptive of this cohort, not a forecast.

## Common failures

**API cost is tiny, therefore profitable:** acquisition, labour, fees, refunds,
and support may dominate.  
**USD receipts plus EUR spend:** withhold the combined total until an FX rate/date
is specified.  
**Revenue per post:** not conversion or unit economics without exposure, buyer,
cost, and acceptance denominators.

## Next action

Connect the stages and sources in [Funnels, attribution, and cohorts](34-funnels-attribution.md).
