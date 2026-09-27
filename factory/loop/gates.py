"""Human gates. Answers come from the keyboard or from a scripted file. Each gate records what it cost the PM."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

READING_WPM = 200
MINUTES_PER_INPUT = 0.5


@dataclass
class GateRecord:
    gate: str
    words_shown: int
    inputs: int
    wall_seconds: float
    answers: dict = field(default_factory=dict)

    @property
    def pm_minutes(self) -> float:
        return round(self.words_shown / READING_WPM + self.inputs * MINUTES_PER_INPUT, 1)


class Gates:
    def __init__(self, script: dict | None = None):
        self.scripted = script is not None  # a scripted run never waits at the keyboard; unscripted gates take their default
        self.script = script or {}
        self.records: list[GateRecord] = []

    def ask(self, gate: str, briefing: str, questions: list[tuple[str, str, str]]) -> dict:
        """questions: (key, prompt, default). Returns answers keyed by key."""
        print(f"\n{'=' * 72}\n{gate.upper()} GATE\n{'=' * 72}\n{briefing}\n")
        started = time.time()
        scripted = self.script.get(gate, {} if self.scripted else None)
        answers = {}
        for key, prompt, default in questions:
            if scripted is not None:
                answers[key] = str(scripted.get(key, default))
                print(f"{prompt} [{default}]: {answers[key]}  (scripted)")
            else:
                raw = input(f"{prompt} [{default}]: ").strip()
                answers[key] = raw or default
        record = GateRecord(gate, len(briefing.split()), len(questions), round(time.time() - started, 1), answers)
        self.records.append(record)
        return answers
