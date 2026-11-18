"""Infrastructure class of a Python test: what its ``covers_none`` marks say, and whether they can be granted.

Granting is strict (the literal ``pytest.mark.covers_none("tooling"|"infra")``), contradiction detection is loose
(any ``.covers`` attribute in reach), so a form this parser misses can only ever fail to grant, never over-grant.
"""

from __future__ import annotations

import ast
from typing import NamedTuple

from ._tag_binding_py import _SCOPES, _attr_chain, _functions, _is_exact_covers_none, _scope_mark_exprs, parse

__all__ = ["INFRA_LABELS", "InfraInfo", "py_infra_info"]

INFRA_LABELS = frozenset({"tooling", "infra"})


class InfraInfo(NamedTuple):
    """What one declaration says about the infrastructure class: ``labels`` the valid grants,
    ``bad`` why a ``covers_none`` it carries cannot be granted, ``has_covers`` any ``.covers`` mark in
    reach (a contradiction), ``declared`` whether it carries any ``covers_none`` at all, ``direct`` whether
    one sits on the function or a class itself rather than only in a module/class ``pytestmark``."""
    labels: frozenset[str]
    bad: tuple[str, ...]
    has_covers: bool
    declared: bool
    direct: bool = False


def _is_literal_mark(mark: ast.expr) -> bool:
    chain = _attr_chain(mark.func if isinstance(mark, ast.Call) else mark)
    return bool(chain) and len(chain) >= 2 and (chain[:2] == ["pytest", "mark"] or chain[0] == "mark")


def _infra_marks(marks: list[ast.expr], scoped: bool, labels: set[str], bad: list[str]) -> tuple[bool, bool]:
    """Fold one scope's marks into ``labels`` / ``bad``; returns ``(has_covers, declared)``.
    Granting is strict (the literal ``pytest.mark.covers_none("<label>")``), contradiction detection is loose
    (any ``.covers`` attribute); a ``pytestmark`` value that is not a literal mark hides what it applies."""
    has_covers = declared = False
    for mark in marks:
        if scoped and not _is_literal_mark(mark):
            bad.append("unresolved pytestmark value (a name or expression, not a literal mark)")
        target = mark.func if isinstance(mark, ast.Call) else mark
        if isinstance(target, ast.Attribute) and target.attr == "covers":
            has_covers = True
        elif isinstance(target, ast.Attribute) and target.attr == "covers_none":
            declared = True
            args = mark.args if isinstance(mark, ast.Call) else []
            if not _is_exact_covers_none(mark):
                bad.append("covers_none must be written exactly pytest.mark.covers_none(...)")
            elif len(args) != 1 or mark.keywords or not (
                    isinstance(args[0], ast.Constant) and isinstance(args[0].value, str)):
                bad.append("covers_none takes exactly one string literal: 'tooling' or 'infra'")
            elif args[0].value not in INFRA_LABELS:
                bad.append(f"covers_none label {args[0].value!r} is not 'tooling' or 'infra'")
            else:
                labels.add(args[0].value)
    return has_covers, declared


def _hidden_pytestmark(body: list[ast.stmt]) -> bool:
    """A ``pytestmark`` assignment this parser cannot read: destructuring, a subscript, an attribute
    (``Cls.pytestmark = ...``) or any assignment nested under ``if``/``try``/``with``. pytest applies it;
    the gate cannot see what it holds, so it must not grant over it."""
    stack = [(s, True) for s in body]
    while stack:
        node, top = stack.pop()
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                named = any((isinstance(n, ast.Name) and n.id == "pytestmark")
                            or (isinstance(n, ast.Attribute) and n.attr == "pytestmark") for n in ast.walk(target))
                if named and not (top and isinstance(target, ast.Name)):
                    return True
        elif not isinstance(node, _SCOPES):
            stack.extend((c, False) for c in ast.iter_child_nodes(node) if isinstance(c, ast.stmt))
    return False


def py_infra_info(text: str, name: str) -> list[InfraInfo] | None:
    """One :class:`InfraInfo` per function named ``name`` (function, classes, class and module ``pytestmark``)."""
    tree = parse(text)
    if tree is None:
        return None
    module = _scope_mark_exprs(tree.body)
    out: list[InfraInfo] = []
    for fn, classes in _functions(tree.body, name):
        labels: set[str] = set()
        bad: list[str] = []
        if _hidden_pytestmark(tree.body) or any(_hidden_pytestmark(c.body) for c in classes):
            bad.append("a pytestmark is assigned in a form this gate cannot read (destructuring, subscript, "
                       "attribute or conditional)")
        covers = declared = direct = False
        scopes = [(list(fn.decorator_list), False), (module, True)]
        for cls in classes:
            scopes += [(list(cls.decorator_list), False), (_scope_mark_exprs(cls.body), True)]
        for marks, scoped in scopes:
            c, d = _infra_marks(marks, scoped, labels, bad)
            covers, declared, direct = covers or c, declared or d, direct or (d and not scoped)
        out.append(InfraInfo(frozenset(labels), tuple(dict.fromkeys(bad)), covers, declared, direct))
    return out
