# Handover: Author Agent — Publishing & Marketing Session
**Date:** 2026-07-30  
**Project:** `sentinel_ai` — `agents/author_agent.py`

---

## Context

The user finished writing a book:

- **Title:** YOU DON'T CHASE: The Zodiac Guide to Modern Dating, Power, and the Art of Being Chosen
- **Author name:** Celeste Morgan (pen name)
- **File:** uploaded as PDF (123 pages, non-fiction)
- **Genre:** Self-help / Dating & Relationships / Astrology crossover
- **Audience:** Women 25–40 navigating modern dating apps
- **Voice:** Sharp, strategic, unapologetic — not soft dating advice
- **Structure:** 4 parts (attraction psychology foundations → 12 zodiac male profiles with scenarios/scripts/red flags → digital dating toolkit → strategic close) + appendices
- **Publishing path:** Undecided between self-publishing (KDP) and traditional (querying agents)

---

## What Was Done This Session

### Files changed

**`sentinel_ai/agents/author_agent.py`** — Both system prompts were rewritten:

- `PUBLISH_SYSTEM_PROMPT`: Was fiction-only. Now has an explicit fiction vs non-fiction section. Added non-fiction synopsis standard (thesis summary, not plot arc), non-fiction query letter standard (market need + platform first, not protagonist + stakes), a full structured non-fiction book proposal template (6 sections), and comp title strategy guidance.

- `MARKET_SYSTEM_PROMPT`: Added Pinterest pin description, YouTube video description, launch team recruitment email. Expanded BookTok guidance (first-line-as-preview, pattern interrupts). Added Amazon bullet list format for descriptions. Added copy principles specific to self-help/empowerment books and astrology-adjacent content.

**`sentinel_ai/config/agents.json`** — Added `"author"` to the agents list.

**`sentinel_ai/agents/router_agent.py`** — Added routing keywords so publishing/marketing queries (query letter, blurb, Amazon description, TikTok caption, etc.) route to the `author` agent instead of falling through to `chat`.

---

## What Still Needs to Be Built

### 1. BookProfile injection (highest priority)

Every author agent request currently starts from scratch — there is no persistent book context. The user has to re-explain the book every time.

**The fix:** Add a `BookProfile` dataclass (or a `book_profile.json` in `sentinel_ai/config/`) that the panel populates once, and inject it at the top of every system prompt as a structured block:

```
BOOK CONTEXT
Title: {title}
Author: {author}
Genre: {genre}
Hook: {hook}
Word Count: {word_count}
Publishing Path: {path}  # "self-pub" or "traditional"
Target Reader: {target_reader}
Comp Titles: {comp_titles}
```

The `AuthorAgent.build_publish_messages()` and `build_market_messages()` methods should accept a `book_profile: dict` argument and prepend this block to the system prompt.

### 2. KDP-specific section in MARKET_SYSTEM_PROMPT

Self-publishing on Amazon requires assets the current prompt doesn't address:
- **Category selection:** 2 BISAC categories (for this book: *Self-Help > Love & Romance* and *Body, Mind & Spirit > Astrology & Horoscopes*)
- **7 backend keywords:** Not hashtags — actual Amazon search strings (e.g. "dating advice for women zodiac", "how to attract men psychology", "modern dating guide women")
- **Pricing guidance:** For a 123-page non-fiction, $7.99–$9.99 ebook / $12.99–$14.99 paperback is the standard KDP range for this genre

Add a `KDP LISTING` document type to `MARKET_SYSTEM_PROMPT`.

### 3. Non-fiction Write mode

`SYSTEM_PROMPT` (Write mode) is entirely fiction-focused (scenes, dialogue, characters, world-building). If the user wants help with the book content — tightening an argument, improving a chapter's flow, adding case studies, strengthening the voice — the current Write mode gives the wrong frame.

Add a non-fiction section covering: argument strengthening, chapter-level structure, evidence integration, voice consistency, and cutting without losing meaning.

### 4. File output

Publishing documents should save as `.docx` (agents specify this for query letters) or formatted `.txt`. Currently everything goes into Sentinel AI's output box. The Manuscript panel already has a "Save as File" button — verify it's wired to the author agent's publish/market outputs.

---

## What the Agent Does Well (don't break)

- Blurb, query letter, Amazon description, social posts — all generate well with the improved prompts
- The three-method pattern (`build_messages`, `build_publish_messages`, `build_market_messages`) is clean — keep it
- The panel (section 5.11 in the README) has a solid three-mode UI (Write / Publish / Market) — no structural changes needed there

---

## Suggested Build Order

1. `BookProfile` injection — unblocks everything else, makes all outputs usable without re-briefing
2. KDP listing document type — needed if user goes self-pub route
3. Non-fiction Write mode additions — quality of life for future books
4. File output verification — low effort, high value

---

## Notes

- The README (`sentinel_ai/README.md`) section 5.11 documents the Manuscript Agent in full detail — read it before touching the panel code
- `agents.json` now lists: `["chat", "writing", "coding", "osint", "audiobook", "author"]`
- The router keyword list in `router_agent.py` is intentionally broad — test it doesn't false-positive on general "write" queries (the word "write" was removed from the writing agent route to avoid routing all writing to the author agent)
