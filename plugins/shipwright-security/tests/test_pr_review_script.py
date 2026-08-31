"""Tests for scripts/tools/pr_review.py — the Tier-3 PR reviewer (I/O + orchestration).

The OpenRouter-backed reviewer `.github/workflows/pr-review.yml` runs on Tier-3 PRs
(external contributors, sensitive paths, `needs-review` label). It must fetch the
diff, call OpenRouter, parse a strict-JSON decision, post a comment, and map that
decision to an exit code (0 approve/comment, 1 block, 2 error); dump the raw
response redacted and exit 2 on a parse failure; cut an over-cap diff at a FILE
BOUNDARY and FAIL CLOSED on the partial review that leaves, naming what went
unreviewed; and never log the API key. Pure helpers live in pr_review_lib.py /
pr_review_diff_filter.py with their own test modules; all network and `gh`
boundaries are monkeypatched, so the suite runs fully offline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))

import pr_review  # noqa: E402

# Deliberately NOT in any real credential format (no `sk-`/`ghp_`/`xox` prefix) so the
# repo's secret-scan hooks don't flag this synthetic fixture. Redaction is format-agnostic.
FAKE_KEY = "ORTESTKEY-not-a-real-credential-0123456789"


# --- File contract ---


class TestFileContract:

    def test_script_exists(self):
        assert (PLUGIN_ROOT / "scripts" / "tools" / "pr_review.py").exists()

    def test_shebang_present(self):
        first = (PLUGIN_ROOT / "scripts" / "tools" / "pr_review.py").read_text(
            encoding="utf-8"
        ).splitlines()[0]
        assert first == "#!/usr/bin/env python3", "missing python3 shebang"

    def test_uses_openrouter_key_not_anthropic(self):
        src = (PLUGIN_ROOT / "scripts" / "tools" / "pr_review.py").read_text(encoding="utf-8")
        assert "OPENROUTER_API_KEY" in src, "script must read OPENROUTER_API_KEY"
        assert "ANTHROPIC_API_KEY" not in src, (
            "script must not reference ANTHROPIC_API_KEY — OpenRouter is the single provider"
        )

    def test_every_re_exported_name_resolves(self):
        # The lib modules are reachable through `pr_review.<symbol>` — that is
        # the contract the workflow and every monkeypatching test rely on, and
        # a module split is exactly what silently breaks it.
        for name in pr_review.__all__:
            assert hasattr(pr_review, name), f"__all__ names {name}, which does not resolve"
        assert pr_review.DEFAULT_MODEL == pr_review.DEEPSEEK_MODEL


# --- main() orchestration — boundaries monkeypatched ---


def _wire(monkeypatch, *, review_json=None, diff="diff --git a b\n+x\n", raise_call=None):
    """Patch every external boundary; capture posted comment/review state."""
    posted = {}
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    # Isolate orchestration from the filesystem prompt files (cwd-dependent).
    monkeypatch.setattr(pr_review, "load_prompts", lambda d: ("SYSTEM", "USER\n{PR_META}\n{DIFF}"))
    monkeypatch.setattr(pr_review, "fetch_pr_diff", lambda pr, repo: diff)
    # This suite is about orchestration, not DeepSeek routing (that's
    # test_pr_review_deepseek_routing.py) — stub the resolver so these tests
    # don't depend on shared/config/external_review.json's health.
    monkeypatch.setattr(pr_review, "resolve_extra_body", lambda model: {})

    def fake_call(api_key, model, messages, timeout=120, *, extra_body=None):
        # Capture what actually reaches the MODEL. Asserting only on the posted
        # comment let the meta wiring rot silently: dropping the file lists from
        # the build_pr_meta call left the whole suite green.
        posted["messages"] = messages
        posted["extra_body"] = extra_body
        if raise_call is not None:
            raise raise_call
        return review_json

    monkeypatch.setattr(pr_review, "call_openrouter", fake_call)
    monkeypatch.setattr(
        pr_review, "post_pr_comment",
        lambda pr, repo, body: posted.update(comment=body),
    )
    monkeypatch.setattr(
        pr_review, "post_pr_review_state",
        lambda pr, repo, decision, summary: posted.update(state=decision),
    )
    # Clearing this reviewer's superseded verdicts talks to `gh`, and so does
    # reading the head it needs. Patched here only to keep this suite offline —
    # WHEN the cleanup may run is pinned in test_pr_review_stale_verdicts.py.
    monkeypatch.setattr(pr_review, "read_reviewed_head", lambda pr, repo: "headsha")
    monkeypatch.setattr(
        pr_review, "dismiss_own_stale_verdicts",
        lambda pr, repo, *, nonce, reviewed_sha: None,
    )
    return posted


ARGV = ["--pr-number", "42", "--repo", "owner/repo", "--prompt-dir", "shared/prompts/pr_reviewer"]


class TestMainOrchestration:

    def test_missing_api_key_exits_2(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        assert pr_review.main(ARGV) == 2

    def test_block_exits_1(self, monkeypatch):
        _wire(monkeypatch, review_json=json.dumps(
            {"decision": "block", "summary": "no", "blocking": ["b"], "comments": []}))
        assert pr_review.main(ARGV) == 1

    def test_approve_exits_0(self, monkeypatch):
        posted = _wire(monkeypatch, review_json=json.dumps(
            {"decision": "approve", "summary": "lgtm", "blocking": [], "comments": []}))
        assert pr_review.main(ARGV) == 0
        assert "lgtm" in posted["comment"]

    def test_comment_exits_0(self, monkeypatch):
        _wire(monkeypatch, review_json=json.dumps(
            {"decision": "comment", "summary": "nit", "blocking": [], "comments": ["c"]}))
        assert pr_review.main(ARGV) == 0

    def test_openrouter_error_exits_2(self, monkeypatch):
        _wire(monkeypatch, raise_call=RuntimeError("502 Bad Gateway"))
        assert pr_review.main(ARGV) == 2

    def test_json_parse_fail_exits_2_and_dumps_raw(self, monkeypatch, capsys):
        _wire(monkeypatch, review_json="<html>rate limited</html>")
        assert pr_review.main(ARGV) == 2
        err = capsys.readouterr().err
        assert "rate limited" in err  # raw response dumped to logs

    # DeepSeek ZDR routing gate tests moved to test_pr_review_deepseek_routing.py
    # to keep this module inside the file-size guideline.

    def test_truncation_fails_closed_needs_human(self, monkeypatch):
        # A partial diff means we did NOT see the whole change, so a large diff
        # must not bypass the gate by size — fail CLOSED even on a partial
        # APPROVE. Rationale in pr_review_lib.MAX_DIFF_CHARS.
        posted = _wire(
            monkeypatch,
            # A real over-cap diff WITH headers. A headerless one is now caught
            # earlier as "nothing to review", which is a different branch.
            diff=("diff --git a/big.py b/big.py\n--- a/big.py\n+++ b/big.py\n"
                  "@@ -1 +1 @@\n" + "+z" * pr_review.MAX_DIFF_CHARS + "\n"),
            review_json=json.dumps(
                {"decision": "approve", "summary": "huge", "blocking": [], "comments": []}),
        )
        rc = pr_review.main(ARGV)
        assert rc == pr_review.EXIT_BLOCK
        assert rc != pr_review.EXIT_OK  # the size-bypass is closed
        assert "review limit" in posted["comment"].lower()
        assert "big.py" in posted["comment"]     # says WHICH file went unreviewed
        assert posted["state"] == "block"  # forced request-changes on truncation

    def test_an_oversized_diff_names_the_unreviewed_file_in_every_sink(
            self, monkeypatch, capsys):
        # End to end: the file list survives truncation -> meta -> comment, and
        # both sinks are sanitised. Diff paths are PR-controlled and CI logs are
        # read in a terminal.
        def _s(p, body):
            return f"diff --git a/{p} b/{p}\n--- a/{p}\n+++ b/{p}\n@@ -1 +1 @@\n{body}\n"
        posted = _wire(monkeypatch, review_json=json.dumps({"decision": "approve"}),
                       diff=_s("s.py", "+y")
                       + _s("b\x1b[31mig.py", "+x" * pr_review.MAX_DIFF_CHARS))
        assert pr_review.main(ARGV) == pr_review.EXIT_BLOCK
        assert "ig.py" in posted["comment"]
        assert "\x1b" not in posted["comment"]
        assert "\x1b" not in capsys.readouterr().err
        # ...and the MODEL is told too, not just the human.
        assert "ig.py" in posted["messages"][1]["content"]

    def test_a_fully_filtered_pr_fails_closed(self, monkeypatch, capsys):
        # This script runs only on PRs the tier step said need review. If the
        # generated-artifact filter leaves nothing, the model would be handed an
        # empty diff — and the system prompt answers that with `approve`. A fork
        # PR touching only regenerated artifacts is the shape that matters.
        posted = _wire(monkeypatch, review_json=json.dumps({"decision": "approve"}),
                       diff="diff --git a/triage.jsonl b/triage.jsonl\n--- a/triage.jsonl\n"
                            "+++ b/triage.jsonl\n@@ -1 +1 @@\n-a\n+x\n")
        assert pr_review.main(ARGV) == pr_review.EXIT_BLOCK
        assert "messages" not in posted        # the model was never consulted
        assert "triage.jsonl" in capsys.readouterr().err

    def test_an_empty_fetch_fails_closed(self, monkeypatch, capsys):
        # The broadened gate, at its widest input. `gh pr diff` returning ''
        # used to satisfy neither half of the old narrow condition (nothing was
        # excluded, so `excluded and ...` was False), truncate_diff('') reports
        # complete, and the system prompt answers an empty diff with `approve`.
        posted = _wire(monkeypatch, review_json=json.dumps({"decision": "approve"}), diff="")
        assert pr_review.main(ARGV) == pr_review.EXIT_BLOCK
        assert "messages" not in posted          # the model was never consulted
        assert "no file sections at all" in capsys.readouterr().err

    def test_a_headerless_body_fails_closed(self, monkeypatch, capsys):
        # Same failure from the model's side: a `gh` body that carries no
        # LF-anchored `diff --git` header at all is also "nothing to review".
        posted = _wire(monkeypatch, review_json=json.dumps({"decision": "approve"}),
                       diff="warning: something went wrong\nno diff here\n")
        assert pr_review.main(ARGV) == pr_review.EXIT_BLOCK
        assert "messages" not in posted
        assert "no file sections at all" in capsys.readouterr().err

    def test_an_ordinary_pr_with_some_generated_files_still_runs(self, monkeypatch):
        # The fail-closed rule must not swing the other way: a PR that mixes a
        # genuinely generated artifact with real source is reviewed normally —
        # the generated section is dropped and disclosed, the source is sent.
        posted = _wire(monkeypatch, review_json=json.dumps({"decision": "approve"}),
                       diff="diff --git a/triage.jsonl b/triage.jsonl\n--- a/triage.jsonl\n"
                            "+++ b/triage.jsonl\n@@ -1 +1 @@\n-a\n+b\n"
                            "diff --git a/src/x.py b/src/x.py\n--- a/src/x.py\n"
                            "+++ b/src/x.py\n@@ -1 +1 @@\n-old\n+new\n")
        assert pr_review.main(ARGV) == pr_review.EXIT_OK
        assert "src/x.py" in posted["messages"][1]["content"]
        assert "excluded" in posted["comment"].lower()   # and the drop is disclosed

    def test_a_lockfile_only_pr_is_reviewed_not_filtered_away(self, monkeypatch):
        # Decision 4, end to end: `uv.lock` used to be filtered as generated, so
        # a fork PR touching only it left NOTHING to review. On the one gate
        # whose input is untrusted, the lockfile IS the supply-chain surface —
        # it must reach the model, and the run must not fail closed on "nothing
        # to review" either.
        posted = _wire(monkeypatch, review_json=json.dumps({"decision": "approve"}),
                       diff="diff --git a/uv.lock b/uv.lock\n--- a/uv.lock\n+++ b/uv.lock\n"
                            "@@ -1 +1 @@\n-name = \"safe-pkg\"\n+name = \"safe-pkq\"\n")
        assert pr_review.main(ARGV) == pr_review.EXIT_OK
        assert "safe-pkq" in posted["messages"][1]["content"], \
            "the lockfile change never reached the model"
        assert "excluded" not in posted["comment"].lower()

    def test_a_broken_template_exits_2_redacted_not_as_a_traceback(self, monkeypatch, capsys):
        # build_messages raises when the shipped template lost a placeholder.
        # That was the only boundary in main() not caught — it escaped as a raw
        # traceback, bypassing _redact and the documented exit-code table, and
        # was fail-closed only by the accident that exit 1 == EXIT_BLOCK.
        _wire(monkeypatch, review_json=json.dumps({"decision": "approve"}))
        monkeypatch.setattr(pr_review, "load_prompts",
                            lambda d: ("SYSTEM", "USER with no placeholders"))
        assert pr_review.main(ARGV) == pr_review.EXIT_ERROR
        err = capsys.readouterr().err
        assert "missing" in err
        assert "Traceback" not in err
        assert FAKE_KEY not in err

    def test_the_fail_closed_comment_does_not_credit_a_model(self, monkeypatch):
        # This branch returns BEFORE call_openrouter, so a footer naming the
        # model says a review happened that provably did not.
        posted = _wire(monkeypatch, review_json=json.dumps({"decision": "approve"}), diff="")
        assert pr_review.main(ARGV) == pr_review.EXIT_BLOCK
        assert pr_review.DEFAULT_MODEL not in posted["comment"]
        assert "nothing was sent" in posted["comment"]

    def test_api_key_never_logged(self, monkeypatch, capsys):
        # Force the worst path (error message embeds the key) and assert it is
        # never present in any captured output.
        _wire(monkeypatch, raise_call=RuntimeError(f"boom with {FAKE_KEY} in message"))
        pr_review.main(ARGV)
        captured = capsys.readouterr()
        assert FAKE_KEY not in captured.out
        assert FAKE_KEY not in captured.err

    def test_generated_files_excluded_lets_review_run(self, monkeypatch):
        # THE root-fix behavior (trg-e1c554d9): a diff that WOULD truncate
        # (dominated by a regenerated compliance artifact) fits once generated
        # noise is dropped — so the review RUNS (exit 0 on approve) instead of
        # failing closed on truncation, and the comment discloses the exclusion.
        big_generated = (
            "diff --git a/.shipwright/compliance/test-evidence.md "
            "b/.shipwright/compliance/test-evidence.md\n"
            "--- a/.shipwright/compliance/test-evidence.md\n"
            "+++ b/.shipwright/compliance/test-evidence.md\n"
            "@@ -1 +1 @@\n" + "+x\n" * 120_000
        )
        source = "diff --git a/shared/real.py b/shared/real.py\n--- a/shared/real.py\n+++ b/shared/real.py\n@@ -1 +1 @@\n+code\n"
        posted = _wire(
            monkeypatch, diff=big_generated + source,
            review_json=json.dumps(
                {"decision": "approve", "summary": "lgtm", "blocking": [], "comments": []}))
        assert pr_review.main(ARGV) == pr_review.EXIT_OK  # NOT blocked by truncation
        assert "truncat" not in posted["comment"].lower()
        assert "excluded" in posted["comment"].lower()
