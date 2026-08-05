"""Unit tests for Step 3.4's artifact-persistence layer
(`risk_recheck_record.py` + `diff_risk_recheck.main()`'s use of it).

Subprocess-level composition (the real CLI, a real repo, exit-0 AND exit-3
paths) lives in `integration-tests/test_risk_recheck_recording_integration.py`
— subprocess-only tests measure 0% against the diff-coverage gate, so the
in-process assertions here carry the real coverage.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import diff_risk_recheck as drr  # noqa: E402
import risk_recheck_record as rrr  # noqa: E402

RUN_ID = "iterate-2026-08-05-example"


# ---------------------------------------------------------------------------
# write_recheck_record — shape, safety, atomicity
# ---------------------------------------------------------------------------


def test_write_recheck_record_writes_expected_shape(tmp_path: Path):
    result = {"effective_complexity": "medium", "risk_flags": ["cross_component"]}
    path = rrr.write_recheck_record(tmp_path, RUN_ID, result)

    assert path == tmp_path / ".shipwright" / "planning" / "iterate" / RUN_ID / "risk_recheck.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["schema_version"] == rrr.RECHECK_SCHEMA_VERSION
    assert body["run_id"] == RUN_ID
    assert body["risk_recheck"] == result


def test_write_recheck_record_is_atomic_no_leftover_tmp(tmp_path: Path):
    rrr.write_recheck_record(tmp_path, RUN_ID, {"effective_complexity": "small"})
    run_dir = tmp_path / ".shipwright" / "planning" / "iterate" / RUN_ID
    leftovers = list(run_dir.glob("*.tmp"))
    assert leftovers == []


def test_write_recheck_record_overwrites_on_rerun(tmp_path: Path):
    rrr.write_recheck_record(tmp_path, RUN_ID, {"effective_complexity": "small"})
    rrr.write_recheck_record(tmp_path, RUN_ID, {"effective_complexity": "medium"})
    path = rrr.recheck_record_path(tmp_path, RUN_ID)
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["risk_recheck"]["effective_complexity"] == "medium"


@pytest.mark.parametrize("bad_run_id", [
    "../escape", "..", ".", "", "a" * 200, "with/slash", "with\\backslash",
    "trailing space ", None, 42,
])
def test_write_recheck_record_rejects_unsafe_run_id(tmp_path: Path, bad_run_id):
    with pytest.raises(ValueError, match="safe path component"):
        rrr.write_recheck_record(tmp_path, bad_run_id, {"effective_complexity": "small"})
    # Nothing must be written on rejection.
    planning = tmp_path / ".shipwright" / "planning" / "iterate"
    assert not planning.exists() or list(planning.iterdir()) == []


def test_write_recheck_record_rejects_non_regular_file_target(tmp_path: Path):
    """A directory (or symlink) sitting where the file should go must not be
    silently overwritten or written through."""
    path = rrr.recheck_record_path(tmp_path, RUN_ID)
    path.mkdir(parents=True)
    with pytest.raises(OSError, match="not a regular file"):
        rrr.write_recheck_record(tmp_path, RUN_ID, {"effective_complexity": "small"})


def test_write_recheck_record_rejects_symlinked_run_directory(tmp_path: Path):
    """A `<run_id>` directory symlinked OUTSIDE the planning tree must not be
    written through (external code review, 2026-08-05)."""
    outside = tmp_path / "outside"
    outside.mkdir()
    planning = tmp_path / ".shipwright" / "planning" / "iterate"
    planning.mkdir(parents=True)
    try:
        (planning / RUN_ID).symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation unavailable")

    with pytest.raises(OSError, match="resolves outside"):
        rrr.write_recheck_record(tmp_path, RUN_ID, {"effective_complexity": "small"})
    assert list(outside.iterdir()) == [], "must not have written through the symlink"


# ---------------------------------------------------------------------------
# is_safe_run_id — behavioral sync with the shared precedent this plugin-lib
# module deliberately never imports (ADR-044-style: plugin-lib never imports
# shared/ at runtime — precedent: session_plan.RUN_ID_STRICT)
# ---------------------------------------------------------------------------


def test_is_safe_run_id_sync_with_shared_precedent():
    repo_root = Path(__file__).resolve().parents[3]
    shared_lib = repo_root / "shared" / "scripts" / "lib"
    sys.path.insert(0, str(shared_lib))
    from review_record_schema import is_safe_run_id as shared_is_safe_run_id

    samples = [
        "iterate-2026-08-05-example", "14.2", "campaign-14-2", "..", ".",
        "", "a" * 200, "with/slash", "with\\backslash", None, 42, "-leading-dash",
        "a", "A0._-", "trailing.",
    ]
    for sample in samples:
        assert rrr.is_safe_run_id(sample) == shared_is_safe_run_id(sample), (
            f"diverged on {sample!r}"
        )


# ---------------------------------------------------------------------------
# main() — the CLI wires persistence in, guarded by --run-id, without
# changing the process contract's exit codes (0 continue / 3 CI escalation)
# ---------------------------------------------------------------------------


def _run_main(monkeypatch, tmp_path, argv_tail):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv",
        ["diff_risk_recheck.py", "--project-root", str(tmp_path)] + argv_tail,
    )
    return drr.main()


def test_main_persists_artifact_when_run_id_given(monkeypatch, tmp_path, capsys):
    exit_code = _run_main(monkeypatch, tmp_path, [
        "--stage1-complexity", "small", "--changed-files", "src/app.py",
        "--diff-loc", "3", "--run-id", RUN_ID,
    ])
    assert exit_code == 0
    path = rrr.recheck_record_path(tmp_path, RUN_ID)
    assert path.is_file()
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["risk_recheck"]["effective_complexity"] == "small"
    out = json.loads(capsys.readouterr().out)
    assert "recheck_record_error" not in out


def test_main_does_not_persist_when_no_run_id(monkeypatch, tmp_path):
    exit_code = _run_main(monkeypatch, tmp_path, [
        "--stage1-complexity", "small", "--changed-files", "src/app.py",
        "--diff-loc", "3",
    ])
    assert exit_code == 0
    assert not (tmp_path / ".shipwright" / "planning" / "iterate").exists()


def test_main_persists_on_ci_escalation_exit_3(monkeypatch, tmp_path):
    """The exit-3 CI-escalation path must persist too — F11's gate needs the
    escalation's `effective_complexity` just as much as the continue path."""
    exit_code = _run_main(monkeypatch, tmp_path, [
        "--stage1-complexity", "small",
        "--changed-files", ".github/workflows/ci.yml",
        "--diff-loc", "3", "--run-id", RUN_ID,
    ])
    assert exit_code == 3
    path = rrr.recheck_record_path(tmp_path, RUN_ID)
    assert path.is_file()
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["risk_recheck"]["escalate"]["required"] is True
    assert body["risk_recheck"]["effective_complexity"]


def test_main_reports_write_failure_without_changing_exit_code(monkeypatch, tmp_path, capsys):
    """A side-artifact write failure must not turn a real CI-boundary escalation
    (branched on by exit code) into a generic operational failure — the run is
    ALREADY stopping for operator review regardless of the artifact."""
    # Plant a directory where the artifact file must go, forcing write_recheck_record
    # to raise OSError("... not a regular file").
    rrr.recheck_record_path(tmp_path, RUN_ID).parent.mkdir(parents=True)
    rrr.recheck_record_path(tmp_path, RUN_ID).mkdir()
    exit_code = _run_main(monkeypatch, tmp_path, [
        "--stage1-complexity", "small",
        "--changed-files", ".github/workflows/ci.yml",
        "--diff-loc", "3", "--run-id", RUN_ID,
    ])
    assert exit_code == 3, "the CI escalation's exit code must survive a write failure"
    out = json.loads(capsys.readouterr().out)
    assert "not a regular file" in out["recheck_record_error"]
    assert out["escalate"]["required"] is True


def test_main_fails_on_write_failure_on_the_continue_path(monkeypatch, tmp_path, capsys):
    """The opposite case (external code review, 2026-08-05): on the CONTINUE
    path, a write failure must NOT silently return 0 — that would let the
    recording-integrity gate's own producer fail invisibly, which is exactly
    the bypass this mechanism exists to close. It becomes an operational
    failure (exit 2), same as any other reason 'the re-check did not run'."""
    rrr.recheck_record_path(tmp_path, RUN_ID).parent.mkdir(parents=True)
    rrr.recheck_record_path(tmp_path, RUN_ID).mkdir()
    exit_code = _run_main(monkeypatch, tmp_path, [
        "--stage1-complexity", "small", "--changed-files", "src/app.py",
        "--diff-loc", "3", "--run-id", RUN_ID,
    ])
    assert exit_code == 2, "a write failure on the continue path must not exit 0"
    out = json.loads(capsys.readouterr().out)
    assert "not a regular file" in out["recheck_record_error"]
    assert out["escalate"]["required"] is False


def test_main_fails_on_unsafe_run_id_on_the_continue_path(monkeypatch, tmp_path, capsys):
    """`write_recheck_record`'s ValueError for an unsafe --run-id must reach
    the same exit-2 handling — not a silent exit-0 continue with no artifact."""
    exit_code = _run_main(monkeypatch, tmp_path, [
        "--stage1-complexity", "small", "--changed-files", "src/app.py",
        "--diff-loc", "3", "--run-id", "../escape",
    ])
    assert exit_code == 2
    out = json.loads(capsys.readouterr().out)
    assert "safe path component" in out["recheck_record_error"]
