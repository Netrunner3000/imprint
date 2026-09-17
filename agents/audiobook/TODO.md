# Audiobook — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)
> agent `agent:<key>` (optional; only meaningful in a parent project's shared TODO.md — not needed here, this file already belongs to Audiobook alone)

---

## v1 — current

- [x] `P1` Move the Convert and Listen workspace layout into `panel.py`.
- [x] `P1` Move Audiobook library, resume and playback actions from `main.py` into this package.
- [ ] `P1` Move paid Audiobook conversion handlers from `main.py` into this package; remove temporary host control aliases.
- [x] `P2` Add keyboard playback controls and a sleep timer.
- [ ] `P2` Persist conversion jobs so interrupted books can resume safely.
- [ ] `P3` Evaluate additional narration providers behind one voice protocol.
