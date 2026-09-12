# Imprint — Suggestions

Ideas not yet committed to. Status: `IDEA` · `CONSIDERING` · `PLANNED` · `DONE` · `REJECTED`

---

## v2 — in the current arc

| # | Suggestion | Category | Effort | Status |
|---|---|---|---|---|
| 1 | Refactor Phase 4 — one module per agent panel (`ui/panels/author.py`, …). Phase 3 (the `AgentHost` protocol + shared `AgentPanel` base) shipped; see `TODO.md`. | design | L | PLANNED |
| 3 | Remove the dead `ops_identity` sidebar entry — listed in `agent_titles` with no implementation behind it | bug | XS | DONE |
| 5 | DONE — Budget card layout. Both caps are progress bars now, and the four spend figures are stat blocks rather than nine lines of prose. The bar turns red at 100%. | design | S | DONE |
| 6 | Per-agent cost breakdown in the cost dialog, so it's visible which agent is eating the daily cap | feature | M | IDEA |
| 13 | DONE — mode tabs, now in the header bar rather than centred over the canvas. | design | L | DONE |

## Creator agent — next arc

Written after building v1. The first three are things I left half-done rather
than ideas: unused schema, an unfinished API loop, and untested handlers.

| # | Suggestion | Category | Effort | Status |
|---|---|---|---|---|
| 20 | DONE — **Voice profile per account.** The biggest quality lever there is. Every draft currently starts from nothing, which is exactly why AI copy reads like AI copy. Store 3–5 of the creator's own posts, plus tone rules, emoji habits, banned words and typical length; inject into every prompt. Without it the drafts are competent and generic — with it they sound like the person. | feature | M | IDEA |
| 21 | DONE — **Finish the Higgsfield loop.** `generate_video()` submits a job and the panel says "check Higgsfield for the result". `HiggsfieldClient.wait()` exists and nothing calls it. Poll on a worker thread, download the mp4, store it against the account and attach it to a calendar item. A half-wired feature is worse than an absent one. | bug | M | IDEA |
| 22 | DONE — **Use `media_path`, or drop it.** The column is in `creator_content` and referenced nowhere in `main.py`. Creator work is media-first: a caption without the photoset it belongs to is half a draft. An asset library that links drafts to the actual files is the missing half. | feature | M | IDEA |
| 23 | DONE — **Close the loop from draft to revenue.** Earnings import currently prints a text summary. What makes it worth having is attribution: which PPV price converted, which hook earned, what a subscriber is worth over time. Chart it, and let the PPV drafter read from it instead of taking a price as a blind argument. | feature | L | IDEA |
| 24 | DONE — **Persona bible.** For `persona` accounts there is a disclosure line and nothing else, so nothing keeps a character consistent between sessions. Appearance, backstory, voice and locked reference images — paired with Higgsfield Soul for visual consistency — is the difference between a persona and a series of unrelated posts. | feature | M | IDEA |
| 25 | DONE — **Hook variants with outcomes.** Creators test openers; the app writes one and forgets it. Generate three, record which was used, join it to what it earned. This is what turns the earnings data into a feedback loop rather than a report. | feature | M | IDEA |
| 26 | DONE — **Performer records for collaborators.** If content is produced with anyone else, US law (18 U.S.C. §2257) requires the producer to keep age and identity records. Nothing here tracks that, and a shoot with a collaborator creates the obligation whether or not the tool knows. Worth a proper records table with the consent model already built for managed accounts. Needs a real read of the requirements first — this is a legal obligation, not a feature. | feature | M | IDEA |
| 27 | DONE — **Fan segments.** A welcome message, a re-engagement message to someone lapsed, and a thank-you to a two-year subscriber are three different messages. The drafter treats them as one. | feature | S | IDEA |
| 28 | PARTIAL — **A calendar that behaves like one.** Today it is a table you append rows to — no week view, no "due today", no reschedule, no export to `.ics` or CSV. | design | M | IDEA |
| 29 | DONE — **Panel handler tests.** `test_creator_agent.py` covers the agent, the content guard and the CSV parser. The panel handlers — save/delete account, schedule, import, the worker lifecycle — have no coverage, which is where the consent rule is actually enforced for a real user. | testing | S | IDEA |
| 30 | DONE — **Agency view across managed accounts.** Consent is recorded per account, but there is no cross-account reporting, no per-account voice, and no commission calculation — the things that make managing several accounts different from managing one. | feature | L | IDEA |

## After the Imprint merge

Written with all five modes shipped and the app rebuilt. The first two are
consequences of what just landed rather than new ideas.

| # | Suggestion | Category | Effort | Status |
|---|---|---|---|---|
| 40 | DONE — **Price the second provider.** Per-unit billing now covers Fiverr images and TTS; Creator renders use Higgsfield's authenticated estimate for the exact prepared payload and pass that amount through the same budget guard. | security | M | DONE |
| 41 | **A doc test that fails when an agent has no guide.** The Learning Centre silently fell a full agent behind twice. `WORKSPACES` is now checked against both `docs/learn/02-agents.md` and `docs/agents/*.md`; the missing OnlyFans sheet was added with the test. | testing | S | DONE |
| 42 | **Project as the object everything hangs off.** A book, a release and a product are each worked on across Write, Audio, Video and Creator, but each mode keeps its own state and the projects rail is decorative. Making Project real — one record the modes read from — is what would turn five tools that share a window into a studio. | design | L | IDEA |
| 43 | DONE — **Video mode.** vidforge imported from the nested repo (not vendored), long-form and clips as one pipeline, cost estimated per stage and charged against the caps. | feature | L | DONE |
| 44 | DONE — **Social mode.** Campaigns, per-platform drafting, cadence scheduling, and real posting for the three platforms where that is possible from a personal account. | feature | L | DONE |
| 45 | **Charts, not monospace.** Three panels now compute genuinely interesting numbers (KDP royalties, creator price points, cost history) and all three render them as aligned text. One small charting layer would serve all of them. | design | M | IDEA |
| 46 | **A "what should I do today" view.** The app knows the publishing todos, the content calendar, which drafts are unposted and which books are part-listened. Nothing assembles that into the one screen a person actually opens in the morning. | feature | M | IDEA |
| 47 | **Retire or rehome the chat agent.** It is still constructed and still owns `normal_panel`, but the tabbed shell reaches no part of it. Either it becomes a real mode or it goes, and with it a meaningful amount of machinery. | infra | M | IDEA |
| 48 | **Back up the writable directory.** Everything that matters — database, keys, chats, logs — lives in one Application Support folder that nothing in this workspace backs up, while `_Admin/backup/` exists and is good at exactly this. One line in `backup_folders.txt`. | infra | XS | IDEA |
| 49 | **Sleep timer and keyboard control for the player.** Resume was the ask and it works; space-to-pause and a sleep timer are what make it something you would actually listen to a novel on. | feature | S | IDEA |
| 50 | DONE — **Make Video's visual provider/model choice real.** Current GPT Image models run through the scene pipeline; Sora, Gemini Omni/Veo, Qwen/Wan and Higgsfield create direct clips; Pexels and Local select their actual visual sources. Retired DALL·E IDs and providers without a video-output API are not offered. | feature | M | DONE |
| 51 | **Migrate Sora before its provider shutdown.** The route is useful for the remaining compatibility window, but the API closes on 24 September 2026. Keep the direct-video adapter boundary and swap in OpenAI's successor when one is published. | maintenance | M | IDEA |

## v3 — bigger swings

| # | Suggestion | Category | Effort | Status |
|---|---|---|---|---|
| 7 | Streaming responses in the chat panel rather than wait-then-dump | feature | L | IDEA |
| 8 | Local model provider (Ollama) as a zero-cost fallback when the budget cap is hit | feature | L | IDEA |
| 9 | Retry-with-backoff wrapper shared by every provider client, instead of per-client handling | infra | M | IDEA |
| 10 | Export a run (prompt + response + usage + cost) as a single markdown file for archiving | feature | S | IDEA |

## Done

| Suggestion | When |
|---|---|
| Video mode — vidforge as an eighth agent, imported from its nested repo rather than vendored; long-form and social clips are one pipeline | Sep 2026 |
| Social mode — the public funnel: campaigns, per-platform drafting, cadence scheduling, and posting for YouTube/Reddit/Pinterest | Sep 2026 |
| Per-unit billing — images, renders and TTS count against the budget caps instead of pricing a $0.04 image at €0.000001 | Sep 2026 |
| `main.py --selftest` — the packaging traps AGENTS.md names, plus proof that vidforge shipped in the bundle | Sep 2026 |
| GUI overhaul — header bar plus two fixed rails instead of a splitter; every panel rebuilt on `ui/forms.py`; one control height enforced in the stylesheet; 58 emoji and 36 colon captions removed; spend as stat blocks and budget bars | Sep 2026 |
| The Gigs and Video image model is a control using the current GPT Image catalog rather than a hardcoded retired DALL·E call; `generate_image()` returns bytes so every model has one caller | Sep 2026 |
| Refactor Phase 3 — `ui/host.py`'s `AgentHost` protocol and `ui/panels/base.py`'s `AgentPanel`, absorbing the five `*_load_models` methods | Sep 2026 |
| `_pending_requests` keyed by request token instead of agent name — two concurrent runs of one agent no longer clobber each other's context | Sep 2026 |
| Kimi prompt caching — `cached_input_per_1m_usd` on the pricing table, captured from the response and billed at the cached rate. Uncovered a bigger bug while wiring it up: the pricing table had no reconciliation path against `config/pricing.json` outside first-run migration, so Kimi/OpenAI/DeepSeek/Gemini were all silently billing €0.00 on this project's own database. `_seed_pricing_from_json()` now reconciles on every launch. | Sep 2026 |
| Cleaned up `main.py` dead code left by the security-vertical strip (unreachable icon/label dicts, the `osint` keyword branch relabelled rather than removed since it's a prompt-keyword branch, the `agent_box` combo no longer injects `"manager"`) | Sep 2026 |
| Pruned `Imprint.spec`'s stale `whois`/`dns` hidden-imports, left over from the deleted `providers/domain_lookup` | Sep 2026 |
| `docs/agents/course.md` reference page for the CLI-only Course Generator | Sep 2026 |
| Removed the dead `ops_identity` sidebar entry (gone by the time this was checked — likely swept up in the security-vertical strip rather than fixed deliberately) | Aug 2026 |
| Saved Chats: agent filter and rename | Aug 2026 |
| `authorize_request` / `record_request` guard applied to all 19 unguarded `ChatWorker` sites | Aug 2026 |
| `FlowLayout` on 13 control rows — panels no longer crush when narrow | Aug 2026 |
| Timeouts on all cloud clients | Aug 2026 |
| Phase 1+2 of the refactor: `ui/workers.py`, `ui/widgets.py`, `ui/style.py`, `ui/tooltips.py`, `ui/dialogs.py` | Aug 2026 |

## Rejected

| Suggestion | Why |
|---|---|
| Fork the ROI / investment agents back in | They moved to SONAR on purpose; two homes for the same logic is worse than one |
