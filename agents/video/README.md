# Video & Ad Generator

Owns Imprint's video workflow: idea and script, visual-provider selection,
narration, direct generation, assembly, job status and output library.

Vidforge remains a separately versioned companion repository.  This package is
the ownership boundary for Imprint orchestration; `studio.py` is its adapter to
Vidforge.  User guidance: `docs/agents/video.md`.

Run focused coverage with `pytest tests/test_media_generation.py tests/test_vidforge_contract.py`.

## Files

- `__init__.py` — package ownership boundary: sets `AGENT_KEY = "video"` and
  re-exports the `studio` module as `video_studio` for callers outside the
  package.
- `studio.py` — the adapter to `vidforge`, a **separate git repository**
  nested at `imprint/vidforge/` and imported rather than vendored, so the
  standalone `vidforge.app` and Imprint's Video mode share one checkout, one
  config and one output history — "two front doors" onto one pipeline —
  instead of drifting apart the way the workspace's one existing
  vendored-copy pair (`lab_hub/tools/convert` vs `toolbox/convert_epub`)
  already has. Key surface:
  - `available()` / `unavailable_reason()` — `_load()` lazily imports
    vidforge's `config`, `pipeline` and `progress` modules and records any
    failure instead of raising at import time, so a checkout without
    `vidforge/` (or one missing PyYAML, or the YouTube-upload extras
    `google-api-python-client` / `google-auth-oauthlib`) gets an explanatory
    message in the panel rather than a crash on startup.
  - `ASPECTS` (Landscape 16:9, Vertical 9:16, Square 1:1) and `CLIP_SECONDS`
    (15/30/45/60/90) — the platform-native shapes and lengths the Social
    mode schedules clips against.
  - `clip_overrides()` — turns the long-form pipeline into a social clip
    purely through config overrides (render width/height, matching image
    size/orientation, and a `script.scene_seconds` floor of 6 for
    faster-cut short-form) rather than a second rendering path, since
    `produce()` already sizes every stage from `video.width`/`height`.
  - `load_config()`, `produce()`, `output_root()`, `library()` — load
    vidforge's `Config` (seeding `config.yaml`/`topics.txt` into the
    writable app-support directory on first run of a frozen build), run
    `pipeline.produce()`, and read vidforge's own output directory and
    build history, so a render started in the standalone app appears here
    too and vice versa.
  - `external_output_path()` / `record_external()` — reserve a slot in the
    shared vidforge library and write its manifest/history entry for a
    direct provider-rendered clip (e.g. Gemini, Higgsfield) that bypassed
    vidforge's own pipeline.
  - `pre_estimate()` — reproduces vidforge's own cost-estimate arithmetic
    (word budget from target seconds and words-per-minute, scene count from
    scene length, then script/TTS/image/caption cost) so the panel can show
    a cost figure *before* a script exists, using
    `services/media_catalog.openai_image_reserve_usd()` for per-image
    pricing when `visuals.source == "ai"`.
  - `stages()`, `reporter_base()`, `cancelled_error()`,
    `overall_fraction()` — expose vidforge's progress-reporting contract
    (stage list, `Reporter` base class, `Cancelled` exception, overall
    fraction) for the Qt worker in `ui/workers.py`.
- `recommendations.py` — registers this agent's `RECOMMENDATION_PROFILE` (an
  `AgentProfile` from `services.recommendations`) with the provider
  recommendation engine: task tags `video`/`creative`/`social`, weighted
  heavily toward quality (.44) with reliability (.23) and cost (.16), and
  per-provider affinity from gemini (.98) down to local (.62).
