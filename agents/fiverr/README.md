# Brand & Logo Designer

Owns client-service workflows: brief interpretation, logo concepts, gig listing
copy and professional delivery messages. Its public API exposes
`agents.fiverr.FiverrAgent` and the lazily loaded `FiverrPanel`; provider
execution, image generation and budget services remain shared by the umbrella.

User guidance: `docs/agents/fiverr.md`.  Run focused coverage with
`pytest tests/test_agents_scenarios.py tests/test_panel_layout.py tests/test_request_guard.py -k fiverr`.

## Files

- **`__init__.py`** — the package's public surface: re-exports `FiverrAgent`
  and lazily exposes `FiverrPanel` so domain-only imports stay Qt-free.

- **`panel.py`** — owns the complete Client Gigs workspace: brief and model
  controls, price estimate, guarded prompt/image/delivery/gig request
  lifecycles with exact tokens, result tabs, order log, save, clear and Stop.
  Thin host delegates and worker aliases remain for umbrella integrations and
  shutdown handling.

- **`agent.py`** — the implementation. `SYSTEM_PROMPT` casts the model as a
  5-star Fiverr freelancer specialising in logo design, and defines three
  distinct output formats it must switch between depending on what is asked:
  - **Delivery message** — warm opening thanking the client, a short
    explanation of the design choices, an offer of one revision round, and a
    professional sign-off; capped under 200 words, no jargon.
  - **Gig description** — a full listing: hook headline, 5–7 bullet "what
    you get" points, differentiators, a Basic/Standard/Premium package
    breakdown with prices, and a call to action; capped under 400 words,
    written in first person.
  - **Logo prompt** — a bare 1–3 sentence image-generation prompt (no
    preamble) describing style, colours and mood, appending "vector logo,
    transparent background, no text" unless a business name was explicitly
    requested in the logo.

  `FiverrAgent` is the class the app calls:
  - `build_messages(task, brief)` — builds a chat-messages list for any of
    the three task types above. `brief` is a dict of `business_name`,
    `industry`, `style`, `colors`, `notes` (each defaults to `"N/A"` if
    absent), formatted into a context block ahead of the `task` instruction.
  - `build_image_prompt_request(brief)` — the same context block, with the
    task fixed to "build an image-generation prompt for the selected GPT
    Image model to create a logo for this business."

- **`recommendations.py`** — registers Brand & Logo Designer's `RECOMMENDATION_PROFILE`
  (an `AgentProfile` from `services.recommendations.models`) with the shared
  model-recommendation engine: task tags `marketing` / `creative` /
  `structured`, `cost_weight=.22` and `speed_weight=.16` — both raised above
  the engine defaults (.15 / .10), reflecting that gig work is volume,
  price-sensitive and needs fast turnaround rather than maximum quality —
  and a `provider_affinity` table ranking OpenAI (.98) above Anthropic
  (.94), Gemini (.90), Qwen (.84), Kimi (.82), DeepSeek (.80), with Ollama
  (.68) included as a local fallback option.
