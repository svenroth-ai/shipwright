"""Tests for shared/scripts/tools/codex_hooks_sync.py (R1b — AC2/AC3/AC5).

Every test works against ``tmp_path``-scoped fake bundle roots and fake
``codex_home`` directories — never the operator's real ``~/.codex/`` (see
the iterate spec's Verification section). See the Iterate Spec's Design
Notes for why hooks are relocated into per-hook launcher scripts (the
Windows ``cmd.exe /C`` double-quote bug) rather than embedded directly.

Malformed-input, lock-contention, and CLI-smoke coverage live in
``test_codex_hooks_sync_errors.py`` (kept separate to stay under the
repo's 300-LOC guideline).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))  # shared/scripts/lib
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests dir (fixtures helper)

from _codex_hooks_sync_fixtures import SAMPLE_HOOKS, make_bundle  # noqa: E402
from codex_hooks_launcher import _command_to_launcher_path  # noqa: E402


def test_ac5_noop_when_not_codex_runtime(tmp_path):
    from codex_hooks_sync import sync_codex_hooks

    not_a_bundle = tmp_path / "not-a-bundle"
    not_a_bundle.mkdir()
    codex_home = tmp_path / "codex_home"

    result = sync_codex_hooks(not_a_bundle, codex_home=codex_home)

    assert result.applied is False
    assert not codex_home.exists()


def test_ac2_placeholder_rewritten_into_launcher_script(tmp_path):
    from codex_hooks_sync import sync_codex_hooks

    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"

    result = sync_codex_hooks(bundle_root, codex_home=codex_home)

    assert result.applied is True
    assert result.hooks_written == 2
    hooks_doc = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    session_start_command = hooks_doc["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    launcher_path = _command_to_launcher_path(session_start_command)
    assert launcher_path is not None
    assert launcher_path.is_file()
    assert "shipwright-hooks" in launcher_path.parts
    launcher_body = launcher_path.read_text(encoding="utf-8")
    # .resolve() — not the unresolved test-local variable — matches what
    # sync_codex_hooks() actually interpolates, and the full expected line
    # (not a substring) also catches a rewrite that merely CONTAINS the
    # bundle root as part of some other, wrong path (external review, glm
    # leg, low).
    expected_line = f'uv run "{bundle_root.resolve()}/scripts/hooks/on_start.py"'
    assert expected_line in launcher_body
    assert "${CLAUDE_PLUGIN_ROOT}" not in launcher_body
    # hooks.json itself must contain no embedded double-quotes or bare
    # arguments — a POSIX command field may be single-quoted by
    # shlex.quote() (module docstring), but never carries extra tokens.
    assert '"' not in session_start_command.strip()


def test_ac3_idempotent_byte_identical_on_rerun(tmp_path):
    from codex_hooks_sync import sync_codex_hooks

    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"

    sync_codex_hooks(bundle_root, codex_home=codex_home)
    first = (codex_home / "hooks.json").read_bytes()

    sync_codex_hooks(bundle_root, codex_home=codex_home)
    second = (codex_home / "hooks.json").read_bytes()

    assert first == second


def test_ac3_foreign_entry_survives_resync_and_content_change(tmp_path):
    from codex_hooks_sync import sync_codex_hooks

    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"

    sync_codex_hooks(bundle_root, codex_home=codex_home)

    # Operator (or another tool) hand-adds an unrelated entry directly.
    hooks_path = codex_home / "hooks.json"
    doc = json.loads(hooks_path.read_text(encoding="utf-8"))
    doc["hooks"].setdefault("Stop", []).append(
        {"hooks": [{"type": "command", "command": "/usr/local/bin/my-own-tool"}]}
    )
    hooks_path.write_text(json.dumps(doc), encoding="utf-8")

    # Bundle content changes (simulates a rebuilt bundle).
    changed_hooks = json.loads(json.dumps(SAMPLE_HOOKS))
    changed_hooks["Stop"][0]["hooks"][0]["command"] = (
        'uv run "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/on_stop_v2.py"'
    )
    (bundle_root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"hooks": {"hooks": changed_hooks}}), encoding="utf-8"
    )

    sync_codex_hooks(bundle_root, codex_home=codex_home)

    final_doc = json.loads(hooks_path.read_text(encoding="utf-8"))
    stop_commands = [
        h["command"] for g in final_doc["hooks"]["Stop"] for h in g["hooks"]
    ]
    assert "/usr/local/bin/my-own-tool" in stop_commands
    # Exactly one Shipwright-owned Stop launcher remains (the old one was
    # replaced, not left as an orphan duplicate).
    shipwright_stop = [c for c in stop_commands if "shipwright-hooks" in c]
    assert len(shipwright_stop) == 1


def test_ownership_survives_without_sidecar_present(tmp_path):
    """External-review manifest-loss finding: ownership detection must not
    depend on the sidecar being present."""
    from codex_hooks_sync import sync_codex_hooks

    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"

    sync_codex_hooks(bundle_root, codex_home=codex_home)
    (codex_home / ".shipwright-hooks-managed.json").unlink()

    sync_codex_hooks(bundle_root, codex_home=codex_home)

    doc = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    session_start_groups = doc["hooks"]["SessionStart"]
    assert len(session_start_groups) == 1
    assert len(session_start_groups[0]["hooks"]) == 1


@pytest.mark.skipif(os.name != "posix", reason="POSIX executable-bit check")
def test_posix_launcher_is_executable(tmp_path):
    from codex_hooks_sync import sync_codex_hooks

    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"

    sync_codex_hooks(bundle_root, codex_home=codex_home)

    doc = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    launcher = _command_to_launcher_path(doc["hooks"]["SessionStart"][0]["hooks"][0]["command"])
    assert launcher is not None
    assert os.access(launcher, os.X_OK)


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission-bit check")
def test_posix_launcher_is_owner_only_executable(tmp_path):
    """Group/other must not gain execute — a launcher embeds real, unquoted
    filesystem paths, so a shared-machine neighbour gains nothing by being
    able to run it (doubt-reviewer, low)."""
    import stat as stat_module

    from codex_hooks_sync import sync_codex_hooks

    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"

    sync_codex_hooks(bundle_root, codex_home=codex_home)

    doc = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    launcher = _command_to_launcher_path(doc["hooks"]["SessionStart"][0]["hooks"][0]["command"])
    assert launcher is not None
    mode = launcher.stat().st_mode
    assert mode & stat_module.S_IXUSR
    assert not (mode & stat_module.S_IXGRP)
    assert not (mode & stat_module.S_IXOTH)


def test_ownership_rejects_lexical_traversal_outside_launcher_dir(tmp_path):
    """A command that lexically contains launcher_dir's own path but
    escapes it via a ``../`` segment must not be treated as Shipwright-
    owned — a lexical ``relative_to()`` with no ``.resolve()`` would get
    this backwards (external review, opus/openai leg, medium)."""
    from codex_hooks_sync import _is_shipwright_entry

    codex_home = tmp_path / "codex_home"
    launcher_dir = codex_home / "shipwright-hooks"
    launcher_dir.mkdir(parents=True)
    escaping_command = str(launcher_dir / ".." / "evil.sh")

    assert _is_shipwright_entry(escaping_command, launcher_dir) is False


def test_ownership_accepts_genuinely_inside_path_with_dot_segment(tmp_path):
    from codex_hooks_sync import _is_shipwright_entry

    launcher_dir = tmp_path / "codex_home" / "shipwright-hooks"
    launcher_dir.mkdir(parents=True)
    inside_command = str(launcher_dir / "." / "abc.sh")

    assert _is_shipwright_entry(inside_command, launcher_dir) is True


def test_stale_launcher_removal_survives_unlink_failure(tmp_path, monkeypatch):
    """A concurrently-running Codex session can hold a stale launcher open
    (mid execution) at exactly the moment a resync tries to remove it —
    hooks.json/the sidecar are already durably published by then, so this
    must degrade to a warning, never an uncaught crash (doubt-reviewer,
    high)."""
    from codex_hooks_sync import sync_codex_hooks

    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"

    sync_codex_hooks(bundle_root, codex_home=codex_home)
    first_doc = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    stale_launcher = _command_to_launcher_path(first_doc["hooks"]["Stop"][0]["hooks"][0]["command"])
    assert stale_launcher is not None
    assert stale_launcher.is_file()

    # Remove the Stop handler entirely (not just its command text) so the
    # old Stop launcher genuinely has no replacement in the next sync's
    # manifest_entries — _launcher_slug() is positional
    # (event, matcher, group_idx, handler_idx), not content-addressed, so
    # merely editing the command string reuses the same filename and never
    # actually orphans anything (external review, opus/openai leg, medium).
    changed_hooks = json.loads(json.dumps(SAMPLE_HOOKS))
    del changed_hooks["Stop"]
    (bundle_root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"hooks": {"hooks": changed_hooks}}), encoding="utf-8"
    )

    real_unlink = Path.unlink

    def flaky_unlink(self, *args, **kwargs):
        if self.parent.name == "shipwright-hooks":
            raise PermissionError(13, "simulated sharing violation")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)

    # Must not raise despite every stale-launcher unlink failing — and the
    # stale file, whose unlink was blocked, must genuinely still be there.
    result = sync_codex_hooks(bundle_root, codex_home=codex_home)
    assert result.applied is True
    assert stale_launcher.is_file()


@pytest.mark.covers("FR-01.21/AC05")
def test_launcher_path_with_spaces_actually_runs(tmp_path):
    """@covers FR-01.21/AC05 — hook-EXECUTION parity, not just discoverability
    (AC01). A live `codex exec` firing this same sync'd hook is the
    operator's own two-round empirical proof (iterate spec Design Notes /
    AC4); this is the automated proxy for it, reproducing Codex's exact
    invocation mechanism byte-for-byte (`cmd.exe /C "<command_line>"` on
    Windows, `$SHELL -lc <command_line>` on POSIX — see
    codex-rs/hooks/src/engine/command_runner.rs) and asserting the command
    genuinely ran, not just that hooks.json's shape looks plausible.

    The concrete regression test for the Windows cmd.exe /C double-quote
    bug: a bundle root (and therefore launcher dir) containing a space in
    the path must still produce a launcher that a real shell can invoke as
    a bare, unquoted token."""
    from codex_hooks_sync import sync_codex_hooks

    bundle_root = tmp_path / "Shipwright Bundle"
    marker = tmp_path / "marker.txt"
    hooks_with_space_path = {
        "Stop": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            f'"{sys.executable}" -c "open(r\'{marker}\', \'w\').write(\'ran\')" '
                            '"${CLAUDE_PLUGIN_ROOT}/unused_arg"'
                        ),
                    }
                ]
            }
        ]
    }
    make_bundle(bundle_root, hooks_with_space_path)
    codex_home = tmp_path / "codex home with spaces"

    sync_codex_hooks(bundle_root, codex_home=codex_home)

    doc = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    launcher = doc["hooks"]["Stop"][0]["hooks"][0]["command"].strip()
    assert " " in launcher  # the whole point of this test

    if os.name == "nt":
        # Mirrors Codex's own Windows hook execution exactly (build_command in
        # codex-rs/hooks/src/engine/command_runner.rs): cmd.exe /C "<command_line>"
        # as ONE raw command-line string, not a Python-quoted argv list — a list
        # would apply subprocess's OWN quoting on top and not reproduce the bug
        # this test exists to catch. Passing a plain str with shell=False on
        # Windows hands it to CreateProcess unmodified (Python subprocess docs).
        raw_cmdline = f'cmd.exe /C "{launcher}"'
        subprocess.run(raw_cmdline, check=True, timeout=30)
    else:
        # $SHELL, not a hardcoded "sh" — Codex invokes via "$SHELL -lc
        # <command_line>" (module docstring), and the operator's real login
        # shell is not guaranteed to be POSIX sh (external review, glm leg).
        shell = os.environ.get("SHELL", "sh")
        subprocess.run([shell, "-lc", launcher], check=True, timeout=30)

    assert marker.is_file()
    assert marker.read_text(encoding="utf-8") == "ran"
