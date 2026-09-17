# Costs, estimates, and limits

> **Outcome:** bound a paid action, interpret its estimate honestly, and include
> retries and human correction in the cost of an accepted output.

## Prerequisites

- The provider/model and unit of work are selected.
- You know the current session and daily caps, plus any active project cap.
- For media, you know quantity, duration, aspect, resolution, and route.

## Cost states

| Label | Meaning | Decision allowed |
|---|---|---|
| Estimated request cost | Local preflight/reserve using known pricing inputs | Decide whether the attempt fits the cap |
| Last request cost | Best locally recorded post-request amount | Reconcile, but do not treat as provider invoice automatically |
| Session / daily / project | Recorded usage against guardrails | Stop or reduce scope before another request |
| Unpriced / unknown | No trustworthy local rate for this action | Investigate externally; never interpret as zero |

## Walkthrough

1. Set both session and daily caps before starting a long or batched job. If a
   named project is active, set its optional daily cap in **Settings → Projects**.
2. Select the final provider, model, quantity, duration, and format first.
3. Read the visible estimate or automatic reserve. If unpriced, stop and obtain
   a current provider quote/rate before authorising the work.
4. Start with one representative unit: short text, one image, one narration
   sample, or minimum practical video.
5. After completion, record retries, discarded generations, correction minutes,
   provider cost, and any external platform/fulfilment cost.
6. Reconcile material differences through **Cost History**, **Run Log**, and the
   provider's own record.

Project instructions add input tokens to each request and are included in the
preflight estimate. The project cap only counts locally recorded spend tagged
to that project; it is not a separate provider account or a provider invoice.

## Effective accepted-output cost

```text
Effective cost = API/media spend + retry spend
                 + correction hours × chosen hourly value
                 + other direct fulfilment cost

Effective cost per accepted output = Effective cost ÷ accepted outputs
```

A cheaper request can be the expensive workflow if its correction or failure
rate is higher. A stronger model is wasteful when a smaller one passes the same
acceptance checklist.

## Verification

- [ ] Both caps are set and the request fits with margin for one recovery step.
- [ ] Unknown pricing is visibly unresolved.
- [ ] Failed attempts and human correction are included.
- [ ] Material totals are reconciled with the provider/account source.

## Common failures

**Budget blocks the action:** reduce duration, quantity, input, or model cost;
do not remove the guardrail reflexively.  
**Stop was pressed but a charge remains:** accepted asynchronous jobs may be
non-cancellable; Stop is not a refund.  
**Token cost looks complete:** image, speech, video, acquisition, platform,
contractor, refund, and human-time costs may still dominate.

## Next action

Learn route-specific cost/cancellation in the relevant Agent Academy lesson,
then calculate complete economics in [Unit economics](33-unit-economics.md).
