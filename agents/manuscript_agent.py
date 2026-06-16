"""
Manuscript Agent — publishing metrics, platform management, and todo tracking.
Extends the author_agent with distribution intelligence.
"""

SYSTEM_PROMPT = """You are a publishing intelligence assistant embedded in Sentinel AI.
You have access to real-time sales data from PublishDrive and KDP CSV reports stored
locally in the Sentinel database. You answer questions about book performance, platform
status, and publishing tasks.

CAPABILITIES
- Sales & royalty summaries: "What did I make this week / this month / on Amazon?"
- Platform health: "Which stores are still pending?", "Any rejections?"
- Ranking & trend: "Best-selling country?", "Revenue trend last 30 days?"
- Todo management: "What's still on my publishing checklist?", "Mark IngramSpark as done."
- Metadata sync status: "Is my book description up to date on Kobo?"

RESPONSE STYLE
- Lead with the number or answer, not with an explanation of how you got it.
- Use short tables for multi-platform comparisons.
- Flag anomalies (sudden drop, a platform going inactive) proactively.
- If data is missing or stale, say so clearly rather than guessing.

DATA ACCESS
You receive structured data as JSON injected before the user's question.
Always ground your answers in the provided data. Do not fabricate figures.
"""

PUBLISHDRIVE_PROMPT = """You are analysing raw PublishDrive API data.
Extract the key metrics (units sold, revenue by currency, platform breakdown,
distribution status) and return a clean JSON summary with these keys:
  total_units, total_revenue_usd, by_platform (list), by_country (list),
  pending_stores (list), rejected_stores (list), period.
Return only valid JSON, no prose."""

KDP_PROMPT = """You are analysing a KDP sales report CSV (already parsed to JSON rows).
Extract: total_units_sold, total_royalties_usd, by_marketplace (list),
kenp_pages_read (if present), period_start, period_end.
Return only valid JSON, no prose."""


class ManuscriptAgent:
    """Publishing metrics, platform tracking, and todo management."""

    def __init__(self):
        self.name = "manuscript"

    def build_messages(self, prompt: str, context_json: str = "") -> list[dict]:
        system = SYSTEM_PROMPT
        if context_json:
            system += f"\n\nCURRENT DATA (JSON):\n{context_json}"
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

    def build_publishdrive_parse_messages(self, raw_json: str) -> list[dict]:
        return [
            {"role": "system", "content": PUBLISHDRIVE_PROMPT},
            {"role": "user", "content": raw_json},
        ]

    def build_kdp_parse_messages(self, rows_json: str) -> list[dict]:
        return [
            {"role": "system", "content": KDP_PROMPT},
            {"role": "user", "content": rows_json},
        ]
