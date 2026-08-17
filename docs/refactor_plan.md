# Splitting `main.py` — plan

`main.py` is 11,902 lines. `GodAI` alone holds 387 methods. This is the plan for
TODO.md #2, written before moving any code.

## What is actually in there

Measured, not estimated:

| region | methods | lines |
|---|---:|---:|
| 15 agent verticals (panel + runners + callbacks + parsing) | ~225 | 6,280 |
| shared core (chrome, styling, dialogs, request guard, workers) | ~160 | 5,389 |

Largest verticals: author 1,195 · manuscript 911 · nfl_bet 480 · wifi 477 ·
ops_identity 436 · fiverr 435 · osint_heavy 434 · bug_bounty 386 · music 339 ·
health 308 · webdesign 293 · manager 245 · osint 227.

Largest single methods: `build_author_panel` 556 · `build_center_panel` 328 ·
`apply_global_style` 312 · `build_right_panel` 300 · `show_model_guide` 269 ·
`_seed_tooltips` 244.

## The finding that makes this tractable

Each agent vertical was checked for how many `self.*` attributes it uses that it
does not own:

| vertical | attrs used | not owned |
|---|---:|---:|
| author | 135 | 27 (20%) |
| osint | 87 | 23 (26%) |
| music | 51 | 16 (31%) |

The verticals are ~75% self-contained, and the external references are almost
the *same set every time*:

- provider clients — `ollama` `openai` `deepseek` `kimi` `gemini` `anthropic` `qwen`
- the request guard — `authorize_request` `record_request` `abandon_request`
  `note_request_usage` (added for TODO #1)
- `run_backend` · `agent_instances` · `_note_failure` · `show_agent_docs` ·
  `execution_mode_box`

That is a ~15-member interface, not a tangle. Panels can be extracted against it
without rewriting their internals.

## Target layout

```
main.py                 # entry point + GodAI shell only  (~800 lines)
ui/
  workers.py            # ChatWorker, SubprocessWorker, ModelPullWorker,
                        #   FiverrImageWorker, ShortsWorker           (~200)
  widgets.py            # FlowLayout, CollapsibleSection              (~170)
  style.py              # apply_global_style + the panel stylesheets  (~570)
  tooltips.py           # _seed_tooltips data                         (~245)
  dialogs.py            # show_settings, show_model_guide, show_cost_history,
                        #   show_run_log                              (~930)
  host.py               # AgentHost protocol — the ~15 shared members
  book_widgets.py       # already exists
  panels/
    base.py             # AgentPanel: provider/model row, model loading,
                        #   run/stop wiring, the FlowLayout control row
    author.py  manuscript.py  nfl_bet.py  wifi.py  ops_identity.py
    fiverr.py  osint_heavy.py  bug_bounty.py  music.py  health.py
    webdesign.py  manager.py  osint.py  chat.py
```

`services/` keeps all non-UI logic, as it does today.

## Order of work

Each phase ends green: `pytest tests/` plus the offscreen build check
(`QT_QPA_PLATFORM=offscreen` constructing `GodAI()`), which catches import and
layout breakage without a display.

**Phase 1 — lift out what barely touches `self`. DONE (2026-08-12).**

| module | lines | contents |
|---|---:|---|
| `ui/workers.py` | 212 | ChatWorker, SubprocessWorker, ModelPullWorker, FiverrImageWorker, ShortsWorker |
| `ui/widgets.py` | 161 | FlowLayout, CollapsibleSection |
| `ui/style.py` | 315 | `GLOBAL_STYLESHEET` |
| `ui/tooltips.py` | 252 | `seed_tooltips(app)` |

`main.py` 11,902 → **11,007** lines. Verbatim moves: the tooltip body is
unchanged apart from the receiver being named `app`, so its section comments and
application order are preserved.

Verified beyond "it imports": the stylesheet is applied at runtime (9,579 chars,
accent `#3cff88` present) and tooltips are present on `send_btn`, `estimate_btn`,
`allow_kimi_checkbox` and the sidebar agent buttons. 219 tests green, offscreen
`GodAI()` builds.

One trap worth repeating for later phases: rewriting `self` → `app` with
`\bself\.` misses bare `self` in `hasattr(self, ...)`, which fails only at
runtime, not at import. The offscreen build check caught it; a compile check
would not have.

**Phase 2 — extract the dialogs. DONE (2026-08-12).**

| module | lines | contents |
|---|---:|---|
| `ui/dialogs.py` | 735 | `show_cost_history` 144 · `show_run_log` 92 · `show_settings` 203 · `show_model_guide` 269 |

A net **−696** lines in `main.py`. Each moved body is byte-identical to
the original after `self`→`app` and one dedent — verified by diffing the
transformed original against the extracted function, not by eye. `GodAI` keeps
four three-line wrappers so every call site and the Docs/Settings buttons are
untouched.

The dependency surface turned out to be small: `show_cost_history` needs only
`usage_tracker`, `show_run_log` only `run_logger`, `show_settings` seven members,
`show_model_guide` six — plus `app` as the dialog parent.

Two traps, both runtime-only:

- The `hasattr(self, …)` trap from Phase 1 recurred — 6 occurrences here. Fixed
  by rewriting `\bself\b` rather than `\bself\.`.
- **Missing imports do not fail at import time.** The moved bodies referenced
  five provider wrappers plus `Registry` and `Validator`; `ui/dialogs.py`
  imported and compiled cleanly, and only `show_model_guide` raised
  `NameError` when actually opened. Guessing the import list from a regex is not
  enough — walk the AST for `Load`ed names not bound in the module, which found
  all seven at once.

Check used, beyond constructing `GodAI`: stub `QDialog.exec`, open all four
dialogs, and assert on their contents (provider names and key status in the
model guide, non-empty cost history, populated Settings fields).

**Phase 3 — define `AgentHost` and the `AgentPanel` base.** No code moves yet.
Write the protocol from the shared-member list above, and pull the repeated
provider/model row + `*_load_models` bodies (16 near-identical methods, 365
lines) into the base class.

**Phase 4 — move agent verticals one at a time**, smallest first:
osint (227) → manager (245) → webdesign (293) → health (308) → music (339) →
bug_bounty (386) → osint_heavy (434) → fiverr (435) → ops_identity (436) →
wifi (477) → nfl_bet (480) → manuscript (911) → author (1,195).

Smallest first is deliberate: the first move proves the base class and the host
protocol on a cheap target, and each later one is the same shape.

**Phase 5 — `GodAI` becomes a shell**: build the three panes, own the shared
services, hold the panel instances.

## Two decisions to make before Phase 3

**Mixins or composition.** Mixins (`class GodAI(QWidget, AuthorPanelMixin, …)`)
are a verbatim cut-and-paste with no call-site edits — fast, and the file
shrinks immediately, but every panel still shares one namespace, so the coupling
is unchanged and name collisions stay possible. Composition (each panel a real
`AgentPanel` holding its own widgets, talking to the host through the protocol)
is the actual fix and is what makes panels testable in isolation.

Recommendation: composition. The coupling numbers above say the cost is
affordable, and mixins would leave #2 half-done while looking finished.

**Phases 1–2 are complete**: **−1,591 lines** out of `main.py` (895 in Phase 1,
696 in Phase 2), with no design commitment made.

Measure the phase delta, not the file total. The absolute count drifts upward
while other work lands — `main.py` read 10,391 at the Phase 2 commit and 10,394
one autosync commit later, so a total quoted here is stale by the time it is read.

Phases 3–5 are the real refactor and want a clear run. The mixins-vs-composition
decision above is still open and should be settled first.

## Risks

- **No UI test coverage.** The 219 tests cover agents, cost and the request
  guard — not layout. The offscreen `GodAI()` build is the only automated check
  that a panel still constructs, so run it after every move.
- **`_pending_requests` is keyed by agent name** (TODO #1). Panels moving to
  their own classes is the natural moment to key it by run id instead.
- **Do not renumber during a move.** Moving a vertical and editing it in the
  same commit makes a regression impossible to bisect. Move verbatim, commit,
  then clean up.
