# Video — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)
> agent `agent:<key>` (optional; only meaningful in a parent project's shared TODO.md — not needed here, this file already belongs to Video alone)

---

## v1 — current

- [x] `P0` Retire the Sora 2 direct route for new Imprint jobs ahead of the **24 September 2026** API shutdown. OpenAI has not announced a direct-video successor, so Sora is absent from the selectable catalog and the handler rejects a legacy selection before authorization. Legacy adapter code remains for previously submitted jobs; Gemini, Qwen and Higgsfield direct routes and the GPT Image scene pipeline remain available.
- [ ] `P1` Move the Video panel and handlers from `main.py` into this package.
- [ ] `P1` Persist provider jobs and resume polling after app restarts.
- [ ] `P2` Give every direct-video provider the same cancel/status contract.
