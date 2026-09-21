# BRAND & LOGO DESIGNER — client identity studio

`key: fiverr` · agent: `agents.fiverr.FiverrAgent` · workspace owner: `agents.fiverr.FiverrPanel`

## What it does
End-to-end logo-gig assistant. Unlike a prompt-only helper, it **actually generates the logo images** via OpenAI GPT Image, saves them locally, and also writes the Fiverr gig description and the client delivery message. One brief → concepts + copy.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Business Name, Industry / Niche | Core brief. |
| Style | Minimalist / bold / vintage / tech / etc. |
| Primary Colors, Notes | Palette + tagline/mood/competitors to avoid. |
| # Concepts (1–4) | How many logos to generate. |
| Text Provider / Model | LLM for the image prompt + copy. |
| Image Model | GPT Image 2.5 Sunburst, GPT Image 2.5 Flare, or GPT Image 2. |
| Generate Logos / Delivery Msg / Gig Description / Stop | The three actions. |
| Save All Images / Clear | Export / reset. |

## Outputs
Tabs: **Logo Preview** (generated PNGs, 280×280 thumbnails), **Delivery Message** (streamed), **Gig Description** (streamed), and **Orders**. The cost shown is a conservative per-image budget reserve. Images save to `data/fiverr_output/<timestamp>/logo_N.png`.

## How it works
Two-step logo flow: a `ChatWorker` runs `FiverrAgent.build_image_prompt_request()` to craft a clean image prompt, then `FiverrImageWorker` calls `openai.generate_image()` with the selected GPT Image model and displays the returned PNG. Delivery/gig use `FiverrAgent.build_messages(task, brief)`.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/fiverr/agent.py` | `FiverrAgent` — delivery / gig / image-prompt roles. |
| `agents/fiverr/panel.py` | Owns the layout and all guarded text/image request, result, Stop, save and order-log lifecycles. |
| `ui/workers.py: FiverrImageWorker` | Threaded GPT Image generation + local save. |
| `services/openai_client.py: generate_image()` | Validated `client.images.generate()` call for the selected current model. |
| `main.py` compatibility entries | Delegate older umbrella call sites to the owned panel; they contain no Client Gigs implementation. |

## Extend it
- **Other gig types**: generalise the brief + add roles to `FiverrAgent` (business cards, thumbnails, banners).
- **Vector export**: post-process PNGs (e.g. trace to SVG) after download.
- **Alternate image providers**: add an adapter and catalog entry rather than placing a model with no execution path in the menu.

## Requirements
**OpenAI API key** is mandatory for image generation. GPT Image uses token-based image pricing, so Imprint reserves a conservative amount against the budget before rendering. Text copy can use any provider. Fiverr seller account to sell.

DALL·E 2 and 3 are intentionally not offered: OpenAI retired and removed both APIs.

## Before you run

Use the client's exact business name, industry, deliverable count, colour
constraints, and prohibited references. Keep trademarked competitors in
“avoid” notes, not as imitation targets. Confirm the OpenAI image key, image
model, concept count, estimated reserve, and remaining session budget before
generating. Delivery and gig copy can use a different text provider.

## Verify the result

- Inspect every logo at full size; the preview thumbnail can hide malformed
  lettering and small artefacts.
- Confirm spelling, contrast, simple-size legibility, and transparent/background
  expectations against the client brief.
- Run a trademark and originality check before commercial delivery. A generated
  PNG is not automatically a vector master or an exclusive mark.
- Edit gig claims, turnaround, revisions, and package terms so they match the
  service you will actually provide.

## Storage, cost, and privacy

Generated working images first land under
`data/fiverr_output/<timestamp>/`. **Save All Images** copies the current set to
a folder you choose; it does not transfer files to Fiverr. Brief text and image
prompts are sent to the selected cloud providers. Image generation is paid per
request and each concept consumes a separate generation call.

## Common failures

| Symptom | Check |
|---|---|
| Generate Logos is blocked | Required brief fields, OpenAI key, image access, and budget reserve. |
| Copy appears but no image | The text prompt stage succeeded; inspect the image-stage status and Run Log. |
| Save All Images is disabled | No complete images are held in the current result set. |
| Text in the logo is wrong | Regenerate with a simpler mark or add lettering manually in a design tool. |
