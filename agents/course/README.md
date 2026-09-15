# Course Generator agent

Owns the CLI pipeline that turns a topic into an outline, lessons, slides,
narration, optional avatar video and a packaged course.  Its public API is
`agents.course.CourseAgent`; `run_course.py` is the umbrella entry point.

## Files

- `__init__.py` — public interface; re-exports `CourseAgent` from `agent.py`.
- `agent.py`
  - `_provider_from_name(provider_name, kind)` — lazily imports and
    instantiates an avatar provider (`mock`, `heygen`, `synthesia`) or a voice
    provider (`mock`, `elevenlabs`) by name, raising `ValueError` on an
    unknown provider or kind.
  - `CourseAgent.__init__(avatar_provider, voice_provider, avatar_config,
    voice_config, verbose)` — accepts either a provider name string or an
    already-constructed `AvatarProvider`/`VoiceProvider` instance.
  - `CourseAgent.build_messages(prompt)` — chat-panel system prompt that asks
    for topic, difficulty, target audience and scope up front.
  - `CourseAgent.run(request)` — the full pipeline: generates the outline via
    `services.course.content_generator`, writes `outline.json`, renders the
    title slide, runs `_process_lesson` for every lesson in every module, then
    packages everything into a browsable course via `services.course.packager`.
  - `CourseAgent._process_lesson(...)` — per lesson: generates script/slides/
    quiz content, saves `script.txt` and `quiz.json`, renders slide images and
    a `slides.pptx`, synthesizes narration audio, generates the avatar video,
    and assembles the final lesson video. Voice synthesis, avatar generation
    and assembly are each wrapped in `try/except` so a provider failure
    degrades that lesson instead of failing the whole course run.
  - `_safe_name(s)` — filesystem-safe slug helper used for output directory
    and file names.

Course-specific generation services currently live under `services/course/`.
User guidance: `docs/agents/course.md`.
