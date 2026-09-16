#!/usr/bin/env python3
"""Post-deploy smoke verification and the coded auto-rollback trigger
(FR-01.08 criterion 5), split out of ``release.py`` once that module crossed
the 300-line guideline (iterate-2026-09-16-deploy-ac02-ac05-coded-gates).

This is the self-contained "was the deploy actually healthy, and if not, was
it safe to automatically roll back" decision — distinct from ``release()``'s
own gate-then-deploy sequencing, which is what stays in ``release.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import rollback_audit
from rollback import rollback_git
from rollback_report import canonical_ref

# Reach the shared tree the same way rollback.py does: two levels above the
# plugin root (scripts/lib/this-file -> parents[2] = plugin root -> .parent.parent
# = the root holding both `plugins/` and `shared/`).
_SHARED_SCRIPTS = Path(__file__).resolve().parents[2].parent.parent / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import deploy_profile  # noqa: E402
import smoke_test  # noqa: E402
from lib.file_lock import LockTimeout  # noqa: E402

__all__ = ["verify_and_maybe_roll_back"]


def verify_and_maybe_roll_back(
    result: dict,
    env_name: str,
    branch: str,
    previous_ref: str | None,
    *,
    context: str,
    project_root: Path,
    migrations_dir: str,
    profile: dict | None,
    smoke_url: str,
    smoke_timeout: int | None,
    smoke_poll_interval: int | None,
    smoke_max_wait: int | None,
    smoke_health_path: str | None,
) -> dict:
    """Post-deploy smoke check (criterion 3/4) and, on failure, the coded
    auto-rollback trigger (criterion 5). Called by ``release()`` after a
    successful deploy — this is the block that answers "was the smoke URL
    and/or --smoke-* flags misconfigured?" separately from "did the deploy
    itself work?".
    """
    try:
        policy = deploy_profile.smoke_policy(
            profile,
            timeout=smoke_timeout,
            poll_interval=smoke_poll_interval,
            max_wait=smoke_max_wait,
            health_path=smoke_health_path,
        )
        smoke_result = smoke_test.run_smoke_test(
            smoke_url, policy.timeout, policy.health_path,
            poll_interval=policy.poll_interval,
            max_wait=policy.max_wait,
            policy_source=policy.source,
        )
    except ValueError as exc:
        # A bad --smoke-timeout/--smoke-max-wait/--smoke-poll-interval is a
        # caller mistake discovered only after the deploy already happened
        # (the policy is only resolved once smoke verification is reached) —
        # reported the same structured way every other failure here is,
        # never an uncaught traceback.
        result["released"] = False
        result["failure_stage"] = "smoke_config"
        result["reason"] = f"invalid smoke-test configuration: {exc}"
        return result

    result["smoke_checked"] = True
    result["smoke"] = smoke_result

    if smoke_result["success"]:
        return result

    result["released"] = False
    result["failure_stage"] = "smoke"

    # A single fixed-timeout attempt (no polling deadline configured, via
    # neither --profile nor --smoke-max-wait) is not a reliable enough signal
    # to trigger a host mutation on its own — smoke_test.py's own docstring:
    # "a fifteen-second start-up gets reported as a failed release and
    # triggers a rollback nobody needed" (doubt review). The failure is still
    # reported; auto-rollback just isn't attempted on that signal alone.
    if policy.max_wait is None:
        result["rollback_triggered"] = False
        result["rollback_skipped_reason"] = (
            "no polling deadline configured (--profile or --smoke-max-wait) "
            "— a single-attempt smoke result is not trusted to trigger an "
            "automatic rollback on its own"
        )
        return result

    # previous_ref is already canonical (read via canonical_ref by the
    # caller) — only branch needs normalizing here.
    if previous_ref is None or previous_ref == canonical_ref(branch):
        result["rollback_triggered"] = False
        result["rollback_skipped_reason"] = (
            "no distinct previous ref at branch-name granularity — this "
            "deploy repinned no branch, so there is nothing this module can "
            "name to roll back to (see 'Known limitations' in "
            "non-interactive-release.md); a live regression from this "
            "deploy's new commits may still be unrestored"
        )
        return result

    rollback_result = rollback_git(
        env_name, previous_ref,
        context=context,
        project_root=project_root,
        migrations_dir=migrations_dir,
        profile=profile,
    )
    # Guarded exactly like rollback.py's own main(): a lock timeout or
    # unwritable audit dir must never crash an auto-rollback that already
    # mutated the host — it writes the durable degraded marker instead, so
    # deploy_checks.check_manual_rollback_proves_alive fails closed rather
    # than reading the missing record as "no rollback happened".
    try:
        rollback_audit.record(project_root, rollback_result, invocation="auto")
    except (LockTimeout, OSError) as exc:
        print(f"WARNING: rollback audit trail not recorded: {exc}", file=sys.stderr)
        rollback_audit.record_degraded(project_root, invocation="auto", reason=str(exc))

    result["rollback_triggered"] = True
    result["rollback"] = rollback_result

    # A confirmed ref pin is not the same claim as "the restored code is
    # actually serving traffic" — re-check liveness against the ref we just
    # restored, rather than leaving that gap for a human to notice later
    # (doubt review).
    if rollback_result.get("success"):
        recheck = smoke_test.run_smoke_test(
            smoke_url, policy.timeout, policy.health_path,
            poll_interval=policy.poll_interval,
            max_wait=policy.max_wait,
            policy_source=policy.source,
        )
        result["rollback_health_check"] = recheck
        result["rollback_verified_healthy"] = recheck["success"]

    return result
