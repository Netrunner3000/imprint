# Publishing Manager agent (`agents.manuscript`)

Owns finished-manuscript preparation: metadata, export, KDP/PublishDrive data,
quote discovery, launch planning and sales interpretation.  Its public API is
`agents.manuscript.ManuscriptAgent`.

The umbrella owns provider execution and the request guard.  Publishing data
adapters remain shared until they are proven exclusive to this package.  User
guidance: `docs/agents/manuscript.md`.

Quote Finder's **Use Project Draft** action loads the selected Project's
current Write draft (or linked saved draft) on demand, using its byline for
attribution. It does not mark that working text as approved for publication.

Run focused coverage with `pytest tests/test_book_pipeline.py`.

## Files

- **`__init__.py`** — the package's public surface: re-exports
  `ManuscriptAgent`.

- **`agent.py`** — the implementation, described in its own docstring as
  "extends the author_agent with distribution intelligence." It holds five
  system prompts, each backing a distinct capability:
  - `SYSTEM_PROMPT` — the general publishing-intelligence assistant: answers
    sales/royalty questions, platform health ("which stores are still
    pending?"), ranking and revenue trends, todo/checklist management, and
    metadata-sync status. Response style leads with the number, uses short
    tables for cross-platform comparisons, proactively flags anomalies (a
    sudden drop, a platform going inactive), and must say when data is
    missing or stale rather than guess — it is always grounded in JSON data
    injected ahead of the user's question.
  - `PUBLISHDRIVE_PROMPT` — parses raw PublishDrive API data into a strict
    JSON summary: `total_units`, `total_revenue_usd`, `by_platform`,
    `by_country`, `pending_stores`, `rejected_stores`, `period`. JSON only,
    no prose.
  - `KDP_PROMPT` — parses an already-JSON-parsed KDP sales CSV into
    `total_units_sold`, `total_royalties_usd`, `by_marketplace`,
    `kenp_pages_read` (if present), `period_start`, `period_end`. JSON only.
  - `QUOTE_SUGGESTION_PROMPT` — extracts quotable lines from a manuscript for
    Instagram/Pinterest quote graphics and short-form video. Lines must
    stand alone with no context, be emotionally sharp or screenshot-worthy,
    read in 3–6 seconds (~6–20 words), and be copied **verbatim** — no
    paraphrasing or invention. Returns a bare JSON array of strings.
  - `CALENDAR_CAPTION_PROMPT` — given a JSON array of `{quote, platform}`
    items (`tiktok` / `instagram` / `pinterest`), writes one short
    platform-native caption per item (TikTok: conversational + hashtags;
    Instagram: warmer/polished + hashtags; Pinterest: keyword-rich, no
    hashtags, soft CTA). Returns a bare JSON array in the same order/length
    as the input.

  `ManuscriptAgent` is the class the app calls:
  - `build_messages(prompt, context_json="")` — appends `context_json` to
    `SYSTEM_PROMPT` when given, for general Q&A grounded in current data.
  - `build_publishdrive_parse_messages(raw_json)` — messages for the
    PublishDrive parser.
  - `build_kdp_parse_messages(rows_json)` — messages for the KDP parser.
  - `build_quote_suggestions_messages(manuscript_text, count=10)` —
    messages requesting the top `count` quotable lines from the given text.
  - `build_calendar_caption_messages(items_json)` — messages for the
    caption generator.

- **`recommendations.py`** — registers Publish's `RECOMMENDATION_PROFILE`
  (an `AgentProfile` from `services.recommendations.models`) with the shared
  model-recommendation engine: task tags `analysis` / `structured` /
  `planning`, `reliability_weight=.27` and `cost_weight=.20` — both raised
  above the engine defaults (.20 / .15), since this agent reports real
  financial figures (accuracy matters) under frequent, routine queries (cost
  adds up) — and a `provider_affinity` table ranking OpenAI (.94) above
  Anthropic (.92), DeepSeek (.90), Gemini (.88), Qwen (.84) and Kimi (.83).
