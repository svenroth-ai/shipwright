#!/usr/bin/env python3
"""Rollback operations for shipwright-deploy.

Git strategy (DEV): pin the VCS project to a previous ref, then update.
Clone strategy (PROD): stop the failed env in favour of a backup clone.

Every claim this module makes has to be earned. It reports a version only if
that version was actually sent to the host; it refuses to restore code over
stored data that has already moved on; and when the way back itself fails it
names the state and stops rather than continuing unattended. The payload
vocabulary and the exit codes (0 done / 1 refused, nothing touched / 3 started
and unfinished, STOP) live in ``rollback_report``.

    uv run rollback.py --env-name <name> --strategy git --target-ref <tag>
    uv run rollback.py --env-name <name> --strategy clone --clone-name <backup>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import data_drift
import rollback_audit
# Shared with release.py — see hosting.py's own docstring for why this must
# stay one implementation, not two.
from hosting import client as _client
from hosting import hosting_errors as _hosting_errors
from rollback_report import (
    EXIT_HALT,
    EXIT_OK,
    EXIT_REFUSED,
    HostingError,
    base,
    canonical_ref,
    exit_code,
    halted,
    refused,
)

# Reach the shared tree the same way every hook does: two levels above the
# plugin root, which holds in the dev repo and in the plugin cache alike.
# Intended target: <repo-or-cache-root>/shared/scripts. The chain reads
# scripts/lib/this-file -> parents[2] = the plugin root -> .parent.parent = the
# root that holds both `plugins/` and `shared/`. An off-by-one here resolves
# silently to the wrong directory, so test_smoke_e2e_cli / test_rollback_e2e_cli
# run this module as a subprocess from an unrelated cwd to prove it resolves.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[2].parent.parent / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import deploy_profile  # noqa: E402
from lib.file_lock import LockTimeout  # noqa: E402

__all__ = [
    "EXIT_HALT", "EXIT_OK", "EXIT_REFUSED", "HostingError",
    "main", "rollback_clone", "rollback_git",
]


def _verify_ref(client, env_name: str, context: str, target_ref: str,
                errors: tuple) -> tuple[str, str | None, str | None]:
    """Read the pin back. Returns (verdict, verification_error, live_ref)."""
    try:
        live = canonical_ref(client.get_vcs_project(env_name, context).get("branch"))
    except errors as exc:
        return "unconfirmed", f"read-back unavailable: {exc}", None
    if live is None:
        return "unconfirmed", f"read-back returned no branch for context {context!r}", None
    if live == canonical_ref(target_ref):
        return "confirmed", None, live
    return "mismatch", None, live


def rollback_git(
    env_name: str,
    target_ref: str,
    *,
    context: str = "ROOT",
    project_root: Path | str | None = None,
    migrations_dir: str = data_drift.DEFAULT_MIGRATIONS_DIR,
    ack_data_drift: bool = False,
    override_reason: str | None = None,
    profile: dict | None = None,
) -> dict:
    """Put ``env_name`` back onto ``target_ref`` — or say why it is not there."""
    common: dict = {"target_ref": target_ref}

    if not data_drift.is_valid_ref(target_ref):
        return refused(
            "git", env_name,
            f"{target_ref!r} is not a valid git ref name, so it was never sent anywhere",
            **common,
        )

    drift, refusal = data_drift.gate(
        project_root, target_ref, migrations_dir,
        strategy=deploy_profile.data_rollback_strategy(profile),
        target_id=(profile or {}).get("target_id"),
        ack=ack_data_drift,
    )
    common["data_drift"] = drift
    if refusal:
        return refused("git", env_name, refusal, **common)

    # FR-01.08 criterion 5: the stored-data gate OFFERS `--ack-data-drift` as
    # the way past its own refusal (the message `gate()` builds above names
    # it); overriding that offer needs a written record. `ack_data_drift`
    # only MATTERS here when the report itself flagged something — an ack
    # passed against a clean/not-applicable report overrode nothing, so no
    # reason is demanded.
    overrode_something = ack_data_drift and drift["status"] in ("drifted", "unknown")
    if overrode_something and not (override_reason or "").strip():
        return refused(
            "git", env_name,
            "an override needs a written reason: stored data was flagged "
            f"({drift['status']!r}) and --ack-data-drift was used without "
            "--override-reason — nothing was overridden without a record",
            **common,
        )
    common["override_reason"] = override_reason if overrode_something else None

    errors = _hosting_errors()
    client = _client()

    # Read before writing: `editproject` may be PUT-shaped, so pinning a sparse
    # payload could clear the repository URL and credentials.
    try:
        project = client.get_vcs_project(env_name, context)
    except errors as exc:
        return refused(
            "git", env_name,
            f"the current VCS project config could not be read ({exc}); pinning a "
            "partial config could wipe the repository URL or credentials",
            last_attempted="environment/vcs/rest/getprojects",
            what_it_found=str(exc),
            **common,
        )

    previous_ref = canonical_ref(project.get("branch"))
    common["previous_ref"] = previous_ref

    try:
        client.set_vcs_ref(env_name, project, target_ref)
    except errors as exc:
        return halted(
            "git", env_name, "environment/vcs/rest/editproject", str(exc),
            f"the ref pin for {env_name} was attempted and rejected; the VCS "
            f"project may be partially written (it was on {previous_ref!r})",
            **common,
        )

    try:
        client.vcs_update(env_name, context)
    except errors as exc:
        return halted(
            "git", env_name, "environment/vcs/rest/update", str(exc),
            f"the VCS project for {env_name} is now pinned to {target_ref} (it was "
            f"on {previous_ref!r}), but deploying that ref failed — a restart would "
            f"now pull {target_ref}",
            **common,
        )

    verified, verification_error, live = _verify_ref(
        client, env_name, context, target_ref, errors)
    if verified == "mismatch":
        return halted(
            "git", env_name, "environment/vcs/rest/getprojects",
            f"the target reports it is on {live!r}, not {target_ref!r}",
            f"the ref pin for {env_name} was accepted but did not take",
            ref_verified="mismatch", **common,
        )

    if verified == "confirmed":
        message = f"Rolled back {env_name} to {target_ref} via git (confirmed by the target)."
    else:
        message = (
            f"Pinned {env_name} to {target_ref} and redeployed, but the target did "
            f"not confirm which ref is live ({verification_error}) — verify before "
            f"trusting this rollback."
        )
    return base(
        "git", env_name,
        success=True,
        mutated=True,
        state="completed",
        ref_verified=verified,
        verification_error=verification_error,
        restored=True,
        message=message,
        operator_message=message,
        **common,
    )


def rollback_clone(env_name: str, clone_name: str) -> dict:
    """Stop the failed environment so a backup clone can take over.

    This stops what is broken; it does not restore anything. ``restored`` stays
    false and the remaining operator steps are stated, because reporting a stop
    as a completed restore is the failure mode worse than the failure.
    """
    common = {"clone_name": clone_name}
    errors = _hosting_errors()
    client = _client()
    try:
        client.stop_env(env_name)
    except errors as exc:
        return halted(
            "clone", env_name, "environment/control/rest/stopenv", str(exc),
            f"stopping {env_name} was attempted and failed, so the failed release "
            f"may still be serving traffic while {clone_name} is not active",
            **common,
        )

    message = (
        f"Stopped {env_name}. Nothing has been restored yet — {clone_name} still has "
        f"to be made the active environment."
    )
    return base(
        "clone", env_name,
        success=True,
        mutated=True,
        state="stopped-awaiting-operator",
        restored=False,
        message=message,
        operator_message=message,
        next_steps=[
            f"Verify {clone_name} is running",
            "Update DNS if needed",
            f"Delete {env_name} when confirmed",
        ],
        **common,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rollback operations")
    parser.add_argument("--env-name", required=True, help="Environment name")
    parser.add_argument("--strategy", required=True, choices=["git", "clone"])
    parser.add_argument("--target-ref", help="Git ref for git strategy")
    parser.add_argument("--clone-name", help="Clone name for clone strategy")
    parser.add_argument("--context", default="ROOT", help="VCS project context")
    parser.add_argument(
        "--project-root", required=True,
        help="Working tree used for the stored-data drift check and the "
             "rollback audit trail. Required, no default: an omitted or "
             "silently-defaulted value used to write the audit trail "
             "relative to whatever the shell's cwd happened to be, where "
             "the deploy-phase verifier that reconciles against it could "
             "never find it (Tier-3 PR review round 7).",
    )
    parser.add_argument("--migrations-dir", default=data_drift.DEFAULT_MIGRATIONS_DIR)
    parser.add_argument("--ack-data-drift", action="store_true",
                        help="Proceed even though stored data has moved past the target ref")
    parser.add_argument("--override-reason",
                        help="Required alongside --ack-data-drift when it actually overrides a "
                             "flagged (drifted/unknown) stored-data report — written into the "
                             "durable rollback audit record, not just the console")
    parser.add_argument("--profile", help="Path to the target's deploy profile JSON")
    parser.add_argument(
        "--invocation", required=True, choices=["auto", "manual"],
        help="Was this triggered automatically (smoke-test failure) or "
             "operator-requested (--rollback)? Recorded verbatim in the audit "
             "trail; this script has no way to infer it. Required, no "
             "default: a silently-defaulted 'auto' used to make a real "
             "manual rollback invisible to "
             "deploy_checks.check_manual_rollback_proves_alive's "
             "invocation=='manual' filter, passing that check vacuously "
             "instead of catching the omission (Tier-3 PR review round 7).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    profile = None
    profile_error: str | None = None
    if args.profile:
        try:
            profile = deploy_profile.load_profile(args.profile)
        except deploy_profile.ProfileError as exc:
            profile_error = str(exc)

    if profile_error is not None:
        result = refused(args.strategy, args.env_name, profile_error)
    elif args.strategy == "git":
        if not args.target_ref:
            result = refused("git", args.env_name, "--target-ref required for git strategy")
        else:
            result = rollback_git(
                args.env_name, args.target_ref,
                context=args.context,
                project_root=args.project_root,
                migrations_dir=args.migrations_dir,
                ack_data_drift=args.ack_data_drift,
                override_reason=args.override_reason,
                profile=profile,
            )
    elif not args.clone_name:
        result = refused("clone", args.env_name, "--clone-name required for clone strategy")
    else:
        result = rollback_clone(args.env_name, args.clone_name)

    # FR-01.08 criterion 7: every invocation is recorded, whatever it decided —
    # including a pre-flight refusal such as an unreadable --profile. No branch
    # above may return early without reaching this call (external review,
    # e4-checks-deploy-changelog round 1: a --profile load failure used to
    # return before the record() call, reopening the exact gap #7 closes).
    #
    # Guarded: a lock timeout or unwritable audit dir must never swallow
    # operator_message and the intended exit code — for a HALTED rollback
    # that already mutated the host, losing that message is the one outcome
    # rollback_report's whole design exists to prevent (external code
    # review, e4-checks-deploy-changelog). The audit gap itself is loud on
    # stderr, never silent.
    try:
        rollback_audit.record(args.project_root, result, invocation=args.invocation)
    except (LockTimeout, OSError) as exc:
        print(f"WARNING: rollback audit trail not recorded: {exc}", file=sys.stderr)
        # Durable degraded marker (Tier-3 PR review round 4): the primary
        # trail's own design treats absence as "nothing happened", so a
        # lost record must not read that way downstream — see
        # rollback_audit.record_degraded's docstring.
        rollback_audit.record_degraded(args.project_root, invocation=args.invocation, reason=str(exc))

    print(json.dumps(result, indent=2))
    return exit_code(result)


if __name__ == "__main__":
    sys.exit(main())
