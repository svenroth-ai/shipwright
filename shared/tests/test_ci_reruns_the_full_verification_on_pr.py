"""This repository's own PR gates actually re-run tests, lint, security and
the host's own code analysis — not merely SOME of them, and not merely on
push.

@covers FR-01.17/AC01 — "the project's tests, its lint, its security checks
and the host's own code analysis all run again there — a pass on the
author's machine is never accepted in place of that." The sibling files in
this directory (``test_ci_workflow_convention.py``,
``test_security_workflow_convention.py``) pin the templates Shipwright
SCAFFOLDS into an adopted repo; none of them pins that THIS repository's own
workflows do all four things on a pull request. That is a distinct claim —
a repo could scaffold a correct template for others while its own CI drifted
— so it needs its own drift pin, read from the real files, not restated from
the templates.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _triggers(doc: dict) -> dict:
    # PyYAML's "Norway problem": a bare `on:` key resolves to boolean True.
    return doc.get("on") or doc.get(True) or {}


def _all_run_bodies(doc: dict) -> str:
    out: list[str] = []
    for job in (doc.get("jobs") or {}).values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                out.append(step["run"])
    return "\n".join(out)


def _real_commands(body: str) -> str:
    """Drop lines that could contain a tool's name without ever running it.

    A bare substring search over a `run:` body is fooled by a workflow that
    merely prints the tool's name — `echo "pytest ruff semgrep"` mentions all
    three without executing any of them, and a `#` comment can say anything.
    Neither shape can appear as a REAL invocation this narrowly, so stripping
    them out before searching closes that gap without needing a full shell
    parser (Tier-3 PR review, req3-05 t9)."""
    kept = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("echo "):
            continue
        kept.append(line)
    return "\n".join(kept)


@pytest.mark.covers("FR-01.17/AC01")
@pytest.mark.parametrize("workflow", ["ci.yml", "security.yml", "codeql.yml"])
def test_each_gate_runs_on_pull_request(workflow: str) -> None:
    triggers = _triggers(_load(workflow))
    assert "pull_request" in triggers, (
        f"{workflow}: does not fire on pull_request — a pass on the author's "
        f"machine would stand in for the host's own re-check"
    )


@pytest.mark.covers("FR-01.17/AC01")
@pytest.mark.parametrize("workflow", ["ci.yml", "security.yml", "codeql.yml"])
def test_the_pull_request_trigger_has_no_path_filter(workflow: str) -> None:
    """A `paths:`/`paths-ignore:` filter under `pull_request:` would let a
    change slip through unre-checked depending only on which files it
    touches — the AC says "all run again there", not "run again there for
    some diffs". This repo's own gates keep the trigger unconditional; a
    filtered trigger would defeat the whole point of an independent re-check
    without ever showing up as a missing job or a passing-green run."""
    triggers = _triggers(_load(workflow))
    pr_trigger = triggers.get("pull_request")
    if isinstance(pr_trigger, dict):
        assert "paths" not in pr_trigger and "paths-ignore" not in pr_trigger, (
            f"{workflow}: pull_request trigger is narrowed by a path filter — "
            f"some PRs would never invoke this gate at all"
        )


#: The one job per workflow that actually carries the verification steps this
#: AC is about — resolved by name, not "every job", so a legitimate
#: `if: github.event_name == 'pull_request'` on some UNRELATED job (a PR-only
#: comment-poster, say) can't be misread as evidence against this one.
_GATE_JOBS = {"ci.yml": "python-checks", "security.yml": "scan", "codeql.yml": "analyze"}

#: Substrings identifying the specific STEPS, inside a gate job, that are the
#: actual verification invocation — narrower than "every step in the job"
#: because unrelated steps (coverage upload, PR comments) legitimately gate
#: on `github.event_name`/`success()` for their own reasons. `ci.yml`/
#: `security.yml` invoke their tools via a `run:` shell body; `codeql.yml`
#: invokes GitHub's own action via `uses:` — different YAML keys, same check.
_GATE_STEP_MARKERS = {
    "ci.yml": ("pytest", "ruff", "semgrep"),
    "security.yml": ("semgrep",),
    "codeql.yml": ("codeql-action/analyze",),
}


def _gate_steps(job: dict, markers: tuple[str, ...]) -> list[dict]:
    out = []
    for step in job.get("steps") or []:
        if not isinstance(step, dict):
            continue
        haystack = "\n".join(
            str(step.get(key, "")) for key in ("run", "uses")
        )
        if any(marker in haystack for marker in markers):
            out.append(step)
    return out


@pytest.mark.covers("FR-01.17/AC01")
@pytest.mark.parametrize("workflow", sorted(_GATE_JOBS))
def test_the_gate_job_itself_carries_no_conditional(workflow: str) -> None:
    """A job-level `if:` — of ANY shape, not merely one that literally
    mentions "pull_request" — can make the job that runs pytest/ruff/semgrep
    a no-op for a pull request while the workflow file still shows the job as
    present to a reviewer skimming triggers (a substring check for the word
    "pull_request" would wrongly pass a condition like
    `if: github.event_name == 'push'`, which excludes PRs without ever
    naming them — external code review, openai, medium). The unconditional
    trigger (asserted separately) plus NO job-level `if:` at all is what
    together prove this job runs on every pull request."""
    doc = _load(workflow)
    job = (doc.get("jobs") or {})[_GATE_JOBS[workflow]]
    assert job.get("if") is None, (
        f"{workflow}:{_GATE_JOBS[workflow]} has a job-level `if:` "
        f"({job.get('if')!r}) — a condition of any shape could make this "
        f"job skip on a pull request while looking present in the file"
    )


@pytest.mark.covers("FR-01.17/AC01")
@pytest.mark.parametrize("workflow", sorted(_GATE_JOBS))
def test_no_gate_carrying_step_is_conditioned_out(workflow: str) -> None:
    """Job-level `if:` absence (checked above) is not enough on its own: a
    step-level `if:` on the specific step invoking pytest/ruff/semgrep would
    defeat the whole guarantee while every other test in this file stays
    green (external code review, glm, low). Checked only against the steps
    whose own `run:` body actually names one of the gate tools — not every
    step in the job, since unrelated steps legitimately gate on
    `github.event_name`/`success()`."""
    doc = _load(workflow)
    job = (doc.get("jobs") or {})[_GATE_JOBS[workflow]]
    gate_steps = _gate_steps(job, _GATE_STEP_MARKERS[workflow])
    assert gate_steps, f"{workflow}: found no step matching {_GATE_STEP_MARKERS[workflow]}"
    for step in gate_steps:
        assert step.get("if") is None, (
            f"{workflow}: step {step.get('name')!r} invokes a gate tool but "
            f"carries a step-level `if:` ({step.get('if')!r}) that could "
            f"skip it on a pull request"
        )


@pytest.mark.covers("FR-01.17/AC01")
def test_ci_reruns_the_real_test_suite() -> None:
    body = _real_commands(_all_run_bodies(_load("ci.yml")))
    assert re.search(r"\bpytest\b\s+\S", body), (
        "ci.yml must actually invoke pytest with a real target/flag, not "
        "merely lint or mention the word"
    )


@pytest.mark.covers("FR-01.17/AC01")
def test_ci_reruns_lint() -> None:
    body = _real_commands(_all_run_bodies(_load("ci.yml")))
    assert re.search(r"\bruff@[\w.]+\s+check\b", body), (
        "ci.yml must actually invoke `ruff@<version> check`, not merely "
        "mention ruff"
    )


@pytest.mark.covers("FR-01.17/AC01")
def test_ci_reruns_security_scanners() -> None:
    """Semgrep never appears as a literal `semgrep ...` command here — it
    runs through `scan.py --scan-types sast,...` (`sast` is Semgrep's scan
    type, confirmed in `scan.py`'s own type map). A bare substring search for
    "semgrep" was matching only `pip install semgrep` and comment prose, none
    of which proves the scanner actually runs on a pull request (Tier-3 PR
    review, req3-05 t9)."""
    ci_body = _real_commands(_all_run_bodies(_load("ci.yml")))
    security_body = _real_commands(_all_run_bodies(_load("security.yml")))
    pattern = re.compile(r"scan\.py\b[\s\S]{0,200}?--scan-types[ =]\S*\bsast\b")
    assert pattern.search(ci_body) or pattern.search(security_body), (
        "neither ci.yml nor security.yml actually invokes scan.py with the "
        "sast scan type — a security check existing is not the same as it "
        "running on the pull request"
    )


@pytest.mark.covers("FR-01.17/AC01")
def test_codeql_is_the_hosts_own_code_analysis() -> None:
    """CodeQL is GitHub's own static analysis engine, distinct from the
    project's own scanners (semgrep/gitleaks/trivy) — the AC names it
    separately ("its security checks AND the host's own code analysis").

    Checked via the parsed `uses:` step, not a raw text search — a step's
    `uses:` field is what GitHub Actions actually executes, unlike a `run:`
    body a comment or echo could imitate."""
    doc = _load("codeql.yml")
    uses_values = [
        str(step.get("uses", ""))
        for job in (doc.get("jobs") or {}).values()
        if isinstance(job, dict)
        for step in job.get("steps") or []
        if isinstance(step, dict)
    ]
    assert any("codeql-action/analyze" in u for u in uses_values), (
        "codeql.yml has no step that actually `uses:` github/codeql-action/analyze"
    )
