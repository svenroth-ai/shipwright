"""Unit tests for ``lib.rebase_cascade`` (campaign-dag-scheduler R5b round 7):
the rebase-cascade counter + exhaustion decision extracted out of
campaign-mode.md step 3f-bis's inline bash, per Tier-3 review's demand for
executable (not prose-only) coverage of the conflict/rebase path.
"""

from __future__ import annotations

from lib.rebase_cascade import decide_rebase_action, read_rebase_count, write_rebase_count


class TestReadRebaseCount:
    def test_missing_file_reads_as_zero(self, tmp_path):
        assert read_rebase_count(tmp_path / "does-not-exist") == 0

    def test_missing_run_dir_reads_as_zero(self, tmp_path):
        assert read_rebase_count(tmp_path) == 0

    def test_reads_a_persisted_count(self, tmp_path):
        write_rebase_count(tmp_path, 1)
        assert read_rebase_count(tmp_path) == 1

    def test_non_numeric_contents_read_as_zero(self, tmp_path):
        """Mirrors the shell's own `case $rebase_count in ''|*[!0-9]*) rebase_count=0;;` guard."""
        run_dir = tmp_path
        run_dir.mkdir(exist_ok=True)
        (run_dir / "rebase_count").write_text("not-a-number\n", encoding="utf-8")
        assert read_rebase_count(run_dir) == 0

    def test_empty_file_reads_as_zero(self, tmp_path):
        run_dir = tmp_path
        run_dir.mkdir(exist_ok=True)
        (run_dir / "rebase_count").write_text("", encoding="utf-8")
        assert read_rebase_count(run_dir) == 0


class TestWriteRebaseCount:
    def test_creates_the_run_dir_if_missing(self, tmp_path):
        run_dir = tmp_path / "nested" / "run"
        write_rebase_count(run_dir, 1)
        assert read_rebase_count(run_dir) == 1

    def test_round_trips_through_read(self, tmp_path):
        write_rebase_count(tmp_path, 2)
        assert read_rebase_count(tmp_path) == 2
        write_rebase_count(tmp_path, 0)
        assert read_rebase_count(tmp_path) == 0


class TestDecideRebaseAction:
    def test_below_the_cap_rebases(self):
        assert decide_rebase_action(0) == "rebase"
        assert decide_rebase_action(1) == "rebase"

    def test_at_the_cap_is_exhausted(self):
        """The exact boundary the bash `[ "$rebase_count" -ge 2 ]` implements —
        the third CONFLICTING result (rebase_count already at 2) exhausts
        the cascade, not the fourth."""
        assert decide_rebase_action(2) == "exhausted"

    def test_past_the_cap_is_still_exhausted(self):
        assert decide_rebase_action(3) == "exhausted"

    def test_custom_cap_is_respected(self):
        assert decide_rebase_action(4, max_rebase_reviews=5) == "rebase"
        assert decide_rebase_action(5, max_rebase_reviews=5) == "exhausted"
