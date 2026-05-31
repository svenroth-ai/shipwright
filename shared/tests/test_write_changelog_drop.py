"""Tests for shared/scripts/tools/write_changelog_drop.py."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tools.write_changelog_drop import (
    ALLOWED_CATEGORIES,
    ChangelogDropError,
    category_dir,
    drop_dir,
    write_changelog_drop,
)


class TestWrite:
    def test_happy_path_creates_counter_001_file(self, tmp_path):
        path = write_changelog_drop(
            tmp_path, "iterate-2026-04-23-feat-x", "Added", "New thing"
        )
        assert path.name == "iterate-2026-04-23-feat-x_001.md"
        assert path.read_text(encoding="utf-8") == "New thing\n"
        assert path.parent == category_dir(tmp_path, "Added")

    def test_second_bullet_same_run_id_gets_counter_002(self, tmp_path):
        write_changelog_drop(
            tmp_path, "iterate-2026-04-23-multi", "Added", "First bullet"
        )
        second = write_changelog_drop(
            tmp_path, "iterate-2026-04-23-multi", "Added", "Second bullet"
        )
        assert second.name == "iterate-2026-04-23-multi_002.md"
        assert second.read_text(encoding="utf-8") == "Second bullet\n"

        # First file must still be there — no silent overwrite.
        first_path = second.parent / "iterate-2026-04-23-multi_001.md"
        assert first_path.exists()
        assert first_path.read_text(encoding="utf-8") == "First bullet\n"

    def test_different_categories_get_independent_counters(self, tmp_path):
        added = write_changelog_drop(
            tmp_path, "iterate-2026-04-23-both", "Added", "added bullet"
        )
        fixed = write_changelog_drop(
            tmp_path, "iterate-2026-04-23-both", "Fixed", "fixed bullet"
        )
        assert added.name.endswith("_001.md")
        assert fixed.name.endswith("_001.md")
        assert added.parent != fixed.parent

    def test_rejects_empty_bullet(self, tmp_path):
        with pytest.raises(ChangelogDropError, match="empty"):
            write_changelog_drop(
                tmp_path, "iterate-2026-04-23-e", "Added", "   \n  "
            )

    def test_rejects_unknown_category(self, tmp_path):
        with pytest.raises(ChangelogDropError, match="unknown category"):
            write_changelog_drop(
                tmp_path, "iterate-2026-04-23-c", "Fixd", "bullet"
            )

    def test_strips_surrounding_whitespace(self, tmp_path):
        path = write_changelog_drop(
            tmp_path, "iterate-2026-04-23-ws", "Changed", "\n\n  Indented bullet  \n\n"
        )
        assert path.read_text(encoding="utf-8") == "Indented bullet\n"


class TestPathSafety:
    def test_run_id_with_path_separator_is_sanitized(self, tmp_path):
        """Even if the caller passes a run_id containing slashes, the final
        write path must stay under CHANGELOG-unreleased.d/<category>/."""
        malicious = "iterate-../../../etc/passwd"
        path = write_changelog_drop(tmp_path, malicious, "Added", "payload")
        resolved = path.resolve()
        base = drop_dir(tmp_path).resolve()
        assert base in resolved.parents

    def test_run_id_with_windows_style_traversal_is_sanitized(self, tmp_path):
        path = write_changelog_drop(
            tmp_path, "iterate-x\\..\\..\\config", "Security", "payload"
        )
        resolved = path.resolve()
        base = drop_dir(tmp_path).resolve()
        assert base in resolved.parents

    def test_run_id_with_null_byte_does_not_create_dangerous_path(self, tmp_path):
        path = write_changelog_drop(
            tmp_path, "iterate-2026-04-23-\x00null", "Added", "payload"
        )
        assert "\x00" not in str(path)
        assert path.exists()


class TestAllowedCategories:
    def test_all_six_keep_a_changelog_categories_are_writable(self, tmp_path):
        for category in ALLOWED_CATEGORIES:
            path = write_changelog_drop(
                tmp_path,
                f"iterate-2026-04-23-cat-{category.lower()}",
                category,
                f"bullet for {category}",
            )
            assert path.parent.name == category

    def test_allowlist_matches_keep_a_changelog_spec(self):
        """Guard against accidental drift with append_changelog_entry.py."""
        assert ALLOWED_CATEGORIES == frozenset(
            {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"}
        )


class TestConcurrentWrites:
    def test_parallel_writes_never_collide(self, tmp_path):
        """Eight threads each write one bullet against the same run_id +
        category. All must succeed, all eight files must exist, and the
        counter values must be the 8 integers 001..008 with no duplicates
        and no gaps."""
        n = 8
        barrier = threading.Barrier(n)
        run_id = "iterate-2026-04-23-parallel"

        def worker(i: int) -> Path:
            barrier.wait(timeout=5.0)
            return write_changelog_drop(
                tmp_path, run_id, "Added", f"bullet from thread {i}"
            )

        with ThreadPoolExecutor(max_workers=n) as pool:
            # Submit all first so the barrier actually has n waiters.
            futures = [pool.submit(worker, i) for i in range(n)]
            paths = [f.result(timeout=15) for f in futures]

        filenames = {p.name for p in paths}
        assert len(filenames) == n  # all unique

        cat_files = sorted(
            category_dir(tmp_path, "Added").glob(f"{run_id}_*.md")
        )
        counters = [
            int(p.name.removeprefix(run_id + "_").removesuffix(".md"))
            for p in cat_files
        ]
        assert sorted(counters) == list(range(1, n + 1))
