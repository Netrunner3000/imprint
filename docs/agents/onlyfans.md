# OF AGENT — OnlyFans venture intelligence

`key: onlyfans` · dashboard: `agents/onlyfans/panel.py → OnlyFansDashboard` · panel: `build_onlyfans_panel()`

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
| Generate SFW Teaser | Sends the selected signal through Creator's existing Higgsfield pipeline to render a real promotional video after account, permission, policy, price, and budget checks. |
| Monetization & Analytics | Shows imported receipts/attribution beside the selected hypothesis. |
| Market & Strategy | Describes competition and positioning context. |
| Create Campaign in Creator | Sends the selected hypothesis and provenance into Creator for human-reviewed drafting. |

## Measurement boundary

`agents.onlyfans.trends.onlyfans_business_metrics()` reads recorded Creator
earnings and subscribers. It does not infer profit when costs are unknown.
Source, freshness, confidence, risk, pricing hypothesis, and requested
deliverables remain attached through the Creator handoff so a generated brief
cannot silently become “evidence.”

The valid loop is:

`sourced signal → bounded campaign → reviewed content → manual publish → imported actuals → decision`

## Safeguards

- Account/content production remains in Creator, where managed authorisation,
  persona disclosure, records, voice, calendar, and earnings are stored.
- Nothing is published or messaged from this dashboard. Teasers are generated
  and saved locally for review; they are not posted automatically.
- Higgsfield teasers are safe-for-work promotional assets only. Explicit
  prompts and unauthorised likenesses are rejected before submission.
- Consent, identity, age, rights, disclosure, and current platform rules remain
  human gates.
- Synthetic or sample values are labelled and must not be presented as live
  demand, competitor performance, or income.

## Under the hood

| Location | Role |
|---|---|
| `agents/onlyfans/panel.py` | Dashboard, charts, tables, source labels, Creator handoff. |
| `agents/onlyfans/trends.py` | Trend loading/filtering, scoring, campaign context, owned metrics. |
| `main.py: build_onlyfans_panel()` | Top-level workspace integration. |
| `main.py: _onlyfans_create_campaign()` | Switches to Creator and fills the structured brief. |
| Creator earnings tables | Observed receipts, attribution, and subscriber counts. |

## Requirements

No key is required to view sample interface data. Live claims require configured
sources that preserve source name and observation time. Creator platform
requirements are documented in [creator.md](creator.md).

## Before you use a signal

Read the source and freshness fields first. Select a row only after confirming
whether it is live, imported, model-generated, or sample data. Define one
audience, one offer, one content hypothesis, one observation window, and one
success/stop rule before creating a campaign. A high directional score without
source quality is not permission to spend or publish.

## Verify the output

- Confirm Content Intelligence names the selected hypothesis, recommended
  format, and concrete Creator deliverables.
- Check Monetization & Analytics separates imported receipts from prices,
  projections, and missing costs.
- Check Market & Strategy preserves geography, period, source, and freshness
  rather than turning them into a universal claim.
- After Creator handoff, verify the brief still contains consent, risk, pricing,
  evidence, and review boundaries.

## Storage, cost, and privacy

Signals and dashboard state are local unless a configured adapter explicitly
loads a source. Earnings displayed here come from Creator records; the dashboard
does not log in to or scrape OnlyFans. Campaign creation changes the local
Creator brief only. SFW teaser generation can call Higgsfield and is subject to
its key, policy, quote, and the shared budget gate.

## Common failures

| Symptom | Check |
|---|---|
| Every source says sample | No live adapter or imported dataset is configured. |
| Analytics cannot calculate profit | Costs or attributable receipts are missing; do not fill them with guesses. |
| Creator handoff is unavailable | Select a complete opportunity row and review its risk/source fields. |
| Teaser is blocked | Managed account, SFW policy, identity/rights, provider access, quote, and budget. |
