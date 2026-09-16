# Social — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)
> agent `agent:<key>` (optional; only meaningful in a parent project's shared TODO.md — not needed here, this file already belongs to Social alone)

---

## v1 — current

- [ ] `P2` `@me` Verify the posting notes in `services/social_platforms.py` against each platform's current terms before wiring credentials. They were written from general knowledge rather than checked against the live APIs, and X's pricing in particular changes often. *(moved from imprint/TODO.md)*
- [ ] `P1` Move the Social panel and handlers from `main.py` into this package.
- [ ] `P1` Add a durable publishing queue with retry and idempotency rules.
- [ ] `P2` Join published variants to reach, clicks and downstream revenue.
- [ ] `P2` Add account-connection onboarding with clear permission scopes.
