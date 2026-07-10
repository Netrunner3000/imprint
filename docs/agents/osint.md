# TRACE — Light OSINT

`key: osint` · class: `agents/osint_agent.py → OSINTAgent` · panel: `build_osint_panel()` · handler: `osint_analyse()`

## What it does
A fast, lightweight open-source-intelligence assistant. Given a target (name, username, email, domain, org) plus optional context, it structures a research query, suggests public sources and search operators, and summarises what to look for. It is a **reasoning/planning layer** — it does not perform live lookups itself.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Query / target box | The subject to research and any known context. |
| Provider / Model | LLM for the analysis (Anthropic/OpenAI give the cleanest structure). |
| Analyse / Stop | Run or cancel. |

## Outputs
Streamed structured text into the OSINT tabs/output area. Raw response is retained (`last_raw_osint`) so it can be reused.

## How it works
`OSINTAgent.build_messages()` wraps the target in a system prompt tuned for defensive, legal OSINT. Runs through the shared `ChatWorker`.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/osint_agent.py` | `OSINTAgent` — system prompt + message builder. |
| `main.py: build_osint_panel()` | Builds the panel. |
| `main.py: osint_analyse()` / `osint_stop()` | Fire/cancel the request. |
| `providers/username_lookup.py`, `email_lookup.py`, `domain_lookup.py` | Real lookup helpers (WHOIS/DNS) available for wiring in. |

## Extend it
- **Live enrichment**: call the `providers/*_lookup.py` modules from `osint_analyse()` and feed real WHOIS/DNS/breach data into the prompt before sending.
- **Escalation**: hand results to **Bloodhound** (`osint_heavy`) for a full dossier.
- Edit the system prompt in `agents/osint_agent.py` to change tradecraft focus.

## Requirements
Any provider (API key for cloud). Optional OSINT API keys (`HIBP_API_KEY`, `VIRUSTOTAL_API_KEY`, etc. in `.env`) for the lookup providers.
