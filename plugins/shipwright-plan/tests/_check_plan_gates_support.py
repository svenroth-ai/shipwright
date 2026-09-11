"""Shared fixtures/helpers for the ``check-plan-gates.py`` test split
(``test_check_plan_gates.py`` — review/boundary — and
``test_check_plan_gates_sections.py`` — the Step 9 section gates).
Not itself a test file (no ``test_`` prefix, nothing here is collected).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = str(
    Path(__file__).resolve().parent.parent / "scripts" / "checks" / "check-plan-gates.py"
)

WELL_FORMED = (
    "# Section: {name}\n\n"
    "Requirements: {frs}\n\n"
    "## Overview\nDoes the thing.\n\n"
    "## Prerequisites\nNone.\n\n"
    "## Implementation Steps\n1. one\n2. two\n\n"
    "## Tests First\n- a unit test\n"
)

DECISION_LOG_WITH_INTERVIEW = (
    "# Decision Log\n\n---\n\n### ADR-001: x\n"
    "- **Date:** 2026-07-23\n- **Section:** Plan Interview — 01-auth\n"
    "- **Context:** x\n- **Decision:** y\n- **Commit:** n/a\n"
)


def _env_without_review_keys() -> dict:
    """A subprocess env with no external-review keys — FR-01.03 #1's
    key-honesty check reads live env vars, and the developer/CI environment
    running this suite may have real ones set (this repo runs real external
    reviews elsewhere). Stripped here so ``get_external_review_status``
    deterministically reads ``missing_keys`` unless a test opts in."""
    env = os.environ.copy()
    env.pop("OPENROUTER_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)
    return env


def run_gates(
    planning_dir: Path, gate: str = "all", project_root: Path | None = None,
    plugin_root: Path | None = None, extra_env: dict | None = None,
) -> tuple[int, dict]:
    root = project_root or planning_dir.parent
    cmd = [
        sys.executable, SCRIPT,
        "--planning-dir", str(planning_dir),
        "--project-root", str(root),
        "--gate", gate,
    ]
    if plugin_root is not None:
        cmd += ["--plugin-root", str(plugin_root)]
    env = _env_without_review_keys()
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        cwd=str(root),  # no .env.local here — CWD-based lookups find nothing
        env=env,
    )
    try:
        return proc.returncode, json.loads(proc.stdout)
    except json.JSONDecodeError:  # pragma: no cover - diagnostic path
        raise AssertionError(f"non-JSON stdout: {proc.stdout!r} / {proc.stderr!r}")


def _problems(out: dict, gate: str) -> list[str]:
    return next(g for g in out["gates"] if g["gate"] == gate)["problems"]


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True,
    )


def _build_planning(tmp_path):
    """A planning split whose every gate passes. Called from the ``planning``
    fixture in ``conftest.py`` — the fixture itself lives there (not here) so
    it is auto-available to every test module without an import that ruff
    would flag as shadowed by the same-named test-function parameter."""
    d = tmp_path / "01-auth"
    (d / "sections").mkdir(parents=True)
    (d / "spec.md").write_text(
        "# Spec\n\n| ID | Requirement | Priority |\n| FR-01.01 | thing | Must |\n",
        encoding="utf-8",
    )
    (d / "plan.md").write_text(
        "# Plan\n\n<!-- SECTION_MANIFEST\n01-a\n02-b: 01-a\nEND_MANIFEST -->\n",
        encoding="utf-8",
    )
    for name in ("01-a", "02-b"):
        (d / "sections" / f"{name}.md").write_text(
            WELL_FORMED.format(name=name, frs="FR-01.01"), encoding="utf-8"
        )
    (d / "external_review_state.json").write_text(
        json.dumps({
            "status": "completed",
            "provider": "openrouter",
            "verdicts": {"gemini": "approve", "openai": "revise"},
        }),
        encoding="utf-8",
    )
    agent_docs = tmp_path / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True)
    (agent_docs / "decision_log.md").write_text(DECISION_LOG_WITH_INTERVIEW, encoding="utf-8")
    return d


def _build_bare_planning_dir(tmp_path):
    """A minimal planning dir under the CANONICAL ``.shipwright/planning/``
    location — unlike ``_build_planning`` above (which places its files
    directly under ``tmp_path`` for gate-logic convenience, not path realism),
    the boundary gate cares specifically about *where* a session's changes
    land, so these tests need the real layout. Called from the
    ``bare_planning_dir`` fixture in ``conftest.py``."""
    d = tmp_path / ".shipwright" / "planning" / "01-auth"
    (d / "sections").mkdir(parents=True)
    (d / "plan.md").write_text("# Plan\n\n<!-- SECTION_MANIFEST\n01-a\nEND_MANIFEST -->\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@test.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    return d
