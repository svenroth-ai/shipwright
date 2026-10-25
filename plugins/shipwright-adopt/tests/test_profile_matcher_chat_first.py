"""Adopt matching is unchanged by the bundled `chat-first-json` profile (brief unit B4).

Every existing fixture must match the same bundled profile with the same
confidence whether or not `chat-first-json` sits in the profiles directory.
"""

import shutil
from pathlib import Path

import pytest

from lib.profile_matcher import match_profile
from lib.stack_detector import detect_stack

pytestmark = pytest.mark.covers("FR-01.06")

_PROFILES = Path(__file__).resolve().parents[3] / "shared" / "profiles"


@pytest.fixture
def profiles_without_chat_first(tmp_path: Path) -> Path:
    out = tmp_path / "profiles"
    out.mkdir()
    for f in _PROFILES.glob("*.json"):
        if f.stem != "chat-first-json":
            shutil.copy(f, out / f.name)
    return out


@pytest.mark.parametrize("fixture_name", ["nextjs_repo", "python_cli", "polyglot_monorepo", "nested_shipwright"])
def test_existing_fixtures_match_the_same_profile_with_and_without_chat_first(
    fixture_name, request, profiles_without_chat_first
):
    sig = detect_stack(request.getfixturevalue(fixture_name))
    before = match_profile(sig, profiles_without_chat_first)
    after = match_profile(sig, _PROFILES)
    assert (after["matched"], after["confidence"], after["source"]) == (
        before["matched"], before["confidence"], before["source"])
    assert after["matched"] != "chat-first-json"
