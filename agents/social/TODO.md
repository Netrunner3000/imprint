# Social Media Campaign Manager — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)
> agent `agent:<key>` (optional; only meaningful in a parent project's shared TODO.md — not needed here, this file already belongs to Social alone)

---

## v1 — current

- [ ] `P2` `@me` Verify the posting notes in `agents/social/platforms.py` against each platform's current terms before wiring credentials. They were written from general knowledge rather than checked against the live APIs, and X's pricing in particular changes often. *(moved from imprint/TODO.md)*
- [x] `P1` Move the Social panel and handlers from `main.py` into this package. Done 2026-09-21: `panel.py` owns the campaign form, compose controls, Draft/Schedule/Analytics/Accounts tabs and every handler, with both guarded flows keeping per-flow request tokens (post writing under "social"; the clip brief plus its "video"-keyed render). The umbrella keeps thin compatibility delegates and the worker attributes its shutdown sweep watches.
- [x] `P1` Add a durable publishing queue with retry and idempotency rules. Done 2026-09-22: every direct post now gets one durable `social_publish_jobs` row before the outbound call and an atomic claim prevents double-click delivery. Known rejections are retryable; timeouts, crashes and other ambiguous outcomes become **Verify platform** and are never retried automatically. Restart recovery, explicit risk-labelled retry, manual resolution and completed-delivery duplicate blocking are covered by focused tests.
- [ ] `P2` Join published variants to reach, clicks and downstream revenue.
- [ ] `P2` Add account-connection onboarding with clear permission scopes.
