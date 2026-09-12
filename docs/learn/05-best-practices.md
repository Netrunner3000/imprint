# 5 · Operate safely

> The best automation is bounded: known input, known cost, observable output,
> explicit approval, and a failure state that does not silently publish.

## Quality before volume

Define acceptance before you generate. A useful checklist contains observable
criteria: required sections exist, names and numbers match the source, links
work, the page responds at phone width, quoted text is exact, audio pronunciation
is approved, or the asset meets the buyer's dimensions.

Generate the smallest unit you can judge. Approve one scene before a chapter,
one voice sample before a novel, one clip before a campaign, and one client
delivery before a batch. Cheap rejection is a feature.

Keep the human review close to the risk:

| Risk | Required review |
|---|---|
| Factual or financial claim | Check against a named, current source. |
| Quote or testimonial | Match the original exactly and confirm permission. |
| Client asset | Test against the written brief and acceptance criteria. |
| Public post | Check platform/community fit, disclosure, links, and claims. |
| Identity or persona | Confirm authorisation, consent, records, and disclosure. |
| Code | Run it, inspect dependencies, test keyboard/mobile/error states. |

## Prompt with constraints, not adjectives

A strong brief answers: **who is this for, what must happen, what inputs are
authoritative, what must be included, what must be avoided, and how will it be
judged?** “Premium and engaging” answers none of those.

Use one main change per run. In Draft, describe the next event or argument. In
Web, state page sections and behaviours. In Gigs, include required wording and
competitors to avoid. In Social, set one goal and one angle. In Creator, name
the account, segment, offer, and actual event.

Edit good output in place. Re-running an entire asset to fix one sentence costs
more, takes longer, and can damage the parts already approved.

## Choose providers and models deliberately

Start with **Use Recommended**. Change the route only when you have a measurable
need: better adherence, larger context, lower latency, lower cost, local privacy,
or a media capability the current route lacks.

Compare routes on the same small input and acceptance checklist. Record:

- pass/fail and the reason;
- human correction minutes;
- request cost and latency;
- policy or format failures;
- whether the output remained usable downstream.

The cheapest request is not cheapest if correction time doubles. The strongest
model is wasteful if a smaller model passes the same checklist.

Text providers can prepare scripts and prompts but cannot automatically become
video providers. Imprint shows a media model only when it has a real output
adapter, key requirement, duration/aspect rules, pricing treatment, polling,
download, and failure path.

## Money and budget controls

- Set session and daily caps before beginning work.
- Estimate before every batch, image set, narration, or video.
- Treat an unpriced action as an unknown liability, not €0.
- Review Cost History weekly and reconcile material differences with the
  provider account.
- Include failed attempts and discarded output in unit economics.
- Keep acquisition spend and fulfilment cost beside API spend; token cost is
  often not the largest cost.

An estimate authorises a reserve; it does not guarantee the provider's final
invoice. Currency conversion, token counting, duration, retries, and provider
reporting can differ.

## Cancellation and long-running work

**Stop means “request cancellation,” not “reverse the charge.”** Local text
streaming and the assembled video pipeline can stop cooperatively. A separate
audiobook process may leave completed chunks. Some direct video providers have
no safe cancellation path after accepting a job; Imprint continues monitoring
so the paid result is not lost. Higgsfield cancellation can depend on whether
the request is still queued or already processing.

Before a long job:

1. verify the input and output folders;
2. generate a small sample;
3. inspect the estimate and remaining cap;
4. keep the computer and connection available when the provider requires
   polling or temporary-file download;
5. know where partial files and logs will appear.

Press Stop once and read the status. Repeated clicks cannot cancel a provider
operation that has no cancellation endpoint.

## Publishing and platform safety

Nothing should leave the machine invisibly. Imprint prepares schedules and can
post only through explicitly configured integrations; it has no unattended
“publish all” business loop. Review each destination's current terms and the
specific community rules immediately before publishing because they change.

Avoid fabricated evidence: reviews, testimonials, awards, rankings, customers,
sales, scarcity, and performance. Generated marketing language is especially
likely to turn a desired claim into an asserted fact. Delete or substantiate it.

For AI-assisted books, media, music, ads, and persona content, check current
disclosure, copyright, likeness, voice, and synthetic-media requirements. An
API accepting a request does not grant rights to the input or output.

## Creator, managed account, and adult-platform safeguards

- Use `managed` only with recorded authorisation.
- Use `persona` only with an accurate disclosure.
- Keep performer identity, age, consent, release, and records location current.
- Never upload an unauthorised likeness, cloned voice, or private material.
- Do not use Creator drafts to impersonate a specific real person in a live
  conversation.
- Higgsfield teaser generation is subject to its own moderation and is designed
  here for safe-for-work promotion, not explicit content.
- Treat the OnlyFans opportunity dashboard as directional unless the source
  note identifies real configured inputs; sample data is demonstration only.

The app can enforce some missing-field gates. It cannot determine whether a
record is legally sufficient or whether real-world consent remains valid.

## Data, secrets, and backups

Application data lives under `~/Library/Application Support/Imprint/`, including
the database, saved content, settings, logs, and private environment file.

- Back up this directory on a tested schedule.
- Keep API keys only in the private environment/settings flow.
- Never paste secrets into prompts; providers receive prompt content.
- Do not commit client briefs, identity records, unreleased work, or earnings
  exports to a public repository.
- Confirm an export's destination before sharing it.
- Removing the app does not necessarily remove Application Support data; treat
  deletion and migration as separate operations.

## A preflight for paid or public actions

```text
[ ] Correct project, account, and destination
[ ] Authoritative inputs and rights confirmed
[ ] Provider/model capability is real
[ ] Estimate understood; cap has room
[ ] Acceptance checklist written
[ ] Human approval before publish/delivery
[ ] Output and partial-output location known
[ ] Primary metric, denominator, window, and stop rule recorded
```

---

Next: [Measure & improve](06-measure-and-improve.md) · If a control fails, use [Troubleshooting](07-troubleshooting.md)
