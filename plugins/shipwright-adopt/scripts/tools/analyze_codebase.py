#!/usr/bin/env python3
"""CLI: run all Layer-1 detectors against a project root and emit snapshot.json.

Usage:
    uv run analyze_codebase.py --project-root /path [--exclude-path webui ...] \\
        [--output /tmp/snapshot.json] [--profile-hint supabase-nextjs]

⚠️ **CROSS-REPO CONTRACT — an external consumer renders this snapshot.** The Command
Center WebUI (github.com/svenroth-ai/shipwright-webui) reads
``.shipwright/adopt/snapshot.json`` to show the operator *"what's already here"*
(stack, conventions, tests, CI) before /shipwright-adopt writes anything.

A key renamed or dropped here — **at any depth**, not just top level — does NOT fail
loudly over there; it renders a half-empty card. Before you change this shape, read
the "Cross-repo contract" section of ``skills/adopt/SKILL.md``. The gate in
``tests/test_snapshot_contract.py`` will stop you and tell you what to do.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Version of the snapshot wire shape (see the module docstring). MAJOR = breaking for
# the consumer (a key removed, renamed or retyped); MINOR = additive. Nothing asks you
# to remember this: tests/test_snapshot_contract.py diffs the live snapshot against the
# contract fixture as of origin/main and fails until the obliged bump is performed.
SNAPSHOT_SCHEMA_VERSION = "1.0"


def _load_lib(lib_dir: Path) -> dict[str, Any]:
    sys.path.insert(0, str(lib_dir))
    from stack_detector import detect_stack  # type: ignore
    from profile_matcher import match_profile  # type: ignore
    from convention_detector import detect_conventions  # type: ignore
    from test_framework_detector import detect_test_frameworks  # type: ignore
    from ci_detector import detect_ci  # type: ignore
    from feature_inferrer import infer_features_ast  # type: ignore
    from folder_introspector import introspect_folders  # type: ignore
    from nested_project_detector import detect_nested_projects  # type: ignore
    from git_analyzer import analyze_git  # type: ignore
    return {
        "detect_stack": detect_stack,
        "match_profile": match_profile,
        "detect_conventions": detect_conventions,
        "detect_test_frameworks": detect_test_frameworks,
        "detect_ci": detect_ci,
        "infer_features_ast": infer_features_ast,
        "introspect_folders": introspect_folders,
        "detect_nested_projects": detect_nested_projects,
        "analyze_git": analyze_git,
    }


def _commands_from_pkg(project_root: Path) -> dict[str, str | None]:
    pkg = project_root / "package.json"
    if not pkg.exists():
        return {"dev": None, "build": None, "test": None, "lint": None}
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"dev": None, "build": None, "test": None, "lint": None}
    scripts = data.get("scripts", {})
    def _pick(*keys: str) -> str | None:
        for k in keys:
            if k in scripts:
                return f"npm run {k}"
        return None
    return {
        "dev": _pick("dev", "start:dev", "serve"),
        "build": _pick("build"),
        "test": _pick("test", "test:unit"),
        "lint": _pick("lint"),
    }


def analyze(
    project_root: Path,
    excludes: list[str],
    profile_hint: str | None,
) -> dict[str, Any]:
    lib_dir = Path(__file__).resolve().parent.parent / "lib"
    fns = _load_lib(lib_dir)
    excludes_set = set(excludes)

    # Shared/profiles path lookup: walk up from this file
    here = Path(__file__).resolve()
    profiles_dir: Path | None = None
    for ancestor in [here, *here.parents]:
        candidate = ancestor.parent / "shared" / "profiles"
        if candidate.exists():
            profiles_dir = candidate
            break

    stack = fns["detect_stack"](project_root, excludes_set)
    profile = fns["match_profile"](stack, profiles_dir or Path()) if profiles_dir else {
        "matched": "generic", "confidence": 0.0, "candidates": []
    }
    if profile_hint:
        profile = {"matched": profile_hint, "confidence": 1.0, "candidates": profile.get("candidates", []), "source": "user-hint"}

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "project_root": str(project_root),
        "excludes": list(excludes),
        "stack": stack,
        "profile": profile,
        "conventions": fns["detect_conventions"](project_root),
        "test_frameworks": fns["detect_test_frameworks"](project_root),
        "ci_pipeline": fns["detect_ci"](project_root),
        "folders": fns["introspect_folders"](project_root, excludes_set),
        "nested_projects": fns["detect_nested_projects"](project_root),
        "features": fns["infer_features_ast"](project_root, stack, excludes_set),
        "git": fns["analyze_git"](project_root),
        "commands": _commands_from_pkg(project_root),
    }


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
    from cli_paths import unquoted_path
    parser = argparse.ArgumentParser(description="Analyze a codebase for /shipwright-adopt")
    parser.add_argument("--project-root", required=True, type=unquoted_path)
    parser.add_argument("--exclude-path", action="append", default=[])
    parser.add_argument("--profile-hint", type=str, default=None)
    parser.add_argument("--output", type=Path, default=None, help="Write snapshot to file (also prints to stdout)")
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        print(f"ERROR: not a directory: {project_root}", file=sys.stderr)
        return 1

    snapshot = analyze(project_root, args.exclude_path, args.profile_hint)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    else:
        # Default write under .shipwright/adopt/snapshot.json for Skill-flow consumption
        default_out = project_root / ".shipwright" / "adopt" / "snapshot.json"
        default_out.parent.mkdir(parents=True, exist_ok=True)
        default_out.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(snapshot, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
