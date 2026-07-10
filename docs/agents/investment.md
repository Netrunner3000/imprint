# ORACLE — Longer-horizon market analysis

`key: investment` · class: `agents/investment_agent.py → InvestmentAgent` · panel: `build_investment_panel()` · handler: `inv_analyse()`

> ⚠️ Market analysis for research only. Not financial advice.

## What it does
Synthesises macro, technical, and fundamental signals into an evidence-based outlook with explicit price targets and probabilities, over a weeks-to-a-year+ horizon. The longer-horizon counterpart to Quick ROI.

## Inputs (panel controls)
| Control | Purpose |
|---|---|
| Ticker / Asset | Instrument or market (e.g. NVDA, BTC, S&P 500). |
| Market | Equities / Crypto / Forex / Commodities / ETF-Index / Fixed Income / Other. |
| Analysis type | Combined / Technical / Fundamental / Macro. |
| Horizon | 1 week → 1 year+. |
| Context | Optional — thesis, focus, concerns. |
| Provider / Model, Analyse / Stop / Save / Clear | Run + manage. |

## Outputs
Six-section report streamed into the panel: `1. MARKET OVERVIEW`, `2. TECHNICAL PICTURE`, `3. MACRO & SECTOR CONTEXT`, `4. FUNDAMENTALS` (equities/ETFs only), `5. PRICE TARGETS & PREDICTION` (base/bull/bear with probabilities + UP/DOWN/SIDEWAYS), `6. KEY RISKS`. Sidebar shows the predicted **direction**.

## How it works
`InvestmentAgent.build_messages()` uses a system prompt that enforces the six sections, probabilistic language, explicit assumptions, and a mandatory disclaimer block. Runs through `ChatWorker`.

## Under the hood — files & functions
| Location | Role |
|---|---|
| `agents/investment_agent.py` | `InvestmentAgent` — 6-section system prompt. |
| `main.py: build_investment_panel()` | Form, output, direction indicator. |
| `main.py: inv_analyse()/inv_stop()/inv_save()/inv_clear()` | Lifecycle. |

## Extend it
- **Fundamentals feed**: pull earnings/ratios in `inv_analyse()` and inject them so §4 is data-backed.
- **Charting**: parse the support/resistance levels from §2 and draw them.
- **Direction history**: log each prediction to compare against outcomes later.
- Tune the six-section spec in `agents/investment_agent.py`.

## Requirements
Capable model recommended (`claude-sonnet`/`gpt-4o`). Supply current price/fundamentals in Context — no live feed.
