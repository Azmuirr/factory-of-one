"""Finding and matching numbers in artifacts. Shared by the eval graders and Quality's correctness checks."""

from __future__ import annotations

import re

TEXT_NUMBER = re.compile(r"(?<![A-Za-z_\d.])\$?(\d[\d,]*(?:\.\d+)?)(%|[kK]\b)?")
NOT_NUMBERS = re.compile(
    r"<script.*?</script>|<style.*?</style>|<[^>]+>|\b[a-z]+_[a-z0-9]+\b|\d{4}-\d{2}-\d{2}|\d+(?:\.\d+)?e-?\d+"
    r"|\b(?:Microsoft|Office|Dynamics) 365\b|\bWindows 1[01]\b", re.S)  # product names, not data
NARRATIVE_MAX = 14  # bare small integers such as "7 days" or "3 weeks" are narrative, not data


def field_numbers(payload) -> list[float]:
    out = []

    def walk(v, key=""):
        if key == "confidence" or isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            out.append(float(v))
        elif isinstance(v, dict):
            for k, x in v.items():
                walk(x, k)
        elif isinstance(v, list):
            for x in v:
                walk(x, key)

    walk(payload)
    return out


def texts(payload) -> list[str]:
    out = []

    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(payload)
    return out


def text_numbers(text: str) -> list[tuple[float, float]]:
    """Numbers written in prose, each with the rounding tolerance its precision implies."""
    out = []
    for digits, suffix in TEXT_NUMBER.findall(NOT_NUMBERS.sub(" ", text)):
        decimals = len(digits.split(".")[1]) if "." in digits else 0
        value, tolerance = float(digits.replace(",", "")), 0.5 * 10 ** -decimals
        if suffix.lower() == "k":
            value, tolerance = value * 1000, tolerance * 1000
        if not suffix and decimals == 0 and value <= NARRATIVE_MAX:
            continue
        out.append((value, tolerance + 1e-9))
    return out


def field_grounded(x: float, pool: set[float]) -> bool:
    for y in pool:
        if abs(x - y) <= max(1e-4, abs(y) * 1e-3):
            return True
        if abs(x - y * 100) <= 0.051 or abs(x * 100 - y) <= 0.051:
            return True
    return False


def text_grounded(value: float, tolerance: float, pool: set[float]) -> bool:
    return any(abs(value - abs(c)) <= tolerance for y in pool for c in (y, y * 100))


def ungrounded(payload, pool: set[float]) -> list[float]:
    """Every field and prose number in a payload that does not match the pool."""
    fields = [n for n in field_numbers(payload) if not field_grounded(n, pool)]
    prose = [v for s in texts(payload) for v, tol in text_numbers(s) if not text_grounded(v, tol, pool)]
    return fields + prose


def pool_of(payloads) -> set[float]:
    pool = set()
    for p in payloads:
        pool |= set(field_numbers(p))
        pool |= {v for s in texts(p) for v, _ in text_numbers(s)}
    return pool
