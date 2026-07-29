"""The `gh` / `git` primitives behind `tools/main_health.py`.

Split out so both files stay inside the 300-LOC source budget, and so the shell
is separable from the assembly: every function here does exactly one host call
and either returns its payload or raises :class:`ShellError`. Nothing here
decides anything — the decisions are in `lib.main_health*`, which are pure.

The one rule: **a failed call raises.** It never returns an empty list that the
caller would read as "nothing found". The assembly layer turns each raise into a
named entry in the report's ``unknown[]``, so a host that could not be reached is
visibly different from a branch that is fine.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

#: Fields `gh run list --json` must return for the health predicate to work.
#: `event` and `headBranch` are load-bearing: without them a green pull-request
#: run for a commit masks the red push-to-main run for the same commit.
RUN_FIELDS = (
    "databaseId,workflowName,headSha,headBranch,event,status,conclusion,"
    "url,createdAt"
)
PR_FIELDS = (
    "number,url,state,headRefName,headRepositoryOwner,author,createdAt,updatedAt"
)

_PR_IN_SUBJECT = re.compile(r"\(#(\d+)\)\s*$")
_UNIT_SEP = "\x1f"


class ShellError(RuntimeError):
    """A `gh`/`git` call that did not succeed. Never folded into a clean answer."""


def run(cmd: list[str], cwd: Path) -> str:
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    except (OSError, ValueError) as exc:  # gh not installed, bad argv
        raise ShellError(f"{cmd[0]}: {exc}") from exc
    if proc.returncode != 0:
        raise ShellError((proc.stderr or f"{cmd[0]} failed").strip()[:300])
    return proc.stdout


def gh_json(args: list[str], cwd: Path):
    try:
        return json.loads(run(["gh", *args], cwd) or "null")
    except json.JSONDecodeError as exc:
        raise ShellError(f"gh {args[0]}: unreadable JSON ({exc})") from exc


def _pairs(out: str) -> list[dict]:
    return [
        {"sha": sha, "subject": subject}
        for sha, subject in (
            line.split(_UNIT_SEP, 1) for line in out.splitlines() if _UNIT_SEP in line
        )
    ]


def commit_series(cwd: Path, branch_ref: str, window: int) -> list[dict]:
    """The first-parent commit series newest-first, `[{sha, subject}, ...]`."""
    return _pairs(run(
        ["git", "-C", str(cwd), "log", "--first-parent", f"-{window}",
         f"--format=%H{_UNIT_SEP}%s", branch_ref],
        cwd,
    ))


def workflow_files(cwd: Path) -> list[str] | None:
    """The repository's actual workflow filenames, so a monitored workflow with
    no file behind it can be named instead of producing silent incompleteness."""
    d = cwd / ".github" / "workflows"
    if not d.is_dir():
        return None
    return sorted(p.name for p in d.glob("*.y*ml"))


def repo_slug(cwd: Path) -> tuple[str, str]:
    payload = gh_json(["repo", "view", "--json", "owner,name"], cwd) or {}
    return (payload.get("owner") or {}).get("login", ""), payload.get("name", "")


def list_runs(cwd: Path, branch: str, limit: int) -> list[dict]:
    return gh_json(
        ["run", "list", "--branch", branch, "--limit", str(limit),
         "--json", RUN_FIELDS],
        cwd,
    ) or []


def failed_steps(cwd: Path, run_id: int, fail_conclusions) -> list[dict]:
    """Failed job/step names from STRUCTURED data, never from log text.

    Log formatting is not a contract and cannot distinguish two failed steps
    that print similarly; the jobs payload names them.
    """
    payload = gh_json(["run", "view", str(run_id), "--json", "jobs"], cwd) or {}
    return [
        {"job": job.get("name"), "step": step.get("name")}
        for job in (payload.get("jobs") or [])
        for step in (job.get("steps") or [])
        if (step.get("conclusion") or "").lower() in fail_conclusions
    ]


def failed_log(cwd: Path, run_id: int) -> str:
    return run(["gh", "run", "view", str(run_id), "--log-failed"], cwd)


def pr_for_commit(cwd: Path, owner: str, name: str, sha: str, subject: str):
    """`(base_sha, pr_number, reason_code)` for the pull request that landed `sha`.

    The commit→PR association endpoint is authoritative and handles squash,
    rebase and merge alike; a `(#NNN)` in the subject is only the fallback. When
    neither answers, the caller gets a reason code — never an invented base.
    """
    try:
        pulls = gh_json(["api", f"repos/{owner}/{name}/commits/{sha}/pulls"], cwd) or []
    except ShellError:
        pulls = []
    chosen = next(
        (p for p in pulls if (p.get("merge_commit_sha") or "") == sha),
        pulls[0] if pulls else None,
    )
    if chosen is not None:
        return (chosen.get("base") or {}).get("sha"), chosen.get("number"), None

    m = _PR_IN_SUBJECT.search(subject or "")
    if not m:
        return None, None, "pr_association_unavailable"
    try:
        view = gh_json(["pr", "view", m.group(1), "--json", "baseRefOid,number"], cwd) or {}
    except ShellError:
        return None, None, "pr_association_unavailable"
    return view.get("baseRefOid"), view.get("number"), None


def commits_between(cwd: Path, base_sha: str, bad_sha: str) -> list[dict] | None:
    """Merges the bad commit was never tested against, or None if the base is
    not an ancestor (a rebase or force-push — the range would be meaningless)."""
    try:
        run(["git", "-C", str(cwd), "merge-base", "--is-ancestor",
             base_sha, f"{bad_sha}^"], cwd)
    except ShellError:
        return None
    return _pairs(run(
        ["git", "-C", str(cwd), "log", "--first-parent", f"--format=%H{_UNIT_SEP}%s",
         f"{base_sha}..{bad_sha}^"],
        cwd,
    ))


#: How many pull requests the claim query looks back over. A repair attempt that
#: falls off the end is invisible, which UNDER-counts `failed_attempts` and can
#: skip the "two attempts already failed" escalation — so the number is named
#: here rather than buried as a literal, and it is generous relative to the two
#: attempts that trigger escalation (Tier-3 review).
CLAIM_LOOKBACK_PRS = 100


def list_prs(cwd: Path, limit: int = CLAIM_LOOKBACK_PRS) -> list[dict]:
    return gh_json(
        ["pr", "list", "--state", "all", "--limit", str(limit), "--json", PR_FIELDS],
        cwd,
    ) or []


def list_branch_refs(cwd: Path, owner: str, name: str) -> list[str]:
    """Branch refs in THIS repository — a pushed claim branch counts even before
    its pull request exists, which is what makes the claim atomic."""
    refs = gh_json(["api", f"repos/{owner}/{name}/git/matching-refs/heads/"], cwd) or []
    return [r.get("ref", "") for r in refs]
