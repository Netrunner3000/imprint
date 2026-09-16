"""What actually earned — the loop back from posted content to the next draft.

Earnings import on its own produces a report. What makes it worth having is
attribution: which price point converted, which hook was used, what a
subscriber is worth. `price_history()` feeds straight back into the PPV
drafter, so the price argument is written against what has actually worked for
this account rather than as a blind number.

Everything here is deliberately arithmetic on the user's own recorded numbers.
It does not predict, and it says how thin the evidence is — three sales at $15
is not a finding, and a tool that presents it as one is worse than no tool.
"""

from __future__ import annotations

from services.database import get_connection

# Below this, a price point is an anecdote. Reported, but labelled.
CONFIDENT_SAMPLE = 5


def record_revenue(content_id: int, revenue_usd: float) -> None:
    """Attach what a posted item earned, and mark it posted."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE creator_content SET revenue_usd = ?, status = 'posted' "
            "WHERE id = ?", (float(revenue_usd), content_id))
        conn.execute(
            "UPDATE creator_variants SET revenue_usd = ? "
            "WHERE content_id = ? AND chosen = 1",
            (float(revenue_usd), content_id))
        conn.commit()


def record_outcome(content_id: int, *, campaign: str, channel: str,
                   permalink: str, reach: int, clicks: int,
                   subscriptions: int, ppv_purchases: int,
                   revenue_usd: float, attributable_cost_usd: float,
                   source: str, window: str) -> None:
    """Record one manually verified published-asset outcome.

    Revenue and all-in cost are both USD; the separately captured model cost is
    EUR and is never silently mixed into this return calculation.
    """
    if min(reach, clicks, subscriptions, ppv_purchases) < 0:
        raise ValueError("Outcome counts cannot be negative.")
    if min(revenue_usd, attributable_cost_usd) < 0:
        raise ValueError("Revenue and cost cannot be negative.")
    if not source.strip() or not window.strip():
        raise ValueError("Name the outcome source and measurement window.")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM creator_content WHERE id = ?", (content_id,)).fetchone()
        if not row:
            raise ValueError("The selected content no longer exists.")
        conn.execute("""
            UPDATE creator_content SET campaign=?, channel=?, permalink=?,
                reach=?, clicks=?, subscriptions=?, ppv_purchases=?,
                revenue_usd=?, attributable_cost_usd=?, metric_source=?,
                metric_window=?, status='posted',
                posted_at=CASE WHEN posted_at='' THEN datetime('now') ELSE posted_at END
            WHERE id=?
        """, (campaign.strip(), channel.strip(), permalink.strip(),
              int(reach), int(clicks), int(subscriptions), int(ppv_purchases),
              float(revenue_usd), float(attributable_cost_usd), source.strip(),
              window.strip(), content_id))
        conn.execute(
            "UPDATE creator_variants SET revenue_usd = ? "
            "WHERE content_id = ? AND chosen = 1",
            (float(revenue_usd), content_id))
        conn.commit()


def asset_outcomes(account_id: int) -> list[dict]:
    """Observed item-level results; no sums across overlapping statements."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT c.id, c.title, c.kind, c.status, c.campaign, c.channel, c.permalink,
                   c.reach, c.clicks, c.subscriptions, c.ppv_purchases,
                   c.revenue_usd, c.attributable_cost_usd, c.generation_cost_eur,
                   c.metric_source, c.metric_window,
                   (SELECT substr(v.body, 1, 80) FROM creator_variants v
                    WHERE v.content_id=c.id AND v.chosen=1 LIMIT 1) AS hook
            FROM creator_content c WHERE c.account_id=? AND c.status='posted'
            ORDER BY c.posted_at DESC, c.id DESC
        """, (account_id,)).fetchall()
    return [dict(row) for row in rows]


def price_points(account_id: int) -> list[dict]:
    """Revenue grouped by PPV price, best average first."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT price_usd,
                   COUNT(*)            AS sends,
                   SUM(revenue_usd)    AS total,
                   AVG(revenue_usd)    AS average
            FROM creator_content
            WHERE account_id = ? AND kind = 'ppv' AND price_usd > 0
                  AND status = 'posted'
            GROUP BY price_usd
            ORDER BY average DESC
        """, (account_id,)).fetchall()
    return [dict(r) for r in rows]


def price_history(account_id: int) -> str:
    """A one-line summary for the PPV prompt, or "" when there is nothing.

    Returns "" rather than a hedged sentence when there is no data — an empty
    string drops out of the prompt, while "no data available" would just be
    noise the model has to ignore.
    """
    points = price_points(account_id)
    if not points:
        return ""
    parts = []
    for point in points[:4]:
        note = "" if point["sends"] >= CONFIDENT_SAMPLE else " (few sends)"
        parts.append(
            f"${point['price_usd']:.2f} averaged ${point['average']:.2f} "
            f"over {point['sends']}{note}")
    return "; ".join(parts)


def account_summary(account_id: int) -> dict:
    """Headline numbers for the Earnings tab."""
    with get_connection() as conn:
        earnings = conn.execute("""
            SELECT COUNT(*) AS statements,
                   COALESCE(SUM(gross_usd), 0) AS gross,
                   COALESCE(SUM(net_usd), 0)   AS net,
                   COALESCE(MAX(subscribers), 0) AS subscribers
            FROM creator_earnings WHERE account_id = ?
        """, (account_id,)).fetchone()
        content = conn.execute("""
            SELECT COUNT(*) AS posted,
                   COALESCE(SUM(revenue_usd), 0) AS attributed
            FROM creator_content
            WHERE account_id = ? AND status = 'posted'
        """, (account_id,)).fetchone()

    summary = dict(earnings)
    summary.update(dict(content))
    subs = summary["subscribers"] or 0
    summary["per_subscriber"] = (summary["net"] / subs) if subs else 0.0
    return summary


def top_content(account_id: int, limit: int = 10) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, kind, title, price_usd, revenue_usd, posted_at, segment
            FROM creator_content
            WHERE account_id = ? AND status = 'posted' AND revenue_usd > 0
            ORDER BY revenue_usd DESC LIMIT ?
        """, (account_id, limit)).fetchall()
    return [dict(r) for r in rows]


def hook_results(account_id: int) -> list[dict]:
    """Which tested hooks were used, and what they earned."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT v.body, v.revenue_usd, c.title, c.kind
            FROM creator_variants v
            JOIN creator_content c ON c.id = v.content_id
            WHERE c.account_id = ? AND v.chosen = 1
            ORDER BY v.revenue_usd DESC
        """, (account_id,)).fetchall()
    return [dict(r) for r in rows]


def agency_overview() -> list[dict]:
    """Every account side by side — the view that makes managing several
    different from managing one."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT a.id, a.handle, a.account_type, a.consent_holder,
                   COALESCE(SUM(e.net_usd), 0)   AS net,
                   COALESCE(MAX(e.subscribers), 0) AS subscribers,
                   (SELECT COUNT(*) FROM creator_content c
                     WHERE c.account_id = a.id AND c.status = 'draft') AS drafts
            FROM creator_accounts a
            LEFT JOIN creator_earnings e ON e.account_id = a.id
            GROUP BY a.id
            ORDER BY net DESC
        """).fetchall()
    return [dict(r) for r in rows]


def commission(net_usd: float, rate_percent: float) -> dict:
    """Split a managed account's net between the creator and the manager."""
    rate = max(0.0, min(float(rate_percent), 100.0)) / 100.0
    manager = round(net_usd * rate, 2)
    return {"net": round(net_usd, 2), "manager": manager,
            "creator": round(net_usd - manager, 2), "rate_percent": rate * 100}
