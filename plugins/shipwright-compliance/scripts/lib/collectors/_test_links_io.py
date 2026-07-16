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
import os
import subprocess
import sys
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


def iter_test_files(roots: list[Path], base: Path, prune_dirs: frozenset[str] = _PRUNE_DIRS):
    """Yield ``(abs_path, rel_path)`` for every test source file under ``roots``.

    Descent-pruned (``os.walk`` + in-place ``dirnames[:]``): a vendored/build subtree whose
    name is in ``prune_dirs`` is never DESCENDED into — no O(all-files) rglob materialize+sort
    of a large committed ``node_modules`` (the TT7 fix, reused here). Files are collected +
    sorted per-root, so the manifest order is deterministic and byte-identical to the prior
    rglob scan for any tree with no prune-named ancestor.
    """
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        found: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):  # followlinks=False (default): no symlink escape
            dirnames[:] = sorted(d for d in dirnames if d not in prune_dirs)  # prune + order before descent
            for name in filenames:
                path = Path(dirpath) / name
                if path.suffix.lower() not in _SRC_SUFFIXES:
                    continue
                low = name.lower()
                is_test = (
                    low.startswith("test_") or low.endswith("_test.py")
                    or ".test." in low or ".spec." in low
                )
                if is_test:
                    found.append(path)
        for path in sorted(found):
            if path in seen:
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


def _read_traceability_config(project_root: Path) -> dict:
    """Return the ``traceability`` block of ``shipwright_compliance_config.json`` — an empty
    dict when the file/key is absent or unreadable (⇒ the historical default behavior)."""
    path = project_root / "shipwright_compliance_config.json"
    if not path.exists():
        return {}
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        # A PRESENT-but-unreadable config (garbled JSON, a leading BOM, an IO error) silently
        # disables the opt-in — surface it so the fallback-to-default is observable, not silent.
        sys.stderr.write(f"[test_links] shipwright_compliance_config.json unreadable ({exc}); using default roots\n")
        return {}
    if not isinstance(config, dict):  # valid JSON but a non-object root (``[]`` / ``"x"`` / ``null``)
        return {}
    block = config.get("traceability")
    return block if isinstance(block, dict) else {}


def configured_test_roots(project_root: Path) -> list[Path]:
    """Resolve the directories the collector scans, honoring an optional project opt-in.

    Reads ``traceability.test_roots`` (dir names / fixed-depth globs relative to the project
    root) from ``shipwright_compliance_config.json``. ABSENT ⇒ the collector keeps its exact
    historical scope — the conventional ``_DEFAULT_TEST_DIRS`` (zero change for every existing
    project + the frozen fixtures). PRESENT ⇒ exactly those roots, so a monorepo opts its
    ``plugins/*/tests`` + ``shared/tests`` in via config rather than the shared collector
    hardcoding any repo layout.

    Each entry may be a literal dir (``shared/tests``) or a BOUNDED glob (``plugins/*/tests``);
    ``Path.glob`` resolves at the pattern's fixed depth so root resolution never descends a
    vendored tree. A ``**`` entry is skipped (it would re-introduce the rglob-descent hang the
    walk-prune fixes); a non-string / empty entry is skipped too. Presence is authoritative — a
    PRESENT list is used exactly (each valid entry resolved, even if it resolves to zero dirs);
    only an ABSENT key or a non-list value falls back to the default (the latter with a stderr
    diagnostic, never a silent revert). Each resolved dir is containment-checked (``os.walk`` runs
    ``followlinks=False``; a match resolving OUTSIDE the project root — an absolute/``..``/symlink
    escape — is dropped). Results are de-duplicated by resolved path and per-pattern sorted.
    """
    entries = _read_traceability_config(project_root).get("test_roots")
    if entries is None:
        return default_test_roots(project_root)                     # key absent → historical default
    if not isinstance(entries, list):
        sys.stderr.write("[test_links] traceability.test_roots is not a list; using default roots\n")
        return default_test_roots(project_root)
    root = project_root.resolve()
    roots: list[Path] = []
    seen: set[Path] = set()
    for entry in entries:
        if not isinstance(entry, str) or not entry or "**" in entry:
            continue
        try:
            matches = sorted(project_root.glob(entry))
        except (ValueError, NotImplementedError, OSError):
            continue  # absolute / unsupported pattern → dropped, never a crashed regen
        for match in matches:
            resolved = match.resolve()
            if match.is_dir() and resolved not in seen and resolved.is_relative_to(root):
                seen.add(resolved)
                roots.append(match)
    return roots


def configured_prune_dirs(project_root: Path) -> frozenset[str]:
    """Dir names pruned DURING descent: the built-in vendored/build ``_PRUNE_DIRS`` plus any
    ``traceability.exclude_dirs`` the project adds. A monorepo excludes ``fixtures`` so the
    collector's OWN traceability test-fixtures (mini-repos carrying deliberately fake ``@FR``
    tags) never pollute the real manifest. ABSENT ⇒ exactly ``_PRUNE_DIRS`` (no change)."""
    extra = _read_traceability_config(project_root).get("exclude_dirs")
    if not isinstance(extra, list):
        return _PRUNE_DIRS
    names = {e for e in extra if isinstance(e, str) and e}
    return _PRUNE_DIRS | names if names else _PRUNE_DIRS


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
    "discover_specs", "default_test_roots", "configured_test_roots", "configured_prune_dirs",
    "load_evidence", "git_head", "_ZERO_SHA",
]
