#!/usr/bin/env python3
"""Write shipwright_project_config.json after scaffolding.

New Shipwright script (not from upstream).

Usage:
    uv run write-project-config.py --planning-dir <path> --profile <name> --scope <scope>

Output (JSON): the written config
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.state import detect_state


def _merge_canonical_gitignore(project_root: Path) -> dict:
    """Merge the canonical ``.shipwright`` artifact-ignore block into the
    project's ``.gitignore`` so framework-managed ignore rules propagate.

    Idempotent + additive (see ``shared/scripts/lib/gitignore_canon.py``).
    /shipwright-project previously wrote no .gitignore entries at all; this
    closes that gap (iterate-2026-05-30-gitignore-canon-propagation). On
    import failure (corrupted shared tree) returns an action=skipped record
    rather than crashing scaffolding.
    """
    repo_root = Path(__file__).resolve().parents[4]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        from shared.scripts.lib.gitignore_canon import (  # type: ignore
            merge_canonical_block,
        )
    except ImportError as exc:
        return {
            "action": "skipped",
            "reason": "gitignore_canon_import_failed",
            "error": str(exc),
            "path": str(project_root / ".gitignore"),
        }
    return merge_canonical_block(project_root)


def main() -> int:
    parser = argparse.ArgumentParser(description="Write shipwright project config")
    parser.add_argument("--planning-dir", required=True, help="Path to planning directory")
    parser.add_argument("--profile", required=True, help="Profile name (e.g., supabase-nextjs)")
    parser.add_argument("--scope", required=True, choices=["full_app", "extension"], help="Project scope")
    parser.add_argument("--project-root", help="Project root: where the config is written. Defaults to the project above "
                        "<project>/.shipwright/planning, else to the parent of planning-dir")
    parser.add_argument("--profile-root", help="Project whose .shipwright/profiles/ is searched for --profile (lookup only: "
                        "the config location is NOT affected). Pass it from a skill: with a requirements file "
                        "(@requirements.md) --planning-dir is that file's folder and says nothing about the project")
    parser.add_argument("--status", default="complete", choices=["in_progress", "complete"],
                        help="Config status (default: complete)")
    args = parser.parse_args()

    planning_dir = Path(args.planning_dir).resolve()
    raw_planning = Path(os.path.abspath(args.planning_dir))  # not resolved: a linked .shipwright keeps its name
    under_dot_shipwright = raw_planning.parent.name == ".shipwright"
    config_planning = planning_dir  # the planning dir as the config stores it: relative to project_root
    if args.project_root:
        project_root = Path(args.project_root).resolve()
    elif under_dot_shipwright:  # the skills pass only <project>/.shipwright/planning: the project is above it
        project_root = raw_planning.parent.parent
        config_planning = raw_planning
    else:
        project_root = planning_dir.parent
    # --profile-root only moves the profile LOOKUP (<root>/.shipwright/profiles); the config location,
    # gitignore and artifact checks below always use `project_root`.
    lookup_root = Path(args.profile_root).resolve() if args.profile_root else project_root

    from lib.profile_check import check_profile, describe  # project's own lib (path set above)

    # The early phase-tracking call (in_progress + reserved sentinel) names no profile file, so it
    # must not gain a new failure mode: the sentinel skips the check entirely. The ImportError degrade
    # below is reached only by a direct in_progress call naming a real profile (no skill makes one;
    # pinned by test_profile_name_check); --status complete keeps the hard install error (exit 1).
    early_sentinel = args.status == "in_progress" and args.profile in ("generic", "detecting")
    if not early_sentinel:
        try:
            check_profile(args.profile, lookup_root)
        except ImportError as exc:
            if args.status != "in_progress":  # a complete scaffold never writes an unvalidated profile name
                print(f"ERROR: {exc}", file=sys.stderr)
                return 1
            print(f"[write-project-config] profile check skipped: {exc}", file=sys.stderr)
        except ValueError as exc:
            print(f"ERROR: {describe(args.profile, exc)}", file=sys.stderr)
            return 4

    if args.status == "in_progress":
        # Early config: minimal tracking before scaffolding completes
        config = {
            "status": "in_progress",
            "scope": args.scope,
            "profile": args.profile,
        }
    else:
        # Full config: after scaffolding with splits and artifacts
        state = detect_state(planning_dir)
        config = {
            "status": "complete",
            "scope": args.scope,
            "profile": args.profile,
            "planning_dir": config_planning.relative_to(project_root).as_posix(),
            "splits": [
                {"name": s, "status": "not_started"}
                for s in state["splits"]
            ],
            "artifacts": {
                "claude_md": (project_root / "CLAUDE.md").exists(),
                "agents_md": (project_root / "AGENTS.md").exists(),
                "agent_docs": (project_root / ".shipwright" / "agent_docs").is_dir(),  # artifact-path-canon: legacy
                "manifest": state["manifest_created"],
            },
        }

    config_path = project_root / "shipwright_project_config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    # Propagate the canonical .shipwright artifact-ignore block into the
    # project's .gitignore on the full-scaffold path. Reported to stderr so
    # stdout stays a pure config JSON for downstream parsers.
    if args.status == "complete":
        merge = _merge_canonical_gitignore(project_root)
        print(
            f"[write-project-config] .gitignore canonical block: "
            f"{merge.get('action')} (added {len(merge.get('added', []))} rule(s))",
            file=sys.stderr,
        )

    print(json.dumps(config, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
