"""Tests for shipwright-build hooks (plugin-specific only).

The SessionStart capture_session_id.py hook is shared across all
plugins and tested in shared/tests/test_capture_session_id.py.
"""

import json
import subprocess
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "hooks"


def test_validate_command_allows_normal():
    """Normal commands should pass."""
    result = subprocess.run(
        ["bash", str(HOOKS_DIR / "validate_command.sh")],
        input=json.dumps({"tool_input": {"command": "npm test"}}),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0


def test_validate_command_blocks_force_push():
    """git push --force should be blocked."""
    result = subprocess.run(
        ["bash", str(HOOKS_DIR / "validate_command.sh")],
        input=json.dumps({"tool_input": {"command": "git push --force origin main"}}),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 2
    assert "BLOCKED" in result.stdout


def test_validate_command_allows_force_push_to_feature():
    """git push --force to feature branch should be allowed."""
    result = subprocess.run(
        ["bash", str(HOOKS_DIR / "validate_command.sh")],
        input=json.dumps({"tool_input": {"command": "git push --force origin my-app/01-auth"}}),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0


def test_validate_command_blocks_rm_rf_root():
    result = subprocess.run(
        ["bash", str(HOOKS_DIR / "validate_command.sh")],
        input=json.dumps({"tool_input": {"command": "rm -rf /"}}),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 2


def test_check_destructive_migration_clean(tmp_path):
    """Non-destructive SQL should pass."""
    sql = tmp_path / "supabase" / "migrations" / "001_create.sql"
    sql.parent.mkdir(parents=True)
    sql.write_text("CREATE TABLE users (id UUID PRIMARY KEY);\n")

    result = subprocess.run(
        ["bash", str(HOOKS_DIR / "check_destructive_migration.sh")],
        input=json.dumps({"tool_input": {"file_path": str(sql)}}),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0


def test_check_destructive_migration_drop_table(tmp_path):
    """DROP TABLE should trigger warning."""
    sql = tmp_path / "supabase" / "migrations" / "002_drop.sql"
    sql.parent.mkdir(parents=True)
    sql.write_text("DROP TABLE users;\n")

    result = subprocess.run(
        ["bash", str(HOOKS_DIR / "check_destructive_migration.sh")],
        input=json.dumps({"tool_input": {"file_path": str(sql)}}),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 2
    # WP4: the block reason is delivered on STDERR (the channel Claude reads on
    # a PostToolUse exit-2 soft block), not the stdout that exit-2 discards.
    assert "DROP TABLE" in result.stderr


def test_check_destructive_non_sql(tmp_path):
    """Non-SQL files should pass without checking."""
    ts = tmp_path / "src" / "app.ts"
    ts.parent.mkdir(parents=True)
    ts.write_text("console.log('hello');\n")

    result = subprocess.run(
        ["bash", str(HOOKS_DIR / "check_destructive_migration.sh")],
        input=json.dumps({"tool_input": {"file_path": str(ts)}}),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0
