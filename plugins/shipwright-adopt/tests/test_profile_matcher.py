"""Unit tests for profile_matcher.match_profile."""

from pathlib import Path

from lib.profile_matcher import match_profile
from lib.stack_detector import detect_stack


def _profiles_dir() -> Path:
    # Walk up from tests/ to repo root and then to shared/profiles/
    # plugins/shipwright-adopt/tests -> plugins/shipwright-adopt -> plugins -> repo root
    here = Path(__file__).resolve()
    repo_root = here.parent.parent.parent.parent
    return repo_root / "shared" / "profiles"


def test_supabase_nextjs_matched(nextjs_repo: Path) -> None:
    sig = detect_stack(nextjs_repo)
    result = match_profile(sig, _profiles_dir())
    assert result["matched"] == "supabase-nextjs"
    assert result["confidence"] > 0.3


def test_python_matches_plugin_monorepo(python_cli: Path) -> None:
    sig = detect_stack(python_cli)
    result = match_profile(sig, _profiles_dir())
    # Since the 2026-05-02 self-adoption shipped
    # shared/profiles/python-plugin-monorepo.json, a python-only signature
    # now matches that profile (Jaccard score 1.0) instead of falling back
    # to generic. The old assertion was correct for the world with no python
    # profile in shared/profiles/; updated to reflect current behavior.
    assert result["matched"] == "python-plugin-monorepo"
    assert result["confidence"] >= 0.30


def test_missing_profiles_dir(tmp_path: Path) -> None:
    sig = {"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}}
    result = match_profile(sig, tmp_path / "nonexistent")
    assert result["matched"] == "generic"
    assert result["confidence"] == 0.0
