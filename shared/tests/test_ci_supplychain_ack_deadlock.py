"""The two F11 gates are satisfiable at the same time
(iterate-2026-07-28-ci-ack-per-run-home).

`check_ci_supplychain_ack` and `check_no_derived_snapshots_committed` are both
ERROR severity and, before this change, contradicted each other for any iterate
touching `.github/workflows/**`: the ack was read from the committed
`shipwright_test_results.json`, which the other gate forbids the commit to touch.

Every test here is a COMPOSITION test — each gate passed in isolation the whole
time, so asserting either one alone would never have caught the deadlock. Read
semantics live in ``test_ci_supplychain_ack_per_run_home.py``, whose helpers this
module reuses.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.derived_snapshots import (  # noqa: E402
    DERIVED_SNAPSHOTS,
    restore_derived_to_head,
)
from test_ci_supplychain_ack_per_run_home import (  # noqa: E402
    _RUN,
    _STMT,
    _WF,
    _WITH,
    _ack,
    _commit,
    _touch_workflow,
    _write_per_run_ack,
)
from test_integrate_main import _write  # noqa: E402
from tools import record_ci_supplychain_ack as rec  # noqa: E402
from tools.verifiers import ci_supplychain as cs  # noqa: E402
from tools.verifiers.derived_snapshot_gate import (  # noqa: E402
    check_no_derived_snapshots_committed,
)


def test_both_gates_are_simultaneously_satisfiable(git_origin_repo, make_worktree):
    """THE regression test. Before this change one of the two always failed:
    committing the results file tripped the derived-snapshot gate, omitting it
    starved the ack gate."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "dl-both")
    _touch_workflow(wt)
    rel = _write_per_run_ack(wt, _ack())
    commit = _commit(wt, _WF, rel)

    ack_res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    derived_res = check_no_derived_snapshots_committed(wt, _RUN, commit)
    assert ack_res.ok is True, ack_res.detail
    assert derived_res.ok is True, derived_res.detail


def test_the_old_home_still_deadlocks(git_origin_repo, make_worktree):
    """Pins WHY the relocation was necessary rather than merely convenient: an
    ack in the legacy location is readable only from a commit the other gate
    rejects. If this ever stops failing, the two gates stopped contradicting each
    other for some other reason and this iterate's premise needs re-checking."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "dl-legacy-conflict")
    _touch_workflow(wt)
    _write(wt, "shipwright_test_results.json",
           json.dumps({"iterate_latest": {"run_id": _RUN, "ci_supplychain_ack": _ack()}}))
    commit = _commit(wt, _WF, "shipwright_test_results.json")

    assert cs.check_ci_supplychain_ack(wt, _RUN, commit).ok is True
    assert check_no_derived_snapshots_committed(wt, _RUN, commit).ok is False


def test_restore_derived_to_head_does_not_erase_the_per_run_ack(
        git_origin_repo, make_worktree):
    """Finalization hygiene reverted the ack in its old home — a third failure
    mode beyond the two gates. The new home is not a derived snapshot.

    The probe vehicle changed with trg-ad29a709: ``shipwright_test_results.json``
    is no longer restored when it is MODIFIED (a run writes it and nothing can
    recompute it, so resetting it destroys the run's own ledger). It can therefore
    no longer prove that a restore really happened. A derived MD does — and the
    property under test, that the ack in its NEW home survives, is untouched.
    """
    probe = ".shipwright/agent_docs/build_dashboard.md"
    work, _o = git_origin_repo
    wt = make_worktree(work, "dl-restore")
    _touch_workflow(wt)
    rel = _write_per_run_ack(wt, _ack())
    _write(wt, "shipwright_test_results.json", json.dumps({"iterate_latest": {}}))
    _write(wt, probe, "committed\n")
    _commit(wt, _WF, rel, "shipwright_test_results.json", probe)

    # producers dirty both mid-run, as F5a/F5b do
    _write(wt, probe, "regenerated\n")
    _write(wt, "shipwright_test_results.json", json.dumps({"iterate_latest": {"x": 1}}))
    restored = restore_derived_to_head(wt)

    assert probe in restored, "probe must exercise a real restore"
    payload = json.loads((wt / rel).read_text(encoding="utf-8"))
    assert payload["ci_supplychain_ack"]["consistent_with"] == _WITH
    # Pinned HERE, where the next reader of this test would otherwise trip over it:
    # the run-written ledger is deliberately left alone (trg-ad29a709).
    assert "shipwright_test_results.json" not in restored
    assert json.loads((wt / "shipwright_test_results.json").read_text(
        encoding="utf-8")) == {"iterate_latest": {"x": 1}}


def test_results_file_is_still_a_derived_snapshot():
    """This change relocates the ack; it must not weaken the other gate."""
    assert "shipwright_test_results.json" in DERIVED_SNAPSHOTS


# --- writer CLI round-trip (touches_io_boundary) ----------------------------

def test_round_trip_cli_write_commit_verifier_read(git_origin_repo, make_worktree):
    """Boundary probe: the writer runs pre-F6 against the WORKING tree, the
    verifier reads the COMMITTED tree. Producer and consumer must agree on both
    the path and the JSON shape — the seam a hand-built fixture cannot prove."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "dl-roundtrip")
    _touch_workflow(wt)

    rec.main(["--project-root", str(wt), "--run-id", _RUN,
              "--consistent-with", _WITH, "--statement", _STMT])

    rel = cs.ack_relpath(_RUN)
    assert (wt / rel).exists(), "the CLI must write the per-run ack file"
    commit = _commit(wt, _WF, rel)

    assert cs.check_ci_supplychain_ack(wt, _RUN, commit).ok is True
    assert check_no_derived_snapshots_committed(wt, _RUN, commit).ok is True


def test_cli_does_not_write_the_ack_into_the_derived_snapshot(
        git_origin_repo, make_worktree):
    """The whole point: the results file must come out of this untouched, and its
    sibling keys must survive."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "dl-nowrite")
    _touch_workflow(wt)
    _write(wt, "shipwright_test_results.json",
           json.dumps({"iterate_latest": {"run_id": _RUN}, "coverage": {"total": 80.2}}))

    rec.main(["--project-root", str(wt), "--run-id", _RUN,
              "--consistent-with", _WITH, "--statement", _STMT])

    data = json.loads((wt / "shipwright_test_results.json").read_text(encoding="utf-8"))
    assert "ci_supplychain_ack" not in data["iterate_latest"]
    assert data["coverage"] == {"total": 80.2}


def test_cli_rejects_an_unsafe_run_id(git_origin_repo, make_worktree):
    """`run_id` becomes a directory name; the writer must refuse traversal rather
    than create a file the verifier will never look for."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "dl-cli-traversal")
    _touch_workflow(wt)

    try:
        rec.main(["--project-root", str(wt), "--run-id", "../../escape",
                  "--consistent-with", _WITH, "--statement", _STMT])
    except SystemExit as exc:
        assert exc.code != 0
    else:
        raise AssertionError("the CLI must refuse an unsafe run id")


def test_cli_is_idempotent(git_origin_repo, make_worktree):
    """Re-running after an amended CI file must overwrite cleanly, not append or
    leave a half-written file — the ack is re-recorded whenever content changes."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "dl-idempotent")
    _touch_workflow(wt)
    rec.main(["--project-root", str(wt), "--run-id", _RUN,
              "--consistent-with", _WITH, "--statement", _STMT])
    _touch_workflow(wt, body="on: push\n# amended\n")
    rec.main(["--project-root", str(wt), "--run-id", _RUN,
              "--consistent-with", "#497", "--statement", _STMT])

    rel = cs.ack_relpath(_RUN)
    payload = json.loads((wt / rel).read_text(encoding="utf-8"))
    assert payload["ci_supplychain_ack"]["consistent_with"] == "#497"
    commit = _commit(wt, _WF, rel)
    assert cs.check_ci_supplychain_ack(wt, _RUN, commit).ok is True


def test_f6_reference_stages_the_per_run_directory():
    """F6 is agent-executed prose, not a script, so the honest pin on staging is
    a drift test — but it has to bite on the ADD LINE.

    The first version asserted that the two substrings appeared anywhere in the
    file. Both also occur in F6.md's prose notes, so the `git add` line could have
    been narrowed to `reviews.json` or deleted outright and the test would still
    have passed green — the one guard on the staging dependency, detecting
    nothing (Stage-1 spec review, finding 2). Assert on the add-list line itself.
    """
    f6 = (REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate"
          / "references" / "F6.md").read_text(encoding="utf-8")
    add_lines = [ln for ln in f6.splitlines()
                 if ln.strip().startswith("git add")
                 and ".shipwright/planning/iterate/<run_id>/" in ln]
    assert add_lines, "F6 must stage the per-run planning directory"
    # DIRECTORY-level: the path ends at the run dir, with no filename appended.
    directory_adds = [ln for ln in add_lines
                      if ".shipwright/planning/iterate/<run_id>/ " in ln + " "
                      or ln.rstrip().endswith(".shipwright/planning/iterate/<run_id>/")]
    assert directory_adds, (
        "the add must stay DIRECTORY-level — narrowing it to a filename strands "
        f"ci_supplychain_ack.json outside the PR; got: {add_lines!r}")
    assert any("ci_supplychain_ack.json" in ln for ln in directory_adds), (
        "the add line must name ci_supplychain_ack.json so a later edit cannot "
        "narrow it while believing only reviews.json depends on it")
