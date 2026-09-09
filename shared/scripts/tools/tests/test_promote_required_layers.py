"""Integration tests for ``promote_required_layers.py``'s process contract
(P3.5, campaign req3-04c-ac-identity-wave2, restart round 2): exit 0/3/other,
ledger written only for actual promotions, spec.md edited surgically,
idempotent re-run.

**Round-2 change to this file's own infrastructure:** ``main()`` now reads
the manifest at ``HEAD`` via ``git show`` (never the working-tree copy), so
every test's project must be a real, committed git repo (``_write_project``
does this). ``resolve_execution_evidence`` is monkeypatched per test
(``_mock_evidence_from``) — its OWN behavior (structural content-binding,
artifact download, the three-outcome contract) is covered directly by
``shared/tests/test_ci_execution_evidence.py``; this file only proves
``promote_required_layers.py``'s OWN orchestration around whatever evidence
it is given.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.promote_required_layers as mod  # noqa: E402
from scripts.ci_execution_evidence import ExecutionEvidence  # noqa: E402
from scripts.lib.fr_table_shape import FR_TABLE_HEADER, FR_TABLE_SEPARATOR  # noqa: E402
from scripts.lib.layer_promotion_ledger import ledger_path, load_ledger  # noqa: E402

_SPEC_RELPATH = ".shipwright/planning/01-adopted/spec.md"
_MANIFEST_RELPATH = ".shipwright/compliance/test-traceability.json"


def _link(*, layer, status="enabled", executed="pass"):
    return {"id": f"t::{layer}", "path": f"t::{layer}", "layer": layer,
            "status": status, "executed": executed}


def _node(fr_id, **overrides):
    node = {
        "id": fr_id, "spec_path": _SPEC_RELPATH, "title": "x",
        "priority": "Must", "status": "active",
        "required_layers": ["unit"], "required_layers_source": "inferred_legacy",
        "tests": {"unit": [_link(layer="unit")]},
        "coverage": {"unit": "ok"},
    }
    node.update(overrides)
    return node


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(  # nosec B603,B607 - fixed argv, shell=False, test helper
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, shell=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {args} failed: {result.stderr}")
    return result.stdout


def _write_project(tmp_path, requirements: dict, *, spec_rows: str, commit: bool = True):
    manifest = {"schema_version": 4, "requirements": requirements}
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "compliance" / "test-traceability.json").write_text(
        json.dumps(manifest), encoding="utf-8",
    )
    spec_dir = tmp_path / ".shipwright" / "planning" / "01-adopted"
    spec_dir.mkdir(parents=True, exist_ok=True)
    doc = "\n".join([
        "# Spec", "", "## Functional Requirements", "",
        FR_TABLE_HEADER, FR_TABLE_SEPARATOR, spec_rows, "",
    ])
    (spec_dir / "spec.md").write_text(doc, encoding="utf-8")
    if commit:
        _git(tmp_path, "init", "-q")
        _git(tmp_path, "config", "user.email", "test@example.com")
        _git(tmp_path, "config", "user.name", "test")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def _mock_evidence_from(monkeypatch, requirements: dict, *, run_id: int = 999, status: str = "confirmed"):
    """Wires ``mod.resolve_execution_evidence`` to return CI evidence built
    directly from ``requirements``'s own ``tests``/``coverage`` — i.e. "CI
    confirms exactly what this test says is currently true," matching the
    pre-restart contract's behavior for every test that isn't specifically
    exercising evidence-unavailable/error paths."""
    ci_map = {
        node["id"]: {"tests": node.get("tests") or {}, "coverage": node.get("coverage") or {}}
        for node in requirements.values()
    }
    evidence = ExecutionEvidence(status, "test", run_id, ci_map if status == "confirmed" else None)
    monkeypatch.setattr(mod, "resolve_execution_evidence", lambda *a, **k: evidence)
    return evidence


def test_clean_promotion_exits_zero_writes_spec_and_ledger(tmp_path, monkeypatch):
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | Does a thing. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements, run_id=34316980804)

    rc = mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-08-p3-5-test"])
    assert rc == 0

    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "| unit |" in spec
    assert "(inferred)" not in spec

    ledger = load_ledger(ledger_path(project))
    entry = ledger["decisions"]["FR-01.01"][-1]
    assert entry["action"] == "promoted"
    assert entry["decided_by"] == "tool"
    assert entry["required_layers"] == ["unit"]
    assert entry["run_id"] == "iterate-2026-09-08-p3-5-test"
    # AC-R12: the ledger names WHICH CI run confirmed this promotion.
    assert entry["ci_run_id"] == 34316980804


def test_a_hand_annotated_cell_is_skipped_instead_of_silently_losing_the_annotation(
    tmp_path, monkeypatch, capsys,
):
    # Medium finding, Stage-3 doubt-review round 2, P3.5 post-push round:
    # otherwise-promotable evidence with a hand-added annotation in the live
    # cell must be skipped, not have this CLI's rewrite silently delete it.
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit, db (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)

    rc = mod.main(["--project-root", str(project)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["promoted"] == []
    assert out["escalated"] == []
    assert out["skipped"][0]["reason_code"] == "live_cell_has_residual_text"
    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "unit, db (inferred)" in spec
    assert not ledger_path(project).exists()


def test_no_eligible_fr_exits_zero_and_writes_nothing(tmp_path, monkeypatch):
    requirements = {"01::FR-01.02": _node("FR-01.02", coverage={"unit": "MISSING"}, tests={})}
    row = "| FR-01.02 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)

    rc = mod.main(["--project-root", str(project)])
    assert rc == 0
    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "(inferred)" in spec
    assert not ledger_path(project).exists()


def test_undecidable_case_exits_three_and_reports_reason_code(tmp_path, monkeypatch, capsys):
    # Two nodes sharing the SAME display id -> collision -> undeterminable.
    requirements = {
        "01::FR-01.01": _node("FR-01.01"),
        "02::FR-01.01": _node("FR-01.01", spec_path=_SPEC_RELPATH, status="removed"),
    }
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)

    rc = mod.main(["--project-root", str(project)])
    assert rc == 3
    out = json.loads(capsys.readouterr().out)
    assert out["escalated"][0]["reason_code"] == "layer_undeterminable"
    assert out["promoted"] == []
    assert "(inferred)" in (project / _SPEC_RELPATH).read_text(encoding="utf-8")


def test_one_escalation_does_not_block_another_frs_clean_promotion(tmp_path, monkeypatch):
    clean = _node("FR-01.01")
    collision_a = _node("FR-01.02", spec_path=_SPEC_RELPATH)
    collision_b = _node("FR-01.02", spec_path=_SPEC_RELPATH, status="removed")
    requirements = {
        "01::FR-01.01": clean,
        "01::FR-01.02": collision_a,
        "02::FR-01.02": collision_b,
    }
    rows = "\n".join([
        "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |",
        "| FR-01.02 | Adopted | x | Must | y. | code | unit (inferred) |",
    ])
    project = _write_project(tmp_path, requirements, spec_rows=rows)
    _mock_evidence_from(monkeypatch, requirements)

    rc = mod.main(["--project-root", str(project)])
    assert rc == 3
    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "| FR-01.01 | Adopted | x | Must | y. | code | unit |" in spec
    assert "| FR-01.02 | Adopted | x | Must | y. | code | unit (inferred) |" in spec


def test_rerun_after_promotion_is_a_clean_noop(tmp_path, monkeypatch):
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)

    assert mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-08-a"]) == 0
    spec_after_first = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    ledger_after_first = json.loads(ledger_path(project).read_text(encoding="utf-8"))

    assert mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-08-b"]) == 0
    assert (project / _SPEC_RELPATH).read_text(encoding="utf-8") == spec_after_first
    ledger_after_second = json.loads(ledger_path(project).read_text(encoding="utf-8"))
    assert ledger_after_second == ledger_after_first
    assert len(ledger_after_second["decisions"]["FR-01.01"]) == 1


def test_ledger_drift_after_manual_revert_escalates_on_rerun(tmp_path, monkeypatch):
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)
    assert mod.main(["--project-root", str(project)]) == 0

    # Someone hand-reverts the spec cell back to advisory, bypassing the tool.
    spec_path = project / _SPEC_RELPATH
    spec_path.write_text(
        spec_path.read_text(encoding="utf-8").replace("| unit |", "| unit (inferred) |"),
        encoding="utf-8",
    )

    rc = mod.main(["--project-root", str(project)])
    assert rc == 3


def test_ledger_write_failure_leaves_spec_md_untouched(tmp_path, monkeypatch):
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)
    original_spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")

    def _boom(*a, **k):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(mod, "write_ledger", _boom)
    rc = mod.main(["--project-root", str(project)])
    assert rc == 2
    assert (project / _SPEC_RELPATH).read_text(encoding="utf-8") == original_spec
    assert not ledger_path(project).exists()


def test_demoted_fr_with_unchanged_evidence_is_a_clean_skip_writes_nothing(tmp_path, monkeypatch):
    import scripts.lib.layer_promotion_ledger as ledger_mod

    node = _node("FR-01.01")
    requirements = {"01::FR-01.01": node}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)

    ledger = ledger_mod.default_ledger()
    ledger_mod.append_decision(
        ledger, "FR-01.01", action="demoted", decided_by="operator",
        reason="evidence is misleading for a reason the manifest can't show",
        evidence_fingerprint=ledger_mod.evidence_fingerprint(node),
    )
    ledger_mod.write_ledger(ledger_mod.ledger_path(project), ledger)
    ledger_before = json.loads(ledger_mod.ledger_path(project).read_text(encoding="utf-8"))

    rc = mod.main(["--project-root", str(project)])
    assert rc == 0

    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "(inferred)" in spec
    ledger_after = json.loads(ledger_mod.ledger_path(project).read_text(encoding="utf-8"))
    assert ledger_after == ledger_before


def test_demoted_fr_with_drifted_evidence_escalates_and_writes_nothing(tmp_path, monkeypatch):
    import scripts.lib.layer_promotion_ledger as ledger_mod

    demoted_against = _node("FR-01.01", coverage={"unit": "MISSING"})
    requirements = {"01::FR-01.01": _node("FR-01.01")}  # CI evidence now "ok"
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)

    ledger = ledger_mod.default_ledger()
    ledger_mod.append_decision(
        ledger, "FR-01.01", action="demoted", decided_by="operator",
        reason="evidence is misleading for a reason the manifest can't show",
        evidence_fingerprint=ledger_mod.evidence_fingerprint(demoted_against),
    )
    ledger_mod.write_ledger(ledger_mod.ledger_path(project), ledger)
    ledger_before = json.loads(ledger_mod.ledger_path(project).read_text(encoding="utf-8"))

    rc = mod.main(["--project-root", str(project)])
    assert rc == 3

    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "(inferred)" in spec
    ledger_after = json.loads(ledger_mod.ledger_path(project).read_text(encoding="utf-8"))
    assert ledger_after == ledger_before


def test_demoted_fr_with_evidence_drifted_toward_worse_is_a_clean_exit_zero_skip(tmp_path, monkeypatch):
    import scripts.lib.layer_promotion_ledger as ledger_mod

    demoted_against = _node("FR-01.01", coverage={"unit": "ok"})
    requirements = {"01::FR-01.01": _node("FR-01.01", coverage={"unit": "MISSING"})}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)

    ledger = ledger_mod.default_ledger()
    ledger_mod.append_decision(
        ledger, "FR-01.01", action="demoted", decided_by="operator",
        reason="evidence is misleading for a reason the manifest can't show",
        evidence_fingerprint=ledger_mod.evidence_fingerprint(demoted_against),
    )
    ledger_mod.write_ledger(ledger_mod.ledger_path(project), ledger)
    ledger_before = json.loads(ledger_mod.ledger_path(project).read_text(encoding="utf-8"))

    rc = mod.main(["--project-root", str(project)])
    assert rc == 0

    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "(inferred)" in spec
    ledger_after = json.loads(ledger_mod.ledger_path(project).read_text(encoding="utf-8"))
    assert ledger_after == ledger_before


def test_stale_manifest_never_narrows_a_hand_declared_multi_layer_cell(tmp_path, monkeypatch):
    node = _node("FR-01.01", required_layers=["unit"])
    requirements = {"01::FR-01.01": node}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit, e2e (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)

    rc = mod.main(["--project-root", str(project)])
    assert rc == 0

    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "| unit, e2e (inferred) |" in spec
    assert not ledger_path(project).exists()


def test_requirement_with_no_spec_path_is_an_operational_failure(tmp_path, monkeypatch, capsys):
    requirements = {"01::FR-01.01": _node("FR-01.01", spec_path="")}
    project = _write_project(tmp_path, requirements, spec_rows="")
    _mock_evidence_from(monkeypatch, requirements)
    rc = mod.main(["--project-root", str(project)])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert "no spec_path" in out["error"]


def test_not_a_git_repo_is_an_operational_failure(tmp_path):
    # Round 2: `main()` reads the manifest via `git show HEAD:...` by
    # default -- a plain (non-git) directory fails at the FIRST step, before
    # evidence resolution or the ledger are ever touched.
    (tmp_path / ".shipwright").mkdir()
    rc = mod.main(["--project-root", str(tmp_path)])
    assert rc == 2


def test_a_git_repo_with_no_commits_is_an_operational_failure(tmp_path, capsys):
    _git(tmp_path, "init", "-q")
    rc = mod.main(["--project-root", str(tmp_path)])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert "could not read the committed manifest at HEAD" in out["error"]


def test_manifest_never_committed_is_an_operational_failure(tmp_path, capsys):
    # A real, non-empty repo, but the manifest file itself was never
    # committed -- `git show HEAD:<path>` fails distinctly from "no HEAD at
    # all."
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    rc = mod.main(["--project-root", str(tmp_path)])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert "could not read the committed manifest at HEAD" in out["error"]


def test_a_corrupted_ledger_required_layers_is_an_operational_failure(tmp_path, monkeypatch, capsys):
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)
    l_path = ledger_path(project)
    l_path.parent.mkdir(parents=True, exist_ok=True)
    l_path.write_text(json.dumps({
        "schema_version": 1,
        "decisions": {
            "FR-01.01": [{
                "action": "promoted", "decided_by": "tool",
                "required_layers": [None, "unit"], "reason": "x",
            }],
        },
    }), encoding="utf-8")

    rc = mod.main(["--project-root", str(project)])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert "FR-01.01" in out["error"]


def test_an_os_error_reading_the_ledger_is_an_operational_failure_not_a_traceback(
    tmp_path, monkeypatch, capsys,
):
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)

    def _boom(*a, **k):
        raise OSError("simulated permission error")

    monkeypatch.setattr(mod, "load_ledger_with_snapshot", _boom)
    rc = mod.main(["--project-root", str(project)])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert "simulated permission error" in out["error"]


def test_majority_escalating_adds_a_sweep_signal_warning_but_keeps_exit_three(tmp_path, monkeypatch, capsys):
    requirements = {
        "01::FR-01.02": _node("FR-01.02", spec_path=_SPEC_RELPATH),
        "02::FR-01.02": _node("FR-01.02", spec_path=_SPEC_RELPATH, status="removed"),
        "01::FR-01.03": _node("FR-01.03", spec_path=_SPEC_RELPATH),
        "02::FR-01.03": _node("FR-01.03", spec_path=_SPEC_RELPATH, status="removed"),
        "01::FR-01.04": _node("FR-01.04", coverage={"unit": "MISSING"}, tests={}),
    }
    rows = "\n".join([
        "| FR-01.02 | Adopted | x | Must | y. | code | unit (inferred) |",
        "| FR-01.03 | Adopted | x | Must | y. | code | unit (inferred) |",
        "| FR-01.04 | Adopted | x | Must | y. | code | unit (inferred) |",
    ])
    project = _write_project(tmp_path, requirements, spec_rows=rows)
    _mock_evidence_from(monkeypatch, requirements)

    rc = mod.main(["--project-root", str(project)])
    assert rc == 3
    out = json.loads(capsys.readouterr().out)
    assert len(out["escalated"]) == 2
    assert "sweep_signal_warning" in out


def test_a_second_invocation_times_out_while_the_lock_is_held(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "_LOCK_TIMEOUT_SECONDS", 0.2)
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)
    original_spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")

    lock_path = mod.ledger_lock_path(project)
    holder_acquired = threading.Event()
    release_holder = threading.Event()

    def _hold_lock():
        with mod.file_lock(lock_path, timeout_seconds=5.0):
            holder_acquired.set()
            release_holder.wait(timeout=5.0)

    holder = threading.Thread(target=_hold_lock)
    holder.start()
    try:
        assert holder_acquired.wait(timeout=5.0), "lock holder never acquired"
        rc = mod.main(["--project-root", str(project)])
        assert rc == 2
    finally:
        release_holder.set()
        holder.join(timeout=5.0)

    assert (project / _SPEC_RELPATH).read_text(encoding="utf-8") == original_spec
    assert not ledger_path(project).exists()


def test_an_exception_inside_the_locked_span_still_releases_the_lock(tmp_path, monkeypatch):
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)

    def _boom(*a, **k):
        raise RuntimeError("simulated non-ValueError ledger read failure")

    with monkeypatch.context() as m:
        m.setattr(mod, "load_ledger_with_snapshot", _boom)
        with pytest.raises(RuntimeError, match="simulated non-ValueError") as excinfo:
            mod.main(["--project-root", str(project)])

    rc = mod.main(["--project-root", str(project)])
    assert rc == 0
    assert excinfo.type is RuntimeError  # keeps `excinfo` referenced past the call above


def test_a_concurrent_spec_edit_between_the_decision_read_and_the_fold_is_refused(
    tmp_path, monkeypatch, capsys,
):
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)
    spec_path = project / _SPEC_RELPATH

    real_plan_promotions = mod.plan_promotions

    def _plan_then_concurrently_edit(manifest, ledger, project_root, evidence):
        decisions, contents_by_path = real_plan_promotions(manifest, ledger, project_root, evidence)
        current = spec_path.read_text(encoding="utf-8")
        spec_path.write_text(
            current.replace("y.", "y (edited concurrently)."), encoding="utf-8",
        )
        return decisions, contents_by_path

    monkeypatch.setattr(mod, "plan_promotions", _plan_then_concurrently_edit)

    rc = mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-08-p3-5-toctou"])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert "could not write a promoted spec.md" in out["error"]

    spec = spec_path.read_text(encoding="utf-8")
    assert "edited concurrently" in spec
    assert "(inferred)" in spec

    ledger = load_ledger(ledger_path(project))
    entry = ledger["decisions"]["FR-01.01"][-1]
    assert entry["action"] == "promoted"


# ---------------------------------------------------------------------------
# Round 2 (restart): CI-evidence-aware ACs specific to THIS orchestration
# layer — AC-R2, AC-R3, AC-R6, AC-R15, AC-R16-adjacent (--manifest dry-run).
# ---------------------------------------------------------------------------


def test_forgery_hand_edited_coverage_with_no_ci_confirmation_never_promotes(tmp_path, monkeypatch):
    # AC-R2, the actual forgery test: the committed manifest CLAIMS 'ok'
    # coverage, but CI evidence is `unavailable` (never confirmed) -- must
    # skip, never promote on the committed file's own unverified claim.
    requirements = {"01::FR-01.01": _node("FR-01.01", coverage={"unit": "ok"})}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    monkeypatch.setattr(
        mod, "resolve_execution_evidence",
        lambda *a, **k: ExecutionEvidence("unavailable", "no qualifying run", None, None),
    )

    rc = mod.main(["--project-root", str(project)])
    assert rc == 0
    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "(inferred)" in spec  # never promoted
    assert not ledger_path(project).exists()


def test_confirmed_evidence_not_containing_this_fr_is_a_decided_skip_not_a_crash(tmp_path, monkeypatch):
    # AC-R3: evidence IS confirmed (a real, verified run), but this
    # particular FR is absent from what it confirmed (e.g. a brand-new FR
    # added after the artifact's own regen) -- treated exactly like "no
    # evidence yet," never a crash, never an escalation.
    requirements = {"01::FR-01.01": _node("FR-01.01", coverage={"unit": "ok"})}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    monkeypatch.setattr(
        mod, "resolve_execution_evidence",
        lambda *a, **k: ExecutionEvidence("confirmed", "test", 1, {}),  # empty -- FR not in it
    )

    rc = mod.main(["--project-root", str(project)])
    assert rc == 0
    assert "(inferred)" in (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert not ledger_path(project).exists()


def test_evidence_error_is_an_operational_failure_never_a_silent_skip_all(tmp_path, monkeypatch, capsys):
    # AC-R15 (blocking change 4b): `evidence.status == "error"` must exit 2
    # BEFORE plan_promotions ever runs -- never fall through to "everything
    # decided as skip" (indistinguishable from the honest `unavailable`
    # steady state).
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    monkeypatch.setattr(
        mod, "resolve_execution_evidence",
        lambda *a, **k: ExecutionEvidence("error", "the artifacts query timed out", None, None),
    )
    plan_promotions_called = []
    monkeypatch.setattr(
        mod, "plan_promotions",
        lambda *a, **k: plan_promotions_called.append(True) or (_ for _ in ()).throw(AssertionError("should not run")),
    )

    rc = mod.main(["--project-root", str(project)])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert "execution evidence could not be resolved" in out["error"]
    assert not plan_promotions_called
    assert not ledger_path(project).exists()


def test_manifest_override_is_dry_run_only_never_writes(tmp_path, monkeypatch, capsys):
    # AC-R6/Q3: `--manifest` is a read-only inspection override -- even when
    # the decision would be a clean promotion, nothing is ever written.
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)

    override_path = tmp_path / "override-manifest.json"
    override_path.write_text(
        json.dumps({"schema_version": 4, "requirements": requirements}), encoding="utf-8",
    )

    rc = mod.main(["--project-root", str(project), "--manifest", str(override_path)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True
    assert out["promoted"][0]["fr"] == "FR-01.01"
    # Nothing actually written, despite the report showing a would-be promotion.
    assert "(inferred)" in (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert not ledger_path(project).exists()


def test_default_run_never_reads_the_working_tree_manifest_file(tmp_path, monkeypatch):
    # AC-R6: the on-disk manifest is irrelevant by default -- only the
    # git-committed content at HEAD is ever evaluated. Corrupt the on-disk
    # copy AFTER committing a good one; the run must still succeed using the
    # committed (good) content.
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)

    (project / _MANIFEST_RELPATH).write_text("not even json", encoding="utf-8")

    rc = mod.main(["--project-root", str(project)])
    assert rc == 0
    assert "| unit |" in (project / _SPEC_RELPATH).read_text(encoding="utf-8")


def test_dry_run_with_a_corrupted_ledger_is_a_clean_operational_failure_not_a_traceback(
    tmp_path, monkeypatch, capsys,
):
    # External code review (glm/medium, P3.5 restart round 3): the dry-run
    # (`--manifest`) branch had no error wrapping around load_ledger/
    # plan_promotions, unlike the real-write path -- a corrupted ledger
    # escaped as a raw traceback instead of this CLI's documented
    # {"error": ...} exit-2 shape.
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)
    l_path = ledger_path(project)
    l_path.parent.mkdir(parents=True, exist_ok=True)
    l_path.write_text(json.dumps({
        "schema_version": 1,
        "decisions": {"FR-01.01": [{"action": "promoted", "decided_by": "tool",
                                     "required_layers": [None, "unit"], "reason": "x"}]},
    }), encoding="utf-8")

    override_path = tmp_path / "override-manifest.json"
    override_path.write_text(json.dumps({"schema_version": 4, "requirements": requirements}), encoding="utf-8")

    rc = mod.main(["--project-root", str(project), "--manifest", str(override_path)])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert "FR-01.01" in out["error"]


def test_dry_run_with_a_spec_path_escaping_the_project_root_is_a_clean_operational_failure(
    tmp_path, monkeypatch, capsys,
):
    # plan_promotions itself resolves each candidate FR's spec_path
    # (resolve_spec_path_within_root) before reading it -- a path escaping
    # the project root raises LayerCellWriteError there, the
    # dry-run-reachable half of this same error-wrapping fix (missing-file
    # is handled separately, non-fatally, inside plan_promotions itself).
    requirements = {"01::FR-01.01": _node("FR-01.01", spec_path="../../outside/spec.md")}
    project = _write_project(tmp_path, requirements, spec_rows="")
    _mock_evidence_from(monkeypatch, requirements)

    override_path = tmp_path / "override-manifest.json"
    override_path.write_text(json.dumps({"schema_version": 4, "requirements": requirements}), encoding="utf-8")

    rc = mod.main(["--project-root", str(project), "--manifest", str(override_path)])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert "could not read a spec.md" in out["error"]
