"""Python half of the test-tag gate's identity: body shapes, rename bindings, collection, tags.

A test's body is the ``ast`` dump of its arguments and statements, leading docstring
dropped (comments never reach the AST). For ``mechanical-refactor`` only BINDINGS are
anonymised: the function's arguments (fixtures), names it assigns, names a local import
binds (the ``as`` alias - the imported name itself stays), nested ``def``/``class`` and
``except ... as`` names. An attribute (``self.assertTrue``, ``resp.ok``), a keyword
argument and a call to a name the test does not bind (``is_ok``) stay literal; a name a
MODULE-level import binds is replaced by its import target, so ``import json as j`` ->
``import json as js`` is a rename while ``from m import is_ok`` -> ``is_err`` is not.
"""

from __future__ import annotations

import ast
import copy
import hashlib
from functools import lru_cache

__all__ = ["parse", "py_shapes", "py_tag_sets", "would_collect_py"]

_FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


@lru_cache(maxsize=32)
def parse(text: str) -> ast.Module | None:
    """One parse per file text: a changed file is asked about every test it holds. Callers
    only read the shared tree; anything they transform is deep-copied first."""
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError):
        return None


def _functions(body: list[ast.stmt], name: str, classes: tuple = ()):
    """``(function, enclosing classes)`` for every function called ``name``, at any depth."""
    for node in body:
        if isinstance(node, _FUNC) and node.name == name:
            yield node, classes
        inner = classes + (node,) if isinstance(node, ast.ClassDef) else classes
        for field in ("body", "orelse", "finalbody", "handlers"):
            sub = getattr(node, field, None)
            if isinstance(sub, list):
                yield from _functions([s for s in sub if isinstance(s, ast.AST)], name, inner)


def _module_imports(tree: ast.Module) -> dict[str, str]:
    """Bound name -> import target for every import outside a function or class."""
    out: dict[str, str] = {}
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Import):
            for a in node.names:
                out[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                out[a.asname or a.name] = f"{'.' * node.level}{node.module or ''}.{a.name}"
        elif not isinstance(node, _SCOPES):
            stack.extend(ast.iter_child_nodes(node))
    return out


def _local_bindings(fn: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name.split(".")[0])
        elif isinstance(node, (*_FUNC, ast.ClassDef)) and node is not fn:
            names.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    return names


class _Bindings(ast.NodeTransformer):
    """Anonymise the bindings to ``_`` (recorded in ``seen``, visit order) and resolve
    module-imported names to their target; leave every other identifier literal."""

    def __init__(self, bound: set[str], imports: dict[str, str]) -> None:
        self.bound, self.imports, self.seen = bound, imports, []

    def _anon(self, name: str) -> str:
        self.seen.append(name)
        return "_"

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id in self.bound:
            node.id = self._anon(node.id)
        elif node.id in self.imports:
            node.id = f"<import {self.imports[node.id]}>"
        return node

    def visit_arg(self, node: ast.arg) -> ast.AST:
        self.generic_visit(node)
        node.arg = self._anon(node.arg)
        return node

    def visit_alias(self, node: ast.alias) -> ast.AST:
        if node.asname:
            node.asname = self._anon(node.asname)
        return node

    def _named(self, node):
        self.generic_visit(node)
        node.name = self._anon(node.name)
        return node

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _named

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> ast.AST:
        self.generic_visit(node)
        if node.name:
            node.name = self._anon(node.name)
        return node


def _body(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    body = list(fn.body)
    first = body[0] if body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        body = body[1:]
    return body


def py_shapes(text: str, name: str, anonymise: bool) -> list[tuple[str, list[str]]] | None:
    """``[(digest, bound names)]`` per function named ``name``; names only when anonymised."""
    tree = parse(text)
    if tree is None:
        return None
    imports = _module_imports(tree) if anonymise else {}
    out: list[tuple[str, list[str]]] = []
    for fn, _classes in _functions(tree.body, name):
        args = copy.deepcopy(fn.args)
        body = ast.Module(body=[copy.deepcopy(s) for s in _body(fn)], type_ignores=[])
        anon = _Bindings(_local_bindings(fn), imports)
        if anonymise:
            args, body = anon.visit(args), anon.visit(body)
        digest = hashlib.sha256((ast.dump(args) + "|" + ast.dump(body)).encode("utf-8")).hexdigest()
        out.append((digest, anon.seen))
    return out


def _covers(decs: list[ast.expr]) -> set[str]:
    out: set[str] = set()
    for dec in decs:
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "covers":
            out |= {a.value if isinstance(a, ast.Constant) else ast.dump(a) for a in dec.args}
    return out


def py_tag_sets(text: str, name: str) -> list[frozenset[str]] | None:
    """The ``covers`` marks each function named ``name`` carries: its own, its classes'
    and the module's ``pytestmark``."""
    tree = parse(text)
    if tree is None:
        return None
    module: set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in stmt.targets):
            marks = stmt.value.elts if isinstance(stmt.value, (ast.List, ast.Tuple)) else [stmt.value]
            module |= _covers(list(marks))
    return [frozenset(_covers(list(fn.decorator_list) + [d for c in classes for d in c.decorator_list]) | module)
            for fn, classes in _functions(tree.body, name)]


def _is_fixture(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in fn.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if (isinstance(target, ast.Attribute) and target.attr == "fixture") or (
            isinstance(target, ast.Name) and target.id == "fixture"
        ):
            return True
    return False


def _declares(node: ast.AST, name: str) -> bool:
    return any(isinstance(n, _FUNC) and n.name == name for n in ast.walk(node))


def _collects(body: list[ast.stmt], name: str) -> bool:
    for node in body:
        if isinstance(node, _FUNC):
            if node.name == name and not _is_fixture(node):
                return True
        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("Test") and not any(
                    isinstance(m, ast.FunctionDef) and m.name == "__init__" for m in node.body):
                if _collects(node.body, name):  # nested Test* classes are collected too
                    return True
        elif not isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.Expr)):
            if _declares(node, name):  # under if/try/with/for: cannot tell statically - fail closed
                return True
    return False


def would_collect_py(text: str, name: str) -> bool:
    if not name.startswith("test"):
        return False
    tree = parse(text)
    return True if tree is None else _collects(tree.body, name)
