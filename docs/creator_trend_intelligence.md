# OnlyFans venture intelligence

The top-level **OnlyFans** workspace ranks **content formats and demand
themes**, not accounts or creators. It combines normalized signals into a compact
opportunity index and keeps every source behind an adapter so one unavailable
provider cannot prevent the dashboard from loading.

OnlyFans business decisions and Creator production are separate on purpose.
The venture workspace owns Overview, Trends & Opportunities, Content
Intelligence, Monetization & Analytics, and Market & Strategy. **Create Campaign
in Creator** passes the selected signal, evidence, freshness, risk, suggested
format, pricing hypothesis, and concrete deliverables into the shared Creator
workspace. Creator can use the same workflow for publishing, music, AltMerch,
and future ventures without inheriting OnlyFans-specific assumptions.

## What the numbers mean

Demand, momentum, saturation, monetization potential, and opportunity are
directional 0–100 indexes. They are decision aids, **not revenue estimates or
promises**. The opportunity score weights demand (30%), momentum (25%),
monetization potential (25%), and whitespace/low saturation (20%), then applies
a visible penalty to elevated compliance risk. Pricing text is an experiment
idea, not a claim about what buyers will pay.

Every row names its source and observation timestamp. When no live connector
is configured, the entire dashboard is marked **SAMPLE DATA** and uses bundled
illustrative records. Sample values are never presented as measured demand.

The analytics view is different: it reads only the user's saved OnlyFans
profiles, imported statements, and manually attributed content revenue. It
shows imported net receipts and attribution, not profit. Imprint deliberately
withholds a profit figure because it does not yet record operating costs against
matching statement periods.

## Data-source limitations

- Google does not offer a general public Google Trends API. Imprint therefore
  does not scrape Google. A licensed or operator-managed service can be
  connected through `GoogleTrendsAdapter`.
- Reddit and X access depends on approved API credentials, scopes, rate limits,
  and each service's current terms. Raw posts should be aggregated into counts
  and velocity signals; do not retain personal data that the dashboard does not
  need.
- Adult-industry reports and insights are often editorial, delayed, regionally
  incomplete, or licensed. Their publication timestamp and methodology should
  be retained in every normalized row.
- Search and discussion interest are proxies for demand. They do not establish
  purchase intent or expected conversion.
- OnlyFans has no supported general analytics API for this use case. Account
  performance should continue to come from user-entered results or statement
  imports, never guessed platform data.

## Wiring connectors later

The normalization contract is the `Trend` dataclass in
`services/creator_trends.py`. A connector implements `fetch(geography, window)`
and returns `Trend` records. Add it to the adapter tuple in `load_trends`.
Network work should run off the UI thread, cache the last successful response,
set an honest `observed_at`, and return an empty list on unavailable sources.

Reserved environment variables:

```text
IMPRINT_TRENDS_CONNECTOR_URL=
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
X_BEARER_TOKEN=
ADULT_TRENDS_FEED_URL=
ADULT_TRENDS_API_KEY=
```

Do not place keys in source control. In development, add them to `.env`; a
packaged build reads the private `.env` in Imprint's application-support
folder. A production connector should also record source status and retrieval
errors separately so a stale cache cannot look live.

## Compliance flags

Flags are planning prompts, not legal conclusions. `Review` calls for a human
check of consent, rights, platform rules, or personalization scope. `High`
receives a score penalty and should not proceed without review. Synthetic media
must be disclosed, all depicted people must be consenting adults, and no trend
signal overrides platform terms or applicable law.
