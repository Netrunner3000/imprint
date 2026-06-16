# PLAYMAKER — NFL Prop Bet Analyser

## What it does
Playmaker is an NFL prop bet analysis agent. It evaluates player props, game totals, and spread bets using statistical modelling, season trend analysis, and edge assessment. It calculates expected value (EV), assigns confidence levels, and generates a projection for the relevant stat line.

> ⚠️ **Disclaimer:** Sports betting analysis is for entertainment and informational purposes. Gambling involves risk. Bet responsibly and within legal limits in your jurisdiction.

---

## How to use

1. **Enter the bet** — e.g. `Patrick Mahomes over 285.5 passing yards vs Ravens`, `Eagles -3.5 vs Cowboys`, `Ravens/Eagles game total over 47.5`.
2. *(Optional)* **Add context** — recent stats, injury reports, weather, line movement, or relevant matchup data.
3. *(Optional)* **Specify season week** — helps the model anchor projections to the correct point in the season.
4. **Select a Provider & Model**.
5. Click **Analyse**.

---

## Output tabs

| Tab | Contents |
|---|---|
| Full Analysis | Comprehensive breakdown covering all relevant factors |
| Over Case | Statistical arguments supporting the over |
| Under Case | Statistical arguments supporting the under |
| Edge Assessment | Implied probability vs estimated true probability; edge % |
| Projection | Model's predicted stat line with confidence range |
| Season Trends | Recent trend context — last 5 games, season averages, splits |

---

## Metrics explained

**Edge %** — the difference between the book's implied probability and Playmaker's estimated true probability. Positive edge = value bet.

**EV (Expected Value)** — the average return per $100 wagered given the estimated edge. Positive EV = mathematically profitable long-term.

**Confidence level** — how reliable the projection is given available data. Low confidence = lean cautiously or pass.

---

## Tips
- Include **injury reports** — a missing offensive lineman or cornerback changes projections significantly.
- Include **weather conditions** for outdoor games (wind, rain, temperature all affect passing and kicking lines).
- Mention **line movement** (e.g. "opened -3.5, now -5") — Playmaker interprets this as sharp money signals.
- For **same-game parlays**, run each leg individually and check for correlation conflicts.
