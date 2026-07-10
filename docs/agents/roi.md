# QUICK ROI — Short-to-medium term opportunity analysis

`key: roi` · class: `agents/roi_agent.py → ROIAgent` · panel: `build_roi_panel()` · handler: `roi_analyse()`

> ⚠️ Analytical output only, not financial advice.

## What it does
Evaluates a specific trade/opportunity across asset classes (equities, options, crypto, forex, ETFs, commodities) on a days-to-months horizon and returns a structured five-part analysis with quantified risk/reward.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Ticker / Asset | The instrument. |
| Asset Type | Frames the analysis (Stock/Crypto/Options/Forex/ETF/Commodity/Other). |
| Timeframe | Short (<2w) / Medium (2–8w) / Long (2–6m). |
| Risk Tolerance | Conservative / Moderate / Aggressive — drives sizing + the Risk bar. |
| Capital (€) | Optional — for absolute sizing. |
| Context / Notes | Optional — price levels, news, thesis. |
| Provider / Model, Analyse / Stop / Help / Save / Clear | Run + manage. |

## Outputs
Four tabs: **Summary** (§1), **Bull / Bear** (§2+§3), **ROI Details** (§4), **Recommendation** (§5). Sidebar indicators: **Risk Level** bar (0–10, colour-coded), **Expected ROI** range, **Risk : Reward**, **Confidence** badge — all regex-parsed from the response.

## How it works
`ROIAgent.build_messages()` uses a system prompt that mandates: `1. OPPORTUNITY SUMMARY`, `2. BULL CASE`, `3. BEAR CASE`, `4. ROI ANALYSIS`, `5. ACTIONABLE RECOMMENDATION`, always with a stop-loss and disclaimer. Streams the Summary tab live, then parses on finish.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/roi_agent.py` | `ROIAgent` — 5-section system prompt. |
| `main.py: build_roi_panel()` | Form, tabs, indicators. |
| `main.py: roi_analyse()/_roi_on_finished()` | Fire + finalise. |
| `main.py: _parse_roi_sections()/_update_roi_indicators()/_populate_roi_tabs()` | Regex → tabs + indicators. |
| `main.py: roi_save()/roi_clear()` | Export / reset. |

## Extend it
- **New indicator**: have the prompt emit a labelled line, parse it in `_update_roi_indicators()`.
- **Live prices**: fetch a quote in `roi_analyse()` and inject it into the prompt.
- **New asset class**: extend the Asset Type combo + a note in the system prompt.
- Section headers must stay verbatim — `_parse_roi_sections()` matches them.

## Requirements
Provider key (Claude sonnet/opus best for section compliance). No live market data — supply current price in Notes.

## See also
**Oracle** (`investment`) for deeper, longer-horizon macro/technical/fundamental synthesis.
