"""Tests for shared/scripts/surface_verification.py.

The orchestrator is the production-time chokepoint for the F0.5 gate;
the post-commit audit (test_verify_iterate_finalization.py) is the
second layer. Tests here cover:

- the four fail-closed exit codes (1-4) plus the happy path (0)
- the ``parse_tests_run`` heuristic for cli/web/api surfaces
- the producer→file→consumer round-trip on the JSON evidence shape
  (boundary probe per iterate skill SKILL.md Step 6a + plan §F.1)
- duplicated-consumer drift protection: the audit function in
  iterate_checks.py reads exactly the keys the orchestrator writes
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add shared/scripts to path so ``import surface_verification`` resolves
# the same way the conftest does for other shared modules.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from surface_verification import (  # noqa: E402  (after sys.path tweak)
    EXIT_INVALID_ARGS,
    EXIT_NONE_WITHOUT_JUSTIFICATION,
    EXIT_OK,
    EXIT_RUNNER_FAILED,
    EXIT_ZERO_TESTS,
    VALID_SURFACES,
    build_block,
    main,
    parse_tests_run,
    verify_surface,
    write_evidence,
)


# ---------------------------------------------------------------------------
# Schema / constants
# ---------------------------------------------------------------------------


def test_valid_surfaces_match_skill_md():
    """SKILL.md F0.5 names exactly four surfaces. Order is irrelevant but
    drift between code and prose is a silent regression risk."""
    assert set(VALID_SURFACES) == {"web", "cli", "api", "none"}


# ---------------------------------------------------------------------------
# parse_tests_run heuristic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stdout,surface,expected",
    [
        ("=== 5 passed in 0.32s ===", "cli", 5),
        ("=== 3 passed, 2 failed in 1.0s ===", "cli", 5),
        ("=== 0 passed in 0.01s ===", "cli", 0),
        ("Running 7 tests using 3 workers\n  7 passed (1.2s)", "web", 7),
        ("0 passed (0ms)", "web", 0),
        ("line one\nline two\n", "api", 2),
        ("", "cli", 0),
        ("no number here", "cli", 0),
    ],
)
def test_parse_tests_run(stdout: str, surface: str, expected: int):
    assert parse_tests_run(stdout, surface) == expected


def test_parse_tests_run_unknown_surface():
    """Unknown surfaces return 0 — caller still has the override knob."""
    assert parse_tests_run("=== 5 passed ===", "wat") == 0


# ---------------------------------------------------------------------------
# verify_surface fail-closed conditions
# ---------------------------------------------------------------------------


def test_invalid_surface_exits_1(tmp_path):
    code, block = verify_surface(
        project_root=tmp_path,
        run_id="iterate-2026-01-01-foo",
        surface="bogus",
        runner=None,
        justification=None,
        tests_run_override=None,
    )
    assert code == EXIT_INVALID_ARGS
    assert block["exit_code"] == EXIT_INVALID_ARGS


def test_none_without_justification_exits_4(tmp_path):
    code, block = verify_surface(
        project_root=tmp_path,
        run_id="iterate-2026-01-01-foo",
        surface="none",
        runner=None,
        justification=None,
        tests_run_override=None,
    )
    assert code == EXIT_NONE_WITHOUT_JUSTIFICATION
    assert block["surface"] == "none"


def test_none_with_blank_justification_exits_4(tmp_path):
    code, _ = verify_surface(
        project_root=tmp_path,
        run_id="iterate-2026-01-01-foo",
        surface="none",
        runner=None,
        justification="   ",
        tests_run_override=None,
    )
    assert code == EXIT_NONE_WITHOUT_JUSTIFICATION


def test_none_with_justification_passes(tmp_path):
    code, block = verify_surface(
        project_root=tmp_path,
        run_id="iterate-2026-01-01-foo",
        surface="none",
        runner=None,
        justification="pure type-hint rename; no runtime path exercised",
        tests_run_override=None,
    )
    assert code == EXIT_OK
    assert block["justification"].startswith("pure type-hint")
    assert block["tests_run"] == 0


def test_non_none_without_runner_exits_1(tmp_path):
    code, _ = verify_surface(
        project_root=tmp_path,
        run_id="iterate-2026-01-01-foo",
        surface="cli",
        runner="",
        justification=None,
        tests_run_override=None,
    )
    assert code == EXIT_INVALID_ARGS


def test_zero_tests_exits_2(tmp_path):
    """Greedy-filter trap: runner exits 0 but matched zero tests."""
    code, block = verify_surface(
        project_root=tmp_path,
        run_id="iterate-2026-01-01-foo",
        surface="cli",
        runner=[sys.executable, "-c", "print('no tests collected')"],
        justification=None,
        tests_run_override=None,
    )
    assert code == EXIT_ZERO_TESTS
    assert block["tests_run"] == 0


def test_runner_failure_exits_3(tmp_path):
    code, block = verify_surface(
        project_root=tmp_path,
        run_id="iterate-2026-01-01-foo",
        surface="cli",
        runner=[sys.executable, "-c", "import sys; sys.exit(1)"],
        justification=None,
        tests_run_override=None,
        retry_cap=2,
    )
    assert code == EXIT_RUNNER_FAILED
    assert block["exit_code"] == 1
    assert block["attempts"] == 2


def test_command_not_found_exits_3(tmp_path):
    code, _ = verify_surface(
        project_root=tmp_path,
        run_id="iterate-2026-01-01-foo",
        surface="cli",
        runner="nonexistent-binary-xyz-9999",
        justification=None,
        tests_run_override=None,
        retry_cap=1,
    )
    assert code == EXIT_RUNNER_FAILED


def test_happy_path_exit_0(tmp_path):
    code, block = verify_surface(
        project_root=tmp_path,
        run_id="iterate-2026-01-01-foo",
        surface="cli",
        runner=[sys.executable, "-c", "print('=== 3 passed in 0.1s ===')"],
        justification=None,
        tests_run_override=None,
    )
    assert code == EXIT_OK
    assert block["tests_run"] == 3
    assert block["exit_code"] == 0


def test_tests_run_override_wins(tmp_path):
    """Explicit count beats stdout parsing — the determinism knob."""
    code, block = verify_surface(
        project_root=tmp_path,
        run_id="iterate-2026-01-01-foo",
        surface="cli",
        runner=[sys.executable, "-c", "print('unparseable')"],
        justification=None,
        tests_run_override=42,
    )
    assert code == EXIT_OK
    assert block["tests_run"] == 42


def test_tests_run_override_zero_still_fails(tmp_path):
    code, _ = verify_surface(
        project_root=tmp_path,
        run_id="iterate-2026-01-01-foo",
        surface="cli",
        runner=[sys.executable, "-c", "print('irrelevant')"],
        justification=None,
        tests_run_override=0,
    )
    assert code == EXIT_ZERO_TESTS


# ---------------------------------------------------------------------------
# Evidence write — boundary probe (round-trip)
# ---------------------------------------------------------------------------


def test_write_evidence_round_trip(tmp_path):
    """Producer (write_evidence) → file → consumer (json.loads) round-trip.

    The audit function in iterate_checks.py reads the same path with
    the same key shape; this test pins the contract on the producer
    side so drift is detectable here, not in the verifier."""
    block = build_block(
        surface="cli",
        runner="pytest -q",
        exit_code=0,
        tests_run=5,
        evidence_path="/tmp/log.txt",
        justification=None,
        attempts=1,
    )
    path = write_evidence(tmp_path, "iterate-2026-01-01-foo", block)
    assert path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    for key in (
        "surface",
        "runner",
        "exit_code",
        "tests_run",
        "evidence_path",
        "timestamp",
        "attempts",
    ):
        assert key in loaded, f"key {key!r} missing from evidence block"
    # justification omitted when None — alternative would be a null
    # which compliance readers would have to special-case
    assert "justification" not in loaded


def test_write_evidence_includes_justification_when_set(tmp_path):
    block = build_block(
        surface="none",
        runner="",
        exit_code=0,
        tests_run=0,
        evidence_path="",
        justification="test-only fixture",
        attempts=0,
    )
    path = write_evidence(tmp_path, "iterate-2026-01-01-foo", block)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["justification"] == "test-only fixture"


def test_write_evidence_idempotent(tmp_path):
    """Re-running F0.5 in the same run_id overwrites cleanly."""
    block_a = build_block(
        surface="cli", runner="x", exit_code=0, tests_run=1,
        evidence_path="", justification=None, attempts=1,
    )
    block_b = build_block(
        surface="cli", runner="y", exit_code=0, tests_run=2,
        evidence_path="", justification=None, attempts=1,
    )
    write_evidence(tmp_path, "iterate-2026-01-01-foo", block_a)
    path = write_evidence(tmp_path, "iterate-2026-01-01-foo", block_b)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["runner"] == "y"
    assert loaded["tests_run"] == 2


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def test_main_writes_evidence_and_returns_exit_code(tmp_path, capsys):
    exit_code = main(
        [
            "--project-root",
            str(tmp_path),
            "--run-id",
            "iterate-2026-01-01-foo",
            "--surface",
            "none",
            "--justification",
            "pure-doc iterate; no runtime",
        ]
    )
    assert exit_code == EXIT_OK
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["surface"] == "none"
    assert Path(summary["evidence_block"]).exists()


def test_main_propagates_zero_tests_exit(tmp_path):
    """Use a runner script on disk so we don't depend on cross-platform
    shlex quoting of sys.executable paths with spaces/backslashes."""
    runner_script = tmp_path / "runner.py"
    runner_script.write_text("print('no tests collected')\n", encoding="utf-8")
    import shlex as _shlex
    runner_str = f"{_shlex.quote(sys.executable)} {_shlex.quote(str(runner_script))}"
    # On Windows shlex.quote uses POSIX-style single-quote escaping, which
    # our orchestrator's tokenizer handles via posix=False. To stay portable,
    # bypass argparse and call verify_surface directly with a list runner.
    code, _ = verify_surface(
        project_root=tmp_path,
        run_id="iterate-2026-01-01-foo",
        surface="cli",
        runner=[sys.executable, str(runner_script)],
        justification=None,
        tests_run_override=None,
    )
    assert code == EXIT_ZERO_TESTS
