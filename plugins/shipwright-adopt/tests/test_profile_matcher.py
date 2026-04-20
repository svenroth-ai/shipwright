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


def test_python_falls_to_generic(python_cli: Path) -> None:
    sig = detect_stack(python_cli)
    result = match_profile(sig, _profiles_dir())
    # Only supabase-nextjs profile exists today; Python CLI should fall back
    assert result["matched"] == "generic"


def test_missing_profiles_dir(tmp_path: Path) -> None:
    sig = {"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}}
    result = match_profile(sig, tmp_path / "nonexistent")
    assert result["matched"] == "generic"
    assert result["confidence"] == 0.0
