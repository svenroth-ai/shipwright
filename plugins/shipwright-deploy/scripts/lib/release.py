#!/usr/bin/env python3
"""The coded release entry point: gate + deploy + smoke + auto-rollback.

FR-01.08 criteria 1 and 5 were, until this module, pure SKILL.md agent
prose: an ``AskUserQuestion`` confirmation before deploying with failing
tests, and an agent reading a failed smoke-test JSON and deciding to invoke
``rollback.py``. Neither had a coded artifact a test could drive end to end
— this module is that artifact.

    uv run release.py --env-name <name> --repo-url <url> --branch <branch> \\
        --project-root <path> [--confirm-failing-tests] \\
        [--smoke-url <url>] [--profile <deploy-profile.json>]

Criterion 1 (refuse until confirmed): ``evaluate_test_gate`` (``test_gate.py``
— the same oracle ``validate-deploy.py`` reads) is checked BEFORE any host is
contacted. A failing/missing gate without ``--confirm-failing-tests`` refuses
here, structurally — ``jelastic_client.deploy_from_git`` is never called.

Criterion 5 (auto-rollback on smoke failure): when ``--smoke-url`` is given,
a failed post-deploy smoke check automatically calls ``rollback.rollback_git``
back to the ref that was live immediately before this deploy, recorded with
``invocation="auto"`` — the same audit trail a manual ``rollback.py --rollback``
invocation writes, so ``deploy_checks`` reconciliation cannot tell the two
apart except by that field, which is exactly the point: this closes the gap
where the audit trail had an ``auto`` vocabulary that nothing ever populated.

Omitting ``--smoke-url`` skips smoke verification and auto-rollback entirely,
matching a bare ``jelastic_client.py deploy`` today — this module only adds
behaviour, it does not require it.

Known limitations (branch-name-not-commit rollback granularity, no
cross-invocation lock per ``env_name``): see
``skills/deploy/references/non-interactive-release.md`` — recorded there
rather than fixed here, because each needs a materially bigger design than
this unit's scope (doubt review, iterate-2026-09-16-deploy-ac02-ac05-coded-
gates).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import data_drift
# Shared with rollback.py — see hosting.py's own docstring for why this must
# stay one implementation, not two.
from hosting import client as _client
from hosting import hosting_errors as _hosting_errors
from release_rollback import verify_and_maybe_roll_back
from rollback_report import canonical_ref
from test_gate import evaluate_test_gate

# release_rollback's own import (above) already put shared/scripts on
# sys.path — deploy_profile lives there, needed here only to load --profile.
import deploy_profile  # noqa: E402

EXIT_RELEASED = 0
EXIT_NOT_RELEASED = 1
EXIT_REFUSED = 2

__all__ = ["EXIT_NOT_RELEASED", "EXIT_REFUSED", "EXIT_RELEASED", "main", "release"]


def release(
    env_name: str,
    repo_url: str,
    branch: str,
    *,
    target: str,
    context: str = "ROOT",
    project_root: Path | str,
    confirm_failing_tests: bool = False,
    confirm_prod: bool = False,
    smoke_url: str | None = None,
    smoke_timeout: int | None = None,
    smoke_poll_interval: int | None = None,
    smoke_max_wait: int | None = None,
    smoke_health_path: str | None = None,
    profile: dict | None = None,
    migrations_dir: str = data_drift.DEFAULT_MIGRATIONS_DIR,
) -> dict:
    """Run the gated release. Returns a result dict; never raises
    ``JelasticError`` — a host failure is reported the same as any other
    outcome so a caller reading the return value never has to also wrap this
    in its own try/except to know what happened.

    ``target`` is required, no default (mirrors ``rollback.py``'s own
    ``--invocation``): a silently-defaulted "dev" would let a caller reach
    PROD by omission. ``target="prod"`` without ``confirm_prod=True`` refuses
    before any host contact — the constitution's PROD-is-ASK-FIRST invariant
    holds for this agent-free entry point too; this module cannot itself ask
    a question, so something upstream (a human-gated CI approval, a campaign
    operator) must have already produced that confirmation.
    """
    project_root = Path(project_root)

    if target not in ("dev", "prod"):
        return {
            "released": False,
            "refused": True,
            "reason": f"target must be 'dev' or 'prod', got {target!r}",
        }
    if target == "prod" and not confirm_prod:
        return {
            "released": False,
            "refused": True,
            "reason": (
                "PROD releases require confirm_prod=True (constitution: PROD "
                "is ASK-FIRST regardless of invocation path) — this module "
                "cannot ask a question itself, so the confirmation must come "
                "from whatever upstream process invoked it"
            ),
        }

    test_gate, test_gate_error = evaluate_test_gate(project_root, confirm_failing_tests)
    if test_gate_error is not None:
        return {
            "released": False,
            "refused": True,
            "test_gate": test_gate,
            "reason": test_gate_error,
        }

    client = _client()
    errors = _hosting_errors()

    # Read the ref that is live BEFORE this deploy — the only thing an
    # automatic rollback can safely put back. A brand-new environment (no
    # VCS project yet) has no such ref; auto-rollback is then skipped
    # rather than guessing, exactly like a manual rollback with no prior
    # deploy would have nothing to restore either.
    previous_ref: str | None = None
    try:
        previous_project = client.get_vcs_project(env_name, context)
    except errors:
        previous_project = None
    else:
        previous_ref = canonical_ref(previous_project.get("branch"))

    try:
        deploy_result = client.deploy_from_git(env_name, repo_url, branch, context)
    except errors as exc:
        return {
            "released": False,
            "refused": False,
            "test_gate": test_gate,
            "failure_stage": "deploy",
            "reason": f"deploy failed: {exc}",
        }

    result: dict = {
        "released": True,
        "refused": False,
        "test_gate": test_gate,
        "deploy": deploy_result,
        "smoke_checked": False,
    }

    if smoke_url is None:
        return result

    return verify_and_maybe_roll_back(
        result, env_name, branch, previous_ref,
        context=context, project_root=project_root, migrations_dir=migrations_dir,
        profile=profile, smoke_url=smoke_url, smoke_timeout=smoke_timeout,
        smoke_poll_interval=smoke_poll_interval, smoke_max_wait=smoke_max_wait,
        smoke_health_path=smoke_health_path,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gated release: test-gate + deploy + smoke + auto-rollback")
    parser.add_argument("--env-name", required=True)
    parser.add_argument("--repo-url", default="")
    parser.add_argument("--branch", default="main")
    parser.add_argument(
        "--target", required=True, choices=["dev", "prod"],
        help="Required, no default: a silently-defaulted target could route a "
             "PROD deploy through the same path as dev without anyone "
             "choosing it (constitution: PROD is ASK-FIRST regardless of "
             "invocation path).",
    )
    parser.add_argument(
        "--confirm-prod", action="store_true",
        help="Required alongside --target prod. This module has no agent in "
             "the loop to ask, so the confirmation must come from whatever "
             "upstream process (human-gated CI step, campaign operator) "
             "invoked it.",
    )
    parser.add_argument("--context", default="ROOT")
    parser.add_argument(
        "--project-root", required=True,
        help="Working tree used for the test-gate read, the stored-data drift "
             "check on an auto-rollback, and the rollback audit trail.",
    )
    parser.add_argument(
        "--confirm-failing-tests", action="store_true",
        help="A person has explicitly confirmed releasing despite failing/missing tests",
    )
    parser.add_argument(
        "--smoke-url", default=None,
        help="Post-deploy liveness URL. Omit to skip smoke verification and auto-rollback.",
    )
    parser.add_argument("--smoke-timeout", type=int, default=None)
    parser.add_argument("--smoke-poll-interval", type=int, default=None)
    parser.add_argument("--smoke-max-wait", type=int, default=None)
    parser.add_argument("--smoke-health-path", default=None)
    parser.add_argument("--profile", help="Path to the target's deploy profile JSON")
    parser.add_argument("--migrations-dir", default=data_drift.DEFAULT_MIGRATIONS_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    profile = None
    if args.profile:
        try:
            profile = deploy_profile.load_profile(args.profile)
        except deploy_profile.ProfileError as exc:
            print(json.dumps({"released": False, "refused": True, "reason": str(exc)}, indent=2))
            return EXIT_REFUSED

    result = release(
        args.env_name, args.repo_url, args.branch,
        target=args.target,
        context=args.context,
        project_root=args.project_root,
        confirm_failing_tests=args.confirm_failing_tests,
        confirm_prod=args.confirm_prod,
        smoke_url=args.smoke_url,
        smoke_timeout=args.smoke_timeout,
        smoke_poll_interval=args.smoke_poll_interval,
        smoke_max_wait=args.smoke_max_wait,
        smoke_health_path=args.smoke_health_path,
        profile=profile,
        migrations_dir=args.migrations_dir,
    )

    print(json.dumps(result, indent=2))

    if result.get("refused"):
        return EXIT_REFUSED
    if not result.get("released"):
        return EXIT_NOT_RELEASED
    return EXIT_RELEASED


if __name__ == "__main__":
    sys.exit(main())
