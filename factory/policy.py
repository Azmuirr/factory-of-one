"""Decision rights, owned by code: what the factory may do alone while the PM is away (decision D10)."""

from __future__ import annotations

from pathlib import Path

import yaml


def load(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def may_apply(rights: dict, action: dict) -> tuple[bool, str]:
    """Whether an action may be applied without the PM. Under prepare_only, never."""
    mode = rights["away"]["actions"]
    if mode == "prepare_only":
        return False, f"{action.get('name', 'this action')} waits for the PM: decision rights are prepare_only"
    return False, f"unknown decision rights mode {mode!r}: the action waits for the PM"


def may_send(rights: dict, audience: str) -> tuple[bool, str]:
    """Whether Comms may send to an audience without the PM. An audience that isn't listed waits."""
    rule = rights["away"]["send"].get(audience, "wait_for_pm")
    if rule == "when_numbers_match":
        return True, "may send when every number matches the ledger"
    return False, f"messages to {audience} wait for the PM"


def prompt_section(rights: dict) -> str:
    return "## Decision rights while the PM is away\n\nFollow these exactly. They come from the PM.\n\n" + yaml.safe_dump(rights, sort_keys=False).strip()
