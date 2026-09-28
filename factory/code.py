"""The product codebase, owned by code: read it, propose a change on a copy, run the tests, and check scope.
Nothing here writes to the app itself. A change lives in its own folder until a human merges it."""

from __future__ import annotations

import difflib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = Path(os.environ.get("FACTORY_APP") or ROOT / "sandbox" / "app")
SKIP = {"__pycache__", ".pytest_cache", "CHANGE.md"}  # CHANGE.md is the pull request description, not code
IN_SCOPE = ("tallybird/", "tests/")
MAX_CHANGED_LINES = 150
TEST_DEF = re.compile(r"^def (test_\w+)", re.M)
# Tests are code an agent wrote. They get only what Python needs to start, never the caller's tokens or keys.
SAFE_ENV = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "LANG", "LC_ALL",
            "PYTHONIOENCODING", "VIRTUAL_ENV")


def files(base: Path) -> list[str]:
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*")
                  if p.is_file() and not SKIP & set(p.relative_to(base).parts))


def inside(base: Path, rel: str) -> Path | None:
    path = (base / rel).resolve()
    return path if path.is_relative_to(base.resolve()) and not SKIP & set(Path(rel).parts) else None


def read(base: Path, rel: str) -> str | None:
    path = inside(base, rel)
    return path.read_text(encoding="utf-8") if path and path.is_file() else None


def search(base: Path, pattern: str) -> list[dict]:
    rx = re.compile(pattern, re.I)
    return [{"path": f, "line": n, "text": line.strip()}
            for f in files(base) for n, line in enumerate((base / f).read_text(encoding="utf-8").splitlines(), 1) if rx.search(line)]


def propose(base: Path, changes: Path, name: str, edits: list[dict], new_files: dict[str, str]) -> dict:
    """Copy the app to changes/<name>, apply edits (each `old` must appear exactly once) and new files, then run the tests."""
    out = changes / name
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(base, out, ignore=shutil.ignore_patterns(*SKIP))
    for e in edits:
        path = inside(out, e["path"])
        text = path.read_text(encoding="utf-8") if path and path.is_file() else None
        if text is None:
            return reject(out, f"{e['path']} is not a file in the app")
        if text.count(e["old"]) != 1:
            return reject(out, f"in {e['path']}, `old` must appear exactly once; it appears {text.count(e['old'])} times")
        path.write_text(text.replace(e["old"], e["new"]), encoding="utf-8")
    for rel, content in new_files.items():
        path = inside(out, rel)
        if not path:
            return reject(out, f"{rel} is outside the app")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return {"status": "value", "location": f"changes/{name}", "tests": run_tests(out), "diff": diff(base, out),
            "new_flags": new_flags(base, out), "scope_problems": scope(base, out)}


def reject(out: Path, message: str) -> dict:
    shutil.rmtree(out, ignore_errors=True)
    return {"status": "rejection", "code": "bad_edit", "message": message}


def run_tests(folder: Path, extra_env: dict | None = None) -> dict:
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=folder, capture_output=True,
                          text=True, encoding="utf-8", timeout=180, env={**{k: v for k, v in os.environ.items() if k in SAFE_ENV}, **(extra_env or {})})
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    return {"passed": proc.returncode == 0, "summary": lines[-1] if lines else proc.stderr[-300:], "output": "\n".join(lines[-40:])}


def acceptance(change: Path, tests_dir: Path) -> dict:
    """Run hidden acceptance tests against a change, in a scratch copy so the change folder stays as proposed."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "app"
        shutil.copytree(change, work, ignore=shutil.ignore_patterns(*SKIP))
        for f in tests_dir.glob("test_*.py"):
            shutil.copy(f, work / "tests" / f"test_zz_{f.name}")
        return run_tests(work, {"TALLYBIRD_BASE": str(APP)})


def diff(base: Path, change: Path) -> str:
    out = []
    for rel in sorted(set(files(base)) | set(files(change))):
        a = (base / rel).read_text(encoding="utf-8").splitlines(keepends=True) if (base / rel).is_file() else []
        b = (change / rel).read_text(encoding="utf-8").splitlines(keepends=True) if (change / rel).is_file() else []
        out += difflib.unified_diff(a, b, f"a/{rel}", f"b/{rel}")
    return "".join(out)


def flags(folder: Path) -> dict:
    return yaml.safe_load((folder / "tallybird" / "flags.yaml").read_text(encoding="utf-8")) or {}


def new_flags(base: Path, change: Path) -> list[str]:
    return sorted(set(flags(change)) - set(flags(base)))


def scope(base: Path, change: Path) -> list[str]:
    """What a reviewer would bounce before reading the logic."""
    problems = []
    before, after = set(files(base)), set(files(change))
    touched = [f for f in sorted(before | after) if f not in before or f not in after
               or (base / f).read_bytes() != (change / f).read_bytes()]
    problems += [f"{f} is outside {', '.join(IN_SCOPE)}" for f in touched if not f.startswith(IN_SCOPE)]
    tests_before = {(f, t) for f in before if f.startswith("tests/") for t in TEST_DEF.findall((base / f).read_text(encoding="utf-8"))}
    tests_after = {(f, t) for f in after if f.startswith("tests/") for t in TEST_DEF.findall((change / f).read_text(encoding="utf-8"))}
    problems += [f"removes the test {f}::{t}" for f, t in sorted(tests_before - tests_after)]
    if not tests_after - tests_before:
        problems.append("adds no test")
    problems += [f"the new flag {n} ships on; new flags ship with enabled: false" for n in new_flags(base, change) if flags(change)[n].get("enabled")]
    changed = sum(1 for l in diff(base, change).splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---")))
    if changed > MAX_CHANGED_LINES:
        problems.append(f"changes {changed} lines; keep a change under {MAX_CHANGED_LINES}")
    return problems
