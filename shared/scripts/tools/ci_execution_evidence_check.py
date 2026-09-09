#!/usr/bin/env python3
"""CLI wrapper around ``ci_execution_evidence.resolve_execution_evidence()``
— asks, for a given commit, whether GitHub Actions produced CI-confirmed
per-requirement ``tests``/``coverage`` evidence bound to that exact commit's
manifest (P3.5 restart round 2,
``.shipwright/planning/iterate/2026-09-09-p3-5-promote-layers-per-fr-restart.md``,
``## New: standalone read-only CLI wrapper``). Mirrors ``ci_provenance_check.
py``'s own shape.

    uv run shared/scripts/tools/ci_execution_evidence_check.py check \\
        --commit <ref> --project-root .

``--commit`` accepts anything ``git rev-parse`` can resolve (a full or
abbreviated SHA, ``HEAD``, a tag) — expanded to the full 40-char SHA first,
same rationale as ``ci_provenance_check.py``. The commit's manifest is then
read via the same commit-pinned ``git show <sha>:<path>`` pattern
``promote_required_layers._read_committed_manifest`` uses (never the
working-tree copy), and passed to ``resolve_execution_evidence`` for the
content-binding check.

**Always exits 0** — this is a pure diagnostic. It never gates anything and
never writes anything (no ``spec.md``, no ledger); the only way to change
either of those is ``promote_required_layers.py`` itself. Built now (not
deferred) because this restart's own operating-context finding means the
first real invocation from an iterate worktree, or against a ``main`` tip
with pre-existing structural drift, reports ``unavailable`` for every FR —
by design — and an operator needs a way to ask "why" without running the
tool that actually writes ``spec.md``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from ci_execution_evidence import resolve_execution_evidence  # noqa: E402

_REV_PARSE_TIMEOUT_SECONDS = 10
_GIT_SHOW_TIMEOUT_SECONDS = 15
_MANIFEST_RELPATH = ".shipwright/compliance/test-traceability.json"


def _resolve_full_sha(commit: str, project_root: Path) -> str | None:
    """Expand ``commit`` to a full 40-char SHA via ``git -C <project_root>
    rev-parse`` — the CLI's one local ref-resolution read. Returns ``None``
    if git could not resolve it (unknown ref, not a git repo, ``git``
    missing, timeout)."""
    try:
        result = subprocess.run(  # nosec B603,B607 - fixed argv, shell=False
            ["git", "-C", str(project_root), "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"],
            capture_output=True,
            text=True,
            timeout=_REV_PARSE_TIMEOUT_SECONDS,
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def _read_manifest_at(sha: str, project_root: Path) -> tuple[dict | None, str | None]:
    """``(manifest, None)`` on success, ``(None, detail)`` on any failure —
    same commit-pinned ``git show`` pattern as
    ``promote_required_layers._read_committed_manifest``, kept independent
    (not imported) so this diagnostic never depends on that CLI's own
    argument/locking machinery."""
    try:
        show = subprocess.run(  # nosec B603,B607 - fixed argv, shell=False
            ["git", "-C", str(project_root), "show", f"{sha}:{_MANIFEST_RELPATH}"],
            capture_output=True,
            text=True,
            timeout=_GIT_SHOW_TIMEOUT_SECONDS,
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"could not run 'git show {sha}:...': {exc}"
    if show.returncode != 0:
        return None, f"could not read {_MANIFEST_RELPATH!r} at {sha}: {show.stderr.strip()}"
    try:
        manifest = json.loads(show.stdout)
    except ValueError as exc:
        return None, f"manifest at {sha} is not valid JSON: {exc}"
    if not isinstance(manifest, dict):
        return None, f"manifest at {sha} is not a JSON object"
    return manifest, None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="ask whether a commit has CI-confirmed execution evidence")
    check.add_argument("--commit", required=True)
    check.add_argument("--project-root", default=".", type=Path)
    args = ap.parse_args(argv)

    project_root = args.project_root.resolve()
    full_sha = _resolve_full_sha(args.commit, project_root)
    if full_sha is None:
        print(json.dumps({
            "status": "error",
            "detail": f"could not resolve {args.commit!r} via git rev-parse",
            "run_id": None, "fr_count": None,
        }))
        return 0

    manifest, read_error = _read_manifest_at(full_sha, project_root)
    if read_error is not None:
        print(json.dumps({"status": "error", "detail": read_error, "run_id": None, "fr_count": None}))
        return 0

    result = resolve_execution_evidence(full_sha, committed_manifest=manifest, project_root=project_root)
    fr_count = len(result.requirements) if result.status == "confirmed" and result.requirements is not None else None
    print(json.dumps({
        "status": result.status, "detail": result.detail,
        "run_id": result.run_id, "fr_count": fr_count,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
