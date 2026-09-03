# COURSE GENERATOR — topic → a packaged video course

`key: course` · class: `agents/course_agent.py → CourseAgent` · panel: **none — CLI only** · entry point: `run_course.py`

## What it does
Turns one topic into a complete self-study course: an outline, per-lesson
narration scripts, rendered slides, a voiced avatar video per lesson, and an
`index.html` that ties them together with downloadable `.pptx` slides.

## Why this page exists
Every other agent has a panel with a 📖 Docs button that opens its sheet from
`docs/agents/`. The Course Generator has no panel, so it has no button — and
until this page existed, `run_course.py --help` was its only documentation.

It is also **excluded from the packaged app**: `CreateAndPublish.spec` lists
`agents.course_agent` under `excludes`, because importing it pulls
`providers.avatar` and `providers.voice`. Run it from a source checkout.

## Inputs (CLI flags)
| Flag | Default | Purpose |
|---|---|---|
| `--topic` | *required* | Course subject. |
| `--difficulty` | `beginner` | `beginner` · `intermediate` · `advanced`. |
| `--audience` | `general learners` | Who it is written for. |
| `--modules` | `2` | Number of modules (1–12). |
| `--lessons` | `2` | Lessons per module (1–10). |
| `--duration` | `15` | Minutes per lesson (5–60). |
| `--avatar` | `mock` | `mock` · `heygen` · `synthesia`. |
| `--voice` | `mock` | `mock` · `elevenlabs`. |
| `--output` | `output/courses` | Output directory. |

Both provider flags default to `mock`, which writes placeholder media and calls
no paid API — so a full dry run of the pipeline is free. `heygen`,
`synthesia` and `elevenlabs` are billed by those services directly and do **not**
go through this app's budget caps or spend counters.

`ANTHROPIC_API_KEY` must be set (in `.env`) or the run exits immediately;
outline and lesson content are generated through it.

```bash
python run_course.py --topic "Threat Modelling for Web Apps" --modules 3 --lessons 4
```

## Outputs
Written under `<output>/<safe topic name>/`:

| File | Contents |
|---|---|
| `outline.json` | The generated `CourseOutline` — modules, lessons, objectives. |
| `title_slide.png` | Rendered course title slide. |
| per-lesson assets | Script, slides (`.pptx`), rendered slide images, narration audio, avatar video. |
| `index.html` | Course home page linking every lesson and its slide download. |

## How it works
`CourseAgent.run()` is the whole pipeline:

1. `content_generator.generate_outline(request)` → `outline.json`
2. `slide_generator.render_title_slide()` → title slide
3. for each lesson, `_process_lesson()` → script, slides, audio, video
4. `packager.package_course()` → `index.html`

Each step logs as it goes when `verbose=True`, which `run_course.py` sets.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/course_agent.py` | `CourseAgent.run()` / `_process_lesson()` — orchestration. |
| `services/course/models.py` | `CourseRequest`, `CourseOutline`, `CourseAssets`, `DifficultyLevel`. |
| `services/course/content_generator.py` | Outline and lesson script generation. |
| `services/course/slide_generator.py` | Slide rendering, including the title slide. |
| `services/course/video_assembler.py` | Narration + avatar video per lesson. |
| `services/course/packager.py` | `build_index_html()` / `package_course()`. |
| `providers/avatar/`, `providers/voice/` | Pluggable avatar and voice backends (`mock` by default). |
| `run_course.py` | CLI entry point and flag parsing. |

## Notes
- Cost scales as `modules × lessons`. The defaults (2 × 2) are a deliberately
  small smoke test; a 12 × 10 course is 120 lessons of generation and media.
- Because it has no panel, it is not in the registry and does not appear in the
  sidebar or in Settings.
