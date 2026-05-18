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
    """Tests for the file-size nudge hook (non-blocking, crossing-only)."""

    @staticmethod
    def _lines(n: int) -> str:
        """File content with exactly ``n`` newline bytes."""
        return "x\n" * n

    def _edit_payload(
        self, file_path: str, old: str = "x", new: str = "x",
        replace_all: bool = False,
    ) -> str:
        return json.dumps({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": file_path,
                "old_string": old,
                "new_string": new,
                "replace_all": replace_all,
            },
        })

    def _write_payload(self, file_path: str, content: str = "") -> str:
        return json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": file_path, "content": content},
        })

    def test_never_blocks_even_when_over_limit(self, tmp_path):
        """Crossing the limit emits a nudge but must never exit 2 / block."""
        f = tmp_path / "big.py"
        f.write_text(self._lines(900))
        # before = 900 - 700 = 200 -> this edit crossed the threshold.
        payload = self._edit_payload(str(f), old="x", new="x" + "\n" * 700)
        result = run_python_hook("check_file_size.py", payload, cwd=str(tmp_path))
        assert result.returncode == 0
        assert "blocked" not in result.stdout

    def test_small_file_no_nudge(self, tmp_path):
        f = tmp_path / "small.py"
        f.write_text(self._lines(50))
        result = run_python_hook(
            "check_file_size.py", self._edit_payload(str(f)), cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_exact_threshold_no_nudge(self, tmp_path):
        f = tmp_path / "exact.py"
        f.write_text(self._lines(300))
        result = run_python_hook(
            "check_file_size.py", self._edit_payload(str(f)), cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_edit_crossing_threshold_nudges(self, tmp_path):
        """Edit that grows a file from <=300 to >300 fires the nudge."""
        f = tmp_path / "grown.py"
        f.write_text(self._lines(305))
        # old has 0 newlines, new has 10 -> delta +10 -> before = 295.
        payload = self._edit_payload(str(f), old="x", new="x" + "\n" * 10)
        result = run_python_hook("check_file_size.py", payload, cwd=str(tmp_path))
        assert result.returncode == 0
        assert "305" in result.stdout
        assert "300" in result.stdout

    def test_edit_on_already_large_file_silent(self, tmp_path):
        """The key de-noising case: a net-zero edit to an already-oversized file."""
        f = tmp_path / "legacy.py"
        f.write_text(self._lines(420))
        payload = self._edit_payload(str(f), old="a", new="b")  # delta 0
        result = run_python_hook("check_file_size.py", payload, cwd=str(tmp_path))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_edit_growing_already_large_file_silent(self, tmp_path):
        """Growing an already-oversized file further still doesn't re-fire."""
        f = tmp_path / "legacy.py"
        f.write_text(self._lines(420))
        # before = 420 - 5 = 415, already over the limit.
        payload = self._edit_payload(str(f), old="x", new="x" + "\n" * 5)
        result = run_python_hook("check_file_size.py", payload, cwd=str(tmp_path))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_write_oversized_file_nudges(self, tmp_path):
        """A Write producing an oversized file nudges when git can't prove
        it was already large (tmp_path is not a git repo)."""
        f = tmp_path / "fresh.py"
        f.write_text(self._lines(360))
        result = run_python_hook(
            "check_file_size.py", self._write_payload(str(f)), cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert "360" in result.stdout

    def test_skips_markdown(self, tmp_path):
        f = tmp_path / "docs.md"
        f.write_text(self._lines(500))
        payload = self._edit_payload(str(f), old="x", new="x" + "\n" * 400)
        result = run_python_hook("check_file_size.py", payload, cwd=str(tmp_path))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_skips_lock_file(self, tmp_path):
        f = tmp_path / "package-lock.json"
        f.write_text(self._lines(5000))
        payload = self._edit_payload(str(f), old="x", new="x" + "\n" * 4000)
        result = run_python_hook("check_file_size.py", payload, cwd=str(tmp_path))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_skips_migration_sql(self, tmp_path):
        migration_dir = tmp_path / "migrations"
        migration_dir.mkdir()
        f = migration_dir / "001_big.sql"
        f.write_text(self._lines(500))
        payload = self._edit_payload(str(f), old="x", new="x" + "\n" * 400)
        result = run_python_hook("check_file_size.py", payload, cwd=str(tmp_path))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_missing_file_no_nudge(self, tmp_path):
        result = run_python_hook(
            "check_file_size.py",
            self._edit_payload(str(tmp_path / "nope.py")),
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_empty_payload(self):
        result = run_python_hook("check_file_size.py", "{}")
        assert result.returncode == 0
        assert result.stdout.strip() == ""


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
