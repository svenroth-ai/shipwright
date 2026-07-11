"""Edge/contract tests for brief-intake (K2c) — split from test_brief_intake.py
to keep both files <= the 300-line source ceiling.

Covers the review follow-ups: an unreadable explicit file reference degrades to
the legacy interview (not description=<path>); description is always str|None;
Supabase env labels match the profile; mixed inline prose is preserved.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from brief_intake import (  # noqa: E402
    BRIEF_QUESTIONS, SUPABASE_ENV_QUESTIONS, intake, load_brief, normalize_brief)


# --- MUST-FIX: unreadable explicit file reference -> legacy interview ---

def test_missing_at_prefixed_json_degrades_to_legacy(tmp_path):
    """The realistic WebUI error path: a brief path is passed but the file is
    momentarily absent -> re-ask the four questions, do NOT build the path."""
    missing = tmp_path / "wizard-brief.json"  # never created
    assert load_brief("@" + str(missing)) is None
    result = intake("@" + str(missing))
    assert result["has_brief"] is False
    for q in BRIEF_QUESTIONS:
        assert q in result["remaining_questions"]


def test_missing_bare_brief_suffix_path_degrades_to_legacy(tmp_path):
    # A bare path whose suffix is a brief format is an explicit file reference.
    missing = tmp_path / "brief.md"
    assert load_brief(str(missing)) is None
    assert intake(str(missing))["has_brief"] is False


def test_oversized_brief_file_degrades_to_legacy(tmp_path):
    p = tmp_path / "huge.json"
    p.write_text(json.dumps({"description": "x" * 300000, "persistence": "yes"}),
                 encoding="utf-8")
    assert load_brief(str(p)) is None  # over the size cap -> not read
    assert intake(str(p))["has_brief"] is False


def test_readable_at_prefixed_json_still_loads(tmp_path):
    p = tmp_path / "brief.json"
    p.write_text(json.dumps({"description": "shop", "persistence": "yes",
                             "users": "public", "run_location": "web"}),
                 encoding="utf-8")
    result = intake("@" + str(p))
    assert result["has_brief"] is True
    assert result["profile"] == "supabase-nextjs"


# --- SHOULD-FIX: description is always str | None ---

def test_non_string_description_coerced_to_str():
    r = normalize_brief({"description": 123, "persistence": "no"})
    assert r["description"] == "123"
    r2 = normalize_brief({"description": ["a", "b"]})
    assert isinstance(r2["description"], str)
    # empty/whitespace still collapses to None (still-missing)
    assert normalize_brief({"description": "   "})["description"] is None


# --- SHOULD-FIX: Supabase env labels match the profile's build vars ---

def test_supabase_env_labels_are_next_public_prefixed():
    assert "NEXT_PUBLIC_SUPABASE_URL" in SUPABASE_ENV_QUESTIONS
    assert "NEXT_PUBLIC_SUPABASE_ANON_KEY" in SUPABASE_ENV_QUESTIONS
    # the old bare names must NOT be emitted (they mis-map the build env)
    assert "SUPABASE_URL" not in SUPABASE_ENV_QUESTIONS
    assert "SUPABASE_ANON_KEY" not in SUPABASE_ENV_QUESTIONS
    web_db = intake({"description": "x", "persistence": "yes",
                     "users": "public", "run_location": "web"})
    assert web_db["env_questions"] == list(SUPABASE_ENV_QUESTIONS)


# --- SHOULD-FIX: mixed inline text preserves the free-text description ---

def test_mixed_inline_text_preserves_prose_as_description():
    loaded = load_brief("Build a shop\nusers: public\npersistence: yes")
    assert loaded["description"] == "Build a shop"
    assert loaded["users"] == "public"
    assert loaded["persistence"] == "yes"


def test_pure_keyvalue_payload_still_parses_without_prose():
    loaded = load_brief("description: a shop\nusers: My Team\npersistence: no")
    assert loaded["description"] == "a shop"
    assert loaded["users"] == "My Team"


def test_fenced_json_block_with_nested_object_parses_in_full():
    payload = ('here is your brief:\n```json\n'
               '{"description": "shop", "meta": {"src": "wizard"}, '
               '"persistence": "yes", "run_location": "web"}\n```\n')
    result = intake(payload)
    assert result["has_brief"] is True
    assert result["profile"] == "supabase-nextjs"
