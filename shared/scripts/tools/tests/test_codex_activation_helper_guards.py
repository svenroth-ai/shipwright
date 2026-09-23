"""Tests for codex_activation_helper.py (R2 -- M3, Step 7): live-record guard,
BatBadBut cwd-hijack guard, and shell-shim refusal.

Split from ``test_codex_activation_helper.py`` (bloat gate, 2026-09-23) --
that file keeps the launch-mechanics/argv half; this one covers the
already-live-session block, ``_resolve_codex_binary``'s cwd-hijack guard,
and the ``.bat``/``.cmd`` shell-shim refusal."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))

import codex_activation_helper  # noqa: E402
import codex_activation_record  # noqa: E402
import codex_envelope_grammar  # noqa: E402


class _FakeCompletedProcess:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode


def _write_record(record_dir: Path, session_id: str, *, cwd: str, expiry: float) -> None:
    record_dir.mkdir(parents=True, exist_ok=True)
    (record_dir / f"{session_id}.json").write_text(
        json.dumps({"session_id": session_id, "cwd": cwd, "expiry": expiry}),
        encoding="utf-8",
    )


def test_live_record_blocks_launch_without_force(tmp_path: Path, capsys) -> None:
    record_dir = codex_activation_record._record_dir(tmp_path)
    normalized = codex_activation_record.normalize_cwd(str(tmp_path))
    _write_record(record_dir, "sess-1", cwd=normalized, expiry=time.time() + 1800)

    with (
        patch.object(codex_activation_helper, "_resolve_codex_binary", return_value="codex"),
        patch("subprocess.run") as mock_run,
    ):
        rc = codex_activation_helper.main(
            ["--skill-id", "shipwright-iterate", "--project-root", str(tmp_path)]
        )
    assert rc == 1
    mock_run.assert_not_called()
    assert "sess-1" in capsys.readouterr().err


def test_force_bypasses_live_record_block(tmp_path: Path) -> None:
    record_dir = codex_activation_record._record_dir(tmp_path)
    normalized = codex_activation_record.normalize_cwd(str(tmp_path))
    _write_record(record_dir, "sess-1", cwd=normalized, expiry=time.time() + 1800)

    with (
        patch.object(codex_activation_helper, "_resolve_codex_binary", return_value="codex"),
        patch("subprocess.run", return_value=_FakeCompletedProcess(0)) as mock_run,
    ):
        rc = codex_activation_helper.main(
            [
                "--skill-id",
                "shipwright-iterate",
                "--project-root",
                str(tmp_path),
                "--force",
            ]
        )
    assert rc == 0
    mock_run.assert_called_once()


def test_expired_record_does_not_block(tmp_path: Path) -> None:
    record_dir = codex_activation_record._record_dir(tmp_path)
    normalized = codex_activation_record.normalize_cwd(str(tmp_path))
    _write_record(record_dir, "sess-1", cwd=normalized, expiry=time.time() - 5)

    with (
        patch.object(codex_activation_helper, "_resolve_codex_binary", return_value="codex"),
        patch("subprocess.run", return_value=_FakeCompletedProcess(0)) as mock_run,
    ):
        rc = codex_activation_helper.main(
            ["--skill-id", "shipwright-iterate", "--project-root", str(tmp_path)]
        )
    assert rc == 0
    mock_run.assert_called_once()


def test_record_for_different_project_does_not_block(tmp_path: Path) -> None:
    record_dir = codex_activation_record._record_dir(tmp_path)
    _write_record(record_dir, "sess-1", cwd="/some/other/unrelated/project", expiry=time.time() + 1800)

    with (
        patch.object(codex_activation_helper, "_resolve_codex_binary", return_value="codex"),
        patch("subprocess.run", return_value=_FakeCompletedProcess(0)) as mock_run,
    ):
        rc = codex_activation_helper.main(
            ["--skill-id", "shipwright-iterate", "--project-root", str(tmp_path)]
        )
    assert rc == 0
    mock_run.assert_called_once()


def test_live_record_blocks_from_raw_worktree_path(tmp_path: Path, monkeypatch, capsys) -> None:
    """Code review MEDIUM: a raw ``--project-root`` (e.g. a worktree path)
    must still find the record the hooks actually wrote at the
    git-normalized main-repo-root -- not the raw path's own, unrelated
    ``.shipwright/`` subtree, which is where an earlier version of this
    scan silently missed it."""
    raw_worktree = tmp_path / "worktrees" / "some-slug"
    raw_worktree.mkdir(parents=True)
    normalized_root = tmp_path / "canonical-repo"

    monkeypatch.setattr(
        codex_activation_record.git_base, "main_repo_root", lambda p: normalized_root
    )

    record_dir = codex_activation_record._record_dir(normalized_root)
    _write_record(record_dir, "sess-1", cwd=str(normalized_root), expiry=time.time() + 1800)

    with (
        patch.object(codex_activation_helper, "_resolve_codex_binary", return_value="codex"),
        patch("subprocess.run") as mock_run,
    ):
        rc = codex_activation_helper.main(
            ["--skill-id", "shipwright-iterate", "--project-root", str(raw_worktree)]
        )
    assert rc == 1
    mock_run.assert_not_called()
    assert "sess-1" in capsys.readouterr().err


def test_resolve_codex_binary_rejects_cwd_planted_executable(tmp_path: Path, monkeypatch) -> None:
    fake = tmp_path / "codex.exe"
    fake.write_text("not the real thing", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with patch("shutil.which", return_value=str(fake)):
        assert codex_activation_helper._resolve_codex_binary() is None


def test_resolve_codex_binary_accepts_a_path_hit(tmp_path: Path) -> None:
    real_dir = tmp_path / "somewhere-on-path"
    real_dir.mkdir()
    real = real_dir / "codex"
    real.write_text("shim", encoding="utf-8")
    with patch("shutil.which", return_value=str(real)):
        assert codex_activation_helper._resolve_codex_binary() == str(real)


def test_resolve_codex_binary_returns_none_when_absent() -> None:
    with patch("shutil.which", return_value=None):
        assert codex_activation_helper._resolve_codex_binary() is None


def test_resolve_codex_binary_delegates_to_shared_cmd_resolver(monkeypatch) -> None:
    """Regression for the R2 code-review dedup: `_resolve_codex_binary` must
    not carry its own copy of the BatBadBut guard logic again -- it must
    call the single shared implementation in `cmd_resolver`."""
    sentinel = object()
    monkeypatch.setattr(
        codex_activation_helper, "resolve_trusted_executable", lambda name: sentinel
    )
    assert codex_activation_helper._resolve_codex_binary() is sentinel


# --- .bat/.cmd shell-shim refusal (R2 code review, 2026-09-22 -- empirically confirmed:
# a real Windows .cmd shim re-splits `a|b`/`c&d`-shaped argv elements via an implicit
# cmd.exe re-parse, even with shell=False and a list argv) ---


def test_refuse_if_shell_shim_rejects_cmd_extension() -> None:
    message = codex_activation_helper._refuse_if_shell_shim("C:\\bin\\codex.cmd", "[ENVELOPE]")
    assert message is not None
    assert "codex.cmd" in message
    assert "[ENVELOPE]" in message


def test_refuse_if_shell_shim_rejects_bat_extension() -> None:
    message = codex_activation_helper._refuse_if_shell_shim("C:\\bin\\codex.bat", "[ENVELOPE]")
    assert message is not None


def test_refuse_if_shell_shim_rejects_cmd_extension_case_insensitively() -> None:
    message = codex_activation_helper._refuse_if_shell_shim("C:\\bin\\codex.CMD", "[ENVELOPE]")
    assert message is not None


def test_refuse_if_shell_shim_allows_exe_extension() -> None:
    assert codex_activation_helper._refuse_if_shell_shim("C:\\bin\\codex.exe", "[ENVELOPE]") is None


def test_refuse_if_shell_shim_allows_no_extension() -> None:
    assert codex_activation_helper._refuse_if_shell_shim("/usr/local/bin/codex", "[ENVELOPE]") is None


def test_main_refuses_to_launch_through_a_cmd_shim(tmp_path: Path, capsys) -> None:
    with (
        patch.object(
            codex_activation_helper, "_resolve_codex_binary", return_value="C:\\bin\\codex.cmd"
        ),
        patch.object(codex_activation_helper, "_find_live_record", return_value=None),
        patch("subprocess.run") as mock_run,
    ):
        rc = codex_activation_helper.main(
            ["--skill-id", "shipwright-iterate", "--project-root", str(tmp_path)]
        )
    assert rc == 1
    mock_run.assert_not_called()
    err = capsys.readouterr().err
    assert "codex.cmd" in err
    # The operator must still be able to launch manually -- the envelope text
    # is echoed back, not swallowed.
    expected_envelope = codex_envelope_grammar.compose("shipwright-iterate", {})
    assert expected_envelope in err


def test_main_launches_normally_through_a_real_exe(tmp_path: Path) -> None:
    with (
        patch.object(
            codex_activation_helper, "_resolve_codex_binary", return_value="C:\\bin\\codex.exe"
        ),
        patch.object(codex_activation_helper, "_find_live_record", return_value=None),
        patch("subprocess.run", return_value=_FakeCompletedProcess(0)) as mock_run,
    ):
        rc = codex_activation_helper.main(
            ["--skill-id", "shipwright-iterate", "--project-root", str(tmp_path)]
        )
    assert rc == 0
    mock_run.assert_called_once()


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe argv re-parsing is Windows-only")
def test_shell_shim_refusal_empirically_matches_a_real_cmd_file(tmp_path: Path) -> None:
    """Not a mock -- writes a real `.cmd` shim and proves the argv metacharacter
    corruption this guard exists to prevent actually happens on this platform,
    the same probe used to confirm the R2 code-review finding before fixing it."""
    shim = tmp_path / "echoargs.cmd"
    shim.write_text("@echo off\r\necho ARGS: %*\r\n", encoding="utf-8")
    result = subprocess.run(
        [str(shim), "a|b"], shell=False, capture_output=True, text=True
    )
    # The pipe character does NOT survive as a literal argv element -- cmd.exe
    # re-parsed it, exactly why _refuse_if_shell_shim exists.
    assert "ARGS: a|b" not in result.stdout


def test_record_subdir_matches_the_library_storage_path(tmp_path: Path) -> None:
    """Regression: an earlier draft of this helper scanned `<root>/shipwright/...`
    (missing the leading dot) -- a wrong-but-consistent path that every other
    test in this file happened to mirror, so it stayed green while silently
    never finding a real record the library actually wrote. Cross-check
    against the library's own path function directly, so this class of bug
    can't hide behind a self-consistent test fixture again."""
    from_library = codex_activation_record._record_dir(tmp_path)
    from_helper = tmp_path.joinpath(*codex_activation_helper._RECORD_SUBDIR)
    assert from_library == from_helper
