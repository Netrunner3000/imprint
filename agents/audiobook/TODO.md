# Audiobook Producer — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)
> agent `agent:<key>` (optional; only meaningful in a parent project's shared TODO.md — not needed here, this file already belongs to Audiobook alone)

---

## v1 — current

- [x] `P1` Move the Convert and Listen workspace layout into `panel.py`.
- [x] `P1` Move Audiobook library, resume and playback actions from `main.py` into this package.
- [x] `P1` Move paid Audiobook conversion handlers from `main.py` into this package. The panel now owns source discovery, exact-text estimation, request authorization/closure, QProcess output/error/exit handling and Stop.
- [ ] `P2` Retire temporary host control and compatibility aliases after shared tooltip, recommendation and umbrella navigation bindings use the panel contract directly.
- [x] `P1` `bug` Book-list selection calls a slot that does not exist — `panel.py:77` connected `estimate_cost_from_selection`, but the host method is `estimate_audiobook_cost_from_selection`; PySide6 swallows the AttributeError, so the per-book cost estimate silently never updated on selection. Fixed same day: the delegating slot (fifth of the f6aefb2 family) plus `test_audiobook_selection_refreshes_the_cost_estimate` in tests/test_panel_layout.py, which fires the real selection signal — this signal→missing-method class has now happened twice and only construction-time wiring was covered.
- [x] `P2` Add keyboard playback controls and a sleep timer.
- [ ] `P2` Persist conversion jobs so interrupted books can resume safely.
- [ ] `P3` Evaluate additional narration providers behind one voice protocol.
