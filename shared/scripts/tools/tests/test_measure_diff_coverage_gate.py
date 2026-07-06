"""Tests for the diff-coverage GATE (``measure_diff_coverage.py --fail-under``).

Phase-4 hardening (``iterate-2026-07-06-diff-coverage-gate-hardening``): before
the warn-only CI gate can be flipped to hard-block, its FAIL-path must be proven
to bite. #324's own CI only ever hit the empty/happy path ("No lines with
coverage information in this diff."), so the fail-path was completely unexercised.
Three layers pin it:

  1. Pure ``decide_gate`` unit tests (``lib.diff_coverage_gate``) — always run.
  2. Full-entrypoint tests via a pre-computed ``--diff-cover-json`` report (no
     diff-cover subprocess) — deterministic, always run in CI.
  3. A REAL end-to-end fail-path: a synthetic git repo with an undercovered
     changed line, driven through ``main --fail-under`` against the real
     diff-cover. Skipped locally when git/diff-cover are absent; HARD-FAILS in
     CI (silent-skip CI-discipline rule) so the empirical proof cannot rot. The
     shared-tests CI step provisions diff-cover (`uv run --with diff-cover`).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# shared/ (for scripts.tools.*) and shared/scripts (for lib.*) on the path.
_SHARED = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_SHARED))
sys.path.insert(0, str(_SHARED / "scripts"))

from lib.diff_coverage_gate import (
    GATE_EXIT_ERROR,
    GATE_EXIT_FAIL,
    GATE_EXIT_PASS,
    decide_gate,
)
import scripts.tools.measure_diff_coverage as measure_mod
from scripts.tools.measure_diff_coverage import main as measure_main

_HAS_GIT = shutil.which("git") is not None
_HAS_DIFF_COVER = (
    shutil.which("diff-cover") is not None
    or importlib.util.find_spec("diff_cover") is not None
)
_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

# coverage.xml over mod.py: lines 1-2 (base) hit, changed line 4 hit; line 5's
# hits are parametrised so the two changed measured lines {4,5} give 100%
# (covered) or 50% (undercovered).
_COVERAGE_XML = (
    '<?xml version="1.0" ?>\n'
    '<coverage line-rate="0.8" version="7.0" timestamp="0"><packages>\n'
    '<package name="." line-rate="0.8"><classes>\n'
    '<class name="mod.py" filename="mod.py" line-rate="0.8"><lines>\n'
    '<line number="1" hits="1"/><line number="2" hits="1"/>\n'
    '<line number="4" hits="1"/><line number="5" hits="{hit5}"/>\n'
    "</lines></class></classes></package></packages></coverage>\n"
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), env=_GIT_ENV,
                   capture_output=True, text=True, check=True)


def _synth_repo(root: Path, *, covered: bool) -> None:
    """A git repo whose working tree changes ``mod.py`` (vs the ``main`` base)
    by adding ``def b()`` — a covered or undercovered change per ``covered``."""
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "core.autocrlf", "false")
    (root / "mod.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    (root / "mod.py").write_text(
        "def a():\n    return 1\n\ndef b():\n    return 2\n", encoding="utf-8")
    (root / "coverage.xml").write_text(
        _COVERAGE_XML.format(hit5="1" if covered else "0"), encoding="utf-8")


def _require_real_tools() -> None:
    if _HAS_GIT and _HAS_DIFF_COVER:
        return
    if os.environ.get("CI", "").lower() in ("true", "1"):
        pytest.fail(
            "git/diff-cover unavailable in CI — the shared-tests step must "
            "provision diff-cover (`uv run --with diff-cover`); see ci.yml "
            "'Run shared tests'."
        )
    pytest.skip("git or diff-cover unavailable; run via "
                "`uv run --with diff-cover pytest`.")


# --------------------------------------------------------------------------- #
# Layer 1 — pure decision (always runs)
# --------------------------------------------------------------------------- #
class TestDecideGate:
    def test_below_threshold_fails(self):
        assert decide_gate(50.0, 80) == GATE_EXIT_FAIL
        assert GATE_EXIT_FAIL != 0

    def test_at_threshold_passes(self):
        assert decide_gate(80.0, 80) == GATE_EXIT_PASS == 0

    def test_above_threshold_passes(self):
        assert decide_gate(95.0, 80) == 0

    def test_empty_diff_passes(self):
        # No changed lines under coverage -> pass, matching diff-cover itself.
        assert decide_gate(None, 80) == 0


# --------------------------------------------------------------------------- #
# Layer 2 — full entrypoint via a pre-computed report (no subprocess)
# --------------------------------------------------------------------------- #
class TestGatePrecomputed:
    def _run(self, tmp_path: Path, pct, *, num_lines=40) -> tuple[int, str]:
        (tmp_path / "coverage.xml").write_text(
            '<coverage line-rate="0.8"/>\n', encoding="utf-8")
        rep = tmp_path / "rep.json"
        rep.write_text(json.dumps(
            {"total_num_lines": num_lines, "total_percent_covered": pct}),
            encoding="utf-8")
        rc = measure_main([
            "--project-root", str(tmp_path),
            "--coverage-xml", str(tmp_path / "coverage.xml"),
            "--diff-cover-json", str(rep),
            "--fail-under", "80",
        ])
        return rc

    def test_undercovered_exits_nonzero_and_prints_report(self, tmp_path, capsys):
        rc = self._run(tmp_path, 50)
        out = capsys.readouterr().out
        assert rc == GATE_EXIT_FAIL
        assert rc != 0
        assert "50" in out  # the report always prints, on fail

    def test_covered_exits_zero_and_prints_report(self, tmp_path, capsys):
        rc = self._run(tmp_path, 90)
        out = capsys.readouterr().out
        assert rc == GATE_EXIT_PASS
        assert "90" in out  # the report always prints, on pass too

    def test_empty_diff_exits_zero(self, tmp_path):
        # A PRODUCED report that legitimately shows no changed lines under
        # coverage -> PASS (parity with raw diff-cover). This is DISTINCT from a
        # measurement failure (no report) — see TestGateMeasurementFailure.
        assert self._run(tmp_path, 100, num_lines=0) == 0


# --------------------------------------------------------------------------- #
# Layer 2b — measurement FAILURE must fail closed (not silently pass).
# Regression: run_diff_cover returns None on BOTH "empty diff" and "diff-cover
# crashed/unavailable"; the gate must not collapse the latter into a green.
# --------------------------------------------------------------------------- #
class TestGateMeasurementFailure:
    def test_no_report_produced_fails_closed(self, tmp_path, monkeypatch, capsys):
        (tmp_path / "coverage.xml").write_text(
            '<coverage line-rate="0.8"/>\n', encoding="utf-8")
        # Simulate a diff-cover crash / unavailable binary: no report produced.
        monkeypatch.setattr(measure_mod, "run_diff_cover", lambda *a, **k: None)
        rc = measure_main([
            "--project-root", str(tmp_path),
            "--coverage-xml", str(tmp_path / "coverage.xml"),
            "--fail-under", "80",
        ])
        out = capsys.readouterr().out
        assert rc == GATE_EXIT_ERROR
        assert rc not in (GATE_EXIT_PASS, GATE_EXIT_FAIL)  # distinct from both
        assert "ERROR" in out  # visibly not a clean pass

    def test_unreadable_precomputed_report_fails_closed(self, tmp_path):
        (tmp_path / "coverage.xml").write_text(
            '<coverage line-rate="0.8"/>\n', encoding="utf-8")
        bad = tmp_path / "bad.json"
        bad.write_text("{ not json", encoding="utf-8")
        rc = measure_main([
            "--project-root", str(tmp_path),
            "--coverage-xml", str(tmp_path / "coverage.xml"),
            "--diff-cover-json", str(bad),
            "--fail-under", "80",
        ])
        assert rc == GATE_EXIT_ERROR


# --------------------------------------------------------------------------- #
# Layer 3 — REAL end-to-end fail-path (the core deliverable, AC2)
# --------------------------------------------------------------------------- #
class TestGateRealDiffCover:
    def test_fail_path_undercovered_line(self, tmp_path, capsys):
        _require_real_tools()
        repo = tmp_path / "repo"
        repo.mkdir()
        _synth_repo(repo, covered=False)
        md = repo / "diff-cover.md"
        rc = measure_main([
            "--project-root", str(repo),
            "--coverage-xml", "coverage.xml",
            "--compare-branch", "main",
            "--fail-under", "80",
            "--markdown-out", str(md),
        ])
        out = capsys.readouterr().out
        assert rc == GATE_EXIT_FAIL, out            # under-covered -> exit != 0
        assert rc != 0
        assert md.exists(), "gate must produce the markdown report"
        report = md.read_text(encoding="utf-8")
        assert "50" in report or "Missing" in report  # shows < 80%

    def test_happy_path_covered_line(self, tmp_path, capsys):
        _require_real_tools()
        repo = tmp_path / "repo"
        repo.mkdir()
        _synth_repo(repo, covered=True)
        rc = measure_main([
            "--project-root", str(repo),
            "--coverage-xml", "coverage.xml",
            "--compare-branch", "main",
            "--fail-under", "80",
        ])
        assert rc == GATE_EXIT_PASS, capsys.readouterr().out
