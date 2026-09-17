# WEB DEVELOPER — HTML / CSS / JS generation

`key: webdesign` · class: `agents.webdesign.WebdesignAgent` · panel and lifecycle: `agents.webdesign.WebdesignPanel`

## What it does
A senior front-end assistant that produces clean, modern, self-contained HTML/CSS/JS — from single components to full responsive landing pages. Defaults to semantic HTML5 + mobile-first CSS (flexbox/grid) with hover/focus states and basic accessibility.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Brief box | Describe the page/component/layout. |
| Provider / Model | Coding-strong model recommended (Claude/GPT-4o/DeepSeek). |
| Generate / Stop / Save .html | Run, cancel, export. |
| Output indicators | Responsive detection, selected framework, line count. |

## Outputs
Generated code streams into HTML / CSS / JS tabs; a row of stats above them shows responsive, framework and line count. **Save .html** writes it to a file you can open in a browser immediately.

## How it works
`WebdesignAgent.build_messages()` uses a system prompt that: delivers complete self-contained code in one block, prefers CSS variables and vanilla ES6 (no jQuery), uses placeholder/SVG assets when none given, and shows code first then a short rationale.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/webdesign/agent.py` | `WebdesignAgent` — front-end system prompt + standards. |
| `agents/webdesign/panel.py` | Brief form, model row, output stats and tabs, guarded generation, copy and export. |
| `main.py` | Shared authorization, worker factory, usage and history; global Stop delegates to the panel. |

## Extend it
- **Live preview**: render the generated HTML in a `QWebEngineView` next to the code.
- **Framework switch**: pass the framework toggle into the prompt so it emits Tailwind/Bootstrap on demand.
- **Multi-file output**: split the single block into `index.html` / `style.css` / `script.js` on save.

## Requirements
Provider key (any capable coding model). No external services.

## Before you run

Describe the page's purpose, audience, primary action, required sections,
content, responsive breakpoints, accessibility needs, and technical constraints.
Choose the framework control deliberately; a brief that asks for one stack
while the selector names another produces ambiguous output. Never place real
secrets, production tokens, or private customer data in the brief.

## Verify the result

- Review all three tabs and confirm HTML, CSS, and JavaScript form one complete
  document rather than disconnected examples.
- Open the saved `.html` locally and test the primary action at narrow and wide
  sizes with keyboard-only navigation.
- Check headings, labels, focus visibility, colour contrast, reduced-motion
  behaviour, form validation, links, and empty/error states.
- Replace placeholders and review third-party scripts before deployment. A
  visually polished render is not a security or accessibility audit.

## Storage, cost, and privacy

The streamed response remains in memory until it is saved or cleared.
**Save .html** extracts the complete HTML block and writes it to the chosen
local path; **Copy All** places the same result on the system clipboard. Neither
action deploys a site. Cloud generation sends the brief to the chosen provider
and is accounted by Imprint's shared request guard.

## Common failures

| Symptom | Check |
|---|---|
| Generate is blocked | Brief, model selection, provider permission, key, and remaining budget. |
| CSS or JS tab is empty | The model returned one unsplit block; inspect HTML and the full response before saving. |
| Saved page is broken | Missing closing tags, external asset URLs, console errors, and framework dependencies. |
| Stop leaves partial code | Expected: partial streamed text is visible but Save stays unavailable until completion. |
