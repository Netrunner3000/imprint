# VIDEO — topic to finished video

`key: video` · pipeline: `vidforge` (nested repo) · bridge: `services/video_studio.py` · panel: `build_video_panel()` · worker: `ui/workers.py → VideoWorker`

## What it does
Turns a topic into a complete narrated, illustrated video: script, text-to-speech narration, word-aligned captions, generated visuals, Ken Burns motion, background music, loudness normalisation, and a thumbnail. Long-form for YouTube, or a vertical clip for social.

## Where the code lives — and why it is not here
The pipeline is `vidforge`, a **separate git repository nested at `imprint/vidforge/`**. Imprint imports it rather than keeping a copy.

That is a deliberate trade. The workspace already has one vendored-copy pair — `lab_hub/tools/convert` against `toolbox/convert_epub` — and they have silently drifted apart in four files. A second copy of a twenty-module video pipeline would drift faster and matter more. One checkout, one pipeline, two front doors: `vidforge.app` standalone, and this tab.

The cost of that choice is that a clone of `imprint` alone has no `vidforge`. Every entry point in `services/video_studio.py` answers `available()` first and the panel renders an explanation instead of a dead form, so the failure is legible rather than a crash.

Frozen, the two apps share `~/Library/Application Support/vidforge/` — one config, one output library, one history, whichever front door you came in by.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Topic | What the video is about. Left empty, the next line of `topics.txt` is used. |
| Format | `Long-form` uses `config.yaml` as-is. `Social clip` overrides it. |
| Aspect | Clips only: vertical 9:16, square 1:1, or landscape. |
| Clip length | Clips only: 15–90 seconds. |
| Render Video / Stop | Run, or cancel at the next stage boundary. |
| Open Output Folder | The shared vidforge output directory. |

## Long-form and clips are the same pipeline
Not two code paths. `produce()` already sizes every stage from `video.width` / `video.height` and the script from a target length, so a clip is the same call with a different config:

| Override | Why |
|---|---|
| `video.width` / `video.height` | The shape of the output. |
| `visuals.image_size` | Portrait or square, or a vertical clip is a landscape image cropped to a strip of its middle. |
| `script.target_seconds` | Length. |
| `script.scene_seconds` → 6 | Long-form cuts every 14s. At that cadence a 30-second clip is two shots. |

This is what lets the Social mode ask for a clip instead of growing a video pipeline of its own.

## Cost
Billed per image, per character of narration and per audio minute — none of which the token cost model can express. `video_studio.pre_estimate()` reproduces vidforge's own per-stage arithmetic *before* the script exists (the panel has to show a number before you press the button) and hands the total to `authorize_request` as a flat cost, so a render counts against the session and daily caps.

Roughly: a long-form video €1–2, a 30-second clip about €0.25. Images dominate.

## Cancellation
Cooperative, through the reporter. The pipeline calls `raise_if_cancelled()` between stages and inside the per-scene loops, so a cancelled render stops at the next checkpoint rather than being killed mid-ffmpeg with a half-written file. The build stays in the library and can be resumed.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `services/video_studio.py` | The bridge: import, availability, config, clip overrides, pre-run estimate, library. |
| `ui/workers.py → VideoWorker` | Runs `produce()` on a thread; bridges vidforge's `Reporter` to Qt signals. |
| `vidforge/vidforge/pipeline.py` | `produce()` — the eight stages. |
| `vidforge/vidforge/progress.py` | `Reporter`, `STAGES`, `overall_fraction`, `Cancelled`. |
| `main.py: build_video_panel()` | Render and Library tabs. |
| `main.py: video_render()` | Estimate, authorise, start the worker. |

## Requirements
`OPENAI_API_KEY` for script, narration, images and caption alignment. `ffmpeg` on PATH. YouTube upload additionally needs `google-api-python-client`, `google-auth-oauthlib` and an OAuth client secret in vidforge's `.secrets/`.
