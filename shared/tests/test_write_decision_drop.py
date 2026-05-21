"""Tests for shared/scripts/tools/write_decision_drop.py."""

from __future__ import annotations

import json

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


def test_two_drops_same_run_get_distinct_counters(tmp_path):
    p1 = write_decision_drop(tmp_path, **_fields())
    p2 = write_decision_drop(tmp_path, **_fields())
    assert p1.name == "iterate-20260515-foo_001.json"
    assert p2.name == "iterate-20260515-foo_002.json"


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
# Worktree-awareness — iterate F3 runs inside an ephemeral worktree whose
# .shipwright/agent_docs/decision-drops/ is destroyed by `git worktree
# remove` before /shipwright-changelog can aggregate it. The drop MUST land
# next to the MAIN repo. Mirrors lib.events_log.resolve_events_path.
# ---------------------------------------------------------------------------


def _main_drops(work):
    return (work / ".shipwright" / "agent_docs" / "decision-drops").resolve()


def test_drop_dir_plain_repo_is_repo_local(git_origin_repo):
    """In a plain checkout drop_dir is repo-local — behavior unchanged."""
    work, _ = git_origin_repo
    assert drop_dir(work).resolve() == _main_drops(work)


def test_drop_written_from_worktree_lands_in_main_repo(git_origin_repo, make_worktree):
    """Core bug: F3 runs inside an iterate worktree; the drop must be written
    to the MAIN repo, not the worktree copy."""
    work, _ = git_origin_repo
    wt = make_worktree(work, "drop-loc")
    path = write_decision_drop(wt, **_fields())
    assert path.resolve().parent == _main_drops(work)
    # NOT inside the worktree — that copy dies with `git worktree remove`.
    assert wt.resolve() not in path.resolve().parents


def test_drop_survives_worktree_removal(git_origin_repo, make_worktree, remove_worktree):
    """The round-trip the bug broke: a drop written from inside the worktree
    must still exist after `git worktree remove` tears the worktree down."""
    work, _ = git_origin_repo
    wt = make_worktree(work, "drop-survive")
    path = write_decision_drop(wt, **_fields())
    assert path.exists()
    remove_worktree(work, wt)
    assert path.exists(), (
        "decision-drop destroyed with the worktree — aggregate_decisions "
        "would never fold it into decision_log.md"
    )


def test_drop_from_worktree_is_aggregated_from_main_repo(
    git_origin_repo, make_worktree, remove_worktree
):
    """End-to-end producer->file->consumer round-trip across the worktree
    boundary: F3 writes the drop from the worktree, the worktree is removed
    (F11 cleanup), then /shipwright-changelog's aggregate runs on the MAIN
    repo and must still see and fold the drop into decision_log.md."""
    work, _ = git_origin_repo
    wt = make_worktree(work, "drop-agg")
    write_decision_drop(wt, **_fields(run_id="iterate-20260519-probe"))
    remove_worktree(work, wt)
    result = aggregate(work)
    assert result["aggregated"] == 1
    log = (
        work / ".shipwright" / "agent_docs" / "decision_log.md"
    ).read_text(encoding="utf-8")
    assert "iterate-20260519-probe" in log


@pytest.mark.parametrize("root_kind", ["plain", "worktree", "non-git"])
def test_drop_dir_producer_consumer_parity(
    git_origin_repo, tmp_path, make_worktree, root_kind
):
    """Drift protection (NOT a correctness test): write_decision_drop.drop_dir
    (producer) and aggregate_decisions.drop_dir (consumer) must resolve the
    SAME directory for the same input — divergence = silently lost ADRs.
    That the resolved directory is *correct* is covered separately by
    test_drop_dir_plain_repo_is_repo_local and
    test_drop_written_from_worktree_lands_in_main_repo."""
    if root_kind == "non-git":
        root = tmp_path
    else:
        work, _ = git_origin_repo
        root = work if root_kind == "plain" else make_worktree(work, "parity")
    assert drop_dir(root).resolve() == aggregate_drop_dir(root).resolve()
