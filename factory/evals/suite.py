from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "agents"


@dataclass
class Grader:
    type: str  # code, model, human
    name: str
    params: dict = field(default_factory=dict)
    advisory: bool = False
    cross_trial: bool = False


@dataclass
class Task:
    id: str
    kind: str  # capability or regression
    scenario: str
    seed: int
    prompt: str
    graders: list[Grader]
    setup: list[dict] = field(default_factory=list)
    reference: str | None = None
    env: dict = field(default_factory=dict)


@dataclass
class AgentConfig:
    name: str
    version: str
    model: str
    max_turns: int
    skill: str
    capabilities: list[str]
    subagents: dict = field(default_factory=dict)
    references: list[str] = field(default_factory=list)

    def all_capabilities(self) -> list[str]:
        caps = list(self.capabilities)
        for spec in self.subagents.values():
            caps += spec["capabilities"]
        return sorted(set(caps))

    @property
    def dir(self) -> Path:
        return AGENTS / self.name


@dataclass
class Suite:
    agent: str
    version: str
    trials: int
    tasks: list[Task]


def load_agent(name: str) -> AgentConfig:
    raw = yaml.safe_load((AGENTS / name / "agent.yaml").read_text(encoding="utf-8"))
    return AgentConfig(**raw)


def load_suite(agent: str) -> Suite:
    raw = yaml.safe_load((AGENTS / agent / "evals" / "suite.yaml").read_text(encoding="utf-8"))
    defaults = raw.get("defaults", {})
    tasks = []
    for t in raw["tasks"]:
        graders = [Grader(**g) if isinstance(g, dict) else Grader("code", g) for g in t["graders"]]
        tasks.append(Task(
            id=t["id"], kind=t["kind"], scenario=t["scenario"], seed=t.get("seed", defaults.get("seed", 1)),
            prompt=t["prompt"], graders=graders, setup=t.get("setup", []), reference=t.get("reference"), env=t.get("env", {}),
        ))
    return Suite(agent=raw["agent"], version=raw["version"], trials=defaults.get("trials", 3), tasks=tasks)
