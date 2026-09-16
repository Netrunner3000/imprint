# Video — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)
> agent `agent:<key>` (optional; only meaningful in a parent project's shared TODO.md — not needed here, this file already belongs to Video alone)

---

## v1 — current

- [ ] `P0` `@me` Replace the Sora 2 direct route once OpenAI names a successor. The API is deprecated and shuts down permanently on **24 September 2026**; `media_catalog.SORA_SHUTDOWN_DATE` blocks submissions from that date, so this is a provider migration rather than an outage. Higgsfield and the GPT Image scene pipeline stay available. *(moved from imprint/TODO.md; replaces the untimed 'migrate the Sora route' item that was here)*
- [ ] `P1` Move the Video panel and handlers from `main.py` into this package.
- [ ] `P1` Persist provider jobs and resume polling after app restarts.
- [ ] `P2` Give every direct-video provider the same cancel/status contract.
