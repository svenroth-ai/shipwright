"""Tests for hook scripts (shell-based, tested via subprocess)."""

import json
import os
import subprocess
import sys
from pathlib import Path


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
        assert "AWS Access Key" in result.stderr

    def test_detects_openai_key(self, tmp_path):
        f = tmp_path / "app.ts"
        f.write_text('const key = "sk-abc123def456ghi789jkl012mno345pqr678stu901"\n')
        result = run_hook("check_secrets.sh", self._make_payload(str(f)))
        assert result.returncode == 2
        assert "API key" in result.stderr

    def test_detects_github_token(self, tmp_path):
        f = tmp_path / "deploy.sh"
        f.write_text('TOKEN=ghp_abcdefghijklmnopqrstuvwxyz1234567890\n')
        result = run_hook("check_secrets.sh", self._make_payload(str(f)))
        assert result.returncode == 2
        assert "GitHub token" in result.stderr

    def test_detects_private_key(self, tmp_path):
        f = tmp_path / "key.pem"
        f.write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----\n")
        result = run_hook("check_secrets.sh", self._make_payload(str(f)))
        assert result.returncode == 2
        assert "Private key" in result.stderr

    def test_detects_hardcoded_password(self, tmp_path):
        f = tmp_path / "db.py"
        f.write_text('password = "SuperSecret123!"\n')
        result = run_hook("check_secrets.sh", self._make_payload(str(f)))
        assert result.returncode == 2
        assert "password" in result.stderr.lower()

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

    # -----------------------------------------------------------------
    # Campaign A.foundation — runtime-prompt classification + marker writer
    # -----------------------------------------------------------------

    def _run_hook_with_session(self, payload: str, cwd: str,
                               session_id: str = "test-sid") -> subprocess.CompletedProcess:
        script = HOOKS_DIR / "check_file_size.py"
        env = os.environ.copy()
        env["SHIPWRIGHT_SESSION_ID"] = session_id
        return subprocess.run(
            [sys.executable, str(script)],
            input=payload, capture_output=True, text=True,
            encoding="utf-8", errors="replace", cwd=cwd, env=env,
        )

    def test_runtime_prompt_skill_md_nudges_at_400(self, tmp_path):
        """SKILL.md at 405 lines crosses the 400 runtime-prompt limit."""
        f = tmp_path / "plugins" / "shipwright-build" / "skills" / "build" / "SKILL.md"
        f.parent.mkdir(parents=True)
        f.write_text(self._lines(405), encoding="utf-8")
        # delta crossing: before = 395 (under 400), after = 405 (over)
        payload = self._edit_payload(str(f), old="x", new="x" + "\n" * 10)
        result = run_python_hook("check_file_size.py", payload, cwd=str(tmp_path))
        assert result.returncode == 0
        assert "405" in result.stdout
        assert "400" in result.stdout

    def test_runtime_prompt_skill_md_silent_at_399(self, tmp_path):
        f = tmp_path / "plugins" / "shipwright-build" / "skills" / "build" / "SKILL.md"
        f.parent.mkdir(parents=True)
        f.write_text(self._lines(399), encoding="utf-8")
        payload = self._edit_payload(str(f))  # delta 0
        result = run_python_hook("check_file_size.py", payload, cwd=str(tmp_path))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_runtime_prompt_claude_md(self, tmp_path):
        f = tmp_path / "CLAUDE.md"
        f.write_text(self._lines(405), encoding="utf-8")
        payload = self._edit_payload(str(f), old="x", new="x" + "\n" * 10)
        result = run_python_hook("check_file_size.py", payload, cwd=str(tmp_path))
        assert result.returncode == 0
        assert "405" in result.stdout

    def test_plain_markdown_still_skipped(self, tmp_path):
        f = tmp_path / "docs" / "guide.md"
        f.parent.mkdir(parents=True)
        f.write_text(self._lines(5000), encoding="utf-8")
        payload = self._edit_payload(str(f), old="x", new="x" + "\n" * 4000)
        result = run_python_hook("check_file_size.py", payload, cwd=str(tmp_path))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_marker_written_for_crossing(self, tmp_path):
        """PostToolUse nudge also writes a per-session marker JSON."""
        f = tmp_path / "grew.py"
        f.write_text(self._lines(310), encoding="utf-8")
        payload = self._edit_payload(str(f), old="x", new="x" + "\n" * 12)
        result = self._run_hook_with_session(payload, str(tmp_path), "sid-1")
        assert result.returncode == 0
        marker = tmp_path / ".shipwright" / "locks" / "bloat_pending.sid-1.json"
        assert marker.is_file(), f"missing marker: {marker}"
        data = json.loads(marker.read_text(encoding="utf-8"))
        assert isinstance(data.get("entries"), list)
        entries = data["entries"]
        assert len(entries) == 1
        e = entries[0]
        assert e["path"].endswith("grew.py")
        assert e["now"] == 310
        assert e["limit"] == 300
        assert e["classification"] == "source"
        assert e["was_in_allowlist"] is False
        assert e["delta"] == "crossing"
        assert e["ts"].endswith("Z") or "+00:00" in e["ts"]

    def test_marker_anti_ratchet_when_path_in_baseline(self, tmp_path):
        """Path already in baseline → delta=anti-ratchet, even if same value."""
        # Seed baseline.
        baseline = {
            "version": 1,
            "entries": [
                {"path": "legacy.py", "limit": 300, "current": 410,
                 "state": "grandfathered", "adr": None},
            ],
        }
        (tmp_path / "shipwright_bloat_baseline.json").write_text(
            json.dumps(baseline), encoding="utf-8",
        )
        f = tmp_path / "legacy.py"
        f.write_text(self._lines(420), encoding="utf-8")  # grew further
        payload = self._edit_payload(str(f), old="x", new="x" + "\n" * 10)
        result = self._run_hook_with_session(payload, str(tmp_path), "sid-2")
        assert result.returncode == 0
        marker = tmp_path / ".shipwright" / "locks" / "bloat_pending.sid-2.json"
        data = json.loads(marker.read_text(encoding="utf-8"))
        e = data["entries"][0]
        assert e["was_in_allowlist"] is True
        assert e["delta"] == "anti-ratchet"

    def test_marker_read_modify_write_preserves_other_paths(self, tmp_path):
        """A second hook fire upserts by path; prior entries survive."""
        # First fire: file_a
        f_a = tmp_path / "a.py"
        f_a.write_text(self._lines(312), encoding="utf-8")
        self._run_hook_with_session(
            self._edit_payload(str(f_a), old="x", new="x" + "\n" * 14),
            str(tmp_path), "sid-3",
        )
        # Second fire: file_b
        f_b = tmp_path / "b.py"
        f_b.write_text(self._lines(315), encoding="utf-8")
        self._run_hook_with_session(
            self._edit_payload(str(f_b), old="x", new="x" + "\n" * 17),
            str(tmp_path), "sid-3",
        )
        marker = tmp_path / ".shipwright" / "locks" / "bloat_pending.sid-3.json"
        data = json.loads(marker.read_text(encoding="utf-8"))
        paths = {e["path"] for e in data["entries"]}
        assert any(p.endswith("a.py") for p in paths)
        assert any(p.endswith("b.py") for p in paths)

    def test_marker_unknown_session_when_env_absent(self, tmp_path):
        """Missing SHIPWRIGHT_SESSION_ID → writes to bloat_pending.unknown.json."""
        f = tmp_path / "fresh.py"
        f.write_text(self._lines(360), encoding="utf-8")
        env = {k: v for k, v in os.environ.items()
               if k != "SHIPWRIGHT_SESSION_ID"}
        script = HOOKS_DIR / "check_file_size.py"
        result = subprocess.run(
            [sys.executable, str(script)],
            input=self._write_payload(str(f)),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(tmp_path), env=env,
        )
        assert result.returncode == 0
        marker = tmp_path / ".shipwright" / "locks" / "bloat_pending.unknown.json"
        assert marker.is_file()

    def test_test_files_count_at_300(self, tmp_path):
        """Test-files participate in crossing/anti-ratchet (campaign §4.1)."""
        f = tmp_path / "tests" / "test_big.py"
        f.parent.mkdir(parents=True)
        f.write_text(self._lines(310), encoding="utf-8")
        payload = self._edit_payload(str(f), old="x", new="x" + "\n" * 12)
        result = run_python_hook("check_file_size.py", payload, cwd=str(tmp_path))
        assert result.returncode == 0
        assert "310" in result.stdout
