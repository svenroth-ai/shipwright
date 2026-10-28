"""Static attribution for test-directory code that coverage omits (BP brief section 2, T-code).

Fixtures, ``conftest.py`` and helper modules live under ``tests/``, which the coverage
configuration omits, so no per-test context can attribute them. They are attributed
statically from the head tree:

* a changed fixture or helper NAME in a test module -> the tests of that module that use it;
* a changed ``conftest.py`` fixture -> the tests in its directory scope that request it; a
  changed hook (``pytest_*``), autouse fixture, or deleted ``conftest.py`` -> EVERY test in
  that scope (it can change any of them);
* a changed or deleted helper module -> every test module that imports it (the brief's
  wording: 'the test modules that import it'; DIRECT importers only - a test-side helper that
  itself imports the changed one is not followed).

A file git cannot read, or that does not parse, is reported in ``notes`` so the caller holds
('baseline evidence incomplete'); it is never read as 'binds nothing'.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import PurePosixPath

from ._baseline_touch_binding import index_tests
from ._baseline_touch_git import GitRev, is_test_path
from ._tag_binding_py import parse

__all__ = ["static_touched"]


def _is_autouse(node: ast.AST) -> bool:
    for dec in getattr(node, "decorator_list", []):
        if isinstance(dec, ast.Call) and any(k.arg == "autouse" and isinstance(k.value, ast.Constant) and k.value.value is True
                                             for k in dec.keywords):
            return True
    return False


def _defs(text: str) -> tuple[dict[str, str], set[str]] | None:
    """Top-level non-test names -> digest; plus the names that act scope-wide (hooks, autouse)."""
    tree = parse(text)
    if tree is None:
        return None
    out: dict[str, str] = {}
    wide: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith(("test", "Test")):
                out[node.name] = hashlib.sha256(ast.dump(node).encode()).hexdigest()
                if node.name.startswith("pytest_") or _is_autouse(node):
                    wide.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            digest = hashlib.sha256(ast.dump(node).encode()).hexdigest()
            out.update({t.id: digest for t in targets if isinstance(t, ast.Name) and t.id != "pytestmark"})
            wide |= {t.id for t in targets if isinstance(t, ast.Name) and t.id == "pytest_plugins"}
    return out, wide


def _used(node: ast.AST) -> set[str]:
    """Names a definition or test uses: arguments, bare names, and fixtures requested by string."""
    used = {a.arg for a in ast.walk(node) if isinstance(a, ast.arg)} | {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    for call in (c for c in ast.walk(node) if isinstance(c, ast.Call)):
        fn = call.func
        if isinstance(fn, ast.Attribute) and fn.attr in ("usefixtures", "getfixturevalue"):
            used |= {a.value for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)}
    return used


def _closure(text: str, names: set[str]) -> set[str]:
    """``names`` plus every non-test top-level def of ``text`` that (transitively) uses one."""
    tree = parse(text)
    if tree is None:
        return set(names)
    uses = {n.name: _used(n) for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not n.name.startswith(("test", "Test"))}
    out = set(names)
    grew = True
    while grew:
        grew = False
        for name, used in uses.items():
            if name not in out and out & used:
                out.add(name)
                grew = True
    return out


def _module_effects(text: str) -> str:
    """Dump of the top-level statements that are neither a definition nor an assignment: imports,
    module-level ``pytest.skip(...)`` / ``importorskip`` calls, ``if`` / ``try`` blocks, side effects."""
    tree = parse(text)
    keep = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign)
    return "".join(ast.dump(n) for n in (tree.body if tree else []) if not isinstance(n, keep))


def _tests_using(text: str, names: set[str], existing: set[str] | None = None) -> set[str]:
    """FRs of the tests in ``text`` whose arguments or body use any of ``names``; with
    ``existing`` only tests that already existed at base count (a new test binds nothing yet)."""
    tree, info = parse(text), index_tests(text)
    if tree is None or not info:
        return set()
    if existing is not None:
        info = {k: v for k, v in info.items() if k in existing}
    frs: set[str] = set()
    names = _closure(text, names)
    module_used = _used(ast.Module(body=[s for s in tree.body if isinstance(s, (ast.Assign, ast.AnnAssign))], type_ignores=[]))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            used = _used(node) | {d for dec in node.decorator_list for d in _used(dec)} | module_used
            if names & used:
                for key, ti in info.items():
                    if key.split("#")[0].split(".")[-1] == node.name:
                        frs |= ti.frs
    return frs


def _imports_module(text: str, stem: str) -> bool:
    """True when a module imports ``stem`` as a dotted component or as an imported name (any statement form)."""
    tree = parse(text)
    for node in ast.walk(tree) if tree is not None else ():
        if isinstance(node, ast.Import) and any(stem in a.name.split(".") for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and (stem in (node.module or "").split(".") or any(a.name == stem for a in node.names)):
            return True
    return False


def _all_frs(text: str) -> set[str]:
    return {fr for ti in (index_tests(text) or {}).values() for fr in ti.frs}


def static_touched(rev: GitRev, changes: list[tuple[str, str, str]]) -> tuple[dict[str, set[str]], list[str]]:
    """``(FR -> reasons, notes)`` for changed non-test definitions under test roots."""
    touched: dict[str, set[str]] = {}
    notes: list[str] = []
    added = {n for s, _o, n in changes if s == "A"}  # new files bind nothing that existed at base
    head_tests = [p for p in rev.listing("head") if is_test_path(p) and p not in added]

    def hit(frs: set[str], why: str) -> None:
        for fr in frs:
            touched.setdefault(fr, set()).add(why)

    def head_text(path: str) -> str:
        text = rev.read(path, "head")
        if text is None:
            notes.append(f"{path}: unreadable at head - baseline evidence incomplete")
            return ""
        return text

    for status, old, new in changes:
        path = old if status == "D" else new
        if not path.endswith(".py") or not is_test_path(path):
            continue
        if status == "A" and PurePosixPath(path).stem != "conftest":
            continue  # a new test module or helper binds nothing that existed at base
        base = rev.read(old, "base")
        head = "" if status == "D" else rev.read(new, "head")
        if base is None or head is None:
            notes.append(f"{path}: unreadable - baseline evidence incomplete")
            continue
        h_parsed, b_parsed = (_defs(head) if head else ({}, set())), (_defs(base) if base else ({}, set()))
        if h_parsed is None or b_parsed is None:
            notes.append(f"{path}: unparsable - baseline evidence incomplete")
            continue
        (h, h_wide), (b, b_wide) = h_parsed, b_parsed
        if status != "D" and ast.dump(parse(head)) == ast.dump(parse(base)):
            continue  # comments, blank lines, formatting: no behaviour moved
        names = {n for n in set(h) | set(b) if h.get(n) != b.get(n)}
        effects = status != "D" and _module_effects(head) != _module_effects(base)
        stem = PurePosixPath(path).stem
        scope_dir = str(PurePosixPath(path).parent)
        why = f"{path} (fixture/helper)"
        if stem == "conftest":
            scope = [p for p in head_tests if p.startswith(scope_dir + "/")]
            scope_wide = status == "D" or not names or effects or bool(names & (h_wide | b_wide))
            for p in scope:
                text = head_text(p)
                hit(_all_frs(text) if scope_wide else _tests_using(text, _closure(head or base, names)), f"{why} -> {p}")
        elif not stem.startswith("test"):
            for p in head_tests:
                if p != path:
                    text = head_text(p)
                    if _imports_module(text, stem):
                        hit(_all_frs(text), f"{why} -> {p}")
        elif effects:  # a module-level skip, import swap or side effect can change every test in the file
            hit(_all_frs(base), f"{path} (module-level statement changed)")
        elif names and status != "D":
            hit(_tests_using(head, names, set(index_tests(base) or {})), f"{why} -> same module")
    return touched, notes
