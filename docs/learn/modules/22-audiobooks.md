# Audiobooks

> **Outcome:** create and inspect a short narration sample before authorising a
> full book conversion, then recover listening progress and partial output.

## Prerequisites

- PDF, EPUB, TXT, or MOBI source you are authorised to process.
- OpenAI TTS access; audiobook narration uses it independently of text choices
  elsewhere.
- Writable input/output folders and sufficient cap for the estimated length.

## Control atlas

| Tab | Controls | Meaning |
|---|---|---|
| Convert | Book list, input folder, output folder, Voice, Chunk tokens, Start, Refresh List, Stop, progress/log | Extract, chunk, narrate, and assemble; completed chunks may survive a stop |
| Listen | Rescan, library, Listen, Start Over, Show in Finder | Play completed audio and persist progress keyed to its full path |

## Worked run

1. Put one short authorised sample in the input folder and press **Refresh List**.
2. Select the book and explicitly verify the output folder.
3. Choose Voice. Treat Chunk tokens as a stability/context trade-off: larger
   chunks reduce joins but increase the impact of one failure.
4. Read the automatic cost state. If price or extracted length is unknown, do
   not infer zero cost.
5. Press **Start** once and follow extraction, chunks, narration, assembly, and
   output messages in the log.
6. Listen to beginning, one join, difficult names, and the ending. Inspect the
   MP3 in Finder.
7. In Listen, pause, leave, return, and verify progress resumes. **Start Over**
   deliberately resets that path's listening position.

## How to read the output

A progress value reports pipeline stage, not pronunciation quality or final
rights clearance. A partial job may contain billable, reusable chunks even when
the assembled MP3 is absent.

## Acceptance checklist

- [ ] Source extraction is complete and ordered correctly.
- [ ] Voice, names, punctuation, joins, silence, and loudness are acceptable.
- [ ] Output path and file duration are correct.
- [ ] Full-book estimate/cap includes retries and review time.
- [ ] Rights to narrate and distribute the source are documented.

## Cost, cancellation, and gates

Speech can be billed by characters/tokens. Stop requests the subprocess to end;
it does not reverse completed chunks or charges. Human approval is required
before full conversion and distribution.

## Verification

Play the local sample from its real output path, inspect at least one chunk join,
and confirm Listen restores progress before approving a full conversion.

## Common failures

**No books:** verify format/folder, then Refresh List.  
**Stopped part-way:** inspect output/log and completed chunks before restarting.  
**Resume disappeared:** moving or renaming the MP3 changes its path identity.  
**Bad pronunciation:** test a shorter excerpt/voice; do not discover it after a
full book.

## Done when

The sample passes audio review, the output and cost state are known, and a full
conversion has a reviewed budget and recovery plan.

## Next action

For a catalogue, connect the accepted audiobook to [Publish](21-publish.md) and
measure the release as a cohort rather than an output count.
