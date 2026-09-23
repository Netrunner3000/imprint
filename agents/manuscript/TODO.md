# Publishing Manager — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)
> agent `agent:<key>` (optional; only meaningful in a parent project's shared TODO.md — not needed here, this file already belongs to Publish alone)

---

## v1 — current

- [x] `P1` Move the Publish panel and handlers from `main.py` into this package. Done 2026-09-21: `panel.py` owns the Overview (metrics, Ask, todos, Connections), Quote Finder, Quote Graphics, Shorts and Calendar tabs with all four guarded flows keeping per-flow request tokens (ask, quote suggestions, calendar captions, ElevenLabs narration); the umbrella keeps thin compatibility delegates, the cross-panel next-step banner, and the worker attributes its shutdown sweep watches.
- [x] `P1` Make one Project record the source for title, author and approved manuscript. Completed 2026-09-24: working Write text, approved immutable versions and approved export receipts have separate identities. **Export Approved…** records the selected version and file hash; **Submission Ledger…** attaches a manual retailer/date/reference-or-evidence note only while the file matches. These entries remain self-reported, not retailer API receipts.
- [ ] `P2` Replace monospace royalty summaries with shared charts.
- [ ] `P2` Add explicit sync/error states for publishing integrations.
