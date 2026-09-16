# MUSIC ARTIST GENERATOR — Songs, albums, artist identity, and release strategy

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
Five tabs mirror the plan: **Artist Profile** (short+long bio, genre tags, similar artists), **Release Setup** (title options, tracklist, cover-art spec, ISRC/UPC), **Distribution** (distributor comparison), **Spotify Strategy** (editorial-pitch and Canvas drafts that require current-rule verification), and **Income Roadmap** (user-supplied hypothetical scenarios, revenue-route experiments, and reconciliation steps). The Income Roadmap must not forecast earnings or use a universal per-stream payout.

## How it works
`MusicAgent.build_messages()` uses a system prompt with the exact five-section format, real distributor names/prices, and the AI/HUMAN action markers. Streamed then split into tabs.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/music_agent.py` | `MusicAgent` — five-section consultant prompt. |
| `main.py: build_music_panel()` | Setup form, model row, five tabs. |
| `main.py: music_analyse()/music_stop()/music_save()/music_clear()` | Lifecycle. |

## Extend it
- **Live data**: pull Spotify for Artists / Soundcharts stats and inject them so advice is data-backed.
- **Per-section export**: split Save into per-tab files (paste-ready bios, pitch, etc.).
- **New distributor**: add to the combo + a note in the system prompt's comparison.

## Requirements
Provider key (Claude best for long structured plans). External accounts to act on it: Spotify for Artists, a distributor, a PRO (see the Income Roadmap output and README §18).

## Before you run

Enter a concrete music description; it is the required creative anchor. Add the
artist name, release type, current distributor, audience, release territory,
and real constraints where known. Choose a model suited to a long structured
response and check the cost estimate before generating. The plan is more useful
when the release date, available assets, and current audience baseline are
included in the description.

## Verify the result

- Confirm every section appears in its matching tab and distinguishes copy-ready
  text from human action.
- Verify distributor pricing, delivery deadlines, Spotify submission windows,
  metadata rules, and territory availability with the current official source.
- Remove invented comparable artists, credentials, audience numbers, and
  performance claims.
- Treat every income scenario as a hypothesis until receipts, attribution, and
  costs are imported or recorded.

## Storage, cost, and evidence

The five tabs are one model response split for reading. **Save** exports that
response as a timestamped text file you choose; it does not submit metadata,
pitch Spotify, register a work, or distribute audio. Provider usage is measured
through the shared request guard. External distributor, PRO, advertising, and
production charges are not inferred by the agent.

## Common failures

| Symptom | Check |
|---|---|
| Generate Plan asks for input | Describe Your Music is empty. |
| A tab is empty | The response missed its numbered section marker; inspect the first tab/full saved response. |
| Advice contains exact prices or deadlines | Treat them as unverified and check the provider's current terms. |
| Income Roadmap predicts earnings | Reject the output and rerun with measured inputs and explicit hypothesis labels. |
