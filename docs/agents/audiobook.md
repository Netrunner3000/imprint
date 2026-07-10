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
