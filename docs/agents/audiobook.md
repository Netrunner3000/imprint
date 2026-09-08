# NARRATOR — Ebook → MP3 audiobook

`key: audiobook` · converter: `services/narrator/converter.py` · panel: `build_audiobook_panel()` · handler: `start_selected_audiobook_book()`

> Uses **OpenAI TTS** regardless of the provider selected elsewhere — an OpenAI API key is required.

## What it does
Converts `.pdf` / `.epub` / `.txt` / `.mobi` ebooks into MP3 audiobooks: extracts text, chunks it, synthesises speech via OpenAI TTS, and stitches the audio — running as a background process so the GUI stays responsive.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Book list + Refresh | Books found in the configured input folder. |
| Input / Output folders | Source ebooks, MP3 destination (Change to pick). |
| Voice | OpenAI TTS voice (from the audiobook tool config). |
| Chunk Tokens | Text per TTS call (default 1400) — trades API calls vs chunk size. |
| Start / Stop | Begin / kill the conversion. |

## Outputs
MP3(s) in the output folder + a live **Output Log** (chunk progress, resume state, quota/error detection). Progress bar reflects completed chunks.

## How it works
The converter runs as a separate process via `QProcess`:
- **Dev**: `python -u -m services.narrator.converter --input ... --output ... --voice ... --chunk-tokens ...`
- **Frozen app**: the bundle has no `python -m`, so it re-invokes its own executable with the `--narrator-worker` sentinel (intercepted at the top of `main.py`, which runs `converter.main()` and exits). Args are otherwise identical.

`converter.convert()` does extraction (pypdf / ebooklib / BeautifulSoup), tiktoken chunking, and parallel TTS calls.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `services/narrator/converter.py` | `convert()`, `main()`, extraction + TTS + chunking. |
| `main.py: start_selected_audiobook_book()` | Builds the QProcess command (dev vs frozen branch). |
| `main.py: handle_audiobook_stdout()/_finished()/_error()` | Streams log, detects done/blocked/paused/quota. |
| `services/tool_runner.py: run_audiobook()` | In-process convert path (used by ToolRunner). |
| `config/tools.json` (`audiobook.module`) | Points at the converter module. |

## Extend it
- **More voices/models**: extend the voice combo + pass `--model tts-1-hd` through to `convert()`.
- **Per-chapter files**: have `convert()` emit one MP3 per chapter instead of stitching.
- **Other TTS providers**: add an engine switch in `converter.py`.

## Requirements
**OpenAI API key** (TTS billed per character; ~$7–10 for a novel). Input folder configured in `config/tools.json`.

---

## Listening (the Listen tab)

Converting a book used to be the end of it: the MP3 existed and nothing in the
app could find or play it. The **Listen** tab is the other half.

- **Library** — a recursive scan of the configured output folder for audio
  files (`.mp3 .m4a .m4b .wav .aac .flac .ogg`), showing progress, position and
  when each was last played.
- **Player** — play/pause, 30-second skips, a scrubber and playback speed from
  0.75× to 2×, built on `QMediaPlayer`.
- **Resume** — the button reads *Resume at 1:24:03* and picks up exactly there.

### How resume works, and the two traps

Position is keyed by **file path**, not by a library index: the library is a
directory scan, and files get renamed, moved and re-converted, so an index would
quietly point at the wrong book.

It is saved **on a five-second timer as well as on stop**, because people close
laptops and quit apps — a resume that only survives a clean exit is not a
resume.

Two bugs found by actually playing a file, each of which silently defeated the
whole feature:

1. **`stop()` overwrote the position it had just saved.** `QMediaPlayer` resets
   position to 0 on stop, and the resulting state change called the save path
   again. Every listen recorded 0 and nothing ever resumed. The player now
   never persists a zero; starting over is an explicit action instead.
2. **The resume seek was applied too early.** `durationChanged` arrives before
   the media is seekable, so the seek was accepted and then discarded, and
   playback began from the beginning while appearing to work. It now waits for
   `LoadedMedia`.

A book played to ~99% is marked **finished** rather than parked at the last
second, so the next play starts from the beginning rather than resuming and
immediately stopping. **Start Over** clears that flag.

| Location | Role |
|---|---|
| `services/audiobook_library.py` | Scan, resume bookkeeping, time formatting. |
| `ui/audio_player.py` | `AudiobookPlayer` widget. |
| `main.py: _build_audiobook_library_tab()` | The Listen tab. |
| `audiobook_progress` table | Path, position, duration, finished, last played. |
