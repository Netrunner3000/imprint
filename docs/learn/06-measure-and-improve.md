# 6 · Measure & improve

> **Outcome:** one weekly review converts Imprint activity into a decision:
> stop, repair, repeat, or scale.

Generation counts are not business results. The scoreboard must connect demand,
production, distribution, payment, quality, cost, and human time. Imprint owns
some of this data; platform exports or a small external sheet may be required
for the rest.

## The minimum scoreboard

Use one row per experiment cohort and never erase the raw counts.

| Field | Definition |
|---|---|
| **Cohort ID** | Stable name for one offer, audience, channel, and start date. |
| **Qualified opportunities** | People or visits that met the audience/channel definition. |
| **Intended actions** | Qualified replies, signups, booked calls, or checkout starts chosen in advance. |
| **Completed sales** | Collected transactions, not promises or invoices sent. |
| **Collected revenue** | Money actually received in the observation window. |
| **Refunds / chargebacks** | Value removed after sale. |
| **Platform / payment fees** | Transaction-linked fees. |
| **AI/API spend** | Text, image, video, speech, and retry cost from Cost History/provider records. |
| **Other variable cost** | Fulfilment, paid traffic, contractors, shipping, and related per-unit costs. |
| **Human hours** | Research, prompting, editing, QA, posting, support, revisions, and recovery. |
| **Quality failures** | Rejected deliveries, policy removals, unusable outputs, corrections, or missed criteria. |
| **Repeat / retained** | Buyers who return or subscribers still paying at the defined period. |

Then compute conversion rate, contribution, contribution margin, contribution
per human hour, refund rate, and retention using the equations in [Income
science](03-profit.md#the-five-equations).

## Where each observation comes from

| Observation | Imprint surface | Boundary |
|---|---|---|
| AI request spend | Right rail → Cost History | Reconcile important differences with the provider. |
| Book sales | Publisher → PublishDrive / Ingest KDP CSV | Current only after refresh/import; attribution may be limited. |
| Creator receipts | Creator → Earnings → Import CSV / Record Revenue | Imported net receipts are not profit when costs are unknown. |
| Creator source hypothesis | OnlyFans → Trends & Opportunities | Directional until tested; sample data is never an observation. |
| Social production/status | Social → Draft / Schedule | Posted status does not prove impressions, clicks, or sales. |
| Client order record | Gigs → Orders | Add fees, revisions, refunds, and time from the real platform. |
| Output inventory | Video Library, Audiobook Listen, project files | An output existing is not distribution or revenue. |

If the platform provides no supported API, export its report and retain the
source file. Unknown attribution should remain `unknown`; forced precision is
worse than missing data.

## The weekly 20-minute review

### 1. Reconcile actuals

Import current reports, record revenue/refunds, review Cost History, and add
human time. Mark the data cutoff. Do not compare cohorts with different cutoff
dates as if both were complete.

### 2. Find the constrained stage

```text
Qualified opportunity
  → intended action
  → completed sale
  → accepted/retained outcome
  → positive contribution
```

The largest verified loss is the constraint. Examples:

- Few qualified opportunities: targeting or distribution problem.
- Traffic but no intended action: promise, proof, trust, or page problem.
- Intended actions but no sale: offer, price, friction, or qualification problem.
- Sales but refunds/revisions: expectation or fulfilment problem.
- Positive sales but weak contribution/hour: scope, process, or automation problem.

### 3. Make exactly one decision

| Decision | When to use it | Next action |
|---|---|---|
| **Stop** | The pre-written stop rule fired or the risk is unacceptable. | Archive the hypothesis and state what was learned. |
| **Repair** | A specific funnel or fulfilment failure is visible. | Change that variable; start a new cohort. |
| **Repeat** | Result is promising but small or noisy. | Run the same test in another fixed window. |
| **Scale** | Positive contribution and acceptable quality repeat. | Increase one resource or automation level, then re-measure. |

Do not add volume to compensate for a broken stage. More posts do not fix an
offer people reach but do not want; faster generation does not fix refunds.

### 4. Write the next experiment card

Record the audience, observed problem, offer, channel, primary metric,
guardrails, window/sample, scale rule, and stop rule. Link it to the previous
cohort so the chain of reasoning remains inspectable.

## A model comparison protocol

Use this when model cost or quality is the suspected constraint.

1. Select 5–10 representative inputs that contain the hard cases.
2. Freeze the prompt, context, temperature/settings available, and acceptance
   checklist.
3. Run both models on the same inputs. Do not let the reviewer know which model
   produced which output when practical.
4. Record checklist pass rate, correction minutes, latency, and cost.
5. Choose the cheapest route that meets the quality threshold; keep the stronger
   model only for the failure class it solves.

This is a workflow test, not a general claim that one model is “best.” Provider
models and pricing change; re-run the test when the route materially changes.

## An automation audit

For each repeated step, ask:

```text
Frequency × human minutes × error cost × suitability for review
```

Good automation candidates are frequent, structured, low-ambiguity tasks with
a cheap review: formatting briefs, generating bounded variants, updating a
calendar, extracting known fields, or producing a first pass.

Poor candidates are rare, irreversible, high-context decisions where error is
expensive: consent, final client acceptance, money movement, legal sufficiency,
public factual claims, account recovery, or unattended publishing.

## Monthly portfolio review

Once a month, compare paths on the same four axes:

- observed contribution, not projected revenue;
- contribution per human hour;
- evidence strength and replication;
- concentration risk by buyer, provider, and platform.

Allocate the next small block of time and budget to the best-supported
constraint. Keep a limited exploration budget for new hypotheses. Do not call a
large catalogue diversified if all discovery and payment still depend on one
platform.

## The output of the review

A useful review ends with five lines:

```text
Decision:       [stop / repair / repeat / scale]
Evidence:       [counts, rates, contribution, time, cutoff]
Constraint:     [one stage]
Next change:    [one variable]
Next review:    [date and stop/scale rule]
```

That small feedback loop is the core of income automation. Without it, Imprint
can accelerate production while the business remains unmeasured.

---

Next: [Troubleshooting](07-troubleshooting.md) · Return to [Income science](03-profit.md)
