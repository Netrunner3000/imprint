# Video

> **Outcome:** choose an implemented visual route, render one bounded video,
> monitor it safely, and find the accepted output without blind retries.

![Video workspace](../img/agent-video.png)

## Prerequisites

- The nested vidforge project is present and importable.
- Topic/source facts, target format, and acceptance checklist are ready.
- Script/narration/visual/stock keys required by the chosen route are eligible.
- The output directory is writable and ffmpeg is available for assembly routes.
- Sora is retired for new Imprint jobs ahead of its 24 September 2026 API
  shutdown. Choose Gemini, Qwen or Higgsfield for direct video, or GPT Image
  for an assembled video.

## Control atlas

| Area | Meaning |
|---|---|
| Topic | Explicit brief; empty can consume the next configured topics-file item |
| Format | Long-form assembled pipeline or social/direct-capable clip context |
| Visual provider/model | Only implemented image/video adapters; badge reflects current capability |
| Aspect / Clip length | Options adapt to provider/model capability |
| Render Video / Stop | Submit once; cancellation differs after provider acceptance |
| Cost/status/progress/log | Reserve and stages: script, narration, captions, visuals, clips, audio, assembly, thumbnail |
| Library | Shared vidforge history with Play, Show in Finder, and Rescan |

## Worked run

1. Enter a small topic with audience, factual boundaries, duration, and CTA.
2. Select format, then provider/model. Recheck aspect, length, recommendation,
   note, and estimate after each capability-changing selection.
3. For a first test choose the minimum practical duration and press **Render
   Video** once.
4. Watch the log to identify whether this is an assembled narrated pipeline or
   a direct asynchronous provider job.
5. If stopping, press once and read the result. Keep monitoring accepted jobs
   that cannot be cancelled so the paid file is not lost.
6. Open Library, play the actual file, reveal it in Finder, and verify duration,
   dimensions, audio, captions, visuals, claims, pacing, and CTA.

## How to read the output

Text providers can prepare scripts/prompts but are not video providers. A 100%
local progress bar does not replace playback QA. Provider completion does not
prove copyright, likeness, disclosure, platform compliance, or marketing value.

## Acceptance checklist

- [ ] Correct dimensions, duration, codecs, audio, captions, and safe areas.
- [ ] Factual claims and visual/voice/likeness rights are reviewed.
- [ ] No missing/duplicate scenes or expired hosted asset remains.
- [ ] Actual output path, provider job state, and cost are recorded.
- [ ] CTA maps to one measurable next action.

## Cost, cancellation, and gates

Images/video may bill by asset or duration; narration and script may add costs.
Veo/Gemini, Wan/Qwen, and other direct jobs may have no safe cancellation
after acceptance. Higgsfield cancellation can depend on queued/processing state.
Humans approve paid submission and public release.

## Verification

Play the local file from Library/Finder and compare its actual duration,
dimensions, captions, sound, visuals, claims, and cost with the submitted brief.

## Common failures

**vidforge unavailable:** restore the nested project/dependency.  
**Stop appears ineffective:** identify the active provider state; do not submit
a duplicate.  
**Assembly fails:** preserve the log and verify ffmpeg/output permissions.  
**Output missing:** check Library/output folder and hosted URL expiry first.

## Done when

The actual file passes playback QA, is saved locally, its route/cost/job state
are known, and publication remains a separate approved step.

## Next action

Prepare distribution in [Social](25-social.md) and measurement in
[Funnels, attribution, and cohorts](34-funnels-attribution.md).
