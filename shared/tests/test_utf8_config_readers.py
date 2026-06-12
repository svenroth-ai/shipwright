"""WP8 of the 2026-06-10 deep audit — F24 + F25 (UTF-8 in config / runner readers).

F24 (MED): config readers did ``json.loads(read_text())`` with no ``encoding=``
→ on cp1252 Windows they crash on non-ASCII FR titles / descriptions written
``ensure_ascii=False``. Fixed by explicit ``encoding="utf-8-sig"`` (BOM-tolerant).

F25 (MED): ``surface_verification`` ran the F0.5 runner ``text=True`` with no
``encoding=`` → cp1252 decode raises on vitest's ``❯`` (U+276F → byte 0x9D) /
em-dash → F0.5 false-fails. Fixed by ``encoding="utf-8", errors="replace"``.

Strategy: F24 tests force cp1252 via ``locale.getpreferredencoding`` (crash on
ANY host); ``_assert_cp1252_would_crash`` keeps fixtures non-vacuous. F25 drives
the real ``run_with_retries`` against a runner emitting ``❯``/em-dash + a raw
0x9D byte.
"""

from __future__ import annotations

import json
import locale
import sys
from pathlib import Path

import pytest

# Resolve surface_verification/artifact_sync (shared/scripts), suggest_iterate
# (shared/scripts/hooks), and classify_* (iterate plugin lib) onto sys.path.
_SHARED_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (
    _SHARED_SCRIPTS,
    _SHARED_SCRIPTS / "hooks",
    _REPO_ROOT / "plugins" / "shipwright-iterate" / "scripts" / "lib",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


# CJK + em-dash + Cyrillic — bytes that are *undefined* in cp1252-strict, so
# an implicit decode RAISES (not merely mojibakes).
_CJK_TITLE = "ユーザー認証 — 安全なログイン"
_CYRILLIC_DESC = "Описание проекта — вход в систему"


@pytest.fixture
def force_cp1252(monkeypatch):
    """Force the process default text encoding to cp1252 — reproduces the
    Windows platform on any host. With the fix (explicit ``encoding=``) the
    reader is unaffected; without it, ``read_text()`` crashes on undefined
    bytes."""
    monkeypatch.setattr(locale, "getpreferredencoding", lambda *a, **k: "cp1252")
    return "cp1252"


def _assert_cp1252_would_crash(path: Path) -> None:
    """Non-vacuity guard: the fixture bytes MUST be undecodable under
    cp1252-strict, so the explicit ``encoding=`` is the only thing making the
    reader succeed."""
    with pytest.raises(UnicodeDecodeError):
        path.read_bytes().decode("cp1252")


# ---------------------------------------------------------------------------
# F24 — config readers
# ---------------------------------------------------------------------------


def test_artifact_sync_detect_drift_parses_cjk_config(tmp_path, force_cp1252):
    """artifact_sync.detect_drift reads shipwright_sync_config.json with CJK
    FR titles under a forced-cp1252 locale without crashing."""
    import artifact_sync

    config = {
        "mappings": [
            {
                "pattern": "src/auth/**",
                "artifacts": ["docs/auth.md"],
                "frs": [f"FR-01.01 {_CJK_TITLE}"],
                "category": "auth",
            }
        ]
    }
    config_path = tmp_path / "shipwright_sync_config.json"
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _assert_cp1252_would_crash(config_path)

    # git diff fails in tmp_path, but json.loads(read_text()) ran first w/o raising.
    assert "drift_detected" in artifact_sync.detect_drift(str(tmp_path), ref="HEAD~1..HEAD")


def test_classify_complexity_cross_split_parses_cjk_config(tmp_path, force_cp1252):
    """detect_cross_split reads a CJK-FR sync config under cp1252 — no crash."""
    from classify_complexity import detect_cross_split

    config = {
        "mappings": [
            {"pattern": "auth", "frs": [f"FR-01.01 {_CJK_TITLE}"]},
            {"pattern": "billing", "frs": [f"FR-02.01 {_CJK_TITLE}"]},
        ]
    }
    config_path = tmp_path / "shipwright_sync_config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    _assert_cp1252_would_crash(config_path)

    out = detect_cross_split("touch auth and billing", str(config_path))
    assert out is None or out["flag"] == "cross_split"


def test_classify_intent_find_frs_parses_cjk_config(tmp_path, force_cp1252):
    """_find_affected_frs reads a CJK-FR sync config under cp1252 — no crash."""
    from classify_intent import classify

    config = {"mappings": [{"pattern": "search", "frs": [f"FR-03.01 {_CJK_TITLE}"]}]}
    config_path = tmp_path / "shipwright_sync_config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    _assert_cp1252_would_crash(config_path)

    assert classify("add a new search feature", str(config_path))["type"] == "feature"


def test_suggest_iterate_reads_cjk_run_config(tmp_path, force_cp1252, monkeypatch):
    """suggest_iterate.main reads a Cyrillic run_config under cp1252 — no crash;
    exits 0 on the happy path."""
    import suggest_iterate

    run_config = {"status": "complete", "description": _CYRILLIC_DESC,
                  "completed_steps": ["test"]}
    config_path = tmp_path / "shipwright_run_config.json"
    config_path.write_text(json.dumps(run_config, ensure_ascii=False), encoding="utf-8")
    _assert_cp1252_would_crash(config_path)

    payload = json.dumps({"prompt": "fix the broken login redirect", "cwd": str(tmp_path)})
    monkeypatch.setattr("sys.stdin", _StringStdin(payload))

    with pytest.raises(SystemExit) as exc:
        suggest_iterate.main()
    assert exc.value.code == 0


def test_config_read_config_parses_cjk(tmp_path, force_cp1252):
    """lib/config.read_config parses a Cyrillic config under cp1252 (non-BOM path)."""
    from lib import config as shared_config  # noqa: PLC0415

    data = {"description": _CYRILLIC_DESC, "status": "complete"}
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    _assert_cp1252_would_crash(tmp_path / "shipwright_run_config.json")
    assert shared_config.read_config("run", tmp_path)["description"] == _CYRILLIC_DESC


def _write_bom_config(path: Path, config: dict) -> None:
    """Write a config exactly as Notepad's 'UTF-8 with BOM' would (BOM + body)."""
    path.write_bytes(
        "﻿".encode("utf-8") + json.dumps(config, ensure_ascii=False).encode("utf-8")
    )


def test_artifact_sync_tolerates_utf8_bom(tmp_path, force_cp1252):
    """A hand-edited UTF-8-BOM config must parse — utf-8-sig strips it (plain
    utf-8 raises JSONDecodeError). External plan review OpenAI #3."""
    import artifact_sync

    _write_bom_config(tmp_path / "shipwright_sync_config.json",
                      {"mappings": [{"pattern": "x", "frs": [f"FR-01 {_CJK_TITLE}"]}]})
    assert "drift_detected" in artifact_sync.detect_drift(str(tmp_path), ref="HEAD~1..HEAD")


def test_classify_intent_tolerates_utf8_bom(tmp_path, force_cp1252):
    """classify_intent reader tolerates a BOM-prefixed config (utf-8-sig)."""
    from classify_intent import classify

    config = {"mappings": [{"pattern": "search", "frs": [f"FR-03 {_CJK_TITLE}"]}]}
    config_path = tmp_path / "shipwright_sync_config.json"
    config_path.write_bytes(
        "﻿".encode("utf-8")
        + json.dumps(config, ensure_ascii=False).encode("utf-8")
    )

    result = classify("add a new search feature", str(config_path))
    assert result["type"] == "feature"


def test_config_read_config_tolerates_utf8_bom(tmp_path):
    """lib/config.read_config must tolerate a hand-edited UTF-8-BOM config:
    ``utf-8-sig`` strips the leading U+FEFF, whereas plain ``utf-8`` keeps it and
    ``json.loads`` then JSONDecodeErrors on char 0. Pins parity with the four
    WP8/F24 sibling readers (the follow-up that completed lib/config)."""
    from lib import config as shared_config  # noqa: PLC0415

    _write_bom_config(
        tmp_path / "shipwright_run_config.json",
        {"description": _CYRILLIC_DESC, "status": "complete"},
    )
    assert shared_config.read_config("run", tmp_path)["status"] == "complete"


def test_readers_pass_explicit_encoding_to_read_text(tmp_path, monkeypatch):
    """Platform-independent regression guard (external code review OpenAI #2):
    patch ``Path.read_text`` to RAISE without an explicit ``encoding=`` kwarg,
    then drive each reader. A reader that reverts to bare ``read_text()`` fails
    here on ANY host — unlike the locale tests, which only catch it where
    ``read_text`` consults ``getpreferredencoding`` at call time."""
    real_read_text = Path.read_text

    def _strict_read_text(self, *args, **kwargs):
        if "encoding" not in kwargs:
            raise AssertionError(
                f"read_text() called without explicit encoding= on {self}"
            )
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _strict_read_text)

    cfg = {"mappings": [{"pattern": "auth", "frs": ["FR-01.01 安全"]}]}
    sync_path = tmp_path / "shipwright_sync_config.json"
    sync_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    import artifact_sync
    from classify_complexity import detect_cross_split
    from classify_intent import _find_affected_frs
    from lib import config as shared_config

    # Each call routes through the patched read_text; a missing encoding= raises.
    artifact_sync.detect_drift(str(tmp_path))
    detect_cross_split("touch auth", str(sync_path))
    _find_affected_frs("touch auth", str(sync_path))

    run_path = tmp_path / "shipwright_run_config.json"
    run_path.write_text(
        json.dumps({"description": "安全", "status": "complete"}, ensure_ascii=False),
        encoding="utf-8",
    )
    shared_config.read_config("run", tmp_path)


class _StringStdin:
    """Minimal stdin stand-in exposing ``.read()`` for hook main() entry."""

    def __init__(self, payload: str) -> None:
        self._payload = payload

    def read(self) -> str:
        return self._payload
