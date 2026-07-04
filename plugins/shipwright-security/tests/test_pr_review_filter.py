"""Tests for filter_generated_paths / is_generated_path in pr_review_lib.py.

Root fix for the Tier-3 truncation false-positive (triage trg-e1c554d9): a
medium+ shipwright PR diff is dominated (~82% of chars, measured on PR #310) by
producer-REGENERATED artifacts (compliance MDs, agent-docs, lockfiles, state
logs) that carry no reviewable logic. Dropping those file-sections from the diff
BEFORE the truncation check keeps the reviewer under MAX_DIFF_CHARS AND focuses
it on real code. Split into its own test module (kept test_pr_review_lib.py
under the source-size guideline).
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import pr_review_lib as L  # noqa: E402


def _section(path: str, body: str = "@@ -1 +1 @@\n-old\n+new\n") -> str:
    return f"diff --git a/{path} b/{path}\nindex 111..222 100644\n--- a/{path}\n+++ b/{path}\n{body}"


class TestIsGeneratedPath:
    def test_compliance_prefix(self):
        assert L.is_generated_path(".shipwright/compliance/dashboard.md")

    def test_agent_docs_prefix(self):
        assert L.is_generated_path(".shipwright/agent_docs/session_handoff.md")

    def test_changelog_drops_prefix(self):
        assert L.is_generated_path("CHANGELOG-unreleased.d/Added/foo_001.md")

    def test_lockfile_basename(self):
        assert L.is_generated_path("uv.lock")
        assert L.is_generated_path("plugins/shipwright-grade/uv.lock")

    def test_state_logs(self):
        assert L.is_generated_path("shipwright_test_results.json")
        assert L.is_generated_path("shipwright_events.jsonl")
        assert L.is_generated_path(".shipwright/triage.jsonl")

    def test_real_source_not_generated(self):
        assert not L.is_generated_path("shared/scripts/tools/measure_diff_coverage.py")
        assert not L.is_generated_path("plugins/shipwright-security/scripts/lib/pr_review_lib.py")
        assert not L.is_generated_path(".github/workflows/ci.yml")
        # a hand-authored planning doc / roadmap is source, not generated
        assert not L.is_generated_path(".shipwright/planning/diff-coverage-roadmap.md")


class TestFilterGeneratedPaths:
    def test_drops_generated_keeps_source(self):
        diff = (
            _section("shared/scripts/tools/foo.py")
            + _section(".shipwright/compliance/dashboard.md")
            + _section("uv.lock")
            + _section("plugins/x/bar.py")
        )
        filtered, excluded = L.filter_generated_paths(diff)
        assert "shared/scripts/tools/foo.py" in filtered
        assert "plugins/x/bar.py" in filtered
        assert ".shipwright/compliance/dashboard.md" not in filtered
        assert "uv.lock" not in filtered
        assert excluded == [".shipwright/compliance/dashboard.md", "uv.lock"]

    def test_all_source_unchanged(self):
        diff = _section("a/x.py") + _section("b/y.py")
        filtered, excluded = L.filter_generated_paths(diff)
        assert filtered == diff
        assert excluded == []

    def test_no_headers_returned_unchanged(self):
        # A diff with no `diff --git` headers (unexpected) is passed through.
        diff = "not a diff at all\njust text\n"
        filtered, excluded = L.filter_generated_paths(diff)
        assert filtered == diff
        assert excluded == []

    def test_excluded_is_sorted_and_deduped(self):
        diff = _section("uv.lock") + _section(".shipwright/agent_docs/x.md") + _section("uv.lock")
        _, excluded = L.filter_generated_paths(diff)
        assert excluded == [".shipwright/agent_docs/x.md", "uv.lock"]

    def test_deleted_generated_file_excluded(self):
        # A deletion has `+++ /dev/null`; path must resolve from the `--- a/` side.
        diff = (
            "diff --git a/uv.lock b/uv.lock\n"
            "deleted file mode 100644\n"
            "index 111..000\n"
            "--- a/uv.lock\n"
            "+++ /dev/null\n"
            "@@ -1 +0,0 @@\n-gone\n"
        ) + _section("keep/me.py")
        filtered, excluded = L.filter_generated_paths(diff)
        assert excluded == ["uv.lock"]
        assert "keep/me.py" in filtered

    def test_new_generated_file_excluded(self):
        # An addition has `--- /dev/null`; path resolves from the `+++ b/` side.
        diff = (
            "diff --git a/CHANGELOG-unreleased.d/Added/x_001.md b/CHANGELOG-unreleased.d/Added/x_001.md\n"
            "new file mode 100644\n"
            "index 000..111\n"
            "--- /dev/null\n"
            "+++ b/CHANGELOG-unreleased.d/Added/x_001.md\n"
            "@@ -0,0 +1 @@\n+added\n"
        )
        filtered, excluded = L.filter_generated_paths(diff)
        assert excluded == ["CHANGELOG-unreleased.d/Added/x_001.md"]
        assert filtered.strip() == ""  # everything excluded

    def test_rename_real_source_into_generated_dir_is_kept(self):
        # Codex review SHOULD-FIX: a rename that MOVES real source into a
        # generated dir must NOT be silently dropped — the real code (and the
        # suspicious move itself) must stay reviewable. Exclude only when EVERY
        # touched path is generated.
        diff = (
            "diff --git a/plugins/x/real.py b/.shipwright/compliance/real.py\n"
            "similarity index 100%\n"
            "rename from plugins/x/real.py\n"
            "rename to .shipwright/compliance/real.py\n"
        )
        filtered, excluded = L.filter_generated_paths(diff)
        assert filtered == diff       # kept in full
        assert excluded == []         # real source side wins

    def test_rename_generated_to_generated_still_excluded(self):
        # A rename where BOTH ends are generated carries no reviewable logic.
        diff = (
            "diff --git a/.shipwright/agent_docs/old.md b/.shipwright/agent_docs/new.md\n"
            "similarity index 100%\n"
            "rename from .shipwright/agent_docs/old.md\n"
            "rename to .shipwright/agent_docs/new.md\n"
        )
        _, excluded = L.filter_generated_paths(diff)
        assert excluded == [".shipwright/agent_docs/new.md", ".shipwright/agent_docs/old.md"]

    def test_filtering_lets_a_big_diff_fit_under_cap(self):
        # The whole point: a diff that WOULD truncate fits once generated noise
        # is dropped, so the review runs instead of failing closed.
        big_generated = _section(
            ".shipwright/compliance/test-evidence.md", body="@@ -1 +1 @@\n" + "+x\n" * 120_000)
        small_source = _section("shared/real.py")
        diff = big_generated + small_source
        assert len(diff) > L.MAX_DIFF_CHARS
        filtered, excluded = L.filter_generated_paths(diff)
        assert len(filtered) < L.MAX_DIFF_CHARS
        _, truncated = L.truncate_diff(filtered)
        assert truncated is False
        assert excluded == [".shipwright/compliance/test-evidence.md"]
