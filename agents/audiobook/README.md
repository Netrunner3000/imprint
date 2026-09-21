# Audiobook Producer agent (`agents.audiobook`)

Owns ebook discovery, narration configuration, conversion progress, listening,
resume state and audiobook output management. Imprint imports its connector and
Convert/Listen workspace from `agents.audiobook`. Discovery, estimation,
conversion process lifecycle, billing closure, library and playback actions all
belong to that workspace; only shared budgets, usage storage, output and the
narration/library services remain on the umbrella side.

## Files

- `__init__.py` — public interface; re-exports `AudiobookConnector` and lazily
  exposes `AudiobookPanel` so converter/CLI imports do not require Qt.
- `agent.py` — `AudiobookConnector.parse_input(text)` parses a `key=value`-per-line
  config block into a dict with defaults (`voice="alloy"`, `chunk_tokens=1500`),
  and raises `ValueError` if `input=` or `output=` is missing.
- `panel.py` — owns the Convert and Listen layouts, source discovery, exact-text
  cost estimation, paid conversion authorization/process/result lifecycle,
  library scan, resume and playback actions. Temporary host aliases remain for
  shared integrations and backwards-compatible entry points (see TODO).
- `recommendations.py` — exports `RECOMMENDATION_PROFILE`, an `AgentProfile`
  (from `services.recommendations`) describing what this agent needs from an
  AI provider/model: tagged `narration`, `longform`, `reliability`, weighted
  toward reliability (0.32) and quality (0.38), with a strong affinity for
  OpenAI (0.95). It is discovered dynamically by
  `agents.recommendation_profiles.profile_for("audiobook")` and scored by the
  shared `RecommendationEngine` to recommend a provider/model for narration jobs.

User guidance: `docs/agents/audiobook.md`.  Run focused coverage with
`pytest tests/test_audiobook_player.py tests/test_request_guard.py -k audiobook`.
