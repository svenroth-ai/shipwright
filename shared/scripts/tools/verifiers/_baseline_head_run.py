"""One context run of every pytest root at ONE commit, as CI runs them (BP unit BL0b, work items 1 and 2).

CI runs the plugin roots from the plugin directory (``cd plugins/X && pytest tests/``) and the shared
roots from the repo root with ``-m "not slow and not cross_plugin"``. This does the same, serially (one
pytest process per root, ADR-044), and measures ``shared`` plus the plugin's ``scripts`` in every root
with ``--cov-context=test``. Each root keeps its own coverage database; ``prefix_of`` gives the
repo-relative directory the root ran in, which ``load_contexts(db, tree, prefix)`` uses to make every
file path and every test id root-prefixed (so two plugins' ``tests/test_x.py`` cannot collide).

Measurement only; nothing here gates anything.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from ._baseline_proc import clean_env, guard_workdir

__all__ = ["prefix_of", "root_command", "run_root", "run_all", "load_head_contexts"]

_WITH = ["--with", "pytest", "--with", "pytest-mock", "--with", "pytest-cov", "--with", "diff-cover==10.3.0"]
_SHARED_ROOTS = ("shared/tests", "shared/scripts/tests", "shared/scripts/tools/tests")


def prefix_of(root: str) -> str:
    """Repo-relative directory a root runs in: ``plugins/X/`` for a plugin root, empty otherwise."""
    return root[: -len("tests")] if root.startswith("plugins/") else ""


def root_command(tree: Path, root: str, db: Path, junit: Path) -> tuple[list[str], Path]:
    """(command, cwd) of one root, mirroring ci.yml (plugin roots from the plugin directory)."""
    cfg = f"--cov-config={(tree / 'pyproject.toml').as_posix()}"
    shared = (tree / "shared").as_posix()
    base = ["uv", "run", *_WITH, "pytest"]
    common = ["-q", "-p", "no:cacheprovider", f"--junitxml={junit}", "--cov-context=test", "--cov-report=", cfg]
    if root.startswith("plugins/"):
        plugin = tree / root[: -len("/tests")]
        scripts = ["--cov=scripts"] if (plugin / "scripts").is_dir() else []
        return [*base, "tests/", *common, *scripts, f"--cov={shared}"], plugin
    marker = ["-m", "not slow and not cross_plugin"] if root in _SHARED_ROOTS else []
    return [*base, root, *marker, *common, "--cov=shared"], tree


def run_root(tree: Path, root: str, out: Path, env: dict, timeout: int) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    slug = root.replace("/", "_")
    db, junit, log = out / f"cov-{slug}", out / f"junit-{slug}.xml", out / f"log-{slug}.txt"
    for stale in (db, junit):
        stale.unlink(missing_ok=True)
    cmd, cwd = root_command(tree, root, db, junit)
    started, timed_out = time.monotonic(), False
    with log.open("w", encoding="utf-8", errors="replace") as fh:
        try:
            proc = subprocess.run(cmd, cwd=cwd, env={**env, "COVERAGE_FILE": str(db)}, stdout=fh, stderr=subprocess.STDOUT, timeout=timeout, check=False)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            rc, timed_out = -9, True
    tail = [ln for ln in log.read_text(encoding="utf-8", errors="replace").strip().splitlines() if ln.strip()][-1:]
    return {"root": root, "cwd": cwd.relative_to(tree).as_posix() or ".", "seconds": round(time.monotonic() - started, 1), "rc": rc,
            "timed_out": timed_out, "summary": (tail[0] if tail else "").strip("= "), "db": db.name, "db_bytes": db.stat().st_size if db.exists() else 0,
            "junit": junit.name if junit.exists() else None, "command": " ".join(cmd[:4] + ["..."] + cmd[-6:])}


def run_all(tree: Path, roots: list[str], out: Path, timeout: int = 3000, venv: str | None = None) -> list[dict]:
    guard_workdir(tree, out)
    env, runs = clean_env(venv), []
    for root in roots:
        runs.append(run_root(tree, root, out, env, timeout))
        print(json.dumps(runs[-1]), flush=True)
        (out / "runs.json").write_text(json.dumps(runs, indent=1), encoding="utf-8")
    return runs


def load_head_contexts(tree: Path, out: Path, runs: list[dict]) -> dict[str, dict[int, set[str]]]:
    """Union of every root's database as ``repo-relative file -> {line -> {root-prefixed test id}}``."""
    from ._baseline_touch_coverage import load_contexts, merge_contexts

    parts = [load_contexts(out / r["db"], tree, prefix_of(r["root"])) for r in runs if r["db_bytes"]]
    return merge_contexts(parts)
