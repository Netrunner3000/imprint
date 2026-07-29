# PUBLISHER — Publishing metrics, marketing content, and launch tracking

`key: manuscript` · class: `agents/manuscript_agent.py → ManuscriptAgent` · panel: `build_manuscript_panel()` · handlers: `manuscript_refresh()`, `manuscript_ingest_kdp()`, `manuscript_ask()`, `quote_finder_suggest()`, `manuscript_generate_quote_graphic()`, `manuscript_generate_short()`, `manuscript_add_todo()`

> Not to be confused with the **Manuscript** left-panel button (`key: author`, see [author.md](author.md)) — that's the writing studio. This agent, labelled **Publisher** in the UI, picks up once a draft exists: sales data, launch content, and the publishing checklist.

## What it does
Four tabs covering the post-draft, pre/post-launch side of publishing a book:

1. **Overview** — PublishDrive sales/royalty summary, a chat sidebar grounded in that data, and the publishing todo checklist.
2. **Quote Finder** — load the manuscript (`.txt`/`.pdf`/`.epub`/`.mobi`) or paste an excerpt; the agent extracts a batch of verbatim, screenshot-worthy lines. Each candidate has inline buttons to turn it directly into a graphic or a narrated short.
3. **Quote Graphics** — turn one quote into a styled PNG (3 themes, square or vertical) for Instagram/Pinterest/TikTok — pure Pillow, no API cost.
4. **Shorts** — narrate a quote (free on-device TTS by default, ElevenLabs optional) and combine it with a quote graphic into a vertical MP4 via ffmpeg.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Period selector / Refresh Data | Pull PublishDrive sales for the selected window. |
| Ingest KDP CSV | Parse new files dropped in `data/kdp_reports/`, dedup by filename. |
| Ask box + Provider/Model | Chat Q&A grounded in the last-fetched sales JSON. |
| Publishing Todos list + Add/Done | Lightweight checklist, seeded with a standard launch checklist on first use. |
| Quote Finder: text box / Load File / quote count / theme / voice / attribution | Source text and generation settings for batch quote extraction. |
| Quote Graphics: quote / attribution / theme / size | Single-graphic generation settings. |
| Shorts: quote / attribution / theme / voice source / voice | Single-short generation settings. |

## Outputs
Sales JSON and chat responses in the Overview text browser. PNGs in `data/quote_graphics/`. MP4s in `data/shorts/`. Todos persisted in the `manuscript_todos` DB table.

## How it works
`ManuscriptAgent.build_messages()` injects the last-fetched sales JSON as system-prompt context so Q&A stays grounded. `build_quote_suggestions_messages()` uses a dedicated prompt that requires quotes to be exact substrings of the source (verified in testing — the model does not paraphrase). `services/quote_graphics.py` renders a vertical gradient + wrapped serif text with Pillow — no external API. `services/shorts_generator.py` narrates via `providers/voice/` (mock/system `say` by default, ElevenLabs optional) then combines the narration with the quote-graphic PNG via a single `ffmpeg -loop 1 -i image -i audio` call — the exact pattern used by `services/course/video_assembler.py`.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/manuscript_agent.py` | `ManuscriptAgent` — sales-summary, PublishDrive/KDP parsing, and quote-suggestion prompts. |
| `services/publishdrive_client.py` | PublishDrive REST wrapper (`PUBLISHDRIVE_API_KEY`). |
| `services/kdp_csv_parser.py` | KDP CSV ingestion + dedup; `manuscript_seed_todos()` seeds the checklist. |
| `services/quote_graphics.py` | `render_quote_graphic()` — Pillow gradient + text render, 3 themes, 2 sizes. |
| `services/shorts_generator.py` | `render_short()` — TTS + ffmpeg image/audio combine. |
| `providers/voice/mock.py` / `elevenlabs.py` | TTS backends (free macOS `say`, or ElevenLabs). |
| `services/narrator/converter.py: load_text()` | Reused for Quote Finder's file loader (pdf/epub/mobi/txt extraction). |
| `main.py: build_manuscript_panel()` + tab builders | 4-tab UI. |
| `main.py: quote_finder_*`, `manuscript_generate_*`, `_quote_finder_*` | Handlers + the `ShortsWorker` background thread. |
| `services/database.py` | `manuscript_metrics`, `manuscript_kdp_ingested`, `manuscript_todos` tables. |

## Extend it
See the roadmap discussion in project notes — short version: full-manuscript export (EPUB/DOCX/PDF), an editing pass, autonomous chapter-by-chapter drafting, a content-calendar generator, and a Buffer/Metricool posting integration are the next logical additions. None of the current tabs write back into the manuscript itself — this agent only consumes a finished or in-progress draft.

## Requirements
Pillow and ffmpeg (both already project dependencies) cover Quote Graphics/Shorts entirely for free. PublishDrive sales data needs `PUBLISHDRIVE_API_KEY` in `.env`. Better short-form narration needs `ELEVENLABS_API_KEY` (optional — free macOS `say` is the default). Quote Finder's LLM step uses whatever provider/model is selected on the Overview tab.
