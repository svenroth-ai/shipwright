"""Tests for hook scripts (shell-based, tested via subprocess)."""

import json
import os
import subprocess
import sys
import time
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


def run_python_hook(script_name: str, stdin_data: str = "", cwd: str = None) -> subprocess.CompletedProcess:
    """Run a Python hook script and return the result."""
    script = HOOKS_DIR / script_name
    return subprocess.run(
        [sys.executable, str(script)],
        input=stdin_data,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
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


class TestCheckSecrets:
    """Tests for secret scanning hook."""

    def _make_payload(self, file_path: str) -> str:
        return json.dumps({"tool_input": {"file_path": file_path}})

    def test_detects_aws_key(self, tmp_path):
        f = tmp_path / "config.py"
        f.write_text('AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n')
        result = run_hook("check_secrets.sh", self._make_payload(str(f)))
        assert result.returncode == 2
        assert "AWS Access Key" in result.stdout

    def test_detects_openai_key(self, tmp_path):
        f = tmp_path / "app.ts"
        f.write_text('const key = "sk-abc123def456ghi789jkl012mno345pqr678stu901"\n')
        result = run_hook("check_secrets.sh", self._make_payload(str(f)))
        assert result.returncode == 2
        assert "API key" in result.stdout

    def test_detects_github_token(self, tmp_path):
        f = tmp_path / "deploy.sh"
        f.write_text('TOKEN=ghp_abcdefghijklmnopqrstuvwxyz1234567890\n')
        result = run_hook("check_secrets.sh", self._make_payload(str(f)))
        assert result.returncode == 2
        assert "GitHub token" in result.stdout

    def test_detects_private_key(self, tmp_path):
        f = tmp_path / "key.pem"
        f.write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----\n")
        result = run_hook("check_secrets.sh", self._make_payload(str(f)))
        assert result.returncode == 2
        assert "Private key" in result.stdout

    def test_detects_hardcoded_password(self, tmp_path):
        f = tmp_path / "db.py"
        f.write_text('password = "SuperSecret123!"\n')
        result = run_hook("check_secrets.sh", self._make_payload(str(f)))
        assert result.returncode == 2
        assert "password" in result.stdout.lower()

    def test_allows_clean_file(self, tmp_path):
        f = tmp_path / "app.py"
        f.write_text('import os\ndb_url = os.environ["DATABASE_URL"]\n')
        result = run_hook("check_secrets.sh", self._make_payload(str(f)))
        assert result.returncode == 0

    def test_allows_env_example(self, tmp_path):
        f = tmp_path / ".env.example"
        f.write_text('API_KEY=your-api-key-here\npassword = "CHANGE_ME"\n')
        result = run_hook("check_secrets.sh", self._make_payload(str(f)))
        assert result.returncode == 0

    def test_allows_test_fixture(self, tmp_path):
        fixture_dir = tmp_path / "fixtures"
        fixture_dir.mkdir()
        f = fixture_dir / "test_data.py"
        f.write_text('FAKE_KEY = "AKIAIOSFODNN7EXAMPLE"\n')
        result = run_hook("check_secrets.sh", self._make_payload(str(f)))
        assert result.returncode == 0

    def test_ignores_env_references(self, tmp_path):
        f = tmp_path / "config.ts"
        f.write_text('const password = process.env.DB_PASSWORD\n')
        result = run_hook("check_secrets.sh", self._make_payload(str(f)))
        assert result.returncode == 0

    def test_empty_payload(self):
        result = run_hook("check_secrets.sh", "{}")
        assert result.returncode == 0


class TestCheckFileSize:
    """Tests for file size guard hook."""

    def _make_payload(self, file_path: str) -> str:
        return json.dumps({"tool_input": {"file_path": file_path}})

    def test_allows_small_file(self, tmp_path):
        f = tmp_path / "small.py"
        f.write_text("\n".join(f"line {i}" for i in range(50)))
        result = run_hook("check_file_size.sh", self._make_payload(str(f)))
        assert result.returncode == 0

    def test_blocks_large_file(self, tmp_path):
        f = tmp_path / "large.py"
        # 401 items joined by \n = 400 lines (wc -l counts newlines)
        f.write_text("\n".join(f"line {i}" for i in range(401)))
        result = run_hook("check_file_size.sh", self._make_payload(str(f)))
        assert result.returncode == 2
        assert "400" in result.stdout
        assert "300" in result.stdout

    def test_allows_exact_threshold(self, tmp_path):
        f = tmp_path / "exact.py"
        f.write_text("\n".join(f"line {i}" for i in range(300)))
        result = run_hook("check_file_size.sh", self._make_payload(str(f)))
        assert result.returncode == 0

    def test_skips_markdown(self, tmp_path):
        f = tmp_path / "docs.md"
        f.write_text("\n".join(f"line {i}" for i in range(500)))
        result = run_hook("check_file_size.sh", self._make_payload(str(f)))
        assert result.returncode == 0

    def test_skips_json(self, tmp_path):
        f = tmp_path / "package.json"
        f.write_text("\n".join(f'"line_{i}": {i}' for i in range(500)))
        result = run_hook("check_file_size.sh", self._make_payload(str(f)))
        assert result.returncode == 0

    def test_skips_lock_file(self, tmp_path):
        f = tmp_path / "package-lock.json"
        f.write_text("\n".join(f"line {i}" for i in range(5000)))
        result = run_hook("check_file_size.sh", self._make_payload(str(f)))
        assert result.returncode == 0

    def test_skips_migration_sql(self, tmp_path):
        migration_dir = tmp_path / "migrations"
        migration_dir.mkdir()
        f = migration_dir / "001_big.sql"
        f.write_text("\n".join(f"INSERT INTO t VALUES ({i});" for i in range(500)))
        result = run_hook("check_file_size.sh", self._make_payload(str(f)))
        assert result.returncode == 0

    def test_empty_payload(self):
        result = run_hook("check_file_size.sh", "{}")
        assert result.returncode == 0


class TestCheckDrift:
    """Tests for CLAUDE.md drift detection hook."""

    def test_warns_when_source_newer(self, tmp_path):
        # Create CLAUDE.md first (older)
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Project\n")

        # Ensure timestamp difference
        time.sleep(0.1)

        # Create source file (newer)
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("print('hello')\n")

        result = run_python_hook("check_drift.py", cwd=str(tmp_path))
        assert result.returncode == 0
        assert "DRIFT WARNING" in result.stdout

    def test_no_warning_when_claude_md_newer(self, tmp_path):
        # Create source first (older)
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("print('hello')\n")

        # Ensure timestamp difference
        time.sleep(0.1)

        # Create CLAUDE.md (newer)
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Project\n")

        result = run_python_hook("check_drift.py", cwd=str(tmp_path))
        assert result.returncode == 0
        assert "DRIFT" not in result.stdout

    def test_no_warning_without_claude_md(self, tmp_path):
        result = run_python_hook("check_drift.py", cwd=str(tmp_path))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_detects_package_json_drift(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Project\n")
        time.sleep(0.1)
        pkg = tmp_path / "package.json"
        pkg.write_text('{"name": "test"}')

        result = run_python_hook("check_drift.py", cwd=str(tmp_path))
        assert result.returncode == 0
        assert "package.json" in result.stdout

    def test_never_blocks(self, tmp_path):
        """Drift detection should never return non-zero exit code."""
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Project\n")
        time.sleep(0.1)
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("print('hello')\n")
        pkg = tmp_path / "package.json"
        pkg.write_text('{"name": "test"}')

        result = run_python_hook("check_drift.py", cwd=str(tmp_path))
        assert result.returncode == 0  # Always 0, never blocks
