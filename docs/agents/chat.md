# CHAT — General-Purpose Conversation

## What it does
Chat is the default agent for open-ended conversation with any supported AI provider and model. It forwards your message directly to the selected model and streams the response back in real time. Use it for brainstorming, Q&A, summarisation, translation, quick analysis, or anything that doesn't need a specialist agent.

---

## How to use

1. **Select a Provider** — choose from Ollama (local/free), OpenAI, DeepSeek, Gemini, or Anthropic in the Provider drop-down.
2. **Select a Model** — pick from the models available for that provider. Hit **Refresh Models** if the list is empty.
3. *(Optional)* **Select a Tool** — pre-loads a system prompt tailored to a specific task (Coding, Writing, OSINT, etc.).
4. *(Optional)* **Select a Command** — applies a fixed instruction style on top of the tool prompt.
5. **Type your message** and press **Send** (or Ctrl+Enter).
6. The response streams into the output box token by token.
7. Use **Stop** to abort a running request at any time.

---

## Controls

| Control | Purpose |
|---|---|
| Provider | Which AI backend to call |
| Model | Specific model within that provider |
| Tool | Pre-built system prompt for a domain |
| Command | Style modifier (e.g. "Explain like I'm 5") |
| Refresh Models | Re-query available models for the current provider |
| Model Guide | Open the full model selection guide |
| Send | Submit the current message |
| Stop | Cancel the in-progress request |
| Clear | Wipe the output box |

---

## Tips
- For **private/offline** use, pick Ollama and a local model — no API key or internet needed.
- For **best quality**, use Anthropic `claude-sonnet-4-6` or OpenAI `gpt-4o`.
- For **lowest cost**, use Anthropic `claude-haiku-4-5-20251001` or DeepSeek.
- The **Tool** drop-down is the fastest way to switch the agent's personality without leaving Chat.

---

## Cost
Depends entirely on the provider and model selected. Ollama is always free. API providers charge per token — see the **Cost** panel (right sidebar) for live estimates.
