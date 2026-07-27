"""Shared readers for the two-stage PR-review workflow tests.

Not a test module (leading underscore keeps pytest from collecting it). It owns
the file locations and the parsers used by ``test_pr_review_fail_closed.py``
(the gate cannot be bypassed) and ``test_pr_review_fork_trust.py`` (a
credentialed stage 2 trusts nothing the contributor controls).

The parsers matter as much as the paths. Assertions about a workflow must read
its parsed STRUCTURE — ``if:`` expressions, comment-stripped ``run:`` bodies —
never its raw text: these files document the holes they close, so a text match
hits the explanatory comment and reports a defect that is not there. Two tests
false-failed exactly that way before these helpers existed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = _ROOT / ".github" / "workflows"
TEMPLATES = _ROOT / "shared" / "templates" / "github-actions"

# (stage-1 path, stage-2 path). Both the monorepo's own gate and the template
# shipped into every adopted repo must satisfy the same invariants — the whole
# point of the card is that the shipped one was weaker than ours.
STAGE1_STAGE2 = [
    pytest.param(
        WORKFLOWS / "pr-review.yml",
        WORKFLOWS / "pr-review-run.yml",
        id="monorepo",
    ),
    pytest.param(
        TEMPLATES / "claude-review.yml.template",
        TEMPLATES / "claude-review-run.yml.template",
        id="shipped-template",
    ),
]

ALL_STAGE1 = [p.values[0] for p in STAGE1_STAGE2]
ALL_STAGE2 = [p.values[1] for p in STAGE1_STAGE2]


def load(path: Path) -> dict:
    assert path.is_file(), f"missing workflow: {path}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def jobs(path: Path) -> dict:
    return load(path).get("jobs") or {}


def run_bodies(path: Path) -> str:
    """Concatenate every ``run:`` body in the workflow."""
    out = []
    for job in jobs(path).values():
        for step in job.get("steps") or []:
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                out.append(step["run"])
    return "\n".join(out)


def shell_code(path: Path) -> str:
    """``run:`` bodies with comment lines stripped.

    These assertions are about what the shell *executes*, so they must not read
    the comments explaining why a construct is absent — a workflow documenting
    ``# no `|| true` here`` would otherwise fail the very rule it honours.
    """
    lines = []
    for raw in run_bodies(path).splitlines():
        code = raw.split("#", 1)[0] if raw.lstrip().startswith("#") else raw
        lines.append(code)
    return "\n".join(lines)


def job_conditions(path: Path) -> str:
    """Every ``if:`` expression in the workflow, jobs and steps alike."""
    out = []
    for job in jobs(path).values():
        if job.get("if") is not None:
            out.append(str(job["if"]))
        for step in job.get("steps") or []:
            if isinstance(step, dict) and step.get("if") is not None:
                out.append(str(step["if"]))
    return "\n".join(out)
