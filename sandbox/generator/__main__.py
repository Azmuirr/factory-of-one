import argparse
import json
from pathlib import Path

from .run import generate


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m sandbox.generator", description="Generate a Tallybird world.")
    parser.add_argument("--scenario", default="s01-calendar-gate")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--actions", type=Path, help="YAML list of actions to apply")
    parser.add_argument("--through", choices=["now", "end"], help="default: now, or end when actions are given")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    out = generate(args.scenario, args.seed, args.actions, args.through, args.out)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    print(f"World written to {out}")
    for table, n in manifest["rows"].items():
        print(f"  {table:<14}{n:>9,}")


if __name__ == "__main__":
    main()
