#!/usr/bin/env python3
"""Publish (or detect) a GitHub Release for an already-pushed tag.

Best-effort by design (Iterate Spec AC: never blocks
``/shipwright-changelog``'s phase completion) — every branch below returns a
structured result instead of raising, EXCEPT a genuinely invalid ``version``
argument (programmer error, not an environment condition).

Preflight order, each a distinct reported status:
1. ``gh --version`` — below the ``--verify-tag`` minimum (2.49) → skipped
2. ``gh auth status --hostname github.com`` — not on PATH / unauthenticated → skipped
3. version string validated against a strict semver grammar BEFORE it ever
   reaches argv (closes the leading-dash-as-flag injection class)
4. repo identity resolved once (``repo_identity.resolve_repo_identity``) and
   passed explicitly as ``--repo owner/repo`` to every ``gh`` call — never
   left to ``gh``'s cwd inference
5. ``gh release view {tag} --repo {identity}`` — a CONFIRMED not-found is the
   only path that proceeds to create; any OTHER failure (network, auth, API
   error) short-circuits to ``failed`` WITHOUT attempting create; a found
   release returns ``exists`` and never attempts create
6. ``gh release create {tag} --notes-file {path} --title {tag} --verify-tag
   --repo {identity}`` — ``--verify-tag`` means gh itself refuses to
   auto-create a divergent tag at the branch tip if the push silently failed

CLI:

    uv run shared/scripts/tools/create_github_release.py \\
        --project-root . --version 1.2.3 --notes-file <path>

Output JSON: ``{"status": "ok"|"exists"|"skipped"|"failed", "url": "...",
"reason": "..."}`` (fields present per status).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from repo_identity import resolve_repo_identity  # noqa: E402

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(-[\w.]+)?$")
_MIN_GH_VERSION = (2, 49, 0)  # gh 2.49.0 shipped --verify-tag
_STDERR_EXCERPT_CHARS = 500


def _run(args: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
    )


def _gh_version() -> tuple[int, int, int] | None:
    try:
        result = _run(["gh", "--version"])
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    match = re.search(r"gh version (\d+)\.(\d+)\.(\d+)", result.stdout)
    if not match:
        return None
    return (int(match[1]), int(match[2]), int(match[3]))


def _gh_authenticated() -> bool:
    try:
        result = _run(["gh", "auth", "status", "--hostname", "github.com"])
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _release_view(tag: str, repo: str) -> dict:
    """Returns ``{"exists": True, "url": ...}`` / ``{"exists": False}`` /
    ``{"exists": None, "reason": ...}`` (indeterminate — a real failure)."""
    try:
        result = _run(["gh", "release", "view", tag, "--repo", repo, "--json", "url"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"exists": None, "reason": f"gh release view failed to run: {exc}"}
    if result.returncode == 0:
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = {}
        return {"exists": True, "url": payload.get("url")}
    stderr = result.stderr or ""
    if "release not found" in stderr.lower() or "404" in stderr:
        return {"exists": False}
    return {"exists": None, "reason": stderr.strip()[:_STDERR_EXCERPT_CHARS]}


def create_release(
    version: str, notes_file: Path, project_root: Path
) -> dict:
    gh_version = _gh_version()
    if gh_version is None:
        return {"status": "skipped", "reason": "gh_not_found"}
    if gh_version < _MIN_GH_VERSION:
        return {
            "status": "skipped",
            "reason": f"unsupported_gh_version:{'.'.join(map(str, gh_version))}",
        }

    if not _gh_authenticated():
        return {"status": "skipped", "reason": "gh_unauthenticated"}

    if not _VERSION_RE.match(version):
        return {"status": "failed", "reason": f"invalid version string: {version!r}"}

    repo_identity = resolve_repo_identity(project_root)
    if not repo_identity:
        return {"status": "skipped", "reason": "repo_identity_unresolved"}

    tag = f"v{version}"

    view = _release_view(tag, repo_identity)
    if view["exists"] is True:
        return {"status": "exists", "url": view.get("url")}
    if view["exists"] is None:
        return {"status": "failed", "reason": f"release_view_failed:{view.get('reason')}"}

    if not notes_file.is_file():
        return {"status": "failed", "reason": f"notes file not found: {notes_file}"}

    try:
        result = _run(
            [
                "gh", "release", "create", tag,
                "--notes-file", str(notes_file),
                "--title", tag,
                "--verify-tag",
                "--repo", repo_identity,
            ],
            timeout=60.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "failed", "reason": f"gh release create failed to run: {exc}"}

    if result.returncode != 0:
        return {
            "status": "failed",
            "reason": (result.stderr or result.stdout).strip()[:_STDERR_EXCERPT_CHARS],
        }
    return {"status": "ok", "url": result.stdout.strip()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--version", required=True, help="e.g. 1.2.3 (no leading 'v')")
    parser.add_argument("--notes-file", required=True)
    args = parser.parse_args(argv)

    result = create_release(
        args.version, Path(args.notes_file), Path(args.project_root).resolve()
    )
    print(json.dumps(result, indent=2))
    return 0  # non-fatal by contract — the caller reads "status", never the exit code


if __name__ == "__main__":
    sys.exit(main())
