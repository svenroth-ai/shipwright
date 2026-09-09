#!/usr/bin/env python3
"""Was a commit's traceability manifest STRUCTURALLY confirmed by a real
GitHub Actions CI run? Never answered from the local tree — always from
GitHub itself.

`ci_manifest_drift_check.py` already runs on every push/PR and regenerates
`.shipwright/compliance/test-traceability.json` from real, fresh test output,
comparing it to the committed one. **Scope, precisely (Stage-3 doubt
review):** that comparison — and therefore this predicate's `verified` — is
STRUCTURAL only (the FR/AC/test-ID mapping: `compare_traceability_manifest
._structural_view()` strips `tests`/`coverage`/`acs` from every requirement
before comparing). The per-test pass/fail status and coverage numbers
(`execution_report()`) are report-only and never gate the exit code — a
standing, deliberate advisory-only decision this predicate does not and must
not change (P3.4c's mandate explicitly forbids making the drift check
blocking). So `verified` means "a real CI run confirmed the committed
manifest's requirement/test-ID structure was not fabricated or hand-edited";
it does NOT independently confirm that the recorded test outcomes or
coverage numbers are accurate. Any consumer reading execution-tier fields
(as P3.5's per-FR promotion does) needs this distinction spelled out, not
assumed.

What WAS missing, and what this predicate adds: the drift check's structural
verdict was discarded at the end of the CI job. `ci.yml` now exposes it as a
step CONCLUSION: a new step, gated on the drift check's own captured exit
code being exactly ``0``, whose only body is a no-op `echo` — so its
conclusion, queryable via the GitHub Actions Jobs API, is `success` if and
only if the manifest committed at that exact commit structurally matched a
fresh regeneration.

No artifact, no digest: a run's `head_sha` already pins it to one exact
commit, and a commit's committed manifest is invariant (content-addressed),
so there is nothing left to bind a digest against that `head_sha` doesn't
already bind (Architecture Review, Round 3 — see the iterate spec's
`## Design history`).

**Unforgeability property.** Only a `push`-triggered, `conclusion=success`
run on the repository's default branch is ever accepted — checked against
the API's OWN run object (`event`, `head_branch`, `conclusion`), never
anything self-reported. A `push` run executes the WORKFLOW FILE OF THE
COMMIT BEING PUSHED, not some earlier version — so the real barrier is not
"the workflow predates the commit" (a `pull_request`-triggered run's own,
possibly attacker-modified `ci.yml` is never accepted regardless, but a
malicious `ci.yml` edit that reaches `main` via a `push` WOULD forge every
`verified` result thereafter). **Who would have to be compromised to fake a
`verified` result:** someone would need to get a `ci.yml` change (or any
commit) onto the default branch — gated by this repo's
`touches_ci_supplychain` mandatory-review POSTURE, a Shipwright-side agent
convention, NOT a GitHub branch-protection technical control — or control of
GitHub's own Actions/API infrastructure, or the ability to repoint THIS
CHECKOUT's `origin` remote to a different, attacker-controlled repository
(`owner_repo()` trusts `git remote get-url origin`, local/mutable/untracked
state), or control of the `gh`/`git` binary or environment this process
resolves (a repo-wide trust assumption every script that shells out to
`gh`/`git` already makes, not unique to this module). This predicate is
trustworthy only run from a checkout and environment the caller itself
controls (true for a freshly-fetched CI/iterate worktree, the only place
P3.5 calls it) — a tree-local *content* write alone is insufficient.

Four outcomes, never conflated: `verified` (a qualifying run's provenance
step conclusion is `success`), `not_verified` (at least one qualifying run
exists, but none confirmed a clean manifest), `no_record` (no qualifying run
exists at all), `error` (the query itself could not complete or was
detectably truncated — `gh` missing, timeout, malformed response, an invalid
`commit`/`workflow_file`, or a `total_count` exceeding the fetched page).
Only `error` means "could not determine"; `no_record` is a definite,
completed negative answer.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import github_api

#: The literal name of the `ci.yml` step whose conclusion this module reads.
#: The ONE place this string is spelled — a CI-YAML-shape test imports this
#: constant rather than duplicating the literal, so a rename in one place
#: cannot silently break resolution into `no_record`.
PROVENANCE_STEP_NAME = "Confirm traceability manifest verified (no drift)"

_TIMEOUT_SECONDS = 30
#: Exactly 40 hex chars — GitHub's `head_sha` filter on the workflow-runs API
#: is an EXACT match, so an accepted-but-unexpanded abbreviation would
#: silently under-match into a false `no_record` (Stage-3 doubt review: the
#: CLI wrapper expands via `git rev-parse` before calling this function, but
#: this function is the actual library surface a caller may invoke directly
#: — the contract belongs here, not only at the CLI). `fullmatch`, not a
#: `$`-anchored `match` — `$` matches before a trailing newline.
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")

#: `workflow_file` lands in the same request path as `commit`; unlike
#: `commit` it was previously unvalidated (Stage-3 doubt review) despite the
#: module's whole job being to trust nothing self-reported.
_WORKFLOW_FILE_RE = re.compile(r"[A-Za-z0-9._-]+\.ya?ml")

#: Sentinel distinguishing "the jobs query itself failed" from a genuine
#: "the step is absent / has no conclusion" (``None``) — Stage-1 spec review
#: caught these being conflated, which silently reported `not_verified`
#: (a definite negative) for what was really a transient `gh` failure.
_JOBS_QUERY_FAILED = object()


@dataclass(frozen=True)
class CIVerification:
    status: str  # "verified" | "not_verified" | "no_record" | "error"
    detail: str
    run_id: int | None = None


def _gh_api(path: str, *, cwd: Path) -> Any | None:
    """Run ``gh api <path>`` with ``cwd`` pinned to ``project_root`` (never the
    process cwd — the exact bug `owner_repo()` was already fixed to avoid,
    which `github_api.default_branch()` would reintroduce if reused here).
    Returns parsed JSON, or ``None`` on ANY failure."""
    try:
        result = subprocess.run(
            ["gh", "api", path],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout or "null")
    except json.JSONDecodeError:
        return None


def _qualifying_runs(
    owner: str, repo: str, commit: str, workflow_file: str, default_branch: str, *, cwd: Path
) -> list[dict] | None:
    """Runs at ``head_sha=commit`` that pass the unforgeability trust boundary
    (push, default branch, conclusion=success), newest first. ``None`` means
    the query itself failed OR was silently truncated by ``per_page`` (caller
    must report ``error``, never `no_record` — Stage-3 doubt review: a
    truncated tail is the OLDEST runs, exactly where an older confirming run
    would live, so an undetected truncation would misreport a genuine
    `verified` commit as `not_verified`)."""
    data = _gh_api(
        f"repos/{owner}/{repo}/actions/workflows/{workflow_file}/runs"
        f"?head_sha={commit}&status=success&per_page=100",
        cwd=cwd,
    )
    if not isinstance(data, dict) or not isinstance(data.get("workflow_runs"), list):
        return None
    total_count = data.get("total_count")
    if isinstance(total_count, int) and total_count > len(data["workflow_runs"]):
        return None
    qualifying = [
        run
        for run in data["workflow_runs"]
        if isinstance(run, dict)
        and run.get("event") == "push"
        and run.get("head_branch") == default_branch
        and run.get("conclusion") == "success"
    ]
    qualifying.sort(key=lambda r: r.get("run_started_at") or r.get("created_at") or "", reverse=True)
    return qualifying


def _provenance_step_conclusion(owner: str, repo: str, run_id: int, *, cwd: Path) -> str | None:
    """The `PROVENANCE_STEP_NAME` step's conclusion within ``run_id`` —
    scanned across ALL of the run's jobs (an OS-matrixed `python-checks` job
    would put the step in more than one; the OS matrix is this repo's own
    workflow convention, so a single-job assumption would be wrong the
    moment it applies here), preferring `success` if ANY job's step
    concluded it — deliberately permissive, not the conservative reading:
    structural drift (see the module docstring's scope note) is expected to
    be platform-independent by the comparator's own premise, so one
    confirming leg is taken as sufficient rather than requiring every leg to
    agree (Stage-3 doubt review, disclosed).

    Returns the conclusion string (`success` wins immediately; otherwise the
    first non-success conclusion seen); ``None`` if the jobs list was fetched
    successfully, every job's shape was well-formed, and the step is
    genuinely absent from all of them; or the ``_JOBS_QUERY_FAILED`` sentinel
    if the query itself could not complete OR any job entry was malformed
    (External Review, openai: a schema-malformed job/step must not be
    silently read as "step absent" — that is a different fact from "the API
    responded, but nothing confirmed") — the caller must map that to
    `error`, never fall through to `not_verified`.
    """
    data = _gh_api(f"repos/{owner}/{repo}/actions/runs/{run_id}/jobs?per_page=100", cwd=cwd)
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        return _JOBS_QUERY_FAILED
    found: str | None = None
    malformed = False
    for job in data["jobs"]:
        if not isinstance(job, dict) or not isinstance(job.get("steps"), list):
            malformed = True
            continue
        for step in job["steps"]:
            if not isinstance(step, dict) or step.get("name") != PROVENANCE_STEP_NAME:
                continue
            conclusion = step.get("conclusion")
            if not isinstance(conclusion, str):
                continue
            if conclusion == "success":
                return "success"
            if found is None:
                found = conclusion
    if found is None and malformed:
        return _JOBS_QUERY_FAILED
    return found


def resolve_ci_verification(
    commit: str, *, project_root: Path | str, workflow_file: str = "ci.yml"
) -> CIVerification:
    """Was ``commit``'s traceability manifest verified by a real, trunk CI run?

    Reads nothing from the local tree — every fact comes from the GitHub
    Actions API for ``project_root``'s own repository, queried with ``cwd``
    pinned explicitly (never the process cwd)."""
    if not isinstance(commit, str):
        return CIVerification("error", f"commit {commit!r} is not a 40 char hex SHA")
    #: git/GitHub always emit lowercase SHAs and the CLI's `rev-parse`
    #: expansion normalizes, but a direct library caller passing an
    #: uppercase (still legal) SHA should not be rejected (External Review:
    #: glm).
    commit = commit.lower()
    if not _COMMIT_RE.fullmatch(commit):
        return CIVerification("error", f"commit {commit!r} is not a 40 char hex SHA")
    if not isinstance(workflow_file, str) or not _WORKFLOW_FILE_RE.fullmatch(workflow_file):
        return CIVerification("error", f"workflow_file {workflow_file!r} is not a bare *.yml/*.yaml filename")

    root = Path(project_root)
    owner_repo_str = github_api.owner_repo(root)
    if owner_repo_str is None or "/" not in owner_repo_str:
        return CIVerification("error", "could not resolve owner/repo from the origin remote")
    owner, repo = owner_repo_str.split("/", 1)

    repo_data = _gh_api(f"repos/{owner}/{repo}", cwd=root)
    default_branch = repo_data.get("default_branch") if isinstance(repo_data, dict) else None
    if not isinstance(default_branch, str) or not default_branch:
        return CIVerification("error", "could not resolve the repository's default branch")

    qualifying = _qualifying_runs(owner, repo, commit, workflow_file, default_branch, cwd=root)
    if qualifying is None:
        return CIVerification("error", "could not list workflow runs for this commit")

    # A query failure (jobs endpoint) or a malformed run object does NOT
    # short-circuit the search: an in-flight rerun or a transient `gh`
    # failure on one candidate must not hide an older run that genuinely
    # confirms the manifest (AC9's own reasoning, extended to failures, not
    # just non-confirming conclusions). Only after every candidate is
    # exhausted with no `verified` match does an unresolved query win over a
    # `not_verified` verdict.
    query_failed = False
    for run in qualifying:
        run_id = run.get("id")
        if not isinstance(run_id, int):
            query_failed = True
            continue
        conclusion = _provenance_step_conclusion(owner, repo, run_id, cwd=root)
        if conclusion is _JOBS_QUERY_FAILED:
            query_failed = True
            continue
        if conclusion == "success":
            return CIVerification("verified", f"run {run_id} confirmed a clean manifest", run_id)

    if query_failed:
        return CIVerification("error", "one or more qualifying runs could not be queried for their jobs")
    if qualifying:
        return CIVerification(
            "not_verified", "qualifying run(s) found for this commit, none confirmed a clean manifest"
        )
    return CIVerification("no_record", "no qualifying push run found for this commit")
