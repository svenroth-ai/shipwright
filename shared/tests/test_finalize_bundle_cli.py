"""CLI + payload-validation tests for finalize_bundle.py.

Split from test_finalize_bundle.py (which covers run() orchestration) to keep
each file focused and under the size guideline. Shares the FakeRunner / _payload
helpers from that module (established sibling-import pattern in shared/tests,
e.g. test_parallel_merge_cascade_integration imports from test_integrate_main).
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

# Sibling-import the shared FakeRunner / _payload helpers (established pattern in
# shared/tests, e.g. test_parallel_merge_cascade_integration → test_integrate_main).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_finalize_bundle import FakeRunner, _payload  # noqa: E402
from tools.finalize_bundle import (  # noqa: E402
    BundleValidationError,
    RunResult,
    main,
    run,
)


# --------------------------------------------------------------------------- #
# Payload validation (AC4) — fail-fast, no subprocess runs
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("mutate", [
    lambda p: p.pop("finalize"),
    lambda p: p.pop("decision"),
    lambda p: p.pop("changelog"),
    lambda p: p.pop("iterate_entry"),
    lambda p: p.pop("run_id"),
])
def test_missing_required_section_is_validation_error(tmp_path, mutate):
    runner = FakeRunner()
    p = _payload()
    mutate(p)
    with pytest.raises(BundleValidationError):
        run(p, tmp_path, runner=runner)
    assert runner.calls == []  # nothing ran


def test_unknown_top_level_key_rejected(tmp_path):
    runner = FakeRunner()
    with pytest.raises(BundleValidationError, match="unknown"):
        run(_payload(bogus="x"), tmp_path, runner=runner)
    assert runner.calls == []


def test_empty_changelog_list_rejected(tmp_path):
    with pytest.raises(BundleValidationError, match="changelog"):
        run(_payload(changelog=[]), tmp_path, runner=FakeRunner())


def test_bad_changelog_category_rejected(tmp_path):
    with pytest.raises(BundleValidationError, match="category"):
        run(_payload(changelog=[{"category": "Nope", "bullet": "x"}]), tmp_path, runner=FakeRunner())


def test_blank_run_id_rejected(tmp_path):
    with pytest.raises(BundleValidationError, match="run_id"):
        run(_payload(run_id="   "), tmp_path, runner=FakeRunner())


def test_finalize_missing_event_extras_rejected(tmp_path):
    with pytest.raises(BundleValidationError, match="event_extras"):
        run(_payload(finalize={"reason": "x"}), tmp_path, runner=FakeRunner())


def test_bad_architecture_impact_rejected(tmp_path):
    p = _payload()
    p["decision"]["architecture_impact"] = "bogus"
    with pytest.raises(BundleValidationError, match="architecture_impact"):
        run(p, tmp_path, runner=FakeRunner())


def test_unknown_decision_key_rejected(tmp_path):
    """A misspelled optional F3 flag (e.g. architecure_impact) must fail fast,
    not be silently ignored by the argv builder (code-review LOW)."""
    p = _payload()
    p["decision"]["architecure_impact"] = "convention"  # typo
    runner = FakeRunner()
    with pytest.raises(BundleValidationError, match="decision: unknown"):
        run(p, tmp_path, runner=runner)
    assert runner.calls == []


def test_unknown_artifact_sync_key_rejected(tmp_path):
    runner = FakeRunner()
    with pytest.raises(BundleValidationError, match="artifact_sync: unknown"):
        run(_payload(artifact_sync={"reff": "HEAD~1..HEAD"}), tmp_path, runner=runner)
    assert runner.calls == []


def test_iterate_entry_forbidden_key_rejected(tmp_path):
    """run_id / date are injected by append_iterate_entry and rejected there —
    pre-reject so the typo fails fast before F1/F3/F4 write."""
    p = _payload()
    p["iterate_entry"]["date"] = "2026-07-15"
    with pytest.raises(BundleValidationError, match="iterate_entry must not set"):
        run(p, tmp_path, runner=FakeRunner())


# --------------------------------------------------------------------------- #
# Internal-error containment (code-review MED / doubt LOW) — one JSON always
# --------------------------------------------------------------------------- #

def test_internal_error_emits_structured_json_exit_3(tmp_path, capsys):
    """A subprocess spawn failure (or any unexpected error) must still emit ONE
    JSON document + a defined exit code, never a bare traceback."""
    def _boom(argv, cwd):
        raise OSError("cannot spawn")

    payload_file = tmp_path / "p.json"
    payload_file.write_text(json.dumps(_payload()), encoding="utf-8")
    rc = main(["--payload-file", str(payload_file), "--project-root", str(tmp_path)],
              runner=_boom)
    assert rc == 3
    parsed = json.loads(capsys.readouterr().out)  # single valid JSON document
    assert parsed["error"] == "internal"
    assert "OSError" in parsed["detail"]


# --------------------------------------------------------------------------- #
# F5b signal surfacing (doubt-review MED) — un-bury finalize_iterate step status
# --------------------------------------------------------------------------- #

def test_finalize_steps_surfaced_from_f5b_stdout(tmp_path):
    """A best-effort compliance skip inside finalize_iterate must be visible at
    the top of the bundle result, not buried in truncated F5b stdout."""
    f5b_out = json.dumps({"steps": {
        "event": {"id": "evt-1"},
        "compliance": {"skipped": True},
        "dashboard": {"written": "x"},
    }})
    runner = FakeRunner({"finalize_iterate.py": RunResult(0, f5b_out, "")})
    result = run(_payload(), tmp_path, runner=runner)
    assert result["success"] is True
    fs = result["steps"]["F5b"]["finalize_steps"]
    assert fs["compliance"] == "skipped"
    assert fs["event"] == "ok"
    assert fs["dashboard"] == "ok"


def test_payload_is_not_mutated_by_run(tmp_path):
    p = _payload()
    snapshot = copy.deepcopy(p)
    run(p, tmp_path, runner=FakeRunner())
    assert p == snapshot


# --------------------------------------------------------------------------- #
# stdout capture / truncation (external-review HIGH)
# --------------------------------------------------------------------------- #

def test_noisy_child_output_is_truncated_and_bundle_emits_single_json(tmp_path, capsys):
    noise = "x" * 50_000
    runner = FakeRunner({"finalize_iterate.py": RunResult(0, noise, noise)})
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps(_payload()), encoding="utf-8")
    rc = main(
        ["--payload-file", str(payload_file), "--project-root", str(tmp_path)],
        runner=runner,
    )
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)  # single valid JSON document
    assert parsed["success"] is True
    assert len(parsed["steps"]["F5b"]["stdout"]) < len(noise)  # truncated


# --------------------------------------------------------------------------- #
# main() exit codes + payload IO
# --------------------------------------------------------------------------- #

def test_main_success_exit_0(tmp_path, capsys):
    payload_file = tmp_path / "p.json"
    payload_file.write_text(json.dumps(_payload()), encoding="utf-8")
    rc = main(["--payload-file", str(payload_file), "--project-root", str(tmp_path)],
              runner=FakeRunner())
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["success"] is True


def test_main_step_failure_exit_1(tmp_path, capsys):
    payload_file = tmp_path / "p.json"
    payload_file.write_text(json.dumps(_payload()), encoding="utf-8")
    runner = FakeRunner({"finalize_iterate.py": RunResult(1, "", "boom")})
    rc = main(["--payload-file", str(payload_file), "--project-root", str(tmp_path)],
              runner=runner)
    assert rc == 1
    assert json.loads(capsys.readouterr().out)["failed_step"] == "F5b"


def test_main_validation_error_exit_2(tmp_path, capsys):
    payload_file = tmp_path / "p.json"
    bad = _payload()
    bad.pop("finalize")
    payload_file.write_text(json.dumps(bad), encoding="utf-8")
    rc = main(["--payload-file", str(payload_file), "--project-root", str(tmp_path)],
              runner=FakeRunner())
    assert rc == 2
    assert json.loads(capsys.readouterr().out)["error"] == "payload_validation"


def test_main_missing_payload_file_exit_2(tmp_path, capsys):
    rc = main(["--payload-file", str(tmp_path / "nope.json"), "--project-root", str(tmp_path)],
              runner=FakeRunner())
    assert rc == 2
    assert json.loads(capsys.readouterr().out)["error"] == "payload_unreadable"


def test_main_invalid_json_exit_2(tmp_path, capsys):
    payload_file = tmp_path / "p.json"
    payload_file.write_text("{not json", encoding="utf-8")
    rc = main(["--payload-file", str(payload_file), "--project-root", str(tmp_path)],
              runner=FakeRunner())
    assert rc == 2
    assert json.loads(capsys.readouterr().out)["error"] == "payload_invalid_json"
