"""Iterate's completion ledger, split out of ``test_completion_writers.py`` at
the 300-LOC bloat-baseline threshold (P3.4 tagging backfill: every test in
that file already carried the same ``FR-01.01/AC08`` tag, so there was no
"newly tagged subset" to extract -- the file's own existing section boundary,
"iterate's completions come from its own ledger", is the split instead).

HIGH-3: `iterate` has never written `phase_history`; F5c writes the
file-per-run ledger, and C3 must read the record iterate actually keeps.
"""

from __future__ import annotations
import pytest

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

from _c3_fixtures import ITERATE_RUN, write_handoff  # noqa: E402
from shared.tests._iterate_entry_helpers import write_current_evidence  # noqa: E402
from lib.phase_history import latest_completion  # noqa: E402
from verifiers.handoff_phase_canon import (  # noqa: E402
    check_c3_session_handoff_fresh_after_phase as check_c3,
)

TOOLS = REPO_ROOT / "shared" / "scripts" / "tools"


def _run(tool: str, *args: str) -> subprocess.CompletedProcess:
    """Invoke a producer exactly as a phase skill does."""
    result = subprocess.run(
        [sys.executable, str(TOOLS / tool), *args],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"{tool} failed: {result.stderr}"
    return result


def _project(root: Path) -> Path:
    (root / "shipwright_run_config.json").write_text(
        json.dumps({"phase_history": {}}), encoding="utf-8"
    )
    write_current_evidence(root, ITERATE_RUN)
    return root


@pytest.mark.covers("FR-01.01/AC08")
def test_the_iterate_ledger_writer_produces_a_readable_completion(tmp_path):
    """HIGH-3. `iterate` has never written `phase_history`; F5c writes the
    file-per-run ledger. C3 must read the record iterate actually keeps."""
    root = _project(tmp_path)
    _run("record_event.py", "--project-root", str(root),
         "--type", "phase_completed", "--phase", "iterate", "--detail", "done")
    _run("append_iterate_entry.py", "--project-root", str(root),
         "--run-id", ITERATE_RUN, "--entry-json", json.dumps({
             "type": "change", "complexity": "medium",
             "branch": "iterate/c3-phase-history-join", "tests_passed": True,
         }))

    completion = latest_completion(root, "iterate")
    config = json.loads((root / "shipwright_run_config.json").read_text(encoding="utf-8"))
    entry = json.loads(
        (root / ".shipwright" / "agent_docs" / "iterates" /
         f"{ITERATE_RUN}.json").read_text(encoding="utf-8"))

    assert "iterate" not in config.get("phase_history", {}), (
        "the ledger writer must not have started writing phase_history"
    )
    assert completion is not None, "iterate's completion must be readable"
    assert completion.run_id == ITERATE_RUN
    assert completion.wall is not None, (
        "its wall clock must be readable — that is what orders iterate against "
        "another phase in the cross-phase branch"
    )
    # The bound this line used to guard has MOVED, on purpose: the ledger stamps
    # the anchor too now (trg-1346abbd), so C3 reads one clock for iterate as
    # well. `test_iterate_ledger_anchor.py` owns that behaviour end to end.
    assert entry["event_at"], "the ledger must carry the anchor C3 reads"
    assert completion.anchor is not None


@pytest.mark.covers("FR-01.01/AC08")
def test_an_iterate_that_wrote_its_note_passes_end_to_end(tmp_path):
    """Ledger entry + marker, both from real writers, joined by C3."""
    root = _project(tmp_path)
    _run("append_iterate_entry.py", "--project-root", str(root),
         "--run-id", ITERATE_RUN, "--entry-json", json.dumps({
             "type": "change", "complexity": "medium", "tests_passed": True,
             "branch": "iterate/c3-phase-history-join",
         }))
    write_handoff(root, phase="iterate", run_id=ITERATE_RUN,
                  timestamp="2026-07-27T08:00:00+00:00")

    result = check_c3(root, "iterate")

    assert result.ok is True, result.detail
