# FORGE — Agent factory

`key: manager` · class: `agents/manager_agent.py → ManagerAgent` · factory: `services/agent_factory.py → AgentFactory` · panel: `build_manager_panel()` · handlers: `manager_analyze_idea()`, `manager_approve_spec()`

> **Dev-only when packaged.** Forge writes new `agents/*.py` files and registers them — a frozen `.app` cannot import newly written code. Run from source (`python main.py`) to create agents, then rebuild the app to ship them.

## What it does
A meta-agent that turns a plain-language idea into a real new agent: it asks an LLM for a structured JSON spec, you review it, and on approval the Agent Factory writes the Python agent file and inserts the DB rows — no manual coding for a basic agent.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Idea box | Describe the agent: purpose, inputs, output sections, providers. |
| Provider / Model | Model that drafts the spec (strong model → better spec). |
| Analyze Idea | Generate the JSON spec. |
| Clear | Reset. |
| Approve & Create / Reject | Commit or discard the reviewed spec. |

## Outputs
A reviewable **JSON spec** (name, label, description, allowed_providers, allowed_tools, budget, requires_approval, system_prompt) in the spec box, plus a **Creation Log**. On approval: a new `agents/<name>_agent.py`, an `agents` table row, and a `tools` row. Restart to see it in the sidebar.

## How it works
`ManagerAgent` prompts the LLM to emit the JSON spec; `manager_analyze_idea()` parses/validates it into `pending_spec`; `manager_approve_spec()` hands it to `AgentFactory`, which writes the class file (with `build_messages()`) and the DB entries.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/manager_agent.py` | `ManagerAgent` — spec-generation prompt. |
| `services/agent_factory.py` | `AgentFactory` — writes files + DB rows. |
| `main.py: manager_analyze_idea()/manager_approve_spec()/manager_reject_spec()` | Review flow. |
| `services/database.py: _seed_default_agents()` | Where built-in agents are also seeded. |

## Extend it
- **Custom GUI generation**: today Forge creates standard-panel agents; extend `AgentFactory` to scaffold a `build_<name>_panel()` too.
- **Validation**: tighten spec checks (provider names, prompt length) before approval.
- **Hot-reload**: in dev, import the new module without a restart.

## Requirements
Provider key. Must run from source to create agents (see the dev-only note above).
