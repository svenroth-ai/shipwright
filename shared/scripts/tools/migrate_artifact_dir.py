"""Move a legacy top-level Shipwright artifact dir to its `.shipwright/` home.

Sub-Iterate F deliverable for the planning -> .shipwright/planning relocation.
Available artifacts come from `shared/scripts/lib/artifact_migrations.py`
(``ARTIFACT_MIGRATIONS``).

Usage:
    uv run shared/scripts/tools/migrate_artifact_dir.py \
        --artifact planning \
        --project-root /path/to/project \
        [--dry-run] [--json]

Exit codes:
    0 -- success (or dry-run reported a planned move)
    1 -- preflight refusal (legacy missing, canonical already populated, ...)
    2 -- argparse / unknown-artifact error (Python's default for argparse)
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

# Allow ``from lib.artifact_migrations import ...`` whether invoked via
# ``uv run shared/scripts/tools/migrate_artifact_dir.py`` from the repo root
# or as a module from a worktree.
_HERE = Path(__file__).resolve()
_SHARED_SCRIPTS = _HERE.parent.parent
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.artifact_migrations import ARTIFACT_MIGRATIONS, get_migration  # noqa: E402


def _format_remediation(unknown_name: str) -> str:
    available = ", ".join(m["name"] for m in ARTIFACT_MIGRATIONS) or "(none)"
    return (
        f"Unknown artifact '{unknown_name}'.\n"
        f"Remediation: pass one of the available artifacts: {available}.\n"
        f"To register a new artifact, append a dict to ARTIFACT_MIGRATIONS in "
        f"shared/scripts/lib/artifact_migrations.py."
    )


def _is_git_repo(project_root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def _git_tracks(project_root: Path, relative_path: str) -> bool:
    """True iff at least one tracked file lives under *relative_path*."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", relative_path],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.returncode == 0


def _dir_is_empty(path: Path) -> bool:
    if not path.exists():
        return True
    return not any(path.iterdir())


def _git_mv(project_root: Path, src_rel: str, dst_rel: str) -> tuple[bool, str]:
    result = subprocess.run(
        ["git", "mv", src_rel, dst_rel],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def _shutil_move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        # Caller already verified dst is empty -- remove the empty shell so
        # ``shutil.move`` doesn't refuse to overwrite a directory.
        dst.rmdir()
    shutil.move(str(src), str(dst))


def migrate(
    artifact_name: str,
    project_root: Path,
    *,
    dry_run: bool = False,
) -> dict:
    """Run the migration. Returns a result dict; never raises on preflight."""
    migration = get_migration(artifact_name)
    if migration is None:
        return {
            "success": False,
            "error": "unknown_artifact",
            "artifact": artifact_name,
            "message": _format_remediation(artifact_name),
        }

    legacy_rel = migration["legacy_dirname"]
    canonical_rel = migration["canonical"]
    legacy = project_root / legacy_rel
    canonical = project_root / canonical_rel

    if not legacy.is_dir():
        return {
            "success": False,
            "error": "legacy_missing",
            "artifact": artifact_name,
            "from": str(legacy),
            "to": str(canonical),
            "message": (
                f"Legacy directory `{legacy}` does not exist. Nothing to migrate.\n"
                f"Remediation: verify --project-root is correct, or that the "
                f"directory wasn't already moved."
            ),
        }

    if canonical.exists() and not _dir_is_empty(canonical):
        return {
            "success": False,
            "error": "canonical_already_populated",
            "artifact": artifact_name,
            "from": str(legacy),
            "to": str(canonical),
            "message": (
                f"Canonical destination `{canonical}` already exists and is "
                f"non-empty. Refusing to merge -- manual review required.\n"
                f"Remediation: inspect both directories, then either remove "
                f"`{canonical}` (if it's empty bootstrap) or merge content "
                f"manually before re-running."
            ),
        }

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "artifact": artifact_name,
            "from": str(legacy),
            "to": str(canonical),
            "message": (
                f"[dry run] would move `{legacy}` -> `{canonical}` "
                f"({'git mv' if _is_git_repo(project_root) and _git_tracks(project_root, legacy_rel) else 'shutil.move'})."
            ),
        }

    # Empty stub canonical dir: remove so the move target is clean.
    if canonical.exists() and _dir_is_empty(canonical):
        canonical.rmdir()

    canonical.parent.mkdir(parents=True, exist_ok=True)

    use_git = _is_git_repo(project_root) and _git_tracks(project_root, legacy_rel)
    if use_git:
        ok, output = _git_mv(project_root, legacy_rel, canonical_rel)
        if not ok:
            return {
                "success": False,
                "error": "git_mv_failed",
                "artifact": artifact_name,
                "from": str(legacy),
                "to": str(canonical),
                "message": (
                    f"`git mv {legacy_rel} {canonical_rel}` failed: {output}\n"
                    f"Remediation: resolve the underlying git error (often a "
                    f"merge conflict, locked index, or missing parent dir), "
                    f"then re-run."
                ),
            }
    else:
        try:
            _shutil_move(legacy, canonical)
        except OSError as exc:
            return {
                "success": False,
                "error": "move_failed",
                "artifact": artifact_name,
                "from": str(legacy),
                "to": str(canonical),
                "message": (
                    f"shutil.move failed: {exc}\n"
                    f"Remediation: check filesystem permissions on the project "
                    f"root and `.shipwright/`."
                ),
            }

    return {
        "success": True,
        "artifact": artifact_name,
        "from": str(legacy),
        "to": str(canonical),
        "method": "git mv" if use_git else "shutil.move",
        "message": (
            f"Moved `{legacy}` -> `{canonical}` "
            f"({'git mv' if use_git else 'shutil.move'}). "
            f"Review with `git status` (if git-tracked) and commit."
        ),
    }


def _emit(result: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result))
    else:
        print(result.get("message", ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Move a legacy artifact dir to its .shipwright/ home.",
    )
    parser.add_argument(
        "--artifact",
        required=True,
        help="Artifact name from ARTIFACT_MIGRATIONS (e.g. 'planning').",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root containing the legacy directory. Defaults to cwd.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan only, do not move.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()

    result = migrate(args.artifact, project_root, dry_run=args.dry_run)
    _emit(result, as_json=args.json)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
