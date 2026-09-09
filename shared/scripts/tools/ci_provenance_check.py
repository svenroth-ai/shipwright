#!/usr/bin/env python3
"""CLI wrapper around ``ci_provenance.resolve_ci_verification()`` — asks
GitHub, for a given commit, whether its traceability manifest was verified
by a real trunk CI run. See `ci_provenance.py`'s module docstring for the
full design (P3.4c, iterate-2026-09-08-ci-provenance-attestation).

    uv run shared/scripts/tools/ci_provenance_check.py verify \\
        --commit <sha> --project-root .

`--commit` accepts anything `git rev-parse` can resolve (a full or
abbreviated SHA, `HEAD`, a tag) — this CLI's ONE local read expands it to
the full 40-char SHA before querying GitHub, since `head_sha` on the
workflow-runs API requires an exact match and an unexpanded abbreviation
would silently under-match into a false `no_record`. `resolve_ci_verification`
itself still reads nothing from the local tree.

Exit codes: 0 verified · 3 not_verified · 4 no_record · 2 error (the query
itself could not complete, `git rev-parse` could not resolve `--commit`, or
the resolved value is not a valid SHA shape) — `error` and `no_record` are
deliberately distinct (see `ci_provenance.py`).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ci_provenance import resolve_ci_verification  # noqa: E402

_EXIT_CODES = {"verified": 0, "not_verified": 3, "no_record": 4, "error": 2}
_REV_PARSE_TIMEOUT_SECONDS = 10


def _resolve_full_sha(commit: str, project_root: Path) -> str | None:
    """Expand ``commit`` to a full 40-char SHA via ``git -C <project_root>
    rev-parse`` — the CLI's one local read, never a manifest file. Returns
    ``None`` if git could not resolve it (unknown ref, not a git repo,
    `git` missing, timeout)."""
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"],
            capture_output=True,
            text=True,
            timeout=_REV_PARSE_TIMEOUT_SECONDS,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="ask whether a commit's manifest was CI-verified")
    verify.add_argument("--commit", required=True)
    verify.add_argument("--project-root", default=".", type=Path)
    args = ap.parse_args(argv)

    project_root = args.project_root.resolve()
    full_sha = _resolve_full_sha(args.commit, project_root)
    if full_sha is None:
        print(json.dumps({"status": "error", "detail": f"could not resolve {args.commit!r} via git rev-parse", "run_id": None}))
        return _EXIT_CODES["error"]

    result = resolve_ci_verification(full_sha, project_root=project_root)
    print(json.dumps({"status": result.status, "detail": result.detail, "run_id": result.run_id}))
    return _EXIT_CODES.get(result.status, 2)


if __name__ == "__main__":
    raise SystemExit(main())
