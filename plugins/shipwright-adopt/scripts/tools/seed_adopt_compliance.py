#!/usr/bin/env python3
"""CLI wrapper: seed compliance reports for an adopted project.

Primary path: run `update_compliance.py --phase X` for each retroactive
phase marker. Fallback path: direct lib-import of the compliance generators.
Non-blocking — reports what succeeded and what didn't.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_lib() -> None:
    """Bootstrap sys.path so the bridge module + the shared contract resolve.

    Iterate B8: the bridge now imports ``shared.contracts.compliance``
    at module load. When this CLI is invoked from a plugin-local venv
    (``plugins/shipwright-adopt/.venv``), ``shared/`` is not on
    sys.path by default. We anchor the repo root from this file's own
    location and add both that AND ``scripts/lib/`` so legacy callers
    still ``from compliance_bridge import ...`` succeed.

    File layout used::

        plugins/shipwright-adopt/scripts/tools/seed_adopt_compliance.py
        repo_root/^         /^         /^     /^^
                  parents[3] parents[2] parent[1] parent[0]=file
        plugins/^          /^                  /^      /^      /^
                parents[4]                                            parents[0]=file
    """
    here = Path(__file__).resolve()
    lib_dir = here.parent.parent / "lib"
    # here.parents: [0]=tools, [1]=scripts, [2]=shipwright-adopt, [3]=plugins, [4]=repo_root.
    repo_root = here.parents[4]
    # Repo root first so ``shared.contracts.compliance`` resolves before any
    # accidentally-shadowing ``shared/`` module that may exist in a sibling
    # plugin's lib path.
    sys.path.insert(0, str(repo_root))
    sys.path.insert(1, str(lib_dir))


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
    from cli_paths import unquoted_path
    parser = argparse.ArgumentParser(description="Seed compliance for /shipwright-adopt")
    parser.add_argument("--project-root", required=True, type=unquoted_path)
    parser.add_argument(
        "--phases", nargs="*",
        default=["project", "plan", "build", "test", "adopt"],
        help=(
            "Retroactive phases to trigger update_compliance for. "
            "iterate-2026-05-23-security-adopt-compliance-snapshots: "
            "'adopt' added so the explicit adopt phase regen runs in "
            "addition to the four retroactive pipeline phases — keeps "
            "the Step H commit's snapshot in sync with the audit's "
            "post-adopt expectations."
        ),
    )
    parser.add_argument(
        "--fallback", action="store_true",
        help="Always run direct-lib fallback in addition to update_compliance",
    )
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        print(f"ERROR: not a directory: {project_root}", file=sys.stderr)
        return 1

    _load_lib()
    from compliance_bridge import run_update_compliance, run_lib_fallback  # type: ignore

    primary = run_update_compliance(project_root, phases=args.phases)
    results = {"primary": primary}

    # If primary failed to find script OR user asks for fallback explicitly,
    # run the lib-import path.
    if primary.get("script") is None or args.fallback:
        results["fallback"] = run_lib_fallback(project_root)

    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
