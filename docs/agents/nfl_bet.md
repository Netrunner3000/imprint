# PLAYMAKER — NFL prop bet analysis

`key: nfl_bet` · class: `agents/nfl_bet_agent.py → NflBetAgent` · panel: `build_nfl_bet_panel()` · handlers: `nfl_bet_analyse()` + `nfl_bet_build_model()`

> ⚠️ Analytical output only, not betting advice. Bet responsibly and legally.

## What it does
Two tools in one panel:
1. **Prop analysis** — evaluates a player/team prop from data you supply and returns an edge assessment with EV.
2. **Season Predictive Model** — parses a pasted season game log into real computed stats (mean, recency-weighted projection, floor/ceiling, consistency) and projects the next game against an optional line.

It never fabricates stats — it reasons only over what you provide.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Player / Team, Prop Type, Line, Odds, Game Context | Prop analysis inputs. |
| Stats / Data box | Paste game logs / matchup data / injury reports. |
| **Season model**: Player, Stat Category, Prop Line, Game Log Data, Opponent/Context | Feeds the computed projection. |
| Analyse Prop / Build Projection / Stop | Run each tool. |

## Outputs
Prop tabs: **Full Analysis**, **Over Case**, **Under Case**, **Edge Assessment** (lean, confidence, EV, unit size), **Projection**, **Season Trends**. Season model: interprets computed stats → point estimate + range + line lean. Sidebar: lean / confidence / EV / unit size.

## How it works
- `NflBetAgent.build_messages()` → 5-section prop prompt with an EV formula.
- `NflBetAgent.build_season_model_messages(computed_stats_text, ...)` interprets stats produced by `agents/nfl_stats_parser.py` (`parse_game_log()`, `compute_stats()`, `format_computed_stats()`) — the numbers are computed in Python, not by the LLM.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/nfl_bet_agent.py` | Prop + season-model system prompts. |
| `agents/nfl_stats_parser.py` | Real stat computation (ground truth for the model). |
| `main.py: nfl_bet_analyse()` / `nfl_bet_build_model()` | The two runners. |
| `main.py: nfl_bet_save()/nfl_bet_clear()` | Export / reset. |

## Extend it
- **Live data**: replace pasted logs with an API pull feeding `parse_game_log()`.
- **New stat metrics**: extend `compute_stats()` (e.g. opponent-adjusted) and surface in `format_computed_stats()`.
- **Auto-EV**: compute EV in Python from odds + projection instead of asking the model.

## Requirements
Provider key. A sportsbook account to act on it (legality varies by jurisdiction).
