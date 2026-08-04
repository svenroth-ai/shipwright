#!/usr/bin/env python3
"""Public CLI for the one canonical Shipwright area-catalog producer."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SHARED_SCRIPTS = Path(__file__).resolve().parents[1]
if str(SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS))

from lib.area_catalog import (  # noqa: E402
    catalog_path,
    refresh_paths,
    seed_brownfield,
    seed_greenfield,
    validate_catalog,
)


def _git_changed_files(root: Path, diff_range: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACDMRT", diff_range],
        cwd=root, text=True, capture_output=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _load_changed_files(args: argparse.Namespace, root: Path) -> list[str]:
    values = list(args.changed_file or [])
    if args.changed_files_json:
        payload = json.loads(Path(args.changed_files_json).read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("changed_files", [])
        if not isinstance(payload, list):
            raise ValueError("changed-files JSON must be a list or contain changed_files")
        values.extend(str(item.get("path", "")) if isinstance(item, dict) else str(item) for item in payload)
    if args.git_range:
        values.extend(_git_changed_files(root, args.git_range))
    return values


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("seed-greenfield", "seed-brownfield"):
        child = sub.add_parser(name)
        child.add_argument("--project-root", default=".")
        child.add_argument("--source", default="project" if name == "seed-greenfield" else "adopt")
    refresh = sub.add_parser("refresh")
    refresh.add_argument("--project-root", default=".")
    refresh.add_argument("--source", required=True, choices=("build", "iterate", "project", "plan", "adopt"))
    refresh.add_argument("--changed-file", action="append", default=[])
    refresh.add_argument("--changed-files-json")
    refresh.add_argument("--git-range")
    refresh.add_argument("--no-provisional", action="store_true")
    validate = sub.add_parser("validate")
    validate.add_argument("--project-root", default=".")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(args.project_root).resolve()
    try:
        if args.command == "seed-greenfield":
            payload = seed_greenfield(root, args.source)
            result = {"action": args.command, "areas": len(payload["areas"]),
                      "catalog_path": str(catalog_path(root)), "catalogue_version": payload["catalogue_version"]}
        elif args.command == "seed-brownfield":
            payload = seed_brownfield(root, args.source)
            result = {"action": args.command, "areas": len(payload["areas"]),
                      "catalog_path": str(catalog_path(root)), "catalogue_version": payload["catalogue_version"]}
        elif args.command == "refresh":
            result = refresh_paths(root, _load_changed_files(args, root), args.source, not args.no_provisional)
            result["action"] = "refresh"
        else:
            path = catalog_path(root)
            payload = json.loads(path.read_text(encoding="utf-8"))
            errors = validate_catalog(payload)
            result = {"action": "validate", "catalog_path": str(path), "errors": errors, "valid": not errors}
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if not errors else 1
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"action": args.command, "error": str(exc), "success": False}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
