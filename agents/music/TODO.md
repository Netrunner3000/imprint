# Music — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)
> agent `agent:<key>` (optional; only meaningful in a parent project's shared TODO.md — not needed here, this file already belongs to Music alone)

---

## v1 — current

- [x] `P1` Music's layout and release-plan request/result handlers live in `panel.py`; the shared guard, worker factory and history remain in the umbrella.
- [ ] `P2` Retire the temporary host-control aliases after recommendation and tooltip bindings use the Music panel contract directly.
- [x] `P2` Ship the Suno-assisted "Songs & Albums" workflow (`suno_panel.py`, `SUNO_WORKFLOW.md`) — draft lyrics/prompts, hand off to the user's own Suno account, import the downloaded audio into the library.
- [ ] `P2` Store release plans as structured Project data rather than prose only.
- [ ] `P2` Feed real campaign and revenue outcomes into future release plans.
- [ ] `P3` Add distributor-specific validation checklists.
