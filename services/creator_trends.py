"""Normalized market signals for the OnlyFans venture workspace.

The UI consumes this module's normalized records and never depends on a
specific network source.  Adapters may return no data (missing credentials,
rate limits, policy changes); the aggregate still returns the other sources
and, when none are available, an explicitly-labelled demonstration feed.

Scores are directional indexes from 0–100.  They are not revenue forecasts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Iterable, Protocol


@dataclass(frozen=True)
class Trend:
    name: str
    category: str
    geography: str
    momentum: float
    search_interest: float
    saturation: float
    monetization: float
    format: str
    pricing_idea: str
    source: str
    observed_at: str
    risk: str = "Low"
    history: tuple[float, ...] = ()
    confidence: str = "indicative"

    @property
    def opportunity(self) -> int:
        """Compact, explainable potential score; never a revenue estimate."""
        score = (
            .30 * self.search_interest
            + .25 * self.momentum
            + .25 * self.monetization
            + .20 * (100 - self.saturation)
        )
        if self.risk.lower() == "high":
            score -= 18
        elif self.risk.lower() == "review":
            score -= 7
        return max(0, min(100, round(score)))


class TrendAdapter(Protocol):
    name: str

    def fetch(self, geography: str, window: str) -> list[Trend]: ...


class GoogleTrendsAdapter:
    """Optional adapter seam for a licensed/approved Trends connector.

    Google does not publish a general Google Trends API. Set
    ``IMPRINT_TRENDS_CONNECTOR_URL`` to an operator-controlled endpoint that
    returns normalized JSON before enabling this adapter in production.
    """

    name = "Search demand connector"

    def fetch(self, geography: str, window: str) -> list[Trend]:
        # Kept deliberately inert until an operator supplies a connector.
        # This avoids silently scraping Google or blocking application startup.
        if not os.getenv("IMPRINT_TRENDS_CONNECTOR_URL"):
            return []
        return []


class DiscussionSignalsAdapter:
    """Optional Reddit/X discussion adapter requiring approved credentials."""

    name = "Discussion signals"

    def fetch(self, geography: str, window: str) -> list[Trend]:
        if not (os.getenv("REDDIT_CLIENT_ID") or os.getenv("X_BEARER_TOKEN")):
            return []
        return []


class AdultIndustryAdapter:
    """Adapter seam for a licensed adult-industry analytics feed."""

    name = "Adult-industry analytics"

    def fetch(self, geography: str, window: str) -> list[Trend]:
        if not os.getenv("ADULT_TRENDS_FEED_URL"):
            return []
        return []


def _demo(geography: str) -> list[Trend]:
    """Plausible fixtures for product demonstration, not live observations."""
    stamp = datetime.now(timezone.utc).isoformat(timespec="minutes")
    rows = [
        ("POV mini-series", "Story-led", 82, 76, 54, 84, "3-part vertical video", "$12–18 bundle; offer the finale as an upsell", "Low", (42, 48, 55, 61, 69, 76, 82)),
        ("Cosplay transformation", "Cosplay", 76, 80, 72, 78, "Reveal carousel + short clip", "Bundle the set; price customs separately", "Review", (58, 61, 59, 66, 70, 73, 76)),
        ("Voice-note GFE", "GFE", 71, 68, 46, 90, "Short voice-note sequence", "Subscription add-on or capped weekly bundle", "Review", (49, 53, 57, 62, 64, 68, 71)),
        ("Behind-the-scenes day", "Lifestyle", 64, 72, 38, 70, "Photo diary + candid clips", "Include a teaser; upsell the extended diary", "Low", (51, 54, 58, 57, 61, 63, 64)),
        ("Interactive outfit poll", "Interactive", 59, 63, 44, 74, "Poll followed by chosen set", "Free poll; paid reveal or subscriber bundle", "Low", (38, 43, 47, 52, 55, 57, 59)),
        ("Custom name request", "Personalized", 53, 57, 35, 88, "Short custom video", "Use a base price plus length/complexity tiers", "Review", (45, 48, 52, 55, 54, 53, 53)),
        ("AI persona lore drop", "Synthetic persona", 48, 61, 58, 65, "Character post + image set", "Bundle chapters; disclose synthetic media clearly", "High", (31, 34, 39, 43, 46, 47, 48)),
    ]
    return [Trend(name, cat, geography, mom, demand, sat, money, fmt, price,
                  "Demonstration dataset", stamp, risk, history, "sample")
            for name, cat, mom, demand, sat, money, fmt, price, risk, history in rows]


def load_trends(geography: str = "Global", window: str = "30 days",
                adapters: Iterable[TrendAdapter] | None = None) -> tuple[list[Trend], bool]:
    """Return normalized trends and whether the bundled sample fallback is used."""
    adapters = tuple(adapters or (
        GoogleTrendsAdapter(), DiscussionSignalsAdapter(), AdultIndustryAdapter()))
    found: list[Trend] = []
    for adapter in adapters:
        try:
            found.extend(adapter.fetch(geography, window))
        except Exception:
            # One source must never take down the decision surface.
            continue
    if not found:
        return _demo(geography), True
    return found, False


def filter_trends(trends: Iterable[Trend], category: str = "All") -> list[Trend]:
    rows = list(trends)
    if category and category != "All":
        rows = [row for row in rows if row.category == category]
    return sorted(rows, key=lambda row: row.opportunity, reverse=True)


def campaign_context(trend: Trend, geography: str, window: str) -> dict:
    """Return the portable brief passed from the venture to Creator.

    Keeping this as plain structured data makes the handoff testable and lets a
    future venture reuse Creator without teaching Creator about this dashboard.
    """
    return {
        "venture": "OnlyFans",
        "platform": "OnlyFans",
        "signal": trend.name,
        "category": trend.category,
        "geography": geography,
        "window": window,
        "opportunity_index": trend.opportunity,
        "momentum_index": round(trend.momentum),
        "demand_index": round(trend.search_interest),
        "saturation_index": round(trend.saturation),
        "monetization_index": round(trend.monetization),
        "suggested_format": trend.format,
        "pricing_experiment": trend.pricing_idea,
        "risk": trend.risk,
        "source": trend.source,
        "observed_at": trend.observed_at,
        "confidence": trend.confidence,
        "deliverables": (
            "three differentiated content concepts",
            "caption and opening-hook variants",
            "a seven-day posting plan",
            "safe-for-work promotional asset briefs",
        ),
    }


def format_creator_brief(context: dict) -> str:
    """Human-readable version of a structured venture handoff."""
    deliverables = "\n".join(f"- {item}" for item in context["deliverables"])
    return (
        f"VENTURE HANDOFF: {context['venture']}\n"
        f"Selected signal: {context['signal']} ({context['category']})\n"
        f"Market context: {context['geography']}, {context['window']}\n"
        f"Directional indexes: opportunity {context['opportunity_index']}/100; "
        f"momentum {context['momentum_index']}/100; demand "
        f"{context['demand_index']}/100; saturation "
        f"{context['saturation_index']}/100; monetization "
        f"{context['monetization_index']}/100.\n"
        f"Suggested format: {context['suggested_format']}\n"
        f"Pricing experiment (not a forecast): {context['pricing_experiment']}\n"
        f"Compliance flag: {context['risk']}\n"
        f"Evidence: {context['source']} · {context['observed_at']} · "
        f"{context['confidence']} confidence\n\n"
        "Create:\n"
        f"{deliverables}\n\n"
        "Keep every claim honest, label synthetic media where required, and "
        "leave publishing as a reviewed manual step."
    )


def onlyfans_business_metrics() -> dict:
    """Aggregate user-owned OnlyFans records without pretending they are profit.

    Imported statements provide net receipts, not operating costs.  We expose
    the useful actuals and explicitly withhold a profit number until costs and
    matching periods exist.
    """
    from services.database import get_connection

    with get_connection() as conn:
        accounts = conn.execute("""
            SELECT COUNT(*) AS accounts
            FROM creator_accounts
            WHERE LOWER(platform) = 'onlyfans'
        """).fetchone()
        earnings = conn.execute("""
            SELECT COUNT(e.id) AS statements,
                   COALESCE(SUM(e.net_usd), 0) AS net_receipts,
                   COALESCE(MAX(e.ingested_at), '') AS latest_import
            FROM creator_earnings e
            JOIN creator_accounts a ON a.id = e.account_id
            WHERE LOWER(a.platform) = 'onlyfans'
        """).fetchone()
        subscribers = conn.execute("""
            SELECT COALESCE(SUM(latest_subscribers), 0) AS subscribers
            FROM (
                SELECT a.id, COALESCE(MAX(e.subscribers), 0) AS latest_subscribers
                FROM creator_accounts a
                LEFT JOIN creator_earnings e ON e.account_id = a.id
                WHERE LOWER(a.platform) = 'onlyfans'
                GROUP BY a.id
            )
        """).fetchone()
        content = conn.execute("""
            SELECT COUNT(*) AS posted,
                   COALESCE(SUM(c.revenue_usd), 0) AS attributed_revenue
            FROM creator_content c
            JOIN creator_accounts a ON a.id = c.account_id
            WHERE LOWER(a.platform) = 'onlyfans' AND c.status = 'posted'
        """).fetchone()

    values = dict(accounts)
    values.update(dict(earnings))
    values.update(dict(subscribers))
    values.update(dict(content))
    values["per_subscriber"] = (
        values["net_receipts"] / values["subscribers"]
        if values["subscribers"] else 0.0
    )
    values["profit_status"] = "Unavailable — operating costs are not recorded"
    return values
