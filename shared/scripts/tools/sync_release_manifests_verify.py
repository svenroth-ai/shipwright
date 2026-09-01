"""``--verify-commit`` mode for ``sync_release_manifests.py`` — split into
its own module to keep that file under the project's 300-line guideline.

Re-reads every manifest from the frozen ``--result-file`` list at the
COMMITTED blob (``git show <sha>:<path>``), never the worktree or the
(mutable) config again.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.manifest_sync_core import (  # noqa: E402
    ManifestSyncError,
    describe_version_state,
    git,
    git_relative_path,
    validate_version,
)

__all__ = ["NO_MANIFESTS_NOTE", "verify_commit"]

NO_MANIFESTS_NOTE = "no published manifests declared"


def verify_commit(project_root: Path, sha: str, version: str, result_file: Path) -> dict:
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
        return {"status": "ok", "version": version, "manifests": [], "note": NO_MANIFESTS_NOTE}

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
            matches, detail = describe_version_state(blob.stdout, fmt, version)
        except ManifestSyncError as exc:
            return {
                "status": exc.status, "detail": exc.detail, "path": rel,
                "version": version, "manifests": checked,
            }
        if not matches:
            return {
                "status": "verify_mismatch",
                "detail": f"{rel}: {detail}",
                "path": rel, "version": version, "manifests": checked,
            }
        checked.append({"path": rel, "committed_version": version})

    return {"status": "ok", "version": version, "manifests": checked}
