#!/usr/bin/env python3
"""Is `main` healthy — and if not, everything needed to repair it, in one JSON.

The diagnosis package of the `main` self-heal (FR-01.19,
iterate-2026-07-28-main-self-heal). The decisions live in `lib.main_health` +
`lib.main_health_diagnosis`, which are pure; the host calls live in
`tools.main_health_gh`. This file is the assembly and the exit-code contract.

**The green path is ONE API call.** A single `gh run list --branch main` answers
the status *and* feeds attribution; the log, PR-association and claim calls only
happen once something is red. That is what makes it affordable at the two points
where an iterate already touches `main` (SKILL.md §B1a and F11).

**It fails honestly.** `gh` missing, a query that errors, a retrieval window
that ran out — each is reported as itself in `unknown[]` with a named source. A
health check that reads "could not determine" as "green" is worse than none,
because it is believed.

**The result is an observation, not a lock.** `origin/main` can advance while
this runs; `tip_sha` and `observed_at` say which moment is being described, and a
run for a SHA outside the local series raises `main_advanced_during_check`.

Exit codes: ``0`` green · ``2`` red · ``3`` running · ``4`` unknown ·
``5`` escalate (a finding-class workflow is red — a card, never an auto-repair).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_TOOLS_ROOT = Path(__file__).resolve().parent
if str(_TOOLS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_TOOLS_ROOT.parent))

from lib import main_health as mh  # noqa: E402
from lib import main_health_diagnosis as dx  # noqa: E402
from tools import main_health_gh as gh  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _note(report: dict, source: str, reason: str) -> None:
    report["unknown"].append({"source": source, "reason": str(reason)[:300]})


def build_report(cwd: Path, args) -> dict:
    """Assemble the package. Every host failure becomes a named `unknown`."""
    limit = mh.run_limit_for(args.window)
    report: dict = {
        "version": 1,
        "observed_at": _now(),
        "note": "an observation of the branch at tip_sha, not a lock on it",
        "window": args.window,
        "run_limit": limit,
        "status": "unknown",
        "tip_sha": None,
        "unknown": [],
    }

    try:
        commits = gh.commit_series(cwd, f"origin/{args.branch}", args.window)
    except gh.ShellError as exc:
        _note(report, "git", exc)
        return report
    report["tip_sha"] = commits[0]["sha"] if commits else None

    try:
        runs = gh.list_runs(cwd, args.branch, limit)
    except gh.ShellError as exc:
        _note(report, "gh", exc)
        return report

    classified = mh.classify(
        commits=commits, runs=runs, default_branch=args.branch,
        workflow_files_present=gh.workflow_files(cwd),
    )
    report["unknown"].extend(classified["unknown"])
    report["status"] = classified["status"]
    report["findings"] = classified["findings"]
    report["runs_fetched"] = len(runs)
    report["saturated"] = len(runs) >= limit

    selected = classified["selected_runs"]
    oldest_run_sha = next(
        (c["sha"] for c in reversed(commits)
         if any((w.name, c["sha"]) in selected for w in mh.MONITORED_WORKFLOWS)),
        None,
    )
    report["attribution"] = mh.attribute(
        commits, classified["verdicts"],
        saturated=report["saturated"], oldest_run_sha=oldest_run_sha,
    )

    report["failure"] = None
    report["candidate_partners"] = None
    report["repair_in_flight"] = None
    bad = report["attribution"]["first_bad_commit"]
    if bad:
        _diagnose(cwd, args, report, bad, selected)

    partners = report.get("candidate_partners") or {}
    # The finding-class workflows are evaluated on the TIP, so a card about one
    # is keyed on the tip — not on `first_bad_commit`, which is about the CI
    # overlap and is often absent here. Keying on a missing sha produced
    # `main-red:Security Scan:` with an empty identity, which is not idempotent
    # at all: every run would file another card.
    report["escalate"] = dx.escalation(
        bad_sha=(bad or {}).get("sha") or report.get("tip_sha"),
        finding_reds=[f["workflow"] for f in classified["findings"]
                      if f["state"] == "fail"],
        partner_count=(len(partners["commits"])
                       if partners.get("commits") is not None else None),
        failed_attempts=(report.get("repair_in_flight") or {}).get(
            "failed_attempts", 0),
    )
    return report


def _diagnose(cwd: Path, args, report: dict, bad: dict, selected: dict) -> None:
    """The red-path calls. Each failure is recorded, never raised past here."""
    ci = next(w for w in mh.MONITORED_WORKFLOWS if w.decides_health)
    run = selected.get((ci.name, bad["sha"])) or {}
    run_id = run.get("databaseId")

    steps, log_text = [], None
    if run_id:
        try:
            steps = gh.failed_steps(cwd, run_id, mh.FAIL_CONCLUSIONS)
        except gh.ShellError as exc:
            _note(report, "gh run view --json jobs", exc)
        try:
            log_text = gh.failed_log(cwd, run_id)
        except gh.ShellError as exc:
            _note(report, "gh run view --log-failed", exc)
    report["failure"] = {
        "run_id": run_id,
        "run_url": run.get("url"),
        "workflow": ci.name,
        "failed_steps": steps,
        **dx.reduce_failure_log(log_text, max_lines=args.log_lines),
    }

    try:
        owner, name = gh.repo_slug(cwd)
    except gh.ShellError as exc:
        _note(report, "gh repo view", exc)
        return

    base_sha, pr_number, reason = gh.pr_for_commit(
        cwd, owner, name, bad["sha"], bad.get("subject", "")
    )
    if base_sha:
        try:
            between = gh.commits_between(cwd, base_sha, bad["sha"])
        except gh.ShellError as exc:
            between, reason = None, str(exc)[:120]
        else:
            reason = None if between is not None else "base_not_ancestor"
        report["candidate_partners"] = {
            **mh.candidate_partners(base_sha=base_sha, commits_between=between,
                                    reason_code=reason),
            "pr_number": pr_number,
        }
    else:
        report["candidate_partners"] = mh.candidate_partners(
            base_sha=None, commits_between=None,
            reason_code=reason or "direct_push",
        )

    try:
        prs = gh.list_prs(cwd)
        refs = gh.list_branch_refs(cwd, owner, name)
    except gh.ShellError as exc:
        _note(report, "gh pr list", exc)
        return
    report["repair_in_flight"] = dx.match_repair_claim(
        bad["sha"], prs=prs, refs=refs, repo_owner=owner,
        now=report["observed_at"], stale_minutes=args.claim_stale_minutes,
        trusted_authors=args.trusted_author or None,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Diagnose the health of the shared branch"
    )
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--window", type=int, default=mh.DEFAULT_COMMIT_WINDOW,
                    help="commits walked back from the tip when attributing")
    ap.add_argument("--log-lines", type=int, default=40)
    ap.add_argument("--claim-stale-minutes", type=float, default=120.0)
    ap.add_argument("--trusted-author", action="append", default=[],
                    help="narrow claims further than the non-fork rule (opt-in)")
    args = ap.parse_args(argv)

    report = build_report(Path(args.project_root).resolve(), args)
    print(json.dumps(report, indent=2))
    if report["status"] != "green":
        print(
            f"main is {report['status']} at {report.get('tip_sha') or '?'} — see "
            "the iterate skill's references/main-repair.md for what to do with "
            "this package.",
            file=sys.stderr,
        )
    return {"green": 0, "red": 2, "running": 3, "escalate": 5}.get(
        report["status"], 4)


if __name__ == "__main__":
    raise SystemExit(main())
