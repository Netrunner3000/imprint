# OnlyFans agent

Owns the OnlyFans venture boundary: authorised account context, consent-aware
operations, demand and saturation analysis, pricing hypotheses, owned revenue
analytics and campaign handoff to Creator.

It intentionally reuses Creator's drafting engine rather than maintaining a
second copy.  This project owns both its normalized trend engine (`trends.py`)
and dashboard (`panel.py`).  User guidance: `docs/agents/onlyfans.md`.

## Files

- `__init__.py` — the package's ownership boundary: sets `AGENT_KEY =
  "onlyfans"` and re-exports `OnlyFansDashboard` (from `panel.py`) and
  `format_creator_brief` (from `trends.py`) as the public surface.
- `trends.py` — the normalized market-signal engine. `Trend` is a frozen
  dataclass (momentum, search interest, saturation, monetization, format,
  pricing idea, risk, history, confidence) whose `opportunity` property
  computes a directional 0–100 index — weighted toward search interest (.30),
  momentum (.25) and monetization (.25), against saturation, and reduced for
  `High`/`Review` risk — explicitly documented as never a revenue estimate.
  Three adapter seams (`GoogleTrendsAdapter`, `DiscussionSignalsAdapter`,
  `AdultIndustryAdapter`) are all deliberately inert until an operator
  supplies credentials or a connector URL (`IMPRINT_TRENDS_CONNECTOR_URL`,
  `REDDIT_CLIENT_ID`/`X_BEARER_TOKEN`, `ADULT_TRENDS_FEED_URL`); each is
  wrapped in `load_trends()` so one failing source never takes down the
  others. When no adapter returns data, `load_trends()` falls back to an
  explicitly-labelled `_demo()` fixture set (seven sample content ideas,
  e.g. "POV mini-series", "Voice-note GFE"; one — "AI persona lore drop" —
  is flagged `High` risk with the note to "disclose synthetic media
  clearly"). `filter_trends()` sorts by opportunity within a category.
  `campaign_context()` / `format_creator_brief()` build the structured
  handoff to Creator (deliverables, pricing experiment, risk flag, evidence
  and confidence), always closing with a reminder to confirm consent, usage
  rights, platform policy and synthetic-media disclosure, and stating the
  handoff is a planning brief, not an automatic publishing approval.
  `onlyfans_business_metrics()` reads the user's own imported
  `creator_accounts` / `creator_earnings` / `creator_content` rows to report
  net receipts, subscriber counts and content-attributed revenue, and
  explicitly returns `profit_status: "Unavailable — operating costs are not
  recorded"` rather than presenting receipts as profit.
- `panel.py` — the PySide6 dashboard (`OnlyFansDashboard`), with two
  custom-painted widgets: `Sparkline` (trend velocity over the stored
  history) and `DemandSaturationChart` (a demand-vs-saturation scatter sized
  by opportunity). Five tabs: Overview (summary stats, both charts, and a
  "SAMPLE DATA" disclosure banner whenever live adapters aren't configured),
  Ranked Opportunities (a sortable 7-column table — Fit, Signal, Momentum,
  Demand, Competition, Revenue fit, Risk — with per-row evidence tooltips),
  Content Intelligence, Monetization Analytics (the imported actuals from
  `onlyfans_business_metrics()` plus a hypothesis-test-then-measure sequence
  and the same profit-status caveat), and Market Strategy (a bounded
  produce/measure/continue-or-stop plan per selected signal). Selecting a
  row and clicking "Create Campaign in Creator" (or double-clicking the row)
  emits a `campaign_requested` signal carrying the `campaign_context()`
  payload. Keeps a compatibility alias `CreatorTrendsDashboard =
  OnlyFansDashboard` for any code still importing the original name.
- `recommendations.py` — registers this agent's `RECOMMENDATION_PROFILE` (an
  `AgentProfile` from `services.recommendations`) with the provider
  recommendation engine: task tags `social`/`marketing`/`creative`, weighted
  toward reliability (.25) and speed (.15) above the engine defaults, with
  per-provider affinity scores (anthropic .98, openai .96, gemini .90, qwen
  .84, kimi .82, deepseek .78) used to rank model/provider choices for this
  agent.
