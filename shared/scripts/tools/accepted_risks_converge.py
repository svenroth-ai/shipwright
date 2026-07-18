"""The ``converge`` subcommand — resolve the register onto the live surface.

Split out of ``accepted_risks_cli`` to keep both files under the 300-LOC cap;
the CLI owns argument dispatch, this module owns the command. Everything
decidable without a network lives in ``alert_convergence`` / ``alert_match``,
which is what the tests actually exercise.

**Read-only is the default and mutation is a separate act.** No scheduled job
may hold the authority to mass-dismiss security alerts — an automated
reconciler is the shape that produced webui #285 in the first place, turning
"accepted once, by a person, with a due date" into "whatever the register said
at 3am". CI's job is to *fail* when register and reality disagree, which
Phase 1 already does.
"""

from __future__ import annotations

import sys
from pathlib import Path

import alert_convergence
import alert_match
import github_api
import github_code_scanning
from accepted_risks import load_register, register_exists, today_utc


def _open_security_items(project_root: Path) -> tuple[list[dict], str | None]:
    """``(items, unreadable_reason)`` — open per-finding local-scanner items.

    These are the only triage items an acceptance may retract: they are keyed
    ``{tool}:{check_id}:{file}:{line}``, the same shape as the alert key. The
    ``gh-security:{owner}/{repo}`` action-unit is deliberately NOT touched — it
    is a repo-wide aggregate, so dismissing it because one alert was accepted
    would silence every security finding in the repo.

    An unreadable store returns a REASON, not an empty list. Collapsing the two
    would let "I could not look" render as "there was nothing there", and the
    run would print `converged` while matching items sat unreconciled — the
    same silent narrowing this tool refuses everywhere else.
    """
    try:
        import triage  # noqa: PLC0415 - absent in a bare temp test root
        items = triage.read_all_items(project_root)
    except FileNotFoundError:
        return [], None  # no store yet is genuinely "no items", not a failure
    except Exception as exc:  # noqa: BLE001 - surfaced, never swallowed
        return [], f"{type(exc).__name__}: {exc}"
    return [
        i for i in items
        if i.get("source") == "security" and i.get("status") == "triage"
    ], None


def build_plan(project_root: Path, *, now=None):
    """Resolve the live convergence plan as ``(owner_repo, Plan)``.

    Repository identity comes from the checked-out tree's ``origin`` remote,
    never from ``gh``'s cwd-derived placeholder substitution — otherwise a
    mutation could land on a different repository than the register that
    authorised it. A failed alert fetch RAISES rather than yielding an empty
    plan: an incomplete listing must never read as "converged".
    """
    slug = github_code_scanning.validate_owner_repo(
        github_api.owner_repo(project_root)
    )
    alerts = []
    for state in github_code_scanning.STATES:
        page = github_code_scanning.list_alerts(slug, state)
        if page is None:
            raise github_code_scanning.RepoIdentityError(
                f"could not list {state} code-scanning alerts for {slug} — "
                "refusing to plan against an incomplete listing"
            )
        alerts.extend(a for a in map(alert_match.alert_from_api, page) if a)
    items, unreadable = _open_security_items(project_root)
    plan = alert_convergence.plan_convergence(
        load_register(project_root), alerts,
        now=now or today_utc(), triage_items=items,
    )
    plan.triage_unreadable = unreadable
    return slug, plan


def cmd_converge(project_root: Path, *, apply: bool = False) -> int:
    # NOTE: an absent register is deliberately NOT an early exit. Deleting the
    # register is the same loss of authority as an entry expiring, so the alerts
    # this tool dismissed must still be reopened — an early return would leave
    # them suppressed forever with nothing left in the repo to explain why.
    slug, plan = build_plan(project_root)
    if not register_exists(project_root):
        print(f"accepted-risks: no register at {project_root} - "
              "reopening anything this tool previously dismissed.")
    n = sum(
        1 for e in load_register(project_root)
        if e.target == alert_convergence.TARGET_GITHUB_DISMISSAL
    )
    print(
        f"accepted-risks converge: {slug}, {n} github-dismissal "
        f"entr{'y' if n == 1 else 'ies'}."
    )
    for line in alert_convergence.format_untouched(plan):
        print(line)

    problems = alert_convergence.format_plan(plan)
    if not problems:
        print("  converged - the security surface matches the register.")
        return 0
    print("\nAccepted-risk surface divergence:\n")
    for problem in problems:
        print(problem)
    if not apply:
        print(
            "\nRead-only. To act on this:\n"
            "  uv run shared/scripts/tools/accepted_risks_cli.py converge "
            "--project-root . --apply"
        )
        return 1
    return apply_plan(slug, plan, project_root)


def apply_plan(slug: str, plan, project_root: Path) -> int:
    """Execute the plan. Only ever reached under an explicit ``--apply``."""
    print("\nApplying:\n")
    failures = 0
    for entry, alert in plan.to_dismiss:
        ok, msg = github_code_scanning.dismiss_alert(
            slug, alert.number,
            reason=alert_match.dismiss_reason_for(entry),
            comment=alert_match.dismissal_comment(entry),
        )
        failures += not ok
        print(f"  {'dismissed' if ok else 'FAILED   '} #{alert.number} {msg[:120]}")
    for _entry_id, alert in plan.to_reopen:
        ok, msg = github_code_scanning.reopen_alert(slug, alert.number)
        failures += not ok
        print(f"  {'reopened ' if ok else 'FAILED   '} #{alert.number} {msg[:120]}")
    failures += _apply_triage(plan, project_root)
    return 1 if failures else 0


def _apply_triage(plan, project_root: Path) -> int:
    if not plan.triage_dismiss:
        return 0
    from triage import mark_status  # noqa: PLC0415 - absent in a bare test root
    failures = 0
    for entry, item in plan.triage_dismiss:
        try:
            mark_status(
                project_root, item["id"], new_status="dismissed",
                by=alert_convergence.TRIAGE_DISMISSER,
                reason=alert_convergence.TRIAGE_REASON,
            )
            print(f"  dismissed triage {item['id']} (accepted by {entry.id})")
        except Exception as exc:  # noqa: BLE001 - fail-soft per item
            failures += 1
            print(f"  FAILED   triage {item.get('id')}: {exc}", file=sys.stderr)
    return failures
