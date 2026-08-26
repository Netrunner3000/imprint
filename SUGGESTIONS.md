# Create & Publish — Suggestions

Ideas not yet committed to. Status: `IDEA` · `CONSIDERING` · `PLANNED` · `DONE` · `REJECTED`

---

## v2 — in the current arc

| # | Suggestion | Category | Effort | Status |
|---|---|---|---|---|
| 1 | Finish the `main.py` split — Phase 3 `AgentHost` protocol + `AgentPanel` base, then one module per agent panel | design | L | PLANNED |
| 2 | Key `_pending_requests` by run-id instead of agent name, so two runs of the same agent can't clobber each other's context | bug | S | PLANNED |
| 3 | Remove the dead `ops_identity` sidebar entry — listed in `agent_titles` with no implementation behind it | bug | XS | DONE |
| 4 | Kimi prompt caching in the pricing model — cached input is billed differently and the estimate currently overstates it | feature | M | CONSIDERING |
| 5 | Budget card layout — the €1 session / €5 daily figures deserve a progress bar, not two labels | design | S | CONSIDERING |
| 6 | Per-agent cost breakdown in the cost dialog, so it's visible which agent is eating the daily cap | feature | M | IDEA |
| 11 | Clean up `main.py` dead code left by the security-vertical strip (unreachable icon/label dicts, `osint` keyword branch in `get_recommended_setup()`, the `agent_box` combo still injecting `"manager"`) | bug | S | PLANNED |
| 12 | Prune `CreateAndPublish.spec`'s stale `whois`/`dns` hidden-imports, left over from the deleted `providers/domain_lookup` | infra | XS | PLANNED |
| 13 | Reshape the left-nav sidebar into tabs (Write / Audio / Web / Gigs) per FORK_PLAN.md step 4 | design | L | CONSIDERING |
| 14 | `docs/agents/course.md` reference page for the CLI-only Course Generator | docs | XS | IDEA |

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
