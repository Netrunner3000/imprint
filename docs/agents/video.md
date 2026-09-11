# VIDEO — topic to finished video

`key: video` · pipeline: `vidforge` (nested repo) · direct providers: OpenAI / Gemini / Qwen-Wan / Higgsfield · bridge: `services/video_studio.py` · panel: `build_video_panel()`

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
| Visual provider | OpenAI, Gemini, Qwen, Higgsfield, Pexels or Local. |
| Visual model | Only implemented models for that provider. See the routes below. |
| Aspect | Clips only: vertical 9:16, square 1:1, or landscape. |
| Clip length | Pipeline clips: 15–90 seconds. Direct choices follow the selected model: Omni 3–10s, Veo 4/6/8s, Wan 2–30s, Sora/Higgsfield 4/8/12s. |
| Render Video / Stop | Run, or cancel at the next stage boundary. |
| Open Output Folder | The shared vidforge output directory. |

## Visual providers and models

Every item in the model menu has a real execution path; chat models are never
mixed into this list.

| Provider | Selectable models | What Imprint does |
|---|---|---|
| OpenAI | GPT Image 2.5 Sunburst, GPT Image 2.5 Flare, GPT Image 2 | Generates one scene image at a time, then vidforge assembles the narrated video. |
| OpenAI | Sora 2, Sora 2 Pro | Generates one direct 4/8/12-second clip with audio, downloads it, and files it in the same Library. |
| Gemini | Gemini Omni 1.1 Flash | Generates a direct 3–10-second 720p clip with audio through the Interactions API. |
| Gemini | Veo 3.1, Veo 3.1 Fast, Veo 3.1 Lite | Creates and polls a 4/6/8-second 720p Veo operation, then downloads the result before Google's temporary file expires. |
| Qwen | Wan 3.0 Video, Wan 3.0 Video Prime | Creates a 2–30-second 720p text-to-video task with audio through Alibaba Model Studio. |
| Qwen | Wan 2.7 Text to Video | Creates a 2–15-second 720p task and saves the temporary result locally. |
| Higgsfield | Seedance 1.0 Lite | Gets the provider's exact quote, asks for approval, renders, downloads, and files the clip. |
| Pexels | Pexels stock photography | Uses stock visuals. Requires `PEXELS_API_KEY`; script and narration still use the pipeline providers. |
| Local | Local gradient cards | Creates visuals locally with no image-generation charge; script and narration still use the pipeline providers. |

DALL·E 2 and DALL·E 3 are intentionally absent: OpenAI retired and removed
their APIs. The GPT Image entries are the supported replacements.

Sora is different: its API still works today, but OpenAI has deprecated it and
scheduled permanent shutdown for **24 September 2026**. Imprint labels that in
the menu, disables new Sora submissions on the shutdown date, and recommends
Higgsfield or the GPT Image scene pipeline for durable workflows.

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
Pipeline video is billed per image, per character of narration and per audio minute — none of which the token cost model can express. `video_studio.pre_estimate()` reproduces vidforge's own per-stage arithmetic *before* the script exists (the panel has to show a number before you press the button) and hands the total to `authorize_request` as a flat cost, so a render counts against the session and daily caps. The GPT Image amount is a conservative budget reserve, because those models bill image tokens rather than a fixed price per generated file.

Sora, Veo and Wan are reserved from the selected 720p per-second list rate before submission. Gemini Omni is token-billed, so its roughly $0.10-per-second figure is explicitly labelled a budget reserve rather than an exact quote. Higgsfield supplies an exact request-specific quote before approval.

Roughly: a long-form video €1–2, a 30-second clip about €0.25. Images dominate.

## Cancellation
Pipeline cancellation is cooperative, through the reporter. Higgsfield uses its returned cancellation URL. Sora, Veo and Wan have no safe cancellation path in these integrations; after submission Imprint keeps watching and saves the paid result instead of pretending a disabled button could stop it. Gemini Omni's request is synchronous and likewise runs to completion on its worker thread.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `services/video_studio.py` | The bridge: import, availability, config, clip overrides, pre-run estimate, library. |
| `ui/workers.py → VideoWorker` | Runs `produce()` on a thread; bridges vidforge's `Reporter` to Qt signals. |
| `services/media_catalog.py` | Explicit visual provider/model capabilities, durations, aspects and 720p pricing. |
| `services/openai_client.py` | GPT Image generation plus Sora create/poll/download. |
| `services/gemini_client.py` | Gemini Omni interaction plus Veo create/poll/download. |
| `services/qwen_client.py` | Wan asynchronous create/poll/download through DashScope. |
| `ui/workers.py → OpenAIVideoWorker / VideoGenerationWorker` | Runs direct jobs off the UI thread and preserves completed output. |
| `vidforge/vidforge/pipeline.py` | `produce()` — the eight stages. |
| `vidforge/vidforge/progress.py` | `Reporter`, `STAGES`, `overall_fraction`, `Cancelled`. |
| `main.py: build_video_panel()` | Render and Library tabs. |
| `main.py: video_render()` | Estimate, authorise, start the worker. |

## Requirements
`OPENAI_API_KEY` for the default script/narration pipeline, GPT Image and Sora. `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) for Gemini Omni and Veo. `DASHSCOPE_API_KEY` for Wan; `DASHSCOPE_VIDEO_BASE_URL` can select a workspace-scoped regional endpoint. `HF_API_KEY_ID` plus `HF_API_KEY_SECRET` for Higgsfield. `PEXELS_API_KEY` for Pexels. `ffmpeg` on PATH. YouTube upload additionally needs `google-api-python-client`, `google-auth-oauthlib` and an OAuth client secret in vidforge's `.secrets/`.

DeepSeek, Anthropic, Kimi and Ollama remain useful for prompts, scripts and shot planning, but their official APIs do not return generated video. They are therefore not shown as visual providers; a selectable renderer must have an implemented, callable video-output route.
