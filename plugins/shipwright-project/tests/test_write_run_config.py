"""Tests for write_run_config.py — the project intro gate helper."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from write_run_config import detect_profile, main, write_run_config


# --------------------------------------------------------------------------- #
# detect_profile
# --------------------------------------------------------------------------- #


def test_detect_profile_nextjs(tmp_path):
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({"dependencies": {"next": "^15.0.0", "react": "^19.0.0"}}))
    assert detect_profile(tmp_path) == "supabase-nextjs"


def test_detect_profile_nextjs_in_devdeps(tmp_path):
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({"devDependencies": {"next": "^15.0.0"}}))
    assert detect_profile(tmp_path) == "supabase-nextjs"


def test_detect_profile_no_package_json(tmp_path):
    assert detect_profile(tmp_path) is None


def test_detect_profile_no_next_dep(tmp_path):
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({"dependencies": {"react": "^19.0.0", "vite": "^6.0.0"}}))
    assert detect_profile(tmp_path) is None


def test_detect_profile_invalid_json(tmp_path):
    pkg = tmp_path / "package.json"
    pkg.write_text("{not valid json")
    assert detect_profile(tmp_path) is None


# --------------------------------------------------------------------------- #
# write_run_config
# --------------------------------------------------------------------------- #


def test_write_run_config_creates_valid_json(tmp_path):
    config_path = write_run_config(tmp_path, "supabase-nextjs")
    assert config_path.exists()
    assert config_path.name == "shipwright_run_config.json"

    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["status"] == "pending"
    assert data["current_step"] == "project"
    assert data["profile"] == "supabase-nextjs"
    assert data["standalone"] is False
    assert data["completed_steps"] == []
    assert "project" in data["pipeline"]
    assert "build" in data["pipeline"]
    assert "created_at" in data
    assert "updated_at" in data


def test_write_run_config_raises_when_exists(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text("{}")
    with pytest.raises(FileExistsError):
        write_run_config(tmp_path, "supabase-nextjs")


def test_write_run_config_trailing_newline(tmp_path):
    config_path = write_run_config(tmp_path, "supabase-nextjs")
    assert config_path.read_text(encoding="utf-8").endswith("\n")


# --------------------------------------------------------------------------- #
# main (CLI)
# --------------------------------------------------------------------------- #


def test_main_success(tmp_path, capsys, monkeypatch):
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({"dependencies": {"next": "^15.0.0"}}))
    monkeypatch.setattr(sys, "argv", ["write_run_config.py", "--project-root", str(tmp_path)])
    rc = main()
    assert rc == 0
    assert (tmp_path / "shipwright_run_config.json").exists()
    out = capsys.readouterr().out
    assert "supabase-nextjs" in out


def test_main_missing_profile(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["write_run_config.py", "--project-root", str(tmp_path)])
    rc = main()
    assert rc == 2
    err = capsys.readouterr().err
    assert "could not detect stack profile" in err


def test_main_existing_config(tmp_path, capsys, monkeypatch):
    (tmp_path / "shipwright_run_config.json").write_text("{}")
    monkeypatch.setattr(
        sys,
        "argv",
        ["write_run_config.py", "--project-root", str(tmp_path), "--profile", "supabase-nextjs"],
    )
    rc = main()
    assert rc == 3
    err = capsys.readouterr().err
    assert "already exists" in err


def test_main_not_a_directory(tmp_path, capsys, monkeypatch):
    fake = tmp_path / "does-not-exist"
    monkeypatch.setattr(sys, "argv", ["write_run_config.py", "--project-root", str(fake)])
    rc = main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "not a directory" in err


def test_main_explicit_profile_override(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["write_run_config.py", "--project-root", str(tmp_path), "--profile", "custom-stack"],
    )
    rc = main()
    assert rc == 0
    data = json.loads((tmp_path / "shipwright_run_config.json").read_text())
    assert data["profile"] == "custom-stack"
