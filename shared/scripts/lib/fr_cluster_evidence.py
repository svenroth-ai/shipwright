"""Code evidence for :mod:`lib.fr_clusters`: which tests name which criterion, and which source files those tests import.

Reads test files from the working tree (stdlib only; no git, so a fresh ``tmp_path`` repo works the same as a checkout):

* a criterion is **bound** to a test when the test names it as ``FR-01.03/AC05`` or ``FR-01.03.AC05`` in a real marker or
  comment - a ``covers(...)`` decorator, a ``#`` / ``//`` comment above the test or inside its body (Python via ``ast`` and
  ``tokenize``). The text of a string literal never binds: fixture data that merely mentions an id is not coverage;
* the **touched files** of a criterion are the repository source files its bound tests import (Python ``import`` /
  ``from``, TS/JS relative ``import`` / ``require``), resolved against the files that exist.

A criterion no test names has no evidence; nothing is inferred from FR-level tags (they bind a whole FR, so they cannot
tell its criteria apart).
"""

from __future__ import annotations

import ast
import io
import os
import re
import tokenize
from pathlib import Path

__all__ = ["collect_evidence", "is_test_file"]

_SKIP_DIRS = frozenset({".git", "node_modules", ".worktrees", ".venv", "venv", "__pycache__", "dist", "build", ".claude", ".pytest_cache",
                       "env", ".tox", ".next", "coverage", "target", ".nuxt", "site-packages"})
_SRC_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs")
_TEST_DIRS = frozenset({"tests", "test", "__tests__", "integration-tests", "e2e"})
_AC_REF = re.compile(r"(FR-\d+\.\d+)[./]AC(\d+)(?!\d)")
_JS_TEST = re.compile(r"""^\s*(?:it|test)(?:\.\w+)*\(\s*(['"`])(.+?)\1""")
_PY_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)
_JS_IMPORT = re.compile(r"""(?:from\s+|require\(\s*|import\(\s*)['"](\.{1,2}/[^'"]+)['"]""")
_MAX_BYTES = 2_000_000


def is_test_file(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    name = parts[-1]
    return (bool(_TEST_DIRS & set(parts[:-1])) or name.startswith("test_") or name.endswith("_test.py")
            or bool(re.search(r"\.(?:test|spec)\.[jt]sx?$", name)))


def _walk(root: Path) -> list[str]:
    out = []
    for base, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
        for n in sorted(names):
            if n.endswith(_SRC_EXTS):
                out.append(Path(base, n).relative_to(root).as_posix())
    return out


def _read(path: Path) -> str:
    try:
        if path.stat().st_size > _MAX_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _refs(text: str) -> list[str]:
    return [f"{m.group(1)}.AC{int(m.group(2)):02d}" for m in _AC_REF.finditer(text)]


def _py_bindings(rel: str, text: str) -> dict[str, set[str]]:
    """Python: ids named in a ``covers(...)`` decorator/``pytestmark`` or in a ``#`` comment; string literals elsewhere never count."""
    try:
        tree = ast.parse(text)
        comments = [(t.start[0], t.string) for t in tokenize.generate_tokens(io.StringIO(text).readline) if t.type == tokenize.COMMENT]
    except (SyntaxError, tokenize.TokenError, ValueError):
        return {}
    funcs: list[tuple[int, int, str]] = []  # (first line incl. decorators, last line, name)
    out: dict[str, set[str]] = {}

    def bind(acs: list[str], name: str) -> None:
        for ac in acs:
            out.setdefault(ac, set()).add(f"{rel}::{name}")

    def covers_refs(decorators: list[ast.expr]) -> list[str]:
        found: list[str] = []
        for d in decorators:
            if "covers" in ast.unparse(d):
                found += [r for n in ast.walk(d) if isinstance(n, ast.Constant) and isinstance(n.value, str) for r in _refs(n.value)]
        return found

    def visit(node: ast.AST, inherited: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, inherited + covers_refs(child.decorator_list))
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if child.name.startswith("test"):
                    start = min([child.lineno] + [d.lineno for d in child.decorator_list])
                    funcs.append((start, child.end_lineno or child.lineno, child.name))
                    bind(inherited + covers_refs(child.decorator_list), child.name)
                visit(child, inherited)
            elif isinstance(child, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in child.targets):
                bind(covers_refs([child.value]), "(module)")

    visit(tree, [])
    lines = text.splitlines()
    for line_no, comment in comments:
        acs = _refs(comment)
        if not acs:
            continue
        inside = [f for f in funcs if f[0] <= line_no <= f[1]]
        if inside:
            bind(acs, max(inside)[2])
            continue
        nxt = min((f for f in funcs if f[0] > line_no), default=None)
        gap = lines[line_no:nxt[0] - 1] if nxt else None
        if nxt and all(not g.strip() or g.strip().startswith("#") for g in gap):  # a comment directly above the test
            bind(acs, nxt[2])
        else:
            bind(acs, "(module)")
    return out


def _js_comment(line: str, in_block: bool) -> tuple[str, bool]:
    """The comment text of one JS/TS line (``//`` and ``/* */``, which may span lines) and whether a block comment is still open."""
    out, i = [], 0
    while i < len(line):
        if in_block:
            j = line.find("*/", i)
            if j < 0:
                out.append(line[i:])
                return " ".join(out), True
            out.append(line[i:j])
            i, in_block = j + 2, False
            continue
        a, b = line.find("/*", i), line.find("//", i)
        if b >= 0 and (a < 0 or b < a):
            out.append(line[b + 2:])
            return " ".join(out), False
        if a < 0:
            break
        i, in_block = a + 2, True
    return " ".join(out), in_block


def _js_bindings(rel: str, text: str) -> dict[str, set[str]]:
    """JS/TS: ids named in a comment only - a ``// @covers`` line above a test, or any comment inside its body."""
    out: dict[str, set[str]] = {}
    pending: list[str] = []
    current, in_block = "", False
    for line in text.splitlines():
        comment, in_block = _js_comment(line, in_block)
        js = _JS_TEST.match(line)
        if js:
            current = js.group(2)
            for ac in pending:
                out.setdefault(ac, set()).add(f"{rel}::{current}")
            pending = []
        acs = _refs(comment)
        if not acs:
            continue
        if "@covers" in comment and not js:
            pending.extend(acs)
        else:
            for ac in acs:
                out.setdefault(ac, set()).add(f"{rel}::{current or '(module)'}")
    for ac in pending:
        out.setdefault(ac, set()).add(f"{rel}::(module)")
    return out


def _bindings(rel: str, text: str) -> dict[str, set[str]]:
    """``{ac id: {"<rel>::<test name>"}}`` for one test file."""
    return _py_bindings(rel, text) if rel.endswith(".py") else _js_bindings(rel, text)


def _resolve_imports(rel: str, text: str, sources: set[str], by_suffix: dict[str, list[str]]) -> set[str]:
    found: set[str] = set()
    if rel.endswith(".py"):
        for m in _PY_IMPORT.finditer(text):
            mod = (m.group(1) or m.group(2)).replace(".", "/")
            for cand in (mod + ".py", mod + "/__init__.py"):
                found.update(by_suffix.get(cand, ()))
    else:
        here = Path(rel).parent
        for m in _JS_IMPORT.finditer(text):
            base = os.path.normpath((here / m.group(1)).as_posix()).replace("\\", "/")
            for cand in [base] + [base + e for e in _SRC_EXTS] + [f"{base}/index{e}" for e in _SRC_EXTS]:
                if cand in sources:
                    found.add(cand)
                    break
    return {f for f in found if not is_test_file(f) and f != rel}


def collect_evidence(project_root: str | Path, wanted: set[str] | None = None) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """``(tests, files)``: ``{ac id: {test ids}}`` and ``{ac id: {source files}}`` for every criterion some test names.

    ``wanted`` limits the result to those ac ids (``FR-01.03.AC05``) when given.
    """
    root = Path(project_root)
    all_files = _walk(root)
    sources = set(all_files)
    by_suffix: dict[str, list[str]] = {}
    for rel in all_files:
        if is_test_file(rel):
            continue
        parts = rel.split("/")
        for i in range(len(parts)):
            by_suffix.setdefault("/".join(parts[i:]), []).append(rel)
    tests: dict[str, set[str]] = {}
    files: dict[str, set[str]] = {}
    for rel in all_files:
        if not is_test_file(rel):
            continue
        text = _read(root / rel)
        if "AC" not in text:
            continue
        bound = {ac: ids for ac, ids in _bindings(rel, text).items() if wanted is None or ac in wanted}
        if not bound:
            continue
        imports = _resolve_imports(rel, text, sources, by_suffix)
        for ac, ids in bound.items():
            tests.setdefault(ac, set()).update(ids)
            files.setdefault(ac, set()).update(imports)
    return tests, files
