"""End-to-end proof that the file-per-iterate refactor eliminates the
iterate_history and CHANGELOG.md merge hotspots.

Two real git branches each run a full iterate-finalize touch (append an
entry + write a changelog drop). The test then merges the second branch
into the first and asserts that git reports no conflicts and both
contributions are present.

Covered scenarios (the ones GPT-R2 #15 + Gemini-R1 #1 flagged as
under-tested in the original plan):

1. Steady-state parallel finalize on already-migrated projects.
2. First-migration-on-both-branches: each branch independently triggers
   the legacy-array → dir migration. Both must converge on a consistent
   final state when merged.
3. Aggregation-while-drop-write: the aggregator runs on one branch while
   another branch is adding new drops. Only the snapshot set is deleted.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.iterate_entry import (  # noqa: E402
    MIGRATION_STATE_KEY,
    RUN_CONFIG_NAME,
    iterates_dir,
)
from tools.aggregate_changelog import aggregate  # noqa: E402
from tools.append_iterate_entry import append_iterate_entry  # noqa: E402
from tools.write_changelog_drop import write_changelog_drop  # noqa: E402


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "Integration Test"
    env["GIT_AUTHOR_EMAIL"] = "integration@test"
    env["GIT_COMMITTER_NAME"] = "Integration Test"
    env["GIT_COMMITTER_EMAIL"] = "integration@test"
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {result.stderr}\n{result.stdout}"
        )
    return result


def _initial_changelog() -> str:
    return (
        "# Changelog\n"
        "\n"
        "All notable changes to this project will be documented in this file.\n"
        "\n"
    )


def _build_repo(tmp_path: Path, *, legacy_array: list[dict] | None = None) -> Path:
    """Create a bare git repo with a commit on main.

    When ``legacy_array`` is supplied, the initial commit seeds a legacy
    ``iterate_history`` array on ``shipwright_run_config.json`` so the
    first append per branch triggers a migration under its own lock.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.email", "integration@test")
    _git(repo, "config", "user.name", "Integration Test")

    (repo / ".shipwright" / "agent_docs").mkdir(parents=True)
    config: dict = {"scope": "full_app"}
    if legacy_array is not None:
        config["iterate_history"] = legacy_array
    else:
        config["iterate_history"] = []
        config[MIGRATION_STATE_KEY] = "complete"
    (repo / RUN_CONFIG_NAME).write_text(json.dumps(config, indent=2), encoding="utf-8")
    (repo / "CHANGELOG.md").write_text(_initial_changelog(), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed")
    return repo


def _canonical_entry(slug: str, date: str) -> dict:
    return {
        "run_id": f"iterate-2026-05-{slug}",
        "date": date,
        "type": "feature",
        "complexity": "small",
        "branch": f"iterate/{slug}",
        "spec": None,
        "tests_passed": True,
        "adr": None,
    }


def _finalize_on_branch(
    repo: Path,
    branch_name: str,
    entry: dict,
    changelog_category: str,
    bullet: str,
) -> None:
    """Simulate iterate finalize on a fresh branch and commit the artifacts."""
    _git(repo, "checkout", "-b", branch_name, "main")
    append_iterate_entry(repo, entry)
    write_changelog_drop(repo, entry["run_id"], changelog_category, bullet)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", f"feat({branch_name}): {bullet}")


class TestSteadyStateParallel:
    """Both branches start from an already-migrated project."""

    def test_two_independent_iterates_merge_without_conflict(self, tmp_path):
        repo = _build_repo(tmp_path)

        entry_a = _canonical_entry("01-alpha", "2026-05-01T10:00:00Z")
        entry_b = _canonical_entry("02-beta", "2026-05-02T10:00:00Z")

        _finalize_on_branch(repo, "iterate/alpha", entry_a, "Added", "alpha bullet")
        _git(repo, "checkout", "main")
        _finalize_on_branch(repo, "iterate/beta", entry_b, "Fixed", "beta bullet")

        # Merge beta back into alpha.
        _git(repo, "checkout", "iterate/alpha")
        merge = _git(repo, "merge", "iterate/beta", "--no-edit", check=False)

        assert merge.returncode == 0, (
            f"merge conflict surfaced — file-per-iterate refactor failed.\n"
            f"stderr: {merge.stderr}\nstdout: {merge.stdout}"
        )

        status = _git(repo, "status", "--porcelain")
        assert status.stdout.strip() == "", "merge left dirty state behind"

        # Both entry files must be present at the merge tip.
        files = sorted(iterates_dir(repo).glob("iterate-*.json"))
        run_ids = {json.loads(p.read_text())["run_id"] for p in files}
        assert "iterate-2026-05-01-alpha" in run_ids
        assert "iterate-2026-05-02-beta" in run_ids

        # Both changelog drops must be present at the merge tip.
        drop_files = sorted((repo / "CHANGELOG-unreleased.d").rglob("*.md"))
        bullets = {p.read_text(encoding="utf-8").strip() for p in drop_files}
        assert "alpha bullet" in bullets
        assert "beta bullet" in bullets


class TestFirstMigrationOnBothBranches:
    """Both branches inherit a legacy iterate_history array and migrate
    independently. The resulting commits must still merge cleanly because
    legacy rows become their own files — no shared array to conflict on.
    """

    def test_migration_on_both_branches_merges_cleanly(self, tmp_path):
        legacy = [
            _canonical_entry("00-seed-a", "2026-04-01T10:00:00Z"),
            _canonical_entry("00-seed-b", "2026-04-02T10:00:00Z"),
        ]
        repo = _build_repo(tmp_path, legacy_array=legacy)

        new_a = _canonical_entry("01-alpha", "2026-05-01T10:00:00Z")
        new_b = _canonical_entry("02-beta", "2026-05-02T10:00:00Z")

        _finalize_on_branch(repo, "iterate/alpha", new_a, "Added", "alpha bullet")
        _git(repo, "checkout", "main")
        _finalize_on_branch(repo, "iterate/beta", new_b, "Added", "beta bullet")

        _git(repo, "checkout", "iterate/alpha")
        merge = _git(repo, "merge", "iterate/beta", "--no-edit", check=False)
        assert merge.returncode == 0, (
            f"first-migration-on-both-branches produced a conflict.\n"
            f"stderr: {merge.stderr}"
        )

        status = _git(repo, "status", "--porcelain")
        assert status.stdout.strip() == ""

        # Both migrated-legacy + both new entries present.
        run_ids = {
            json.loads(p.read_text())["run_id"]
            for p in iterates_dir(repo).glob("iterate-*.json")
        }
        assert run_ids == {
            "iterate-2026-05-00-seed-a",
            "iterate-2026-05-00-seed-b",
            "iterate-2026-05-01-alpha",
            "iterate-2026-05-02-beta",
        }

        # The legacy array was emptied on both branches; merged state
        # preserves that (no dangling array entries).
        config = json.loads((repo / RUN_CONFIG_NAME).read_text(encoding="utf-8"))
        assert config["iterate_history"] == []
        assert config[MIGRATION_STATE_KEY] == "complete"


class TestAggregatorPreservesInFlightDrops:
    """The aggregator runs on branch A while branch B has already committed
    additional drop files. B's drops live in the merged tree and must
    survive A's aggregation (selective cleanup)."""

    def test_aggregator_does_not_delete_drops_outside_its_snapshot(self, tmp_path):
        repo = _build_repo(tmp_path)

        entry_a = _canonical_entry("01-alpha", "2026-05-01T10:00:00Z")
        entry_b = _canonical_entry("02-beta", "2026-05-02T10:00:00Z")

        _finalize_on_branch(repo, "iterate/alpha", entry_a, "Added", "alpha bullet")
        _git(repo, "checkout", "main")
        _finalize_on_branch(repo, "iterate/beta", entry_b, "Fixed", "beta bullet")

        # Merge beta into alpha so both drops are present in the tree.
        _git(repo, "checkout", "iterate/alpha")
        merge = _git(repo, "merge", "iterate/beta", "--no-edit", check=False)
        assert merge.returncode == 0

        # Place a THIRD drop manually to simulate "new bullet written
        # between snapshot and cleanup". We write it after the snapshot
        # semantically by monkey-patching the snapshot phase so the
        # aggregator doesn't see it.
        extra = write_changelog_drop(
            repo, "iterate-2026-05-03-late", "Added", "late bullet"
        )

        # Patch the aggregator's snapshot to exclude the "late" drop —
        # emulating the race where it was written after the snapshot.
        import tools.aggregate_changelog as mod

        real_snapshot = mod._snapshot_drop_files

        def partial_snapshot(project_root):
            by_cat, processed = real_snapshot(project_root)
            processed = [p for p in processed if p != extra]
            for cat in list(by_cat):
                by_cat[cat] = [
                    item for item in by_cat[cat]
                    if item[1].strip() != "late bullet"
                ]
                if not by_cat[cat]:
                    del by_cat[cat]
            return by_cat, processed

        try:
            mod._snapshot_drop_files = partial_snapshot
            result = aggregate(repo, "0.3.0", release_date="2026-05-10")
        finally:
            mod._snapshot_drop_files = real_snapshot

        # Released: alpha + beta. Not-released: late (stays for next round).
        assert result["changelog_updated"] is True
        changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
        assert "alpha bullet" in changelog
        assert "beta bullet" in changelog
        assert "late bullet" not in changelog

        # The "late" drop file is still on disk.
        assert extra.exists(), "aggregator deleted an out-of-snapshot drop"
