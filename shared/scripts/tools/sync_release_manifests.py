"""Release-time write + verify for project-declared published package
manifests (parsing/validation primitives: ``lib/manifest_sync_core.py``).

Called from ``/shipwright-changelog`` Step 5.4 (write+stage) and Step 6
(``--verify-commit``, chained ``&&`` immediately before ``git tag``). Full
contract, status vocabulary, and recovery notes: ``plugins/shipwright-
changelog/skills/changelog/references/manifest-sync.md``.

Two modes:

    # write + stage (Step 5.4)
    uv run shared/scripts/tools/sync_release_manifests.py \\
        --project-root . --version 0.3.0 --stage \\
        --result-file .shipwright/planning/iterate/{run_id}/manifest_sync_result.json

    # verify against the committed blob (Step 6, before `git tag`)
    uv run shared/scripts/tools/sync_release_manifests.py \\
        --project-root . --version 0.3.0 --verify-commit "$(git rev-parse HEAD)" \\
        --result-file .shipwright/planning/iterate/{run_id}/manifest_sync_result.json

``--verify-commit`` reads its manifest list from the frozen ``--result-file``
Step 5.4 wrote — never re-reading ``shipwright_changelog_config.json``,
mutable worktree state that must not silently change what gets verified.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.atomic_write import durable_atomic_write  # noqa: E402
from lib.manifest_sync_core import (  # noqa: E402
    ManifestSyncError,
    git,
    git_relative_path,
    load_declared_manifests,
    read_manifest_version,
    render_manifest_write,
    resolve_contained_path,
    validate_version,
)

_NO_MANIFESTS_NOTE = "no published manifests declared"


def _is_dirty(project_root: Path, rel: str) -> bool:
    """A failing ``git status`` (index lock, damaged repo) fails closed as
    dirty; repo-ness is decided structurally (``git rev-parse --git-dir``),
    not by matching git's localizable stderr text, so a genuinely non-git
    project (this tool's own test fixtures) still proceeds cleanly."""
    if git(project_root, "rev-parse", "--git-dir").returncode != 0:
        return False
    proc = git(project_root, "status", "--porcelain", "--", rel)
    if proc.returncode != 0:
        return True
    return bool(proc.stdout.strip())


def _preflight_entry(project_root: Path, entry: dict) -> dict:
    """Validate one declared entry; raises :class:`ManifestSyncError` fail-closed."""
    rel, fmt = entry["path"], entry["format"]
    resolved = resolve_contained_path(project_root, rel)
    if not resolved.is_file():
        raise ManifestSyncError("manifest_missing", f"{rel} does not exist", path=rel)
    if _is_dirty(project_root, rel):
        raise ManifestSyncError(
            "manifest_dirty_before_sync",
            f"{rel} has uncommitted changes before the sync started",
            path=rel,
        )
    # read_bytes().decode(), NOT read_text(): read_text folds CRLF to LF,
    # silently rewriting a CRLF manifest while reformatted stays False.
    text = resolved.read_bytes().decode("utf-8")
    try:
        current_version = read_manifest_version(text, fmt)
    except ManifestSyncError as exc:
        raise ManifestSyncError(exc.status, exc.detail, path=exc.path or rel) from exc
    return {"path": rel, "format": fmt, "resolved": resolved, "current_version": current_version, "text": text}


def _restore(written: list[tuple[Path, bytes]]) -> None:
    """Best-effort byte restoration; see manifest-sync.md's recovery
    section if this itself fails, leaving the worktree partly modified."""
    for path, original in written:
        try:
            durable_atomic_write(path, original)
        except OSError:
            pass


def sync(project_root: Path, version: str, *, dry_run: bool, stage: bool) -> dict:
    """Validate, write (two-phase: preflight every entry first), and
    optionally stage. Every named failure returns ``{"status": ...,
    "detail": ...}``; an unreadable-file OSError/UnicodeDecodeError during
    preflight is the one thing that still escapes as a traceback (non-zero
    exit either way, so the release gate still holds)."""
    try:
        validate_version(version)
        declared = load_declared_manifests(project_root)
    except ManifestSyncError as exc:
        return {"status": exc.status, "detail": exc.detail, "version": version, "manifests": []}

    if not declared:
        result = {"status": "ok", "version": version, "manifests": [], "note": _NO_MANIFESTS_NOTE}
        if stage:
            result["manifest_pathspec"] = []
        return result

    prepared = []
    for entry in declared:
        try:
            prepared.append(_preflight_entry(project_root, entry))
        except ManifestSyncError as exc:
            return {
                "status": exc.status, "detail": exc.detail, "path": exc.path,
                "version": version, "manifests": [],
            }

    written: list[tuple[Path, bytes]] = []
    manifests_result = []
    for p in prepared:
        if p["current_version"] == version:
            manifests_result.append(
                {"path": p["path"], "format": p["format"], "changed": False, "reformatted": False}
            )
            continue
        try:
            new_text, reformatted = render_manifest_write(
                p["text"], p["format"], p["current_version"], version
            )
            if not dry_run:
                original_bytes = p["resolved"].read_bytes()
                written.append((p["resolved"], original_bytes))
                durable_atomic_write(p["resolved"], new_text)
        except (ManifestSyncError, OSError) as exc:
            _restore(written)
            status = exc.status if isinstance(exc, ManifestSyncError) else "write_failed"
            detail = exc.detail if isinstance(exc, ManifestSyncError) else str(exc)
            return {"status": status, "detail": detail, "path": p["path"], "version": version, "manifests": []}
        manifests_result.append(
            {"path": p["path"], "format": p["format"], "changed": True, "reformatted": reformatted}
        )

    result = {"status": "ok", "version": version, "manifests": manifests_result, "dry_run": dry_run}

    # manifest_pathspec is always present when --stage was requested
    # (dry-run or not) — never a KeyError depending on which branch ran.
    if stage:
        if dry_run:
            result["manifest_pathspec"] = []
        else:
            paths = [p["path"] for p in prepared]
            add = git(project_root, "add", "--", *paths)
            if add.returncode != 0:
                # Defense-in-depth: a bad pathspec already fails `git add`
                # atomically (paths are preflight-confirmed to exist), but
                # this unstages regardless in case another failure partially staged.
                git(project_root, "reset", "-q", "--", *paths)
                _restore(written)
                return {
                    "status": "stage_failed", "detail": add.stderr.strip(),
                    "version": version, "manifests": [],
                }
            result["manifest_pathspec"] = list(paths)

    return result


def verify_commit(project_root: Path, sha: str, version: str, result_file: Path) -> dict:
    """Re-read every manifest from the frozen ``--result-file`` list at the
    COMMITTED blob (``git show <sha>:<path>``) — never the worktree or the
    (mutable) config again."""
    try:
        validate_version(version)
    except ManifestSyncError as exc:
        return {"status": exc.status, "detail": exc.detail, "version": version, "manifests": []}

    try:
        recorded = json.loads(result_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "result_file_invalid", "detail": str(exc), "version": version, "manifests": []}
    if not isinstance(recorded, dict):
        return {
            "status": "result_file_invalid", "detail": "--result-file must contain a JSON object",
            "version": version, "manifests": [],
        }

    # Written unconditionally (incl. on a failed/dry-run sync, at a fixed
    # path persisting across releases) — status, dry_run, AND version must
    # all check out before the manifest list is trusted, or a stale/failed
    # run recreates the card's regression inside the gate's own state.
    if recorded.get("status") != "ok":
        return {
            "status": "sync_incomplete",
            "detail": f"--result-file records status {recorded.get('status')!r}, not 'ok'",
            "version": version, "manifests": [],
        }
    if recorded.get("dry_run"):
        return {
            "status": "sync_incomplete",
            "detail": "--result-file records a --dry-run sync — nothing was actually staged",
            "version": version, "manifests": [],
        }
    if recorded.get("version") != version:
        return {
            "status": "result_file_stale",
            "detail": f"--result-file records version {recorded.get('version')!r}, "
                      f"not the release being verified ({version!r})",
            "version": version, "manifests": [],
        }

    manifests = recorded.get("manifests") or []
    if not isinstance(manifests, list):
        return {
            "status": "result_file_invalid", "detail": "--result-file 'manifests' must be a JSON array",
            "version": version, "manifests": [],
        }
    if not manifests:
        return {"status": "ok", "version": version, "manifests": [], "note": _NO_MANIFESTS_NOTE}

    checked = []
    for m in manifests:
        if not isinstance(m, dict) or not isinstance(m.get("path"), str) or not isinstance(m.get("format"), str):
            return {
                "status": "result_file_invalid",
                "detail": f"--result-file 'manifests' entry is malformed: {m!r}",
                "version": version, "manifests": checked,
            }
        rel, fmt = m["path"], m["format"]
        git_rel = git_relative_path(project_root, rel)
        blob = git(project_root, "show", f"{sha}:{git_rel}")
        if blob.returncode != 0:
            return {
                "status": "verify_mismatch", "detail": f"{rel} not found at commit {sha}",
                "path": rel, "version": version, "manifests": checked,
            }
        try:
            committed_version = read_manifest_version(blob.stdout, fmt)
        except ManifestSyncError as exc:
            return {
                "status": exc.status, "detail": exc.detail, "path": rel,
                "version": version, "manifests": checked,
            }
        if committed_version != version:
            return {
                "status": "verify_mismatch",
                "detail": f"{rel}: committed version {committed_version!r} != released {version!r}",
                "path": rel, "version": version, "manifests": checked,
            }
        checked.append({"path": rel, "committed_version": committed_version})

    return {"status": "ok", "version": version, "manifests": checked}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync/verify published-package-manifest versions at release time"
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--version", required=True, help="bare semver, no leading 'v'")
    parser.add_argument("--dry-run", action="store_true", help="report without touching disk")
    parser.add_argument("--stage", action="store_true", help="git add the declared paths after writing")
    parser.add_argument(
        "--result-file", default=None,
        help="write the sync result here (sync mode); read the frozen manifest list from here (--verify-commit mode)",
    )
    parser.add_argument(
        "--verify-commit", metavar="SHA", default=None,
        help="verify the committed blob at SHA instead of writing — requires --result-file",
    )
    args = parser.parse_args(argv)

    if args.verify_commit and not args.result_file:
        parser.error("--verify-commit requires --result-file")

    project_root = Path(args.project_root).resolve()
    # Relative --result-file resolves against --project-root, not CWD —
    # SKILL.md's usage makes them coincide, but nothing enforces that.
    result_file = (project_root / args.result_file) if args.result_file else None

    if args.verify_commit:
        result = verify_commit(project_root, args.verify_commit, args.version, result_file)
    else:
        result = sync(project_root, args.version, dry_run=args.dry_run, stage=args.stage)
        if result_file:
            durable_atomic_write(result_file, json.dumps(result, indent=2) + "\n")

    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
