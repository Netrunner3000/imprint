# Brand & Logo Designer — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)
> agent `agent:<key>` (optional; only meaningful in a parent project's shared TODO.md — not needed here, this file already belongs to Client Gigs alone)

---

## v1 — current

- [x] `P1` Move the Client Gigs panel and handlers from `main.py` into this package. Done 2026-09-21 (commit c4b9cf5, two sessions jointly): `panel.py` owns the layout, all four guarded flows with per-flow request tokens, and the order log; the umbrella keeps thin compatibility delegates and the workers for its global Stop/shutdown sweeps.
- [ ] `P2` Store briefs, revisions and deliveries as one client order record.
- [ ] `P2` Add brand-kit inputs and reusable client preferences.
- [ ] `P3` Add marketplace-policy reminders before listing export.
