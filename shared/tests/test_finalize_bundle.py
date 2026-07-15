"""Unit tests for shared/scripts/tools/finalize_bundle.py.

The bundle orchestrates the iterate finalization sub-tools (F1 artifact_sync,
F3 write_decision_drop, F4 write_changelog_drop, F5c append_iterate_entry,
F5b finalize_iterate) as subprocesses in dependency order. These tests use an
INJECTED runner so they exercise ordering / abort / argv construction / stdout
capture WITHOUT spawning a real process. The real-tool composition is proven by
test_finalize_bundle_integration.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.finalize_bundle import RunResult, run


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #

def _payload(**over):
    base = {
        "run_id": "iterate-2026-07-15-demo",
        "decision": {
            "section": "Iterate — change: demo",
            "title": "Demo ADR",
            "context": "why",
            "decision": "what",
            "consequences": "impact",
        },
        "changelog": [{"category": "Changed", "bullet": "did a thing"}],
        "iterate_entry": {
            "type": "change",
            "complexity": "medium",
            "branch": "iterate/demo",
            "tests_passed": True,
            "adr": "iterate-2026-07-15-demo",
        },
        "finalize": {
            "reason": "iterate: demo",
            "event_extras": {"intent": "change", "spec_impact": "none"},
        },
    }
    base.update(over)
    return base


class FakeRunner:
    """Records (tool_name, argv, cwd) and returns scripted RunResults.

    ``script`` maps a tool filename (e.g. ``write_decision_drop.py``) to a
    RunResult; unscripted tools default to rc 0. ``artifact_sync.py`` defaults
    to a clean no-drift stdout so the happy path resolves to "ok".
    """

    def __init__(self, script=None):
        self.calls = []  # list of dicts: {tool, argv, cwd}
        self.script = script or {}

    def tools(self):
        return [c["tool"] for c in self.calls]

    def argv_for(self, tool):
        for c in self.calls:
            if c["tool"] == tool:
                return c["argv"]
        return None

    def all_argv_for(self, tool):
        return [c["argv"] for c in self.calls if c["tool"] == tool]

    def __call__(self, argv, cwd):
        tool = Path(argv[1]).name
        self.calls.append({"tool": tool, "argv": list(argv), "cwd": cwd})
        if tool in self.script:
            return self.script[tool]
        if tool == "artifact_sync.py":
            return RunResult(0, json.dumps({"drift_detected": False}), "")
        return RunResult(0, "", "")


def _val(argv, flag):
    """Return the value following ``flag`` in an argv list."""
    return argv[argv.index(flag) + 1]


# --------------------------------------------------------------------------- #
# AC1 — happy path, ordering
# --------------------------------------------------------------------------- #

def test_all_steps_ok_runs_in_dependency_order(tmp_path):
    runner = FakeRunner()
    result = run(_payload(), tmp_path, runner=runner)
    assert result["success"] is True
    assert result["failed_step"] is None
    for step in ("F1", "F3", "F4", "F5c", "F5b"):
        assert result["steps"][step]["status"] == "ok"
    # F1 first, F5b last; F3 before F4 before F5c before F5b.
    assert runner.tools() == [
        "artifact_sync.py",
        "write_decision_drop.py",
        "write_changelog_drop.py",
        "append_iterate_entry.py",
        "finalize_iterate.py",
    ]


# --------------------------------------------------------------------------- #
# AC2 — F3 failure aborts before F4/F5c/F5b
# --------------------------------------------------------------------------- #

def test_f3_failure_aborts_and_names_the_step(tmp_path):
    runner = FakeRunner(
        {"write_decision_drop.py": RunResult(1, "", "ERROR: context exceeds 500-char budget")}
    )
    result = run(_payload(), tmp_path, runner=runner)
    assert result["success"] is False
    assert result["failed_step"] == "F3"
    assert "500-char budget" in result["steps"]["F3"]["stderr"]
    # No later step ran.
    assert "write_changelog_drop.py" not in runner.tools()
    assert "append_iterate_entry.py" not in runner.tools()
    assert "finalize_iterate.py" not in runner.tools()


# --------------------------------------------------------------------------- #
# AC3 — F1 drift aborts before ANY write
# --------------------------------------------------------------------------- #

def test_f1_drift_aborts_before_any_write(tmp_path):
    runner = FakeRunner(
        {"artifact_sync.py": RunResult(1, json.dumps({"drift_detected": True}), "")}
    )
    result = run(_payload(), tmp_path, runner=runner)
    assert result["success"] is False
    assert result["failed_step"] == "F1"
    assert result["steps"]["F1"]["status"] == "drift"
    assert "drift" in result["steps"]["F1"]["reason"].lower()
    # Only artifact_sync ran — no writes.
    assert runner.tools() == ["artifact_sync.py"]


def test_f1_crash_unparseable_stdout_is_failure_not_drift(tmp_path):
    """A crash in artifact_sync also exits 1 but emits no drift JSON — it must
    be reported as a tool failure, never mislabelled as drift (external-review)."""
    runner = FakeRunner(
        {"artifact_sync.py": RunResult(1, "Traceback (most recent call last): ...", "boom")}
    )
    result = run(_payload(), tmp_path, runner=runner)
    assert result["success"] is False
    assert result["failed_step"] == "F1"
    assert result["steps"]["F1"]["status"] == "failed"
    assert runner.tools() == ["artifact_sync.py"]


def test_f1_skip_bypasses_drift_gate(tmp_path):
    runner = FakeRunner()
    result = run(_payload(artifact_sync={"skip": True}), tmp_path, runner=runner)
    assert result["success"] is True
    assert result["steps"]["F1"]["status"] == "skipped"
    assert "artifact_sync.py" not in runner.tools()


def test_f1_custom_ref_is_passed_through(tmp_path):
    runner = FakeRunner()
    run(_payload(artifact_sync={"ref": "origin/main..HEAD"}), tmp_path, runner=runner)
    assert _val(runner.argv_for("artifact_sync.py"), "--ref") == "origin/main..HEAD"


def test_f1_default_ref_when_section_absent(tmp_path):
    runner = FakeRunner()
    run(_payload(), tmp_path, runner=runner)
    assert _val(runner.argv_for("artifact_sync.py"), "--ref") == "HEAD~1..HEAD"


# --------------------------------------------------------------------------- #
# AC6 — argv construction
# --------------------------------------------------------------------------- #

def test_f3_argv_carries_decision_fields(tmp_path):
    runner = FakeRunner()
    p = _payload()
    p["decision"]["rationale"] = "because"
    p["decision"]["architecture_impact"] = "convention"
    run(p, tmp_path, runner=runner)
    argv = runner.argv_for("write_decision_drop.py")
    assert _val(argv, "--run-id") == "iterate-2026-07-15-demo"
    assert _val(argv, "--section") == "Iterate — change: demo"
    assert _val(argv, "--title") == "Demo ADR"
    assert _val(argv, "--decision") == "what"
    assert _val(argv, "--rationale") == "because"
    assert _val(argv, "--architecture-impact") == "convention"


def test_f3_omits_optional_flags_when_absent(tmp_path):
    runner = FakeRunner()
    run(_payload(), tmp_path, runner=runner)
    argv = runner.argv_for("write_decision_drop.py")
    assert "--rationale" not in argv
    assert "--spec-ref" not in argv


def test_f5c_argv_passes_entry_json(tmp_path):
    runner = FakeRunner()
    run(_payload(), tmp_path, runner=runner)
    argv = runner.argv_for("append_iterate_entry.py")
    entry = json.loads(_val(argv, "--entry-json"))
    assert entry["type"] == "change"
    assert entry["complexity"] == "medium"


def test_f5b_argv_passes_reason_and_event_extras(tmp_path):
    runner = FakeRunner()
    run(_payload(), tmp_path, runner=runner)
    argv = runner.argv_for("finalize_iterate.py")
    assert _val(argv, "--reason") == "iterate: demo"
    extras = json.loads(_val(argv, "--event-extras-json"))
    assert extras["spec_impact"] == "none"


def test_all_steps_receive_the_same_project_root(tmp_path):
    runner = FakeRunner()
    run(_payload(), tmp_path, runner=runner)
    roots = {_val(c["argv"], "--project-root") for c in runner.calls}
    assert roots == {str(tmp_path.resolve())}


# --------------------------------------------------------------------------- #
# AC7 — N changelog bullets → N invocations
# --------------------------------------------------------------------------- #

def test_n_changelog_bullets_produce_n_invocations(tmp_path):
    runner = FakeRunner()
    p = _payload(changelog=[
        {"category": "Added", "bullet": "one"},
        {"category": "Fixed", "bullet": "two"},
    ])
    result = run(p, tmp_path, runner=runner)
    calls = runner.all_argv_for("write_changelog_drop.py")
    assert len(calls) == 2
    assert _val(calls[0], "--category") == "Added"
    assert _val(calls[0], "--bullet") == "one"
    assert _val(calls[1], "--category") == "Fixed"
    assert _val(calls[1], "--bullet") == "two"
    assert len(result["steps"]["F4"]["drops"]) == 2


def test_f4_failure_on_second_bullet_names_f4_and_aborts(tmp_path):
    calls = {"n": 0}

    def script(argv, cwd):
        pass

    # Fail the SECOND changelog invocation only.
    class _R(FakeRunner):
        def __call__(self, argv, cwd):
            tool = Path(argv[1]).name
            if tool == "write_changelog_drop.py":
                calls["n"] += 1
                self.calls.append({"tool": tool, "argv": list(argv), "cwd": cwd})
                if calls["n"] == 2:
                    return RunResult(1, "", "ERROR: unknown category")
                return RunResult(0, "", "")
            return super().__call__(argv, cwd)

    runner = _R()
    p = _payload(changelog=[
        {"category": "Added", "bullet": "one"},
        {"category": "Fixed", "bullet": "two"},
    ])
    result = run(p, tmp_path, runner=runner)
    assert result["success"] is False
    assert result["failed_step"] == "F4"
    assert result["steps"]["F4"]["drops"][1]["status"] == "failed"
    # F5c / F5b did not run.
    assert "append_iterate_entry.py" not in runner.tools()


def test_f5b_failure_names_f5b(tmp_path):
    runner = FakeRunner(
        {"finalize_iterate.py": RunResult(1, json.dumps({"error": "fr_gate_unclassified"}), "gate")}
    )
    result = run(_payload(), tmp_path, runner=runner)
    assert result["success"] is False
    assert result["failed_step"] == "F5b"
