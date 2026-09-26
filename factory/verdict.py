"""Signal's verdict script: did the action move the metric, and did the prediction hold. Code owns the call."""

from __future__ import annotations

from datetime import date, timedelta

from factory.metrics import World

SIGNIFICANCE = 0.05


def verdict(world: World, bet: dict, before_start: str, action_date: str) -> dict:
    prediction = bet["prediction"]
    effective = date.fromisoformat(action_date) + timedelta(days=1)
    before_end = (effective - timedelta(days=1)).isoformat()
    after_end = (world.data_through - timedelta(seconds=1)).date().isoformat()
    result = world.compare_periods(prediction["metric"], before_start, before_end, effective.isoformat(), after_end,
                                   prediction.get("segment"))
    if result["status"] != "value":
        return {"status": result["status"], "detail": result}
    if result["p_value"] >= SIGNIFICANCE:
        outcome = "no_change"
    else:
        outcome = "improved" if result["absolute"] > 0 else "worse"
    tolerance = prediction.get("tolerance", 0.0)
    hit = abs(result["after"] - prediction["expected"]) <= tolerance
    return {
        "status": "value",
        "entry": {
            "metric": result["metric"],
            "segment": result["segment"],
            "before": result["before"],
            "after": result["after"],
            "outcome": outcome,
            "method": (f"Mature cohorts {result['after_period']['start']} to {result['after_period']['end']} "
                       f"({result['n_after']} workspaces) against {result['before_period']['start']} to "
                       f"{result['before_period']['end']}. Two-proportion test, p = {result['p_value']}."),
            "does_not_prove": "That the effect will last, or that the action was the only change in the period.",
        },
        "prediction_hit": hit,
        "brier": round((bet["confidence"] - (1.0 if hit else 0.0)) ** 2, 4),
    }
