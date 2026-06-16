"""
Lightweight season stats parser — no external dependencies.
Parses user-supplied game-log text and computes descriptive statistics
that are passed to the LLM as structured context.

Accepted input formats (auto-detected):
  • Raw numbers:        "287, 312, 198, 341"
  • Newline-separated:  "287\n312\n198"
  • Labeled rows:       "Week 1: 287 | Week 2: 312"  or  "W1 287"
  • CSV with a numeric column: "Week,Yards\n1,287\n2,312"
  • Mixed separators:   tabs, commas, semicolons, pipes
"""

import re
import math
import statistics
from typing import Optional


def parse_game_log(text: str) -> list[float]:
    """Extract an ordered list of numeric values from free-form text.

    Strategy:
    1. Remove common game/week label tokens so their numbers aren't mistaken for stats.
    2. Remove opponent abbreviations (2-3 uppercase letters like "vs BUF").
    3. Split on all common separators *including whitespace* between words.
    4. From each remaining token take the single numeric value, if present.
    """
    # Remove label prefixes: "Week 3:", "W3", "Game 3 -", "Wk 3"
    cleaned = re.sub(r"(?i)(week|wk|game|gm)\s*\d+\s*[:\-|]?\s*", " ", text)
    # Standalone "W<digit>" or "G<digit>" labels
    cleaned = re.sub(r"\b[WwGg]\d+\b", " ", cleaned)
    # Remove "vs" and short team abbreviations (2-3 uppercase letters)
    cleaned = re.sub(r"(?i)\bvs\.?\s*[A-Z]{2,4}\b", " ", cleaned)
    cleaned = re.sub(r"\b[A-Z]{2,4}\b", " ", cleaned)

    # Split on any separator: comma, semicolon, pipe, tab, newline, or whitespace
    tokens = re.split(r"[,;\|\t\n\s]+", cleaned)
    values: list[float] = []
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        # Match a single standalone number (including decimals and negatives)
        m = re.fullmatch(r"-?\d+(?:\.\d+)?", tok)
        if m:
            try:
                v = float(m.group())
                # Sanity filter: plausible NFL stat range, ignore years (e.g. 2024)
                if -500 <= v <= 9999 and not (1900 <= v <= 2100 and v == int(v)):
                    values.append(v)
            except ValueError:
                pass
    return values


def _linear_trend(values: list[float]) -> float:
    """Return average change per game (positive = improving, negative = declining)."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = statistics.mean(values)
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    return numerator / denominator if denominator else 0.0


def _weighted_average(values: list[float], recency_bias: float = 1.5) -> float:
    """Weighted average with exponentially higher weight on recent games."""
    if not values:
        return 0.0
    weights = [recency_bias ** i for i in range(len(values))]
    total_weight = sum(weights)
    return sum(v * w for v, w in zip(values, weights)) / total_weight


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (pct in 0–100)."""
    sorted_v = sorted(values)
    n = len(sorted_v)
    if n == 1:
        return sorted_v[0]
    index = (pct / 100) * (n - 1)
    lo = int(index)
    hi = min(lo + 1, n - 1)
    frac = index - lo
    return sorted_v[lo] + frac * (sorted_v[hi] - sorted_v[lo])


def compute_stats(values: list[float]) -> dict:
    """Compute descriptive + predictive stats from a game log."""
    if not values:
        return {}

    n = len(values)
    season_avg = statistics.mean(values)
    last3 = values[-3:] if n >= 3 else values
    last5 = values[-5:] if n >= 5 else values
    last3_avg = statistics.mean(last3)
    last5_avg = statistics.mean(last5) if n >= 5 else None
    weighted_proj = _weighted_average(values)
    trend_per_game = _linear_trend(values)
    std_dev = statistics.stdev(values) if n >= 2 else 0.0
    season_min = min(values)
    season_max = max(values)
    floor_25 = _percentile(values, 25)
    ceiling_75 = _percentile(values, 75)
    median = statistics.median(values)

    # Classify trend
    if abs(trend_per_game) < 1.5:
        trend_label = "Stable"
    elif trend_per_game > 0:
        trend_label = f"Improving (+{trend_per_game:.1f}/game)"
    else:
        trend_label = f"Declining ({trend_per_game:.1f}/game)"

    # Classify consistency
    cv = (std_dev / season_avg * 100) if season_avg else 0.0
    if cv < 15:
        consistency = "High (low variance)"
    elif cv < 30:
        consistency = "Medium"
    else:
        consistency = "Low (high variance)"

    return {
        "games_parsed": n,
        "season_avg": round(season_avg, 1),
        "last3_avg": round(last3_avg, 1),
        "last5_avg": round(last5_avg, 1) if last5_avg is not None else None,
        "weighted_projection": round(weighted_proj, 1),
        "trend_per_game": round(trend_per_game, 2),
        "trend_label": trend_label,
        "std_dev": round(std_dev, 1),
        "consistency": consistency,
        "season_min": round(season_min, 1),
        "season_max": round(season_max, 1),
        "floor_p25": round(floor_25, 1),
        "ceiling_p75": round(ceiling_75, 1),
        "median": round(median, 1),
        "raw_values": values,
    }


def format_computed_stats(computed: dict, stat_name: str = "Stat") -> str:
    """Format computed stats into a structured string for the LLM prompt."""
    if not computed:
        return "[No parseable data found — check input format.]"

    lines = [
        f"COMPUTED SEASON MODEL — {stat_name.upper()}",
        f"Games parsed: {computed['games_parsed']}",
        f"",
        f"AVERAGES",
        f"  Season avg:         {computed['season_avg']}",
        f"  Last 3 games avg:   {computed['last3_avg']}",
    ]
    if computed.get("last5_avg") is not None:
        lines.append(f"  Last 5 games avg:   {computed['last5_avg']}")
    lines += [
        f"  Weighted projection (recency-biased): {computed['weighted_projection']}",
        f"",
        f"TREND",
        f"  {computed['trend_label']}",
        f"",
        f"DISTRIBUTION",
        f"  Median:     {computed['median']}",
        f"  Std dev:    {computed['std_dev']}",
        f"  Consistency: {computed['consistency']}",
        f"  Floor (P25):   {computed['floor_p25']}",
        f"  Ceiling (P75): {computed['ceiling_p75']}",
        f"  Season min:    {computed['season_min']}",
        f"  Season max:    {computed['season_max']}",
        f"",
        f"RAW GAME LOG ({computed['games_parsed']} games): "
        + ", ".join(str(v) for v in computed["raw_values"]),
    ]
    return "\n".join(lines)
