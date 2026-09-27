"""The design system, owned by code: tokens, the stylesheet, the class list, and the checks every design must pass."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = Path(os.environ.get("FACTORY_DESIGN_SYSTEM") or ROOT / "sandbox" / "design")
VIEWPORT = {"width": 1280, "height": 800}
MAX_HEIGHT = 900

CLASS_ATTR = re.compile(r'class\s*=\s*["\']([^"\']*)["\']', re.I)
RULES = [
    (re.compile(r"\sstyle\s*=", re.I), "uses an inline style; use design system classes"),
    (re.compile(r"<style", re.I), "has a <style> tag; the page shell adds the stylesheet"),
    (re.compile(r"<(script|img|iframe|link)[^>]+(src|href)\s*=\s*[\"']?https?:", re.I), "loads an external resource"),
    (re.compile(r"\s(color|bgcolor|fill|stroke)\s*=", re.I), "sets a color outside the tokens"),
]


def tokens() -> dict:
    return json.loads((SYSTEM / "tokens.json").read_text(encoding="utf-8"))


def stylesheet() -> str:
    return (SYSTEM / "tallybird.css").read_text(encoding="utf-8")


def classes() -> set[str]:
    return set(re.findall(r"\.(tb-[a-z0-9-]+)", stylesheet()))


def components() -> str:
    return (SYSTEM / "components.md").read_text(encoding="utf-8")


def page(markup: str, title: str = "Tallybird") -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title>'
            f"<style>{stylesheet()}</style></head><body class=\"tb-canvas\">{markup}</body></html>")


def static_problems(markup: str) -> list[str]:
    problems = [message for rx, message in RULES if rx.search(markup)]
    known = classes()
    unknown = sorted({c for attr in CLASS_ATTR.findall(markup) for c in attr.split() if c not in known})
    if unknown:
        problems.append(f"uses classes that are not in the design system: {', '.join(unknown)}")
    return problems


def render(markup: str, out: Path) -> dict:
    """Save the design and a screenshot, and run the checks."""
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    (out / "markup.html").write_text(markup, encoding="utf-8")
    (out / "index.html").write_text(page(markup), encoding="utf-8")
    problems = static_problems(markup)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        view = browser.new_page(viewport=VIEWPORT)
        view.route("**/*", lambda r: r.continue_() if r.request.url.startswith("file:") else r.abort())
        view.goto((out / "index.html").resolve().as_uri())
        height = view.evaluate("document.documentElement.scrollHeight")
        view.screenshot(path=str(out / "screen.png"), full_page=True)
        browser.close()
    if height > MAX_HEIGHT:
        problems.append(f"is {height}px tall; a design fits one {VIEWPORT['width']}x{VIEWPORT['height']} screen")
    return {"passed": not problems, "problems": problems, "height": height}
