"""Edge/contract tests for brief-intake (K2c) — split from test_brief_intake.py
to keep both files <= the 300-line source ceiling.

Covers the review follow-ups: an unreadable explicit file reference degrades to
the legacy interview (not description=<path>); description is always str|None;
Supabase env labels match the profile; mixed inline prose is preserved.
"""

import json
import sys
from pathlib import Path

import pytest

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


# --- run route: an unusable brief FILE is refused, never swapped for the interview ---

@pytest.mark.covers("FR-01.16/AC01")
def test_package_route_refuses_missing_brief_file(tmp_path):
    result = intake("@" + str(tmp_path / "gone.json"), str(tmp_path), package=True)
    assert result["refused"] is True and result["code"] == "brief_unreadable"
    assert result["has_brief"] is False


@pytest.mark.covers("FR-01.16/AC01")
def test_package_route_refuses_unsupported_suffix(tmp_path):
    (tmp_path / "brief.pdf").write_bytes(b"%PDF")
    for source in ("@" + str(tmp_path / "brief.pdf"), str(tmp_path / "brief.pdf")):
        result = intake(source, str(tmp_path), package=True)
        assert result["refused"] is True and "unsupported suffix" in result["message"]


@pytest.mark.covers("FR-01.16/AC01")
def test_package_route_still_reads_a_good_file_and_plain_descriptions(tmp_path):
    good = tmp_path / "brief.md"
    good.write_text("description: a notes app\n", encoding="utf-8")
    assert intake(str(good), str(tmp_path), package=True)["has_brief"] is True
    assert intake("Build a SaaS time tracker", str(tmp_path), package=True)["has_brief"] is True


@pytest.mark.covers("FR-01.16/AC01")
def test_non_package_route_keeps_the_degrade_for_adopt(tmp_path):
    assert intake("@" + str(tmp_path / "gone.json"))["has_brief"] is False


@pytest.mark.covers("FR-01.16/AC01")
def test_package_route_refuses_a_document_path_with_spaces(tmp_path):
    result = intake(str(tmp_path / "dinovo GmbH" / "brief.pdf"), str(tmp_path), package=True)
    assert result["code"] == "brief_unreadable"


@pytest.mark.covers("FR-01.16/AC01")
def test_cli_exits_3_on_an_unreadable_brief_file(tmp_path, monkeypatch, capsys):
    import brief_intake
    monkeypatch.setattr(sys, "argv", ["brief_intake.py", "--brief", "@" + str(tmp_path / "gone.json"),
                                      "--project-root", str(tmp_path)])
    assert brief_intake.main() == 3
    assert json.loads(capsys.readouterr().out)["code"] == "brief_unreadable"


@pytest.mark.covers("FR-01.16/AC01")
def test_package_route_keeps_a_description_ending_in_a_file_name(tmp_path):
    result = intake("Build an app that edits package.json", str(tmp_path), package=True)
    assert result.get("refused") is None  # not mistaken for a file (load_brief's own legacy degrade is unchanged)


@pytest.mark.covers("FR-01.16/AC01")
def test_package_route_refuses_a_bare_relative_spaced_document(tmp_path):
    assert intake("my notes v2.pdf", str(tmp_path), package=True)["code"] == "brief_unreadable"
