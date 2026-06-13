#!/usr/bin/env python3
"""Behavior-snapshot gate for the OS1 / P3.2 Code-Simplify path.

A simplify iterate must preserve behavior. This module makes that mechanical
instead of an honor-system: ``snapshot`` records the green state of the test
suite BEFORE the edit; ``verify`` re-runs it AFTER and STOPs (non-zero exit) on
any behavior drift or removed coverage.

The gate compares **collected test node-id sets + counts + exit code** (robust
and dependency-free) rather than parsing per-test output. The reject conditions
mirror the OS1 acceptance: "reject if any test status flips OR if a line-count
drop is accompanied by removed test coverage".

Split for testability: the verdict logic (``build_snapshot`` /
``compute_verdict``) is pure and unit-tested with synthetic inputs; the
subprocess/git runners are thin and exercised by the CLI integration test.

> Adapted from addyosmani/agent-skills `skills/code-simplification/SKILL.md`
> (MIT, © Addy Osmani) — the "preserve behavior, fewer lines is not the goal"
> principle, expressed here as an executable snapshot/verify gate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_VERSION = 1
SNAPSHOT_FILENAME = "behavior_snapshot.json"

_EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".shipwright", "node_modules",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", ".worktrees",
}
_PASSED_RE = re.compile(r"(\d+) passed")
_FAILED_RE = re.compile(r"(\d+) (?:failed|error)")


@dataclass
class SuiteResult:
    """The observable state of one test-suite run."""

    node_ids: list[str]
    passed: int
    failed: int
    total: int
    exit_code: int
    loc: int


@dataclass
class Verdict:
    ok: bool
    reasons: list[str] = field(default_factory=list)


# --- pure: snapshot record + gate -------------------------------------------


def build_snapshot(run_id: str, result: SuiteResult, test_cmd: list[str]) -> dict:
    """Assemble the serializable green-state record (pure)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "test_cmd": list(test_cmd),
        "green": result.exit_code == 0 and result.failed == 0,
        "exit_code": result.exit_code,
        "passed": result.passed,
        "failed": result.failed,
        "total": result.total,
        "loc": result.loc,
        "node_ids": sorted(result.node_ids),
        # False when the runner yielded no pytest node-ids: the coverage/count
        # reject conditions are then inert and only green->red is checked.
        "node_ids_collected": bool(result.node_ids),
    }


def compute_verdict(snapshot: dict, current: SuiteResult) -> Verdict:
    """Decide whether ``current`` preserves the snapshot's behavior (pure).

    Reject when (a) the suite flipped green->red, (b) a previously-collected
    test disappeared (removed coverage), (c) the collected test count dropped,
    or (d) source LOC dropped *together with* reduced coverage. A LOC drop with
    intact, green coverage is the desirable simplify outcome and is allowed.
    """
    reasons: list[str] = []

    if current.exit_code != 0 or current.failed > 0:
        reasons.append(
            f"test status flipped: baseline was green, now exit={current.exit_code}, "
            f"failed={current.failed}"
        )

    snap_ids = set(snapshot.get("node_ids", []))
    missing = snap_ids - set(current.node_ids)
    if missing:
        sample = ", ".join(sorted(missing)[:5])
        reasons.append(
            f"removed test coverage: {len(missing)} previously-collected test(s) gone ({sample})"
        )

    snap_total = int(snapshot.get("total", 0))
    if snap_ids and current.total < snap_total:
        reasons.append(f"test count dropped: {snap_total} -> {current.total}")

    snap_loc = int(snapshot.get("loc", 0))
    if current.loc < snap_loc and current.total < snap_total:
        reasons.append(
            f"source LOC dropped ({snap_loc} -> {current.loc}) with reduced coverage"
        )

    return Verdict(ok=not reasons, reasons=reasons)


# --- I/O boundary (round-trip tested) ---------------------------------------


def snapshot_path(project_root: str | os.PathLike, run_id: str) -> Path:
    return Path(project_root) / ".shipwright" / "runs" / run_id / SNAPSHOT_FILENAME


def write_snapshot(project_root: str | os.PathLike, run_id: str, snapshot: dict) -> Path:
    path = snapshot_path(project_root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)  # atomic on same filesystem
    return path


def read_snapshot(project_root: str | os.PathLike, run_id: str) -> dict:
    return json.loads(snapshot_path(project_root, run_id).read_text(encoding="utf-8"))


# --- impure runners ---------------------------------------------------------


def _split_cmd(test_cmd: str) -> list[str]:
    # posix=False on Windows so backslash paths (e.g. sys.executable) survive.
    return shlex.split(test_cmd, posix=(os.name != "nt"))


def collect_test_ids(project_root: str | os.PathLike, base: list[str], targets: list[str]) -> list[str]:
    """Collected pytest node ids (empty for a non-pytest runner)."""
    proc = subprocess.run(
        [*base, *targets, "--collect-only", "-q"],
        cwd=str(project_root), capture_output=True, text=True,
    )
    return sorted(line.strip() for line in proc.stdout.splitlines() if "::" in line)


def run_test_suite(project_root: str | os.PathLike, base: list[str], targets: list[str]) -> tuple[int, int, int]:
    """Run the suite; return (passed, failed, exit_code).

    ``exit_code`` is AUTHORITATIVE for the green/red decision (a non-zero exit
    means a failure/error/no-tests regardless of the summary text). The parsed
    ``passed``/``failed`` counts are ADVISORY (best-effort, first-match) — used
    only for the human summary and the count-drop signal — so a future change
    must not make the gate trust them in place of ``exit_code``.
    """
    proc = subprocess.run(
        [*base, *targets, "-q"],
        cwd=str(project_root), capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    passed = int(m.group(1)) if (m := _PASSED_RE.search(out)) else 0
    failed = int(m.group(1)) if (m := _FAILED_RE.search(out)) else 0
    return passed, failed, proc.returncode


def measure_loc(project_root: str | os.PathLike) -> int:
    """Total non-test Python source LOC under ``project_root``."""
    total = 0
    for p in Path(project_root).rglob("*.py"):
        if any(part in _EXCLUDE_DIRS for part in p.parts):
            continue
        # `tests/` dir + conventional test filenames are test code, not source.
        # (Only the plural `tests` dir name — a source module literally named
        # `test` is real and must still count toward the source-LOC signal.)
        if "tests" in p.parts:
            continue
        if p.name.startswith("test_") or p.name.endswith("_test.py") or p.name == "conftest.py":
            continue
        try:
            with p.open("r", encoding="utf-8", errors="ignore") as fh:
                total += sum(1 for _ in fh)
        except OSError:
            continue
    return total


def gather_current(project_root: str | os.PathLike, base: list[str], targets: list[str]) -> SuiteResult:
    node_ids = collect_test_ids(project_root, base, targets)
    passed, failed, exit_code = run_test_suite(project_root, base, targets)
    total = len(node_ids) if node_ids else passed + failed
    return SuiteResult(node_ids, passed, failed, total, exit_code, measure_loc(project_root))


# --- CLI --------------------------------------------------------------------


def _cmd_snapshot(args: argparse.Namespace) -> int:
    base = _split_cmd(args.test_cmd)
    result = gather_current(args.project_root, base, args.target)
    if result.exit_code != 0 or result.failed > 0:
        print(
            f"behavior_snapshot: REFUSED — baseline is not green "
            f"(exit={result.exit_code}, failed={result.failed}). Make the suite "
            f"green before snapshotting; there is no green state to preserve.",
            file=sys.stderr,
        )
        return 2
    snap = build_snapshot(args.run_id, result, base + args.target)
    path = write_snapshot(args.project_root, args.run_id, snap)
    if not result.node_ids:
        print(
            "behavior_snapshot: WARNING — no pytest node-ids collected; the "
            "removed-coverage and count-drop guards are INERT for this run "
            "(only green->red is checked). Use a pytest runner for the full gate.",
            file=sys.stderr,
        )
    print(
        f"behavior_snapshot: stored green baseline — {snap['total']} test(s), "
        f"{result.loc} source LOC -> {path}"
    )
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    try:
        snap = read_snapshot(args.project_root, args.run_id)
    except FileNotFoundError:
        print(
            f"behavior_snapshot: no snapshot for run_id={args.run_id!r} — run "
            f"'snapshot' before the edit.",
            file=sys.stderr,
        )
        return 2
    # Always replay the snapshot's exact effective command (base + targets) so
    # the before/after comparison is symmetric. A scoped `--target` snapshot vs.
    # a re-specified, unscoped verify command would compare a narrow baseline
    # against a wide current and silently neuter the gate. If the caller passes
    # a `--test-cmd` that differs from what the snapshot ran, WARN and still
    # replay the snapshot's command for a faithful comparison.
    stored = snap.get("test_cmd", [])
    if args.test_cmd:
        provided = _split_cmd(args.test_cmd) + args.target
        if provided != stored:
            print(
                f"behavior_snapshot: WARNING — verify command {provided} differs "
                f"from the snapshot's {stored}; replaying the snapshot command for "
                f"a faithful comparison.",
                file=sys.stderr,
            )
    current = gather_current(args.project_root, stored, [])
    verdict = compute_verdict(snap, current)
    if verdict.ok:
        print(
            f"behavior_snapshot: VERIFIED — behavior preserved "
            f"({current.total} test(s) green; LOC {snap.get('loc')} -> {current.loc})."
        )
        return 0
    print("behavior_snapshot: REJECTED — behavior not preserved:", file=sys.stderr)
    for reason in verdict.reasons:
        print(f"  - {reason}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Behavior-snapshot gate for code-simplify iterates.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("snapshot", "verify"):
        sp = sub.add_parser(name)
        sp.add_argument("--project-root", required=True)
        sp.add_argument("--run-id", required=True)
        sp.add_argument("--test-cmd", default="" if name == "verify" else f"{sys.executable} -m pytest")
        sp.add_argument("--target", nargs="*", default=[])
    args = parser.parse_args(argv)
    return _cmd_snapshot(args) if args.command == "snapshot" else _cmd_verify(args)


if __name__ == "__main__":
    raise SystemExit(main())
