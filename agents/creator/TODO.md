# Brand Creator — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)
> agent `agent:<key>` (optional; only meaningful in a parent project's shared TODO.md — not needed here, this file already belongs to Creator alone)

---

## v1 — current

- [ ] `P2` `@me` Read the actual 18 U.S.C. §2257 requirements before trusting the performer records table. It records *that* documents exist and where they are held, which is the right shape, but the field list was designed from a general understanding rather than from the regulation. This is a legal obligation, not a feature. *(moved from imprint/TODO.md)*
- [x] `P1` Move the Creator panel and handlers from `main.py` into this package. Done 2026-09-21: `panel.py` owns the profile form, consent-aware compose controls, all seven tabs (Draft, Calendar, Earnings, Voice, Media, Agency, Records) and every handler, with the drafting token on the panel and the Higgsfield teaser token in its job context — nothing resolves by the shared "creator" name (the teaser's old `or "creator"` record fallback is gone). The umbrella keeps thin delegates for the OnlyFans handoff and tests, and the worker attributes its shutdown sweep watches; the teaser output dir moved off BASE_DIR onto the writable base.
- [ ] `P1` Finish the calendar as a real week view with rescheduling and export.
- [ ] `P2` Turn revenue attribution into shared charts and drafting signals.
- [ ] `P2` Define a stable handoff contract for every venture using Creator.
