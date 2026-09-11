"""`record_ci_supplychain_ack` — the writer CLI for the F11 CI supply-chain gate
(iterate-2026-07-18-ci-supplychain-risk-flag).

The ack must never be hand-written: the run and content bindings are computed, not
typed. Since iterate-2026-07-28-ci-ack-per-run-home it is written to
`.shipwright/planning/iterate/<run_id>/ci_supplychain_ack.json` rather than into
`shipwright_test_results.json`, which is a derived snapshot the iterate commit may
not carry.

The CLI runs PRE-F6, so it fingerprints the WORKING TREE while the F11 verifier
fingerprints the COMMITTED tree. These tests pin that the two agree across that
boundary, that an edit made after recording invalidates the ack, and that sibling
keys survive the write.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402
from tools import record_ci_supplychain_ack as rec  # noqa: E402
from tools.verifiers import ci_supplychain as cs  # noqa: E402

_RUN = "iterate-2026-07-18-ci-supplychain-risk-flag"


@pytest.fixture(autouse=True)
def _no_ambient_campaign_context(monkeypatch):
    """Every test in this module runs as a standalone caller by default —
    whatever launched the test process must not leak SHIPWRIGHT_LOOP_UNIT_ID into
    the guard added for trg-33d30377. Tests that exercise the guard set it back
    explicitly."""
    monkeypatch.delenv("SHIPWRIGHT_LOOP_UNIT_ID", raising=False)


def _stage_only(wt: Path, path: str, body: str = "on: push\n") -> None:
    """Write the change but do NOT commit — the state the ack CLI runs in (pre-F6)."""
    _write(wt, path, body)


def _commit_all(wt: Path) -> str:
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "touch CI boundary")
    return _git(wt, "rev-parse", "HEAD").stdout.strip()


def test_written_ack_satisfies_the_gate(git_origin_repo, make_worktree):
    """End-to-end in REAL order: write -> record (working tree) -> commit -> verify
    (committed tree). The two fingerprints must agree across that boundary."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "rec-ok")
    _stage_only(wt, ".github/workflows/ci.yml")

    rec.main(["--project-root", str(wt), "--run-id", _RUN,
              "--consistent-with", "ADR-042",
              "--statement", "GitHub-owned actions stay on mutable tags here."])
    commit = _commit_all(wt)

    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is True, res.detail


def test_ack_is_invalidated_when_the_ci_file_changes_after_recording(
        git_origin_repo, make_worktree):
    """The point of content binding: the recorded sentence must not survive an
    edit that makes it untrue."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "rec-amended")
    _stage_only(wt, ".github/workflows/ci.yml")
    rec.main(["--project-root", str(wt), "--run-id", _RUN,
              "--consistent-with", "ADR-042",
              "--statement", "Adds a ruff step to the existing lint job."])

    # slipped in AFTER the acknowledgement was recorded
    _write(wt, ".github/workflows/ci.yml", "on: pull_request_target\n")
    commit = _commit_all(wt)

    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is False
    assert "fingerprint" in res.detail.lower()


def test_leaves_the_derived_results_file_untouched(git_origin_repo, make_worktree):
    """Was `test_preserves_sibling_keys`, which pinned the ack being MERGED into
    `iterate_latest` while sibling keys (the top-level `coverage` block feeding the
    CI coverage-baseline lint) survived.

    Since iterate-2026-07-28-ci-ack-per-run-home the ack is not written here at
    all — that file is a DERIVED SNAPSHOT, and parking the ack in it made two
    ERROR-severity F11 checks unsatisfiable at once. The invariant is therefore
    strictly stronger than "siblings survive": the file must come out BYTE-IDENTICAL.
    """
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "rec-preserve")
    _stage_only(wt, ".github/workflows/ci.yml")
    before = json.dumps({
        "iterate_latest": {"run_id": _RUN, "unit": {"status": "passed"}},
        "coverage": {"total": 80.2, "measured_tier": "repo"},
    })
    _write(wt, "shipwright_test_results.json", before)

    rec.main(["--project-root", str(wt), "--run-id", _RUN,
              "--consistent-with", "#285",
              "--statement", "Reverts the hosted updater, keeping third-party pins."])

    after = (wt / "shipwright_test_results.json").read_text(encoding="utf-8")
    assert after == before, "the writer must not touch the derived snapshot at all"
    ack = json.loads((wt / cs.ack_relpath(_RUN)).read_text(encoding="utf-8"))
    assert ack["ci_supplychain_ack"]["consistent_with"] == "#285"


def test_refuses_when_working_tree_touches_no_ci_file(git_origin_repo, make_worktree):
    """Recording an ack for a non-CI change would only plant a stale ack."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "rec-noci")
    _stage_only(wt, "src/app/page.tsx", body="export default null\n")

    with pytest.raises(SystemExit):
        rec.main(["--project-root", str(wt), "--run-id", _RUN,
                  "--consistent-with", "ADR-042", "--statement", "nothing to see here"])


def test_refuses_with_a_pointer_to_commit_once_the_ci_change_is_committed(
        git_origin_repo, make_worktree):
    """trg-33d30377's third finding: the working tree sees nothing once F6 has
    run, and the OLD message ("no acknowledgement is needed") actively lied
    about that. The new message must point at the way out."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "rec-already-committed")
    _stage_only(wt, ".github/workflows/ci.yml")
    _commit_all(wt)   # the CI change is now committed; working tree is clean

    with pytest.raises(SystemExit) as exc:
        rec.main(["--project-root", str(wt), "--run-id", _RUN,
                  "--consistent-with", "ADR-042", "--statement", "already committed"])
    assert "--commit" in str(exc.value)


# --- external review follow-ups (Branch A, iterate-2026-09-11) --------------

def test_commit_ref_is_resolved_to_a_full_sha(git_origin_repo, make_worktree):
    """A symbolic ref recorded verbatim as `provenance_ref` would keep meaning
    "whatever HEAD was" even after HEAD moves on — resolve it once, up front."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "rec-commit-sha-resolve")
    _stage_only(wt, ".github/workflows/ci.yml")
    commit = _commit_all(wt)

    rec.main(["--project-root", str(wt), "--run-id", _RUN, "--commit", "HEAD",
              "--consistent-with", "ADR-042", "--statement", "acknowledged via HEAD"])

    payload = json.loads((wt / cs.ack_relpath(_RUN)).read_text(encoding="utf-8"))
    ack = payload["ci_supplychain_ack"]
    assert ack["provenance_ref"] == commit, "HEAD must resolve to the full SHA"


def test_commit_mode_refuses_an_unresolvable_ref(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "rec-commit-bad-ref")
    _stage_only(wt, ".github/workflows/ci.yml")
    _commit_all(wt)

    with pytest.raises(SystemExit):
        rec.main(["--project-root", str(wt), "--run-id", _RUN, "--commit", "not-a-ref",
                  "--consistent-with", "ADR-042", "--statement", "bogus ref"])


# --- --commit mode (reachable operator path for committed content) ----------

def test_commit_mode_acknowledges_already_committed_content(
        git_origin_repo, make_worktree, monkeypatch):
    """The reachable path trg-33d30377 demanded: an operator, in any later
    session, can acknowledge a CI change that is already on the branch."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "rec-commit-mode")
    monkeypatch.delenv("SHIPWRIGHT_LOOP_UNIT_ID", raising=False)
    _stage_only(wt, ".github/workflows/ci.yml")
    commit = _commit_all(wt)   # working tree is now clean

    rec.main(["--project-root", str(wt), "--run-id", _RUN, "--commit", commit,
              "--consistent-with", "ADR-042",
              "--statement", "GitHub-owned actions stay on mutable tags here."])

    payload = json.loads((wt / cs.ack_relpath(_RUN)).read_text(encoding="utf-8"))
    ack = payload["ci_supplychain_ack"]
    assert ack["provenance"] == "commit"
    assert ack["provenance_ref"] == commit
    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is True, res.detail


def test_worktree_mode_stamps_provenance_worktree(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "rec-worktree-provenance")
    _stage_only(wt, ".github/workflows/ci.yml")

    rec.main(["--project-root", str(wt), "--run-id", _RUN,
              "--consistent-with", "ADR-042", "--statement", "pre-commit acknowledgement"])

    payload = json.loads((wt / cs.ack_relpath(_RUN)).read_text(encoding="utf-8"))
    ack = payload["ci_supplychain_ack"]
    assert ack["provenance"] == "worktree"
    assert ack["provenance_ref"] is None


def test_verifier_rejects_an_ack_missing_the_provenance_stamp(
        git_origin_repo, make_worktree):
    """An ack that was not written by this CLI (hand-assembled, or predating the
    stamp) must not be treated as equally trustworthy at the per-run location."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "rec-no-provenance")
    _stage_only(wt, ".github/workflows/ci.yml")
    rel = cs.ack_relpath(_RUN)
    _write(wt, rel, json.dumps({
        "schema_version": 1, "run_id": _RUN,
        "ci_supplychain_ack": {
            "run_id": _RUN,
            "paths_fingerprint": cs.ci_supplychain_fingerprint(
                [".github/workflows/ci.yml"], lambda _r: "on: push\n"),
            "consistent_with": "ADR-042",
            "statement": "hand-assembled, with no provenance field at all",
            "ci_paths": [".github/workflows/ci.yml"],
        },
    }))
    commit = _commit_all(wt)

    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is False
    assert "provenance" in res.detail.lower()
