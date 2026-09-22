# Social Media Campaign Manager

Owns the public distribution funnel for work made elsewhere in Imprint:
campaign context, platform-native drafts, variants, cadence schedules, clip
briefs and supported publishing actions. Its durable delivery ledger prevents
duplicate clicks and refuses to guess after an ambiguous API outcome. Its
public functions are exported by `agents.social`.

Platform clients, queue state and storage live in this package; credentials
remain in the app environment and are never persisted. User guidance:
`docs/agents/social.md`.  Run focused coverage with `pytest tests/test_social.py`.

## Files

- `__init__.py` — public surface: re-exports `ANGLES`, `SUBJECT_KINDS`,
  `build_clip_brief_messages`, `build_post_messages`, `over_limit` and
  `split_variants` from `agent.py`.
- `agent.py` — the drafting engine, and the single owner of the promotion
  funnel that other modes previously half-implemented on their own (the
  Publish mode's quote graphics, Creator's promo post draft). `SUBJECT_KINDS`
  (book / release / product / gig / other) and `ANGLES` (launch,
  behind_the_scenes, excerpt, value, question, milestone) are the two axes a
  campaign is built from — the kind shapes the prompt's framing, the angle
  shapes what the post is *for*. A fixed `SYSTEM` prompt hard-bans inventing
  reviews, testimonials, endorsements, sales figures, chart positions,
  follower counts or press quotes; bans writing in the voice of a named
  third party; bans engagement bait ("comment YES", fake urgency/scarcity);
  and caps hashtag use to a few specific tags rather than a wall of generic
  ones. `build_post_messages()` assembles one platform-specific prompt,
  pulling per-platform tone/length guidance from `agents/social/
  platforms.py`'s `Platform` (used verbatim, on the reasoning that
  Reddit penalizes anything reading as marketing, Pinterest behaves like a
  search engine, and X gives about seven words before a scroll) and can
  request several genuinely-different variants in one call, separated by a
  `---` line. `build_clip_brief_messages()` produces a single self-contained
  topic sentence handed to the Video mode's own script stage — Social asks
  for a clip, it does not write video scripts itself. `split_variants()`
  parses a `---`-separated response, falling back to treating the whole
  response as one variant if the model didn't follow the separator
  convention (an unusable format is a lesser failure than dropping a usable
  post). `over_limit()` checks a drafted post's length against
  `Platform.limit` and returns the character overage (0 if it fits), since
  models overshoot a stated limit often enough to need a hard check before
  posting.
- `recommendations.py` — registers this agent's `RECOMMENDATION_PROFILE` (an
  `AgentProfile` from `services.recommendations`) with the provider
  recommendation engine: task tags `social`/`marketing`/`creative`, weighted
  toward cost (.21) and speed (.19), with per-provider affinity scores from
  openai (.98) down to ollama (.68).
- `store.py` — campaign/post persistence, observed metrics and cadence.
- `queue.py` — one durable delivery job per post, atomic claim, local
  idempotency, safe/uncertain retry states and restart reconciliation.
- `publishing.py` — direct Reddit, Pinterest and YouTube adapters plus the
  readiness explanations for drafting-only platforms.
- `panel.py` — the complete Social workspace and guarded request lifecycles.
