"""In-process (non-subprocess) coverage for codex_hooks_launcher.py's
bootstrap sys.path insertion and the POSIX-only branches of
``_write_launcher``/``_hooks_json_command``/``_command_to_launcher_path``.

This machine is Windows, so the real ``sys.platform == "win32"`` branches in
these functions never execute a genuine POSIX code path in the rest of the
suite (``@pytest.mark.skipif(os.name != "posix", ...)`` tests exist for the
behavioral side of this, but they SKIP here). Monkeypatching ``sys.platform``
on the already-imported module exercises the POSIX branches' actual lines
under diff-coverage instrumentation without needing a real POSIX host —
mirroring ``test_write_grill_trace_direct.py``'s precedent for the identical
sys.path-bootstrap gap.
"""

from __future__ import annotations

import importlib
import stat as stat_module
import sys
from pathlib import Path, PurePosixPath

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

import codex_hooks_launcher as launcher_module  # noqa: E402
from codex_hooks_launcher import (  # noqa: E402
    CodexHooksSyncError,
    _command_to_launcher_path,
    _hooks_json_command,
    _materialize,
    _write_launcher,
)


def test_bootstrap_inserts_lib_when_missing_from_syspath(monkeypatch):
    """The ``if str(_LIB) not in sys.path: sys.path.insert(...)`` bootstrap
    only executes when the lib dir isn't already present. Both this module
    and codex_hooks_sync.py insert the identical directory, so whichever
    imports first in a given test session satisfies the other's guard as a
    no-op — force the True branch by removing the entry and re-importing."""
    lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != lib_dir])
    original_module = sys.modules.pop("codex_hooks_launcher", None)
    try:
        importlib.import_module("codex_hooks_launcher")
        assert lib_dir in sys.path
    finally:
        if original_module is not None:
            sys.modules["codex_hooks_launcher"] = original_module
        else:
            sys.modules.pop("codex_hooks_launcher", None)


def test_write_launcher_posix_branch_writes_sh_with_shebang_and_exec_bit(tmp_path, monkeypatch):
    """Windows os.chmod cannot actually set the POSIX execute bit on disk
    (there is no such concept on NTFS), so this asserts the MODE THE CODE
    REQUESTED via a chmod spy rather than the mode the filesystem reports
    back — the behavioral claim under test is "asked for owner-execute",
    which stat() cannot answer truthfully on this host."""
    monkeypatch.setattr(launcher_module.sys, "platform", "linux")
    launcher_dir = tmp_path / "launchers"
    launcher_dir.mkdir()
    requested_modes = []
    real_chmod = Path.chmod

    def spy_chmod(self, mode, *a, **kw):
        requested_modes.append(mode)
        return real_chmod(self, mode, *a, **kw)

    monkeypatch.setattr(Path, "chmod", spy_chmod)

    launcher_path = _write_launcher(
        launcher_dir, "abc123", "uv run /real/script.py", "/real/bundle"
    )

    assert launcher_path.suffix == ".sh"
    body = launcher_path.read_text(encoding="utf-8")
    assert body == (
        "#!/bin/sh\n"
        "SHIPWRIGHT_PLUGIN_ROOT=/real/bundle\n"
        "export SHIPWRIGHT_PLUGIN_ROOT\n"
        "exec uv run /real/script.py\n"
    )
    assert len(requested_modes) == 1
    assert requested_modes[0] & stat_module.S_IXUSR


def test_write_launcher_posix_branch_quotes_bundle_root_with_space(tmp_path, monkeypatch):
    """Belt-and-braces (mini-plan §0.2): shlex.quote() the injected value
    even though _validate_bundle_root_for_launcher already rejects the
    characters that would make this unsafe — a space alone is allowed by
    that allowlist and must still round-trip as one shell token."""
    monkeypatch.setattr(launcher_module.sys, "platform", "linux")
    launcher_dir = tmp_path / "launchers"
    launcher_dir.mkdir()
    monkeypatch.setattr(Path, "chmod", lambda self, *a, **kw: None)

    launcher_path = _write_launcher(
        launcher_dir, "abc123", "uv run /real/script.py", "/home/svenroth/Shipwright Bundle"
    )

    body = launcher_path.read_text(encoding="utf-8")
    assert "SHIPWRIGHT_PLUGIN_ROOT='/home/svenroth/Shipwright Bundle'\n" in body
    assert "export SHIPWRIGHT_PLUGIN_ROOT\n" in body


def test_write_launcher_windows_branch_injects_env_var(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher_module.sys, "platform", "win32")
    launcher_dir = tmp_path / "launchers"
    launcher_dir.mkdir()

    launcher_path = _write_launcher(
        launcher_dir, "abc123", 'uv run "C:\\bundle\\script.py"', "C:\\bundle"
    )

    assert launcher_path.suffix == ".cmd"
    # read_text() applies universal-newline translation (\r\n -> \n on read);
    # the file on disk is still genuinely \r\n-terminated, matching the
    # pre-existing body format for the other two lines.
    body = launcher_path.read_text(encoding="utf-8")
    assert body == (
        "@echo off\n"
        'set "SHIPWRIGHT_PLUGIN_ROOT=C:\\bundle"\n'
        'uv run "C:\\bundle\\script.py"\n'
        "exit /b %ERRORLEVEL%\n"
    )
    raw_bytes = launcher_path.read_bytes()
    assert raw_bytes.count(b"\r\n") == 4


def test_hooks_json_command_quotes_on_posix(monkeypatch):
    """PurePosixPath, not Path — a real Path on this Windows host would
    normalize the separators to backslashes before str() ever sees it,
    masking the POSIX-shaped quoting this test exists to check."""
    monkeypatch.setattr(launcher_module.sys, "platform", "linux")
    path_with_space = PurePosixPath("/home/svenroth/Shipwright Bundle/launcher.sh")

    command = _hooks_json_command(path_with_space)

    assert command == "'/home/svenroth/Shipwright Bundle/launcher.sh'"


def test_command_to_launcher_path_empty_string_returns_none():
    assert _command_to_launcher_path("") is None
    assert _command_to_launcher_path("   ") is None


def test_command_to_launcher_path_posix_single_token_round_trips(monkeypatch):
    monkeypatch.setattr(launcher_module.sys, "platform", "linux")
    path_with_space = Path("/home/svenroth/Shipwright Bundle/launcher.sh")
    quoted = _hooks_json_command(path_with_space)

    recovered = _command_to_launcher_path(quoted)

    assert recovered == path_with_space


def test_command_to_launcher_path_posix_multi_token_is_foreign(monkeypatch):
    """A hooks.json entry from an unrelated tool with a real, multi-argument
    shell command is not a single-token launcher reference."""
    monkeypatch.setattr(launcher_module.sys, "platform", "linux")

    assert _command_to_launcher_path("/usr/local/bin/my-own-tool --flag value") is None


def test_command_to_launcher_path_posix_unparseable_returns_none(monkeypatch):
    """An unterminated quote is not valid shell syntax — shlex.split raises
    ValueError, which must surface as a foreign (non-launcher) entry, not an
    uncaught crash while scanning an operator's hooks.json."""
    monkeypatch.setattr(launcher_module.sys, "platform", "linux")

    assert _command_to_launcher_path('"unterminated') is None


def test_materialize_raises_on_blank_command(tmp_path):
    bundle_hooks = {
        "Stop": [
            {
                "hooks": [
                    {"type": "command", "command": "   "},
                ]
            }
        ]
    }
    launcher_dir = tmp_path / "launchers"

    with pytest.raises(CodexHooksSyncError, match=r"Stop\[0\]\.hooks\[0\] has no command"):
        _materialize(bundle_hooks, tmp_path / "bundle", launcher_dir)


# ---------------------------------------------------------------------------
# bundle_root validation — F11 PR-review preflight (2026-09-22): bundle_root
# is spliced into a launcher-script body wherever the bundle's raw_command
# places ${CLAUDE_PLUGIN_ROOT}, in a quoting context this module cannot
# assume. Reject unsafe characters outright instead of escaping for it.
# ---------------------------------------------------------------------------

_PLACEHOLDER_HOOKS = {
    "Stop": [{"hooks": [{"type": "command", "command": 'uv run "${CLAUDE_PLUGIN_ROOT}/x.py"'}]}]
}


@pytest.mark.parametrize(
    "bad_char",
    ['"', "`", "$", ";", "|", "&", "<", ">", "^", "%", "'", "\n"],
)
def test_materialize_rejects_unsafe_bundle_root_characters(tmp_path, bad_char):
    bundle_root = tmp_path / f"bundle{bad_char}root"
    launcher_dir = tmp_path / "launchers"

    with pytest.raises(CodexHooksSyncError, match="unsafe for launcher-script"):
        _materialize(_PLACEHOLDER_HOOKS, bundle_root, launcher_dir)

    assert not launcher_dir.exists() or not list(launcher_dir.iterdir())


def test_materialize_accepts_windows_style_path_with_parentheses_and_spaces(tmp_path, monkeypatch):
    """A real, entirely legitimate Windows install path (e.g. under
    ``Program Files (x86)``) must not be rejected by the same guard. Forces
    the win32 branch (module docstring) so the `.bat`-style assertions below
    hold on a POSIX CI runner too, not just on this Windows dev machine."""
    monkeypatch.setattr(launcher_module.sys, "platform", "win32")
    bundle_root = Path("C:/Program Files (x86)/Shipwright Bundle_v1.2/cache")
    launcher_dir = tmp_path / "launchers"

    new_hooks, manifest_entries = _materialize(_PLACEHOLDER_HOOKS, bundle_root, launcher_dir)

    assert len(manifest_entries) == 1
    launcher_path = _command_to_launcher_path(manifest_entries[0]["command"])
    body = launcher_path.read_text(encoding="utf-8")
    # Twice by design: once in the injected SHIPWRIGHT_PLUGIN_ROOT env line
    # (mini-plan §0.2), once in the substituted command line.
    assert body.count(str(bundle_root)) == 2
    assert f'set "SHIPWRIGHT_PLUGIN_ROOT={bundle_root}"' in body
