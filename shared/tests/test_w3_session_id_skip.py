"""W3 must not audit a Claude session id as if it were an iterate run (#984).

When no iterate run resolves, ``resolve_run_id`` falls back to the session UUID
(or ``"unknown"``). W3 then looked for a ``work_completed`` event under that id,
found none, and FAILed for a run that does not exist; the FAIL was saved and
repeated in every later SessionStart notice. A session-shaped id SKIPs now.

What must NOT change: a real-looking run id with no event still FAILs, and so
does stale test-evidence for a real run (a different failure, with a real cause).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import phase_quality as pq  # noqa: E402
from tools.verifiers import iterate_compliance  # noqa: E402

SESSION_ID = "322972ae-2d74-42d6-993b-03463bec9a0a"
REAL_RUN = "iterate-2026-10-01-codextender-agent-tool-review-dispatch"
OLDER_RUN = "iterate-2026-09-28-hooks-uv-run-project-pin"


def _events(root: Path, *run_ids: str) -> None:
    rows = [
        {"type": "work_completed", "source": "iterate", "adr_id": rid,
         "ts": f"2026-10-0{i + 1}T12:00:00Z"}
        for i, rid in enumerate(run_ids)
    ]
    (root / "shipwright_events.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _evidence(root: Path, run: str) -> None:
    path = root / ".shipwright" / "compliance" / "test-evidence.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# Evidence\n\nSource-State: run={run}\n", encoding="utf-8")


def _w3(root: Path, run_id: str) -> dict:
    return iterate_compliance.check_w3_work_completed_and_evidence(root, run_id)


@pytest.mark.covers("FR-01.11/AC01")
class TestW3SessionIdFallback:

    @pytest.mark.parametrize("run_id", [SESSION_ID, SESSION_ID.upper(), "unknown", "Unknown"])
    def test_session_shaped_id_skips_even_though_other_runs_completed(
        self, tmp_path: Path, run_id: str,
    ):
        # The reported shape: a project full of finished iterates, audited under
        # the session id because no iterate was active.
        _events(tmp_path, REAL_RUN, OLDER_RUN)
        _evidence(tmp_path, REAL_RUN)

        finding = _w3(tmp_path, run_id)

        assert finding["status"] == pq.STATUS_SKIP
        assert finding["reason_code"] == pq.REASON_CODE_UNRESOLVABLE_RUN_ID

    def test_session_id_with_its_own_completion_event_is_still_audited(self, tmp_path: Path):
        # A run that really is keyed by that id (an event names it) is not
        # unresolvable: the normal logic runs and judges the evidence.
        _events(tmp_path, SESSION_ID)
        _evidence(tmp_path, SESSION_ID)

        assert _w3(tmp_path, SESSION_ID)["status"] == pq.STATUS_PASS

    def test_real_run_without_completion_event_still_fails(self, tmp_path: Path):
        _events(tmp_path, OLDER_RUN)

        assert _w3(tmp_path, REAL_RUN)["status"] == pq.STATUS_FAIL

    def test_stale_evidence_for_a_real_run_still_fails(self, tmp_path: Path):
        # The "Source-State run=<old> does not match latest work_completed
        # run=<new>" notice is a genuine staleness, NOT a session id: the skip
        # must never mask it.
        _events(tmp_path, REAL_RUN)
        _evidence(tmp_path, OLDER_RUN)

        finding = _w3(tmp_path, REAL_RUN)

        assert finding["status"] == pq.STATUS_FAIL
        assert "does not match" in finding["evidence"]

    def test_empty_run_id_keeps_matching_every_completion(self, tmp_path: Path):
        # Pre-existing behaviour for ``""`` is untouched by the guard.
        _events(tmp_path, REAL_RUN)
        _evidence(tmp_path, REAL_RUN)

        assert _w3(tmp_path, "")["status"] == pq.STATUS_PASS
