"""Unit tests for Codex CLI binary resolution and availability detection
(`external_review_default_legs.py`): `_resolve_codex_binary` (cwd-hijack
guard, exception safety) and `is_codex_available` (never raises, bounded
timeout). Split out of `test_external_review_codex_leg.py` to stay under
the 300-line guideline.
"""

import subprocess
import sys
from pathlib import Path

import pytest

_LIB_DIR = Path(__file__).resolve().parents[1] / "scripts" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import external_review_default_legs as legs  # noqa: E402


class _FakeCompleted:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


# --- _resolve_codex_binary cwd-hijack guard (BatBadBut: a reviewed repo could plant its own
# codex.exe/.cmd/.bat at its root and have shutil.which prefer it over the real PATH install) ---

@pytest.mark.parametrize("in_cwd,expected", [(True, None), (False, "/usr/bin/codex")])
def test_resolve_codex_binary_cwd_hijack_guard(monkeypatch, tmp_path, in_cwd, expected):
    monkeypatch.chdir(tmp_path)
    hit = str(tmp_path / "codex.exe") if in_cwd else "/usr/bin/codex"
    monkeypatch.setattr(legs.shutil, "which", lambda _name: hit)
    assert legs._resolve_codex_binary() == expected


def test_resolve_codex_binary_never_raises_on_a_symlink_loop(monkeypatch, tmp_path):
    """Path.resolve() raises RuntimeError (not OSError) on a symlink loop — is_codex_available()'s
    "never raises" contract must survive that too."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(legs.Path, "resolve", lambda self: (_ for _ in ()).throw(RuntimeError("symlink loop")))
    assert legs._resolve_codex_binary() is None


# --- is_codex_available -----------------------------------------------------

def test_unavailable_when_binary_not_on_path(monkeypatch):
    monkeypatch.setattr(legs.shutil, "which", lambda _name: None)
    available, reason = legs.is_codex_available()
    assert available is False
    assert "not found on PATH" in reason


def test_unavailable_when_not_authenticated(monkeypatch):
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(legs.subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=1))
    available, reason = legs.is_codex_available()
    assert available is False
    assert "not authenticated" in reason


def test_unavailable_on_login_status_timeout(monkeypatch):
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/codex")

    def _raise(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="codex", timeout=15)

    monkeypatch.setattr(legs.subprocess, "run", _raise)
    available, reason = legs.is_codex_available()
    assert available is False
    assert "timed out" in reason


def test_unavailable_on_oserror_never_raises(monkeypatch):
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(legs.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    available, reason = legs.is_codex_available()
    assert available is False
    assert "boom" in reason


def test_available_when_installed_and_authenticated(monkeypatch):
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(legs.subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=0))
    available, reason = legs.is_codex_available()
    assert available is True
    assert reason == ""
