#!/usr/bin/env python3
"""
Deploy Profile validator CLI.

Wraps shared/scripts/lib/deploy_profile_validator.py with file I/O + arg
parsing. Validates one profile (--profile) or all profiles in a directory
(--all). Strict mode (--strict) additionally checks that shipped profiles'
client.entrypoint resolves to a real file under repo_root.

Exit codes:
  0  all profiles valid
  1  one or more validation errors found, or unrecoverable I/O / parse error
  2  CLI usage error (e.g. --profile and --all combined)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Repo-root resolution: this script lives at shared/scripts/tools/, so the repo
# root is three parents up. We use this both for default --profiles-dir and for
# default --repo-root (when not explicitly given).
_SCRIPT_DIR = Path(__file__).resolve().parent
_DEFAULT_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent
_DEFAULT_PROFILES_DIR = _DEFAULT_REPO_ROOT / "shared" / "profiles" / "deploy"
_DEFAULT_SCHEMA_PATH = _DEFAULT_REPO_ROOT / "shared" / "profiles" / "deploy-profile.schema.json"

# Make the lib importable when this script is invoked as a script
# (`uv run shared/scripts/tools/...`).
sys.path.insert(0, str(_DEFAULT_REPO_ROOT))

from shared.scripts.lib.deploy_profile_validator import (  # noqa: E402
    ValidationError,
    validate,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Shipwright deploy profiles against the JSON-Schema + semantic rules.",
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument(
        "--profile",
        type=Path,
        help="Path to a single profile JSON file.",
    )
    target.add_argument(
        "--all",
        action="store_true",
        help=f"Validate all *.json files in --profiles-dir (default: {_DEFAULT_PROFILES_DIR}).",
    )
    parser.add_argument(
        "--profiles-dir",
        type=Path,
        default=_DEFAULT_PROFILES_DIR,
        help="Directory of profiles to validate when --all is set.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=_DEFAULT_SCHEMA_PATH,
        help="Path to deploy-profile.schema.json.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Verify shipped profiles' client.entrypoint resolves to a real file under --repo-root.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=_DEFAULT_REPO_ROOT,
        help="Repository root for --strict path-existence checks.",
    )
    return parser


def _emit(errors: list[ValidationError]) -> None:
    for err in errors:
        print(str(err), file=sys.stderr)


def _load_schema(schema_path: Path) -> dict:
    if not schema_path.is_file():
        print(
            f"FAIL :: schema :: schema file not found: {schema_path}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    try:
        return json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(
            f"FAIL {schema_path} :: $ :: schema is not valid JSON: {e}",
            file=sys.stderr,
        )
        raise SystemExit(1) from e


def _load_profile(profile_path: Path) -> tuple[dict | None, ValidationError | None]:
    """Parse a profile file.

    Returns:
        Tuple of (profile_dict, error). On success: (dict, None). On failure:
        (None, ValidationError) — the caller is responsible for emitting the
        error through the normal error pipeline (no direct stderr print here).
    """
    if not profile_path.is_file():
        return None, ValidationError(
            json_pointer="$",
            message="profile not found",
            profile_path=profile_path,
        )
    try:
        return json.loads(profile_path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as e:
        return None, ValidationError(
            json_pointer="$",
            message=f"malformed JSON: {e}",
            profile_path=profile_path,
        )


def _enumerate_all(profiles_dir: Path) -> list[Path]:
    """Non-recursive *.json scan; skips hidden files, symlinks, schema files."""
    if not profiles_dir.is_dir():
        # Empty / missing dir is a soft warning, not an error.
        print(
            f"WARN :: --all :: profiles directory not found: {profiles_dir}",
            file=sys.stderr,
        )
        return []
    candidates: list[Path] = []
    for entry in sorted(profiles_dir.iterdir()):
        if entry.is_symlink():
            continue
        if not entry.is_file():
            continue
        name = entry.name
        if name.startswith("."):
            continue
        if name.endswith(".schema.json"):
            continue
        if not name.endswith(".json"):
            continue
        candidates.append(entry)
    return candidates


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.profile and not args.all:
        parser.error("one of --profile or --all is required")
        return 2  # parser.error raises SystemExit(2); included for clarity

    schema = _load_schema(args.schema)
    repo_root = args.repo_root.resolve()
    total_errors: list[ValidationError] = []

    if args.profile:
        profile, load_err = _load_profile(args.profile)
        if load_err is not None:
            total_errors.append(load_err)
        else:
            errors = validate(
                profile,
                schema,
                profile_path=args.profile,
                strict=args.strict,
                repo_root=repo_root if args.strict else None,
            )
            total_errors.extend(errors)
    else:
        # --all
        profile_paths = _enumerate_all(args.profiles_dir)
        if not profile_paths:
            print(
                f"WARN :: --all :: no profile files in {args.profiles_dir} — exit 0",
                file=sys.stderr,
            )
            return 0
        seen_ids: set[str] = set()
        for path in profile_paths:
            profile, load_err = _load_profile(path)
            if load_err is not None:
                total_errors.append(load_err)
                continue
            errors = validate(
                profile,
                schema,
                profile_path=path,
                strict=args.strict,
                repo_root=repo_root if args.strict else None,
                known_target_ids=seen_ids,
            )
            total_errors.extend(errors)

    if total_errors:
        _emit(total_errors)
        plural = "s" if len(total_errors) != 1 else ""
        print(
            f"\n{len(total_errors)} validation error{plural} found.",
            file=sys.stderr,
        )
        return 1

    print("All profiles valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
