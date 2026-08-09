from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import phase_quality as pq  # noqa: E402
from tools.verifiers import iterate_compliance  # noqa: E402


def _events(root: Path, rows: list[dict]) -> None:
    (root / "shipwright_events.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _evidence(root: Path, run: str) -> Path:
    path = root / ".shipwright" / "compliance" / "test-evidence.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# Evidence\n\nSource-State: run={run}\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("key", ["adr_id", "run_id", "iterate_run_id"])
def test_w3_accepts_each_declared_run_identity(tmp_path: Path, key: str):
    first = {"type": "work_completed", "source": "iterate", "ts": "2026-04-18T12:00:00Z", key: "run-1"}
    _events(tmp_path, [first, {"type": "work_completed", "source": "iterate", "adr_id": "run-2", "ts": "2026-04-19T12:00:00Z"}])
    _evidence(tmp_path, "run-1")
    assert iterate_compliance.check_w3_work_completed_and_evidence(tmp_path, "run-1")["status"] == pq.STATUS_PASS


def test_w3_ignores_old_mtime_when_source_state_is_current(tmp_path: Path):
    _events(tmp_path, [{"type": "work_completed", "source": "iterate", "adr_id": "run-1", "ts": "2026-04-18T12:00:00Z"}])
    evidence = _evidence(tmp_path, "run-1")
    old = time.time() - 172800
    os.utime(evidence, (old, old))
    assert iterate_compliance.check_w3_work_completed_and_evidence(tmp_path, "run-1")["status"] == pq.STATUS_PASS


def test_w3_rejects_newer_input_or_missing_requested_completion(tmp_path: Path):
    _events(tmp_path, [{"type": "work_completed", "source": "iterate", "adr_id": "run-1", "ts": "2026-04-18T12:00:00Z"}, {"type": "work_completed", "source": "iterate", "adr_id": "run-2", "ts": "2026-04-19T12:00:00Z"}])
    _evidence(tmp_path, "run-1")
    assert iterate_compliance.check_w3_work_completed_and_evidence(tmp_path, "run-2")["status"] == pq.STATUS_FAIL
    _evidence(tmp_path, "run-2")
    assert iterate_compliance.check_w3_work_completed_and_evidence(tmp_path, "run-3")["status"] == pq.STATUS_FAIL


def test_w3_fails_closed_for_missing_or_non_utf8_source_state(tmp_path: Path):
    _events(tmp_path, [{"type": "work_completed", "source": "iterate", "adr_id": "run-1", "ts": "2026-04-18T12:00:00Z"}])
    evidence = _evidence(tmp_path, "run-1")
    evidence.write_text("# Evidence\n", encoding="utf-8")
    assert iterate_compliance.check_w3_work_completed_and_evidence(tmp_path, "run-1")["status"] == pq.STATUS_FAIL
    evidence.write_bytes(b"\xff")
    assert iterate_compliance.check_w3_work_completed_and_evidence(tmp_path, "run-1")["status"] == pq.STATUS_FAIL