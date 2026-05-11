"""CLI wrapper for ``shared/scripts/lib/test_hygiene.py``'s static probe.

Usage:

    # Scan the changed Python test files in the current branch
    uv run shared/scripts/tools/scan_test_hygiene.py --diff

    # Scan explicit files
    uv run shared/scripts/tools/scan_test_hygiene.py --files path/to/test.py path/to/other.py

    # Emit JSON for machine consumption
    uv run shared/scripts/tools/scan_test_hygiene.py --diff --json

Exit codes:
- 0 — no findings
- 1 — one or more findings reported (silent-skip-without-CI-guard)
- 2 — usage error / unable to resolve diff base

The CLI is the mechanically-executable handle that the iterate
Self-Review § 8 ("Test Hygiene Probe") invokes. See
``plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md``
for the gate semantics (mandatory at medium+, advisory below).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
# `shared/scripts/` must be on the path so `from test_hygiene` works
# when the CLI is invoked directly via `uv run <path>` from the repo root.
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from test_hygiene import (  # noqa: E402  (path bootstrap above)
    Finding,
    scan_for_silent_skip_without_ci_guard,
)


def _git_repo_root() -> Path:
    """Resolve the repo root via ``git rev-parse --show-toplevel``.

    Used so the diff resolves regardless of cwd. Subprocess uses
    explicit argv (no ``shell=True``) per external-review #G5 / #O11.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    if result.returncode != 0:
        return REPO_ROOT
    return Path(result.stdout.strip())


def _default_branch(repo_root: Path) -> str | None:
    """Resolve the default branch name via the remote HEAD symref.

    Returns None when no remote default is configured — caller emits an
    actionable error rather than guessing ``main`` (external-review #O2).
    """
    result = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        return None
    ref = result.stdout.strip()
    # Strip the `refs/remotes/origin/` prefix.
    if ref.startswith("refs/remotes/origin/"):
        return ref.removeprefix("refs/remotes/origin/")
    return None


def _head_is_default_branch(repo_root: Path, base_ref: str) -> bool:
    """True if local HEAD matches origin/<base_ref> — i.e. the user is on
    the default branch with nothing ahead of it.

    Detects the false-green scenario (code-review MEDIUM-3): running
    ``scan_test_hygiene.py --diff`` on freshly-pulled ``main`` would
    silently scan zero files and exit 0, masking the Self-Review § 8
    intent.
    """
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False, shell=False,
        cwd=repo_root,
    )
    remote = subprocess.run(
        ["git", "rev-parse", f"origin/{base_ref}"],
        capture_output=True, text=True, check=False, shell=False,
        cwd=repo_root,
    )
    if head.returncode != 0 or remote.returncode != 0:
        return False
    return head.stdout.strip() == remote.stdout.strip()


def _diff_files(repo_root: Path, base_ref: str | None) -> list[Path]:
    """Return changed-file Paths between ``base_ref`` and HEAD.

    Falls back to ``git diff --name-only`` (working tree changes) when
    ``base_ref`` is None — useful when the user is on the default branch
    itself or pre-PR with no merge base.
    """
    if base_ref is None:
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            cwd=repo_root,
        )
    else:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"origin/{base_ref}...HEAD"],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            cwd=repo_root,
        )
    if result.returncode != 0:
        return []
    return [
        repo_root / line
        for line in result.stdout.splitlines()
        if line.strip()
    ]


def _is_python_test_file(path: Path) -> bool:
    """True if path is a Python file matching one of the test conventions.

    Used only for ``--diff``-mode filtering (external-review #O8). When
    the user passes explicit ``--files`` we do NOT filter — they asked
    for those files, scan them.
    """
    name = path.name
    return path.suffix == ".py" and (
        name.startswith("test_") or name.endswith("_test.py")
    )


def _format_text(findings: list[Finding]) -> str:
    """Human-readable rendering for the default (non-JSON) output."""
    if not findings:
        return "test_hygiene: no findings\n"
    lines = [f"test_hygiene: {len(findings)} finding(s)\n"]
    for f in findings:
        lines.append(
            f"  {f.file}:{f.line}  [{f.pattern}]  {f.reason}"
        )
    return "\n".join(lines) + "\n"


def _format_json(findings: list[Finding]) -> str:
    payload = {
        "findings_count": len(findings),
        "findings": [
            {**asdict(f), "file": str(f.file)} for f in findings
        ],
    }
    return json.dumps(payload, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scan_test_hygiene",
        description=(
            "Scan Python test files for silent-skip patterns lacking a "
            "CI-gated fail branch. See ADR-044 / ADR-045."
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--diff",
        action="store_true",
        help=(
            "Scan changed test files (vs origin/<default-branch>). "
            "Filter restricts to test_*.py / *_test.py."
        ),
    )
    group.add_argument(
        "--files",
        nargs="+",
        type=Path,
        help=(
            "Scan an explicit list of .py files. No naming filter — "
            "every path passed is scanned. Caller-controlled."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit findings as JSON instead of text.",
    )
    args = parser.parse_args(argv)

    repo_root = _git_repo_root()
    if args.diff:
        base = _default_branch(repo_root)
        if base is None:
            print(
                "scan_test_hygiene: could not resolve origin/HEAD — pass "
                "--files instead, or `git remote set-head origin -a`.",
                file=sys.stderr,
            )
            return 2
        # Code-review MEDIUM-3: detect the false-green where the user is on
        # the default branch and `origin/main...HEAD` is empty. Fall back
        # to working-tree diff with an informational stderr message.
        if _head_is_default_branch(repo_root, base):
            print(
                f"scan_test_hygiene: HEAD == origin/{base} — no branch diff "
                f"to scan. Falling back to working-tree changes; pass "
                f"--files for an explicit list.",
                file=sys.stderr,
            )
            candidates = _diff_files(repo_root, None)
        else:
            candidates = _diff_files(repo_root, base)
        files = [p for p in candidates if _is_python_test_file(p)]
    else:
        files = [Path(p) for p in args.files]
        non_python = [p for p in files if p.suffix != ".py"]
        if non_python:
            print(
                f"scan_test_hygiene: rejecting non-Python files: "
                f"{[str(p) for p in non_python]}",
                file=sys.stderr,
            )
            return 2

    findings = scan_for_silent_skip_without_ci_guard(files)
    output = _format_json(findings) if args.json else _format_text(findings)
    sys.stdout.write(output)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
