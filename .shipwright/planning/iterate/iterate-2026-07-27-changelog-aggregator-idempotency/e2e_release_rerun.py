#!/usr/bin/env python3
"""F0.5 end-to-end verification: the release command, re-run.

Drives the REAL CLI the release path invokes (`/shipwright-changelog` SKILL.md
Step 4) as a subprocess against a throwaway project — not the library, not a
mock. Every assertion is on the bytes of `CHANGELOG.md` and on the drop files
left on disk, because those are what a release can destroy.

Four scenarios, in the order an operator meets them:

  1. First release            -> section inserted, drops consumed
  2. Interrupted, then re-run -> ONE section, drops consumed  (the bug)
  3. Completed, then re-run   -> clean no-op                  (must not refuse)
  4. Partially consumed drops -> non-zero exit, nothing touched (the hazard)

Exit 0 = all scenarios passed. Prints one line per assertion so the F0.5
evidence shows what was actually checked.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
AGGREGATOR = REPO / "shared" / "scripts" / "tools" / "aggregate_changelog.py"
DROPS = "CHANGELOG-unreleased.d"

HEADER = (
    "# Changelog\n\n"
    "All notable changes to this project will be documented in this file.\n\n"
)
PRIOR = "## [0.2.0] - 2026-04-01\n\n### Added\n\n- an earlier release\n"

_checks = 0
_failures: list[str] = []


def check(label: str, condition: bool) -> None:
    global _checks
    _checks += 1
    status = "ok" if condition else "FAIL"
    print(f"  [{status}] {label}")
    if not condition:
        _failures.append(label)


def run_cli(project: Path, *extra: str) -> subprocess.CompletedProcess:
    """Invoke the aggregator exactly as the release path does."""
    return subprocess.run(
        [
            sys.executable, str(AGGREGATOR),
            "--project-root", str(project),
            "--version", "0.3.0",
            "--release-date", "2026-04-23",
            *extra,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=120,
    )


def seed(project: Path, bullets: list[tuple[str, str]]) -> None:
    (project / "CHANGELOG.md").write_text(HEADER + PRIOR, encoding="utf-8")
    for i, (category, text) in enumerate(bullets):
        d = project / DROPS / category
        d.mkdir(parents=True, exist_ok=True)
        (d / f"iterate-2026-04-2{i}-run_001.md").write_text(text, encoding="utf-8")


def drops_on_disk(project: Path) -> set[str]:
    base = project / DROPS
    if not base.is_dir():
        return set()
    return {p.read_text(encoding="utf-8").strip() for p in base.rglob("*.md")}


BULLETS = [("Added", "first bullet"), ("Added", "second bullet"), ("Fixed", "a fix")]


def scenario_first_release(project: Path) -> None:
    print("1. first release")
    seed(project, BULLETS)
    result = run_cli(project)
    check("exit 0", result.returncode == 0)
    payload = json.loads(result.stdout)
    check("section_action == inserted", payload["section_action"] == "inserted")
    text = (project / "CHANGELOG.md").read_text(encoding="utf-8")
    check("one [0.3.0] section", text.count("## [0.3.0]") == 1)
    check("all three bullets published", all(b in text for _, b in BULLETS))
    check("prior release intact", "an earlier release" in text)
    check("title not displaced", text.startswith("# Changelog"))
    check("drops consumed", drops_on_disk(project) == set())


def scenario_interrupted_then_rerun(project: Path) -> None:
    print("2. interrupted between write and unlink, then re-run")
    seed(project, BULLETS)
    backup = project / "_backup"
    shutil.copytree(project / DROPS, backup)
    run_cli(project)
    shutil.rmtree(project / DROPS)
    shutil.copytree(backup, project / DROPS)
    shutil.rmtree(backup)
    after_first = (project / "CHANGELOG.md").read_text(encoding="utf-8")

    result = run_cli(project)
    check("exit 0", result.returncode == 0)
    text = (project / "CHANGELOG.md").read_text(encoding="utf-8")
    check("still exactly ONE [0.3.0] section", text.count("## [0.3.0]") == 1)
    check("file byte-identical to the first run", text == after_first)
    check("all bullets survived", all(b in text for _, b in BULLETS))
    check("drops now consumed", drops_on_disk(project) == set())


def scenario_completed_then_rerun(project: Path) -> None:
    print("3. completed release, re-run again")
    seed(project, BULLETS)
    run_cli(project)
    before = (project / "CHANGELOG.md").read_text(encoding="utf-8")

    result = run_cli(project)
    check("exit 0 (a finished release stays re-runnable)", result.returncode == 0)
    payload = json.loads(result.stdout)
    check("section_action == none", payload["section_action"] == "none")
    check("changelog untouched", (project / "CHANGELOG.md").read_text(
        encoding="utf-8") == before)


def scenario_partial_unlink_refuses(project: Path) -> None:
    print("4. drops partially consumed, then re-run")
    seed(project, BULLETS)
    backup = project / "_backup"
    shutil.copytree(project / DROPS, backup)
    run_cli(project)
    shutil.rmtree(project / DROPS)
    shutil.copytree(backup, project / DROPS)
    shutil.rmtree(backup)
    # The unlink loop got two of three before dying.
    for path in (project / DROPS).rglob("*.md"):
        if "a fix" not in path.read_text(encoding="utf-8"):
            path.unlink()

    before_text = (project / "CHANGELOG.md").read_text(encoding="utf-8")
    before_drops = drops_on_disk(project)

    result = run_cli(project)
    check("non-zero exit", result.returncode != 0)
    check("stderr names the version", "0.3.0" in result.stderr)
    check("stderr names the cause",
          "not what the pending entries say" in result.stderr)
    check("stderr is ASCII (survives a Windows pipe)",
          all(ord(c) < 128 for c in result.stderr))
    check("CHANGELOG.md byte-unchanged",
          (project / "CHANGELOG.md").read_text(encoding="utf-8") == before_text)
    check("no drop consumed", drops_on_disk(project) == before_drops)
    check("released bullets NOT deleted",
          all(b in before_text for _, b in BULLETS))


def main() -> int:
    print(f"F0.5 end-to-end: {AGGREGATOR.relative_to(REPO)}")
    for scenario in (
        scenario_first_release,
        scenario_interrupted_then_rerun,
        scenario_completed_then_rerun,
        scenario_partial_unlink_refuses,
    ):
        with tempfile.TemporaryDirectory() as td:
            scenario(Path(td))

    print(f"\ntests_run={_checks} failures={len(_failures)}")
    if _failures:
        for f in _failures:
            print(f"  FAILED: {f}")
        return 1
    print("F0.5 PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
