"""Bet's sizing script: turns an activation gap into weekly new ARR at stake."""

from __future__ import annotations

from factory.metrics import World, query_id


def weekly_arr_impact(world: World, before_start: str, before_end: str, after_start: str, after_end: str,
                      segment: dict | None = None) -> dict:
    activation = world.compare_periods("activation_rate_7d", before_start, before_end, after_start, after_end, segment)
    if activation["status"] != "value":
        return activation
    ended = [f for f in world.facts if f.trial_outcome is not None]
    activated = [f for f in ended if f.within(f.first_real_share, 7)]
    not_activated = [f for f in ended if not f.within(f.first_real_share, 7)]
    conv_activated = sum(f.trial_outcome == "paid" for f in activated) / len(activated)
    conv_not = sum(f.trial_outcome == "paid" for f in not_activated) / len(not_activated)
    mrr = [f.first_mrr for f in ended if f.first_mrr]
    arr_per_paid = 12 * sum(mrr) / len(mrr)

    in_segment = [f for f in world.facts if all(f.dims[d] in v for d, v in activation["segment"].items())]
    days = (world.data_through - min(f.created_at for f in world.facts)).days
    trials_per_week = len(in_segment) / days * 7

    impact = (activation["before"] - activation["after"]) * (conv_activated - conv_not) * trials_per_week * arr_per_paid
    request = {"tool": "estimate_weekly_arr_impact", "before_start": before_start, "before_end": before_end,
               "after_start": after_start, "after_end": after_end, "segment": activation["segment"]}
    return {
        "status": "value",
        "confidence": "validated",
        "query_id": query_id(request),
        "usd_per_week": round(impact),
        "inputs": {
            "activation_before": activation["before"],
            "activation_after": activation["after"],
            "conversion_if_activated": round(conv_activated, 4),
            "conversion_if_not": round(conv_not, 4),
            "trials_per_week": round(trials_per_week),
            "arr_per_paid_workspace": round(arr_per_paid),
        },
        "segment": activation["segment"],
        "method": "activation gap x conversion gap (activated vs not) x trials per week in the segment x ARR per paid workspace",
        "does_not_prove": "That the whole gap is recoverable, or that it will persist.",
    }
