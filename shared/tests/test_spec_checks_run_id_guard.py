"""S2/S3 run_id guard (Layer 2 of iterate-2026-05-31-phasequality-triage-bundle).

When the resolved run_id is a sentinel (``""`` / ``"unknown"``) or has no
exact ``iterate_history`` entry — AND no matching spec/mini-plan file is on
disk — S2/S3 must SKIP rather than tail-fall-back to the most-recent entry's
complexity and emit an unsatisfiable FAIL (AC-5). A matching file on disk
preserves the file-exists→PASS signal (AC-6).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import lib.phase_quality as pq  # noqa: E402
from tools.verifiers import spec_checks as sc  # noqa: E402


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    return tmp_path


def _history(proj: Path, entries: list[dict]) -> None:
    (proj / "shipwright_run_config.json").write_text(
        json.dumps({"iterate_history": entries}), encoding="utf-8")


def _spec_file(proj: Path, stem: str) -> None:
    d = proj / ".shipwright" / "planning" / "iterate"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.md").write_text("body", encoding="utf-8")


# --- S2 -----------------------------------------------------------------

def test_s2_skip_on_unknown_run_id_ignores_tail_fallback(proj: Path) -> None:
    # The bug: run_id=unknown inherited the latest entry's medium complexity
    # and FAILed on an impossible spec-file match. Now it SKIPs.
    _history(proj, [{"run_id": "iterate-2026-05-30-real", "complexity": "medium"}])
    f = sc.check_s2_iterate_spec(proj, run_id="unknown")
    assert f["status"] == pq.STATUS_SKIP
    assert "not a resolvable iterate run" in f["evidence"]


def test_s2_skip_on_empty_run_id(proj: Path) -> None:
    _history(proj, [{"run_id": "iterate-2026-05-30-real", "complexity": "medium"}])
    assert sc.check_s2_iterate_spec(proj, run_id="")["status"] == pq.STATUS_SKIP


def test_s2_file_on_disk_overrides_guard(proj: Path) -> None:
    # AC-6: a matching spec file on disk → guard does NOT skip; normal logic
    # runs and the file satisfies S2 (PASS), even without an exact entry.
    _history(proj, [{"run_id": "other", "complexity": "medium"}])
    _spec_file(proj, "2026-05-31-myrun")
    f = sc.check_s2_iterate_spec(proj, run_id="myrun")
    assert f["status"] == pq.STATUS_PASS


def test_s2_exact_entry_still_fails_when_spec_missing(proj: Path) -> None:
    # Guard must NOT fire for a real run with an exact entry → genuine FAIL.
    _history(proj, [{"run_id": "real", "complexity": "medium"}])
    f = sc.check_s2_iterate_spec(proj, run_id="real")
    assert f["status"] == pq.STATUS_FAIL


def test_s2_skip_when_no_history_at_all(proj: Path) -> None:
    # No run_config / no entries → unresolvable → SKIP (not a crash).
    assert sc.check_s2_iterate_spec(proj, run_id="unknown")["status"] == pq.STATUS_SKIP


# --- S3 -----------------------------------------------------------------

def test_s3_skip_on_unknown_run_id(proj: Path) -> None:
    _history(proj, [{"run_id": "iterate-2026-05-30-real", "complexity": "medium"}])
    f = sc.check_s3_iterate_miniplan(proj, run_id="unknown")
    assert f["status"] == pq.STATUS_SKIP
    assert "not a resolvable iterate run" in f["evidence"]


def test_s3_exact_entry_still_warns_when_miniplan_missing(proj: Path) -> None:
    _history(proj, [{"run_id": "real", "complexity": "medium"}])
    f = sc.check_s3_iterate_miniplan(proj, run_id="real")
    assert f["status"] == pq.STATUS_WARN
