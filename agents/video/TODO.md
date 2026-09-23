# Video & Ad Generator — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)
> agent `agent:<key>` (optional; only meaningful in a parent project's shared TODO.md — not needed here, this file already belongs to Video alone)

---

## v1 — current

- [x] `P0` Remove the Sora 2 direct route and adapter ahead of the **24 September 2026** API shutdown. OpenAI has not announced a direct-video successor, so Sora is absent from the catalog and the handler rejects a stale selection before authorization. Gemini, Qwen and Higgsfield direct routes and the GPT Image scene pipeline remain available.
- [x] `P1` Move the Video panel and handlers from `main.py` into this package. Done 2026-09-21: `panel.py` owns the Render/Library tabs, all render lifecycles (pipeline, Gemini/Wan direct, Higgsfield estimate→render) with the request token kept per flow, and the vidforge-missing notice; the umbrella keeps thin delegates and the worker attributes its shutdown sweep watches.
- [x] `P1` Persist provider jobs and resume polling after app restarts. Done 2026-09-22: every direct render (Gemini, Qwen, Higgsfield) writes a `video_jobs` row before the create POST and follows each provider transition; `VideoPanel.resume_pending_jobs()` runs one event-loop turn after startup, restores the budget reservation through the new `restore_request()` guard method (never re-asks — the money was approved pre-restart), re-polls via `agents/video/workers.py::VideoResumeWorker` (Higgsfield/Wan resume from the job id; Gemini Veo via the new `resume_video()`), downloads, bills exactly once and lands the clip in the library. Unacknowledged submissions are marked `lost` and surfaced, never billed; a local poll timeout keeps the row pending for the next launch. 12 tests incl. a full window-level reconciliation.
- [x] `P1` Link finished clips to the shared Project. Done 2026-09-23: pipeline and direct renders link verified local MP4s to the Project captured at authorization. Resumed provider jobs use the Project ID saved in their durable job row. The shared vidforge Library still needs Project grouping/filtering (umbrella Project P1).
- [ ] `P2` Give every direct-video provider the same cancel/status contract.
