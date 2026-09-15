# Site Builder agent

Owns responsive HTML, CSS and JavaScript generation plus front-end layout and
accessibility guidance. Imprint imports `WebdesignAgent` from
`agents.webdesign`; preview and file operations are umbrella concerns today.

## Files

- **`__init__.py`** — package surface. Re-exports `WebdesignAgent` from
  `agent.py` as the only public name (`__all__ = ["WebdesignAgent"]`); Imprint
  imports the class from here rather than reaching into `agent.py` directly.

- **`agent.py`** — the agent itself. `WebdesignAgent` is a thin wrapper
  (`name = "webdesign"`) whose `build_messages(prompt)` returns the
  `[system, user]` message pair Imprint sends to the model. Nearly all of the
  behaviour lives in the module-level `SYSTEM_PROMPT` string, which instructs
  the model to:
  - clarify purpose/audience, palette and style before generating when the
    request is underspecified, defaulting to vanilla HTML/CSS/JS unless a
    framework is named;
  - output complete, self-contained, semantic, mobile-first responsive
    markup with hover/focus states and basic accessibility (aria labels, alt
    text, tab order), briefly commenting non-obvious CSS/JS;
  - prefer CSS custom properties over inline styles, vanilla ES6+ over
    jQuery, and placeholder/inline-SVG assets when none are supplied;
  - lead with code and keep explanations short.

- **`recommendations.py`** — routing metadata, not agent logic. Defines
  `RECOMMENDATION_PROFILE`, an `AgentProfile` (from
  `services.recommendations`) that tells Imprint's model/provider selector how
  to weight this agent: task tags `("code", "structured", "analysis")`,
  `quality_weight=.45`, `reliability_weight=.25`, and a `provider_affinity`
  table ranking providers for this agent's work (openai .98, anthropic .96,
  kimi .94, deepseek .92, qwen .88, gemini .86, ollama .70). Imprint reads this
  to pick a backing model per provider availability/preference, independent of
  the `WebdesignAgent` class itself.

User guidance: `docs/agents/webdesign.md`. Run focused coverage with
`pytest tests/test_agents_scenarios.py -k webdesign`.
