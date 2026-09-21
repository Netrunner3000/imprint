# Course Generator — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)
> agent `agent:<key>` (optional; only meaningful in a parent project's shared TODO.md — not needed here, this file already belongs to Course Generator alone)

---

## v1 — current

- [x] `P1` `security` Bill and guard course runs. Fixed 2026-09-21: `run_course.py` prints an upper-bound estimate (1 outline call + modules × lessons lesson calls, priced through `UsageTracker.calculate_cost_eur`), shows today's studio spend, requires y/N (`--yes` for scripted runs), and warns that ElevenLabs/HeyGen provider billing is outside the estimate. `content_generator` builds its client with the shared api_limits timeout/retry policy, degrades gracefully on a missing key, tallies real token usage per call (also on failure partway), joins text blocks instead of indexing `content[0]`, and the CLI logs the run's actual spend through `UsageTracker` under `agent='course'` — course runs land in the same daily totals the GUI enforces.
- [ ] `P1` Move `services/course/` under this package after dependency review.
- [ ] `P2` Add a supported Imprint workspace instead of CLI-only operation.
- [ ] `P2` Add resumable stage manifests and artifact validation.
- [ ] `P3` Add focused tests for provider and packaging failures.
