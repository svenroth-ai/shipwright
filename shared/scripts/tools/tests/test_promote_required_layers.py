"""Integration tests for ``promote_required_layers.py``'s process contract
(P3.5, campaign req3-04c-ac-identity-wave2): exit 0/3/other, ledger written
only for actual promotions, spec.md edited surgically, idempotent re-run.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.promote_required_layers as mod  # noqa: E402
from scripts.lib.fr_table_shape import FR_TABLE_HEADER, FR_TABLE_SEPARATOR  # noqa: E402
from scripts.lib.layer_promotion_ledger import ledger_path, load_ledger  # noqa: E402

_SPEC_RELPATH = ".shipwright/planning/01-adopted/spec.md"


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


def _write_project(tmp_path, requirements: dict, *, spec_rows: str):
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
    return tmp_path


def test_clean_promotion_exits_zero_writes_spec_and_ledger(tmp_path):
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | Does a thing. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)

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


def test_a_hand_annotated_cell_is_skipped_instead_of_silently_losing_the_annotation(tmp_path, capsys):
    # Medium finding, Stage-3 doubt-review round 2, P3.5 post-push round:
    # otherwise-promotable evidence with a hand-added annotation in the live
    # cell must be skipped, not have this CLI's rewrite silently delete it.
    # A non-canonical token ("db") in the still-inferred cell -- not a second
    # canonical layer name, so this exercises the NEW residual-content check
    # alone, not the pre-existing live_declared_layers widening. Stage-1
    # spec-review REJECTed an earlier version of this fix that reported this
    # as an escalation (exit 3, `layer_undeterminable`): the predicate
    # demonstrably HOLDS here, so it is not one of the spec's three named
    # undecidable cases, and that reason code's meaning did not match what
    # actually happened. A named skip (exit 0) reports the same protection
    # honestly instead.
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit, db (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)

    rc = mod.main(["--project-root", str(project)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["promoted"] == []
    assert out["escalated"] == []
    assert out["skipped"][0]["reason_code"] == "live_cell_has_residual_text"
    # The annotation survives untouched -- nothing was written at all.
    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "unit, db (inferred)" in spec
    assert not ledger_path(project).exists()


def test_no_eligible_fr_exits_zero_and_writes_nothing(tmp_path):
    requirements = {"01::FR-01.02": _node("FR-01.02", coverage={"unit": "MISSING"}, tests={})}
    row = "| FR-01.02 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)

    rc = mod.main(["--project-root", str(project)])
    assert rc == 0
    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "(inferred)" in spec
    assert not ledger_path(project).exists()


def test_undecidable_case_exits_three_and_reports_reason_code(tmp_path, capsys):
    # Two nodes sharing the SAME display id -> collision -> undeterminable.
    requirements = {
        "01::FR-01.01": _node("FR-01.01"),
        "02::FR-01.01": _node("FR-01.01", spec_path=_SPEC_RELPATH, status="removed"),
    }
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)

    rc = mod.main(["--project-root", str(project)])
    assert rc == 3
    out = json.loads(capsys.readouterr().out)
    assert out["escalated"][0]["reason_code"] == "layer_undeterminable"
    # A collision escalates instead of promoting -- nothing was written.
    assert out["promoted"] == []
    assert "(inferred)" in (project / _SPEC_RELPATH).read_text(encoding="utf-8")


def test_one_escalation_does_not_block_another_frs_clean_promotion(tmp_path):
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

    rc = mod.main(["--project-root", str(project)])
    assert rc == 3
    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "| FR-01.01 | Adopted | x | Must | y. | code | unit |" in spec
    assert "| FR-01.02 | Adopted | x | Must | y. | code | unit (inferred) |" in spec


def test_rerun_after_promotion_is_a_clean_noop(tmp_path):
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)

    assert mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-08-a"]) == 0
    spec_after_first = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    ledger_after_first = json.loads(ledger_path(project).read_text(encoding="utf-8"))

    assert mod.main(["--project-root", str(project), "--run-id", "iterate-2026-09-08-b"]) == 0
    assert (project / _SPEC_RELPATH).read_text(encoding="utf-8") == spec_after_first
    ledger_after_second = json.loads(ledger_path(project).read_text(encoding="utf-8"))
    assert ledger_after_second == ledger_after_first
    # already_explicit is a silent skip, not a second "promoted" entry.
    assert len(ledger_after_second["decisions"]["FR-01.01"]) == 1


def test_ledger_drift_after_manual_revert_escalates_on_rerun(tmp_path):
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
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
    # external code review (openai/medium + glm/high, P3.5 round 2 -- same
    # ordering property, automated-tool side): a ledger-write failure must
    # never leave a promoted cell behind with no durable record.
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    original_spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")

    def _boom(*a, **k):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(mod, "write_ledger", _boom)
    rc = mod.main(["--project-root", str(project)])
    assert rc == 2
    assert (project / _SPEC_RELPATH).read_text(encoding="utf-8") == original_spec
    assert not ledger_path(project).exists()


def test_demoted_fr_with_unchanged_evidence_is_a_clean_skip_writes_nothing(tmp_path):
    """"Exitable" (spec L25/L40, Stage-1 spec-review finding): the automated
    tool never overrides an operator's demoted decision -- and a veto
    recorded against evidence that still looks the SAME today is a clean,
    silent skip, not a forever-escalation against a decision already made."""
    import scripts.lib.layer_promotion_ledger as ledger_mod

    node = _node("FR-01.01")
    requirements = {"01::FR-01.01": node}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)

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


def test_demoted_fr_with_drifted_evidence_escalates_and_writes_nothing(tmp_path):
    """A genuinely NEW evidence state since the veto is exactly the case a
    permanent veto cannot have considered -- it escalates again (still never
    promoting on its own; only the human CLI may clear it), distinguishing
    "already vetoed, nothing changed" from "something changed since"."""
    import scripts.lib.layer_promotion_ledger as ledger_mod

    demoted_against = _node("FR-01.01", coverage={"unit": "MISSING"})
    requirements = {"01::FR-01.01": _node("FR-01.01")}  # coverage now "ok"
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)

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


def test_demoted_fr_with_evidence_drifted_toward_worse_is_a_clean_exit_zero_skip(tmp_path):
    """Drift alone is not enough (Stage-1 spec-review round 2): the fingerprint
    differs, but the drift is TOWARD worse evidence (green -> MISSING) -- the
    predicate does not hold now either, so this is the same plain decided
    skip it would be with no ledger entry at all, not a 4th, unnamed
    undecidable escalation over an FR the tool could never have promoted."""
    import scripts.lib.layer_promotion_ledger as ledger_mod

    demoted_against = _node("FR-01.01", coverage={"unit": "ok"})
    requirements = {"01::FR-01.01": _node("FR-01.01", coverage={"unit": "MISSING"})}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)

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


def test_stale_manifest_never_narrows_a_hand_declared_multi_layer_cell(tmp_path):
    """HIGH finding (Stage-3 doubt-review, P3.5 post-push round): the LIVE
    cell already hand-declares ``unit, e2e``, but the manifest is stale and
    still says ``required_layers: ["unit"]`` (ordinary snapshot lag -- this
    tool never regenerates the manifest). Only ``unit`` has fresh 'ok'
    coverage; ``e2e`` has no evidence at all. Before the fix this narrowed
    the cell to bare ``unit`` on promotion, silently dropping the
    hand-declared ``e2e``. After the fix, ``e2e`` is unioned into
    ``required_before``, so it is UNVERIFIED and the FR is a clean skip --
    nothing is written, and the hand-declared ``e2e`` survives untouched."""
    node = _node("FR-01.01", required_layers=["unit"])
    requirements = {"01::FR-01.01": node}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit, e2e (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)

    rc = mod.main(["--project-root", str(project)])
    assert rc == 0

    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "| unit, e2e (inferred) |" in spec
    assert not ledger_path(project).exists()


def test_requirement_with_no_spec_path_is_an_operational_failure(tmp_path, capsys):
    # external code review (glm/low, P3.5 round 3): fails loudly and
    # specifically here, not as a misattributed IsADirectoryError later.
    requirements = {"01::FR-01.01": _node("FR-01.01", spec_path="")}
    project = _write_project(tmp_path, requirements, spec_rows="")
    rc = mod.main(["--project-root", str(project)])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert "no spec_path" in out["error"]


def test_missing_manifest_is_an_operational_failure(tmp_path):
    (tmp_path / ".shipwright").mkdir()
    rc = mod.main(["--project-root", str(tmp_path)])
    assert rc == 2


def test_a_corrupted_ledger_required_layers_is_an_operational_failure(tmp_path, capsys):
    # Low 1, Stage-2 code-review, P3.5 post-push round: a hand-corrupted
    # `promoted` entry's `required_layers` (e.g. containing `null`) used to
    # pass `load_ledger_with_snapshot` unnoticed and only surface later as a
    # bare, uncaught `ValueError` out of `_canonical_layer_tokens` -- this
    # CLI-level test pins the fixed, normal JSON error shape (rc 2, an
    # "error" key), alongside the lib-level test that pins the underlying
    # `_parse_ledger` behavior directly (test_layer_promotion_ledger.py).
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
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
    # Low finding, Stage-3 doubt-review round 2, P3.5 post-push round:
    # `load_ledger_with_snapshot` calls `path.read_bytes()` after
    # `path.is_file()` -- a permissions error, or the path becoming a
    # directory between the two calls, is a real OSError this call site
    # previously did not catch (only ValueError), unlike every OTHER read
    # site in this mechanism. Fail-safe in outcome either way (nothing
    # written) -- this pins the error SHAPE: this CLI's normal JSON error
    # with an "error" key, not an uncaught traceback.
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)

    def _boom(*a, **k):
        raise OSError("simulated permission error")

    monkeypatch.setattr(mod, "load_ledger_with_snapshot", _boom)
    rc = mod.main(["--project-root", str(project)])
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert "simulated permission error" in out["error"]


def test_majority_escalating_adds_a_sweep_signal_warning_but_keeps_exit_three(tmp_path, capsys):
    # Two collisions (escalate) and one clean skip -- 2 of 3 is a majority.
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

    rc = mod.main(["--project-root", str(project)])
    assert rc == 3
    out = json.loads(capsys.readouterr().out)
    assert len(out["escalated"]) == 2
    assert "sweep_signal_warning" in out


def test_a_second_invocation_times_out_while_the_lock_is_held(tmp_path, monkeypatch):
    """Stage-4 doubt-review Medium finding, P3.5 post-push round -- the same
    hazard ``test_mint_ac_ids.py:198`` documents fixing once already in this
    repo: nothing previously exercised ``file_lock`` at all, so deleting the
    ``with file_lock(...):``/manual-enter wrapper around ``main()``'s
    locked span left every OTHER test in this file green. The timeout is
    monkeypatched down from the real 10s so this test stays fast."""
    monkeypatch.setattr(mod, "_LOCK_TIMEOUT_SECONDS", 0.2)
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
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

    # Nothing was written -- the lock was never acquired for this run.
    assert (project / _SPEC_RELPATH).read_text(encoding="utf-8") == original_spec
    assert not ledger_path(project).exists()


def test_an_exception_inside_the_locked_span_still_releases_the_lock(tmp_path, monkeypatch):
    """A body exception ``_plan_and_apply_locked`` does not itself catch (here
    a non-``ValueError`` failure reading the ledger) must not leave the lock
    held for a follow-up invocation.

    Mechanism-sensitive, not merely outcome-sensitive (Low finding, Stage-5
    code-review, P3.5 post-push round -- the original version of this test
    still passed with ``main()``'s ``finally: lock_cm.__exit__(...)`` deleted
    entirely, because ``file_lock`` is a ``@contextmanager`` generator and
    CPython's refcount-driven ``GeneratorExit`` finalization released the
    lock anyway once ``excinfo``/its traceback -- the only thing keeping
    ``lock_cm`` referenced -- went out of scope). ``excinfo`` stays bound
    (and therefore its traceback, and therefore ``main()``'s own ``lock_cm``
    local it chains through) THROUGH the follow-up call below: refcount GC
    of ``lock_cm`` cannot have run while it is still referenced, so only
    ``main()``'s own explicit ``finally`` can be what makes the follow-up
    succeed."""
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)

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
    """Medium finding, Stage-4 code-review, P3.5 post-push round:
    ``compute_promotion_writes``'s ``contents_by_path`` param (Stage-3
    doubt-review Medium fix) only closes the decide->write TOCTOU window
    because ``_plan_and_apply_locked`` PASSES ``plan_promotions``'s own
    already-read content through as the fold base -- reverting that call
    back to 2-arg leaves the rest of the suite green, because
    ``compute_promotion_writes`` would then re-read fresh (silently picking
    up the concurrent edit as its new "original") and
    ``write_promotion_files``'s later re-read-and-compare would find nothing
    to complain about. Simulates the edit landing in the exact gap
    ``contents_by_path`` closes by mutating the file from inside a wrapped
    ``plan_promotions`` -- after its own read, before the fold.

    Also pins the ledger-written/spec-unwritten ordering ("your call" item
    3, Stage-4 code-review): the ledger entry survives even though the
    spec.md write is refused -- ledger-before-spec.md (module docstring)
    means a write refused this late still leaves a durable record, and the
    NEXT run sees the live/ledger mismatch and escalates
    ``contradicts_recorded_decision`` instead of silently retrying.
    """
    requirements = {"01::FR-01.01": _node("FR-01.01")}
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    project = _write_project(tmp_path, requirements, spec_rows=row)
    spec_path = project / _SPEC_RELPATH

    real_plan_promotions = mod.plan_promotions

    def _plan_then_concurrently_edit(manifest, ledger, project_root):
        decisions, contents_by_path = real_plan_promotions(manifest, ledger, project_root)
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

    # The concurrent edit survives untouched -- the promotion write never landed.
    spec = spec_path.read_text(encoding="utf-8")
    assert "edited concurrently" in spec
    assert "(inferred)" in spec

    # But the ledger entry IS durable -- ledger-before-spec.md held even on
    # this late a refusal.
    ledger = load_ledger(ledger_path(project))
    entry = ledger["decisions"]["FR-01.01"][-1]
    assert entry["action"] == "promoted"
