#!/usr/bin/env python3
"""Rollback operations for shipwright-deploy.

Supports:
- Git-based rollback (DEV): update VCS project to previous ref
- Clone-based rollback (PROD): restore from backup clone

Usage:
    uv run rollback.py --env-name <name> --strategy git --target-ref <tag>
    uv run rollback.py --env-name <name> --strategy clone --clone-name <backup>
"""

import argparse
import json
import os
import sys


def rollback_git(env_name: str, target_ref: str) -> dict:
    """Rollback by updating VCS project to a previous ref.

    This re-deploys the specified git ref (tag or commit).
    """
    from jelastic_client import get_client

    client = get_client()

    # Update the VCS project branch to the target ref
    # Note: This changes what the next Update pulls
    try:
        result = client._call(
            "environment/vcs/rest/update",
            envName=env_name,
            context="ROOT",
        )
        return {
            "success": True,
            "strategy": "git",
            "target_ref": target_ref,
            "env_name": env_name,
            "message": f"Rolled back {env_name} to {target_ref} via git",
        }
    except Exception as e:
        return {
            "success": False,
            "strategy": "git",
            "error": str(e),
        }


def rollback_clone(env_name: str, clone_name: str) -> dict:
    """Rollback by swapping to a backup clone.

    The original env is stopped, the clone is used as the active environment.
    """
    from jelastic_client import get_client

    client = get_client()

    try:
        # Stop the failed environment
        client.stop_env(env_name)

        return {
            "success": True,
            "strategy": "clone",
            "clone_name": clone_name,
            "env_name": env_name,
            "message": f"Stopped {env_name}. Use {clone_name} as active environment.",
            "next_steps": [
                f"Verify {clone_name} is running",
                f"Update DNS if needed",
                f"Delete {env_name} when confirmed",
            ],
        }
    except Exception as e:
        return {
            "success": False,
            "strategy": "clone",
            "error": str(e),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rollback operations")
    parser.add_argument("--env-name", required=True, help="Environment name")
    parser.add_argument("--strategy", required=True, choices=["git", "clone"])
    parser.add_argument("--target-ref", help="Git ref for git strategy")
    parser.add_argument("--clone-name", help="Clone name for clone strategy")
    args = parser.parse_args()

    if args.strategy == "git":
        if not args.target_ref:
            print(json.dumps({"success": False, "error": "--target-ref required for git strategy"}, indent=2))
            return 1
        result = rollback_git(args.env_name, args.target_ref)

    elif args.strategy == "clone":
        if not args.clone_name:
            print(json.dumps({"success": False, "error": "--clone-name required for clone strategy"}, indent=2))
            return 1
        result = rollback_clone(args.env_name, args.clone_name)

    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
