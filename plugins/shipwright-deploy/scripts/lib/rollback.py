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
import urllib.error
from pathlib import Path

import data_drift
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

__all__ = [
    "EXIT_HALT", "EXIT_OK", "EXIT_REFUSED", "HostingError",
    "main", "rollback_clone", "rollback_git",
]


def _client():
    from jelastic_client import get_client

    return get_client()


def _hosting_errors() -> tuple[type[BaseException], ...]:
    """Exactly the failures that mean "the host said no", never a local bug.

    ``URLError`` is included because a client that does not wrap transport
    failures would otherwise escape the read-back downgrade and produce no
    report at all. Programming errors (TypeError, KeyError, …) still propagate.
    """
    errors: list[type[BaseException]] = [HostingError, urllib.error.URLError]
    try:
        from jelastic_client import JelasticError
    except ImportError:
        pass
    else:
        if isinstance(JelasticError, type) and issubclass(JelasticError, BaseException):
            errors.append(JelasticError)
    return tuple(errors)


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
    parser.add_argument("--project-root", default=".",
                        help="Working tree used for the stored-data drift check")
    parser.add_argument("--migrations-dir", default=data_drift.DEFAULT_MIGRATIONS_DIR)
    parser.add_argument("--ack-data-drift", action="store_true",
                        help="Proceed even though stored data has moved past the target ref")
    parser.add_argument("--profile", help="Path to the target's deploy profile JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    profile = None
    if args.profile:
        try:
            profile = deploy_profile.load_profile(args.profile)
        except deploy_profile.ProfileError as exc:
            print(json.dumps(refused(args.strategy, args.env_name, str(exc)), indent=2))
            return EXIT_REFUSED

    if args.strategy == "git":
        if not args.target_ref:
            result = refused("git", args.env_name, "--target-ref required for git strategy")
        else:
            result = rollback_git(
                args.env_name, args.target_ref,
                context=args.context,
                project_root=args.project_root,
                migrations_dir=args.migrations_dir,
                ack_data_drift=args.ack_data_drift,
                profile=profile,
            )
    elif not args.clone_name:
        result = refused("clone", args.env_name, "--clone-name required for clone strategy")
    else:
        result = rollback_clone(args.env_name, args.clone_name)

    print(json.dumps(result, indent=2))
    return exit_code(result)


if __name__ == "__main__":
    sys.exit(main())
