"""CLI wrapper for the test-hygiene static probes (Python + TS/JS).

Routes changed Python test files to ``test_hygiene`` (silent-skip-without-
CI-guard) and changed TS/JS specs to ``ts_test_hygiene`` (silent-skip ban +
quarantine-with-expiry + unconditional ``.only``/``fit`` fail, TT4).

    uv run shared/scripts/tools/scan_test_hygiene.py --diff [--json]
    uv run shared/scripts/tools/scan_test_hygiene.py --files a_test.py b.spec.ts

Exit codes: 0 = no findings; 1 = findings; 2 = usage error / no diff base.

The TS/JS leg is **diff-scoped by line**: an expired quarantine or a bare skip
only fails a PR that introduces or edits it (no calendar-based CI rot on
unrelated PRs). This CLI is the single mechanical hygiene gate — the iterate
Self-Review § 8 ("Test Hygiene Probe") and F0.5 invoke it and act on its exit
code. (The post-commit F11 verifier does NOT re-run it; F0.5/§8 is the gate.)
See ``plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md``.
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
from ts_test_hygiene import (  # noqa: E402  (path bootstrap above)
    TsFinding,
    added_lines_from_diff,
    filter_to_changed,
    is_ts_test_file,
    scan_ts_test_files,
)

_TS_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"})


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


def _changed_lines(repo_root: Path, base: str | None, rel: Path) -> set[int]:
    """New-file line numbers ``rel`` changed in the diff (line-scoping source).

    ``base`` is the default-branch name (compared as ``origin/<base>...HEAD``,
    same merge-base semantics as the Python leg); ``None`` falls back to the
    working-tree diff. Delegates hunk parsing to ``added_lines_from_diff`` so
    the diff interpretation lives in one tested place.
    """
    spec = ["-U0"] if base is None else ["-U0", f"origin/{base}...HEAD"]
    result = subprocess.run(
        ["git", "diff", *spec, "--", str(rel).replace("\\", "/")],
        capture_output=True, text=True, check=False, shell=False, cwd=repo_root,
    )
    if result.returncode != 0:
        return set()
    return added_lines_from_diff(result.stdout)


def _ts_to_finding(f: TsFinding) -> Finding:
    # Adapt a TsFinding to the common Finding for uniform output.
    return Finding(file=f.file, line=f.line, pattern=f.pattern, reason=f.reason)


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
            "Scan changed test files (vs origin/<default-branch>): Python "
            "test_*.py / *_test.py plus TS/JS *.spec.* / *.test.* specs."
        ),
    )
    group.add_argument(
        "--files",
        nargs="+",
        type=Path,
        help=(
            "Scan an explicit list of .py or TS/JS files. No naming filter — "
            "every path passed is scanned (no diff line-scoping)."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit findings as JSON instead of text.",
    )
    args = parser.parse_args(argv)

    repo_root = _git_repo_root()
    diff_base: str | None = None
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
            diff_base = base
        py_files = [p for p in candidates if _is_python_test_file(p)]
        ts_files = [p for p in candidates if is_ts_test_file(p)]
    else:
        py_files = [p for p in args.files if p.suffix == ".py"]
        ts_files = [p for p in args.files if p.suffix in _TS_SUFFIXES]
        other = [p for p in args.files if p not in py_files and p not in ts_files]
        if other:
            print(
                f"scan_test_hygiene: rejecting unsupported files: "
                f"{[str(p) for p in other]}",
                file=sys.stderr,
            )
            return 2

    findings = list(scan_for_silent_skip_without_ci_guard(py_files))

    ts_findings = scan_ts_test_files(ts_files)
    if args.diff and ts_files:  # line-scope to what the PR introduces or edits
        changed = {
            p: _changed_lines(repo_root, diff_base, p.relative_to(repo_root))
            for p in ts_files
        }
        ts_findings = filter_to_changed(ts_findings, changed)
    findings.extend(_ts_to_finding(f) for f in ts_findings)

    output = _format_json(findings) if args.json else _format_text(findings)
    sys.stdout.write(output)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
