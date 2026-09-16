"""Deterministic Income Lab calculations.

These functions calculate descriptions of user-supplied observations or
hypothetical scenarios. They do not forecast income and never fetch or invent
missing values. Callers must preserve evidence type, source, period and currency.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def _finite(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _nonnegative(value: float, name: str) -> float:
    result = _finite(value, name)
    if result < 0:
        raise ValueError(f"{name} cannot be negative")
    return result


def contribution(*, revenue: float, refunds: float = 0, fees: float = 0,
                 ai_media: float = 0, fulfilment: float = 0,
                 acquisition: float = 0, contractors: float = 0,
                 owner_hours: float = 0, hourly_value: float = 0,
                 accepted_outputs: float = 1) -> dict[str, float | None]:
    values = {name: _nonnegative(value, name) for name, value in locals().items()}
    cash = (values["revenue"] - values["refunds"] - values["fees"]
            - values["ai_media"] - values["fulfilment"]
            - values["acquisition"] - values["contractors"])
    owner_cost = values["owner_hours"] * values["hourly_value"]
    economic = cash - owner_cost
    all_direct_and_time = (values["refunds"] + values["fees"]
                           + values["ai_media"] + values["fulfilment"]
                           + values["acquisition"] + values["contractors"]
                           + owner_cost)
    return {
        "cash_contribution": cash,
        "economic_contribution": economic,
        "owner_time_cost": owner_cost,
        "cash_margin": cash / values["revenue"] if values["revenue"] else None,
        "cash_contribution_per_hour": (
            cash / values["owner_hours"] if values["owner_hours"] else None),
        "effective_cost_per_accepted_output": (
            all_direct_and_time / values["accepted_outputs"]
            if values["accepted_outputs"] else None),
    }


def break_even(*, price: float, fee_rate: float = 0,
               variable_cost: float = 0, acquisition_cost: float = 0,
               fixed_cost: float = 0) -> dict[str, float | int | None]:
    price = _nonnegative(price, "price")
    fee_rate = _nonnegative(fee_rate, "fee_rate")
    if fee_rate > 1:
        raise ValueError("fee_rate must be a decimal between 0 and 1")
    variable_cost = _nonnegative(variable_cost, "variable_cost")
    acquisition_cost = _nonnegative(acquisition_cost, "acquisition_cost")
    fixed_cost = _nonnegative(fixed_cost, "fixed_cost")
    before_acquisition = price * (1 - fee_rate) - variable_cost
    unit_contribution = before_acquisition - acquisition_cost
    units = (math.ceil(fixed_cost / unit_contribution)
             if unit_contribution > 0 else None)
    return {
        "unit_contribution": unit_contribution,
        "maximum_acquisition_cost_at_zero_margin": before_acquisition,
        "break_even_units": units,
    }


def wilson_interval(events: int, total: int,
                    z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0 or events < 0 or events > total:
        raise ValueError("events must be between zero and a positive total")
    p = events / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return max(0.0, centre - radius), min(1.0, centre + radius)


def funnel(stage_counts: Sequence[tuple[str, int]]) -> list[dict[str, object]]:
    if len(stage_counts) < 2:
        raise ValueError("at least two funnel stages are required")
    result: list[dict[str, object]] = []
    for (source_name, source), (target_name, target) in zip(
            stage_counts, stage_counts[1:]):
        if source <= 0 or target < 0 or target > source:
            raise ValueError("funnel counts must be nonnegative and non-increasing")
        low, high = wilson_interval(target, source)
        result.append({
            "from": source_name, "to": target_name,
            "events": target, "total": source, "rate": target / source,
            "drop_off": source - target, "interval": (low, high),
        })
    return result


def compare_variants(*, baseline_events: int, baseline_total: int,
                     variant_events: int, variant_total: int,
                     minimum_effect: float = 0) -> dict[str, object]:
    baseline_interval = wilson_interval(baseline_events, baseline_total)
    variant_interval = wilson_interval(variant_events, variant_total)
    baseline_rate = baseline_events / baseline_total
    variant_rate = variant_events / variant_total
    difference = variant_rate - baseline_rate
    return {
        "baseline_rate": baseline_rate, "baseline_interval": baseline_interval,
        "variant_rate": variant_rate, "variant_interval": variant_interval,
        "absolute_difference": difference,
        "relative_difference": (
            difference / baseline_rate if baseline_rate else None),
        "meets_minimum_observed_effect": abs(difference) >= minimum_effect,
        "decision": "repeat" if variant_total and baseline_total else "incomplete",
    }


def recurring_cohort(*, starts: int, retained: Sequence[int],
                     collected_receipts: float = 0,
                     refunds: float = 0, variable_costs: float = 0) -> dict[str, object]:
    if starts <= 0:
        raise ValueError("starts must be positive")
    if any(value < 0 or value > starts for value in retained):
        raise ValueError("retained counts must be between zero and starts")
    receipts = _nonnegative(collected_receipts, "collected_receipts")
    refunds = _nonnegative(refunds, "refunds")
    costs = _nonnegative(variable_costs, "variable_costs")
    return {
        "retention_rates": [value / starts for value in retained],
        "cash_contribution": receipts - refunds - costs,
        "observed_periods": len(retained),
        "projected_ltv": None,
    }


def workflow_cost(*, base_api_cost: float, retry_rate: float = 0,
                  retry_cost: float = 0, correction_minutes: float = 0,
                  hourly_value: float = 0, acceptance_rate: float = 1) -> dict[str, float]:
    base = _nonnegative(base_api_cost, "base_api_cost")
    retry_rate = _nonnegative(retry_rate, "retry_rate")
    retry_cost = _nonnegative(retry_cost, "retry_cost")
    minutes = _nonnegative(correction_minutes, "correction_minutes")
    hourly = _nonnegative(hourly_value, "hourly_value")
    acceptance = _finite(acceptance_rate, "acceptance_rate")
    if not 0 < acceptance <= 1:
        raise ValueError("acceptance_rate must be above zero and at most one")
    expected_attempt_cost = base + retry_rate * retry_cost + minutes / 60 * hourly
    return {
        "expected_cost_per_attempt": expected_attempt_cost,
        "effective_cost_per_accepted_output": expected_attempt_cost / acceptance,
    }


def automation_payback(*, build_hours: float, hourly_value: float,
                       direct_tool_cost: float = 0,
                       maintenance_per_period: float = 0,
                       minutes_saved_per_run: float = 0,
                       runs_per_period: float = 0,
                       exception_rate: float = 0,
                       exception_minutes: float = 0,
                       quality_gate_passed: bool = False,
                       rollback_tested: bool = False) -> dict[str, object]:
    build_cost = (_nonnegative(build_hours, "build_hours")
                  * _nonnegative(hourly_value, "hourly_value")
                  + _nonnegative(direct_tool_cost, "direct_tool_cost"))
    maintenance = _nonnegative(maintenance_per_period, "maintenance_per_period")
    runs = _nonnegative(runs_per_period, "runs_per_period")
    saved_hours = _nonnegative(minutes_saved_per_run, "minutes_saved_per_run") / 60 * runs
    recovery_hours = (_nonnegative(exception_rate, "exception_rate")
                      * _nonnegative(exception_minutes, "exception_minutes") / 60 * runs)
    period_value = (saved_hours - recovery_hours) * hourly_value - maintenance
    gates_passed = bool(quality_gate_passed and rollback_tested)
    payback = build_cost / period_value if gates_passed and period_value > 0 else None
    return {
        "build_cost": build_cost, "net_hours_saved_per_period": saved_hours - recovery_hours,
        "net_value_per_period": period_value, "payback_periods": payback,
        "promotion_allowed": gates_passed,
        "blocked_reason": "" if gates_passed else "quality and rollback gates must pass",
    }
