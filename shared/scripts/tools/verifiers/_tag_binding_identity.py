"""Test identity for the test-tag gate: normalised body digests, renames, tags, "is it a test".

The traceability manifest identifies a test as ``<file>::<name>`` (Python: the function
name; TS/JS: the ``test(``/``it(`` title). That is function-level identity, never the
pytest node id, so adding a parametrize case or a class-level mark never creates a "new"
test. What the manifest cannot say is whether a test that shows up under a new id is a
MOVE of an existing one, or whether a legacy untagged test was EDITED. Both questions are
answered here by a normalised digest of the test's body:

* **Python** (:mod:`._tag_binding_py`) — the ``ast`` dump of the function's arguments and
  body. The leading docstring is dropped and comments never reach the AST, so a docstring-
  or comment-only edit digests the same. The name and the decorators are excluded: a rename
  keeps its digest (so it is matched as a move) and a new parametrize case or mark is not a
  body edit.
* **TS/JS** (:mod:`._tag_binding_ts`) — the token stream of the call after the title
  (comments stripped, every run of whitespace collapsed), up to the call's closing paren.

:func:`mechanically_renamed` decides the one edit the ``mechanical-refactor`` exemption may
cover: equal shapes once the test's BINDINGS are anonymised (attributes and unbound names
stay literal), AND a one-to-one rename mapping of those bindings.

Every digest function returns ``None`` for an unparseable file and ``()`` when no test of
that name is declared, so a caller can tell "could not look" from "not there".
"""

from __future__ import annotations

from ._tag_binding_py import py_shapes, py_tag_sets, would_collect_py
from ._tag_binding_ts import ts_shapes, ts_tag_sets

__all__ = ["body_digests", "mechanically_renamed", "sibling_tag_sets", "would_collect"]

_PY = (".py",)
_TS = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts")


def _strip_bom(text: str) -> str:
    return text[1:] if text.startswith("﻿") else text  # a UTF-8 BOM is not code


def _shapes(text: str, path: str, name: str, anonymise: bool) -> list[tuple[str, list[str]]] | None:
    text, low = _strip_bom(text), path.lower()
    if low.endswith(_PY):
        return py_shapes(text, name, anonymise)
    if low.endswith(_TS):
        return ts_shapes(text, name, anonymise)
    return None


def body_digests(text: str, path: str, name: str) -> tuple[str, ...] | None:
    """Normalised digests of every test named ``name`` declared in ``text``.

    ``None`` = the file could not be parsed (or is not a test language); ``()`` = no such
    test. A tuple because the manifest's function-level id can name two methods of the
    same name in different classes; they are compared as one sorted set."""
    shapes = _shapes(text, path, name, False)
    return None if shapes is None else tuple(sorted(d for d, _ids in shapes))


def sibling_tag_sets(text: str, path: str, name: str) -> list[frozenset[str]] | None:
    """The requirement ids each declaration named ``name`` carries, one set per
    declaration (same order and count as :func:`body_digests` sees them); ``None`` when
    the file cannot be parsed or is not a test language."""
    text, low = _strip_bom(text), path.lower()
    if low.endswith(_PY):
        return py_tag_sets(text, name)
    if low.endswith(_TS):
        return ts_tag_sets(text, name)
    return None


def _bijective(before: list[str], after: list[str]) -> bool:
    forward: dict[str, str] = {}
    backward: dict[str, str] = {}
    for old, new in zip(before, after):
        if forward.setdefault(old, new) != new or backward.setdefault(new, old) != old:
            return False
    return len(before) == len(after)


def mechanically_renamed(base_text: str, head_text: str, path: str, name: str) -> bool:
    """True when every test ``name`` differs from base ONLY by a consistent rename of the
    names it BINDS (arguments/fixtures, assigned names, import aliases).

    The shapes must be equal with the bindings anonymised - so an attribute
    (``assertTrue`` -> ``assertFalse``, ``resp.ok`` -> ``resp.failed``) or a call to a name
    the test does not bind (``is_ok`` -> ``is_err``) is a real change - AND the bindings
    must map one-to-one in both directions at every occurrence. That refuses a swap at one
    call site (``f(a, b)`` -> ``f(b, a)``), a rename onto a name already in use, and any
    change of literals or structure, while a fixture or alias renamed throughout passes."""
    before, after = _shapes(base_text, path, name, True), _shapes(head_text, path, name, True)
    if not before or not after or len(before) != len(after):
        return False
    pairs = zip(sorted(before), sorted(after))
    return all(bd == hd and _bijective(bids, hids) for (bd, bids), (hd, hids) in pairs)


def would_collect(text: str, path: str, name: str) -> bool:
    """Would pytest collect a function called ``name`` in this file as a test?

    True for a module-level ``test*`` function or a ``test*`` method of a module-level
    ``Test*`` class (or of a ``Test*`` class nested in one), unless it is a fixture. False
    for a fixture, a nested helper, or a method of a non-``Test*`` class — the shapes the
    ``fixture-or-helper`` exemption is for (and a ``Test*`` class with an ``__init__``,
    which pytest refuses to collect). Fails closed (True) for a ``test*`` function under a
    module-level ``if``/``try``/``with``, for every TS/JS ``test(``/``it(`` declaration, and
    for an unparseable file. Known limit: a project that customises
    ``python_functions``/``python_classes`` is judged by pytest's DEFAULT patterns."""
    if not path.lower().endswith(_PY):
        return True
    return would_collect_py(_strip_bom(text), name)
