"""Regression test for the cross-worktree retention-cap merge race.

Root cause (see F5c.md's "Why 'approximately,' not 'exactly'" section):
retention is computed per-worktree from
whatever is on disk *in that worktree* when the append runs. Two iterates
built in independent worktrees off the same ``origin/main`` tip each start
from an identical base set they cannot see each other's write into, so both
evict the same oldest entry (deterministic ``sort_key`` over identical
input) and both add their own new one. Git merges the shared eviction as an
agreed delete/delete (no conflict) and both adds as unrelated new files (no
conflict) -- so the merged directory lands one entry over the cap per branch
that overshot together in the same merge.

Measured 2026-08-13 in shipwright-webui: two same-tip worktrees
(iterate-2026-08-13-mission-mobile-visual,
iterate-2026-08-13-changelog-manifest-config) both evicted
``iterate-2026-07-20-triage-write-fs-race.json``; merging PR #365 into PR
#366 left 51 tracked entries where the invariant claimed 50.

This module does not touch git plumbing -- it reproduces the outcome at the
filesystem layer the merge produces, which is what ``append_iterate_entry``
actually reads. That is also all a real merge changes: the tracked file set
under ``.shipwright/agent_docs/iterates/``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from lib.iterate_entry import (
    MIGRATION_STATE_KEY,
    MIGRATION_TS_KEY,
    RUN_CONFIG_NAME,
    iterates_dir,
)
from lib.iterate_test_results import install_immutable_evidence
import tools.append_iterate_entry as tool


ITERATE_RETENTION = tool.ITERATE_RETENTION


@pytest.fixture(autouse=True)
def _generated_current_evidence(monkeypatch):
    def install(project: Path, run_id: str):
        raw = json.dumps({"iterate_latest": {"run_id": run_id}}).encode()
        return install_immutable_evidence(project, run_id, raw)

    monkeypatch.setattr(tool, "install_current_evidence", install)


def _canonical_entry(slug: str, date: str) -> dict:
    """``run_id`` derives its date segment from ``date`` so the two never
    disagree -- the entries this file seeds are eviction-ordered by date,
    and a mismatched id would read as a bug in the fixture, not the code
    under test."""
    return {
        "run_id": f"iterate-{date[:10]}-{slug}",
        "date": date,
        "type": "feature",
        "complexity": "medium",
        "branch": f"iterate/{slug}",
        "spec": None,
        "tests_passed": True,
        "adr": None,
    }


def _seed_at_cap(project_root: Path) -> None:
    """Seed a project already at the retention cap -- identical content
    across every caller, so two independent seeds are byte-for-byte the
    same base a real shared ``origin/main`` tip would provide."""
    (project_root / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    d = iterates_dir(project_root)
    d.mkdir(parents=True)

    for i in range(ITERATE_RETENTION):
        day = (i // 24) + 1
        hour = i % 24
        run_id = f"iterate-2026-07-{day:02d}-seed{i:03d}"
        entry = {
            "run_id": run_id,
            "date": f"2026-07-{day:02d}T{hour:02d}:00:00Z",
            "type": "feature",
            "complexity": "small",
            "branch": f"iterate/seed{i}",
            "spec": None,
            "tests_passed": True,
            "adr": None,
        }
        (d / f"{run_id}.json").write_text(json.dumps(entry), encoding="utf-8")

    config = {
        "scope": "full_app",
        "iterate_history": [],
        MIGRATION_STATE_KEY: "complete",
        MIGRATION_TS_KEY: "2026-07-23T09:00:00Z",
    }
    (project_root / RUN_CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")


def _summary_names(project_root: Path) -> set[str]:
    return {
        p.name
        for p in iterates_dir(project_root).glob("iterate-*.json")
        if not p.name.endswith(".test-results.json")
    }


def _merged_overshoot_tree(tmp_path: Path) -> tuple[Path, dict, dict]:
    """Build the cap+1 merged tree the incident produced: two identically
    seeded worktrees each independently append+evict, then a fresh
    ``merged`` directory gets the base seed, the one agreed delete, and
    both branches' new (non-conflicting) adds -- the filesystem shape a
    real git merge of the two branches would leave behind."""
    branch_a = tmp_path / "branch_a"
    branch_b = tmp_path / "branch_b"
    _seed_at_cap(branch_a)
    _seed_at_cap(branch_b)
    seed_names = _summary_names(branch_a)
    assert seed_names == _summary_names(branch_b), (
        "both branches must start from an identical base set for this "
        "to reproduce the real race -- a divergent seed would not prove "
        "the same-oldest-eviction mechanism"
    )

    entry_a = _canonical_entry("mission-mobile-visual", date="2026-08-13T10:00:00Z")
    entry_b = _canonical_entry("changelog-manifest-config", date="2026-08-13T11:00:00Z")
    tool.append_iterate_entry(branch_a, entry_a)
    tool.append_iterate_entry(branch_b, entry_b)

    evicted_by_a = seed_names - _summary_names(branch_a)
    evicted_by_b = seed_names - _summary_names(branch_b)
    assert evicted_by_a == evicted_by_b and len(evicted_by_a) == 1, (
        "identical base + deterministic sort_key must evict the exact "
        "same oldest seed entry on both branches -- otherwise the merge "
        "would conflict instead of silently overshooting"
    )

    merged = tmp_path / "merged"
    _seed_at_cap(merged)
    for name in evicted_by_a:
        (iterates_dir(merged) / name).unlink()
    for branch, entry in ((branch_a, entry_a), (branch_b, entry_b)):
        src = iterates_dir(branch) / f"{entry['run_id']}.json"
        shutil.copy(src, iterates_dir(merged) / src.name)

    return merged, entry_a, entry_b


class TestRetentionMergeOvershoot:
    def test_two_independent_worktrees_merge_one_over_cap(self, tmp_path):
        """Two branches, same tip, each append+evict independently -- the
        merged tree lands at cap+1, reproducing the shipwright-webui
        incident. This is the failure this test pins; the next test proves
        it self-heals."""
        merged, entry_a, entry_b = _merged_overshoot_tree(tmp_path)

        merged_files = _summary_names(merged)
        assert len(merged_files) == ITERATE_RETENTION + 1, (
            f"expected the documented one-over-cap overshoot "
            f"({ITERATE_RETENTION + 1}), got {len(merged_files)}"
        )
        assert f"{entry_a['run_id']}.json" in merged_files
        assert f"{entry_b['run_id']}.json" in merged_files

    def test_next_append_on_the_merged_tree_self_heals_to_cap(self, tmp_path):
        """A subsequent append against the overshot merged directory reads
        the FULL on-disk state (not just what this call itself wrote) and
        re-applies retention -- the overshoot is bounded and transient, not
        an unbounded leak."""
        merged, entry_a, entry_b = _merged_overshoot_tree(tmp_path)
        assert len(_summary_names(merged)) == ITERATE_RETENTION + 1

        entry_c = _canonical_entry("next-run-on-main", date="2026-08-14T09:00:00Z")
        tool.append_iterate_entry(merged, entry_c)

        healed_files = _summary_names(merged)
        assert len(healed_files) == ITERATE_RETENTION, (
            "the append immediately after a merge must trim the merged "
            "directory back to the cap, not compound the overshoot"
        )
        healed_run_ids = {
            json.loads((iterates_dir(merged) / name).read_text())["run_id"]
            for name in healed_files
        }
        # The two branches' entries and the new one are the freshest by date
        # (2026-08-13/14 vs. the 2026-07 seed rows) so all three must survive.
        assert entry_a["run_id"] in healed_run_ids
        assert entry_b["run_id"] in healed_run_ids
        assert entry_c["run_id"] in healed_run_ids
