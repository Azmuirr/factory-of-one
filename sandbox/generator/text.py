from __future__ import annotations

from functools import lru_cache

from .scenario import SANDBOX_DIR


@lru_cache(maxsize=None)
def variants(path: str) -> list[tuple[str, str]]:
    """Each variant is a subject line, then a body, separated by lines of ---."""
    text = (SANDBOX_DIR / path).read_text(encoding="utf-8")
    out = []
    for block in text.split("\n---\n"):
        lines = block.strip().splitlines()
        if lines:
            out.append((lines[0].strip(), "\n".join(lines[1:]).strip()))
    return out


def render(path: str, rng, **slots) -> tuple[str, str]:
    options = variants(path)
    subject, body = options[int(rng.integers(len(options)))]
    return subject.format(**slots), body.format(**slots)


def baseline_template(theme: str) -> str:
    return f"templates/tickets/{theme}.txt"
