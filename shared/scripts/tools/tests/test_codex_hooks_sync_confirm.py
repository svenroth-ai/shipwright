"""main()'s interactive y/N confirmation checkpoint before writing to the
global ~/.codex/hooks.json — the mitigation added alongside the operator's
Accepted Risk decision on bundle-root authenticity (ADR "Accepted Risk"
section, ``.shipwright/planning/adr/
iterate-2026-09-22-r1b-codex-hooks-config-layer-shim-launcher-script-quoting.md``).
Split out of test_codex_hooks_sync_direct.py to stay under the repo's
300-LOC guideline.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))  # shared/scripts/lib
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests dir (fixtures helper)

from _codex_hooks_sync_fixtures import SAMPLE_HOOKS, make_bundle  # noqa: E402
from codex_hooks_sync import main  # noqa: E402


def test_main_yes_flag_skips_prompt_and_proceeds(tmp_path, monkeypatch, capsys):
    """--yes must never read stdin at all — a real bundle with an
    unreadable/absent stdin (e.g. a scripted caller) must still succeed."""
    def _fail_if_called(*a, **kw):
        raise AssertionError("input() must not be called when --yes is passed")

    monkeypatch.setattr("builtins.input", _fail_if_called)
    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"

    rc = main(["--bundle-root", str(bundle_root), "--codex-home", str(codex_home), "--yes"])

    assert rc == 0
    assert "Synced 2 Shipwright hook(s)" in capsys.readouterr().out
    assert (codex_home / "hooks.json").is_file()


def test_main_declines_on_eof_stdin_and_writes_nothing(tmp_path, monkeypatch, capsys):
    """A piped/closed stdin (EOF, no answer at all) must decline, never be
    read as implicit consent — the same fail-closed default as an explicit
    'n'."""
    def _raise_eof(*a, **kw):
        raise EOFError

    monkeypatch.setattr("builtins.input", _raise_eof)
    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"

    rc = main(["--bundle-root", str(bundle_root), "--codex-home", str(codex_home)])

    assert rc == 1
    assert "aborted" in capsys.readouterr().err
    assert not (codex_home / "hooks.json").exists()


def test_main_declines_on_explicit_n_and_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda *a, **kw: "n")
    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"

    rc = main(["--bundle-root", str(bundle_root), "--codex-home", str(codex_home)])

    assert rc == 1
    assert "aborted" in capsys.readouterr().err
    assert not (codex_home / "hooks.json").exists()


def test_main_confirmation_prompt_shows_resolved_bundle_root_and_commands(tmp_path, monkeypatch, capsys):
    """The preview must show the RESOLVED command (placeholder substituted),
    not the raw bundle text — what the operator sees is what will run."""
    seen_prompts = []

    def _capture(prompt=""):
        seen_prompts.append(prompt)
        return "n"

    monkeypatch.setattr("builtins.input", _capture)
    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    codex_home = tmp_path / "codex_home"

    main(["--bundle-root", str(bundle_root), "--codex-home", str(codex_home)])

    err = capsys.readouterr().err
    assert str(bundle_root.resolve()) in err
    assert "${CLAUDE_PLUGIN_ROOT}" not in err
    assert "on_start.py" in err
    assert seen_prompts  # input() was actually called


def test_main_unreadable_bundle_hooks_errors_before_prompting(tmp_path, monkeypatch, capsys):
    """A bundle that passes is_codex_runtime()'s shape check (genuine
    BUILD_MANIFEST.json, plugin.json present) but whose plugin.json is not
    valid JSON fails while building the confirmation preview — must surface
    as the same 'error:' CodexHooksSyncError path main() uses elsewhere,
    never reach the prompt."""
    def _fail_if_called(*a, **kw):
        raise AssertionError("input() must not be called when the preview read fails")

    monkeypatch.setattr("builtins.input", _fail_if_called)
    bundle_root = tmp_path / "bundle"
    make_bundle(bundle_root, SAMPLE_HOOKS)
    (bundle_root / ".codex-plugin" / "plugin.json").write_text("not json", encoding="utf-8")
    codex_home = tmp_path / "codex_home"

    rc = main(["--bundle-root", str(bundle_root), "--codex-home", str(codex_home)])

    assert rc == 1
    assert "error:" in capsys.readouterr().err


def test_main_not_a_bundle_never_prompts_even_without_yes(tmp_path, monkeypatch, capsys):
    """A non-bundle root no-ops inside sync_codex_hooks() regardless of
    confirmation — the checkpoint must not block (or even attempt) a call
    that was always going to be a no-op."""
    def _fail_if_called(*a, **kw):
        raise AssertionError("input() must not be called for a non-bundle root")

    monkeypatch.setattr("builtins.input", _fail_if_called)
    not_a_bundle = tmp_path / "not-a-bundle"
    not_a_bundle.mkdir()
    codex_home = tmp_path / "codex_home"

    rc = main(["--bundle-root", str(not_a_bundle), "--codex-home", str(codex_home)])

    assert rc == 0
    assert "no-op:" in capsys.readouterr().out
