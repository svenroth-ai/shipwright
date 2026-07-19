"""Record-boundary recovery in the F11 verifier's event lookups (sites 9-11).

The Stage-2 code review surfaced these after the brief's "six sites" enumeration
had already been shown incomplete. They matter more than their line count
suggests: ``_committed_blob_has_event`` is the oracle behind the F11
``check_events_has_commit`` gate, so here the defect is **inverted and
operator-facing** — a concatenated line does not merely lose history, it makes
F11 FAIL FINALIZATION for a run that recorded everything correctly.

All three live in one file. The review named two; the third
(``_find_work_event_by_run_id``) is adjacent and identical, and converting only
the named ones would reproduce this bug's own root cause: *the fix reached only
the call sites that were rewritten.*
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.events_log import resolve_events_path  # noqa: E402
from tools.verifiers import iterate_checks as ic  # noqa: E402

_RUN_A = "iterate-2026-07-19-side-a"
_RUN_B = "iterate-2026-07-19-side-b"


def _work(run_id: str, commit: str) -> dict:
    return {
        "v": 1, "id": f"evt-{run_id}", "ts": "2026-07-19T10:00:00+00:00",
        "type": "work_completed", "adr_id": run_id, "run_id": run_id, "commit": commit,
    }


def _concatenated_blob() -> str:
    """Two work_completed records on ONE physical line, side B second."""
    return json.dumps(_work(_RUN_A, "aaa1111")) + json.dumps(_work(_RUN_B, "bbb2222")) + "\n"


# ---------------------------------------------------------------------------
# Site 9 — the F11 check_events_has_commit oracle (inverted failure)
# ---------------------------------------------------------------------------

def test_committed_blob_finds_an_event_that_is_second_on_a_line() -> None:
    """THE operator-facing case. Pre-fix the whole line was skipped, so an
    iterate whose ``work_completed`` landed second read as never recorded and
    F11 failed a correctly-finalized run."""
    blob = _concatenated_blob()
    assert ic._committed_blob_has_event(blob, "bbb2222", _RUN_B) is True


def test_committed_blob_finds_an_event_that_is_first_on_a_line() -> None:
    blob = _concatenated_blob()
    assert ic._committed_blob_has_event(blob, "aaa1111", _RUN_A) is True


def test_committed_blob_still_reports_absence_for_an_unrelated_run() -> None:
    """Recovery must not turn the gate into a rubber stamp: an event that is
    genuinely absent must still read as absent."""
    blob = _concatenated_blob()
    assert ic._committed_blob_has_event(blob, "ccc3333", "iterate-not-present") is False


def test_committed_blob_tolerates_a_fragment_without_losing_valid_records() -> None:
    blob = json.dumps(_work(_RUN_A, "aaa1111")) + "{truncated\n"
    assert ic._committed_blob_has_event(blob, "aaa1111", _RUN_A) is True


def test_committed_blob_ignores_a_bare_scalar_line() -> None:
    blob = "5\n" + json.dumps(_work(_RUN_A, "aaa1111")) + "\n"
    assert ic._committed_blob_has_event(blob, "aaa1111", _RUN_A) is True


# ---------------------------------------------------------------------------
# Sites 10 + 11 — the two on-disk lookups
# ---------------------------------------------------------------------------

def test_find_work_event_by_commit_recovers_a_second_record(tmp_path: Path) -> None:
    resolve_events_path(tmp_path).write_text(_concatenated_blob(), encoding="utf-8")
    found = ic._find_work_event_by_commit(tmp_path, "bbb2222")
    assert found is not None and found["adr_id"] == _RUN_B


def test_find_work_event_by_run_id_recovers_a_second_record(tmp_path: Path) -> None:
    """The third site — adjacent, identical, and NOT named by the review."""
    resolve_events_path(tmp_path).write_text(_concatenated_blob(), encoding="utf-8")
    found = ic._find_work_event_by_run_id(tmp_path, _RUN_B)
    assert found is not None and found["commit"] == "bbb2222"


def test_on_disk_lookups_do_not_crash_on_a_bare_scalar_line(tmp_path: Path) -> None:
    """Neither lookup had an ``isinstance`` guard: ``json.loads('5')`` returned an
    int and ``evt.get(...)`` raised AttributeError."""
    resolve_events_path(tmp_path).write_text(
        "5\n" + json.dumps(_work(_RUN_A, "aaa1111")) + "\n", encoding="utf-8"
    )
    assert ic._find_work_event_by_commit(tmp_path, "aaa1111") is not None
    assert ic._find_work_event_by_run_id(tmp_path, _RUN_A) is not None


def test_on_disk_lookups_return_none_when_absent(tmp_path: Path) -> None:
    assert ic._find_work_event_by_commit(tmp_path, "aaa1111") is None
    assert ic._find_work_event_by_run_id(tmp_path, _RUN_A) is None
