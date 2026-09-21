# Web Developer — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)
> agent `agent:<key>` (optional; only meaningful in a parent project's shared TODO.md — not needed here, this file already belongs to Site Builder alone)

---

## v1 — current

- [x] `P1` Site Builder's panel, guarded generation lifecycle, output parsing, copy and export now live in `panel.py`.
- [x] `P2` Retire temporary host-control aliases after recommendation and tooltip bindings use the panel contract directly. Done 2026-09-21, in the sweep that finished the pattern music started: the panel no longer mirrors its widgets onto the host, every shared consumer (tooltips, recommendation installs, context watchers, panel_base lookup) resolves through `GodAI._find_control()`, and the ownership test asserts the absence of aliases.
- [ ] `P2` Export structured multi-file projects, not only one response blob.
- [ ] `P2` Add automated HTML and accessibility validation before export.
- [ ] `P3` Add safe local preview with explicit external-resource controls.
