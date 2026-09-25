from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .baseline import DAY

SANDBOX_DIR = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = SANDBOX_DIR / "scenarios"


def day_index(at: dict) -> int:
    return (at["week"] - 1) * 7 + (at["day"] - 1)


@dataclass
class Release:
    id: str
    day: int
    title: str
    notes: str
    flag: str | None
    effects: list[dict]

    @property
    def ts(self) -> float:
        return self.day * DAY + 17 * 3600


@dataclass
class Action:
    day: int
    name: str
    params: dict
    decided_by: str

    @property
    def ts(self) -> float:
        return self.day * DAY + 20 * 3600

    @property
    def effective_from(self) -> float:
        return (self.day + 1) * DAY

    def matches(self, segment: dict) -> bool:
        wanted = self.params.get("segment") or {}
        return all(segment.get(key) in values for key, values in wanted.items())


@dataclass
class Scenario:
    id: str
    version: str
    weeks: int
    now_day: int
    releases: list[Release]
    ticket_themes: list[dict]
    messages: list[dict]
    raw: dict = field(repr=False)

    @property
    def now_cutoff(self) -> float:
        return (self.now_day + 1) * DAY

    @property
    def end_cutoff(self) -> float:
        return self.weeks * 7 * DAY


def load_scenario(scenario_id: str) -> Scenario:
    raw = yaml.safe_load((SCENARIOS_DIR / scenario_id / "scenario.yaml").read_text(encoding="utf-8"))
    releases = [
        Release(r["id"], day_index(r["at"]), r["title"], r["notes"], r.get("flag"), r.get("effects") or [])
        for r in raw["releases"]
    ]
    return Scenario(
        id=raw["id"],
        version=raw["version"],
        weeks=raw["clock"]["weeks"],
        now_day=day_index(raw["clock"]["now"]),
        releases=releases,
        ticket_themes=(raw.get("text") or {}).get("tickets") or [],
        messages=raw.get("messages") or [],
        raw=raw,
    )


def load_actions(path: Path | None) -> list[Action]:
    if path is None:
        return []
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    return [Action(day_index(a["at"]), a["name"], a.get("params") or {}, a.get("decided_by", "pm")) for a in raw]
