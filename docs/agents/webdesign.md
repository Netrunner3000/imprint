# SITE BUILDER — HTML / CSS / JS generation

`key: webdesign` · class: `agents/webdesign_agent.py → WebdesignAgent` · panel: `build_webdesign_panel()` · handler: `webdesign_generate()`

## What it does
A senior front-end assistant that produces clean, modern, self-contained HTML/CSS/JS — from single components to full responsive landing pages. Defaults to semantic HTML5 + mobile-first CSS (flexbox/grid) with hover/focus states and basic accessibility.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Brief box | Describe the page/component/layout. |
| Provider / Model | Coding-strong model recommended (Claude/GPT-4o/DeepSeek). |
| Generate / Stop / Save .html | Run, cancel, export. |
| Sidebar | Responsive toggle, framework choice, line-count indicator. |

## Outputs
Generated code streamed into the output area; sidebar shows a **lines** count. **Save .html** writes it to a file you can open in a browser immediately.

## How it works
`WebdesignAgent.build_messages()` uses a system prompt that: delivers complete self-contained code in one block, prefers CSS variables and vanilla ES6 (no jQuery), uses placeholder/SVG assets when none given, and shows code first then a short rationale.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/webdesign_agent.py` | `WebdesignAgent` — front-end system prompt + standards. |
| `main.py: build_webdesign_panel()` | Brief form, output, sidebar toggles. |
| `main.py: webdesign_generate()/webdesign_stop()/webdesign_save()` | Lifecycle. |

## Extend it
- **Live preview**: render the generated HTML in a `QWebEngineView` next to the code.
- **Framework switch**: pass the framework toggle into the prompt so it emits Tailwind/Bootstrap on demand.
- **Multi-file output**: split the single block into `index.html` / `style.css` / `script.js` on save.

## Requirements
Provider key (any capable coding model). No external services.
