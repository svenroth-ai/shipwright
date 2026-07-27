"""Tests for the design phase's Requirement Write-Back Gate.

External review's sharpest hit on the first draft: AC-4 said finalization must
*refuse* while a round is silent, but the gate was an ``ls`` plus a prose
instruction — no code consumer, nothing that could fail. This is the mechanism
that makes the refusal real.

Origin: trg-e9e5188e (FR-01.04).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tools"))

from check_design_round_declarations import discover_rounds, main  # noqa: E402
from lib.requirement_impact_store import declaration_dir  # noqa: E402
from record_requirement_impact import main as record_main  # noqa: E402

SPEC = ".shipwright/planning/01-adopted/spec.md"
RUN = "design-run-a"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    _write(tmp_path, SPEC, "# Spec\n\n| FR-01.04 | ... |\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def _round_file(project: Path, n: int, run_id: str = RUN) -> None:
    """Start a round: snapshot its baseline, which is also the round registry.

    The registry deliberately is NOT `design-feedback-round*.md` — that file is
    gitignored review scratch the standalone flow exports through a browser
    download, so it may live anywhere or arrive named `...round2 (1).md`, and an
    empty glob resolved to PASS.
    """
    record_main([
        "--project-root", str(project), "--run-id", run_id,
        "--phase", "design", "--scope", f"round-{n}", "--snapshot-baseline",
    ])


def _declare(project: Path, scope: str, run_id: str = RUN) -> int:
    return record_main([
        "--project-root", str(project), "--run-id", run_id,
        "--phase", "design", "--scope", scope,
        "--impact", "none", "--reason", "appearance only: spacing and colour",
        "--worktree",
    ])


def _check(project: Path, capsys, *extra: str) -> tuple[int, dict]:
    code = main(["--project-root", str(project), "--run-id", RUN, *extra])
    return code, json.loads(capsys.readouterr().out)


# --------------------------------------------------------------------------
# Round discovery
# --------------------------------------------------------------------------

def test_rounds_are_discovered_from_the_baselines_the_rounds_recorded(project, capsys):
    """NOT from gitignored review scratch, which could live anywhere or vanish."""
    _round_file(project, 1)
    _round_file(project, 2)
    capsys.readouterr()
    assert discover_rounds(project, RUN) == ["round-1", "round-2"]


def test_rounds_from_another_run_are_not_this_run_s(project, capsys):
    """The design loop is resumable; an earlier session's rounds are not ours."""
    _round_file(project, 1, run_id="EARLIER-SESSION")
    _round_file(project, 2)
    capsys.readouterr()
    assert discover_rounds(project, RUN) == ["round-2"]


def test_no_baselines_means_no_rounds(project):
    assert discover_rounds(project, RUN) == []


# --------------------------------------------------------------------------
# The gate itself
# --------------------------------------------------------------------------

def test_a_silent_round_blocks_finalization(project, capsys):
    """The failure AC-4 exists to prevent."""
    _round_file(project, 1)
    capsys.readouterr()

    code, payload = _check(project, capsys)

    assert code == 1
    assert payload["undeclared"] == ["round-1"]
    assert "not complete while a round is silent" in payload["detail"]


def test_a_declared_round_passes(project, capsys):
    _round_file(project, 1)
    _declare(project, "round-1")
    capsys.readouterr()

    code, payload = _check(project, capsys)

    assert code == 0
    assert payload["declared"] == ["round-1"]
    assert payload["undeclared"] == []


def test_one_declared_and_one_silent_still_blocks(project, capsys):
    _round_file(project, 1)
    _round_file(project, 2)
    _declare(project, "round-1")
    capsys.readouterr()

    code, payload = _check(project, capsys)

    assert code == 1
    assert payload["declared"] == ["round-1"]
    assert payload["undeclared"] == ["round-2"]


def test_a_declaration_from_another_run_does_not_satisfy_this_one(project, capsys):
    """Identity is (run_id, phase, scope) — a stale round must not count."""
    _round_file(project, 1)
    _declare(project, "round-1", run_id="SOME-EARLIER-RUN")
    capsys.readouterr()

    code, payload = _check(project, capsys)

    assert code == 1
    assert payload["undeclared"] == ["round-1"]


def test_a_build_declaration_does_not_satisfy_a_design_round(project, capsys):
    _round_file(project, 1)
    record_main([
        "--project-root", str(project), "--run-id", RUN,
        "--phase", "build", "--scope", "round-1",
        "--impact", "none", "--reason", "wrong phase", "--worktree",
    ])
    capsys.readouterr()

    code, payload = _check(project, capsys)

    assert code == 1
    assert payload["undeclared"] == ["round-1"]


def test_explicit_rounds_override_discovery(project, capsys):
    """A phase that knows its rounds should not depend on discovery at all."""
    code, payload = _check(project, capsys, "--round", "round-7")

    assert code == 1
    assert payload["rounds_checked"] == ["round-7"]


def test_no_rounds_passes_but_says_so(project, capsys):
    """A design approved on the first pass is clean — and must not read as
    'the gate ran and found everything in order' when it had nothing to check."""
    code, payload = _check(project, capsys)

    assert code == 0
    assert "nothing to declare" in payload["note"]


def test_a_damaged_declaration_is_reported_not_treated_as_absent(project, capsys):
    _round_file(project, 1)
    capsys.readouterr()
    directory = declaration_dir(project)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "broken__design__round-1__deadbeef.json").write_text(
        "{not json", encoding="utf-8")

    code, payload = _check(project, capsys)

    assert code == 2
    assert payload["error"] == "declaration_damaged"
    assert len(payload["problems"]) == 1
