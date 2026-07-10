# MAESTRO — Spotify artist setup & release strategy

`key: music` · class: `agents/music_agent.py → MusicAgent` · panel: `build_music_panel()` · handler: `music_analyse()`

## What it does
A music-business consultant that produces a complete, copy-paste-ready release-and-monetisation plan for independent artists. Every section explicitly marks **[AI OUTPUT — COPY-PASTE READY]** vs **[HUMAN ACTION REQUIRED]** so you always know what to paste and what to do manually.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Artist / Project Name | Identity. |
| Genre | Primary sound. |
| Release Type | Single / EP / Album / Mixtape. |
| Distributor | Not signed up yet / DistroKid / TuneCore / CD Baby / etc. |
| Target Audience, Describe Your Music | Optional context. |
| Provider / Model, Generate Plan / Stop / Help / Save / Clear | Run + manage. |

## Outputs
Five tabs mirroring the plan: **Artist Profile** (short+long bio, genre tags, similar artists), **Release Setup** (title options, tracklist, cover-art spec, ISRC/UPC), **Distribution** (DistroKid/TuneCore/CD Baby comparison + pick), **Spotify Strategy** (editorial pitch ≤500 chars, Canvas brief, curator targets), **Income Roadmap** (stream-revenue projections, PRO/SoundExchange steps). Sidebar echoes release type / genre / distributor + a static procedure checklist.

## How it works
`MusicAgent.build_messages()` uses a system prompt with the exact five-section format, real distributor names/prices, and the AI/HUMAN action markers. Streamed then split into tabs.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/music_agent.py` | `MusicAgent` — five-section consultant prompt. |
| `main.py: build_music_panel()` | Form, five tabs, sidebar. |
| `main.py: music_analyse()/music_stop()/music_save()/music_clear()` | Lifecycle. |

## Extend it
- **Live data**: pull Spotify for Artists / Soundcharts stats and inject them so advice is data-backed.
- **Per-section export**: split Save into per-tab files (paste-ready bios, pitch, etc.).
- **New distributor**: add to the combo + a note in the system prompt's comparison.

## Requirements
Provider key (Claude best for long structured plans). External accounts to act on it: Spotify for Artists, a distributor, a PRO (see the Income Roadmap output and README §18).
