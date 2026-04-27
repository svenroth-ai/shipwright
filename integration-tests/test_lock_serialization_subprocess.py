"""Cross-process lock serialization regression for iterate-entry append.

Promotes the security-audit subprocess probe into first-class CI.

The scenario that triggered this test in the v0.3.2 verification:
- A v0.2.x-shape project carries a ``iterate_history`` array with N rows
  (no ``_iterate_migration_state`` yet).
- Four parallel iterates from four worktrees race into
  ``append_iterate_entry.py`` simultaneously — each one would notice
  the missing state and try to run the migration.

Invariants this test asserts:
1. Migration runs EXACTLY once (``_iterate_migration_state == "complete"``
   with ``_iterate_migration_quarantined_count == 0`` for clean data).
2. All legacy rows land in ``.shipwright/agent_docs/iterates/``.
3. All new entries land as distinct files (no run_id collision, no
   ``O_EXCL`` clobber).
4. ``shipwright_run_config.json`` is valid JSON at the end (no torn
   writes from interleaved atomic-rename operations).

Marked ``slow`` — excluded from the default ``uv run pytest`` run to
avoid the ~10–15s Windows cold-start budget on every commit. Run
explicitly via ``uv run pytest -m slow integration-tests/``.
"""
from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
APPEND_ITERATE = ROOT / "shared" / "scripts" / "tools" / "append_iterate_entry.py"


def _legacy_row(run_id: str, date: str) -> dict:
    return {
        "run_id": run_id,
        "date": date,
        "type": "bug",
        "complexity": "small",
        "branch": "main",
        "tests_passed": True,
    }


def _seed_legacy_project(project_root: Path, legacy_count: int) -> None:
    config = {
        "status": "complete",
        "iterate_history": [
            _legacy_row(
                f"iterate-2026-01-{(i % 28) + 1:02d}-legacy-{i:02d}",
                f"2026-01-{(i % 28) + 1:02d}T10:00:00Z",
            )
            for i in range(legacy_count)
        ],
    }
    (project_root / "shipwright_run_config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )


def _append_cmd(project_root: Path, slug: str) -> list[str]:
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


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=60
    )


@pytest.mark.slow
def test_four_parallel_appends_against_legacy_array(tmp_path: Path) -> None:
    """4 concurrent appenders → migration runs once, 4+legacy entries land cleanly."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _seed_legacy_project(project_root, legacy_count=4)

    slugs = ["alpha", "bravo", "charlie", "delta"]
    with ThreadPoolExecutor(max_workers=len(slugs)) as pool:
        results = list(pool.map(_run, [_append_cmd(project_root, s) for s in slugs]))

    for r, slug in zip(results, slugs):
        assert r.returncode == 0, (
            f"append failed for {slug}: stdout={r.stdout!r} stderr={r.stderr!r}"
        )

    # Config is still valid JSON.
    config_path = project_root / "shipwright_run_config.json"
    config = json.loads(config_path.read_text("utf-8"))

    # Migration ran to completion exactly once with zero quarantine.
    assert config.get("_iterate_migration_state") == "complete"
    assert config.get("_iterate_migration_quarantined_count") == 0
    # Legacy array cleared (backward-compat shim, empty list).
    assert config.get("iterate_history") == []

    # Entry dir holds 4 legacy + 4 new = 8 distinct files.
    entries_dir = project_root / ".shipwright" / "agent_docs" / "iterates"
    files = sorted(p.name for p in entries_dir.iterdir() if p.name.endswith(".json"))
    expected_new = [f"iterate-2026-04-24-{s}.json" for s in slugs]
    for exp in expected_new:
        assert exp in files, f"missing new entry file {exp}; got {files}"
    legacy_files = [f for f in files if f.startswith("iterate-2026-01-")]
    assert len(legacy_files) == 4, (
        f"expected 4 legacy entry files, got {len(legacy_files)}: {legacy_files}"
    )

    # Each entry file is valid JSON with the expected run_id.
    for p in entries_dir.iterdir():
        if not p.name.endswith(".json"):
            continue
        payload = json.loads(p.read_text("utf-8"))
        assert payload["run_id"] == p.stem, (
            f"run_id/filename mismatch: {payload['run_id']!r} vs {p.stem!r}"
        )


@pytest.mark.slow
def test_parallel_appends_on_clean_project(tmp_path: Path) -> None:
    """No legacy array → still serializes; no migration side-effects."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "iterate_history": []}, indent=2) + "\n",
        encoding="utf-8",
    )

    slugs = ["echo", "foxtrot", "golf"]
    with ThreadPoolExecutor(max_workers=len(slugs)) as pool:
        results = list(pool.map(_run, [_append_cmd(project_root, s) for s in slugs]))

    for r, slug in zip(results, slugs):
        assert r.returncode == 0, (
            f"append failed for {slug}: stdout={r.stdout!r} stderr={r.stderr!r}"
        )

    config = json.loads(
        (project_root / "shipwright_run_config.json").read_text("utf-8")
    )
    # Migration still flips to complete (covers the empty-array path).
    assert config.get("_iterate_migration_state") == "complete"
    assert config.get("_iterate_migration_quarantined_count") == 0

    entries_dir = project_root / ".shipwright" / "agent_docs" / "iterates"
    files = sorted(p.name for p in entries_dir.iterdir() if p.name.endswith(".json"))
    assert files == [f"iterate-2026-04-24-{s}.json" for s in slugs]
