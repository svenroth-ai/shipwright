"""Tests for codex_activation_helper.py (R2 -- M3, Step 7): launch mechanics.

Argv/quoting shape only -- this never actually launches ``codex`` (that
needs a live, trusted Codex install, out of scope here and deliberately
deferred to this run's live-probe step).

Split from the live-record/BatBadBut-guard/shell-shim half (bloat gate,
2026-09-23) -- that half lives in ``test_codex_activation_helper_guards.py``."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))

import codex_activation_helper  # noqa: E402
import codex_envelope_grammar  # noqa: E402


class _FakeCompletedProcess:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode


def test_build_launch_argv_is_a_plain_list() -> None:
    argv = codex_activation_helper._build_launch_argv("codex", "[ENVELOPE]")
    assert argv == ["codex", "[ENVELOPE]"]
    assert isinstance(argv, list)


def test_shell_unsafe_characters_survive_argv_boundary_unescaped() -> None:
    dangerous = '[SHIPWRIGHT-CODEX-ACTIVATE-v1|skill_id=x|args_b64=] && rm -rf / ; echo "$(whoami)" | sh'
    argv = codex_activation_helper._build_launch_argv("codex", dangerous)
    # The dangerous text must appear byte-for-byte as a single argv element --
    # never re-escaped, never split, since a list + shell=False never re-parses it.
    assert argv[1] == dangerous
    assert len(argv) == 2


def test_main_never_passes_shell_true(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    with (
        patch.object(codex_activation_helper, "_resolve_codex_binary", return_value="codex"),
        patch.object(codex_activation_helper, "_find_live_record", return_value=None),
        patch("subprocess.run", return_value=_FakeCompletedProcess(0)) as mock_run,
    ):
        rc = codex_activation_helper.main(
            ["--skill-id", "shipwright-iterate", "--project-root", str(tmp_path)]
        )
    assert rc == 0
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs.get("shell", False) is False


def test_main_does_not_capture_output_interactive_launch(tmp_path: Path) -> None:
    """This is an interactive hand-off to codex, not a one-shot capture -- must
    never pass capture_output/input, unlike the sibling `codex exec` pattern."""
    with (
        patch.object(codex_activation_helper, "_resolve_codex_binary", return_value="codex"),
        patch.object(codex_activation_helper, "_find_live_record", return_value=None),
        patch("subprocess.run", return_value=_FakeCompletedProcess(0)) as mock_run,
    ):
        codex_activation_helper.main(
            ["--skill-id", "shipwright-iterate", "--project-root", str(tmp_path)]
        )
    _, kwargs = mock_run.call_args
    assert "capture_output" not in kwargs
    assert "input" not in kwargs


def test_main_launches_with_project_root_as_cwd(tmp_path: Path) -> None:
    with (
        patch.object(codex_activation_helper, "_resolve_codex_binary", return_value="codex"),
        patch.object(codex_activation_helper, "_find_live_record", return_value=None),
        patch("subprocess.run", return_value=_FakeCompletedProcess(0)) as mock_run,
    ):
        codex_activation_helper.main(
            ["--skill-id", "shipwright-iterate", "--project-root", str(tmp_path)]
        )
    _, kwargs = mock_run.call_args
    assert kwargs.get("cwd") == str(tmp_path.resolve())


def test_main_composes_envelope_into_argv(tmp_path: Path) -> None:
    with (
        patch.object(codex_activation_helper, "_resolve_codex_binary", return_value="codex"),
        patch.object(codex_activation_helper, "_find_live_record", return_value=None),
        patch("subprocess.run", return_value=_FakeCompletedProcess(0)) as mock_run,
    ):
        codex_activation_helper.main(
            [
                "--skill-id",
                "shipwright-iterate",
                "--args-json",
                '{"type": "feature"}',
                "--project-root",
                str(tmp_path),
            ]
        )
    launch_argv = mock_run.call_args[0][0]
    expected_envelope = codex_envelope_grammar.compose("shipwright-iterate", {"type": "feature"})
    assert launch_argv == ["codex", expected_envelope]


def test_invalid_skill_id_rejected_before_launch(tmp_path: Path, capsys) -> None:
    with patch("subprocess.run") as mock_run:
        rc = codex_activation_helper.main(
            ["--skill-id", "not a valid id!", "--project-root", str(tmp_path)]
        )
    assert rc == 1
    mock_run.assert_not_called()
    assert "error" in capsys.readouterr().err


def test_invalid_args_json_rejected_before_launch(tmp_path: Path, capsys) -> None:
    with patch("subprocess.run") as mock_run:
        rc = codex_activation_helper.main(
            [
                "--skill-id",
                "shipwright-iterate",
                "--args-json",
                "{not json",
                "--project-root",
                str(tmp_path),
            ]
        )
    assert rc == 1
    mock_run.assert_not_called()
    assert "valid JSON" in capsys.readouterr().err


def test_non_object_args_json_rejected(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        rc = codex_activation_helper.main(
            [
                "--skill-id",
                "shipwright-iterate",
                "--args-json",
                "[1, 2, 3]",
                "--project-root",
                str(tmp_path),
            ]
        )
    assert rc == 1
    mock_run.assert_not_called()


def test_codex_not_found_on_path(tmp_path: Path) -> None:
    with (
        patch.object(codex_activation_helper, "_resolve_codex_binary", return_value=None),
        patch.object(codex_activation_helper, "_find_live_record", return_value=None),
        patch("subprocess.run") as mock_run,
    ):
        rc = codex_activation_helper.main(
            ["--skill-id", "shipwright-iterate", "--project-root", str(tmp_path)]
        )
    assert rc == 1
    mock_run.assert_not_called()


def test_launch_failure_reports_error_not_crash(tmp_path: Path, capsys) -> None:
    with (
        patch.object(codex_activation_helper, "_resolve_codex_binary", return_value="codex"),
        patch.object(codex_activation_helper, "_find_live_record", return_value=None),
        patch("subprocess.run", side_effect=OSError("boom")),
    ):
        rc = codex_activation_helper.main(
            ["--skill-id", "shipwright-iterate", "--project-root", str(tmp_path)]
        )
    assert rc == 1
    assert "failed to launch" in capsys.readouterr().err
