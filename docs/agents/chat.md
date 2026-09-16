# CHAT — General-purpose conversation

`key: chat` · class: `agents/chat/agent.py → ChatAgent` · panel: standard `normal_panel` (no custom panel) · handler: `send_prompt()`

## What it does
The Assistant workspace's agent. Plain text in, plain text out, with full multi-turn conversation history. It has no domain framing of its own — instead it wears whichever **Tool** you pick (General Chat, Writing, Coding, Summarize, Rewrite), each supplying a different system prompt. Use it for anything without a dedicated specialist agent.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Tool | System prompt frame prepended to every message. |
| Command | Optional pre-built prompt scaffold from `config/commands.json`. |
| Provider / Model | Which LLM runs the request. |
| Mode + API checkboxes | Local-only / hybrid / cloud, and per-provider permission. |
| Prompt box | Your message. Send, or Stop to cancel. |

## Outputs
Streaming text into the **Output** box (auto-hidden until there's content). Each turn is appended to `current_messages`, so follow-ups keep context. Conversations auto-save to `data/chats/` and appear in **Saved Chats**.

## How it works
`ChatAgent.build_messages()` returns `[system(tool prompt), user]`. On later turns the prior assistant reply is included so the model sees the whole thread. Token-by-token streaming for streaming backends, word-by-word emulation otherwise.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/chat/agent.py` | `ChatAgent` — message builder. |
| `main.py: send_prompt()` | Builds request, spawns `ChatWorker`, streams tokens. |
| `main.py: ChatWorker` (QThread) | Runs the backend call off the UI thread. |
| DB `tools` table / `config/tool_prompts.json` | The actual system prompts per Tool. |
| `services/history_store.py` | Saves/loads chats in `data/chats/`. |

## Extend it
- **Add a Tool**: insert a row in the `tools` table (or `config/tool_prompts.json`) with a new system prompt — it shows up in the Tool combo automatically.
- **Add command scaffolds**: extend `config/commands.json`.
- **Attachments / RAG**: `send_prompt()` is the hook — enrich the user message before it reaches `ChatWorker`.

## Requirements
Any provider. Ollama is free/local; cloud providers need an API key (app `.env`).

## Before you run

Choose the narrowest Tool that matches the deliverable, then state the desired
format and acceptance criteria in the prompt. In Hybrid or Cloud mode, confirm
that the provider is permitted and the right rail says the key is configured.
Long saved conversations send more prior context and can cost more; start a new
chat when old turns are no longer relevant.

## Verify the result

- Check factual claims against a named source when accuracy matters.
- Confirm the response followed the requested format and did not silently omit
  constraints from an earlier turn.
- Treat code, financial reasoning, platform rules, and publishable copy as a
  draft until the relevant specialist agent or a human review passes it.
- Verify that the conversation appears under Saved Chats before relying on it
  as the only copy.

## Storage, cost, and privacy

Prompts and responses are stored locally in `data/chats/`. A cloud run sends
the current conversation context to the selected provider; a local Ollama run
does not. Imprint checks the request against session and daily limits before
starting, then records measured usage when available. Deleting a saved chat is
separate from clearing the visible prompt and requires confirmation.

## Common failures

| Symptom | Check |
|---|---|
| Send does nothing | Prompt, selected model, API permission, and remaining budget. |
| Model menu is empty | Refresh Models; confirm the provider is reachable or Ollama is running. |
| Response ignores context | Start a clean chat or restate the constraint in the current prompt. |
| Run stops mid-answer | Status line and Run Log; partial text is not a confirmed completion. |
