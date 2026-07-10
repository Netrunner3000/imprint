# ATELIER — Fiverr logo gig studio

`key: fiverr` · class: `agents/fiverr_agent.py → FiverrAgent` · panel: `build_fiverr_panel()` · handlers: `fiverr_generate_logos()`, `fiverr_write_delivery()`, `fiverr_write_gig()`

## What it does
End-to-end logo-gig assistant. Unlike a prompt-only helper, it **actually generates the logo images** via OpenAI DALL·E 3, downloads them locally, and also writes the Fiverr gig description and the client delivery message. One brief → concepts + copy.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Business Name, Industry / Niche | Core brief. |
| Style | Minimalist / bold / vintage / tech / etc. |
| Primary Colors, Notes | Palette + tagline/mood/competitors to avoid. |
| # Concepts (1–4) | How many logos to generate. |
| Text Provider / Model | LLM for the DALL·E prompt + copy. |
| Generate Logos / Delivery Msg / Gig Description / Stop | The three actions. |
| Save All Images / Clear | Export / reset. |

## Outputs
Tabs: **Logo Preview** (generated PNGs, 280×280 thumbnails), **Delivery Message** (streamed), **Gig Description** (streamed). Sidebar: status, est. cost (~$0.04/image), order log. Images save to `data/fiverr_output/<timestamp>/logo_N.png`.

## How it works
Two-step logo flow: a `ChatWorker` runs `FiverrAgent.build_image_prompt_request()` to craft a clean DALL·E prompt, then `FiverrImageWorker` (QThread) calls `openai.generate_image()` (dall-e-3), downloads each URL, and displays it. Delivery/gig use `FiverrAgent.build_messages(task, brief)`.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/fiverr_agent.py` | `FiverrAgent` — delivery / gig / image-prompt roles. |
| `main.py: FiverrImageWorker` | DALL·E generation + download. |
| `services/openai_client.py: generate_image()` | `client.images.generate(dall-e-3)`. |
| `main.py: fiverr_generate_logos()/fiverr_write_delivery()/fiverr_write_gig()` | The actions. |
| `main.py: fiverr_save_images()/fiverr_clear()` | Export / reset. |

## Extend it
- **Other gig types**: generalise the brief + add roles to `FiverrAgent` (business cards, thumbnails, banners).
- **Vector export**: post-process PNGs (e.g. trace to SVG) after download.
- **Alternate image models**: swap `generate_image()` for another provider/quality tier.

## Requirements
**OpenAI API key** is mandatory for image generation (DALL·E 3 ≈ $0.04/image). Text copy can use any provider. Fiverr seller account to sell.
