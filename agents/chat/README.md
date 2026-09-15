# Studio Assistant

Internal general-purpose chat capability retained from the original fork.  It
is not currently exposed as an Imprint workspace.  Its public API is
`agents.chat.ChatAgent`.

This package exists so the compatibility surface is explicit rather than hidden
in `main.py`; the product decision is to expose it deliberately or retire it.

## Files

- `__init__.py` — public interface; re-exports `ChatAgent` from `agent.py`.
- `agent.py` — `ChatAgent.build_messages(prompt)` returns a single-message
  `[{"role": "user", "content": prompt}]` payload; there is no system prompt
  or conversation-history handling yet.
- `recommendations.py` — exports `RECOMMENDATION_PROFILE` (an `AgentProfile`)
  tagged `general`, `analysis`, `structured`, using the engine's default
  weighting (no quality/cost/etc. overrides) with broad provider affinity
  (Anthropic and OpenAI 0.94, Gemini and DeepSeek 0.88, Qwen and Kimi 0.86,
  Ollama 0.72). Discovered by `agents.recommendation_profiles.profile_for("chat")`
  even though the agent itself is currently unexposed.
