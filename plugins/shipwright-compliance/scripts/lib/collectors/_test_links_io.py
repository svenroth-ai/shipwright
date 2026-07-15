"""IO + discovery helpers for the ``test_links`` collector (traceability TT1).

Split out of ``test_links.py`` to keep both modules under the 300-LOC cap (ADR-099):
this file owns the filesystem-facing side (which files are tests, which layer, spec
discovery, evidence load, git head, spec hash); ``test_links.py`` owns the pure
tag→FR→manifest assembly. Nothing here writes.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

_ZERO_SHA = "0" * 40
_PY_SUFFIXES = (".py",)
_TS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts")
_SRC_SUFFIXES = _PY_SUFFIXES + _TS_SUFFIXES
# Conventional roots generate_file scans in a real project. Comprehensive repo-wide
# discovery (and the untagged inventory) is the backfill engine's job (TT6/TT8).
_DEFAULT_TEST_DIRS = (
    "tests", "test", "__tests__", "e2e", "integration-tests", "src", "app", "packages",
)
_PRUNE_DIRS = frozenset({
    "node_modules", ".git", ".venv", "venv", "__pycache__", ".worktrees", "dist",
    "build", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".next",
})
# Directory names + filename infixes that mark the integration layer. Both the
# `tests/integration/` dir AND the top-level `integration-tests/` dir count (the
# integration-tests.md.template globs `**/tests/integration/**,**/*.integration.test.*`).
_INTEGRATION_DIRS = frozenset({"integration", "integration-tests"})


def detect_layer(rel_path: str) -> str:
    """Classify a test file's layer from its path (unit | integration | e2e)."""
    norm = rel_path.replace("\\", "/").lower()
    parts = norm.split("/")
    name = parts[-1]
    if "e2e" in parts or ".e2e." in name:
        return "e2e"
    if _INTEGRATION_DIRS & set(parts) or ".integration.test." in name or ".integration.spec." in name:
        return "integration"
    if name.endswith((".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx")):
        return "e2e"  # Playwright spec convention
    return "unit"


def enumerate_tests(rel_path: str, source: str, grammar) -> list[str]:
    """Return every test id (``path::name``) declared in a file — tagged or not.

    Uses the SAME name/title extraction as ``fr_tag_grammar`` (pytest AST func names;
    the shared ``_TEST_DECL_RE`` for TS/JS) so an enumerated id is byte-identical to
    the parser's binding id — untagged = enumerated − tagged, with no drift.
    """
    low = rel_path.lower()
    if low.endswith(_PY_SUFFIXES):
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        return [
            f"{rel_path}::{n.name}"
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")
        ]
    if low.endswith(_TS_SUFFIXES):
        out = []
        for line in source.splitlines():
            m = grammar._TEST_DECL_RE.search(line)  # shared decl matcher — no divergence
            if m:
                out.append(f"{rel_path}::{m.group('title')}")
        return out
    return []


def iter_test_files(roots: list[Path], base: Path):
    """Yield ``(abs_path, rel_path)`` for every test source file under ``roots``."""
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in _SRC_SUFFIXES:
                continue
            if any(part in _PRUNE_DIRS for part in path.parts):
                continue
            name = path.name.lower()
            is_test = (
                name.startswith("test_") or name.endswith("_test.py")
                or ".test." in name or ".spec." in name
            )
            if not is_test or path in seen:
                continue
            seen.add(path)
            yield path, path.relative_to(base).as_posix()


def rel(path, project_root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(project_root).resolve()).as_posix()
    except ValueError:
        return Path(path).name


def spec_hash(spec_texts: list[str]) -> str:
    digest = hashlib.sha256("\n".join(sorted(spec_texts)).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def discover_specs(project_root: Path) -> list[Path]:
    out: list[Path] = []
    top = project_root / ".shipwright" / "agent_docs" / "spec.md"
    if top.exists():
        out.append(top)
    planning = project_root / ".shipwright" / "planning"
    if planning.is_dir():
        for d in sorted(planning.iterdir()):
            if d.is_dir() and d.name != "iterate" and (d / "spec.md").exists():
                out.append(d / "spec.md")
    return out


def default_test_roots(project_root: Path) -> list[Path]:
    return [project_root / d for d in _DEFAULT_TEST_DIRS if (project_root / d).is_dir()]


def load_evidence(project_root: Path) -> dict:
    path = project_root / ".shipwright" / "compliance" / "test-evidence-index.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("results", {})
    except (json.JSONDecodeError, OSError):
        return {}


def git_head(project_root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or _ZERO_SHA
    except (OSError, subprocess.SubprocessError):
        return _ZERO_SHA


__all__ = [
    "detect_layer", "enumerate_tests", "iter_test_files", "rel", "spec_hash",
    "discover_specs", "default_test_roots", "load_evidence", "git_head", "_ZERO_SHA",
]
