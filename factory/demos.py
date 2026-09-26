"""Demo checks, owned by code: honesty label, decision link, one screen, offline, and no dead clicks."""

from __future__ import annotations

import re
from pathlib import Path

HONESTY = {"live", "mocked", "hardcoded"}
DECISION_ID = re.compile(r"^(sig|pkt|bet|act|bld|ver|rev|call|rdo)_[a-z0-9]{4,}$")
VIEWPORT = {"width": 1280, "height": 800}
MAX_HEIGHT = 900
CLICKABLE = "button, a[href], [onclick], [role=button], input[type=submit], input[type=button], summary"


def check(html_path: Path) -> dict:
    from playwright.sync_api import sync_playwright

    html_path = Path(html_path).resolve()
    url = html_path.as_uri()
    blocked: list[str] = []
    dead: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)

        def guard(route):
            if route.request.url.startswith("file:"):
                route.continue_()
            else:
                blocked.append(route.request.url)
                route.abort()

        page.route("**/*", guard)
        page.goto(url)
        honesty_el = page.locator("[data-honesty]")
        honesty = honesty_el.first.get_attribute("data-honesty") if honesty_el.count() else None
        decision_el = page.locator("[data-decision]")
        decision = decision_el.first.get_attribute("data-decision") if decision_el.count() else None
        height = page.evaluate("document.documentElement.scrollHeight")
        count = page.locator(CLICKABLE).count()
        for i in range(count):
            page.goto(url)
            target = page.locator(CLICKABLE).nth(i)
            label = (target.inner_text() or target.get_attribute("aria-label") or f"element {i}").strip()[:40]
            before_html, before_url = page.content(), page.url
            try:
                target.click(timeout=2000)
                page.wait_for_timeout(150)
            except Exception:
                dead.append(f"{label} (not clickable)")
                continue
            if page.content() == before_html and page.url == before_url:
                dead.append(label)
        browser.close()
    problems = []
    if honesty not in HONESTY:
        problems.append(f"honesty label must be one of {sorted(HONESTY)}, found {honesty!r}")
    if not decision or not DECISION_ID.match(decision):
        problems.append(f"data-decision must name a ledger entry id, found {decision!r}")
    if height > MAX_HEIGHT:
        problems.append(f"page is {height}px tall; one screen is {MAX_HEIGHT}px")
    if blocked:
        problems.append(f"page requested the network: {blocked[:3]}")
    if dead:
        problems.append(f"dead clicks: {dead}")
    return {
        "status": "value",
        "passed": not problems,
        "problems": problems,
        "honesty_label": honesty,
        "decision": decision,
        "clickables": count,
        "dead_clicks": len(dead),
        "height_px": height,
    }
