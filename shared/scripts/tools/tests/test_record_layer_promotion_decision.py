"""Tests for the HUMAN-ONLY escalation/demotion recorder (P3.5).

``promote_required_layers.py`` never calls anything in this module and this
module never calls anything that would let the automated tool exercise a
``demoted`` action or override a prior decision — see both modules'
docstrings.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.record_layer_promotion_decision as mod  # noqa: E402
from scripts.lib.fr_table_shape import FR_TABLE_HEADER, FR_TABLE_SEPARATOR  # noqa: E402
from scripts.lib.layer_promotion_ledger import ledger_path, load_ledger  # noqa: E402

_SPEC_RELPATH = ".shipwright/planning/01-adopted/spec.md"


def _write_project(tmp_path, *, fr_id="FR-01.11", layers_cell="unit (inferred)"):
    manifest = {
        "schema_version": 4,
        "requirements": {
            f"01::{fr_id}": {
                "id": fr_id, "spec_path": _SPEC_RELPATH, "status": "active",
                "coverage": {"unit": "ok"}, "tests": {},
            },
        },
    }
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "compliance" / "test-traceability.json").write_text(
        json.dumps(manifest), encoding="utf-8",
    )
    spec_dir = tmp_path / ".shipwright" / "planning" / "01-adopted"
    spec_dir.mkdir(parents=True, exist_ok=True)
    doc = "\n".join([
        "# Spec", "", "## Functional Requirements", "",
        FR_TABLE_HEADER, FR_TABLE_SEPARATOR,
        f"| {fr_id} | Adopted | x | Must | y. | code | {layers_cell} |",
        "",
    ])
    (spec_dir / "spec.md").write_text(doc, encoding="utf-8")
    return tmp_path


def test_ledger_write_failure_leaves_spec_md_untouched(tmp_path, monkeypatch):
    # external code review (openai/medium + glm/high, P3.5 round 2): ledger
    # must land before spec.md -- a ledger-write failure must never leave an
    # explicit cell with no durable record behind it.
    project = _write_project(tmp_path)
    original_spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")

    def _boom(*a, **k):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(mod, "write_ledger", _boom)
    with pytest.raises(OSError):
        mod.main([
            "--project-root", str(project), "--fr-id", "FR-01.11", "--action", "promoted",
            "--required-layers", "unit", "--reason", "x",
        ])
    assert (project / _SPEC_RELPATH).read_text(encoding="utf-8") == original_spec


def test_an_os_error_reading_the_ledger_is_a_named_systemexit_not_a_traceback(
    tmp_path, monkeypatch,
):
    # Low finding, Stage-3 doubt-review round 2, P3.5 post-push round: same
    # fix as promote_required_layers.py's matching call site -- `load_ledger_
    # with_snapshot` calls `path.read_bytes()` after `path.is_file()`, so an
    # OSError (a permissions error, or the path becoming a directory between
    # the two calls) previously escaped uncaught instead of this CLI's
    # normal SystemExit shape.
    project = _write_project(tmp_path)

    def _boom(*a, **k):
        raise OSError("simulated permission error")

    monkeypatch.setattr(mod, "load_ledger_with_snapshot", _boom)
    with pytest.raises(SystemExit, match="simulated permission error"):
        mod.main([
            "--project-root", str(project), "--fr-id", "FR-01.11", "--action", "demoted",
            "--reason", "x",
        ])


def test_promoted_action_writes_spec_and_ledger(tmp_path):
    project = _write_project(tmp_path)
    rc = mod.main([
        "--project-root", str(project), "--fr-id", "FR-01.11", "--action", "promoted",
        "--required-layers", "unit,integration", "--reason", "operator reviewed directly",
        "--escalation-reason-code", "layer_undeterminable",
    ])
    assert rc == 0
    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "| unit, integration |" in spec
    ledger = load_ledger(ledger_path(project))
    entry = ledger["decisions"]["FR-01.11"][-1]
    assert entry["decided_by"] == "operator"
    assert entry["action"] == "promoted"
    assert entry["required_layers"] == ["unit", "integration"]
    assert entry["escalation_reason_code"] == "layer_undeterminable"


def test_promoted_action_with_missing_spec_path_is_rejected_by_name(tmp_path):
    # Low finding, Stage-5 code-review, P3.5 post-push round: mirrors
    # layer_promotion_apply.compute_promotion_writes's own named rejection
    # -- an empty spec_path resolves to the project root, and indexing
    # `node["spec_path"]` directly would otherwise raise a raw
    # IsADirectoryError instead of naming the actual problem.
    manifest_path = tmp_path / ".shipwright" / "compliance" / "test-traceability.json"
    project = _write_project(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["requirements"]["01::FR-01.11"]["spec_path"] = ""
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SystemExit, match="no spec_path"):
        mod.main([
            "--project-root", str(project), "--fr-id", "FR-01.11", "--action", "promoted",
            "--required-layers", "unit", "--reason", "x",
        ])


def test_promoted_action_on_a_deleted_spec_md_fails_with_a_named_error(tmp_path):
    # Low finding, Stage-5 code-review, P3.5 post-push round: the promoted
    # branch only caught LayerCellWriteError, unlike its sibling demoted
    # branch (which already catches OSError too) -- a deleted spec.md raised
    # a raw FileNotFoundError instead of this CLI's normal SystemExit shape.
    # `match=` (Low 3, Stage-2 code-review, P3.5 post-push round) actually
    # pins the NAMED part this test's own title claims, mirroring its
    # `no spec_path` sibling two lines up -- without it this test still
    # catches the regression (a bare FileNotFoundError is not a SystemExit
    # at all) but does not confirm the CLI's error names the real file.
    project = _write_project(tmp_path)
    (project / _SPEC_RELPATH).unlink()

    with pytest.raises(SystemExit, match="spec.md"):
        mod.main([
            "--project-root", str(project), "--fr-id", "FR-01.11", "--action", "promoted",
            "--required-layers", "unit", "--reason", "x",
        ])


def test_demoted_action_never_touches_spec_md(tmp_path):
    project = _write_project(tmp_path)
    original_spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    rc = mod.main([
        "--project-root", str(project), "--fr-id", "FR-01.11", "--action", "demoted",
        "--reason", "evidence is misleading for a reason the manifest can't show",
    ])
    assert rc == 0
    assert (project / _SPEC_RELPATH).read_text(encoding="utf-8") == original_spec
    ledger = load_ledger(ledger_path(project))
    assert ledger["decisions"]["FR-01.11"][-1]["action"] == "demoted"


def test_demoted_action_on_an_already_explicit_fr_reverts_the_cell_to_inferred(tmp_path):
    # HIGH finding (Stage-3 doubt-review, P3.5 post-push round): demoting an
    # FR whose live cell is already explicit must not leave it explicit
    # forever -- evaluate_fr's demoted-branch `already_explicit` arm has no
    # exitability qualifier, so a live explicit cell would re-escalate
    # `contradicts_recorded_decision` on every future run with no way to
    # clear it. The CLI must revert the cell to `(inferred)` instead.
    project = _write_project(tmp_path, layers_cell="unit, integration")
    rc = mod.main([
        "--project-root", str(project), "--fr-id", "FR-01.11", "--action", "demoted",
        "--reason", "evidence looked green but was misleading; this was a mistake to promote",
    ])
    assert rc == 0
    spec = (project / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "| unit, integration (inferred) |" in spec
    ledger = load_ledger(ledger_path(project))
    entry = ledger["decisions"]["FR-01.11"][-1]
    assert entry["action"] == "demoted"

    # And the wall is actually gone: `evaluate_fr` now sees a non-explicit
    # cell for this FR, so a fresh evaluation is a plain, exitable
    # `demoted_consistent` skip -- never a forever escalation.
    from scripts.lib.layer_promotion import SKIP_DEMOTED_CONSISTENT, evaluate_fr

    node = {
        "id": "FR-01.11", "required_layers_source": "inferred_legacy",
        "required_layers": ["unit", "integration"], "coverage": {"unit": "ok"}, "tests": {},
    }
    decision = evaluate_fr(node, is_collision=False, ledger_entry=entry)
    assert decision == {"fr": "FR-01.11", "action": "skip", "reason_code": SKIP_DEMOTED_CONSISTENT}


def test_demoted_action_spec_write_failure_names_the_state_and_says_a_retry_will_clear_it(
    tmp_path, monkeypatch,
):
    # Low finding, Stage-3 doubt-review round 2, P3.5 post-push round: the
    # demote path is ledger-first -- if the spec.md revert-to-inferred write
    # is refused after the ledger already recorded the demotion, on-disk
    # state becomes ledger=demoted + cell-still-explicit (reds the
    # repo-wide explicit<=promoted integration guard, same as the automated
    # tool's own `already_explicit` escalation arm). Unlike the automated
    # tool's matching message (which explicitly says a plain re-run will NOT
    # clear it -- only an operator, via THIS CLI, can), this path already IS
    # that CLI: re-running the exact same --action demoted command retries
    # and completes the revert. Only the promote-path write ordering was
    # pinned before (test_promote_required_layers.py's TOCTOU test) -- this
    # is the demote-path sibling, same simulation idiom (mutate the file
    # from inside a wrapped `_plan_decision`, after its own read, before the
    # write).
    project = _write_project(tmp_path, layers_cell="unit, integration")
    spec_path = project / _SPEC_RELPATH

    real_plan_decision = mod._plan_decision

    def _plan_then_concurrently_edit(args, manifest, project_root):
        plan = real_plan_decision(args, manifest, project_root)
        current = spec_path.read_text(encoding="utf-8")
        spec_path.write_text(current.replace("y.", "y (edited concurrently)."), encoding="utf-8")
        return plan

    monkeypatch.setattr(mod, "_plan_decision", _plan_then_concurrently_edit)

    with pytest.raises(SystemExit, match="re-run the same --action demoted"):
        mod.main([
            "--project-root", str(project), "--fr-id", "FR-01.11", "--action", "demoted",
            "--reason", "evidence looked green but was misleading",
        ])

    # The ledger entry landed even though the spec.md revert did not.
    ledger = load_ledger(ledger_path(project))
    assert ledger["decisions"]["FR-01.11"][-1]["action"] == "demoted"
    spec = spec_path.read_text(encoding="utf-8")
    assert "edited concurrently" in spec
    assert "| unit, integration |" in spec  # still explicit -- the revert never landed


def test_promoted_without_required_layers_is_rejected(tmp_path):
    project = _write_project(tmp_path)
    with pytest.raises(SystemExit, match="required-layers"):
        mod.main([
            "--project-root", str(project), "--fr-id", "FR-01.11", "--action", "promoted",
            "--reason", "x",
        ])


def test_demoted_with_required_layers_is_rejected(tmp_path):
    project = _write_project(tmp_path)
    with pytest.raises(SystemExit, match="must not carry"):
        mod.main([
            "--project-root", str(project), "--fr-id", "FR-01.11", "--action", "demoted",
            "--required-layers", "unit", "--reason", "x",
        ])


def test_unrecognised_layer_is_rejected(tmp_path):
    project = _write_project(tmp_path)
    with pytest.raises(SystemExit, match="unrecognised"):
        mod.main([
            "--project-root", str(project), "--fr-id", "FR-01.11", "--action", "promoted",
            "--required-layers", "smoke", "--reason", "x",
        ])


def test_unknown_fr_id_is_rejected(tmp_path):
    project = _write_project(tmp_path)
    with pytest.raises(SystemExit, match="FR-99.99"):
        mod.main([
            "--project-root", str(project), "--fr-id", "FR-99.99", "--action", "demoted",
            "--reason", "x",
        ])


def test_decided_by_is_always_operator_never_configurable():
    # No --decided-by flag exists at all -- an unrecognised flag is rejected
    # by argparse itself, not merely absent from the source text (external
    # code review, glm/low, P3.5 round 1: a source grep alone would still
    # pass if some OTHER code path fed `append_decision` a different
    # `decided_by`; asserting the CLI's actual parse behavior does not).
    with pytest.raises(SystemExit):
        mod.main([
            "--project-root", "unused", "--fr-id", "FR-01.11", "--action", "demoted",
            "--reason", "x", "--decided-by", "tool",
        ])


def test_automated_tool_demoted_evidence_is_never_written_by_this_cli_alone(tmp_path):
    # The one property that actually matters: every entry THIS module writes
    # is "operator", regardless of which action or how the manifest evidence
    # looks -- proven behaviorally, not by grepping for an absent flag.
    project = _write_project(tmp_path, layers_cell="unit")
    rc = mod.main([
        "--project-root", str(project), "--fr-id", "FR-01.11", "--action", "demoted",
        "--reason", "operator vetoes despite green evidence",
    ])
    assert rc == 0
    ledger = load_ledger(ledger_path(project))
    entry = ledger["decisions"]["FR-01.11"][-1]
    assert entry["decided_by"] == "operator"
    assert entry["action"] == "demoted"


def test_promoted_action_on_a_collision_id_is_rejected_use_demoted_instead(tmp_path):
    manifest_path = tmp_path / ".shipwright" / "compliance" / "test-traceability.json"
    project = _write_project(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["requirements"]["02::FR-01.11"] = {
        "id": "FR-01.11", "spec_path": _SPEC_RELPATH, "status": "active",
        "coverage": {}, "tests": {},
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SystemExit, match="collision fan-out"):
        mod.main([
            "--project-root", str(project), "--fr-id", "FR-01.11", "--action", "promoted",
            "--required-layers", "unit", "--reason", "x",
        ])


def test_demoted_action_on_a_collision_id_still_clears_it(tmp_path):
    manifest_path = tmp_path / ".shipwright" / "compliance" / "test-traceability.json"
    project = _write_project(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["requirements"]["02::FR-01.11"] = {
        "id": "FR-01.11", "spec_path": _SPEC_RELPATH, "status": "active",
        "coverage": {}, "tests": {},
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    rc = mod.main([
        "--project-root", str(project), "--fr-id", "FR-01.11", "--action", "demoted",
        "--reason", "collision id vetoed",
    ])
    assert rc == 0
    ledger = load_ledger(ledger_path(project))
    entry = ledger["decisions"]["FR-01.11"][-1]
    assert entry["action"] == "demoted"
    assert "evidence_fingerprint" not in entry


def test_a_second_invocation_times_out_while_the_lock_is_held(tmp_path, monkeypatch):
    """Stage-4 doubt-review Medium finding, P3.5 post-push round -- the same
    hazard ``test_mint_ac_ids.py:198`` documents fixing once already in this
    repo: nothing previously exercised ``file_lock`` at all here, so
    deleting the locked span around ``main()``'s write left every OTHER test
    in this file green. The timeout is monkeypatched down from the real 10s
    so this test stays fast."""
    monkeypatch.setattr(mod, "_LOCK_TIMEOUT_SECONDS", 0.2)
    project = _write_project(tmp_path)
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
        with pytest.raises(SystemExit):
            mod.main([
                "--project-root", str(project), "--fr-id", "FR-01.11",
                "--action", "demoted", "--reason", "x",
            ])
    finally:
        release_holder.set()
        holder.join(timeout=5.0)

    # Nothing was written -- the lock was never acquired for this run.
    assert (project / _SPEC_RELPATH).read_text(encoding="utf-8") == original_spec
    assert not ledger_path(project).exists()


def test_an_exception_inside_the_locked_span_still_releases_the_lock(tmp_path, monkeypatch):
    """A body exception ``_decide_and_write_locked`` does not itself catch
    (here a non-``ValueError`` failure reading the ledger) must not leave
    the lock held for a follow-up invocation.

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
    project = _write_project(tmp_path)

    def _boom(*a, **k):
        raise RuntimeError("simulated non-ValueError ledger read failure")

    with monkeypatch.context() as m:
        m.setattr(mod, "load_ledger_with_snapshot", _boom)
        with pytest.raises(RuntimeError, match="simulated non-ValueError") as excinfo:
            mod.main([
                "--project-root", str(project), "--fr-id", "FR-01.11",
                "--action", "demoted", "--reason", "x",
            ])

    rc = mod.main([
        "--project-root", str(project), "--fr-id", "FR-01.11",
        "--action", "demoted", "--reason", "y",
    ])
    assert rc == 0
    assert excinfo.type is RuntimeError  # keeps `excinfo` referenced past the call above
