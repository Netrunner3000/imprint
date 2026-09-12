# ONLYFANS — venture intelligence

`key: onlyfans` · dashboard: `ui/creator_trends.py → OnlyFansDashboard` · panel: `build_onlyfans_panel()`

## What it does

Separates business signals from content production. It ranks configured trend
hypotheses, shows source and freshness, compares directional demand with
saturation, and places imported account performance beside monetization ideas.
The selected row can be handed to the shared Creator agent as a structured
campaign brief.

Scores are directional indexes, not creator rankings, observed platform
revenue, or forecasts. When live adapters are not configured, the source note
labels the rows **SAMPLE DATA** and they must not be used as market evidence.

## Controls

| Control | Purpose |
|---|---|
| Niche / category | Filters the loaded signal rows. |
| Geography | Selects the market context requested from configured sources. |
| Time window | Selects 7, 30, or 90 days of context. |
| Refresh signals | Reloads the source set and its freshness metadata. |
| Overview | Opportunity summary, velocity chart, demand/saturation plot, and source status. |
| Trends & Opportunities | Sortable hypotheses with momentum, demand, saturation, monetization, format, pricing idea, risk, source, and freshness. |
| Content Intelligence | Explains the selected format and Creator deliverables. |
| Monetization & Analytics | Shows imported receipts/attribution beside the selected hypothesis. |
| Market & Strategy | Describes competition and positioning context. |
| Create Campaign in Creator | Sends the selected hypothesis and provenance into Creator for human-reviewed drafting. |

## Measurement boundary

`services.creator_trends.onlyfans_business_metrics()` reads recorded Creator
earnings and subscribers. It does not infer profit when costs are unknown.
Source, freshness, confidence, risk, pricing hypothesis, and requested
deliverables remain attached through the Creator handoff so a generated brief
cannot silently become “evidence.”

The valid loop is:

`sourced signal → bounded campaign → reviewed content → manual publish → imported actuals → decision`

## Safeguards

- Account/content production remains in Creator, where managed authorisation,
  persona disclosure, records, voice, calendar, and earnings are stored.
- Nothing is published or messaged from this dashboard.
- Consent, identity, age, rights, disclosure, and current platform rules remain
  human gates.
- Synthetic or sample values are labelled and must not be presented as live
  demand, competitor performance, or income.

## Under the hood

| Location | Role |
|---|---|
| `ui/creator_trends.py` | Dashboard, charts, tables, source labels, Creator handoff. |
| `services/creator_trends.py` | Trend loading/filtering, scoring, campaign context, owned metrics. |
| `main.py: build_onlyfans_panel()` | Top-level workspace integration. |
| `main.py: _onlyfans_create_campaign()` | Switches to Creator and fills the structured brief. |
| Creator earnings tables | Observed receipts, attribution, and subscriber counts. |

## Requirements

No key is required to view sample interface data. Live claims require configured
sources that preserve source name and observation time. Creator platform
requirements are documented in [creator.md](creator.md).
