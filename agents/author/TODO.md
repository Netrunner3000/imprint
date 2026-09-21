# Book Author — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)
> agent `agent:<key>` (optional; only meaningful in a parent project's shared TODO.md — not needed here, this file already belongs to Draft alone)

---

## v1 — current

- [x] `P1` Move the Draft panel and handlers from `main.py` into this package. Done 2026-09-21, the last panel of Phase 4: `panel.py` owns the project bar, book profile, the Write page (compose deck, manuscript tabs, chapters, document bar) and the Publish & Market pages, with all three flows keeping per-flow request tokens and the still-running-worker guard. The responsive footer moved into the panel's own resizeEvent (the app-level event filter now only handles tooltips); the next-step advisor stays on the umbrella because Publishing Manager shares its banner; save/export dialog defaults moved onto the writable base.
- [ ] `P1` Bind drafts, profiles and exports to the shared Project record.
- [ ] `P2` Add continuity tests across long chapter-generation sessions.
- [ ] `P2` Add evidence/citation controls for non-fiction drafting.
