# VITALITY — Health & wellness guidance

`key: health` · class: `agents/health_agent.py → HealthAgent` · panel: `build_health_panel()` · handler: `health_analyse()`

> ⚠️ General wellness guidance only, not medical advice. Consult a qualified professional for personalised decisions.

## What it does
An evidence-minded advisor across nutrition, fitness, mental wellness, sleep, weight management, and performance. Turns a profile + goal into a structured, prioritised four-part plan with quick wins vs longer-term habits.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Category | General / Nutrition / Fitness / Mental Health / Wellness / Weight Management / Performance. |
| Goal | Weight loss / muscle gain / energy / stress / sleep / etc. |
| Activity Level | Sedentary → Athlete (drives calorie/training targets). |
| Age | Optional. |
| Question / Goal | Free-text detail. |
| Provider / Model, Analyse / Stop / Help / Save / Clear | Run + manage. |

## Outputs
Four tabs: **Overview** (§1 Summary), **Action Plan** (§2), **Nutrition & Lifestyle** (§3 Diet & Lifestyle), **Important Notes** (§4 Cautions). Sidebar: Category, Goal, and a **Confidence** badge parsed from the response.

## How it works
`HealthAgent.build_messages()` uses a system prompt mandating: `1. SUMMARY`, `2. ACTION PLAN`, `3. DIET & LIFESTYLE`, `4. CAUTIONS`, metric units, mechanism-based advice, and a disclaimer. Streams to Overview, then parses to tabs.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/health_agent.py` | `HealthAgent` — 4-section system prompt. |
| `main.py: build_health_panel()` | Form, tabs, confidence badge. |
| `main.py: health_analyse()/_health_on_finished()` | Fire + finalise. |
| `main.py: _parse_health_sections()/_update_health_indicators()/_populate_health_tabs()` | Regex → tabs + badge. |

## Extend it
- **Add metrics**: compute BMI/TDEE in `health_analyse()` from age/weight/height and inject, or show as an indicator.
- **Progress tracking**: persist plans per date and diff them.
- **New indicator**: emit a labelled line in the prompt, parse in `_update_health_indicators()`.

## Requirements
Provider key (any). No external services.
