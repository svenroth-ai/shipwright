"""Tests for shared/scripts/tools/write_decision_drop.py."""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from tools.aggregate_decisions import aggregate
from tools.aggregate_decisions import drop_dir as aggregate_drop_dir
from tools.write_decision_drop import (
    DecisionDropError,
    drop_dir,
    write_decision_drop,
)

# Linked worktrees come from the shared ``make_worktree`` / ``remove_worktree``
# fixtures (shared/tests/conftest.py).


def _fields(**over):
    base = dict(
        run_id="iterate-20260515-foo",
        section="Iterate — change: foo",
        title="Foo decision",
        context="why",
        decision="what",
        consequences="impact",
    )
    base.update(over)
    return base


def test_writes_json_drop(tmp_path):
    path = write_decision_drop(tmp_path, **_fields())
    assert path.exists()
    assert path.parent == drop_dir(tmp_path)
    assert path.name == "iterate-20260515-foo_001.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["run_id"] == "iterate-20260515-foo"
    assert data["decision"] == "what"
    assert data["architecture_impact"] == "none"
    assert data["date"]  # populated by the tool


def test_two_distinct_drops_same_run_get_distinct_counters(tmp_path):
    """Two DIFFERENT ADRs in the same run still get their own counters —
    the multi-ADR-per-run feature is preserved by the idempotency guard
    (dedup keys on content, not just run_id)."""
    p1 = write_decision_drop(tmp_path, **_fields(title="First"))
    p2 = write_decision_drop(tmp_path, **_fields(title="Second"))
    assert p1.name == "iterate-20260515-foo_001.json"
    assert p2.name == "iterate-20260515-foo_002.json"


def test_identical_content_is_idempotent(tmp_path):
    """Re-invoking with the SAME (run_id, content) returns the EXISTING drop
    instead of creating a duplicate _002 — makes whole-bundle retry safe
    (iterate-2026-07-15-finalize-bundle). Volatile date/commit are excluded
    from the dedup key so a cross-midnight re-run still dedups."""
    p1 = write_decision_drop(tmp_path, **_fields())
    p2 = write_decision_drop(tmp_path, **_fields())
    assert p2 == p1
    assert p1.name == "iterate-20260515-foo_001.json"
    # Exactly ONE file on disk — no duplicate.
    assert sorted(drop_dir(tmp_path).glob("iterate-20260515-foo_*.json")) == [p1]


def test_empty_decision_rejected(tmp_path):
    with pytest.raises(DecisionDropError):
        write_decision_drop(tmp_path, **_fields(decision="   "))


def test_empty_run_id_rejected(tmp_path):
    with pytest.raises(DecisionDropError):
        write_decision_drop(tmp_path, **_fields(run_id=""))


def test_bad_architecture_impact_rejected(tmp_path):
    with pytest.raises(DecisionDropError):
        write_decision_drop(tmp_path, **_fields(architecture_impact="bogus"))


def test_optional_fields_persisted(tmp_path):
    path = write_decision_drop(
        tmp_path,
        **_fields(
            rationale="because",
            rejected="alt-a",
            architecture_impact="convention",
        ),
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["rationale"] == "because"
    assert data["rejected"] == "alt-a"
    assert data["architecture_impact"] == "convention"


# ---------------------------------------------------------------------------
# Iterate A.3 — hard reject + spec_ref persistence
# ---------------------------------------------------------------------------


def test_spec_ref_persisted_in_drop(tmp_path):
    """spec_ref MUST survive into the JSON payload so the aggregator can
    render the **Details:** link at release time."""
    path = write_decision_drop(
        tmp_path,
        **_fields(spec_ref=".shipwright/planning/adr/042-foo.md"),
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["spec_ref"] == ".shipwright/planning/adr/042-foo.md"


def test_spec_ref_omitted_defaults_to_empty(tmp_path):
    """Backwards-compat: a drop without spec_ref must still validate and the
    persisted field is an empty string (not missing) — so the schema is stable."""
    path = write_decision_drop(tmp_path, **_fields())
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["spec_ref"] == ""


def test_drop_hard_rejected_on_field_length_overflow(tmp_path):
    """Iterate A.3: new drops with any field above the 500-char budget must
    raise DecisionDropError immediately — single-user-repo hard reject."""
    with pytest.raises(DecisionDropError, match=r"500-char budget"):
        write_decision_drop(tmp_path, **_fields(context="x" * 600))
    # No file written on rejection
    assert not list(drop_dir(tmp_path).glob("*.json")) if drop_dir(tmp_path).is_dir() else True


def test_drop_overflow_error_mentions_spec_folder(tmp_path):
    with pytest.raises(DecisionDropError) as exc:
        write_decision_drop(tmp_path, **_fields(consequences="y" * 800))
    assert ".shipwright/planning/adr/" in str(exc.value)


# ---------------------------------------------------------------------------
# Worktree-local writes (iterate-2026-08-08-track-decision-drops) — the
# directory is now TRACKED, so the drop is written INTO the calling
# iterate's own worktree; F6 stages it and it ships in that iterate's own
# commit/PR. Durability comes from git history now, not from redirecting the
# write to the main repo's disk (the pre-2026-08-08 behavior, when the
# directory was gitignored and disk survival was the only safety net).
# ---------------------------------------------------------------------------


def _main_drops(work):
    return (work / ".shipwright" / "agent_docs" / "decision-drops").resolve()


def test_drop_dir_plain_repo_is_repo_local(git_origin_repo):
    """In a plain checkout drop_dir is repo-local — behavior unchanged."""
    work, _ = git_origin_repo
    assert drop_dir(work).resolve() == _main_drops(work)


def test_drop_written_from_worktree_lands_in_the_worktree(git_origin_repo, make_worktree):
    """The drop is written into the CALLING worktree, not redirected to the
    main repo — the directory is tracked, so this run's own commit is what
    carries it into git history."""
    work, _ = git_origin_repo
    wt = make_worktree(work, "drop-loc")
    path = write_decision_drop(wt, **_fields())
    assert path.resolve().parent == (wt / ".shipwright" / "agent_docs" / "decision-drops").resolve()
    assert path.resolve().parent != _main_drops(work)


def test_uncommitted_drop_is_lost_with_the_worktree(
    git_origin_repo, make_worktree, remove_worktree
):
    """Accepted tradeoff (internal Opus review, mini-plan addendum item 9):
    an uncommitted drop does NOT survive `git worktree remove` — unlike the
    pre-2026-08-08 main-root redirect, which existed precisely to survive
    this. Durability now comes from committing (F6) before the worktree is
    torn down, not from disk placement; an abandoned run's drop was never
    delivered under the PR+CI model either."""
    work, _ = git_origin_repo
    wt = make_worktree(work, "drop-abandon")
    path = write_decision_drop(wt, **_fields())
    assert path.exists()
    remove_worktree(work, wt)
    assert not path.exists()


def test_committed_drop_survives_worktree_removal_and_is_aggregated(
    git_origin_repo, make_worktree, remove_worktree
):
    """The real round-trip: F3 writes the drop into the worktree, F6 commits
    it (simulated here with a plain git add+commit), the branch merges into
    main (simulated with a merge), THEN the worktree is removed (F11
    cleanup) — the drop must survive via git history and
    /shipwright-changelog's aggregate must still fold it from the main repo."""
    work, _ = git_origin_repo
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Iso Test",
            "GIT_AUTHOR_EMAIL": "iso@test.invalid",
            "GIT_COMMITTER_NAME": "Iso Test",
            "GIT_COMMITTER_EMAIL": "iso@test.invalid",
        }
    )
    wt = make_worktree(work, "drop-commit")
    write_decision_drop(wt, **_fields(run_id="iterate-20260519-probe"))
    subprocess.run(
        ["git", "add", ".shipwright/agent_docs/decision-drops/"],
        cwd=wt, env=env, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "feat: probe decision-drop"],
        cwd=wt, env=env, check=True, capture_output=True,
    )
    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=wt, env=env, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "merge", "--no-ff", branch], cwd=work, env=env,
        check=True, capture_output=True,
    )
    remove_worktree(work, wt)

    result = aggregate(work)
    assert result["aggregated"] == 1
    log = (
        work / ".shipwright" / "agent_docs" / "decision_log.md"
    ).read_text(encoding="utf-8")
    assert "iterate-20260519-probe" in log


def test_sibling_worktrees_do_not_share_pending_drops(git_origin_repo, make_worktree):
    """No more shared-disk cross-contamination: a drop written in one
    worktree does not appear in a sibling worktree's own local view — each
    worktree only sees its own tracked-but-uncommitted content, unlike the
    pre-2026-08-08 shared main-repo directory every worktree wrote into."""
    work, _ = git_origin_repo
    wt_a = make_worktree(work, "sibling-a")
    wt_b = make_worktree(work, "sibling-b")
    write_decision_drop(wt_a, **_fields(run_id="iterate-sibling-a"))
    assert list(drop_dir(wt_b).glob("*.json")) == []


@pytest.mark.parametrize("root_kind", ["plain", "worktree", "non-git"])
def test_drop_dir_producer_consumer_parity(
    git_origin_repo, tmp_path, make_worktree, root_kind
):
    """Drift protection (NOT a correctness test): write_decision_drop.drop_dir
    (producer) and aggregate_decisions.drop_dir (consumer) must resolve the
    SAME directory for the same input — divergence = silently lost ADRs.
    That the resolved directory is *correct* is covered separately by
    test_drop_dir_plain_repo_is_repo_local and
    test_drop_written_from_worktree_lands_in_the_worktree."""
    if root_kind == "non-git":
        root = tmp_path
    else:
        work, _ = git_origin_repo
        root = work if root_kind == "plain" else make_worktree(work, "parity")
    assert drop_dir(root).resolve() == aggregate_drop_dir(root).resolve()


# F6 glob-scoped staging tests (doubt-reviewer MEDIUM #4) live in
# test_f6_decision_drop_staging.py — split out to stay under the bloat gate.
