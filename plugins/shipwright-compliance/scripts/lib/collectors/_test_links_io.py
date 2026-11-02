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

from ._lib_loader import load_shared_lib
from ._test_links_profile_roots import (  # noqa: F401  (_WARNED_NO_ROOTS: re-exported, tests clear it)
    _WARNED_NO_ROOTS, profile_test_roots, warn_no_roots, warn_profile_roots_unresolved,
)

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
                # ``is_file()`` (follows symlinks) fences a broken/dangling symlink or a
                # non-regular entry named ``test_*.py``: os.walk lists it in ``filenames`` but
                # ``read_text`` would raise an uncaught ``FileNotFoundError`` (``errors='ignore'``
                # swallows only decode errors), crashing the whole regen. Matters more now the
                # scan reaches the wide plugin/shared tree, not just curated ``tests/`` roots.
                if is_test and path.is_file():
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
    # is_file() (S2b pass C4): matches the require="is_file" gate below --
    # this site is outside the 15-site planning_discovery inventory, but a
    # spec.md DIRECTORY here reached read_text() and raised the same way.
    if top.is_file():
        out.append(top)
    planning = project_root / ".shipwright" / "planning"
    iter_spec_files = load_shared_lib("planning_discovery").iter_spec_files
    # require="is_file" (S2b pass B1): a directory named spec.md is skipped.
    out.extend(iter_spec_files(
        planning, guard="is_dir", sort=True, include_iterate=False, require="is_file"
    ))
    return out


def default_test_roots(project_root: Path) -> list[Path]:
    return [project_root / d for d in _DEFAULT_TEST_DIRS if (project_root / d).is_dir()]


def _read_traceability_config(project_root: Path, *, quiet: bool = False) -> dict:
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
        if not quiet:
            sys.stderr.write(f"[test_links] shipwright_compliance_config.json unreadable ({exc}); using default roots\n")
        return {}
    if not isinstance(config, dict):  # valid JSON but a non-object root (``[]`` / ``"x"`` / ``null``)
        return {}
    block = config.get("traceability")
    return block if isinstance(block, dict) else {}


def configured_test_roots(project_root: Path, *, warn: bool = True) -> list[Path]:
    """Resolve the scan roots (see ``_resolve_test_roots``) and SAY SO when there are none.

    An empty result used to be silent: a project whose tests live below ``server/`` and
    ``client/`` has none of the conventional TOP-LEVEL folders, so zero test files were scanned
    and the coverage gate then asked for tests that already existed (GitHub issue #972). One line
    per project root per process; ``warn=False`` is for callers resolving on a throwaway tree
    (the F11 gate's archives), which carry their own diagnosis.
    """
    roots = _resolve_test_roots(project_root, warn=warn)
    if warn and not roots:
        warn_no_roots(project_root, _read_traceability_config(project_root, quiet=True).get("test_roots"),
                      _DEFAULT_TEST_DIRS)
    return roots


def _resolve_test_roots(project_root: Path, *, warn: bool = True) -> list[Path]:
    """Resolve the directories the collector scans. Tiers, first that applies wins (REPLACE, no union):

    1. ``traceability.test_roots`` in ``shipwright_compliance_config.json`` -- the project's own
       choice, used exactly (even when it resolves to zero dirs); a non-list value falls back to
       the defaults with a stderr diagnostic, never a silent revert.
    2. ``traceability.test_roots`` of the project's stack profile (``_test_links_profile_roots``)
       when at least one declared folder exists; a declared list matching nothing warns and falls on.
    3. The conventional ``_DEFAULT_TEST_DIRS`` (zero change for a project with neither).
    """
    entries = _read_traceability_config(project_root).get("test_roots")
    if entries is None:
        name, declared = profile_test_roots(project_root, warn=warn)
        if declared:
            roots = _expand_root_entries(project_root, declared)
            if roots:
                return roots
            if warn:
                warn_profile_roots_unresolved(project_root, name)
        return default_test_roots(project_root)
    if not isinstance(entries, list):
        if warn:
            sys.stderr.write("[test_links] traceability.test_roots is not a list; using default roots\n")
        return default_test_roots(project_root)
    return _expand_root_entries(project_root, entries)


def _expand_root_entries(project_root: Path, entries: list) -> list[Path]:
    """Expand ``test_roots`` entries (config AND profile alike) into existing directories.

    Each entry may be a literal dir (``shared/tests``) or a BOUNDED glob (``plugins/*/tests``);
    ``Path.glob`` resolves at the pattern's fixed depth so root resolution never descends a
    vendored tree. A ``**`` entry is skipped (it would re-introduce the rglob-descent hang the
    walk-prune fixes); a non-string / empty entry is skipped too. Each resolved dir is
    containment-checked (``os.walk`` runs ``followlinks=False``; a match resolving OUTSIDE the
    project root -- an absolute/``..``/symlink escape -- is dropped). Results are de-duplicated by
    resolved path and per-pattern sorted.
    """
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
