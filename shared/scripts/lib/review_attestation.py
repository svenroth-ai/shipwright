"""Can ``3f-bis`` rely on the campaign runner's own review rows?

The runner spawns the ``spec`` -> ``code`` -> ``doubt`` cascade itself and records
each row ``completed``. Those rows are self-attested, so ``3f-bis`` used to re-run
the cascade whenever its trigger fired. It may skip that re-review only when the
runner's rows are specific enough to check: each reviewed row carries
``verdict: "pass"`` and ``reviewed_commit`` (the HEAD the reviewed diff was taken
at), and nothing but non-code artifacts changed between that commit and the head
``3f-bis`` is about to merge. Everything else -- an absent field, a legacy row, a
fix committed after the review -- means "not attested" and the cascade runs.

The commit binding is verified here against the git history, not taken from the
row's word. The row itself stays self-reported (a runner can write any SHA that
is genuinely an ancestor with a clean tail); the check closes stale and absent
attestations, not a runner that lies about what its subagent said.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

_SHA_RE = re.compile(r"[0-9a-f]{40}")
#: Paths whose change after a review cannot alter the reviewed behaviour: the
#: artifacts finalization writes. Anything else is code the reviewer never saw.
NON_CODE_PREFIXES = (".shipwright/", "CHANGELOG-unreleased.d/")
#: ... except what executes or feeds a gate: a script under ``.shipwright/``, a bloat
#: exception (relaxes a CI gate) and the traceability manifest (a CI gate input).
_EXECUTABLE_SUFFIXES = (".py", ".sh", ".ps1", ".cmd", ".bat", ".js", ".mjs", ".ts")
_GATE_INPUTS = ("bloat-exception", "test-traceability.json")


def _is_code(path: str) -> bool:
    if not path.startswith(NON_CODE_PREFIXES):
        return True
    return path.endswith(_EXECUTABLE_SUFFIXES) or any(g in path for g in _GATE_INPUTS)
_STAGES = {"spec": "spec-reviewer", "code": "code-reviewer"}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          encoding="utf-8", errors="replace", timeout=60, check=False)


def _commit_is_current(repo: Path, reviewed: str, head: str) -> str | None:
    """``None`` when ``head`` is ``reviewed`` plus non-code changes only."""
    if reviewed == head:
        return None
    if _git(repo, "merge-base", "--is-ancestor", reviewed, head).returncode != 0:
        return f"reviewed_commit {reviewed[:12]} is not an ancestor of {head[:12]}"
    diff = _git(repo, "diff", "--name-only", "--no-renames", f"{reviewed}..{head}")
    if diff.returncode != 0:
        return "git diff between reviewed_commit and head failed"
    code = [p for p in diff.stdout.splitlines() if p and _is_code(p)]
    if code:
        return f"code changed after the review: {', '.join(code[:3])}" + (" ..." if len(code) > 3 else "")
    return None


#: Above this many diff lines a runner's own "Stage 3 did not apply" is not
#: enough: the doubt pass must have actually run (mirrors 3f-bis's floor).
DOUBT_REQUIRED_ABOVE_LINES = 100


def _blocking(row: dict) -> bool:
    """A row that is a ``pass`` yet carries a high/critical finding was recorded
    from a template, not from the reviewer's reply: refuse to trust its verdict."""
    findings = row.get("findings")
    return any(isinstance(f, dict) and str(f.get("severity", "")).lower() in {"high", "critical", "blocking"}
               for f in (findings if isinstance(findings, list) else []))


def attest(project_root: Path | str, run_id: str, head: str,
           diff_lines: int | None = None) -> tuple[bool, str]:
    """``(attested, reason)`` for the unit worktree ``project_root`` at ``head``.

    ``diff_lines`` is 3f-bis's own measure of the unit's diff; over the floor (or
    unknown) the runner may not have declared ``doubt`` not applicable."""
    root = Path(project_root)
    if not _SHA_RE.fullmatch(head or ""):
        return False, "head is not a full commit SHA"
    # The record is read from the commit being merged, not the working tree: a row
    # written after the last commit would otherwise attest a tree that never carries it.
    shown = _git(root, "show", f"{head}:.shipwright/planning/iterate/{run_id}/reviews.json")
    if shown.returncode != 0:
        return False, "the head commit carries no reviews.json for this run"
    try:
        record = json.loads(shown.stdout)
    except ValueError as exc:
        return False, f"review record unreadable: {exc}"
    reviews = (record or {}).get("reviews") or {}
    for review_type, reviewer in _STAGES.items():
        row = reviews.get(review_type) or {}
        if row.get("status") != "completed" or row.get("verdict") != "pass":
            return False, f"{review_type} is not a completed pass"
        if _blocking(row):
            return False, f"{review_type} records an unresolved high-severity finding"
        if row.get("recorded_by") != reviewer:
            return False, f"{review_type} was not recorded from {reviewer}"
        if not _SHA_RE.fullmatch(row.get("reviewed_commit") or ""):
            return False, f"{review_type} records no reviewed_commit"
        if (why := _commit_is_current(root, row["reviewed_commit"], head)):
            return False, f"{review_type}: {why}"
    doubt = reviews.get("doubt") or {}
    if _blocking(doubt):
        return False, "doubt records an unresolved high-severity finding"
    small = diff_lines is not None and diff_lines <= DOUBT_REQUIRED_ABOVE_LINES
    if small and doubt.get("status") == "not_applicable" and doubt.get("reason_code") == "diff-below-threshold":
        return True, "spec and code passed at a reviewed commit that is current; doubt did not apply"
    if doubt.get("recorded_by") != "doubt-reviewer" and doubt.get("status") == "completed":
        return False, "doubt was not recorded from doubt-reviewer"
    if doubt.get("status") != "completed" or doubt.get("verdict") != "pass":
        return False, "doubt is not a completed pass (and the diff is not known to be below the doubt threshold)"
    if not _SHA_RE.fullmatch(doubt.get("reviewed_commit") or ""):
        return False, "doubt records no reviewed_commit"
    if (why := _commit_is_current(root, doubt["reviewed_commit"], head)):
        return False, f"doubt: {why}"
    return True, "spec, code and doubt passed at a reviewed commit that is current"
