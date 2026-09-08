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
