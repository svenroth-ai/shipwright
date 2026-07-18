"""`record_ci_supplychain_ack` — the writer CLI for the F11 CI supply-chain gate
(iterate-2026-07-18-ci-supplychain-risk-flag).

The ack must never be hand-edited into `shipwright_test_results.json`: it is a
machine-written artifact, and a hand-injected field is dropped on the next regen.

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


def test_preserves_sibling_keys(git_origin_repo, make_worktree):
    """The top-level `coverage` block has been silently dropped by a wholesale
    rewrite of this file before — every untouched key must survive."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "rec-preserve")
    _stage_only(wt, ".github/workflows/ci.yml")
    _write(wt, "shipwright_test_results.json", json.dumps({
        "iterate_latest": {"run_id": _RUN, "unit": {"status": "passed"}},
        "coverage": {"total": 80.2, "measured_tier": "repo"},
    }))

    rec.main(["--project-root", str(wt), "--run-id", _RUN,
              "--consistent-with", "#285",
              "--statement", "Reverts the hosted updater, keeping third-party pins."])

    data = json.loads((wt / "shipwright_test_results.json").read_text(encoding="utf-8"))
    assert data["coverage"] == {"total": 80.2, "measured_tier": "repo"}
    assert data["iterate_latest"]["unit"] == {"status": "passed"}
    assert data["iterate_latest"]["ci_supplychain_ack"]["consistent_with"] == "#285"


def test_refuses_when_working_tree_touches_no_ci_file(git_origin_repo, make_worktree):
    """Recording an ack for a non-CI change would only plant a stale ack."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "rec-noci")
    _stage_only(wt, "src/app/page.tsx", body="export default null\n")

    with pytest.raises(SystemExit):
        rec.main(["--project-root", str(wt), "--run-id", _RUN,
                  "--consistent-with", "ADR-042", "--statement", "nothing to see here"])
