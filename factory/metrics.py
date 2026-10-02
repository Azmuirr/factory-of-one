"""Metrics engine. The model chooses a metric and parameters; this code computes every number."""

from __future__ import annotations

import difflib
import hashlib
import json
import math
import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import yaml

CATALOGS = Path(os.environ.get("FACTORY_CATALOGS") or Path(__file__).resolve().parents[1] / "catalogs")

FACTS_SQL = """
CREATE TEMP TABLE real_meetings AS
  SELECT workspace_id, json_extract(props, '$.meeting_id') AS meeting_id, ts FROM events
  WHERE name = 'meeting_recorded'
    AND json_extract(props, '$.participants') >= 2 AND json_extract(props, '$.duration_min') >= 5;
CREATE INDEX temp.real_meetings_key ON real_meetings (workspace_id, meeting_id);
CREATE TEMP TABLE first_share AS
  SELECT s.workspace_id, MIN(s.ts) AS ts FROM events s
  JOIN real_meetings r ON r.workspace_id = s.workspace_id AND r.meeting_id = json_extract(s.props, '$.meeting_id')
  WHERE s.name = 'recap_shared' GROUP BY s.workspace_id;
CREATE TEMP TABLE first_meeting AS SELECT workspace_id, MIN(ts) AS ts FROM real_meetings GROUP BY workspace_id;
CREATE TEMP TABLE first_connect AS
  SELECT workspace_id, MIN(ts) AS ts FROM events WHERE name = 'calendar_connect_completed' GROUP BY workspace_id;
CREATE TEMP TABLE saw_calendar AS
  SELECT DISTINCT workspace_id FROM events
  WHERE name = 'onboarding_step_viewed' AND json_extract(props, '$.step') = 'calendar_connect';
CREATE TEMP TABLE trials AS
  SELECT workspace_id, json_extract(props, '$.outcome') AS outcome FROM events WHERE name = 'trial_ended';
CREATE TEMP TABLE first_paid AS
  SELECT workspace_id, mrr, plan, MIN(ts) AS ts FROM subscriptions WHERE mrr > 0 GROUP BY workspace_id;
"""

FACTS_SELECT = """
SELECT w.workspace_id, w.created_at, w.calendar_provider, w.channel, w.company_size,
  fs.ts, fm.ts, fc.ts, sc.workspace_id IS NOT NULL, t.outcome, p.mrr, p.plan
FROM workspaces w
LEFT JOIN first_share fs ON fs.workspace_id = w.workspace_id
LEFT JOIN first_meeting fm ON fm.workspace_id = w.workspace_id
LEFT JOIN first_connect fc ON fc.workspace_id = w.workspace_id
LEFT JOIN saw_calendar sc ON sc.workspace_id = w.workspace_id
LEFT JOIN trials t ON t.workspace_id = w.workspace_id
LEFT JOIN first_paid p ON p.workspace_id = w.workspace_id
"""


def parse_ts(value: str | None) -> datetime | None:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) if value else None


@dataclass(frozen=True)
class Fact:
    workspace_id: str
    created_at: datetime
    dims: dict
    first_real_share: datetime | None
    first_real_meeting: datetime | None
    first_connect: datetime | None
    saw_calendar_step: bool
    trial_outcome: str | None
    first_mrr: float | None

    def within(self, ts: datetime | None, days: int) -> bool:
        return ts is not None and ts <= self.created_at + timedelta(days=days)


# One evaluator per registered metric: fact -> (numerator, denominator). Denominator None means a sum or count.
EVALUATORS = {
    "activation_rate_7d": lambda f: (int(f.within(f.first_real_share, 7)), 1),
    "first_meeting_rate_7d": lambda f: (int(f.within(f.first_real_meeting, 7)), 1),
    "calendar_connect_rate_1d": lambda f: (int(f.saw_calendar_step and f.within(f.first_connect, 1)), int(f.saw_calendar_step)),
    "trial_to_paid_rate": lambda f: (int(f.trial_outcome == "paid"), int(f.trial_outcome is not None)),
    "new_mrr": lambda f: (f.first_mrr or 0.0, None),
    "new_workspaces": lambda f: (1, None),
}


@lru_cache(maxsize=None)
def catalog() -> tuple[dict, dict]:
    raw = yaml.safe_load((CATALOGS / "metrics.yaml").read_text(encoding="utf-8"))
    metrics = {}
    for family_id, family in raw["families"].items():
        for metric_id, m in family["metrics"].items():
            metrics[metric_id] = {**m, "id": metric_id, "family": family_id}
    dims = yaml.safe_load((CATALOGS / "dimensions.yaml").read_text(encoding="utf-8"))["dimensions"]
    return metrics, dims


def rejection(code: str, message: str, **extra) -> dict:
    return {"status": "rejection", "code": code, "message": message, **extra}


def resolve_metric(text: str) -> tuple[str | None, list[str], dict | None]:
    metrics, _ = catalog()
    key = text.strip().lower()
    if key in metrics:
        return key, [], None
    hits = sorted(mid for mid, m in metrics.items() if key in [a.lower() for a in m.get("aliases", [])])
    if len(hits) == 1:
        return hits[0], [f"Read '{text}' as {hits[0]}."], None
    if len(hits) > 1:
        return None, [], {"status": "clarification", "message": f"'{text}' matches more than one metric.", "candidates": hits}
    names = list(metrics) + [a for m in metrics.values() for a in m.get("aliases", [])]
    close = difflib.get_close_matches(key, names, n=3, cutoff=0.5)
    return None, [], rejection("metric_not_registered", f"'{text}' is not a registered metric. Use the warehouse for an exploratory answer.",
                               suggestions=close)


def resolve_segment(metric: dict, segment: dict | None, group_by: list[str] | None) -> tuple[dict, list[str], list[str], dict | None]:
    _, dims = catalog()
    resolved, assumptions = {}, []
    for dim in list(segment or {}) + list(group_by or []):
        if dim not in dims:
            return {}, [], [], rejection("dimension_not_recognized", f"'{dim}' is not a dimension.", allowed=metric["dimensions"])
        if dim not in metric["dimensions"]:
            detail = dims[dim].get("warning", f"{dim} has grain '{dims[dim]['grain']}', which this metric does not support.")
            return {}, [], [], rejection("dimension_not_allowed", f"{metric['id']} cannot be split by {dim}. {detail}",
                                         allowed=metric["dimensions"])
    for dim, values in (segment or {}).items():
        out = []
        for value in values:
            v = value.strip().lower()
            if v in dims[dim]["values"]:
                out.append(v)
                continue
            match = [canon for canon, aliases in (dims[dim].get("aliases") or {}).items() if v in [a.lower() for a in aliases]]
            if len(match) != 1:
                return {}, [], [], rejection("value_not_recognized", f"'{value}' is not a value of {dim}.", allowed=dims[dim]["values"])
            out.append(match[0])
            assumptions.append(f"Read '{value}' as {dim} = {match[0]}.")
        resolved[dim] = sorted(set(out))
    return resolved, sorted(group_by or []), assumptions, None


class World:
    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
        conn.executescript(FACTS_SQL)
        self.data_through = parse_ts(conn.execute("SELECT value FROM meta WHERE key = 'data_through'").fetchone()[0])
        rows = conn.execute(FACTS_SELECT).fetchall()
        conn.close()
        self.facts = [self._fact(r) for r in rows]

    @staticmethod
    def _fact(r) -> Fact:
        (ws, created, provider, channel, size, share, meeting, connect, saw, outcome, mrr, plan) = r
        return Fact(ws, parse_ts(created), {"calendar_provider": provider, "channel": channel, "company_size": size, "plan": plan},
                    parse_ts(share), parse_ts(meeting), parse_ts(connect), bool(saw), outcome, mrr)

    # Public tools -----------------------------------------------------------

    def get_metric(self, metric: str, start: str, end: str, segment: dict | None = None, group_by: list[str] | None = None) -> dict:
        prepared = self._prepare(metric, start, end, segment, group_by)
        if "status" in prepared:
            return prepared
        m, period, seg, groups, assumptions = (prepared[k] for k in ("metric", "period", "segment", "group_by", "assumptions"))
        included, excluded = self._select(m, period, seg)
        if not included:
            return rejection("period_immature", f"No cohort in {period['start']}..{period['end']} has a full {m['window_days']}-day window "
                             f"before the data ends ({self.data_through:%Y-%m-%d}).", excluded_workspaces=excluded)
        request = {"metric": m["id"], "period": period, "segment": seg, "group_by": groups}
        return {
            "status": "value",
            "confidence": "validated",
            **request,
            **self._aggregate(m, included),
            "rows": self._grouped(m, included, groups),
            "unit": m["unit"],
            "definition": {k: m[k] for k in ("description", "numerator", "denominator", "window_days")},
            "maturity": {"data_through": f"{self.data_through:%Y-%m-%dT%H:%M:%SZ}", "excluded_immature_workspaces": excluded},
            "assumptions": assumptions,
            "related": m["related"],
            "query_id": query_id(request),
            "does_not_prove": "Why the value is what it is. A metric describes behavior. It does not identify a cause.",
        }

    def compare_periods(self, metric: str, before_start: str, before_end: str, after_start: str, after_end: str,
                        segment: dict | None = None, group_by: list[str] | None = None) -> dict:
        before = self.get_metric(metric, before_start, before_end, segment, group_by)
        if before["status"] != "value":
            return before
        after = self.get_metric(metric, after_start, after_end, segment, group_by)
        if after["status"] != "value":
            return after
        rate = after["denominator"] is not None
        rows = []
        before_rows = {json.dumps(r["group"], sort_keys=True): r for r in before["rows"]}
        for r in after["rows"]:
            b = before_rows.get(json.dumps(r["group"], sort_keys=True))
            if b:
                rows.append({"group": r["group"], **change(b, r, rate)})
        request = {"metric": after["metric"], "before_period": before["period"], "after_period": after["period"],
                   "segment": after["segment"], "group_by": after["group_by"]}
        return {
            "status": "value",
            "confidence": "validated",
            **request,
            **change(before, after, rate),
            "rows": rows,
            "unit": after["unit"],
            "maturity": after["maturity"],
            "assumptions": sorted(set(before["assumptions"] + after["assumptions"])),
            "related": after["related"],
            "query_id": query_id(request),
            "does_not_prove": "What caused the change. A significant difference is unlikely to be noise. It is not evidence of a cause.",
        }

    # Internals --------------------------------------------------------------

    def _prepare(self, metric, start, end, segment, group_by) -> dict:
        metric_id, assumptions, problem = resolve_metric(metric)
        if problem:
            return problem
        metrics, _ = catalog()
        m = metrics[metric_id]
        if m["id"] not in EVALUATORS:
            return {"status": "error", "message": f"{m['id']} is registered but has no evaluator."}
        try:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
        except ValueError:
            return rejection("period_invalid", "Periods use YYYY-MM-DD dates.")
        if first > last:
            return rejection("period_invalid", f"Start {start} is after end {end}.")
        latest = (self.data_through - timedelta(seconds=1)).date()
        if last > latest:
            assumptions.append(f"Period end {end} is after the data ends. Used {latest}.")
            last = latest
        seg, groups, seg_assumptions, problem = resolve_segment(m, segment, group_by)
        if problem:
            return problem
        return {"metric": m, "period": {"start": first.isoformat(), "end": last.isoformat()}, "segment": seg,
                "group_by": groups, "assumptions": assumptions + seg_assumptions}

    def _select(self, m, period, segment) -> tuple[list[Fact], int]:
        first, last = date.fromisoformat(period["start"]), date.fromisoformat(period["end"])
        window = timedelta(days=m["window_days"])
        included, excluded = [], 0
        for f in self.facts:
            if not first <= f.created_at.date() <= last:
                continue
            if any(f.dims[d] not in values for d, values in segment.items()):
                continue
            if f.created_at + window > self.data_through:
                excluded += 1
                continue
            included.append(f)
        return included, excluded

    @staticmethod
    def _aggregate(m, facts) -> dict:
        evaluate = EVALUATORS[m["id"]]
        num = den = 0
        rate = True
        for f in facts:
            n, d = evaluate(f)
            num += n
            if d is None:
                rate = False
            else:
                den += d
        if not rate:
            return {"value": round(num, 2), "numerator": round(num, 2), "denominator": None, "n": len(facts)}
        return {"value": round(num / den, 4) if den else None, "numerator": num, "denominator": den, "n": len(facts)}

    def _grouped(self, m, facts, groups) -> list[dict]:
        if not groups:
            return []
        buckets: dict[tuple, list[Fact]] = {}
        for f in facts:
            buckets.setdefault(tuple(f.dims[g] for g in groups), []).append(f)
        return [{"group": dict(zip(groups, key)), **self._aggregate(m, buckets[key])} for key in sorted(buckets, key=str)]


MATERIAL_P = 0.01
MATERIAL_RELATIVE = 0.03


def change(before: dict, after: dict, rate: bool) -> dict:
    if before["value"] is None or after["value"] is None:
        return {"before": before["value"], "after": after["value"], "absolute": None, "relative": None, "material": None,
                "note": "No eligible workspaces in one period, so there is nothing to compare."}
    relative = round((after["value"] - before["value"]) / before["value"], 4) if before["value"] else None
    out = {
        "before": before["value"],
        "after": after["value"],
        "absolute": round(after["value"] - before["value"], 4),
        "relative": relative,
    }
    if rate:
        n1, n2 = before["denominator"], after["denominator"]
        pooled = (before["numerator"] + after["numerator"]) / (n1 + n2)
        se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2)) if 0 < pooled < 1 else 0
        z = (after["value"] - before["value"]) / se if se else 0.0
        p_value = round(math.erfc(abs(z) / math.sqrt(2)), 6)
        out.update({"z": round(z, 2), "p_value": p_value, "n_before": n1, "n_after": n2,
                    "material": p_value < MATERIAL_P and relative is not None and abs(relative) >= MATERIAL_RELATIVE})
    else:
        out["material"] = None  # no significance test for a sum; materiality needs a rate metric
    return out


def query_id(request: dict) -> str:
    return "q_" + hashlib.sha1(json.dumps(request, sort_keys=True).encode()).hexdigest()[:12]


@lru_cache(maxsize=4)
def open_world(db_path: str) -> World:
    return World(Path(db_path))


def list_metrics() -> dict:
    metrics, _ = catalog()
    return {
        "status": "value",
        "metrics": [
            {"id": mid, "description": m["description"], "unit": m["unit"], "window_days": m["window_days"],
             "dimensions": m["dimensions"], "aliases": m.get("aliases", [])}
            for mid, m in metrics.items()
        ],
    }
