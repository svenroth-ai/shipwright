"""`tools/review_via_codex.py` — the CLI entry point AC1's dispatch sites
invoke, wrapping `lib.codex_review_transport.run_codex_review`.

Exercises `main()` in-process (not via a real subprocess) — the underlying
`codex exec` call is already covered end-to-end by
`test_codex_review_transport.py`; this file tests argument wiring: the agent
`.md` and the review subject (spec/diff or plan/spec) are read and passed
through `build_prompt()`, and the JSON result lands on stdout with the right
exit code.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib import codex_review_transport as transport  # noqa: E402
from tools import review_via_codex  # noqa: E402

VALID_CODE_REVIEW = {"section": "s1", "review": []}


def _patch_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transport, "is_codex_available", lambda **kw: (True, ""))
    monkeypatch.setattr(transport, "_resolve_codex_binary", lambda: "codex")


def test_success_prints_json_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_available(monkeypatch)
    agent_md = tmp_path / "code-reviewer.md"
    agent_md.write_text("---\nmodel: inherit\n---\nReview the diff.", encoding="utf-8")
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("the spec contract", encoding="utf-8")
    diff_file = tmp_path / "the.diff"
    diff_file.write_text("+ added line", encoding="utf-8")
    captured_prompt = {}

    def _run(argv, input, capture_output, encoding, errors, timeout, env):  # noqa: A002
        captured_prompt["prompt"] = input
        out_path = Path(argv[argv.index("-o") + 1])
        out_path.write_text(json.dumps(VALID_CODE_REVIEW), encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(transport.subprocess, "run", Mock(side_effect=_run))

    exit_code = review_via_codex.main([
        "--role", "code", "--worktree-root", str(tmp_path),
        "--agent-md", str(agent_md), "--out-dir", str(tmp_path),
        "--spec-file", str(spec_file), "--diff-file", str(diff_file),
    ])

    assert exit_code == 0
    stdout = capsys.readouterr().out
    result = json.loads(stdout)
    assert result["status"] == "completed"
    assert result["canonical_path"] == str(tmp_path / "code_review_reply.json")
    # Frontmatter stripped, review subject + transport addendum appended.
    assert "model: inherit" not in captured_prompt["prompt"]
    assert "Review the diff." in captured_prompt["prompt"]
    assert "the spec contract" in captured_prompt["prompt"]
    assert "+ added line" in captured_prompt["prompt"]
    assert transport.INJECTION_BOUNDARY in captured_prompt["prompt"]


def test_plan_review_uses_plan_file_not_diff_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_available(monkeypatch)
    agent_md = tmp_path / "opus-plan-reviewer.md"
    agent_md.write_text("Review the plan.", encoding="utf-8")
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("the spec contract", encoding="utf-8")
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("the plan body", encoding="utf-8")
    valid_plan_review = {
        "reviewer": "opus-plan-reviewer", "severity": "low", "findings": [], "summary": "ok",
    }
    captured_prompt = {}

    def _run(argv, input, capture_output, encoding, errors, timeout, env):  # noqa: A002
        captured_prompt["prompt"] = input
        out_path = Path(argv[argv.index("-o") + 1])
        out_path.write_text(json.dumps(valid_plan_review), encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(transport.subprocess, "run", Mock(side_effect=_run))

    exit_code = review_via_codex.main([
        "--role", "plan_review", "--worktree-root", str(tmp_path),
        "--agent-md", str(agent_md), "--out-dir", str(tmp_path),
        "--spec-file", str(spec_file), "--plan-file", str(plan_file),
    ])

    assert exit_code == 0
    assert "the plan body" in captured_prompt["prompt"]
    assert "the spec contract" in captured_prompt["prompt"]


def test_diff_file_missing_for_non_plan_role_is_reported_not_raised(tmp_path: Path) -> None:
    agent_md = tmp_path / "code-reviewer.md"
    agent_md.write_text("x", encoding="utf-8")
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("x", encoding="utf-8")

    exit_code = review_via_codex.main([
        "--role", "code", "--worktree-root", str(tmp_path),
        "--agent-md", str(agent_md), "--out-dir", str(tmp_path),
        "--spec-file", str(spec_file),
    ])

    assert exit_code == 1


def test_plan_file_missing_for_plan_review_role_is_reported_not_raised(tmp_path: Path) -> None:
    agent_md = tmp_path / "opus-plan-reviewer.md"
    agent_md.write_text("x", encoding="utf-8")
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("x", encoding="utf-8")

    exit_code = review_via_codex.main([
        "--role", "plan_review", "--worktree-root", str(tmp_path),
        "--agent-md", str(agent_md), "--out-dir", str(tmp_path),
        "--spec-file", str(spec_file),
    ])

    assert exit_code == 1


def test_empty_diff_file_is_reported_not_silently_reviewed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression for doubt-reviewer HIGH, 2026-09-17: `git diff HEAD` on an
    all-new-file change writes an empty diff file, which is not an OSError —
    without a content check codex would answer a schema-valid PASS over no
    subject, and a HARD-GATE spec-reviewer row would record it as real."""
    agent_md = tmp_path / "code-reviewer.md"
    agent_md.write_text("x", encoding="utf-8")
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("the spec contract", encoding="utf-8")
    diff_file = tmp_path / "empty.diff"
    diff_file.write_text("   \n", encoding="utf-8")

    exit_code = review_via_codex.main([
        "--role", "code", "--worktree-root", str(tmp_path),
        "--agent-md", str(agent_md), "--out-dir", str(tmp_path),
        "--spec-file", str(spec_file), "--diff-file", str(diff_file),
    ])

    assert exit_code == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "error"
    assert "empty" in result["reason"]


def test_nonexistent_context_file_is_reported_not_raised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression for code-reviewer REJECT 2026-09-17: an unreadable input
    file must produce `{"status": "error", ...}` on stdout, never a bare
    Python traceback — the dispatch doc tells callers to 'parse the printed
    JSON line'."""
    agent_md = tmp_path / "code-reviewer.md"
    agent_md.write_text("x", encoding="utf-8")

    exit_code = review_via_codex.main([
        "--role", "code", "--worktree-root", str(tmp_path),
        "--agent-md", str(agent_md), "--out-dir", str(tmp_path),
        "--spec-file", str(tmp_path / "does-not-exist.md"),
        "--diff-file", str(tmp_path / "also-missing.diff"),
    ])

    assert exit_code == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "error"


def test_failure_prints_json_and_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(transport, "is_codex_available", lambda **kw: (False, "not authenticated"))
    agent_md = tmp_path / "code-reviewer.md"
    agent_md.write_text("Review the diff.", encoding="utf-8")
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("x", encoding="utf-8")
    diff_file = tmp_path / "the.diff"
    diff_file.write_text("x", encoding="utf-8")

    exit_code = review_via_codex.main([
        "--role", "code", "--worktree-root", str(tmp_path),
        "--agent-md", str(agent_md), "--out-dir", str(tmp_path),
        "--spec-file", str(spec_file), "--diff-file", str(diff_file),
    ])

    assert exit_code == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "error"
    assert result["reason"] == "not authenticated"


def test_invalid_role_rejected_by_argparse(tmp_path: Path) -> None:
    agent_md = tmp_path / "x.md"
    agent_md.write_text("x", encoding="utf-8")

    with pytest.raises(SystemExit):
        review_via_codex.main([
            "--role", "nonsense", "--worktree-root", str(tmp_path),
            "--agent-md", str(agent_md), "--out-dir", str(tmp_path),
            "--spec-file", str(agent_md),
        ])
