"""Adopt repo-wide skip inventory (traceability TT7, Spec §11-R5).

The standing skip/quarantine/focused-test rot across a brownfield repo — the rot TT4's
diff-scoped gate cannot see. Reuses the TT4 hygiene scanners (``test_hygiene`` /
``ts_test_hygiene``, top-level ``shared/scripts`` modules, imported lazily) and supplements
the Python side with a local ``@pytest.mark.skip`` scan (the commonest disable idiom the
shared scanner does not flag).

Split out of ``traceability_baseline`` only to keep both modules under the 300-LOC source
cap. Imports no ``lib`` package — importing this module binds no ``sys.modules['lib']``.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

_PRUNE_DIRS = frozenset({
    "node_modules", ".git", ".venv", "venv", "__pycache__", ".worktrees", "dist",
    "build", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".next", "coverage",
    "site-packages", ".shipwright",
})
_TS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")


def _is_python_test_file(path: Path) -> bool:
    name = path.name
    return name.startswith("test_") and name.endswith(".py") or name.endswith("_test.py")


def enumerate_test_files(project_root: Path, is_ts_test_file) -> tuple[list[Path], list[Path]]:
    """Walk the whole repo → (py, ts) test files, pruning vendored/build dirs DURING descent.

    ``os.walk`` with an in-place ``dirnames`` prune means a large committed ``node_modules``
    (the brownfield-JS class adopt exists for) is never DESCENDED into — no O(all-files)
    materialize+sort of hundreds of thousands of vendored paths (doubt MED#2). ``.shipwright``
    is pruned so the framework's own scaffolded specs never enter a target repo's inventory.
    """
    py_files: list[Path] = []
    ts_files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(str(project_root)):
        dirnames[:] = [d for d in dirnames if d not in _PRUNE_DIRS]  # prune before descent
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix == ".py" and _is_python_test_file(path):
                py_files.append(path)
            elif path.suffix in _TS_SUFFIXES and is_ts_test_file(path):
                ts_files.append(path)
    py_files.sort()
    ts_files.sort()
    return py_files, ts_files


def _scan_pytest_mark_skip(files: list[Path]) -> list[tuple[Path, int, str]]:
    """Flag every UNCONDITIONAL ``@pytest.mark.skip`` decorator (the most common
    disable-a-test idiom — the shared scanner covers ``skipif`` + ``pytest.skip()`` but
    NOT this; doubt LOW#3). Returns ``(file, line, reason)``. AST-based (a comment/string
    mention never matches); a per-file parse/read error is skipped silently (the shared
    scanner already surfaces syntax errors on the same files)."""
    out: list[tuple[Path, int, str]] = []
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for deco in node.decorator_list:
                target = deco.func if isinstance(deco, ast.Call) else deco
                if (isinstance(target, ast.Attribute) and target.attr == "skip"
                        and isinstance(target.value, ast.Attribute)
                        and target.value.attr == "mark"):
                    out.append((path, getattr(deco, "lineno", node.lineno),
                                "unconditional @pytest.mark.skip — a permanently disabled "
                                "test; delete it or convert to a quarantined conditional skip"))
    return out


def _norm_finding(root: Path, file: Path, line: int, pattern: str, reason: str, language: str) -> dict:
    try:
        rel = Path(file).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        rel = Path(file).name
    return {"file": rel, "line": line, "pattern": pattern, "reason": reason, "language": language}


def repo_wide_skip_inventory(project_root: Path, shared_scripts: Path) -> list[dict]:
    """Full skip/quarantine inventory across every test file (reuses TT4 verbatim).

    Returns one normalized dict per finding: ``{file, line, pattern, reason, language}``.
    NOT diff-scoped — ``filter_to_changed`` is deliberately NOT applied, so adopt catches
    every pre-existing silent skip / focused test / expired quarantine (Spec §11-R5). The
    shared Python scanner (``skipif`` + un-guarded ``pytest.skip()``) is supplemented by a
    local ``@pytest.mark.skip`` scan so the commonest disable idiom is not missed.
    """
    import sys
    if str(shared_scripts) not in sys.path:
        sys.path.insert(0, str(shared_scripts))
    from test_hygiene import scan_for_silent_skip_without_ci_guard  # noqa: PLC0415
    from ts_test_hygiene import is_ts_test_file, scan_ts_test_files  # noqa: PLC0415

    py_files, ts_files = enumerate_test_files(project_root, is_ts_test_file)
    inventory: list[dict] = []
    for f in scan_for_silent_skip_without_ci_guard(py_files):
        inventory.append(_norm_finding(project_root, f.file, f.line, f.pattern, f.reason, "python"))
    for path, line, reason in _scan_pytest_mark_skip(py_files):
        inventory.append(_norm_finding(project_root, path, line, "pytest.mark.skip", reason, "python"))
    for f in scan_ts_test_files(ts_files):
        inventory.append(_norm_finding(project_root, f.file, f.line, f.pattern, f.reason, "ts/js"))
    inventory.sort(key=lambda d: (d["file"], d["line"], d["pattern"]))
    return inventory


__all__ = ["enumerate_test_files", "repo_wide_skip_inventory"]
