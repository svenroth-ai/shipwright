"""Handler heuristics of the ``*.py`` stack-profile guard (rule 2), split out of
``stack_profile_py_rules.py`` for the file-size cap: what makes an ``except`` around a resolver call
loud (re-raise, non-zero exit or return, failure builder, branch on ``.kind``) or a swallow.
"""

from __future__ import annotations

import ast
import re

PROFILE_ERRORS = ("ProfileError", "ProfileNotFound", "ProfileInvalid", "ProfileSchemaDrift")


def _call_name(node: ast.Call) -> str:
    f = node.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def _handler_names(handler: ast.ExceptHandler) -> list[str]:
    t = handler.type
    if t is None:
        return []
    return [e.id if isinstance(e, ast.Name) else e.attr
            for e in (t.elts if isinstance(t, ast.Tuple) else [t]) if isinstance(e, (ast.Name, ast.Attribute))]


def _names_value_error(name: str) -> bool:
    """An exception class name that covers the resolver's ValueError family (handlers and ``suppress``)."""
    return name in ("ValueError", "Exception", "BaseException") or name.endswith(PROFILE_ERRORS)


def _catches_value_error(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    return any(_names_value_error(n) for n in _handler_names(handler))


def _is_exit_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _call_name(node) in ("exit", "_exit", "SystemExit")


def _exits_zero(call: ast.Call) -> bool:
    """``sys.exit()``, ``sys.exit(0)``, ``SystemExit(None)``: success is not a failure exit."""
    return not call.args or (isinstance(call.args[0], ast.Constant) and call.args[0].value in (0, None))


def _is_nonzero_int(v: ast.AST) -> bool:
    """``3``, ``-1``: a failure code (``True`` is not one, ``0`` is success)."""
    if isinstance(v, ast.UnaryOp) and isinstance(v.op, (ast.USub, ast.UAdd)):
        v = v.operand
    return isinstance(v, ast.Constant) and isinstance(v.value, int) and not isinstance(v.value, bool) and v.value != 0


def _raises_zero_exit(exc: ast.AST | None) -> bool:
    """``raise SystemExit(0)``, ``raise SystemExit()`` and the bare-name ``raise SystemExit``."""
    if isinstance(exc, ast.Name):
        return exc.id == "SystemExit"
    return exc is not None and _is_exit_call(exc) and _exits_zero(exc)


def _scope_nodes(scope: ast.AST, *, lambdas: bool = False):
    """Nodes of ``scope`` itself: nested functions and classes (methods) are their own scopes, and
    with ``lambdas`` so are lambdas."""
    stop = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef) + ((ast.Lambda,) if lambdas else ())
    todo = list(ast.iter_child_nodes(scope))
    while todo:
        node = todo.pop()
        yield node
        if not isinstance(node, stop):
            todo.extend(ast.iter_child_nodes(node))


def _mentions_kind(tree: ast.AST) -> bool:
    return any((isinstance(n, ast.Attribute) and n.attr in ("kind", "exit_code"))
               or (isinstance(n, ast.Constant) and n.value in ("kind", "exit_code")) for n in ast.walk(tree))


def _kind_locals(handler: ast.ExceptHandler) -> set[str]:
    """Names assigned straight from the error's kind: ``kind = getattr(e, 'kind', ...)`` / ``kind = e.kind``."""
    return {t.id for n in _scope_nodes(handler, lambdas=True) if isinstance(n, ast.Assign)
            and (isinstance(n.value, ast.Attribute) or (isinstance(n.value, ast.Call) and _call_name(n.value) == "getattr"))
            and _mentions_kind(n.value) for t in n.targets if isinstance(t, ast.Name)}


def _branches_on_kind(handler: ast.ExceptHandler) -> bool:
    """``.kind`` / ``.exit_code`` (or ONE local assigned from it) read in a test, or returned as the code."""
    local = _kind_locals(handler)

    def reads(t: ast.AST) -> bool:
        return _mentions_kind(t) or any(isinstance(x, ast.Name) and x.id in local for x in ast.walk(t))

    for n in _scope_nodes(handler, lambdas=True):
        if isinstance(n, (ast.If, ast.IfExp, ast.While, ast.Assert)) and reads(n.test):
            return True
        if isinstance(n, ast.Compare) and reads(n):
            return True
        if isinstance(n, ast.Match) and reads(n.subject):
            return True
        if isinstance(n, ast.Return) and n.value is not None and (
                isinstance(n.value, ast.Attribute) or (isinstance(n.value, ast.Call) and _call_name(n.value) == "getattr")):
            if _mentions_kind(n.value):
                return True
    return False


# Callees that only convert or log: handing them the exception is not handling it.
_NEUTRAL = frozenset({"str", "repr", "format", "print", "dict", "list", "tuple", "set", "bool", "int", "float"})
_NEUTRAL_ATTR = frozenset({"debug", "info", "warning", "error", "exception", "log", "critical", "format"})
_FAILURE_BUILDER = re.compile(r"fail|error|refus|reject|abort|die|halt|escalat|invalid|exit_code", re.I)


def _receives(call: ast.Call, name: str | None) -> bool:
    """A failure builder (``_fail(exc)``, ``build_error(p, exc=exc)``) that is handed the caught exception."""
    if not name:
        return False
    callee = _call_name(call)
    if callee in (_NEUTRAL_ATTR if isinstance(call.func, ast.Attribute) else _NEUTRAL):
        return False
    args = [*call.args, *(k.value for k in call.keywords)]
    return bool(_FAILURE_BUILDER.search(callee)) and any(isinstance(a, ast.Name) and a.id == name for a in args)


def _handles_loudly(handler: ast.ExceptHandler) -> bool:
    for n in _scope_nodes(handler, lambdas=True):
        if isinstance(n, ast.Raise):
            if not _raises_zero_exit(n.exc):  # `raise SystemExit(0)` / `raise SystemExit` swallow
                return True
        elif _is_exit_call(n) and not _exits_zero(n):
            return True
        elif isinstance(n, ast.Return) and n.value is not None:
            v = n.value
            if _is_nonzero_int(v):
                return True
            if isinstance(v, ast.Call) and _receives(v, handler.name):
                return True
    return _branches_on_kind(handler)


def _propagates(handler: ast.ExceptHandler) -> bool:
    """The handler lets the error through: bare ``raise``, ``raise exc`` or ``raise ... from exc``."""
    for n in _scope_nodes(handler, lambdas=True):
        if isinstance(n, ast.Raise):
            named = lambda x: isinstance(x, ast.Name) and x.id == handler.name
            if n.exc is None or named(n.exc) or named(n.cause):
                return True
    return False


_TRY = tuple(t for t in (ast.Try, getattr(ast, "TryStar", None)) if t)
