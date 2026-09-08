# Imprint — Suggestions

Ideas not yet committed to. Status: `IDEA` · `CONSIDERING` · `PLANNED` · `DONE` · `REJECTED`

---

## v2 — in the current arc

| # | Suggestion | Category | Effort | Status |
|---|---|---|---|---|
| 1 | Refactor Phase 4 — one module per agent panel (`ui/panels/author.py`, …). Phase 3 (the `AgentHost` protocol + shared `AgentPanel` base) shipped; see `TODO.md`. | design | L | PLANNED |
| 3 | Remove the dead `ops_identity` sidebar entry — listed in `agent_titles` with no implementation behind it | bug | XS | DONE |
| 5 | Budget card layout — the €1 session / €5 daily figures deserve a progress bar, not two labels. Session and Daily now share one row (the € moved into the card heading to make room), but neither field is a progress bar yet. | design | S | CONSIDERING |
| 6 | Per-agent cost breakdown in the cost dialog, so it's visible which agent is eating the daily cap | feature | M | IDEA |
| 13 | Reshape the left-nav sidebar into tabs (Write / Audio / Web / Gigs) per FORK_PLAN.md step 4 | design | L | CONSIDERING |

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
