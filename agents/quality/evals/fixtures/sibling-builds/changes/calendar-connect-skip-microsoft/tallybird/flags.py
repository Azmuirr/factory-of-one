"""Feature flags, modeled on LaunchDarkly. A flag is on for a user when it is enabled and the user matches
one of its rules. A flag with no rules applies to everyone."""

from __future__ import annotations

from pathlib import Path

import yaml

FLAGS_FILE = Path(__file__).with_name("flags.yaml")


class Flags:
    def __init__(self, defs: dict):
        self.defs = defs

    @classmethod
    def load(cls, path: Path | str = FLAGS_FILE, overrides: dict[str, bool] | None = None) -> "Flags":
        """Read flags.yaml. `overrides` turns flags on or off while keeping their rules, as a flag console would."""
        defs = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        for name, enabled in (overrides or {}).items():
            defs[name] = {**defs.get(name, {"rules": []}), "enabled": enabled}
        return cls(defs)

    def is_on(self, name: str, user: dict) -> bool:
        flag = self.defs.get(name)
        if not flag or not flag.get("enabled"):
            return False
        rules = flag.get("rules") or []
        return not rules or any(all(user.get(key) in allowed for key, allowed in rule.items()) for rule in rules)
