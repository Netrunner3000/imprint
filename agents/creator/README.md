# Creator agent

Owns shared content production for Imprint ventures: voice profiles, concepts,
captions, campaigns, promotional assets, calendars, account consent and
performance-informed drafting.  Its public API is `agents.creator` (see
`__init__.py` for the exact re-exports).

Creator is platform-neutral.  OnlyFans composes this capability through the
umbrella and owns its own venture rules.  User guidance:
`docs/agents/creator.md`.  Run focused coverage with
`pytest tests/test_creator_agent.py tests/test_creator_v2.py`.

## Files

- **`__init__.py`** — the package's public surface: re-exports `CreatorAgent`,
  `require_ready`, `ConsentError`, and the constants `ACCOUNT_TYPES`, `KINDS`,
  `PROMO_CHANNELS`. Callers should import from the package, not `agent.py`
  directly.

- **`agent.py`** — the implementation. Creator is a drafting tool, not an
  unattended publisher — it has no send path, which matters most for
  OnlyFans (no public posting API exists; automation that *replaces* a human
  rather than assisting one risks a permanent ban). Key pieces:
  - `ACCOUNT_TYPES = ("own", "managed", "persona")` — the three account
    kinds, each carrying different obligations.
  - `KINDS` — every draft type Creator can produce (`post`, `caption`,
    `posting_plan`, `promo_assets`, `ppv`, `welcome`, `promo`, `bio`,
    `campaign`, `hooks`), each mapped to the description injected into the
    prompt.
  - `PROMO_CHANNELS` — the off-platform channels ("X / Twitter", "Reddit",
    "TikTok", "Instagram", "Threads") promo drafts target, since the
    subscription platform itself is a poor discovery surface.
  - `ConsentError(ValueError)` — raised when a `managed` account has no
    recorded consent holder.
  - `require_ready(account)` — the guard called before every generation.
    Validates `account_type` is known and, for `managed` accounts, that a
    `consent_holder` is recorded, so an agency cannot quietly accumulate
    accounts nobody authorised.
  - `_account_context(account)` — builds the per-account framing block: own
    accounts write in the user's voice, managed accounts write in the
    consent holder's established voice without inventing biographical facts,
    persona accounts stay explicitly fictional and surface their disclosure
    line.
  - `SYSTEM_PROMPT` — the ground rules every draft operates under: it's for
    human review before sending; no fabricated claims, false scarcity, or
    fake testimonials; personas stay fictional; adult-platform copy is
    suggestive, not explicit; zero tolerance for any minors framing.
  - `CreatorAgent` — the class the rest of the app calls:
    - `build_messages(prompt)` — wraps a prompt with `SYSTEM_PROMPT`.
    - `build_draft_prompt(account, kind, brief, *, price_usd=0.0,
      channel="", segment="", price_history="")` — the main entry point.
      Calls `require_ready` first, then assembles account context, the
      persona bible and voice-sample block (via
      `services.creator_profile.persona_block` / `voice_block`) — the voice
      block is what keeps output from reading like generic AI copy — the
      requested `kind`, audience-segment notes
      (`services.creator_profile.SEGMENTS`), PPV price / price-history
      framing, promo-channel framing, and finally the brief itself.
    - `build_video_prompt(account, brief)` — builds a Higgsfield
      teaser-clip prompt. Deliberately safe-for-work only (Higgsfield
      moderates prompts, references and output, and prohibits explicit
      material), and pulls a persona's locked `appearance` via
      `services.creator_profile.load_persona` so repeated renders stay the
      same character rather than drifting between requests.

- **`recommendations.py`** — registers Creator's `RECOMMENDATION_PROFILE`
  (an `AgentProfile` from `services.recommendations.models`) with the shared
  model-recommendation engine: task tags `creative` / `marketing` / `social`,
  `reliability_weight=.23` and `speed_weight=.14` — both raised above the
  engine defaults (.20 / .10), since a bad draft or a slow turnaround both
  hurt a live content calendar — and a `provider_affinity` table ranking
  Anthropic (.98) and OpenAI (.96) above Gemini (.91), Qwen (.85), Kimi (.83)
  and DeepSeek (.78) for this task type.
