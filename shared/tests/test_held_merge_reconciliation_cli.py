"""CLI/subprocess-boundary tests for ``lib.held_merge_reconciliation``
(campaign-dag-scheduler R5b, round 7 diff-coverage gate): ``_real_gh_query``,
``_real_mark_merged`` and ``main`` are the literal entrypoint
`campaign-mode.md` shells out to via `uv run ...`. Split out of
`test_held_merge_reconciliation.py` when it crossed the 300-line guideline
— that file keeps the pure `find_reconcilable_held`/`poll_for_merged_sha`/
`reconcile` coverage.
"""

from __future__ import annotations

import json
import subprocess

from lib.held_merge_reconciliation import _real_gh_query, _real_mark_merged, main


class TestRealGhQuery:
    """The one subprocess boundary in this module -- monkeypatched at the
    `subprocess.run` layer, not the business logic (already exercised
    directly in the sibling file)."""

    def test_parses_a_successful_gh_response(self, monkeypatch):
        def fake_run(cmd, cwd, capture_output, text, check):
            assert cmd[:3] == ["gh", "pr", "view"]
            assert cmd[3] == "iterate/A"
            assert cwd == "/wt"
            return subprocess.CompletedProcess(cmd, 0, stdout='{"state": "MERGED", "mergeCommit": {"oid": "abc"}}')

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert _real_gh_query("iterate/A", "/wt") == {"state": "MERGED", "mergeCommit": {"oid": "abc"}}

    def test_returns_none_on_a_nonzero_gh_exit(self, monkeypatch):
        def fake_run(*_a, **_k):
            raise subprocess.CalledProcessError(1, ["gh"])

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert _real_gh_query("iterate/A", "/wt") is None

    def test_returns_none_when_gh_is_not_installed(self, monkeypatch):
        def fake_run(*_a, **_k):
            raise OSError("gh: command not found")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert _real_gh_query("iterate/A", "/wt") is None

    def test_returns_none_on_unparseable_output(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run",
                             lambda *_a, **_k: subprocess.CompletedProcess([], 0, stdout="not json"))
        assert _real_gh_query("iterate/A", "/wt") is None


class TestRealMarkMerged:
    def test_builds_the_expected_loop_claim_invocation(self, tmp_path, monkeypatch):
        captured = {}

        def fake_run(cmd):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(subprocess, "run", fake_run)
        ok = _real_mark_merged("A", "sha123", state_path=tmp_path / "loop_state.json",
                                project_root="/proj", shared_root="/shared")
        assert ok is True
        cmd = captured["cmd"]
        assert "mark" in cmd
        assert "--status" in cmd and "merged" in cmd
        assert "--merged-commit" in cmd and "sha123" in cmd
        assert "--reason-code" in cmd and "held_merge_reconciled" in cmd
        assert "--campaign-worktree" in cmd and "/proj" in cmd

    def test_returns_false_on_a_nonzero_exit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda cmd: subprocess.CompletedProcess(cmd, 1))
        ok = _real_mark_merged("A", "sha123", state_path=tmp_path / "loop_state.json",
                                project_root="/proj", shared_root="/shared")
        assert ok is False


class TestMainCLI:
    """`campaign-mode.md` shells out to this script directly -- exercised
    here through `main(argv)` with the two subprocess-facing functions
    swapped for fakes."""

    def test_wires_state_loading_and_reconciliation_together(self, tmp_path, monkeypatch, capsys):
        state_path = tmp_path / "loop_state.json"
        state_path.write_text(json.dumps({"units": [
            {"id": "A", "status": "held", "reason_code": "drain_timeout", "branch": "iterate/A", "worktree": None},
        ]}), encoding="utf-8")

        monkeypatch.setattr(
            "lib.held_merge_reconciliation._real_gh_query",
            lambda branch, cwd: {"state": "MERGED", "mergeCommit": {"oid": "sha-a"}},
        )
        monkeypatch.setattr(
            "lib.held_merge_reconciliation._real_mark_merged",
            lambda unit_id, merged_sha, **_kw: True,
        )

        rc = main([
            "--state", str(state_path), "--project-root", "/proj", "--shared-root", "/shared",
            "--poll-interval-seconds", "0",
        ])
        assert rc == 0
        assert "reconciled A -> merged (sha-a)" in capsys.readouterr().out

    def test_prints_nothing_when_nothing_is_reconciled(self, tmp_path, monkeypatch, capsys):
        state_path = tmp_path / "loop_state.json"
        state_path.write_text(json.dumps({"units": [{"id": "A", "status": "merged"}]}), encoding="utf-8")

        rc = main(["--state", str(state_path), "--project-root", "/proj", "--shared-root", "/shared"])
        assert rc == 0
        assert capsys.readouterr().out == ""
