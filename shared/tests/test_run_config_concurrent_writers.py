"""Concurrency regression for writers of ``shipwright_run_config.json``.

Pitfall #3 in docs/guide.md §8.5 names ``shipwright_run_config.json`` as
not multi-writer safe. v0.3.0 introduced the file-per-iterate refactor
to eliminate the iterate_history merge conflict, but the config file
itself is still written by at least two concurrent code paths:

- ``append_iterate_entry.py``  (F5c — file-per-iterate migration state)
- ``append_phase_history.py``  (phase-complete history append)

Both acquire the same lock (``shipwright_run_config.json.lock`` via
``shared/scripts/lib/file_lock.py``). This module exercises that
invariant: spawn both as real subprocesses against one temp project and
assert no lost update, no malformed JSON, no duplicate entries.

Bootstrap writers (``plugins/shipwright-project/scripts/write_run_config.py``
and ``plugins/shipwright-adopt/scripts/lib/config_writer.py``) do NOT
use the lock. That is semantically safe: both run once at project
creation / onboarding, never in parallel with iterate/phase appends.
This test does not cover them; the audit trail for this decision lives
in the v0.3.2 iterate plan.
"""
from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
APPEND_ITERATE = ROOT / "shared" / "scripts" / "tools" / "append_iterate_entry.py"
APPEND_PHASE = ROOT / "shared" / "scripts" / "tools" / "append_phase_history.py"


def _seed_project(project_root: Path) -> None:
    (project_root / "shipwright_run_config.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "phase_history": {},
                "iterate_history": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _uv_subprocess(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=45,
    )


@pytest.mark.slow
def test_iterate_and_phase_appends_are_serialized(tmp_path: Path) -> None:
    """Two concurrent writers produce a consistent config + one entry each."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _seed_project(project_root)

    iterate_cmd = [
        sys.executable,
        str(APPEND_ITERATE),
        "--project-root",
        str(project_root),
        "--run-id",
        "iterate-2026-04-24-concurrent-writer",
        "--entry-json",
        json.dumps(
            {
                "type": "bug",
                "complexity": "small",
                "branch": "iterate/concurrent-writer",
                "tests_passed": True,
            }
        ),
    ]
    phase_cmd = [
        sys.executable,
        str(APPEND_PHASE),
        "--project-root",
        str(project_root),
        "--phase",
        "iterate",
        "--run-id",
        "phase-2026-04-24-concurrent-writer",
        "--entry-json",
        json.dumps({"status": "completed"}),
    ]

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_iterate = pool.submit(_uv_subprocess, iterate_cmd)
        fut_phase = pool.submit(_uv_subprocess, phase_cmd)
        iterate_result = fut_iterate.result()
        phase_result = fut_phase.result()

    assert iterate_result.returncode == 0, (
        f"iterate append failed:\nSTDOUT:{iterate_result.stdout}\n"
        f"STDERR:{iterate_result.stderr}"
    )
    assert phase_result.returncode == 0, (
        f"phase append failed:\nSTDOUT:{phase_result.stdout}\n"
        f"STDERR:{phase_result.stderr}"
    )

    # Config must be valid JSON (no torn write).
    config_text = (project_root / "shipwright_run_config.json").read_text("utf-8")
    config = json.loads(config_text)
    assert isinstance(config, dict)

    # Phase history gained exactly one iterate-bucket entry.
    phase_bucket = config.get("phase_history", {}).get("iterate", [])
    assert len(phase_bucket) == 1, (
        f"expected 1 phase entry, got {len(phase_bucket)}: {phase_bucket}"
    )
    assert phase_bucket[0].get("status") == "completed"
    assert phase_bucket[0].get("run_id") == "phase-2026-04-24-concurrent-writer"

    # Iterate entry landed as a file, not in the legacy array.
    entry_path = (
        project_root
        / "agent_docs"
        / "iterates"
        / "iterate-2026-04-24-concurrent-writer.json"
    )
    assert entry_path.exists(), "iterate entry file missing"
    entry = json.loads(entry_path.read_text("utf-8"))
    assert entry["run_id"] == "iterate-2026-04-24-concurrent-writer"

    # Migration flipped the iterate-side state.
    assert config.get("_iterate_migration_state") == "complete"


@pytest.mark.slow
def test_many_iterate_writers_dont_corrupt_config(tmp_path: Path) -> None:
    """Four concurrent iterate appenders → no duplicate files, no torn JSON."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _seed_project(project_root)

    def iterate_cmd(slug: str) -> list[str]:
        return [
            sys.executable,
            str(APPEND_ITERATE),
            "--project-root",
            str(project_root),
            "--run-id",
            f"iterate-2026-04-24-{slug}",
            "--entry-json",
            json.dumps(
                {
                    "type": "bug",
                    "complexity": "small",
                    "branch": f"iterate/{slug}",
                    "tests_passed": True,
                }
            ),
        ]

    slugs = ["alpha", "bravo", "charlie", "delta"]
    with ThreadPoolExecutor(max_workers=len(slugs)) as pool:
        results = list(pool.map(_uv_subprocess, [iterate_cmd(s) for s in slugs]))

    for r, slug in zip(results, slugs):
        assert r.returncode == 0, (
            f"append failed for {slug}:\nSTDOUT:{r.stdout}\nSTDERR:{r.stderr}"
        )

    # All four entry files landed distinctly.
    entry_dir = project_root / "agent_docs" / "iterates"
    files = sorted(p.name for p in entry_dir.iterdir() if p.name.endswith(".json"))
    assert files == [f"iterate-2026-04-24-{s}.json" for s in slugs], (
        f"unexpected entry files: {files}"
    )

    # Config ended up valid + state flipped to complete exactly once.
    config = json.loads(
        (project_root / "shipwright_run_config.json").read_text("utf-8")
    )
    assert config.get("_iterate_migration_state") == "complete"
    # Legacy array stays empty (documented backward-compat shim).
    assert config.get("iterate_history") == []
