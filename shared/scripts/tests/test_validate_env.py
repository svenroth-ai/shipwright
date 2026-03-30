"""Tests for shared.scripts.validate_env module."""

import json

import pytest

from shared.scripts.validate_env import init_env_file, parse_env_file, validate


@pytest.fixture
def profile_dir(tmp_path):
    """Create a temporary profile directory with a test profile."""
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    profile = {
        "name": "test-profile",
        "required_env_vars": {
            "build": [
                {"name": "NEXT_PUBLIC_SUPABASE_URL", "description": "Supabase project URL"},
                {"name": "NEXT_PUBLIC_SUPABASE_ANON_KEY", "description": "Supabase anonymous key"},
            ],
            "deploy": [
                {"name": "JELASTIC_TOKEN", "description": "Jelastic API token"},
                {"name": "SUPABASE_ACCESS_TOKEN", "description": "Supabase CLI token", "optional": True},
            ],
        },
    }
    (profiles / "test-profile.json").write_text(json.dumps(profile), encoding="utf-8")
    return profiles


@pytest.fixture
def project_root(tmp_path):
    """Create a temporary project root with run config."""
    root = tmp_path / "project"
    root.mkdir()
    run_config = {"profile": "test-profile"}
    (root / "shipwright_run_config.json").write_text(json.dumps(run_config), encoding="utf-8")
    return root


class TestParseEnvFile:
    def test_simple_vars(self, tmp_path):
        env_file = tmp_path / ".env.local"
        env_file.write_text("FOO=bar\nBAZ=qux\n", encoding="utf-8")
        result = parse_env_file(env_file)
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_quoted_values(self, tmp_path):
        env_file = tmp_path / ".env.local"
        env_file.write_text('KEY="hello world"\nKEY2=\'single\'\n', encoding="utf-8")
        result = parse_env_file(env_file)
        assert result == {"KEY": "hello world", "KEY2": "single"}

    def test_comments_and_blanks(self, tmp_path):
        env_file = tmp_path / ".env.local"
        env_file.write_text("# comment\n\nKEY=val\n  # indented comment\n", encoding="utf-8")
        result = parse_env_file(env_file)
        assert result == {"KEY": "val"}

    def test_nonexistent_file(self, tmp_path):
        result = parse_env_file(tmp_path / "missing")
        assert result == {}

    def test_no_equals(self, tmp_path):
        env_file = tmp_path / ".env.local"
        env_file.write_text("INVALID_LINE\nKEY=val\n", encoding="utf-8")
        result = parse_env_file(env_file)
        assert result == {"KEY": "val"}


class TestValidateBuild:
    def test_all_vars_present(self, project_root, profile_dir):
        env_file = project_root / ".env.local"
        env_file.write_text(
            "NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co\n"
            "NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGci...\n",
            encoding="utf-8",
        )
        result = validate(project_root, "build", profile_dir)
        assert result["success"] is True
        assert result["skipped"] is False
        assert len(result["found"]) == 2
        assert result["missing"] == []
        assert result["env_file_exists"] is True

    def test_missing_vars(self, project_root, profile_dir):
        result = validate(project_root, "build", profile_dir)
        assert result["success"] is False
        assert result["skipped"] is False
        assert len(result["missing"]) == 2
        assert result["missing"][0]["name"] == "NEXT_PUBLIC_SUPABASE_URL"
        assert result["env_file_exists"] is False

    def test_partial_vars(self, project_root, profile_dir):
        env_file = project_root / ".env.local"
        env_file.write_text("NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co\n", encoding="utf-8")
        result = validate(project_root, "build", profile_dir)
        assert result["success"] is False
        assert len(result["found"]) == 1
        assert len(result["missing"]) == 1
        assert result["missing"][0]["name"] == "NEXT_PUBLIC_SUPABASE_ANON_KEY"

    def test_vars_from_os_environ(self, project_root, profile_dir, monkeypatch):
        monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co")
        monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "eyJhbGci...")
        result = validate(project_root, "build", profile_dir)
        assert result["success"] is True
        assert len(result["found"]) == 2


class TestValidateDeploy:
    def test_required_deploy_var_present(self, project_root, profile_dir, monkeypatch):
        monkeypatch.setenv("JELASTIC_TOKEN", "abc123")
        result = validate(project_root, "deploy", profile_dir)
        assert result["success"] is True
        assert "JELASTIC_TOKEN" in result["found"]
        assert len(result["optional_missing"]) == 1
        assert result["optional_missing"][0]["name"] == "SUPABASE_ACCESS_TOKEN"

    def test_missing_required_deploy_var(self, project_root, profile_dir, monkeypatch):
        monkeypatch.delenv("JELASTIC_TOKEN", raising=False)
        result = validate(project_root, "deploy", profile_dir)
        assert result["success"] is False
        assert len(result["missing"]) == 1
        assert result["missing"][0]["name"] == "JELASTIC_TOKEN"

    def test_all_deploy_vars_present(self, project_root, profile_dir, monkeypatch):
        monkeypatch.setenv("JELASTIC_TOKEN", "abc123")
        monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", "sbp_token")
        result = validate(project_root, "deploy", profile_dir)
        assert result["success"] is True
        assert result["optional_missing"] == []
        assert len(result["found"]) == 2


class TestSkipConditions:
    def test_no_run_config(self, tmp_path, profile_dir):
        project = tmp_path / "empty_project"
        project.mkdir()
        result = validate(project, "build", profile_dir)
        assert result["success"] is True
        assert result["skipped"] is True
        assert "No shipwright_run_config.json" in result["skip_reason"]

    def test_no_profile_in_config(self, tmp_path, profile_dir):
        project = tmp_path / "no_profile"
        project.mkdir()
        (project / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
        result = validate(project, "build", profile_dir)
        assert result["success"] is True
        assert result["skipped"] is True
        assert "No profile set" in result["skip_reason"]

    def test_missing_profile_file(self, tmp_path, profile_dir):
        project = tmp_path / "bad_profile"
        project.mkdir()
        (project / "shipwright_run_config.json").write_text(
            json.dumps({"profile": "nonexistent"}), encoding="utf-8"
        )
        result = validate(project, "build", profile_dir)
        assert result["success"] is True
        assert result["skipped"] is True
        assert "not found" in result["skip_reason"]

    def test_no_required_env_vars_for_phase(self, tmp_path):
        profiles = tmp_path / "profiles"
        profiles.mkdir()
        (profiles / "empty.json").write_text(json.dumps({"name": "empty"}), encoding="utf-8")
        project = tmp_path / "proj"
        project.mkdir()
        (project / "shipwright_run_config.json").write_text(
            json.dumps({"profile": "empty"}), encoding="utf-8"
        )
        result = validate(project, "build", profiles)
        assert result["success"] is True
        assert result["skipped"] is True


class TestInitEnvFile:
    def test_creates_env_local_when_missing(self, project_root, profile_dir):
        result = init_env_file(project_root, "build", profile_dir)
        assert result["action"] == "created"
        assert result["profile"] == "test-profile"
        assert "NEXT_PUBLIC_SUPABASE_URL" in result["vars"]
        assert "NEXT_PUBLIC_SUPABASE_ANON_KEY" in result["vars"]

        env_file = project_root / ".env.local"
        assert env_file.exists()
        content = env_file.read_text(encoding="utf-8")
        assert "# NEXT_PUBLIC_SUPABASE_URL=" in content
        assert "# NEXT_PUBLIC_SUPABASE_ANON_KEY=" in content
        assert "Supabase project URL" in content
        assert "Profile: test-profile" in content

    def test_appends_missing_vars_to_existing_file(self, project_root, profile_dir):
        env_file = project_root / ".env.local"
        env_file.write_text(
            "NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co\n",
            encoding="utf-8",
        )
        result = init_env_file(project_root, "build", profile_dir)
        assert result["action"] == "updated"
        assert result["added"] == ["NEXT_PUBLIC_SUPABASE_ANON_KEY"]

        content = env_file.read_text(encoding="utf-8")
        assert "NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co" in content
        assert "# NEXT_PUBLIC_SUPABASE_ANON_KEY=" in content

    def test_idempotent_when_all_vars_present(self, project_root, profile_dir):
        env_file = project_root / ".env.local"
        env_file.write_text(
            "NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co\n"
            "NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGci...\n",
            encoding="utf-8",
        )
        result = init_env_file(project_root, "build", profile_dir)
        assert result["action"] == "unchanged"

    def test_idempotent_with_commented_vars(self, project_root, profile_dir):
        """Already-commented placeholders count as present."""
        env_file = project_root / ".env.local"
        env_file.write_text(
            "# NEXT_PUBLIC_SUPABASE_URL=        # Supabase project URL\n"
            "# NEXT_PUBLIC_SUPABASE_ANON_KEY=   # Supabase anonymous key\n",
            encoding="utf-8",
        )
        result = init_env_file(project_root, "build", profile_dir)
        assert result["action"] == "unchanged"

    def test_skips_deploy_phase(self, project_root, profile_dir):
        result = init_env_file(project_root, "deploy", profile_dir)
        assert result["action"] == "skipped"
        assert "deploy" in result["reason"]

    def test_skips_without_run_config(self, tmp_path, profile_dir):
        project = tmp_path / "empty"
        project.mkdir()
        result = init_env_file(project, "build", profile_dir)
        assert result["action"] == "skipped"

    def test_skips_without_profile(self, tmp_path, profile_dir):
        project = tmp_path / "no_profile"
        project.mkdir()
        (project / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
        result = init_env_file(project, "build", profile_dir)
        assert result["action"] == "skipped"
