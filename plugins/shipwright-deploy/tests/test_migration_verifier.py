"""Tests for shipwright-deploy migration_verifier.

Replit-pattern adopt (Sub-Iterate B): post-apply verification of
`-- VERIFY:` blocks. Parses, executes, reports. Failure flips the
all_passed flag, which deploy SKILL.md then uses to trigger rollback.

Backwards-compat: migrations without a `-- VERIFY:` block are silently
skipped (skipped=True, all_passed=True) — never break existing
projects that were written before this convention existed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add the deploy plugin's lib dir to path
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import migration_verifier as mv  # type: ignore[import-not-found]  # noqa: E402


@pytest.fixture
def tmp_migration(tmp_path: Path):
    def _make(name: str, body: str) -> Path:
        p = tmp_path / name
        p.write_text(body, encoding="utf-8")
        return p

    return _make


# ---------------------------------------------------------------------------
# 1. Parser — extracts `-- VERIFY: <SQL>` from migration text
# ---------------------------------------------------------------------------


def test_migration_verifier_parses_verify_comment():
    """The parser must find `-- VERIFY:` lines anywhere in the file and
    return their SQL. Tolerates leading whitespace and multiple verify
    blocks per file."""
    sql = """
    -- 20260426_add_user_preferences.sql
    alter table public.profiles add column theme text;

    -- VERIFY: select count(*) from information_schema.columns where table_name = 'profiles' and column_name = 'theme'
    -- VERIFY: select 'true' as verified where exists (select 1 from public.profiles limit 0)

    -- non-verify comment should not be picked up
        -- VERIFY:    select 1
    """
    blocks = mv.parse_verify_blocks(sql)
    assert len(blocks) == 3, f"expected 3 VERIFY blocks, got {len(blocks)}: {blocks!r}"
    assert blocks[0].startswith("select count(*)")
    assert blocks[2] == "select 1"


def test_migration_verifier_parser_returns_empty_when_no_verify_blocks():
    """Backwards-compat anchor for the parser layer."""
    sql = "alter table public.profiles add column theme text;"
    assert mv.parse_verify_blocks(sql) == []


# ---------------------------------------------------------------------------
# 2. Execution — subprocess invocation produces verified=True on real success
# ---------------------------------------------------------------------------


def test_migration_verifier_executes_select(tmp_migration):
    """Happy path: the verifier executes a SELECT, reads non-empty output,
    reports verified=True. Subprocess is mocked so the test does not
    require a live psql."""
    migration = tmp_migration(
        "20260426_test.sql",
        "alter table foo add column bar text;\n-- VERIFY: select 1\n",
    )

    def fake_run(cmd, capture_output, text, timeout):
        class R:
            returncode = 0
            stdout = "1\n"
            stderr = ""

        return R()

    with patch.object(mv.subprocess, "run", side_effect=fake_run):
        report = mv.verify_migration_file(migration, db_url="postgres://stub")

    assert report["skipped"] is False, "VERIFY block was present — must not skip"
    assert report["verify_count"] == 1
    assert report["all_passed"] is True
    assert report["results"][0]["verified"] is True
    assert "select 1" in report["results"][0]["sql"]


# ---------------------------------------------------------------------------
# 3. Failure → all_passed=False (the signal deploy SKILL uses for rollback)
# ---------------------------------------------------------------------------


def test_migration_verifier_triggers_rollback_on_fail(tmp_migration):
    """When the VERIFY SQL returns no rows OR `false`, the report must
    surface all_passed=False so deploy SKILL.md's rollback path fires.

    The verifier does NOT itself perform the rollback (that would couple
    it to jelastic_client) — it provides the failure signal. The deploy
    SKILL is the orchestrator."""
    migration = tmp_migration(
        "20260426_bad.sql",
        "alter table foo add column bar text;\n-- VERIFY: select false\n",
    )

    def fake_run_returns_false(cmd, capture_output, text, timeout):
        class R:
            returncode = 0
            stdout = "f\n"
            stderr = ""

        return R()

    with patch.object(mv.subprocess, "run", side_effect=fake_run_returns_false):
        report = mv.verify_migration_file(migration, db_url="postgres://stub")

    assert report["all_passed"] is False, (
        "verifier must surface failure when VERIFY SQL returns false/empty"
    )
    assert report["skipped"] is False
    assert report["results"][0]["verified"] is False


def test_migration_verifier_triggers_rollback_on_empty_result(tmp_migration):
    """A VERIFY that returns zero rows is also a failure — the contract
    is 'verify produces evidence', and no evidence means no verification."""
    migration = tmp_migration(
        "20260426_empty.sql",
        "alter table foo add column bar text;\n-- VERIFY: select 1 where false\n",
    )

    def fake_run_empty(cmd, capture_output, text, timeout):
        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    with patch.object(mv.subprocess, "run", side_effect=fake_run_empty):
        report = mv.verify_migration_file(migration, db_url="postgres://stub")

    assert report["all_passed"] is False
    assert report["results"][0]["verified"] is False


def test_migration_verifier_triggers_rollback_on_psql_error(tmp_migration):
    """A non-zero psql return code is a failure (CLI error, syntax, etc.)."""
    migration = tmp_migration(
        "20260426_syntax.sql",
        "alter table foo add column bar text;\n-- VERIFY: SLECT 1\n",
    )

    def fake_run_err(cmd, capture_output, text, timeout):
        class R:
            returncode = 1
            stdout = ""
            stderr = 'ERROR: syntax error at or near "SLECT"'

        return R()

    with patch.object(mv.subprocess, "run", side_effect=fake_run_err):
        report = mv.verify_migration_file(migration, db_url="postgres://stub")

    assert report["all_passed"] is False
    assert "syntax error" in report["results"][0]["stderr"]


# ---------------------------------------------------------------------------
# 4. Backwards-compat — no VERIFY block ⇒ skipped=True, all_passed=True
# ---------------------------------------------------------------------------


def test_migration_verifier_skips_when_no_verify_block(tmp_migration):
    """Migrations written before this iterate (or where the author chose
    not to add VERIFY) must NOT cause deploy to fail. The verifier reports
    skipped=True and all_passed=True so the rollback path is not entered."""
    migration = tmp_migration(
        "20260101_legacy.sql",
        "alter table public.legacy add column created_at timestamptz;\n",
    )

    # subprocess.run must NOT be called when there are no VERIFY blocks
    with patch.object(mv.subprocess, "run") as mock_run:
        report = mv.verify_migration_file(migration, db_url="postgres://stub")

    assert report["skipped"] is True
    assert report["all_passed"] is True
    assert report["verify_count"] == 0
    assert report["results"] == []
    mock_run.assert_not_called(), "must not invoke psql when no VERIFY blocks present"


# ---------------------------------------------------------------------------
# 5. CLI entrypoint — JSON output + exit code reflect failure
# ---------------------------------------------------------------------------


def test_migration_verifier_cli_dry_run(tmp_migration, capsys):
    """--dry-run skips actual subprocess but still parses + reports."""
    migration = tmp_migration(
        "20260426_dry.sql",
        "alter table foo add column bar text;\n-- VERIFY: select 1\n",
    )

    with patch.object(sys, "argv", ["mv", "--migration", str(migration), "--dry-run"]):
        rc = mv.main()

    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["all_passed"] is True
    assert parsed["migrations_with_verify"] == 1


def test_migration_verifier_cli_returns_nonzero_on_failure(tmp_migration, capsys):
    """When any verification fails, CLI exit code must be non-zero so
    shell pipelines (and deploy SKILL) can branch on it."""
    migration = tmp_migration(
        "20260426_fail.sql",
        "alter table foo add column bar text;\n-- VERIFY: select 1\n",
    )

    def fake_run_empty(cmd, capture_output, text, timeout):
        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    with (
        patch.object(mv.subprocess, "run", side_effect=fake_run_empty),
        patch.object(sys, "argv", ["mv", "--migration", str(migration)]),
    ):
        rc = mv.main()

    assert rc == 1, "CLI must exit non-zero when verification fails"
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["all_passed"] is False
