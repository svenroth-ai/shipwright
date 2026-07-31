"""F1's drift verdict must not read a git FAILURE as a clean tree.

Run-ID: iterate-2026-07-31-triage-store-failsafe (AC-7, consumer half).

**Why this lives in THIS root and not in `shared/tests`.** `finalize_bundle.py`
imports its sibling with the BARE package name (`from tools.finalize_bundle_lib
import …`), so it resolves whatever `tools` means first in the process. The
`shared/tests` root contains `shared/tests/tools/`, a package of exactly that
name, and several of its modules put `shared/tests` on `sys.path` ahead of
`shared/scripts` to sibling-import helpers. Whichever binds first wins for the
whole process (ADR-044/ADR-045), so an `_f1_record` test placed there passes or
fails on collection ORDER — measured, in both directions, on this run.

Here there is no competing `tools`: the root anchors on `shared/` and imports via
the `scripts.tools.` prefix, which `shared/tests/tools` cannot shadow.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.tools.finalize_bundle import _f1_record  # noqa: E402
from scripts.tools.finalize_bundle_lib import RunResult  # noqa: E402


def _rr(payload: dict, returncode: int) -> RunResult:
    return RunResult(returncode=returncode, stdout=json.dumps(payload), stderr="")


def test_f1_record_reports_a_git_failure_as_failed() -> None:
    """An `error` in artifact_sync's JSON must outrank its drift verdict.

    The gate has to live HERE, not in artifact_sync: `_f1_record` reads
    `drift_detected` and maps `False` -> ok, so a git failure — which legitimately
    reports `drift_detected: False` because it never determined any drift — was
    passing F1 as a clean tree.
    """
    rec = _f1_record(_rr(
        {"drift_detected": False, "error": "could not read git diff",
         "message": "x", "affected": []}, returncode=2))

    assert rec["status"] == "failed", rec
    assert "could not determine drift" in rec["reason"], rec


def test_f1_record_still_reports_a_clean_run_ok() -> None:
    """The opposite direction: a genuine no-drift run must stay `ok`.

    Without this, hard-coding `failed` would satisfy the test above.
    """
    assert _f1_record(_rr(
        {"drift_detected": False, "message": "No drift detected",
         "affected": []}, returncode=0))["status"] == "ok"


def test_f1_record_still_reports_real_drift() -> None:
    """And a real drift verdict is still reported as drift, not as an error."""
    rec = _f1_record(_rr(
        {"drift_detected": True, "message": "1 mapping(s) affected",
         "affected": [{"pattern": "src/**"}]}, returncode=1))
    assert rec["status"] == "drift", rec


def test_empty_error_string_is_not_treated_as_an_error() -> None:
    """`error: ""` is falsy and must NOT hijack a clean verdict — the branch tests
    the VALUE, not the key's presence."""
    assert _f1_record(_rr(
        {"drift_detected": False, "error": "", "message": "clean",
         "affected": []}, returncode=0))["status"] == "ok"
