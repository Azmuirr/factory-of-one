"""Quality's correctness pass. Code recomputes each artifact from the world. The model cannot override the result."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from factory import demos, ledger, queries, sizing
from factory import numbers as nums
from factory.metrics import World, catalog

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.I)
CHECKS = ("numbers", "quotes", "fields", "privacy")


def recompute_pool(world: World, card: dict, diagnosis: dict | None) -> set[float]:
    """Numbers an honest analyst could cite: every rate metric, overall and by each dimension, plus the sizing."""
    before, after = card["before"]["period"], card["after"]["period"]
    periods = (before["start"], before["end"], after["start"], after["end"])
    segments = [card.get("segment") or None]
    if diagnosis and diagnosis.get("segment"):
        segments.append(diagnosis["segment"])
    results = []
    for metric_id, m in catalog()[0].items():
        if m["unit"] != "rate":
            continue
        for segment in segments:
            results.append(world.compare_periods(metric_id, *periods, segment=segment))
            for dim in m["dimensions"]:
                results.append(world.compare_periods(metric_id, *periods, segment=segment, group_by=[dim]))
    for segment in segments:
        results.append(sizing.weekly_arr_impact(world, *periods, segment=segment))
    return nums.pool_of(r for r in results if r.get("status") == "value")


QUERY_REF = re.compile(r"^q_[0-9a-f]{12}$")


def close(x: float, y: float | None) -> bool:
    return y is not None and nums.field_grounded(x, {y})


def card_exact(world: World, card: dict) -> list[str]:
    """A signal card names its metric, periods, and segment, so code recomputes it exactly."""
    b, a = card["before"]["period"], card["after"]["period"]
    r = world.compare_periods(card["metric"], b["start"], b["end"], a["start"], a["end"], card.get("segment"))
    if r["status"] != "value":
        return [f"the card's comparison cannot be recomputed: {r.get('code')}"]
    problems = []
    pairs = [("before", card["before"]["value"], r["before"]), ("after", card["after"]["value"], r["after"]),
             ("change.absolute", card["change"]["absolute"], r["absolute"]), ("change.relative", card["change"]["relative"], r["relative"])]
    for name, got, want in pairs:
        if not close(got, want):
            problems.append(f"card {name} is {got}; recomputed {want}")
    return problems


def claim_numbers(world: World, claim: dict, log: dict, fallback) -> list[str]:
    """Replay each cited query. Evidence values and the claim's prose numbers must match its own replayed results."""
    problems, replayed = [], set()
    for ev in claim.get("evidence", []):
        ref = ev.get("ref", "")
        if QUERY_REF.match(ref):
            if ref not in log:
                problems.append(f"query {ref} is not in the query log")
                continue
            q = log[ref]
            result_pool = nums.pool_of([queries.run(world, q["tool"], q["args"])])
            replayed |= result_pool
            if "value" in ev and not nums.field_grounded(ev["value"], result_pool):
                problems.append(f"evidence value {ev['value']} does not match query {ref}")
        elif "value" in ev and ev.get("source") == "metrics":
            problems.append(f"metric evidence {ev['value']} does not cite a query_id")
    pool = replayed | {ev["value"] for ev in claim.get("evidence", []) if "value" in ev} if replayed else fallback()
    problems += [f"'{v:g}' in \"{claim['text'][:60]}\" is not in its evidence"
                 for v, tol in nums.text_numbers(claim["text"]) if not nums.text_grounded(v, tol, pool)]
    return problems


def packet_numbers(world: World, packet: dict, card: dict, log: dict) -> list[str]:
    cache: dict = {}

    def fallback() -> set[float]:
        if "pool" not in cache:
            cache["pool"] = recompute_pool(world, card, packet.get("diagnosis"))
        return cache["pool"]

    problems = [p for claim in packet.get("cause", []) + packet.get("ruled_out", []) for p in claim_numbers(world, claim, log, fallback)]
    b, a = card["before"]["period"], card["after"]["period"]
    sizes = [sizing.weekly_arr_impact(world, b["start"], b["end"], a["start"], a["end"], segment=s)
             for s in (None, packet.get("diagnosis", {}).get("segment"))]
    size = packet.get("size", {}).get("value")
    if size is not None and not any(abs(size - s["usd_per_week"]) <= 1 for s in sizes if s.get("status") == "value"):
        problems.append(f"size {size} does not match the sizing tool: {[s.get('usd_per_week') for s in sizes]}")
    rest = [packet.get(k, "") for k in ("question", "cheapest_test", "recommendation")] + packet.get("would_change_if", []) + packet.get("unknowns", [])
    problems += [f"'{v:g}' in \"{t[:60]}\" is not in the data" for t in rest for v, tol in nums.text_numbers(t)
                 if not nums.text_grounded(v, tol, fallback())]
    return problems


def source_text(world_path: Path) -> str:
    conn = sqlite3.connect(f"file:{Path(world_path).as_posix()}?mode=ro", uri=True)
    parts = [f"{s} {b}" for s, b in conn.execute("SELECT subject, body FROM tickets")]
    parts += [f"{t} {n}" for t, n in conn.execute("SELECT title, notes FROM releases")]
    conn.close()
    return " ".join(" ".join(p.split()) for p in parts)


def voice_bound(world_path: Path, segment: dict, start: str, end: str) -> int:
    """Upper bound for a voice count: distinct accounts in the segment with any ticket in the period."""
    sql = "SELECT COUNT(DISTINCT t.workspace_id) FROM tickets t JOIN workspaces w USING (workspace_id) WHERE date(t.created_at) BETWEEN ? AND ?"
    params: list = [start, end]
    for dim, values in (segment or {}).items():
        sql += f" AND w.{dim} IN ({','.join('?' * len(values))})"
        params += values
    conn = sqlite3.connect(f"file:{Path(world_path).as_posix()}?mode=ro", uri=True)
    n = conn.execute(sql, params).fetchone()[0]
    conn.close()
    return n


def correctness(entry: dict, entries: list[dict], world_path: Path, root: Path) -> dict:
    payload, kind = entry["payload"], entry["type"]
    earlier = [e for e in entries if e["id"] != entry["id"]]
    ids = {e["id"] for e in earlier}
    details: dict[str, list] = {c: [] for c in CHECKS}
    result = {c: "pass" for c in CHECKS}
    result["numbers"] = result["quotes"] = "n/a"

    details["fields"] += ledger.errors(entry, ids)
    details["privacy"] += [m for text in nums.texts(payload) for m in EMAIL.findall(text)]

    if kind == "signal_card":
        details["numbers"] += card_exact(World(world_path), payload)
        result["numbers"] = "pass"

    if kind == "decision_packet":
        card = next((e for e in reversed(earlier) if e["type"] == "signal_card" and e["id"] in entry["refs"]), None)
        if card is None:
            details["fields"].append("a decision packet must reference its signal card")
        else:
            details["numbers"] += packet_numbers(World(world_path), payload, card["payload"], queries.load(queries.log_path(root / "ledger.jsonl")))
            voice = payload.get("diagnosis", {}).get("voice_workspaces")
            if voice is not None:
                after = card["payload"]["after"]["period"]
                bound = voice_bound(world_path, payload["diagnosis"].get("segment"), after["start"], after["end"])
                if voice > bound:
                    details["numbers"].append(f"voice_workspaces {voice} exceeds the {bound} accounts with any ticket")
            result["numbers"] = "pass"

    if kind in ("signal_card", "decision_packet"):
        quotes = [ev["quote"] for claim in payload.get("cause", []) + payload.get("ruled_out", [])
                  for ev in claim.get("evidence", []) if ev.get("quote")]
        if quotes:
            corpus = source_text(world_path)
            details["quotes"] += [q for q in quotes if " ".join(q.split()) not in corpus]
            result["quotes"] = "pass"

    if kind == "build":
        path = root / payload["location"]
        if not path.is_file():
            details["fields"].append(f"{payload['location']} does not exist")
        else:
            check = demos.check(path)
            details["fields"] += check["problems"]
            pool = nums.pool_of(e["payload"] for e in earlier if e["type"] != "build")
            shown = nums.text_numbers(path.read_text(encoding="utf-8"))
            details["numbers"] += [v for v, tol in shown if not nums.text_grounded(v, tol, pool)]
            result["numbers"] = "pass"

    for c in CHECKS:
        if details[c]:
            result[c] = "fail"
    return {**result, "details": {c: [str(d) for d in details[c]] for c in CHECKS if details[c]}}


def failed(checks: dict) -> list[str]:
    return [c for c in CHECKS if checks.get(c) == "fail"]


def code_only_review(entry: dict, entries: list[dict], world_path: Path, root: Path) -> dict:
    """A review with no model: SHIP if every check passes, otherwise FIX with the first problem."""
    checks = correctness(entry, entries, world_path, root)
    bad = failed(checks)
    findings = [{
        "claim": f"The {c} check failed.",
        "evidence": "; ".join(checks["details"][c][:3]),
        "impact": "The PM would act on something the data does not support.",
        "smallest_action": f"Correct the {c} in {entry['id']} and resubmit.",
        "proof_required": f"The {c} check passes.",
        "severity": "correctness",
    } for c in bad[:3]]
    return {"verdict": "FIX" if bad else "SHIP", "correctness": {c: checks[c] for c in CHECKS}, "findings": findings}
