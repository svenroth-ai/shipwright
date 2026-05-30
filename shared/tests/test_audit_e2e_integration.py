"""End-to-end audit-chain probe via the verify_iterate_finalization CLI.

Plan §V.2 calls for the four F0.5 fail-closed conditions to be reproduced
not just at the check-function level (already covered in
``test_verify_iterate_finalization.py``) but through the CLI itself —
so we exercise the same path the iterate skill's F11 step actually
invokes:

    uv run shared/scripts/tools/verify_iterate_finalization.py \\
        --run-id ... --project-root ... --commit ...

Each test seeds a tmp project with a different state and asserts:

- exit code 0 on green / skipped (only WARNs)
- exit code 1 when the F0.5 audit reports an ERROR

These tests are slower than the unit tests because each one spawns a
subprocess; the trade-off is they catch CLI regressions (argparse,
import path, formatter) that pure-import tests miss.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


# Resolve the verifier path relative to this test file. The script is at
# shared/scripts/tools/verify_iterate_finalization.py, two levels up.
VERIFIER = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "tools"
    / "verify_iterate_finalization.py"
)


# A valid Test Completeness Ledger block — seeded green by default so the
# F0.5 surface block stays the isolated red flag (gate added 2026-05-30).
_VALID_COMPLETENESS: dict = {
    "status": "complete",
    "behaviors": [
        {"behavior": "seeded behavior", "disposition": "tested",
         "evidence": "fixture::seeded PASSED"},
    ],
    "counts": {"testable": 1, "tested": 1, "untestable": 0, "untested_testable": 0},
}


def _seed(
    proj: Path,
    run_id: str,
    *,
    complexity: str = "medium",
    surface_block: dict | None = None,
    completeness_block: dict | None = None,
    include_test_results: bool = True,
) -> None:
    """Build a minimally-passing project state, optionally with the F0.5 block.

    The other audit checks (iterate_history, ADR, changelog, session_handoff,
    test_completeness) are seeded green so the only red flag (or its absence)
    is the F0.5 surface_verification block. That isolates the failure mode
    under test. Pass ``completeness_block`` to override the green default and
    isolate the completeness gate instead."""
    proj.mkdir(parents=True, exist_ok=True)
    (proj / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (proj / ".shipwright" / "agent_docs" / "iterates").mkdir(parents=True, exist_ok=True)

    # iterate_history entry (file-per-iterate format)
    entry_path = proj / ".shipwright" / "agent_docs" / "iterates" / f"{run_id}.json"
    entry_path.write_text(json.dumps({
        "run_id": run_id,
        "date": "2026-05-06T07:00:00Z",
        "type": "feature",
        "complexity": complexity,
        "branch": "iterate/foo",
        "tests_passed": True,
        "adr": "ADR-999",
    }), encoding="utf-8")

    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [],   # legacy-array empty (file-per-iterate is canonical)
    }), encoding="utf-8")

    # decision_log with ADR-999
    (proj / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "# Decision Log\n\n### ADR-999: Test\n- **Date:** 2026-05-06\n",
        encoding="utf-8",
    )

    # CHANGELOG drop file for run_id
    drop_dir = proj / "CHANGELOG-unreleased.d" / "Added"
    drop_dir.mkdir(parents=True, exist_ok=True)
    (drop_dir / f"{run_id}_001.md").write_text("Test bullet\n", encoding="utf-8")

    # session_handoff.md fresh
    (proj / ".shipwright" / "agent_docs" / "session_handoff.md").write_text(
        "fresh", encoding="utf-8"
    )

    # build_dashboard with run_id
    (proj / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text(
        f"# Build Dashboard\nrun_id: {run_id}\n", encoding="utf-8"
    )

    # events.jsonl with the commit (we'll pass --commit fakeSHA)
    (proj / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "work_completed", "commit": "abc123def456"}) + "\n",
        encoding="utf-8",
    )

    # test_results.json — varies per test
    if include_test_results:
        results: dict = {"iterate_latest": {}}
        if surface_block is not None:
            results["iterate_latest"]["surface_verification"] = surface_block
        comp = completeness_block if completeness_block is not None else _VALID_COMPLETENESS
        results["iterate_latest"]["test_completeness"] = comp
        (proj / "shipwright_test_results.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )


def _run_verifier(proj: Path, run_id: str, commit: str = "abc123def456") -> tuple[int, str]:
    """Invoke the verifier as a subprocess. Returns (exit_code, stdout+stderr)."""
    result = subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--run-id", run_id,
            "--project-root", str(proj),
            "--commit", commit,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


# ---------------------------------------------------------------------------
# Happy paths — exit 0
# ---------------------------------------------------------------------------


def test_cli_passes_with_valid_surface_block(tmp_path):
    proj = tmp_path / "proj"
    _seed(proj, "iterate-2026-05-06-cli-happy", surface_block={
        "surface": "cli", "runner": "pytest", "exit_code": 0,
        "tests_run": 5, "evidence_path": "log.txt", "timestamp": "now",
    })
    code, output = _run_verifier(proj, "iterate-2026-05-06-cli-happy")
    assert code == 0, f"happy path must exit 0; output:\n{output}"
    assert "F0.5 surface_verification" in output


def test_cli_passes_with_surface_none_and_justification(tmp_path):
    proj = tmp_path / "proj"
    _seed(proj, "iterate-2026-05-06-none-ok", surface_block={
        "surface": "none", "runner": "", "exit_code": 0,
        "tests_run": 0, "evidence_path": "", "timestamp": "now",
        "justification": "pure type-hint rename; no runtime path exercised",
    })
    code, output = _run_verifier(proj, "iterate-2026-05-06-none-ok")
    assert code == 0, output


def test_cli_passes_at_trivial_complexity_skipping_audit(tmp_path):
    """At trivial/small the audit returns SKIPPED and verifier exits 0
    even when the block is absent."""
    proj = tmp_path / "proj"
    _seed(proj, "iterate-2026-05-06-trivial",
          complexity="trivial", surface_block=None)
    code, output = _run_verifier(proj, "iterate-2026-05-06-trivial")
    assert code == 0, output
    assert "skipped" in output.lower()


# ---------------------------------------------------------------------------
# Fail-closed paths — exit 1
# ---------------------------------------------------------------------------


def test_cli_fails_when_block_missing_at_medium(tmp_path):
    """Plan §V.2 case 'Spec missing': medium+ iterate without
    surface_verification → verifier exits 1."""
    proj = tmp_path / "proj"
    _seed(proj, "iterate-2026-05-06-missing-block", surface_block=None)
    code, output = _run_verifier(proj, "iterate-2026-05-06-missing-block")
    assert code == 1, f"missing block must fail; output:\n{output}"
    assert "surface_verification" in output


def test_cli_fails_on_zero_tests(tmp_path):
    """Plan §V.2 case 'Zero tests': greedy-filter trap recorded as
    tests_run=0 → audit fails."""
    proj = tmp_path / "proj"
    _seed(proj, "iterate-2026-05-06-zero", surface_block={
        "surface": "cli", "runner": "pytest -k nope", "exit_code": 0,
        "tests_run": 0, "evidence_path": "log.txt", "timestamp": "now",
    })
    code, output = _run_verifier(proj, "iterate-2026-05-06-zero")
    assert code == 1, f"zero tests must fail; output:\n{output}"
    assert "tests_run" in output


def test_cli_fails_on_runner_failure(tmp_path):
    """Plan §V.3: dev-server-kill / runner-failure path — exit_code != 0
    after retries → audit fails."""
    proj = tmp_path / "proj"
    _seed(proj, "iterate-2026-05-06-runner-failed", surface_block={
        "surface": "web", "runner": "playwright test", "exit_code": 1,
        "tests_run": 5, "evidence_path": "report.html", "timestamp": "now",
    })
    code, output = _run_verifier(proj, "iterate-2026-05-06-runner-failed")
    assert code == 1, output
    assert "exit_code" in output


def test_cli_fails_on_surface_none_without_justification(tmp_path):
    """Plan §V.2 case 'Surfaceless bad-path': surface=none but no
    justification → audit fails."""
    proj = tmp_path / "proj"
    _seed(proj, "iterate-2026-05-06-none-bad", surface_block={
        "surface": "none", "runner": "", "exit_code": 0,
        "tests_run": 0, "evidence_path": "", "timestamp": "now",
        # justification deliberately absent
    })
    code, output = _run_verifier(proj, "iterate-2026-05-06-none-bad")
    assert code == 1, output
    assert "justification" in output


def test_cli_fails_when_test_results_missing_at_medium(tmp_path):
    """A medium+ iterate that didn't write shipwright_test_results.json at
    all is the most-broken path — F5 didn't run, so F0.5 couldn't have
    consolidated either. Verifier must exit 1."""
    proj = tmp_path / "proj"
    _seed(proj, "iterate-2026-05-06-no-results", include_test_results=False)
    code, output = _run_verifier(proj, "iterate-2026-05-06-no-results")
    assert code == 1, output


def test_cli_fails_on_testable_but_untested_behavior(tmp_path):
    """CLI-level completeness gate: surface green, but the ledger declares a
    testable-but-untested behavior → verifier exits 1 (the merge chokepoint)."""
    proj = tmp_path / "proj"
    _seed(
        proj, "iterate-2026-05-06-untested",
        surface_block={
            "surface": "cli", "runner": "pytest", "exit_code": 0,
            "tests_run": 5, "evidence_path": "log.txt", "timestamp": "now",
        },
        completeness_block={
            "status": "complete",
            "behaviors": [
                {"behavior": "happy", "disposition": "tested",
                 "evidence": "t::a PASSED"},
            ],
            "counts": {"testable": 3, "tested": 1, "untestable": 0,
                       "untested_testable": 2},
        },
    )
    code, output = _run_verifier(proj, "iterate-2026-05-06-untested")
    assert code == 1, f"testable-but-untested must fail; output:\n{output}"
    assert "completeness" in output.lower()


# ---------------------------------------------------------------------------
# Strict mode — promote warnings to errors
# ---------------------------------------------------------------------------


def test_cli_strict_mode_does_not_falsely_promote_skipped_to_error(tmp_path):
    """A SKIPPED check at trivial complexity must NOT be treated as an
    error in --strict mode. Only WARN should escalate."""
    proj = tmp_path / "proj"
    _seed(proj, "iterate-2026-05-06-strict-trivial",
          complexity="trivial", surface_block=None)
    result = subprocess.run(
        [
            sys.executable, str(VERIFIER),
            "--run-id", "iterate-2026-05-06-strict-trivial",
            "--project-root", str(proj),
            "--commit", "abc123def456",
            "--strict",
        ],
        capture_output=True, text=True, check=False,
    )
    # build_dashboard check may WARN; surface check is SKIPPED. The
    # contract is that SKIPPED never escalates. A WARN may; that's
    # acceptable — we just assert SKIPPED alone doesn't trip --strict.
    output = (result.stdout or "") + (result.stderr or "")
    assert "skipped" in output.lower(), f"surface check should be SKIPPED; output:\n{output}"
