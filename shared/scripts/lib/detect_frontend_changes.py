"""Detect frontend file changes in a git diff range.

Used by shipwright-build Step 8 and shipwright-iterate F2 to decide whether
Browser Verify must run. Skip only when no frontend file changed; missing
dev_server config is a resolution concern, not a skip trigger.

Usage:
    uv run {shared_root}/scripts/lib/detect_frontend_changes.py \\
      --cwd {project_root} [--since <rev>]

Default --since: merge-base between HEAD and origin/main (falls back to
HEAD~1 when no remote main exists). Pass an explicit rev for stacked
branches, e.g. "$(git merge-base HEAD {branch_name})".

Returns JSON on stdout:
    {
        "has_frontend_changes": true,
        "files": ["webui/client/src/App.tsx", "webui/client/src/index.css"]
    }
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Extensions that unambiguously belong to frontend.
FRONTEND_SUFFIXES: tuple[str, ...] = (
    ".tsx", ".jsx", ".vue", ".svelte",
    ".css", ".scss", ".sass", ".less",
    ".html",
)

# .ts / .js are ambiguous (also used for Node scripts, tooling, configs).
# Only count them as frontend when they live under these path prefixes.
FRONTEND_TS_JS_ROOTS: tuple[str, ...] = (
    "src/",
    "webui/client/",
    "frontend/",
    "app/",
    "client/",
)


def _is_frontend_path(path: str) -> bool:
    """Return True when the path is a frontend source file."""
    lower = path.lower().replace("\\", "/")
    if lower.endswith(FRONTEND_SUFFIXES):
        return True
    if lower.endswith((".ts", ".js", ".mjs", ".cjs")):
        # Must live under a known frontend root to count.
        return any(root in lower for root in FRONTEND_TS_JS_ROOTS)
    return False


def _resolve_since(cwd: Path, override: str | None) -> str:
    """Pick the diff base rev."""
    if override:
        return override
    # Prefer merge-base with origin/main.
    for ref in ("origin/main", "origin/master", "main", "master"):
        proc = subprocess.run(
            ["git", "merge-base", "HEAD", ref],
            cwd=str(cwd),
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    return "HEAD~1"


def detect(cwd: Path, since: str | None = None) -> dict:
    """Run git diff and classify changed files."""
    base = _resolve_since(cwd, since)
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {
            "has_frontend_changes": False,
            "files": [],
            "error": f"git diff failed: {proc.stderr.strip()}",
        }
    files = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    frontend = [f for f in files if _is_frontend_path(f)]
    return {
        "has_frontend_changes": bool(frontend),
        "files": frontend,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect frontend file changes")
    parser.add_argument("--cwd", required=True, help="Project working directory")
    parser.add_argument(
        "--since",
        default=None,
        help="Base git rev (default: merge-base with origin/main)",
    )
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    if not cwd.exists():
        print(json.dumps({"has_frontend_changes": False, "files": [], "error": f"cwd not found: {cwd}"}))
        return 1

    result = detect(cwd, args.since)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
