"""Layer 1 of the artifact-relocation drift safety net.

Forbids any reference to a *legacy* artifact path (per
``ARTIFACT_MIGRATIONS``) outside the per-migration allowlist.

Two scan modes:

- **Text-regex** on ``.py .md .json .yaml .yml .toml .sh .gitignore``.
  Catches obvious string literals (``"planning"``, ``planning/``,
  ``planning\\`` for Windows, ``'planning'``).

- **Python AST** on ``.py``. Walks every ``Constant`` node whose value
  equals the migration's ``ast_check_string`` and reports it when used
  inside a path-construction context: ``Path(...)``, ``os.path.join(...)``,
  the ``/`` operator with a Path on either side, an f-string segment
  before ``/``, or an argparse/function default.

Allowlist mechanisms (any one suffices):
- File-path allowlist in ``ARTIFACT_MIGRATIONS`` ``ALLOWLIST[name]``
  (exact paths or globs, repo-relative, POSIX form).
- Inline marker comment containing ``artifact-path-canon: legacy``
  (Python ``#``, HTML ``<!-- -->`` — JSON has no comment syntax, so use
  the file-path allowlist for those).

Run: ``cd shared && uv run pytest tests/test_artifact_path_canon.py -v``
"""
from __future__ import annotations

import ast
import fnmatch
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import pytest

# Import the manifest. ``shared/tests/conftest.py`` already inserts
# ``shared/scripts`` into ``sys.path``.
from lib.artifact_migrations import (  # noqa: E402
    ALLOWLIST,
    ARTIFACT_MIGRATIONS,
    INLINE_MARKER,
)


# ---------------------------------------------------------------------------
# Repo discovery
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def _git_tracked_files() -> list[str]:
    """Return all repo-tracked files as POSIX-relative strings.

    Cached for the test session so the lint runs only once on Windows
    (where ``subprocess`` startup is comparatively expensive).
    """
    try:
        out = subprocess.run(
            ["git", "ls-files"],
            cwd=_REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    # ``git ls-files`` emits POSIX paths even on Windows.
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


_LINT_EXTENSIONS = {
    ".py", ".md", ".json", ".yaml", ".yml", ".toml", ".sh",
}
_LINT_BASENAMES = {".gitignore"}


def _eligible_files(migration: dict) -> Iterable[tuple[str, Path]]:
    """Yield ``(rel_path, abs_path)`` for files this migration should scan."""
    allowlist = ALLOWLIST.get(migration["name"], [])
    for rel in _git_tracked_files():
        path = _REPO_ROOT / rel
        if not path.is_file():
            continue
        if path.suffix not in _LINT_EXTENSIONS and path.name not in _LINT_BASENAMES:
            continue
        if _path_matches_any(rel, allowlist):
            continue
        yield rel, path


def _path_matches_any(rel_path: str, patterns: Iterable[str]) -> bool:
    """True when *rel_path* matches any glob in *patterns* (POSIX form)."""
    for pat in patterns:
        # Normalize Windows-style separators in the pattern itself.
        pat_posix = pat.replace("\\", "/")
        if fnmatch.fnmatch(rel_path, pat_posix):
            return True
        # Also try matching against the basename — some allowlist entries
        # use just a filename glob (e.g. ``project_paths_refactor_evaluated.md``).
        if fnmatch.fnmatch(Path(rel_path).name, pat_posix):
            return True
    return False


# ---------------------------------------------------------------------------
# Text-regex scan
# ---------------------------------------------------------------------------


def _text_violations(rel: str, path: Path, patterns: list[re.Pattern]) -> list[dict]:
    """Return one finding per regex match outside an inline-marker line."""
    findings: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return findings
    for lineno, line in enumerate(text.splitlines(), start=1):
        if INLINE_MARKER in line:
            continue
        for pat in patterns:
            if pat.search(line):
                findings.append({
                    "file": rel,
                    "line": lineno,
                    "mode": "text-regex",
                    "pattern": pat.pattern,
                    "snippet": line.strip()[:120],
                })
                break  # one finding per line is enough
    return findings


# ---------------------------------------------------------------------------
# AST scan (Python only)
# ---------------------------------------------------------------------------


_PATH_BUILDER_NAMES = {"Path", "PurePath", "PosixPath", "WindowsPath"}


class _AstFinder(ast.NodeVisitor):
    """Collect every string-literal usage that *looks like* a path segment."""

    def __init__(self, target: str):
        self.target = target
        self.findings: list[tuple[int, str]] = []

    def _is_target(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Constant) and node.value == self.target

    def visit_Call(self, node: ast.Call) -> None:
        # Path("planning"), pathlib.Path("planning"), os.path.join(..., "planning", ...)
        is_path_call = (
            (isinstance(node.func, ast.Name) and node.func.id in _PATH_BUILDER_NAMES)
            or (isinstance(node.func, ast.Attribute) and node.func.attr in _PATH_BUILDER_NAMES)
        )
        is_join = (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "join"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "path"
        )
        if is_path_call or is_join:
            for arg in node.args:
                if self._is_target(arg):
                    self.findings.append((node.lineno, "Path/join argument"))
        # default= in argparse add_argument(...)
        for kw in node.keywords:
            if kw.arg == "default" and self._is_target(kw.value):
                self.findings.append((node.lineno, "argparse/function default"))
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        # Path division: <expr> / "planning"  or  "planning" / <expr>.
        # Skip the canonical migrated form: <expr> / ".shipwright" / "planning"
        # (the legacy-target string is the right operand BUT the LHS is
        # itself a `<expr> / ".shipwright"` chain).
        if isinstance(node.op, ast.Div):
            if self._is_target(node.right):
                if self._is_post_shipwright_chain(node.left):
                    pass  # canonical form, not a violation
                else:
                    self.findings.append((node.lineno, "Path '/' operator"))
            elif self._is_target(node.left):
                self.findings.append((node.lineno, "Path '/' operator"))
        self.generic_visit(node)

    def _is_post_shipwright_chain(self, node: ast.AST) -> bool:
        """True if *node* is ``<expr> / ".shipwright"`` (any depth on left)."""
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Div):
            return False
        if isinstance(node.right, ast.Constant) and node.right.value == ".shipwright":
            return True
        return False

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        # f-strings — match only if the target appears as the FIRST segment
        # (legacy path root), not as an inner segment of an already-migrated
        # path like ``.shipwright/planning/...``.
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                segments = re.split(r"[/\\]", v.value)
                if segments and segments[0] == self.target:
                    self.findings.append((node.lineno, "f-string path segment"))
                    break
        self.generic_visit(node)


def _ast_violations(rel: str, path: Path, target: str) -> list[dict]:
    if path.suffix != ".py":
        return []
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=rel)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []
    finder = _AstFinder(target)
    finder.visit(tree)

    # Filter out lines bearing the inline marker.
    lines = text.splitlines()
    findings: list[dict] = []
    for lineno, context in finder.findings:
        line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
        if INLINE_MARKER in line:
            continue
        findings.append({
            "file": rel,
            "line": lineno,
            "mode": "ast",
            "pattern": context,
            "snippet": line.strip()[:120],
        })
    return findings


# ---------------------------------------------------------------------------
# Public test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "migration",
    [m for m in ARTIFACT_MIGRATIONS if m["status"] in ("in_progress", "migrated")],
    ids=lambda m: f"{m['name']}-{m['status']}",
)
def test_no_legacy_artifact_paths(migration: dict) -> None:
    """No legacy-path string literals outside the allowlist."""
    if not _git_tracked_files():
        pytest.skip("git ls-files unavailable — running outside a git checkout")

    patterns = [re.compile(p) for p in migration["old_path_patterns"]]
    target = migration["ast_check_string"]
    all_findings: list[dict] = []
    for rel, path in _eligible_files(migration):
        all_findings.extend(_text_violations(rel, path, patterns))
        all_findings.extend(_ast_violations(rel, path, target))

    if not all_findings:
        return

    name = migration["name"]
    canonical = migration["canonical"]
    msg_lines = [
        f"\nLayer-1 canon lint failed for migration `{name}` "
        f"(status: {migration['status']}). Found {len(all_findings)} legacy-path "
        f"reference(s) outside the allowlist.\n",
        f"Canonical path: `{canonical}`. Fix options per finding:",
        f"  1) replace literal with `{canonical}` (or its constant)",
        f"  2) add inline marker `# {INLINE_MARKER}` on the offending line",
        f"  3) extend ALLOWLIST['{name}'] in shared/scripts/lib/artifact_migrations.py",
        "",
    ]
    # Group by file for readability; cap at 30 findings in the message.
    grouped: dict[str, list[dict]] = {}
    for f in all_findings:
        grouped.setdefault(f["file"], []).append(f)
    shown = 0
    for file_, hits in grouped.items():
        msg_lines.append(f"  {file_}:")
        for h in hits[:8]:
            msg_lines.append(
                f"    L{h['line']:>4} [{h['mode']}] {h['pattern']!s} → {h['snippet']}"
            )
            shown += 1
            if shown >= 30:
                break
        if len(hits) > 8:
            msg_lines.append(f"    ... +{len(hits) - 8} more in this file")
        if shown >= 30:
            msg_lines.append(f"  ... +{len(all_findings) - shown} more findings hidden")
            break

    pytest.fail("\n".join(msg_lines))
