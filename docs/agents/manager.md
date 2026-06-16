# FORGE — Agent Builder

## What it does
Forge is a meta-agent that creates new Sentinel AI agents from plain-language descriptions. You describe what you want an agent to do, and Forge writes the Python agent class, the system prompt, the configuration spec, and registers it in the agent registry — ready to use immediately.

---

## How to use

1. **Describe your agent idea** in the text box — be as specific as possible about:
   - What the agent does
   - What input it takes
   - What output/sections it produces
   - Any special behaviour (modes, toggles, structured output, etc.)
2. *(Optional)* **Select a base agent template** — Forge can model the new agent after an existing one (e.g. "like TRACE but for LinkedIn profiles").
3. **Select the model** — use a powerful model (Claude Sonnet or GPT-4o) for best code quality.
4. Click **Analyze**.
5. Forge generates:
   - A Python agent class file
   - A system prompt
   - A JSON configuration spec
6. Review the output in the code box.
7. Click **Register Agent** to save and activate it.

---

## What Forge generates

**Python agent class** — a new file in `agents/` with the proper `BaseAgent` inheritance, `__init__`, `build_messages()`, and `parse_spec()` methods.

**System prompt** — a detailed, role-specific system prompt following Sentinel AI's conventions.

**JSON spec** — the configuration entry for `agents_config.json` including the agent name, display label, and supported providers.

---

## Input description tips

The more detail you give, the better the output:

| Vague | Better |
|---|---|
| "An agent for Twitter" | "An agent that analyses a Twitter/X username and generates a follower growth strategy, tweet frequency analysis, and content calendar" |
| "A cooking agent" | "An agent that takes ingredients as input and generates a recipe, macros per serving, and a shopping list" |
| "A legal agent" | "An agent that reviews contract clauses for common risks and outputs: risk flags with severity, plain-English summaries of each clause, and recommended edits" |

---

## Tips
- Describe the **output structure** explicitly — list the tabs, sections, or fields you want.
- Mention **modes** if needed (like Manuscript's Write/Publish/Market split).
- After generation, review the code before registering — Forge is thorough but you may want to tweak naming or prompt wording.
- Registered agents appear immediately in the left sidebar after the app refreshes.
