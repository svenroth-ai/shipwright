"""The operator-only authorship guard for `record_ci_supplychain_ack` (trg-33d30377
/ PR #718). Split out of test_record_ci_supplychain_ack.py (bloat gate) — this
group covers one cohesive property: no entry point into writing an ack (CLI
`main()`, `build_ack()`, or `write_ack()` called directly) can be reached while
`SHIPWRIGHT_LOOP_UNIT_ID` names an active campaign sub-iterate runner.
"""

from __future__ import annotations

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


def test_build_ack_refuses_in_campaign_context_even_bypassing_main(
        git_origin_repo, make_worktree, monkeypatch):
    """Defense in depth: a future caller that reaches build_ack() directly
    (skipping main()'s CLI parsing) must still be refused."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "rec-build-ack-guard")
    _stage_only(wt, ".github/workflows/ci.yml")
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "p3.8")

    with pytest.raises(SystemExit) as exc:
        rec.build_ack(wt, _RUN, "ADR-042", "self-authored via the API directly")
    assert "campaign" in str(exc.value).lower()


def test_write_ack_refuses_a_hand_built_dict_bypassing_build_ack(
        git_origin_repo, make_worktree, monkeypatch, tmp_path):
    """Doubt review: write_ack() is independently reachable and importable —
    a caller that hand-builds an ack dict (never calling build_ack()) must
    still be refused, and must leave no file behind. This is the gap
    build_ack's own "defense in depth" docstring did not actually close."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "rec-write-ack-guard")
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "p3.8")

    hand_built = {
        "run_id": _RUN,
        "paths_fingerprint": {},
        "consistent_with": "ADR-042",
        "statement": "hand-built, never went through build_ack",
        "ci_paths": [],
        "provenance": "worktree",
        "provenance_ref": None,
    }
    with pytest.raises(SystemExit) as exc:
        rec.write_ack(wt, _RUN, hand_built)
    assert "campaign" in str(exc.value).lower()
    assert not (wt / "ci_supplychain_ack.json").exists()
    assert not (wt / ".shipwright" / "planning" / "iterate" / _RUN
                / "ci_supplychain_ack.json").exists()


def test_refuses_inside_an_active_campaign_runner_context(
        git_origin_repo, make_worktree, monkeypatch):
    """The actual observed failure: a campaign sub-iterate runner, still carrying
    SHIPWRIGHT_LOOP_UNIT_ID, called this CLI for its own diff. It must not be
    able to produce a usable ack at all — no override flag."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "rec-campaign-refuse")
    _stage_only(wt, ".github/workflows/ci.yml")
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "p3.8")

    with pytest.raises(SystemExit) as exc:
        rec.main(["--project-root", str(wt), "--run-id", _RUN,
                  "--consistent-with", "ADR-042", "--statement", "self-authored"])
    assert "campaign" in str(exc.value).lower()
    assert not (wt / cs.ack_relpath(_RUN)).exists(), (
        "the guard must fire before anything is written")


def test_refuses_in_commit_mode_too(git_origin_repo, make_worktree, monkeypatch):
    """The guard is orthogonal to which content mode is used — a runner must not
    be able to route around it via --commit either."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "rec-campaign-refuse-commit")
    _stage_only(wt, ".github/workflows/ci.yml")
    commit = _commit_all(wt)
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "p3.8")

    with pytest.raises(SystemExit) as exc:
        rec.main(["--project-root", str(wt), "--run-id", _RUN, "--commit", commit,
                  "--consistent-with", "ADR-042", "--statement", "self-authored"])
    assert "campaign" in str(exc.value).lower()


def test_allows_when_loop_unit_id_is_unset(git_origin_repo, make_worktree, monkeypatch):
    """A standalone iterate never sets the var; the guard must be a pure no-op."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "rec-standalone-ok")
    _stage_only(wt, ".github/workflows/ci.yml")
    monkeypatch.delenv("SHIPWRIGHT_LOOP_UNIT_ID", raising=False)

    rec.main(["--project-root", str(wt), "--run-id", _RUN,
              "--consistent-with", "ADR-042", "--statement", "operator recorded this"])
    assert (wt / cs.ack_relpath(_RUN)).exists()
