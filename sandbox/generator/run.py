from __future__ import annotations

import json
from pathlib import Path

from .baseline import DAY
from .model import Simulator
from .scenario import load_actions, load_scenario
from .store import iso, write_truth, write_world

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR_VERSION = "0.1.0"


def generate(scenario_id: str, seed: int = 1, actions_path: Path | None = None,
             through: str | None = None, out: Path | None = None, now_day: int | None = None) -> Path:
    """Build one world. `through` is "now" (what agents see first) or "end" (after actions). `now_day` overrides
    the scenario's own "now" day (0-indexed from its epoch), for a snapshot of a later day in the same week."""
    scenario = load_scenario(scenario_id)
    actions = load_actions(actions_path)
    through = through or ("end" if actions else "now")
    if through == "now":
        cutoff = (now_day + 1) * DAY if now_day is not None else scenario.now_cutoff
    else:
        cutoff = scenario.end_cutoff
    out = Path(out) if out else REPO_ROOT / "runs" / scenario_id / f"seed-{seed}"

    world = Simulator(scenario, seed, actions).run(n_days=int(cutoff // DAY))
    counts = write_world(out / "world" / "world.db", world, scenario, actions, cutoff)
    write_truth(out / "truth" / "truth.db", world, scenario, seed, cutoff)
    manifest = {
        "scenario": scenario.id,
        "scenario_version": scenario.version,
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "through": through,
        "cutoff": iso(cutoff),
        "actions": len(actions),
        "rows": counts,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out
