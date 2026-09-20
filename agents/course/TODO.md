# Course Generator — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)
> agent `agent:<key>` (optional; only meaningful in a parent project's shared TODO.md — not needed here, this file already belongs to Course Generator alone)

---

## v1 — current

- [ ] `P1` `security` Bill and guard course runs. `run_course.py` drives modules × lessons Anthropic calls plus optional ElevenLabs/HeyGen renders with no estimate, no confirmation and no usage row — course spend is invisible to the GUI's daily cap. Pre-compute an estimate, require y/N before running, pass `services/api_limits.py` timeouts to the Anthropic client (`services/course/content_generator.py:16` builds a bare `anthropic.Anthropic` today), and log each request through `UsageTracker` under `agent='course'`.
- [ ] `P1` Move `services/course/` under this package after dependency review.
- [ ] `P2` Add a supported Imprint workspace instead of CLI-only operation.
- [ ] `P2` Add resumable stage manifests and artifact validation.
- [ ] `P3` Add focused tests for provider and packaging failures.
