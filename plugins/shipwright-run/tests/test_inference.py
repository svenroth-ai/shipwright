"""Tests for inference engine."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from inference import detect_profile, detect_scope, infer_settings

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "lib" / "inference.py")


# --- Scope detection ---

def test_scope_full_app_no_project(tmp_path):
    scope, signals = detect_scope(tmp_path)
    assert scope == "full_app"


def test_scope_extension_existing_project(existing_project):
    scope, signals = detect_scope(existing_project)
    assert scope == "extension"
    assert any("CLAUDE.md" in s for s in signals)


def test_scope_iterate_flag():
    scope, signals = detect_scope(iterate=True)
    assert scope == "iterate"


# --- Profile detection ---

def test_profile_supabase_nextjs():
    profile, confidence, signals = detect_profile("Build a SaaS app with Supabase and Next.js")
    assert profile == "supabase-nextjs"
    assert confidence == "high"


def test_profile_supabase_only():
    profile, confidence, signals = detect_profile("Build an app with Supabase")
    assert profile == "supabase-nextjs"


def test_profile_nextjs_only():
    profile, confidence, signals = detect_profile("Build a Next.js dashboard")
    assert profile == "supabase-nextjs"


def test_profile_no_match():
    profile, confidence, signals = detect_profile("Build a CLI tool in Rust")
    assert profile is None
    assert confidence == "none"


def test_profile_case_insensitive():
    profile, _, _ = detect_profile("I want SUPABASE with NEXTJS")
    assert profile == "supabase-nextjs"


# --- Full inference ---

def test_infer_full_app():
    result = infer_settings("Build a time tracker with Supabase and Next.js")
    assert result["scope"] == "full_app"
    assert result["profile"] == "supabase-nextjs"
    assert result["autonomy"] == "guided"


def test_infer_extension(existing_project):
    result = infer_settings(
        "Add dark mode",
        project_root=str(existing_project),
    )
    assert result["scope"] == "extension"


def test_infer_iterate(existing_project):
    result = infer_settings(
        "Fix the login button",
        project_root=str(existing_project),
        iterate=True,
    )
    assert result["scope"] == "iterate"


# --- CLI ---

def test_cli_output():
    result = subprocess.run(
        [sys.executable, SCRIPT,
         "--description", "Build a SaaS app with Supabase"],
        capture_output=True, text=True, encoding="utf-8",
    )
    output = json.loads(result.stdout)
    assert output["profile"] == "supabase-nextjs"
    assert output["scope"] == "full_app"
