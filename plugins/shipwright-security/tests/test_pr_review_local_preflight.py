"""Tests for `pr_review.main()`'s local-preflight orchestration
(`--base`/`--diff-file`).

Same review logic as the required CI gate (FR-01.17), run against a branch
that has not been pushed or opened as a PR — see `pr_review_local`'s module
docstring for the "preflight, never a waiver" contract this suite pins:
no PR comment, no review state, no dismissal, and the same decision->exit
mapping as CI mode. `pr_review_local`'s own pure functions (`resolve_diff_mode`,
`build_local_diff`, ...) are tested in `test_pr_review_local_diff.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import pr_review  # noqa: E402
import pr_review_local  # noqa: E402

from _pr_review_local_fixtures import (  # noqa: E402
    FAKE_KEY, _git_init_only, _repo_with_branch_history,
)

# --- main() orchestration: local mode never posts, same decision->exit map ---


def _wire_local(monkeypatch, *, review_json=None, diff="diff --git a/x b/x\n+y\n"):
    """Same boundary set as `_wire` in test_pr_review_script.py, but a local
    run must never even CALL the posting boundaries — leaving them unpatched
    would raise if reached, which IS the assertion."""
    posted = {}
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    monkeypatch.setattr(pr_review, "load_prompts", lambda d: ("SYSTEM", "USER\n{PR_META}\n{DIFF}"))
    monkeypatch.setattr(pr_review, "resolve_extra_body", lambda model: {})

    def fake_call(api_key, model, messages, timeout=120, *, extra_body=None):
        posted["messages"] = messages
        return review_json

    monkeypatch.setattr(pr_review, "call_openrouter", fake_call)

    def _unexpected(*a, **k):  # pragma: no cover - assertion via failure
        raise AssertionError("local preflight must never call this CI-only boundary")

    monkeypatch.setattr(pr_review, "post_pr_comment", _unexpected)
    monkeypatch.setattr(pr_review, "post_pr_review_state", _unexpected)
    monkeypatch.setattr(pr_review, "read_reviewed_head", _unexpected)
    monkeypatch.setattr(pr_review, "dismiss_own_stale_verdicts", _unexpected)
    monkeypatch.setattr(pr_review, "fetch_pr_diff", _unexpected)
    return posted


class TestLocalPreflightOrchestration:

    def test_diff_file_approve_exits_0_no_posting(self, monkeypatch, tmp_path):
        diff_path = tmp_path / "x.diff"
        diff_path.write_text("diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n",
                             encoding="utf-8")
        _wire_local(monkeypatch, review_json=json.dumps(
            {"decision": "approve", "summary": "lgtm", "blocking": [], "comments": []}))
        rc = pr_review.main(["--diff-file", str(diff_path), "--prompt-dir", "shared/prompts/pr_reviewer"])
        assert rc == pr_review.EXIT_OK

    def test_diff_file_block_exits_1(self, monkeypatch, tmp_path):
        diff_path = tmp_path / "x.diff"
        diff_path.write_text("diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n",
                             encoding="utf-8")
        _wire_local(monkeypatch, review_json=json.dumps(
            {"decision": "block", "summary": "no", "blocking": ["b"], "comments": []}))
        rc = pr_review.main(["--diff-file", str(diff_path), "--prompt-dir", "shared/prompts/pr_reviewer"])
        assert rc == pr_review.EXIT_BLOCK

    def test_prints_preflight_banner_never_the_ci_body(self, monkeypatch, tmp_path, capsys):
        diff_path = tmp_path / "x.diff"
        diff_path.write_text("diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n",
                             encoding="utf-8")
        _wire_local(monkeypatch, review_json=json.dumps(
            {"decision": "approve", "summary": "lgtm", "blocking": [], "comments": []}))
        pr_review.main(["--diff-file", str(diff_path), "--prompt-dir", "shared/prompts/pr_reviewer"])
        captured = capsys.readouterr()
        assert "LOCAL PREFLIGHT" in captured.err
        assert "lgtm" in captured.out  # printed to stdout, not posted anywhere

    def test_prints_which_files_are_sent_before_the_model_call(self, monkeypatch, tmp_path, capsys):
        diff_path = tmp_path / "x.diff"
        diff_path.write_text("diff --git a/secret.env b/secret.env\n--- a/secret.env\n"
                             "+++ b/secret.env\n@@ -1 +1 @@\n-a\n+b\n", encoding="utf-8")
        _wire_local(monkeypatch, review_json=json.dumps(
            {"decision": "approve", "summary": "ok", "blocking": [], "comments": []}))
        pr_review.main(["--diff-file", str(diff_path), "--prompt-dir", "shared/prompts/pr_reviewer"])
        err = capsys.readouterr().err
        assert "sending 1 file section(s)" in err
        assert "secret.env" in err

    def test_truncated_local_diff_still_prints_banner_and_body(self, monkeypatch, tmp_path, capsys):
        # Regression: local mode's truncated-diff early return used to skip
        # post_local_result entirely, leaving a human with an exit code and
        # nothing else — caught by a live external-review probe, 2026-09-12.
        big = ("diff --git a/big.py b/big.py\n--- a/big.py\n+++ b/big.py\n"
              "@@ -1 +1 @@\n" + "+z" * pr_review.MAX_DIFF_CHARS + "\n")
        diff_path = tmp_path / "x.diff"
        diff_path.write_text(big, encoding="utf-8")
        _wire_local(monkeypatch, review_json=json.dumps(
            {"decision": "approve", "summary": "huge", "blocking": [], "comments": []}))
        rc = pr_review.main(["--diff-file", str(diff_path), "--prompt-dir", "shared/prompts/pr_reviewer"])
        assert rc == pr_review.EXIT_BLOCK
        captured = capsys.readouterr()
        assert "LOCAL PREFLIGHT" in captured.err
        assert "big.py" in captured.out  # the rendered review body, printed not posted

    def test_base_mode_reviews_the_merge_base_diff(self, monkeypatch, tmp_path):
        _repo_with_branch_history(tmp_path)
        posted = _wire_local(monkeypatch, review_json=json.dumps(
            {"decision": "approve", "summary": "lgtm", "blocking": [], "comments": []}))
        rc = pr_review.main(["--base", "main", "--project-root", str(tmp_path),
                             "--prompt-dir", "shared/prompts/pr_reviewer"])
        assert rc == pr_review.EXIT_OK
        # main() must actually send the merge-base diff, not just exit 0 on
        # whatever the fake model returns (code review, 2026-09-12).
        sent = str(posted["messages"])
        assert "feature.py" in sent and "untracked.py" in sent
        assert "shared.py" not in sent

    def test_unresolvable_base_exits_usage_not_error(self, monkeypatch, tmp_path):
        # A bad --base/--project-root is local misconfiguration, not model/
        # transport unavailability — must STOP (EXIT_USAGE), not read as the
        # advisory "reviewer infra unavailable" case (external review, 2026-09-12).
        _git_init_only(tmp_path)
        _wire_local(monkeypatch)
        rc = pr_review.main(["--base", "origin/does-not-exist", "--project-root", str(tmp_path),
                             "--prompt-dir", "shared/prompts/pr_reviewer"])
        assert rc == pr_review.EXIT_USAGE
        assert rc != pr_review.EXIT_ERROR

    def test_unreadable_diff_file_exits_usage_not_error(self, monkeypatch, tmp_path):
        _wire_local(monkeypatch)
        rc = pr_review.main(["--diff-file", str(tmp_path / "does-not-exist.diff"),
                             "--prompt-dir", "shared/prompts/pr_reviewer"])
        assert rc == pr_review.EXIT_USAGE
        assert rc != pr_review.EXIT_ERROR

    def test_empty_diff_fails_closed_without_posting(self, monkeypatch, tmp_path):
        diff_path = tmp_path / "x.diff"
        diff_path.write_text("", encoding="utf-8")
        posted = _wire_local(monkeypatch, review_json=json.dumps({"decision": "approve"}))
        rc = pr_review.main(["--diff-file", str(diff_path), "--prompt-dir", "shared/prompts/pr_reviewer"])
        assert rc == pr_review.EXIT_BLOCK
        assert "messages" not in posted  # the model was never consulted

    def test_pr_number_and_base_combined_exits_usage_not_error(self, monkeypatch):
        # EXIT_USAGE (3), never EXIT_ERROR (2) — F11 treats 2 as "reviewer
        # infra unavailable, advisory-only"; a bad invocation must not read as that.
        monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
        rc = pr_review.main(["--pr-number", "1", "--repo", "o/r", "--base", "main"])
        assert rc == pr_review.EXIT_USAGE
        assert rc != pr_review.EXIT_ERROR

    def test_no_mode_at_all_exits_usage(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
        rc = pr_review.main(["--prompt-dir", "shared/prompts/pr_reviewer"])
        assert rc == pr_review.EXIT_USAGE

    def test_argparse_level_usage_error_also_exits_usage_not_2(self, monkeypatch):
        # An actual argparse parse failure (not resolve_diff_mode's) used to
        # exit 2, indistinguishable from EXIT_ERROR (code review, 2026-09-12).
        monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
        rc = pr_review.main(["--timeout", "not-a-number"])
        assert rc == pr_review.EXIT_USAGE
        assert rc != pr_review.EXIT_ERROR

    def test_help_flag_still_exits_0(self):
        with pytest.raises(SystemExit) as exc:
            pr_review.main(["--help"])
        assert exc.value.code == 0

    def test_local_result_strips_control_chars_from_printed_body(self, capsys):
        # `summary` skips render_comment's own control-char stripping (inert
        # in a Markdown PR comment, not in a real terminal — code review, 2026-09-12).
        body = "line one\x1b[31mline two\x00"
        rc = pr_review_local.post_local_result("approve", 0, {"summary": "ok"}, body)
        assert rc == 0
        out = capsys.readouterr().out
        assert "\x1b" not in out and "\x00" not in out
        assert "line one" in out and "line two" in out
