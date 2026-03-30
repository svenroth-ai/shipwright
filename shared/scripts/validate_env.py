#!/usr/bin/env python3
"""Validate required environment variables for any pipeline phase.

Reads the stack profile from shipwright_run_config.json, checks the
profile's required_env_vars for the given phase, and reports missing vars.
All vars (build, deploy, plugin) live in the project's .env.local.

Usage:
    uv run validate_env.py --project-root <path> --phase build|deploy|plugin|all [--profile-dir <path>]

Output (JSON):
    {
        "success": true/false,
        "phase": "build",
        "profile": "supabase-nextjs",
        "missing": [{"name": "...", "description": "..."}],
        "optional_missing": [{"name": "...", "description": "..."}],
        "found": ["VAR_NAME", ...],
        "env_file_exists": true/false,
        "env_file_path": ".env.local",
        "skipped": false,
        "skip_reason": null
    }
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Allow importing shared lib
sys.path.insert(0, str(Path(__file__).parent / "lib"))


def parse_env_file(env_path: Path) -> dict[str, str]:
    """Parse a .env file into a dict of key-value pairs.

    Handles KEY=value, KEY="value", KEY='value', comments, and blank lines.
    Does NOT expand variable references.
    """
    env_vars: dict[str, str] = {}
    if not env_path.exists():
        return env_vars

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key:
            env_vars[key] = value
    return env_vars


def load_profile(profile_name: str, profile_dir: Path) -> dict | None:
    """Load a stack profile JSON by name."""
    profile_path = profile_dir / f"{profile_name}.json"
    if not profile_path.exists():
        return None
    return json.loads(profile_path.read_text(encoding="utf-8"))


def _collect_phase_vars(
    profile: dict, phase: str,
) -> list[tuple[str, list[dict]]]:
    """Return list of (section_label, vars) tuples for *phase*.

    If *phase* is ``"all"``, returns all sections.  Otherwise returns
    only the requested phase.
    """
    required = profile.get("required_env_vars", {})
    phase_order = ["build", "deploy", "plugin"]

    if phase == "all":
        return [
            (p.capitalize(), required.get(p, []))
            for p in phase_order
            if required.get(p)
        ]
    vars_list = required.get(phase, [])
    return [(phase.capitalize(), vars_list)] if vars_list else []


def _find_existing_keys(env_file_path: Path) -> set[str]:
    """Parse existing .env.local and return all keys (active or commented)."""
    keys: set[str] = set()
    if not env_file_path.exists():
        return keys
    for line in env_file_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        check = stripped.lstrip("#").strip()
        if "=" in check:
            key = check.partition("=")[0].strip()
            if key:
                keys.add(key)
    return keys


def init_env_file(
    project_root: Path,
    phase: str,
    profile_dir: Path,
) -> dict:
    """Create or update .env.local with commented placeholders for required vars.

    Includes all phases when *phase* is ``"all"``, or a single phase otherwise.
    Returns a result dict with status: created, updated, or unchanged.
    """
    # Load profile
    run_config_path = project_root / "shipwright_run_config.json"
    if not run_config_path.exists():
        return {"action": "skipped", "reason": "No shipwright_run_config.json found"}

    run_config = json.loads(run_config_path.read_text(encoding="utf-8"))
    profile_name = run_config.get("profile")
    if not profile_name:
        return {"action": "skipped", "reason": "No profile set in run config"}

    profile = load_profile(profile_name, profile_dir)
    if not profile:
        return {"action": "skipped", "reason": f"Profile '{profile_name}' not found"}

    sections = _collect_phase_vars(profile, phase)
    all_vars = [v for _, vars_list in sections for v in vars_list]
    if not all_vars:
        return {"action": "skipped", "reason": f"No vars defined for phase '{phase}'"}

    env_file_path = project_root / ".env.local"
    existing_keys = _find_existing_keys(env_file_path)

    if env_file_path.exists():
        # Find vars that need to be added
        missing_vars = [v for v in all_vars if v["name"] not in existing_keys]
        if not missing_vars:
            return {
                "action": "unchanged",
                "env_file_path": str(env_file_path),
                "profile": profile_name,
            }

        # Append missing vars to existing file
        lines = ["\n# --- Added by Shipwright ---"]
        for var in missing_vars:
            opt = " (optional)" if var.get("optional") else ""
            lines.append(f"# {var['name']}=        # {var['description']}{opt}")
        lines.append("")

        with env_file_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return {
            "action": "updated",
            "env_file_path": str(env_file_path),
            "profile": profile_name,
            "added": [v["name"] for v in missing_vars],
        }

    # Create new file with all sections
    lines = [
        "# =============================================================================",
        f"# Environment Variables — generated by Shipwright",
        f"# Profile: {profile_name}",
        "#",
        "# Fill in the values below and remove the leading '#' to activate each variable.",
        "# This file is NOT committed to git (.gitignore).",
        "# =============================================================================",
    ]
    for label, vars_list in sections:
        lines.append("")
        lines.append(f"# --- {label} ---")
        for var in vars_list:
            opt = " (optional)" if var.get("optional") else ""
            lines.append(f"# {var['name']}=        # {var['description']}{opt}")
    lines.append("")

    env_file_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "action": "created",
        "env_file_path": str(env_file_path),
        "profile": profile_name,
        "vars": [v["name"] for v in all_vars],
    }


def validate(
    project_root: Path,
    phase: str,
    profile_dir: Path,
) -> dict:
    """Run env var validation for the given phase.

    Returns a result dict suitable for JSON output.
    """
    # Read run config to get profile name
    run_config_path = project_root / "shipwright_run_config.json"
    if not run_config_path.exists():
        return {
            "success": True,
            "phase": phase,
            "profile": None,
            "missing": [],
            "optional_missing": [],
            "found": [],
            "env_file_exists": False,
            "env_file_path": None,
            "skipped": True,
            "skip_reason": "No shipwright_run_config.json found — skipping env validation",
        }

    run_config = json.loads(run_config_path.read_text(encoding="utf-8"))
    profile_name = run_config.get("profile")
    if not profile_name:
        return {
            "success": True,
            "phase": phase,
            "profile": None,
            "missing": [],
            "optional_missing": [],
            "found": [],
            "env_file_exists": False,
            "env_file_path": None,
            "skipped": True,
            "skip_reason": "No profile set in run config — skipping env validation",
        }

    profile = load_profile(profile_name, profile_dir)
    if not profile:
        return {
            "success": True,
            "phase": phase,
            "profile": profile_name,
            "missing": [],
            "optional_missing": [],
            "found": [],
            "env_file_exists": False,
            "env_file_path": None,
            "skipped": True,
            "skip_reason": f"Profile '{profile_name}' not found in {profile_dir}",
        }

    sections = _collect_phase_vars(profile, phase)
    phase_vars = [v for _, vars_list in sections for v in vars_list]

    if not phase_vars:
        return {
            "success": True,
            "phase": phase,
            "profile": profile_name,
            "missing": [],
            "optional_missing": [],
            "found": [],
            "env_file_exists": False,
            "env_file_path": None,
            "skipped": True,
            "skip_reason": f"No required_env_vars defined for phase '{phase}' in profile",
        }

    # Collect available vars from .env.local and os.environ
    env_file_path = project_root / ".env.local"
    env_file_exists = env_file_path.exists()

    available_vars: dict[str, str] = {}
    if env_file_exists:
        available_vars.update(parse_env_file(env_file_path))
    # Always check os.environ as fallback
    available_vars.update(os.environ)

    found: list[str] = []
    missing: list[dict] = []
    optional_missing: list[dict] = []

    for var_def in phase_vars:
        var_name = var_def["name"]
        is_optional = var_def.get("optional", False)
        value = available_vars.get(var_name, "")

        if value:
            found.append(var_name)
        elif is_optional:
            optional_missing.append({
                "name": var_name,
                "description": var_def.get("description", ""),
            })
        else:
            missing.append({
                "name": var_name,
                "description": var_def.get("description", ""),
            })

    success = len(missing) == 0

    return {
        "success": success,
        "phase": phase,
        "profile": profile_name,
        "missing": missing,
        "optional_missing": optional_missing,
        "found": found,
        "env_file_exists": env_file_exists,
        "env_file_path": str(env_file_path),
        "skipped": False,
        "skip_reason": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate env vars for build/deploy")
    parser.add_argument("--project-root", required=True, help="Path to target project root")
    parser.add_argument("--phase", required=True, choices=["build", "deploy", "plugin", "all"], help="Pipeline phase")
    parser.add_argument(
        "--profile-dir",
        help="Directory containing profile JSON files (default: shared/profiles/ relative to this script)",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Create/update .env.local with commented placeholders for required vars",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(json.dumps({"success": False, "error": f"Project root not found: {project_root}"}, indent=2))
        return 1

    if args.profile_dir:
        profile_dir = Path(args.profile_dir).resolve()
    else:
        # Default: shared/profiles/ relative to this script's location
        profile_dir = Path(__file__).parent.parent / "profiles"

    if args.init:
        result = init_env_file(project_root, args.phase, profile_dir)
        print(json.dumps(result, indent=2))
        return 0

    result = validate(project_root, args.phase, profile_dir)
    print(json.dumps(result, indent=2))

    return 0 if result.get("success", False) or result.get("skipped", False) else 1


if __name__ == "__main__":
    sys.exit(main())
