"""Unit tests for the 'opus' reviewer identity (`external_review_opus_leg.py`):
binary resolution (cwd-hijack guard + the `.cmd`/`.bat`-shim refusal that is
this leg's own addition over the Codex leg's guard), availability detection,
`claude_cli_settings`, and `resolve_opus_route` (route selection + fallback).
`review_claude_cli`'s own dispatch/retry/env-scrub tests live in
`test_external_review_opus_leg_dispatch.py` (split to stay under 300 lines).
"""

import subprocess
import sys
from pathlib import Path

import pytest

_LIB_DIR = Path(__file__).resolve().parents[1] / "scripts" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import external_review_opus_leg as legs  # noqa: E402

_CONFIG = {"models": {"claude_cli": "claude-opus-5"}, "claude_cli": {"max_retries": 1}}


class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# --- _resolve_claude_binary: cwd-hijack guard + .cmd/.bat shim refusal ------

@pytest.mark.parametrize("in_cwd,expected", [(True, None), (False, "/usr/bin/claude")])
def test_resolve_claude_binary_cwd_hijack_guard(monkeypatch, tmp_path, in_cwd, expected):
    monkeypatch.chdir(tmp_path)
    hit = str(tmp_path / "claude.exe") if in_cwd else "/usr/bin/claude"
    monkeypatch.setattr(legs.shutil, "which", lambda _name: hit)
    assert legs._resolve_claude_binary() == expected


@pytest.mark.parametrize("suffix", [".cmd", ".bat", ".CMD"])
def test_resolve_claude_binary_refuses_a_windows_shim(monkeypatch, tmp_path, suffix):
    """The real Windows npm install of the Claude CLI IS a .cmd shim, and this
    leg (unlike review_codex) must pass untrusted content via a `-p` argv
    argument, not stdin — subprocess's list2cmdline argv quoting is not
    cmd.exe-batch-safe, so a diff containing &/|/^/" could break out of the
    argument. Refusing outright (not escaping harder) is the fix."""
    monkeypatch.chdir(tmp_path)
    shim = tmp_path.parent / f"claude{suffix}"
    monkeypatch.setattr(legs.shutil, "which", lambda _name: str(shim))
    assert legs._resolve_claude_binary() is None


def test_resolve_claude_binary_never_raises_on_a_symlink_loop(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(legs.Path, "resolve", lambda self: (_ for _ in ()).throw(RuntimeError("symlink loop")))
    assert legs._resolve_claude_binary() is None


# --- is_claude_cli_available -------------------------------------------------

def test_unavailable_when_binary_not_on_path(monkeypatch):
    monkeypatch.setattr(legs.shutil, "which", lambda _name: None)
    available, reason = legs.is_claude_cli_available()
    assert available is False
    assert "not found on PATH" in reason


def test_unavailable_on_nonzero_version_exit(monkeypatch):
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(legs.subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=1))
    available, reason = legs.is_claude_cli_available()
    assert available is False
    assert "exited 1" in reason


def test_unavailable_on_version_probe_timeout(monkeypatch):
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/claude")

    def _raise(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=15)

    monkeypatch.setattr(legs.subprocess, "run", _raise)
    available, reason = legs.is_claude_cli_available()
    assert available is False
    assert "timed out" in reason


def test_unavailable_on_oserror_never_raises(monkeypatch):
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(legs.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    available, reason = legs.is_claude_cli_available()
    assert available is False
    assert "boom" in reason


def test_available_when_installed(monkeypatch):
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(legs.subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=0))
    available, reason = legs.is_claude_cli_available()
    assert available is True
    assert reason == ""


# --- claude_cli_settings ------------------------------------------------------

def test_claude_cli_settings_clamps_a_negative_max_retries():
    assert legs.claude_cli_settings({"claude_cli": {"max_retries": -3}}) == (
        legs.CLAUDE_CLI_DEFAULT_TIMEOUT_SECONDS, 0,
    )


def test_claude_cli_settings_defaults_when_unconfigured():
    assert legs.claude_cli_settings({}) == (
        legs.CLAUDE_CLI_DEFAULT_TIMEOUT_SECONDS, legs.CLAUDE_CLI_DEFAULT_MAX_RETRIES,
    )


def test_claude_cli_settings_rejects_nan_and_infinite_timeout():
    assert legs.claude_cli_settings({"claude_cli": {"timeout_seconds": float("nan")}}) == (
        legs.CLAUDE_CLI_DEFAULT_TIMEOUT_SECONDS, legs.CLAUDE_CLI_DEFAULT_MAX_RETRIES,
    )
    assert legs.claude_cli_settings({"claude_cli": {"timeout_seconds": float("inf")}}) == (
        legs.CLAUDE_CLI_DEFAULT_TIMEOUT_SECONDS, legs.CLAUDE_CLI_DEFAULT_MAX_RETRIES,
    )


# --- resolve_opus_route -------------------------------------------------------

def test_resolve_opus_route_uses_claude_cli_when_available(monkeypatch):
    monkeypatch.setattr(legs, "is_claude_cli_available", lambda: (True, ""))
    config = {"external_review": {"opus_leg": {"provider": "claude_cli"}}}
    route, note = legs.resolve_opus_route(config, has_openrouter_key=False)
    assert route == "claude_cli"
    assert note == ""


def test_resolve_opus_route_falls_back_to_openrouter_when_cli_unavailable(monkeypatch):
    monkeypatch.setattr(legs, "is_claude_cli_available", lambda: (False, "claude CLI not found on PATH"))
    config = {"external_review": {"opus_leg": {"provider": "claude_cli"}}}
    route, note = legs.resolve_opus_route(config, has_openrouter_key=True)
    assert route == "openrouter"
    assert "claude CLI unavailable" in note and "falling back to openrouter" in note


def test_resolve_opus_route_falls_back_to_skip_when_neither_is_usable(monkeypatch):
    monkeypatch.setattr(legs, "is_claude_cli_available", lambda: (False, "claude CLI not found on PATH"))
    config = {"external_review": {"opus_leg": {"provider": "claude_cli"}}}
    route, note = legs.resolve_opus_route(config, has_openrouter_key=False)
    assert route == "none"
    assert "skipping this leg" in note


def test_resolve_opus_route_explicit_openrouter_provider_skips_cli_check(monkeypatch):
    def _boom():
        raise AssertionError("is_claude_cli_available must not be called when provider is openrouter")

    monkeypatch.setattr(legs, "is_claude_cli_available", _boom)
    config = {"external_review": {"opus_leg": {"provider": "openrouter"}}}
    route, note = legs.resolve_opus_route(config, has_openrouter_key=True)
    assert route == "openrouter"
    assert note == ""
