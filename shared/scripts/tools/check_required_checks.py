#!/usr/bin/env python3
"""Producer: does the host's must-pass check set match the checks that exist?

Which checks block a merge is configured OUTSIDE the repository, so a newly
added check runs, reports, and gates nothing until someone configures it there.
The derivation helper that knows the real names already existed and compared
nothing; this is the comparison. FR-01.17 (E)6.

Runs as a producer with the operator's own `gh` auth, NOT as a CI gate: the
Actions token cannot read a repo's protection configuration. On divergence it
files ONE tracked follow-up, deduped on the exact divergence so the same drift
does not re-file every run.

    uv run shared/scripts/tools/check_required_checks.py --project-root .

**An empty must-pass set is a finding, not an error.** A repo that requires
nothing is the loudest case this tool has to report — every check it runs gates
nothing — so "no policy exists" is READ successfully and compared against, and
only "the policy could not be consulted" exits non-zero. Conflating the two
would blind the producer exactly where it matters most.

Exit codes: 0 in sync or drift recorded · 2 the configuration could not be read
(no `gh`, no auth, unreachable repo) — reported, never guessed at.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.required_checks_drift import (  # noqa: E402
    all_workflow_check_names,
    compare_required_checks,
    dedup_key,
    render_drift,
)
from triage import append_triage_item_idempotent, should_route_to_outbox  # noqa: E402


_HTTP_STATUS_RE = re.compile(r"\(HTTP (\d{3})\)")
_SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


class GhError(RuntimeError):
    """A failed `gh` call, carrying the HTTP status when the API gave one.

    The status is what separates "this policy does not exist" (404, an answer)
    from "I could not ask" (401/403/network/no binary). Everything downstream
    depends on telling those apart.
    """

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _gh(args: list[str]) -> str:
    """Run `gh` and return stdout, or raise GhError.

    `gh` missing and `gh` hanging are the two failures a user actually hits, and
    neither raises CalledProcessError — they raise FileNotFoundError and
    TimeoutExpired, which would escape as a traceback and exit 1 instead of the
    documented exit 2.
    """
    try:
        proc = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
    except FileNotFoundError as exc:
        raise GhError(
            "`gh` is not installed or not on PATH. Install the GitHub CLI and "
            "run `gh auth login` — reading branch protection needs your own auth."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise GhError(f"`gh {' '.join(args)}` timed out after 60s.") from exc
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        found = _HTTP_STATUS_RE.search(stderr)
        raise GhError(
            f"`gh {' '.join(args)}` failed: {stderr}",
            int(found.group(1)) if found else None,
        )
    return proc.stdout


def resolve_repo(project_root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(project_root), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"could not run `git` to resolve the origin remote: {exc}") from exc
    url = out.stdout.strip()
    if not url:
        raise RuntimeError("no `origin` remote — cannot resolve the repository")
    # `rsplit` on a string that does not contain the separator returns the WHOLE
    # string, so an SSH alias (`gh:owner/repo`) or a GitHub Enterprise host would
    # silently yield the raw URL as the "slug" and get sent to `gh api repos/…`.
    # Say what is wrong instead of guessing at a repository identity.
    if "github.com" not in url:
        raise RuntimeError(
            f"`origin` is {url!r}, which is not a github.com remote — this "
            f"producer reads GitHub rulesets. Pass `--repo owner/name` if the "
            f"repository is reachable under a different remote URL."
        )
    slug = url.rsplit("github.com", 1)[-1].lstrip(":/")
    slug = slug[:-4] if slug.endswith(".git") else slug
    if not _SLUG_RE.match(slug):
        raise RuntimeError(
            f"could not read an owner/name out of `origin` ({url!r}) — got "
            f"{slug!r}. Pass `--repo owner/name` explicitly."
        )
    return slug


def resolve_default_branch(repo: str) -> str:
    """The repo's default branch — and proof the repo itself is readable.

    Called before any policy lookup so a later 404 is unambiguous. Without this
    proof, a typo'd slug 404s on every endpoint, which would read as "this repo
    protects nothing" and report every check as unenforced: a producer crying
    wolf at maximum volume.
    """
    meta = json.loads(_gh(["api", f"repos/{repo}"]))
    branch = (meta or {}).get("default_branch")
    if not branch:
        raise GhError(f"`{repo}` returned no default_branch")
    return str(branch)


def fetch_configured_contexts(repo: str, branch: str) -> list[str]:
    """Contexts the host will actually block on for ``branch``.

    Two mechanisms, because a repo may use either or both. **Readability is
    tracked separately from content:** a source that answers "no policy here" has
    been read, and an empty result is a finding rather than a failure. Only a
    branch on which NEITHER mechanism could be consulted raises.

    Callers must have proven the repo readable first (``resolve_default_branch``)
    — that is what licenses reading a 404 as "no such policy".
    """
    contexts: list[str] = []
    read_any = False
    problems: list[str] = []

    # Rulesets: ask the host which ones APPLY to this ref rather than walking
    # /rulesets ourselves. GitHub evaluates the ref conditions, so a ruleset
    # scoped to release/* cannot leak its contexts onto main and be reported as
    # a phantom — and this projection needs no admin scope.
    try:
        rules = json.loads(_gh(["api", f"repos/{repo}/rules/branches/{branch}"]))
        read_any = True
        for rule in rules if isinstance(rules, list) else []:
            if not isinstance(rule, dict) or rule.get("type") != "required_status_checks":
                continue
            params = rule.get("parameters") or {}
            for chk in params.get("required_status_checks") or []:
                ctx = (chk or {}).get("context") if isinstance(chk, dict) else None
                if ctx:
                    contexts.append(str(ctx))
    except GhError as exc:
        if exc.status == 404:
            read_any = True  # no ruleset governs this ref
        else:
            problems.append(f"rulesets: {exc}")
    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        problems.append(f"rulesets: unparseable response ({exc})")

    # Classic branch protection — the pre-ruleset mechanism, still in use.
    try:
        prot = json.loads(_gh(["api", f"repos/{repo}/branches/{branch}/protection"]))
        read_any = True
        checks = ((prot or {}).get("required_status_checks") or {}).get("contexts") or []
        contexts.extend(str(c) for c in checks if c)
    except GhError as exc:
        if exc.status == 404:
            read_any = True  # "Branch not protected" — an answer, not a failure
        else:
            problems.append(f"branch protection: {exc}")
    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        problems.append(f"branch protection: unparseable response ({exc})")

    if not read_any:
        raise RuntimeError(
            f"could not read the required-status-check configuration for "
            f"{repo}@{branch}: " + "; ".join(problems)
        )
    return contexts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Required-check drift producer")
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--repo", default=None, help="owner/name (default: from origin)")
    ap.add_argument("--branch", default=None,
                    help="branch whose policy to read (default: the repo's default branch)")
    ap.add_argument("--json", action="store_true", help="print the comparison")
    ap.add_argument("--no-file", action="store_true", help="compare, file nothing")
    args = ap.parse_args(argv)

    root = Path(args.project_root).resolve()
    try:
        repo = args.repo or resolve_repo(root)
        # Always resolved, even when --branch is given: it proves the repo is
        # readable, which is what makes a later 404 mean "no policy" rather
        # than "wrong slug".
        default_branch = resolve_default_branch(repo)
        branch = args.branch or default_branch
        configured = fetch_configured_contexts(repo, branch)
    except (RuntimeError, json.JSONDecodeError) as e:  # GhError is a RuntimeError
        print(f"[required-checks] {e}", file=sys.stderr)
        return 2

    target = f"{repo}@{branch}"
    result = compare_required_checks(all_workflow_check_names(root), configured)
    if args.json:
        print(json.dumps({"repo": repo, "branch": branch, **result}, indent=2))
    else:
        print(render_drift(result, target))

    if result["in_sync"] or args.no_file:
        return 0

    append_triage_item_idempotent(
        root,
        source="required-checks",
        severity="high" if result["phantom"] else "medium",
        kind="improvement",
        title="must-pass check set does not match the checks the project has",
        # Keyed on repo@branch: two branches with different policies are two
        # findings, and folding them onto one key would hide the second.
        detail=render_drift(result, target),
        dedup_key=dedup_key(result, target),
        match_commit=False,
        window_seconds=None,
        # Routed, not hardcoded. `to_outbox=True` was harmless while a human typed
        # this on main; wiring it to a SessionStart hook
        # (iterate-2026-08-05-wire-local-guard-scripts) made it load-bearing,
        # because `resolve_project_root` is cwd-based and a session opened inside
        # `.worktrees/<slug>` resolves the WORKTREE. The outbox there is gitignored,
        # `sweep_outbox_to_branch` only ever reads the MAIN root's outbox, and the
        # tree is deleted after the PR merges — so the finding was written to a
        # buffer nothing drains and then destroyed. Every sibling producer routes
        # conditionally (`check_drift`, `triage_add`, `github_triage/consumer`,
        # `_triage_bundle`); on an iterate branch that means the tracked log, which
        # F6 stages and which ships in the PR.
        to_outbox=should_route_to_outbox(root),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
