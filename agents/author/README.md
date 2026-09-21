# Book Author agent (`agents.author`)

Owns long-form ideation, outlining, character and world development, drafting,
continuation and revision for fiction and non-fiction.  Imprint imports
`AuthorAgent` from `agents.author`; the private implementation is `agent.py`.

The umbrella owns the editor, project record, provider execution, request guard
and export UI.  Book export lives in this package's `book_exporter.py`.

## Files

- `__init__.py` — public interface; re-exports `AuthorAgent` from `agent.py`.
- `agent.py` — the `AuthorAgent` implementation plus its four system prompts:
  - `SYSTEM_PROMPT` / `SYSTEM_PROMPT_NONFICTION` — drafting personas for
    fiction and non-fiction respectively, with a structured
    `[DRAFT]`/`[OUTLINE]`/`[CHARACTER]` response format and genre/voice/
    argument guidance.
  - `PUBLISH_SYSTEM_PROMPT` — publishing-document specialist (synopses, query
    letters, book proposals, back-cover blurbs, author bios, chapter
    breakdowns) with separate fiction vs. non-fiction document standards and
    comp-title strategy.
  - `MARKET_SYSTEM_PROMPT` — marketing copywriter covering per-platform copy:
    Amazon description, a full KDP listing package, Goodreads blurb,
    Instagram, X/Twitter thread, TikTok/BookTok caption, newsletter, press
    release, book club questions, ARC outreach, podcast pitch, author website
    bio, Pinterest pin description, YouTube description and launch-team email.
  - `AuthorAgent.build_messages(prompt, consistency_context, book_profile_context,
    content_type)` — builds the chat payload for drafting, selecting the
    fiction or non-fiction system prompt by `content_type` and appending
    book-profile / consistency context when supplied.
  - `AuthorAgent.build_publish_messages(prompt, book_profile_context)` /
    `build_market_messages(prompt, book_profile_context)` — same pattern using
    `PUBLISH_SYSTEM_PROMPT` / `MARKET_SYSTEM_PROMPT`.
- `book_exporter.py` — chapter detection (`split_into_chapters()`,
  `find_chapter_offsets()`) and EPUB/DOCX/PDF export (`export_book()`).
- `recommendations.py` — exports `RECOMMENDATION_PROFILE` (an `AgentProfile`)
  tagged `creative`, `longform`, `editing`, weighted heavily toward quality
  (0.48) and context (0.16) over cost (0.08), with affinity across most
  providers (Anthropic 1.0, OpenAI 0.86, Gemini 0.82, Qwen 0.82, Kimi 0.80,
  DeepSeek 0.74, Ollama 0.66). Discovered by
  `agents.recommendation_profiles.profile_for("author")`.

User guidance: `docs/agents/author.md`.

Run focused coverage with `pytest tests/test_agents_scenarios.py tests/test_book_pipeline.py`.
