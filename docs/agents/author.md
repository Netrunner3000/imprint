# MANUSCRIPT — Long-form writing studio

`key: author` · class: `agents/author_agent.py → AuthorAgent` · panel: `build_author_panel()` · handlers: `author_write()`, `author_continue()`, `author_pub_generate()`, `author_mkt_generate()`

> Handles off where this agent's Publish/Market modes stop short (real sales data, quote content, launch checklist): see the **Publisher** agent, `key: manuscript` — [manuscript.md](manuscript.md).

## What it does
A three-mode writing workspace for novelists:
1. **Write** — draft prose, outlines, characters, and world-building into separate editable tabs.
2. **Publish** — generate query letters, synopses, blurbs, KDP metadata.
3. **Market** — generate launch posts, ARC outreach, newsletter/press copy.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Task / mode | Free write · Generate Outline · Develop Characters · Build World (Write mode). |
| Direction / instruction box | What to write next. |
| Provider / Model | Large-context model recommended. |
| Write / Continue / Stop / Save / Clear | Drafting lifecycle. |
| Publish + Market sub-panels | Their own generate / copy / save buttons. |

## Outputs
Write mode tabs: **Draft**, **Outline**, **Characters**, **World** — all editable. Sidebar: word count, scene count. Publish/Market render generated documents into their own areas with copy/save.

## How it works
`AuthorAgent.build_messages()` uses a prose-craft system prompt with structured markers `[DRAFT]` / `[OUTLINE]` / `[CHARACTER]` / `[WORLD]`; `_parse_author_sections()` routes each marked block to the right tab. `author_continue()` resends the current draft as context to keep going.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/author_agent.py` | `AuthorAgent` — craft prompt + markers. |
| `agents/manuscript_agent.py` | Publishing/marketing prompt logic. |
| `main.py: author_write()/author_continue()` | Write mode. |
| `main.py: author_pub_generate()/_copy()/_save()` | Publish mode. |
| `main.py: author_mkt_generate()/_copy()/_save()` | Market mode. |
| `main.py: _parse_author_sections()/_populate_author_tabs()` | Marker routing. |

## Extend it
- **Consistency memory**: feed the Characters/World tabs into every Write request so generated scenes stay canonical.
- **Export**: add EPUB/DOCX export from the Draft tab (python-pptx/docx patterns already in the deps).
- **New Publish/Market doc types**: add options + a branch in the respective `*_generate()`.

## Requirements
Provider key. Large-context model (`claude-sonnet`/`gpt-4o`) for long manuscripts.
