"""Tests for hook scripts (shell-based, tested via subprocess)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "hooks"


def run_hook(script_name: str, stdin_data: str = "", env_extra: dict = None) -> subprocess.CompletedProcess:
    """Run a hook script and return the result."""
    script = HOOKS_DIR / script_name
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(script)],
        input=stdin_data,
        capture_output=True,
        text=True,
        env=env,
        encoding="utf-8",
        errors="replace",
    )


class TestCheckDestructiveMigration:
    def test_ignores_non_migration_files(self):
        result = run_hook(
            "check_destructive_migration.sh",
            stdin_data='{"filePath": "src/app/page.tsx"}',
        )
        assert result.returncode == 0

    def test_ignores_safe_migration(self, tmp_path):
        migration = tmp_path / "supabase" / "migrations" / "001_create_users.sql"
        migration.parent.mkdir(parents=True)
        migration.write_text("CREATE TABLE users (id uuid PRIMARY KEY);")

        result = run_hook(
            "check_destructive_migration.sh",
            stdin_data=f'{{"filePath": "{str(migration)}"}}',
        )
        assert result.returncode == 0

    def test_detects_drop_table(self, tmp_path):
        migration = tmp_path / "supabase" / "migrations" / "002_drop_old.sql"
        migration.parent.mkdir(parents=True)
        migration.write_text("DROP TABLE old_users;")

        result = run_hook(
            "check_destructive_migration.sh",
            stdin_data=f'{{"filePath": "{str(migration)}"}}',
        )
        assert result.returncode == 2
        assert "DESTRUCTIVE" in result.stderr

    def test_detects_drop_column(self, tmp_path):
        migration = tmp_path / "supabase" / "migrations" / "003_alter.sql"
        migration.parent.mkdir(parents=True)
        migration.write_text("ALTER TABLE users DROP COLUMN email;")

        result = run_hook(
            "check_destructive_migration.sh",
            stdin_data=f'{{"filePath": "{str(migration)}"}}',
        )
        assert result.returncode == 2
        assert "DESTRUCTIVE" in result.stderr


class TestValidateCommand:
    def test_allows_normal_git_push(self):
        result = run_hook(
            "validate_command.sh",
            stdin_data='{"command": "git push origin main"}',
        )
        assert result.returncode == 0

    def test_blocks_git_push_force(self):
        result = run_hook(
            "validate_command.sh",
            stdin_data='{"command": "git push --force origin main"}',
        )
        assert result.returncode == 2
        assert "BLOCKED" in result.stderr

    def test_blocks_git_push_f(self):
        result = run_hook(
            "validate_command.sh",
            stdin_data='{"command": "git push -f origin main"}',
        )
        assert result.returncode == 2

    def test_blocks_rm_rf(self):
        result = run_hook(
            "validate_command.sh",
            stdin_data='{"command": "rm -rf /some/path"}',
        )
        assert result.returncode == 2
        assert "BLOCKED" in result.stderr

    def test_allows_rm_single_file(self):
        result = run_hook(
            "validate_command.sh",
            stdin_data='{"command": "rm file.txt"}',
        )
        assert result.returncode == 0
