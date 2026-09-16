# Studio Assistant

General-purpose conversation is available in Imprint's **Assistant** workspace.
It uses the shared `normal_panel`, not a duplicate agent panel. Its public API
is `agents.chat.ChatAgent`.

The workspace is for a bounded question that does not belong to a specialist
agent. Chats are saved locally; cloud requests send the active conversation
context to the selected provider and pass through the normal permission and
budget checks. See `docs/learn/modules/19-assistant.md` for the operating path.

## Files

- `__init__.py` — public interface; re-exports `ChatAgent` from `agent.py`.
- `agent.py` — `ChatAgent.build_messages(prompt)` supplies the basic message;
  `main.py` adds the selected Tool's system prompt and saved turn context.
- `recommendations.py` — exports `RECOMMENDATION_PROFILE` (an `AgentProfile`)
  tagged `general`, `analysis`, `structured`, using the engine's default
  weighting (no quality/cost/etc. overrides) with broad provider affinity
  (Anthropic and OpenAI 0.94, Gemini and DeepSeek 0.88, Qwen and Kimi 0.86,
  Ollama 0.72). Discovered by `agents.recommendation_profiles.profile_for("chat")`
  for the visible Assistant workspace.
