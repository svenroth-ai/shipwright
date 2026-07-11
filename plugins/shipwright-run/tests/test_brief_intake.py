"""Tests for brief-intake (K2c): full brief -> no re-ask + right profile;
partial brief -> asks only the gap; no brief -> legacy interview unchanged.
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from brief_intake import (  # noqa: E402
    BRIEF_QUESTIONS, intake, load_brief, map_brief, normalize_brief)

SCRIPT = str(
    Path(__file__).resolve().parent.parent / "scripts" / "lib" / "brief_intake.py"
)

FULL_WEB_DB = {
    "description": "A booking tool for my yoga studio",
    "users": "public",
    "persistence": "yes",
    "run_location": "web",
}

FULL_LOCAL_NODB = {
    "description": "A tool that turns meeting notes into follow-up emails",
    "users": "just_me",
    "persistence": "no",
    "run_location": "local",
}


# --- normalize_brief: synonym tolerance ---

def test_normalize_canonical_values():
    b = normalize_brief(FULL_WEB_DB)
    assert b["users"] == "public"
    assert b["persistence"] == "yes"
    assert b["run_location"] == "web"


def test_normalize_synonyms():
    raw = {
        "description": "x",
        "users": "Customers / public",
        "persistence": "Not sure yet",
        "run_location": "Just my machine",
    }
    b = normalize_brief(raw)
    assert b["users"] == "public"
    assert b["persistence"] == "unsure"
    assert b["run_location"] == "local"


def test_normalize_unknown_value_becomes_none():
    b = normalize_brief({"users": "aliens", "persistence": "", "run_location": None})
    assert b["users"] is None
    assert b["persistence"] is None
    assert b["run_location"] is None


def test_normalize_ambiguous_phrases_fall_through_to_remaining():
    """Conservative: ambiguous plain-language answers are never guessed — they
    collapse to None (still-missing) so the interview asks, not mis-selects."""
    for phrase in ("maybe later", "prototype first", "host it somewhere"):
        b = normalize_brief({"persistence": phrase, "run_location": phrase})
        assert b["persistence"] is None
        assert b["run_location"] is None
        result = map_brief(b)
        assert "persistence" in result["remaining_questions"]
        assert "run_location" in result["remaining_questions"]
        assert result["profile"] is None  # never guessed from ambiguous input


# --- map_brief: profile / deploy / env / remaining ---

def test_full_brief_persistence_yes_selects_supabase():
    result = map_brief(normalize_brief(FULL_WEB_DB))
    assert result["profile"] == "supabase-nextjs"
    assert result["deploy_target"] == "jelastic-dev"
    assert result["auth_scope"] == "public"
    # the four wizard answers are NOT re-asked
    for q in BRIEF_QUESTIONS:
        assert q not in result["remaining_questions"]
    assert set(result["answered"]) == set(BRIEF_QUESTIONS)


def test_full_brief_persistence_no_selects_vite_hono_default():
    result = map_brief(normalize_brief(FULL_LOCAL_NODB))
    assert result["profile"] == "vite-hono"
    assert result["deploy_target"] == "none"
    assert result["auth_scope"] == "none"
    assert result["env_questions"] == []
    for q in BRIEF_QUESTIONS:
        assert q not in result["remaining_questions"]


def test_persistence_unsure_selects_vite_hono():
    result = map_brief(normalize_brief({**FULL_LOCAL_NODB, "persistence": "unsure"}))
    assert result["profile"] == "vite-hono"


def test_env_questions_only_when_web_and_persistence():
    # web + persistence -> supabase env asked
    web_db = map_brief(normalize_brief(FULL_WEB_DB))
    assert web_db["env_questions"]  # non-empty
    # persistence but local -> no env questions yet
    local_db = map_brief(normalize_brief({**FULL_WEB_DB, "run_location": "local"}))
    assert local_db["env_questions"] == []
    # web but no persistence -> vite-hono, no supabase env
    web_nodb = map_brief(normalize_brief({**FULL_WEB_DB, "persistence": "no"}))
    assert web_nodb["env_questions"] == []


# --- partial brief: asks only the gap ---

def test_partial_brief_missing_persistence_asks_only_that():
    partial = dict(FULL_WEB_DB)
    del partial["persistence"]
    result = map_brief(normalize_brief(partial))
    assert "persistence" in result["remaining_questions"]
    # the answered ones are not re-asked
    assert "description" not in result["remaining_questions"]
    assert "users" not in result["remaining_questions"]
    assert "run_location" not in result["remaining_questions"]
    # profile cannot be fixed without persistence
    assert result["profile"] is None


def test_partial_brief_description_only():
    result = map_brief(normalize_brief({"description": "a CLI tool"}))
    assert "description" not in result["remaining_questions"]
    assert "users" in result["remaining_questions"]
    assert "persistence" in result["remaining_questions"]
    assert "run_location" in result["remaining_questions"]


# --- contradictory / partial field interplay (review OpenAI #8) ---

def test_persistence_yes_but_local_defers_env():
    # Real DB on the local machine: supabase profile, deploy none, env deferred.
    result = map_brief(normalize_brief({**FULL_WEB_DB, "run_location": "local"}))
    assert result["profile"] == "supabase-nextjs"
    assert result["deploy_target"] == "none"
    assert result["env_questions"] == []


def test_persistence_yes_run_location_missing_asks_location_defers_env():
    partial = {**FULL_WEB_DB}
    del partial["run_location"]
    result = map_brief(normalize_brief(partial))
    assert result["profile"] == "supabase-nextjs"
    assert result["deploy_target"] is None
    assert "run_location" in result["remaining_questions"]
    assert result["env_questions"] == []  # deferred until web is known


# --- no brief: legacy interview unchanged ---

def test_no_brief_all_questions_remain():
    result = intake(None)
    assert result["has_brief"] is False
    assert result["profile"] is None
    for q in BRIEF_QUESTIONS:
        assert q in result["remaining_questions"]
    assert result["answered"] == []


# --- load_brief: file path + payload shapes ---

def test_load_brief_from_json_file(tmp_path):
    p = tmp_path / "brief.json"
    p.write_text(json.dumps(FULL_WEB_DB), encoding="utf-8")
    loaded = load_brief(str(p))
    assert loaded["persistence"] == "yes"


def test_load_brief_at_prefix_path(tmp_path):
    p = tmp_path / "brief.json"
    p.write_text(json.dumps(FULL_LOCAL_NODB), encoding="utf-8")
    loaded = load_brief("@" + str(p))
    assert loaded["run_location"] == "local"


def test_load_brief_inline_json_payload():
    loaded = load_brief(json.dumps(FULL_WEB_DB))
    assert loaded["users"] == "public"


def test_load_brief_plain_text_is_description_only():
    loaded = load_brief("Build me a Rust CLI")
    assert loaded["description"] == "Build me a Rust CLI"
    assert "users" not in loaded or loaded.get("users") is None


def test_load_brief_inline_keyvalue_payload():
    # Inline key:value payload is parsed for fields, not description-only.
    loaded = load_brief("description: a shop\nusers: public\npersistence: yes")
    assert loaded["users"] == "public"
    assert loaded["persistence"] == "yes"


def test_load_brief_none():
    assert load_brief(None) is None


# --- malformed / hostile file inputs (review OpenAI #11 + security) ---

def test_load_brief_malformed_json_file_degrades(tmp_path):
    """A malformed .json brief must degrade, not crash the run."""
    p = tmp_path / "broken.json"
    p.write_text('{"description": "half a bri', encoding="utf-8")
    load_brief(str(p))  # must not raise
    result = intake(str(p))  # degrades to a usable (description-only) brief
    assert result["has_brief"] is True


def test_non_dict_json_shape_degrades_not_crashes(tmp_path):
    # Wrong-shape brief (JSON array/scalar) degrades to all-missing, not a crash.
    p = tmp_path / "arr.json"
    p.write_text(json.dumps(["a", "b"]), encoding="utf-8")
    assert intake(str(p))["profile"] is None  # must not raise
    assert intake(42)["profile"] is None


def test_load_brief_empty_file_yields_all_remaining(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text("", encoding="utf-8")
    result = intake(str(p))
    for q in ("users", "persistence", "run_location"):
        assert q in result["remaining_questions"]


def test_load_brief_disallowed_suffix_not_read_as_file(tmp_path):
    # An unreadable explicit file ref: content never leaks AND it degrades to
    # the legacy interview (has_brief False) — not description=<the path>.
    secret = tmp_path / "secret.conf"
    secret.write_text("password=hunter2", encoding="utf-8")
    assert load_brief("@" + str(secret)) is None  # @/etc/passwd can't leak
    assert intake("@" + str(secret))["has_brief"] is False


# --- round-trip: write brief -> parse -> assert mapping (io-boundary probe) ---

def test_roundtrip_json_file(tmp_path):
    p = tmp_path / "wizard-brief.json"
    p.write_text(json.dumps(FULL_WEB_DB), encoding="utf-8")
    result = intake(str(p))
    assert result["has_brief"] is True
    assert result["profile"] == "supabase-nextjs"
    assert result["deploy_target"] == "jelastic-dev"
    for q in BRIEF_QUESTIONS:
        assert q not in result["remaining_questions"]


def test_roundtrip_utf8_bom_and_crlf(tmp_path):
    # human/edited or Windows-written brief may carry a BOM + CRLF newlines
    p = tmp_path / "brief-bom.json"
    body = json.dumps(FULL_LOCAL_NODB).replace("\n", "\r\n")
    p.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    result = intake(str(p))
    assert result["profile"] == "vite-hono"
    assert result["deploy_target"] == "none"


def test_intake_partial_brief_object():
    partial = dict(FULL_WEB_DB)
    del partial["run_location"]
    result = intake(partial)
    assert result["has_brief"] is True
    assert "run_location" in result["remaining_questions"]
    assert "description" not in result["remaining_questions"]


# --- CLI ---

def test_cli_full_brief(tmp_path):
    p = tmp_path / "brief.json"
    p.write_text(json.dumps(FULL_WEB_DB), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, SCRIPT, "--brief", str(p)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["profile"] == "supabase-nextjs"
    assert out["has_brief"] is True


def test_cli_no_brief():
    result = subprocess.run(
        [sys.executable, SCRIPT],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["has_brief"] is False
    for q in BRIEF_QUESTIONS:
        assert q in out["remaining_questions"]
