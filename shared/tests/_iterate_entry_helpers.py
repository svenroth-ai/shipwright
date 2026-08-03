"""Small helpers shared by iterate-entry transaction tests."""

import json
from pathlib import Path

from lib.iterate_entry import iterates_dir
from tools.append_iterate_entry import append_iterate_entry as _append


def write_current_evidence(project: Path, run_id: str) -> bytes:
    raw = json.dumps({"iterate_latest": {"run_id": run_id}}).encode()
    (project / "shipwright_test_results.json").write_bytes(raw)
    return raw


def append_iterate_entry(project: Path, entry: dict, **kwargs):
    """Exercise F5c while keeping legacy transaction tests terse."""
    write_current_evidence(project, entry["run_id"])
    return _append(project, entry, **kwargs)


def summary_files(project: Path) -> list[Path]:
    return sorted(
        p for p in iterates_dir(project).glob("iterate-*.json")
        if not p.name.endswith(".test-results.json")
    )
