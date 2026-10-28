"""T-code: the FRs whose bound tests execute a changed line (BP brief section 2).

Input is a per-test-context coverage database from a run at the MERGE BASE (the replay and
BL2's CI context run both produce one), so every line number below is a base line. A removed
or replaced line is looked up directly. A line only ADDED inside an existing function is
attributed through that function's base lines (a pure deletion is the same case read the
other way); an added line outside any function (module level, import time) has no per-test
context and is reported unattributed - a disclosed limit, never silently dropped.

``fan_out`` records, per changed function, how many FRs it reaches: the measurement the
'broad change' threshold N is proposed from.
"""

from __future__ import annotations

import ast
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

from ._baseline_touch_binding import index_tests
from ._baseline_touch_git import GitRev, is_test_path
from ._tag_binding_py import _FUNC, parse

__all__ = ["CodeTouch", "context_to_test", "load_contexts", "merge_contexts", "code_touched"]

_CTX = re.compile(r"^(?P<path>[^:|]+\.py)::(?P<name>[^|\[]+)")


@dataclass
class CodeTouch:
    touched: dict[str, set[str]] = field(default_factory=dict)      # FR -> changed functions
    fan_out: dict[str, set[str]] = field(default_factory=dict)      # "file::func" -> FRs
    unattributed: list[str] = field(default_factory=list)
    incomplete: list[str] = field(default_factory=list)


def context_to_test(context: str, prefix: str = "") -> str | None:
    """``tests/test_x.py::TestC::test_y[p]|run`` -> ``<prefix>tests/test_x.py::TestC.test_y``."""
    m = _CTX.match(context or "")
    if not m:
        return None
    return f"{prefix}{m['path'].replace(chr(92), '/')}::{m['name'].replace('::', '.')}"


def load_contexts(db: str | Path, repo_root: str | Path, prefix: str = "") -> dict[str, dict[int, set[str]]]:
    """``repo-relative file -> {line -> {test id}}`` from a coverage database with contexts.

    ``prefix`` is the repo-relative directory the tier ran in (``plugins/shipwright-x/`` for a
    plugin tier, empty for a root tier): with ``relative_files`` the database stores paths
    relative to that directory, and its test ids are relative to it as well.
    """
    from coverage import CoverageData  # local: the library is importable without coverage installed

    data = CoverageData(basename=str(db))
    data.read()
    root = Path(repo_root).resolve()
    out: dict[str, dict[int, set[str]]] = {}
    for fname in data.measured_files():
        if Path(fname).is_absolute():
            try:
                rel = Path(fname).resolve().relative_to(root).as_posix()
            except ValueError:
                rel = fname.replace("\\", "/")
        else:
            rel = posixpath.normpath(prefix + fname.replace("\\", "/"))
        lines = out.setdefault(rel, {})
        for line, ctxs in (data.contexts_by_lineno(fname) or {}).items():
            tests = {t for c in ctxs if (t := context_to_test(c, prefix))}
            if tests:
                lines.setdefault(line, set()).update(tests)
    return out


def merge_contexts(parts: list[dict[str, dict[int, set[str]]]]) -> dict[str, dict[int, set[str]]]:
    """Union of several tiers' databases (a line covered in any tier counts)."""
    out: dict[str, dict[int, set[str]]] = {}
    for part in parts:
        for rel, lines in part.items():
            dest = out.setdefault(rel, {})
            for ln, tests in lines.items():
                dest.setdefault(ln, set()).update(tests)
    return out


def _spans(text: str) -> list[tuple[str, int, int]]:
    tree = parse(text)
    out: list[tuple[str, int, int]] = []

    def visit(body, prefix):
        for node in body:
            if isinstance(node, _FUNC):
                out.append((prefix + node.name, node.lineno, node.end_lineno or node.lineno))
                visit(node.body, prefix + node.name + ".")
            elif isinstance(node, ast.ClassDef):
                visit(node.body, prefix + node.name + ".")

    if tree is not None:
        visit(tree.body, "")
    return out


def _enclosing(spans, line: int):
    inside = [s for s in spans if s[1] <= line <= s[2]]
    return min(inside, key=lambda s: s[2] - s[1]) if inside else None  # innermost


def code_touched(rev: GitRev, changes: list[tuple[str, str, str]],
                 contexts: dict[str, dict[int, set[str]]]) -> CodeTouch:
    """Attribute every changed production line to FRs through the base-run contexts."""
    out = CodeTouch()
    fr_cache: dict[str, frozenset[str]] = {}

    def frs_of(test_id: str) -> frozenset[str]:
        if test_id not in fr_cache:
            path, _, name = test_id.partition("::")
            text = rev.read(path, "base")
            if text is None:
                out.incomplete.append(f"unreadable bound test file {path} at base")
                text = ""
            info = (index_tests(text) or {}).get(name)
            fr_cache[test_id] = info.frs if info else frozenset()
        return fr_cache[test_id]

    for status, old, new in changes:
        if status == "A" or not old.endswith(".py") or is_test_path(old):
            continue  # a new file executes nowhere at base; test-dir code is static attribution's
        lines = contexts.get(old)
        removed, added = rev.line_changes(old, new)
        if lines is None:
            if removed or added:
                out.unattributed.append(f"{old}: no coverage at base (not measured or never executed)")
            continue
        base_text, head_text = rev.read(old, "base"), rev.read(new, "head")
        if base_text is None or head_text is None:
            out.incomplete.append(f"{old}: unreadable source - baseline evidence incomplete")
            continue
        b_spans, h_spans = _spans(base_text), _spans(head_text)
        targets: dict[str, set[int]] = {}
        for ln in removed:
            span = _enclosing(b_spans, ln)
            targets.setdefault(span[0] if span else "<module>", set()).add(ln)
        for ln in added:
            span = _enclosing(h_spans, ln)
            base_span = next((s for s in b_spans if span and s[0] == span[0]), None)
            if base_span is None:
                if span is None:
                    targets.setdefault("<module>", set())
                continue  # a brand-new function executes nowhere at base
            targets.setdefault(base_span[0], set()).update(range(base_span[1], base_span[2] + 1))
        for func, lns in targets.items():
            tests = set().union(*(lines.get(ln, set()) for ln in lns)) if lns else set()
            key = f"{old}::{func}"
            frs = {fr for t in tests for fr in frs_of(t)}
            if frs:
                out.fan_out[key] = frs
                for fr in frs:
                    out.touched.setdefault(fr, set()).add(key)
            else:
                out.unattributed.append(f"{key}: executed by no FR-bound test")
    return out
