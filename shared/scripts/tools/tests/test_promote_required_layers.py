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

**Round-3 post-push addition — the composition seam.** Every test above
monkeypatches ``mod.resolve_execution_evidence`` directly, and
``test_ci_execution_evidence.py`` separately mocks the REAL resolver's own
dependencies (``_gh_api``, ``_download_and_parse_artifact``) — so no test in
either file ever composed the real resolver's actual return value with the
real ``plan_promotions`` consumer. That composition gap is exactly what hid
a real production defect for three review rounds: ``plan_promotions`` looked
up CI evidence by a requirement node's bare ``id`` (``"FR-01.01"``) against a
dict the real resolver keys by the manifest's own namespaced top-level key
(``"01::FR-01.01"``) — a lookup that could never match, silently forcing
every FR through the "no evidence" branch regardless of what CI actually
confirmed. ``test_end_to_end_seam_between_the_real_resolver_and_plan_promotions``
below composes the two for real (mocking only the resolver's OWN external
dependencies) specifically to close that gap; see also the fixed
``_mock_evidence_from`` (now keyed the real namespaced way, not the bare
``id`` both sides previously agreed on) and
``test_ci_confirmed_evidence_overrides_a_greener_committed_claim`` /
its mirror, both of which would have failed red under the pre-fix lookup.
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
    exercising evidence-unavailable/error paths.

    Keyed by the MANIFEST key (``"01::FR-01.01"``, the real
    ``ci_execution_evidence.ExecutionEvidence.requirements`` contract —
    ``committed_manifest["requirements"]``'s own top-level keys), NOT by
    ``node["id"]`` (the node's bare display id). Round-3 post-push fix:
    this fixture previously keyed by ``node["id"]``, which matched an
    equally-wrong `plan_promotions` lookup by `fr_id` — the two wrongs
    canceled out and hid a real production defect (the lookup could never
    match against the REAL resolver's namespaced keys) from every test in
    this file for three review rounds. See
    ``test_end_to_end_seam_between_the_real_resolver_and_plan_promotions``
    below for the regression pin that composes the real resolver instead of
    this mock."""
    ci_map = {
        manifest_key: {"tests": node.get("tests") or {}, "coverage": node.get("coverage") or {}}
        for manifest_key, node in requirements.items()
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


def test_an_id_less_active_node_is_excluded_not_a_raw_traceback(tmp_path, monkeypatch):
    # Round-4 post-push doubt-review fix, low: `plan_promotions` dereferences
    # `node["id"]` unguarded -- a hand-corrupted committed manifest (never
    # something this tool itself writes) carrying an ACTIVE requirement node
    # with no `id` field, or a non-string one, must not escape as a raw
    # KeyError/AttributeError. `_active_requirements` now excludes it, the
    # same treatment a structurally-invalid (non-dict) node already gets --
    # the run completes cleanly and the OTHER, well-formed FR is unaffected.
    clean = _node("FR-01.01")
    corrupted = _node("FR-01.02")
    del corrupted["id"]
    requirements = {"01::FR-01.01": clean, "01::FR-01.02": corrupted}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements)

    rc = mod.main(["--project-root", str(project)])
    assert rc == 0
    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "| FR-01.01 | Adopted | x | Must | y. | code | unit |" in spec


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


def test_demoted_fr_with_raw_evidence_noise_but_same_derived_facts_stays_a_clean_skip(tmp_path, monkeypatch):
    # Round-4 post-push doubt-review fix, HIGH regression pin -- composed
    # through the REAL seam (both writers, not two separate mocks): the
    # operator demoted against one RAW evidence snapshot; a later automated
    # run's CI evidence carries DIFFERENT raw `tests` link content
    # (simulating OS/marker-selection variance -- a different test collected
    # this run) but the SAME derived facts (still exactly one "ok" unit
    # layer, nothing bound-but-absent). Before the fix the two writers'
    # fingerprints were built from structurally different bases (committed
    # manifest vs. CI-sourced) and so NEVER agreed regardless of whether the
    # evidence had genuinely moved, re-escalating REASON_CONTRADICTS_DECISION
    # on every single run. After the fix, unchanged derived facts stay a
    # clean, exitable skip.
    import scripts.lib.layer_promotion_ledger as ledger_mod

    demoted_against = _node("FR-01.01")  # tests: [t::unit], coverage: unit=ok
    noisy_now = _node("FR-01.01", tests={"unit": [
        _link(layer="unit"),
        {"id": "t::unit-2", "path": "t::unit-2", "layer": "unit", "status": "enabled", "executed": "pass"},
    ]})
    # Sanity check the fixture actually exercises "different raw content,
    # same derived facts" -- if this ever stopped holding the test below
    # would pass for the wrong reason (no real drift to distinguish).
    assert demoted_against["tests"] != noisy_now["tests"]
    assert ledger_mod.evidence_fingerprint(demoted_against) == ledger_mod.evidence_fingerprint(noisy_now)

    requirements = {"01::FR-01.01": noisy_now}
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

    def _plan_then_concurrently_edit(manifest, ledger, project_root, evidence, **kwargs):
        decisions, contents_by_path = real_plan_promotions(manifest, ledger, project_root, evidence, **kwargs)
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


def test_ci_confirmed_evidence_overrides_a_greener_committed_claim(tmp_path, monkeypatch):
    # CI evidence CONTRADICTS the committed manifest in the GREENER
    # direction: the committed file claims MISSING coverage / no tests (it
    # would never promote on its own), but CI actually confirmed real
    # passing coverage for this exact commit. The decision must follow CI,
    # not the committed file's own conservative/stale claim -- proving
    # REPLACE-never-merge actually READS the CI map, not merely ignores the
    # committed claim. Round-3 post-push regression pin (code-reviewer
    # HIGH): under the key-mismatch bug this fixture exercises
    # (`ci_by_fr.get(fr_id)` looked up against a dict keyed by the manifest
    # key), `ci_node` was always `None` regardless of what CI actually
    # confirmed, so this promotion would never have happened -- this test
    # is red under that lookup and green only under the fix.
    requirements = {
        "01::FR-01.01": _node("FR-01.01", coverage={"unit": "MISSING"}, tests={"unit": []}),
    }
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    ci_map = {
        "01::FR-01.01": {"coverage": {"unit": "ok"}, "tests": {"unit": [_link(layer="unit")]}},
    }
    monkeypatch.setattr(
        mod, "resolve_execution_evidence",
        lambda *a, **k: ExecutionEvidence("confirmed", "test", 999, ci_map),
    )

    rc = mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-09-p3-5-test"])
    assert rc == 0
    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "| unit |" in spec
    assert "(inferred)" not in spec
    ledger = load_ledger(ledger_path(project))
    assert ledger["decisions"]["FR-01.01"][-1]["action"] == "promoted"


def test_ci_confirmed_evidence_overrides_a_committed_claim_that_was_too_optimistic(tmp_path, monkeypatch):
    # Mirror of the test above: the committed file claims GREEN coverage
    # ('ok'), but CI actually confirmed MISSING coverage / no tests for this
    # FR. Must skip, matching CI's weaker state -- never promote on the
    # committed file's own rosier, unverified claim. This is AC-R2's forgery
    # test in the CONFIRMED-but-disagreeing shape (CI ran and disagrees),
    # distinct from the `unavailable` shape
    # `test_forgery_hand_edited_coverage_with_no_ci_confirmation_never_promotes`
    # already covers (CI never ran at all).
    requirements = {
        "01::FR-01.01": _node("FR-01.01", coverage={"unit": "ok"}, tests={"unit": [_link(layer="unit")]}),
    }
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    ci_map = {
        "01::FR-01.01": {"coverage": {"unit": "MISSING"}, "tests": {"unit": []}},
    }
    monkeypatch.setattr(
        mod, "resolve_execution_evidence",
        lambda *a, **k: ExecutionEvidence("confirmed", "test", 999, ci_map),
    )

    rc = mod.main(["--project-root", str(project)])
    assert rc == 0
    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "(inferred)" in spec  # never promoted on the committed file's own optimistic claim
    assert not ledger_path(project).exists()


def test_end_to_end_seam_between_the_real_resolver_and_plan_promotions(tmp_path, monkeypatch):
    """Composes the REAL ``resolve_execution_evidence`` (mocking only ITS
    OWN external dependencies -- ``resolve_ci_verification``, ``_gh_api``,
    ``_download_and_parse_artifact``, ``github_api.owner_repo`` -- never
    ``mod.resolve_execution_evidence`` itself) with the REAL
    ``plan_promotions``, asserting a real promotion happens end-to-end. See
    the module docstring's "Round-3 post-push addition" note: this is the
    test that should have existed from round 1 and would have caught the
    key-mismatch defect immediately -- every other test in this file (and in
    ``test_ci_execution_evidence.py``) mocks one side or the other of this
    exact seam."""
    # DELIBERATELY the bare-named module object, not `scripts.ci_execution_
    # evidence` (this file's own top-level import) -- round-4 post-push
    # doubt-review fix, low, ADR-045-class hazard. `mod` (`promote_required_
    # layers.py`) does its OWN `sys.path.insert` + bare `from
    # ci_execution_evidence import ...`, which registers a SEPARATE
    # `sys.modules["ci_execution_evidence"]` entry from this test file's
    # package-qualified `sys.modules["scripts.ci_execution_evidence"]` --
    # two distinct module objects for the same source file. A monkeypatch
    # on the package-qualified one (the "normal", more obvious way to write
    # this) would silently never reach `mod`'s own calls into it, and this
    # seam test would pass for the wrong reason (or not exercise the real
    # code path at all). Do not "simplify" this back to a normal
    # `monkeypatch.setattr(m, ...)` shape without re-verifying which module
    # object `mod` itself actually holds a reference to.
    cee = sys.modules["ci_execution_evidence"]
    from ci_provenance import CIVerification  # noqa: PLC0415 - same bare-name module `cee` itself imports

    requirements = {
        "01::FR-01.01": _node("FR-01.01", coverage={"unit": "MISSING"}, tests={"unit": []}),
    }
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)

    committed_manifest = json.loads((project / _MANIFEST_RELPATH).read_text(encoding="utf-8"))
    head_sha = _git(project, "rev-parse", "HEAD").strip()
    artifact = json.loads(json.dumps(committed_manifest))  # deep copy via round-trip
    artifact["source_commit"] = head_sha
    artifact["requirements"]["01::FR-01.01"]["coverage"] = {"unit": "ok"}
    artifact["requirements"]["01::FR-01.01"]["tests"] = {"unit": [_link(layer="unit")]}

    monkeypatch.setattr(cee, "resolve_ci_verification", lambda *a, **k: CIVerification("verified", "confirmed", 999))
    monkeypatch.setattr(
        cee, "_gh_api",
        lambda path, *, cwd: {"artifacts": [
            {"name": cee.EXECUTION_EVIDENCE_ARTIFACT_NAME, "expired": False,
             "id": 1, "created_at": "2026-09-09T10:00:00Z"},
        ]},
    )
    monkeypatch.setattr(cee, "_download_and_parse_artifact", lambda artifact_id, *, owner, repo, cwd: (artifact, None))
    monkeypatch.setattr(cee.github_api, "owner_repo", lambda project_root: "acme/foo")

    rc = mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-09-p3-5-seam-test"])
    assert rc == 0
    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "| unit |" in spec
    assert "(inferred)" not in spec
    ledger = load_ledger(ledger_path(project))
    entry = ledger["decisions"]["FR-01.01"][-1]
    assert entry["action"] == "promoted"
    assert entry["ci_run_id"] == 999


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


# --- P3.4c: anchor-to-newest-verified-ancestor fallback --------------------
#
# These tests build a REAL two-commit repo (anchor commit, then HEAD) so the
# `git diff`-based staleness guard runs against real git behavior, but mock
# both `mod.resolve_verified_anchor` (the `gh`-boundary seam this tool's own
# `main()` calls directly) and `mod.resolve_execution_evidence` (dispatched
# by WHICH commit it is asked about, since both the tip's own attempt and
# the anchor's fall-back attempt call the exact same patched name).


def _mock_anchor_and_evidence(monkeypatch, *, anchor_status, anchor_commit=None, anchor_depth=None,
                               head_evidence_status="unavailable", anchor_requirements=None, anchor_run_id=999,
                               anchor_evidence_status="confirmed"):
    """Wires ``mod.resolve_verified_anchor`` to a canned outcome and
    ``mod.resolve_execution_evidence`` to answer per-commit: ``unavailable``
    for HEAD (the trigger for the fallback), ``anchor_evidence_status`` (from
    ``anchor_requirements`` when ``confirmed``) for ``anchor_commit`` —
    mirroring ``_mock_evidence_from``'s own manifest-key-namespaced shape.
    ``anchor_evidence_status`` lets a caller exercise the anchor's OWN
    ``error``/``unavailable`` outcomes distinctly from ``confirmed``."""
    from scripts.ci_verified_anchor import VerifiedAnchor

    monkeypatch.setattr(
        mod, "resolve_verified_anchor",
        lambda head_commit, **kw: VerifiedAnchor(anchor_status, "test", anchor_commit, anchor_depth),
    )

    def fake_resolve_execution_evidence(commit, *, committed_manifest, project_root):
        if commit == anchor_commit and anchor_requirements is not None:
            if anchor_evidence_status != "confirmed":
                return ExecutionEvidence(anchor_evidence_status, "test", None, None)
            ci_map = {
                key: {"tests": node.get("tests") or {}, "coverage": node.get("coverage") or {}}
                for key, node in anchor_requirements.items()
            }
            return ExecutionEvidence("confirmed", "test", anchor_run_id, ci_map)
        return ExecutionEvidence(head_evidence_status, "test", None, None)

    monkeypatch.setattr(mod, "resolve_execution_evidence", fake_resolve_execution_evidence)


def test_anchor_promotion_succeeds_when_nothing_invalidating_changed_since_the_anchor(tmp_path, monkeypatch):
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | Does a thing. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    anchor_sha = _git(project, "rev-parse", "HEAD").strip()

    # HEAD moves on with an UNRELATED change -- never touching the bound
    # test file (`t::unit`, per `_link`'s fixed id/path) or spec.md.
    (project / "unrelated.txt").write_text("x", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "unrelated change")

    _mock_anchor_and_evidence(
        monkeypatch, anchor_status="found", anchor_commit=anchor_sha, anchor_depth=1,
        anchor_requirements=requirements,
    )

    rc = mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-10-p34c-test"])
    assert rc == 0

    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "| unit |" in spec
    assert "(inferred)" not in spec

    ledger = load_ledger(ledger_path(project))
    entry = ledger["decisions"]["FR-01.01"][-1]
    assert entry["action"] == "promoted"
    assert entry["ci_run_id"] == 999
    assert entry["anchor_commit"] == anchor_sha


def test_anchor_promotion_is_refused_when_a_bound_test_file_changed_since_the_anchor(tmp_path, monkeypatch):
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | Does a thing. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)

    # `_link(layer="unit")` binds `t::unit` (both `id` and `path`) -- create
    # and then MODIFY that exact path between the anchor and HEAD, the
    # precise "a bound test moved/changed" case the guard exists to catch.
    (project / "t").write_text("original", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "add bound test file")
    anchor_sha = _git(project, "rev-parse", "HEAD").strip()
    (project / "t").write_text("changed", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "touch the bound test file")

    _mock_anchor_and_evidence(
        monkeypatch, anchor_status="found", anchor_commit=anchor_sha, anchor_depth=1,
        anchor_requirements=requirements,
    )

    rc = mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-10-p34c-test"])
    assert rc == 0

    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "(inferred)" in spec  # untouched -- never promoted

    ledger = load_ledger(ledger_path(project))
    assert "FR-01.01" not in ledger["decisions"]


def test_anchor_promotion_reports_stale_reason_code_in_the_result(tmp_path, monkeypatch, capsys):
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | Does a thing. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    (project / "t").write_text("original", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "add bound test file")
    anchor_sha = _git(project, "rev-parse", "HEAD").strip()
    (project / "t").write_text("changed", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "touch the bound test file")

    _mock_anchor_and_evidence(
        monkeypatch, anchor_status="found", anchor_commit=anchor_sha, anchor_depth=1,
        anchor_requirements=requirements,
    )

    rc = mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-10-p34c-test"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["skipped"]) == 1
    assert out["skipped"][0]["fr"] == "FR-01.01"
    assert out["skipped"][0]["action"] == "skip"
    assert out["skipped"][0]["reason_code"] == "evidence_stale_since_anchor"


def test_anchor_promotion_is_refused_when_only_the_head_spec_path_changed(tmp_path, monkeypatch):
    # Regression pin for external review (openai/high + glm/low): the FR's
    # spec_path itself moved to a DIFFERENT spec.md between the anchor and
    # HEAD, while nothing else (the bound test file, the OLD spec.md)
    # changed at all. Promoting here would write into the NEW spec.md using
    # evidence from a CI run that only ever covered the OLD one.
    old_spec_relpath = _SPEC_RELPATH
    new_spec_relpath = ".shipwright/planning/01-adopted/spec-moved.md"
    row = "| FR-01.01 | Adopted | x | Must | Does a thing. | code | unit (inferred) |"

    requirements = {"01::FR-01.01": _node("FR-01.01", spec_path=old_spec_relpath)}
    project = _write_project(tmp_path, requirements, spec_rows=row)
    anchor_sha = _git(project, "rev-parse", "HEAD").strip()

    # HEAD: the FR's spec_path moves to a new file (added, never covered by
    # the anchor's CI run); the bound test file (`t::unit`) never changes.
    (project / ".shipwright" / "planning" / "01-adopted" / "spec-moved.md").write_text(
        "\n".join([
            "# Spec", "", "## Functional Requirements", "",
            FR_TABLE_HEADER, FR_TABLE_SEPARATOR, row, "",
        ]),
        encoding="utf-8",
    )
    manifest_path = project / _MANIFEST_RELPATH
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["requirements"]["01::FR-01.01"]["spec_path"] = new_spec_relpath
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "move FR-01.01 to a new spec.md")

    _mock_anchor_and_evidence(
        monkeypatch, anchor_status="found", anchor_commit=anchor_sha, anchor_depth=1,
        anchor_requirements=requirements,
    )

    rc = mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-10-p34c-test"])
    assert rc == 0

    new_spec = (project / new_spec_relpath).read_text(encoding="utf-8")
    assert "(inferred)" in new_spec  # never promoted into the NEW spec.md

    ledger = load_ledger(ledger_path(project))
    assert "FR-01.01" not in ledger["decisions"]


def test_anchor_promotion_is_refused_when_the_bound_test_set_changed_at_head(tmp_path, monkeypatch):
    # Regression pin for external plan review (glm/medium + openai/high,
    # both independently): the FR's traceability BINDING itself changed
    # between the anchor and HEAD -- a second test newly bound to this FR --
    # without either bound file's own bytes ever changing, so it never shows
    # up in `git diff --name-only` at all. The guard must catch this via a
    # direct anchor-vs-HEAD bound-set comparison, not just the file diff.
    anchor_requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | Does a thing. | code | unit (inferred) |"
    project = _write_project(tmp_path, anchor_requirements, spec_rows=row)
    anchor_sha = _git(project, "rev-parse", "HEAD").strip()

    # HEAD: FR-01.01 gains a SECOND bound test link -- an unrelated file
    # never touched on disk, so it is invisible to the git diff.
    manifest_path = project / _MANIFEST_RELPATH
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["requirements"]["01::FR-01.01"]["tests"]["unit"].append(
        {"id": "extra::unit", "path": "extra::unit", "layer": "unit", "status": "enabled", "executed": "pass"},
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "bind a second test to FR-01.01")

    _mock_anchor_and_evidence(
        monkeypatch, anchor_status="found", anchor_commit=anchor_sha, anchor_depth=1,
        anchor_requirements=anchor_requirements,
    )

    rc = mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-10-p34c-test"])
    assert rc == 0

    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "(inferred)" in spec  # never promoted

    ledger = load_ledger(ledger_path(project))
    assert "FR-01.01" not in ledger["decisions"]


def test_anchor_promotion_is_refused_when_a_new_test_file_is_unaccounted_for_in_any_manifest(
    tmp_path, monkeypatch,
):
    # Stage-3 doubt review, high: the concrete non-adversarial failure the
    # doubt reviewer named directly. A new test file is added at HEAD (a
    # real e2e test for FR-01.01, tagged in the codebase) but the committed
    # manifest was never regenerated to record it as bound -- the exact
    # "drifted, unregenerated HEAD manifest" state this whole mechanism
    # exists to operate in. Without the unaccounted-test-file widening, the
    # binding-drift check sees no difference (HEAD's stale manifest still
    # matches the anchor's), and the new file never appears in the
    # invalidating set (nothing ever recorded it as bound to anything) --
    # this FR would silently promote on evidence that never covered it.
    anchor_requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | Does a thing. | code | unit (inferred) |"
    project = _write_project(tmp_path, anchor_requirements, spec_rows=row)
    anchor_sha = _git(project, "rev-parse", "HEAD").strip()

    # HEAD: a genuinely new test file lands on disk, but nobody re-ran the
    # manifest regeneration -- the committed manifest is byte-identical to
    # the anchor's.
    (project / "tests").mkdir(parents=True, exist_ok=True)
    (project / "tests" / "test_fr_01_01_e2e.py").write_text(
        "def test_fr_01_01_covers_the_new_flow():\n    assert True\n", encoding="utf-8",
    )
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "add a new e2e test (manifest not regenerated)")

    _mock_anchor_and_evidence(
        monkeypatch, anchor_status="found", anchor_commit=anchor_sha, anchor_depth=1,
        anchor_requirements=anchor_requirements,
    )

    rc = mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-10-p34c-test"])
    assert rc == 0

    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "(inferred)" in spec  # never promoted

    ledger = load_ledger(ledger_path(project))
    assert "FR-01.01" not in ledger["decisions"]


def test_no_verified_ancestor_within_the_bound_reports_unavailable_not_error(tmp_path, monkeypatch):
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | Does a thing. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)

    _mock_anchor_and_evidence(monkeypatch, anchor_status="unavailable")

    rc = mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-10-p34c-test"])
    assert rc == 0  # never an operational failure

    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "(inferred)" in spec  # never promoted

    ledger = load_ledger(ledger_path(project))
    assert "FR-01.01" not in ledger["decisions"]


def test_a_query_error_walking_the_anchor_degrades_to_unavailable_not_exit_2(tmp_path, monkeypatch):
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | Does a thing. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)

    _mock_anchor_and_evidence(monkeypatch, anchor_status="error")

    rc = mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-10-p34c-test"])
    assert rc == 0


def test_a_local_git_fault_reading_the_anchors_manifest_degrades_not_exit_2(tmp_path, monkeypatch):
    # Regression pin for code-reviewer/medium: a `ManifestReadError` on the
    # anchor's OWN manifest read (pure local git plumbing on an optional,
    # best-effort path) must degrade to the tip's original `unavailable`,
    # never exit 2 -- there is a perfectly good fallback already in hand
    # (give up on the anchor, not on the run).
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | Does a thing. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    anchor_sha = _git(project, "rev-parse", "HEAD").strip()
    (project / "unrelated.txt").write_text("x", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "unrelated change")

    _mock_anchor_and_evidence(
        monkeypatch, anchor_status="found", anchor_commit=anchor_sha, anchor_depth=1,
        anchor_requirements=requirements,
    )
    # `mod.ManifestReadError`, not a fresh `scripts.lib.manifest_at_commit`
    # import -- ADR-044/045's package-collision gotcha means those are two
    # DIFFERENT class objects (`mod` imports it via bare `lib.`, this test
    # module via the `scripts.` prefix), so raising the latter would not be
    # caught by `mod`'s own `except ManifestReadError`.
    real_read_manifest_at_commit = mod.read_manifest_at_commit

    def _fail_only_for_the_anchor(project_root, sha, **kw):
        if sha == anchor_sha:
            raise mod.ManifestReadError("simulated local git fault reading the anchor's manifest")
        return real_read_manifest_at_commit(project_root, sha, **kw)

    monkeypatch.setattr(mod, "read_manifest_at_commit", _fail_only_for_the_anchor)

    rc = mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-10-p34c-test"])
    assert rc == 0  # never an operational failure

    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "(inferred)" in spec  # never promoted -- the anchor was abandoned

    ledger = load_ledger(ledger_path(project))
    assert "FR-01.01" not in ledger["decisions"]


def test_a_local_git_fault_diffing_anchor_to_head_degrades_not_exit_2(tmp_path, monkeypatch):
    # Regression pin for code-reviewer/medium: `changed_paths_between`
    # returning `None` (a local `git diff` fault, not a data problem) must
    # also degrade rather than exit 2, for the same reason as the manifest
    # read above.
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | Does a thing. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    anchor_sha = _git(project, "rev-parse", "HEAD").strip()
    (project / "unrelated.txt").write_text("x", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "unrelated change")

    _mock_anchor_and_evidence(
        monkeypatch, anchor_status="found", anchor_commit=anchor_sha, anchor_depth=1,
        anchor_requirements=requirements,
    )
    monkeypatch.setattr(mod, "changed_paths_between", lambda *a, **k: None)

    rc = mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-10-p34c-test"])
    assert rc == 0  # never an operational failure

    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "(inferred)" in spec  # never promoted -- the anchor was abandoned

    ledger = load_ledger(ledger_path(project))
    assert "FR-01.01" not in ledger["decisions"]


def test_the_anchors_own_evidence_erroring_degrades_not_exit_2(tmp_path, monkeypatch):
    # Stage-3 doubt review, medium (reversed from an earlier round of this
    # same fix): `resolve_execution_evidence`'s `error` status is not
    # reliably a content-binding/integrity signal -- most of its `error`
    # returns are plain transient/operational download faults, and treating
    # them as fatal made a best-effort fallback into a new, self-repeating
    # exit-2 for the SAME anchor commit on every run until it ages out of
    # the walk's bound. Degrades the same way the two git-plumbing faults
    # above do -- give up on the anchor, not on the run.
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | Does a thing. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    anchor_sha = _git(project, "rev-parse", "HEAD").strip()
    (project / "unrelated.txt").write_text("x", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "unrelated change")

    _mock_anchor_and_evidence(
        monkeypatch, anchor_status="found", anchor_commit=anchor_sha, anchor_depth=1,
        anchor_requirements=requirements, anchor_evidence_status="error",
    )

    rc = mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-10-p34c-test"])
    assert rc == 0

    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "(inferred)" in spec  # never promoted


def test_the_anchors_own_evidence_staying_unavailable_falls_through_cleanly(tmp_path, monkeypatch):
    # A genuinely found, verified anchor whose OWN execution evidence is
    # simply not yet available (no artifact, not an error) must fall
    # through to the tip's original `unavailable` -- never a promotion,
    # never an exit-2, and `resolve_verified_anchor` must not be consulted
    # again beyond this one candidate (the walk itself already exhausted
    # per `anchor_status`, tested separately in test_ci_verified_anchor.py).
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | Does a thing. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    anchor_sha = _git(project, "rev-parse", "HEAD").strip()
    (project / "unrelated.txt").write_text("x", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "unrelated change")

    _mock_anchor_and_evidence(
        monkeypatch, anchor_status="found", anchor_commit=anchor_sha, anchor_depth=1,
        anchor_requirements=requirements, anchor_evidence_status="unavailable",
    )

    rc = mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-10-p34c-test"])
    assert rc == 0

    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "(inferred)" in spec  # never promoted

    ledger = load_ledger(ledger_path(project))
    assert "FR-01.01" not in ledger["decisions"]


def test_tip_is_verified_never_triggers_the_anchor_fallback_at_all(tmp_path, monkeypatch):
    # AC4: the existing tip-is-verified path promotes IDENTICALLY -- proven
    # here by making `resolve_verified_anchor` explode if it is ever called.
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | Does a thing. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    _mock_evidence_from(monkeypatch, requirements, run_id=34316980804)

    def _boom(*a, **k):
        raise AssertionError("resolve_verified_anchor must not be called when the tip is verified")

    monkeypatch.setattr(mod, "resolve_verified_anchor", _boom)

    rc = mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-10-p34c-test"])
    assert rc == 0

    ledger = load_ledger(ledger_path(project))
    entry = ledger["decisions"]["FR-01.01"][-1]
    assert entry["action"] == "promoted"
    # No anchor fallback ran -- the commit evidence was resolved against IS
    # the promoted commit itself.
    head_sha = _git(project, "rev-parse", "HEAD").strip()
    assert entry["anchor_commit"] == head_sha
