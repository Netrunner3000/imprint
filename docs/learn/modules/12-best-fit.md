# Providers, models, and Best Fit

> **Outcome:** choose an eligible route and explain what the recommendation
> optimises, how confident it is, and why an override might be reasonable.

## Prerequisites

- Open a dedicated agent that exposes provider/model selectors.
- Define the task or format first where possible; recommendations recalculate
  when those requirements change.

## The two recommendations

**Provider BEST FIT** marks the provider containing the highest-scoring eligible
model for the current agent and task. **Model BEST FIT** marks the best eligible
model *inside the provider currently selected*. If you manually choose another
provider, the model menu still gives useful guidance within that choice.

**BEST AVAILABLE** or setup-target wording means the ideal route is not fully
ready under current keys, permissions, capability, or budget. It is a setup
recommendation, not proof that pressing the action will work now.

## How ranking works

Imprint first removes incompatible, retired, unavailable, disallowed, and
over-budget candidates. It then scores the remaining routes against the agent's
maintained quality, reliability, cost, speed, context, and privacy priorities.
The process is deterministic and local; opening a menu does not make a paid call.

## Walkthrough

1. Select the task, format, duration, or aspect controls that affect capability.
2. Open the provider menu and locate the recommendation badge.
3. Read the provider tooltip: task, strongest dimensions, score, confidence,
   availability, and setup-target caveat should be visible.
4. Select a different provider deliberately. Open the model menu and note that
   its badge now identifies the best model within your selected provider.
5. Check the API-key/status and permission state before treating any route as
   executable.
6. For a meaningful override, compare the same small input and acceptance
   checklist. Record pass/fail, correction minutes, latency, retries, and cost.

## Confidence does and does not mean

Recommendation confidence describes the completeness and separation of local
capability evidence. It is not confidence that the output will sell, comply
with every current platform rule, or outperform on your specific material.

## Sensible overrides

- local privacy or offline operation;
- a required media capability, context size, latency, or format;
- measured lower effective cost after retries and correction time;
- temporary provider reliability;
- an approved client/account restriction.

“Strongest model” or “cheapest token” alone is not a complete decision.

## Verification

- [ ] I can distinguish provider-best overall from model-best within provider.
- [ ] I checked eligibility and setup-target wording.
- [ ] Any override has a measurable reason and a small comparison plan.
- [ ] I did not interpret recommendation confidence as market evidence.

## Common failures

**No badge:** the catalog may lack comparable eligible candidates; inspect the
tooltip/status rather than assuming the first item is best.  
**A text provider appears absent from video:** text models can write a script but
are not automatically video-rendering endpoints.  
**The route changed after a control:** this is expected when task capability,
budget, permission, duration, or aspect requirements change.

## Next action

Confirm [Access, permissions, and privacy](13-access-privacy.md), then compare
effective cost in [Unit economics](33-unit-economics.md).
