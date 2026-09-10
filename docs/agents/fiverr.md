# ATELIER — Fiverr logo gig studio

`key: fiverr` · class: `agents/fiverr_agent.py → FiverrAgent` · panel: `build_fiverr_panel()` · handlers: `fiverr_generate_logos()`, `fiverr_write_delivery()`, `fiverr_write_gig()`

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
| `agents/fiverr_agent.py` | `FiverrAgent` — delivery / gig / image-prompt roles. |
| `ui/workers.py: FiverrImageWorker` | Threaded GPT Image generation + local save. |
| `services/openai_client.py: generate_image()` | Validated `client.images.generate()` call for the selected current model. |
| `main.py: fiverr_generate_logos()/fiverr_write_delivery()/fiverr_write_gig()` | The actions. |
| `main.py: fiverr_save_images()/fiverr_clear()` | Export / reset. |

## Extend it
- **Other gig types**: generalise the brief + add roles to `FiverrAgent` (business cards, thumbnails, banners).
- **Vector export**: post-process PNGs (e.g. trace to SVG) after download.
- **Alternate image providers**: add an adapter and catalog entry rather than placing a model with no execution path in the menu.

## Requirements
**OpenAI API key** is mandatory for image generation. GPT Image uses token-based image pricing, so Imprint reserves a conservative amount against the budget before rendering. Text copy can use any provider. Fiverr seller account to sell.

DALL·E 2 and 3 are intentionally not offered: OpenAI retired and removed both APIs.
