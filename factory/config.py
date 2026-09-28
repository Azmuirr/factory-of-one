"""Install config: which MCP servers exist, and which real tool serves each capability."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SANDBOX = ROOT / "config" / "sandbox.yaml"
ENV_VAR = re.compile(r"\$\{([A-Z0-9_]+)\}")


@dataclass
class Config:
    path: Path
    mode: str
    company: Path
    catalogs: Path
    servers: dict
    server_env: dict
    capabilities: dict
    goals: Path | None = None
    lessons: Path | None = None
    decision_rights: Path | None = None


@lru_cache(maxsize=None)
def vocabulary() -> dict:
    return yaml.safe_load((ROOT / "config" / "capabilities.yaml").read_text(encoding="utf-8"))["capabilities"]


def config_path() -> Path:
    if os.environ.get("FACTORY_CONFIG"):
        return Path(os.environ["FACTORY_CONFIG"])
    local = ROOT / "factory.yaml"
    return local if local.exists() else SANDBOX


def load(path: Path | None = None) -> Config:
    path = Path(path or config_path())
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    unknown = sorted(set(raw["capabilities"]) - set(vocabulary()))
    if unknown:
        raise ValueError(f"{path.name} maps capabilities that are not in the vocabulary: {unknown}")
    return Config(path, raw["mode"], ROOT / raw["company"], ROOT / raw["catalogs"], raw["servers"],
                  raw.get("server_env", {}), raw["capabilities"],
                  ROOT / raw["goals"] if raw.get("goals") else None, ROOT / raw["lessons"] if raw.get("lessons") else None,
                  ROOT / raw["decision_rights"] if raw.get("decision_rights") else None)


def resolve(config: Config, capabilities: list[str]) -> dict[str, str]:
    missing = sorted(c for c in set(capabilities) if c not in config.capabilities)
    if missing:
        raise ValueError(f"{config.path.name} does not map these capabilities: {missing}")
    return {c: config.capabilities[c] for c in capabilities}


def server_of(tool: str) -> str:
    return tool.split("__")[1]


def fill(value: str, slots: dict) -> str:
    for key, v in slots.items():
        value = value.replace("{" + key + "}", str(v))
    return ENV_VAR.sub(lambda m: os.environ.get(m.group(1), ""), value)


def mcp_servers(config: Config, tools: list[str], slots: dict) -> dict:
    slots = {"python": sys.executable, "catalogs": config.catalogs, "goals": config.goals or "", **slots}
    env = {k: fill(str(v), slots) for k, v in config.server_env.items()}
    out = {}
    for name in sorted({server_of(t) for t in tools}):
        spec = config.servers[name]
        if "url" in spec:
            out[name] = {"type": spec.get("type", "http"), "url": fill(spec["url"], slots)}
            continue
        out[name] = {
            "type": "stdio",
            "command": fill(spec["command"], slots),
            "args": [fill(str(a), slots) for a in spec.get("args", [])],
            "env": {**env, **{k: fill(str(v), slots) for k, v in (spec.get("env") or {}).items()}},
        }
    return out


def tools_section(mapping: dict[str, str]) -> str:
    rows = [f"| {cap} | `{tool}` | {vocabulary()[cap]['description']} |" for cap, tool in sorted(mapping.items())]
    return "\n".join(["## Your tools in this install", "", "| Capability | Tool | What it does |", "|---|---|---|", *rows])
