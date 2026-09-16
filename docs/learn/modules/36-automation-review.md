# Automation maturity and review

> **Outcome:** pass or fail one workflow against an observable promotion gate
> and finish the weekly review with a reversible next action.

## Prerequisites

- Complete economics, quality/error/rework rates, and replicated demand evidence.
- Stable inputs, acceptance checklist, run logging, spend/stop controls.
- Manual fallback and human owners for irreversible actions.

## Maturity ladder

| Level | Capability | Promotion gate |
|---|---|---|
| 0 · Instrumented | IDs, definitions, costs, time, outcomes can be recorded | One complete row without invented fields |
| 1 · Manual proof | Human finds, offers, fulfils, reviews | Paid and accepted outcome observed |
| 2 · Assisted | AI creates bounded drafts; every output reviewed | Positive economic contribution and acceptable corrections |
| 3 · Standardised | Reusable brief and acceptance checklist | Results reproduce across comparable runs |
| 4 · Batched | Multiple prepared outputs under one cap | Batch failure, rework, and spend stay within thresholds |
| 5 · Supervised workflow | Reversible queues/handoffs advance automatically | Observability, retry limits, idempotency, rollback, and human gates tested |
| 6 · Feedback-informed | Owned outcomes influence recommendations/allocation | Proven provenance, no proxy/revenue shortcut, periodic human audit |

## Promotion gate

```text
[ ] Demand evidence is observed, not model-generated
[ ] Primary metric and denominator are complete
[ ] Cash and owner-time costs are recorded
[ ] Quality pass, exception, and rework rates meet prewritten thresholds
[ ] Result replicated in a second comparable window/cohort
[ ] Human approval remains at irreversible steps
[ ] Failures are visible and recoverable
[ ] Rollback/manual fallback has been tested
[ ] Spend cap, retry limit, and stop condition are enforced
[ ] Platform, rights, consent, identity, public claims, and money gates remain
```

If any required box fails, keep the current level and repair the missing
evidence/control. Automation readiness is not the same as technical possibility.

## Automation payback worksheet

```text
Build hours × hourly value:
Direct build/tool cost:
Expected maintenance per period:
Manual minutes saved per accepted run:
Expected eligible runs per period:
Exception rate × recovery cost:
Quality difference and harm guardrail:
Break-even runs / payback range:
Rollback cost and tested fallback:
```

## Worked example — hypothetical scenario, not a forecast

A batching tool costs 20 hours to build at €40/hour plus €100. It saves 12
minutes per accepted run, but 10% of runs require a 30-minute recovery. At 50
runs/month, expected gross time saved is 10 hours and recovery is 2.5 hours:
7.5 hours/month before maintenance.

Tempting wrong conclusion: “It pays back in about three months, automate now.”

Correct next decision: the quality defect rate rose above the prewritten
threshold and rollback was never tested, so promotion fails regardless of the
time scenario. Fix observability/quality/fallback, then repeat.

## Weekly 20-minute review

1. Reconcile source files, costs, refunds, human time, and cutoff.
2. Find the largest verified funnel or fulfilment loss.
3. Choose exactly one: stop, repair, repeat, or scale.
4. Write the next experiment card and automation level.

```text
Decision:
Evidence and cutoff:
Constraint:
Next change:
Automation level and failed/passed gates:
Next review:
```

## Verification

- [ ] Promotion is blocked when provenance, cost, quality, replication, or rollback is missing.
- [ ] No identity/consent/rights/publishing/payment gate is automated away.
- [ ] Provider/platform concentration and manual fallback are reviewed.
- [ ] The next change is one reversible step with a review date.

## Common failures

**Frequent task = good automation:** ambiguity and error cost may dominate.  
**Positive cash contribution:** owner time and failure recovery can reverse it.  
**Feedback loop optimises revenue:** it must also preserve provenance, quality,
risk, stop rules, and human irreversible-action gates.

## Done when

The workflow has a documented maturity level, evidence-backed pass/fail record,
tested fallback, and one bounded next review—not an aspiration for autonomy.

## Next action

Return to the relevant Agent Academy module and implement only the approved
promotion step.
