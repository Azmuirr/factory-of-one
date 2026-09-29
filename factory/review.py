"""Quality's correctness pass. Code recomputes each artifact from the world. The model cannot override the result."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from factory import code, demos, design, ledger, queries, sizing, support
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
    for table, cols in (("docs", "title, body"), ("requests", "account, text"), ("mail", "subject, body"), ("chat", "text, ''")):
        try:
            parts += [" ".join(str(c or "") for c in row) for row in conn.execute(f"SELECT {cols} FROM {table}")]
        except sqlite3.OperationalError:
            pass  # an older world without the workplace tables
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


def voice_problems(world_path: Path, diagnosis: dict, log: dict) -> list[str]:
    """The voice count must be one search's distinct_workspaces, replayed. Adding up separate searches double counts."""
    voice, ref = diagnosis.get("voice_workspaces"), diagnosis.get("voice_ref")
    if voice is None:
        return []
    q = log.get(ref)
    if not q or q["tool"] != "search_tickets":
        return ["voice_workspaces must cite the ticket search it came from as voice_ref"]
    got = support.search(world_path, **q["args"])["distinct_workspaces"]
    return [] if got == voice else [f"voice_workspaces is {voice}; replaying {ref} gives {got}"]


METRIC_MOVE = re.compile(r"\b(?:dip|drop|dropped|decline|declined|fell|falling|reads worse|looks worse|recovered|recovery)\b", re.I)
EXPLAINS = re.compile(r"\b(?:because|due to|mostly|driven by|caused by|comes from|is from|reads worse than|looks worse than|not real|isn't real)\b", re.I)


def unsourced_causes(payload) -> list[str]:
    """Sentences that say why a metric moved without citing a decision packet. Chief has no metrics, so it cannot know."""
    sentences = [s for text in nums.texts(payload) for s in re.split(r"(?<=[.!?])\s+|\n", text)]
    return [s.strip()[:140] for s in sentences if METRIC_MOVE.search(s) and EXPLAINS.search(s) and "pkt_" not in s]


def cited_numbers(world_path: Path, payload: dict, log: dict, earlier: list[dict]) -> set[float]:
    """Every number Bet may use in prose: replayed from its cited queries, or found in the items it cites, or in the ledger."""
    pool = set(nums.pool_of(e["payload"] for e in earlier))
    world = World(world_path)
    refs = {r for item in payload.get("items", []) + payload.get("set_aside", [])
            for r in [item.get("size", {}).get("ref", ""), *item.get("sources", []), *[e.get("ref", "") for e in item.get("evidence", [])]]}
    conn = sqlite3.connect(f"file:{Path(world_path).as_posix()}?mode=ro", uri=True)
    for ref in refs:
        if ref in log:
            got = queries.run(world, log[ref]["tool"], log[ref]["args"])
            pool |= {float(v) for v in nums.field_numbers(got)}
        kind, _, rid = ref.partition(":")
        table = {"req": ("requests", "request_id", "arr_at_stake || ' ' || text"), "doc": ("docs", "doc_id", "body"),
                 "mail": ("mail", "message_id", "body"), "chat": ("chat", "message_id", "text")}.get(kind)
        if table:
            row = conn.execute(f"SELECT {table[2]} FROM {table[0]} WHERE {table[1]} = ?", (rid,)).fetchone()
            if row:
                pool |= {float(t.replace(",", "")) for t, _ in nums.TEXT_NUMBER.findall(str(row[0]))}
    conn.close()
    return pool


def candidate_problems(world_path: Path, payload: dict, log: dict, earlier: list[dict] | None = None) -> list[str]:
    """Every size in a ranked list is replayed from the query or search it cites, and every number in its prose comes from
    something it cites. A sum Bet worked out itself fails."""
    problems = []
    world = None
    pool = cited_numbers(world_path, payload, log, earlier or [])
    for item in payload.get("items", []) + payload.get("set_aside", []):
        texts = [item.get(k, "") for k in ("title", "problem", "why", "needs_from_pm", "cheapest_test", "kill_trigger")]
        texts += [a["text"] for a in item.get("assumptions", [])]
        for text in texts:
            bad = [v for v, tol in nums.text_numbers(text) if not nums.text_grounded(v, tol, pool)]
            if bad:
                problems.append(f"{item.get('title', '')[:40]}: {bad} in the text do not come from anything it cites")
    for item in payload.get("items", []):
        size = item["size"]
        q = log.get(size["ref"])
        if not q:
            problems.append(f"rank {item['rank']}: size {size['value']} does not cite a logged query or search")
            continue
        world = world or World(world_path)
        got = queries.run(world, q["tool"], q["args"])
        want = got.get("arr_at_stake") if q["tool"] == "search_requests" else got.get("usd_per_week", got.get("value"))
        if want is None or not close(float(size["value"]), float(want)):
            problems.append(f"rank {item['rank']}: size {size['value']}; replaying {size['ref']} gives {want}")
        if q["tool"] == "search_requests" and size.get("accounts") is not None and size["accounts"] != got["distinct_accounts"]:
            problems.append(f"rank {item['rank']}: {size['accounts']} accounts; replaying {size['ref']} gives {got['distinct_accounts']}")
    for item in payload.get("items", []):
        for ev in item.get("evidence", []):
            q = log.get(ev.get("ref"))
            if "value" in ev and q:
                world = world or World(world_path)
                got = queries.run(world, q["tool"], q["args"])
                allowed = [got.get(k) for k in ("arr_at_stake", "distinct_accounts", "matches", "usd_per_week", "value") if got.get(k) is not None]
                if not any(close(float(ev["value"]), float(a)) for a in allowed):
                    problems.append(f"rank {item['rank']}: evidence {ev['value']} does not match {ev['ref']}")
    return problems


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
            details["numbers"] += voice_problems(world_path, payload.get("diagnosis", {}), queries.load(queries.log_path(root / "ledger.jsonl")))
            result["numbers"] = "pass"

    if kind in ("signal_card", "decision_packet"):
        quotes = [ev["quote"] for claim in payload.get("cause", []) + payload.get("ruled_out", [])
                  for ev in claim.get("evidence", []) if ev.get("quote")]
        if quotes:
            corpus = source_text(world_path)
            details["quotes"] += [q for q in quotes if " ".join(q.split()) not in corpus]
            result["quotes"] = "pass"

    evidence = {}
    if kind == "candidates":
        details["numbers"] += candidate_problems(world_path, payload, queries.load(queries.log_path(root / "ledger.jsonl")), earlier)
        result["numbers"] = "pass"
        quotes = [ev["quote"] for item in payload.get("items", []) for ev in item.get("evidence", []) if ev.get("quote")]
        if quotes:
            # Bet may quote the ledger, such as a claim in Signal's packet, as well as docs, requests, and messages.
            ledger_text = " ".join(" ".join(s.split()) for e in earlier for s in nums.texts(e["payload"]))
            corpus = source_text(world_path) + " " + ledger_text
            details["quotes"] += [q for q in quotes if " ".join(q.split()) not in corpus]
            result["quotes"] = "pass"

    if kind == "build" and payload.get("kind") == "mvp":
        details["fields"] += mvp_problems(root / payload["location"], payload)
        folder = root / payload["location"]
        if folder.is_dir():  # what the change does, so the reviewer judges the code and not the description
            evidence = {"diff": code.diff(code.APP, folder)[:8000], "new_flags": code.new_flags(code.APP, folder),
                        "flags": {n: code.flags(folder)[n] for n in code.new_flags(code.APP, folder)}, "tests": code.run_tests(folder)}

    if kind == "build" and payload.get("kind") == "design":
        details["fields"] += design_problems(root / payload["location"], payload)

    if kind == "build" and payload.get("kind") not in ("mvp", "design"):
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
    out = {**result, "details": {c: [str(d) for d in details[c]] for c in CHECKS if details[c]}}
    return {**out, "evidence": evidence} if evidence else out


def mvp_problems(folder: Path, payload: dict) -> list[str]:
    """A proposed code change: code reruns its tests and checks its scope. The entry must report what code finds."""
    if not folder.is_dir():
        return [f"{payload['location']} is not a proposed change"]
    tests = code.run_tests(folder)
    problems = [] if tests["passed"] else [f"the tests fail: {tests['summary']}"]
    if payload.get("checks", {}).get("tests_passed") != tests["passed"]:
        problems.append(f"the entry says tests_passed={payload.get('checks', {}).get('tests_passed')}; code found {tests['passed']}")
    if payload.get("honesty_label") != "live":
        problems.append("a code change is real code: its honesty label is live")
    return problems + code.scope(code.APP, folder)


def design_problems(page: Path, payload: dict) -> list[str]:
    markup = page.parent / "markup.html"
    if not markup.is_file():
        return [f"{payload['location']} was not rendered by the design tool"]
    problems = design.static_problems(markup.read_text(encoding="utf-8"))
    if payload.get("honesty_label") != "mocked":
        problems.append("a design is a mock: its honesty label is mocked")
    return problems


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
