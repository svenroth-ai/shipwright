"""T-test and 'moved': the FRs bound to a modified or deleted test (BP brief section 2).

A test's identity is its qualified name (``Class.test_x``); its CONTENT is the digest of its
arguments, body (docstring dropped) and every decorator that changes what it does, class and
module ``pytestmark`` included - ``covers`` tags excluded, so tagging is not a body edit but
un-skipping or changing a parametrize case is. Its BINDINGS are the FRs named by ``covers``
on the function, its classes and the module (``FR-01.09/AC03`` binds ``FR-01.09``).

A test is MOVED when it vanished from base and a head test has the identical digest and
identical bindings: it only relocated or was renamed (listed, not touched).

Deferred: the brief also names the manifest's runtime ids (parametrize instances) as a binding
source. Bindings here are static (AST) at function granularity, which over-approximates (every
instance of a parametrized test shares its function's FRs) and so cannot go silent; instance-level
bindings are left to BL2/BL3, where the manifest is regenerated per run.
"""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, field

from ._baseline_touch_git import GitRev, is_test_path
from ._tag_binding_py import _FUNC, _body, _behavioural_decorators, _covers, _scope_marks, parse

__all__ = ["TestInfo", "TestTouch", "index_tests", "test_touched"]

_FR_RE = re.compile(r"^(FR-\d{2}\.\d{2})(?:/AC\d+)?$")


@dataclass(frozen=True)
class TestInfo:
    __test__ = False  # not a pytest class
    digest: str
    frs: frozenset[str]


@dataclass
class TestTouch:
    __test__ = False
    touched: dict[str, set[str]] = field(default_factory=dict)   # FR -> test ids that touch it
    moved: list[tuple[str, str]] = field(default_factory=list)    # (base id, head id)
    unreadable: list[str] = field(default_factory=list)


def _module_covers(tree: ast.Module) -> set[str]:
    marks: list[ast.expr] = []
    for stmt in tree.body:
        targets = stmt.targets if isinstance(stmt, ast.Assign) else [getattr(stmt, "target", None)]
        if any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets) and getattr(stmt, "value", None) is not None:
            v = stmt.value
            marks += v.elts if isinstance(v, (ast.List, ast.Tuple)) else [v]
    return _covers(marks)


def _class_covers(cls: ast.ClassDef) -> set[str]:
    marks = list(cls.decorator_list)
    for stmt in cls.body:
        if _is_pytestmark(stmt) and getattr(stmt, "value", None) is not None:
            v = stmt.value
            marks += v.elts if isinstance(v, (ast.List, ast.Tuple)) else [v]
    return _covers(marks)


def _is_pytestmark(node: ast.AST) -> bool:
    targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
    return any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets)


def _frs(raw: set[str]) -> frozenset[str]:
    return frozenset(m[1] for r in raw if (m := _FR_RE.match(r)))


def _walk(body, prefix: str, classes: tuple, out: list, module_covers: set, class_covers: set):
    for node in body:
        if isinstance(node, _FUNC) and node.name.startswith("test"):
            out.append((prefix + node.name, node, classes, module_covers | class_covers))
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            _walk(node.body, f"{prefix}{node.name}.", classes + (node,), out, module_covers,
                  class_covers | _class_covers(node))


def index_tests(text: str) -> dict[str, TestInfo] | None:
    """``qualified name -> TestInfo`` for every collectable test; ``None`` on a syntax error."""
    tree = parse(text)
    if tree is None:
        return None
    found: list = []
    _walk(tree.body, "", (), found, _module_covers(tree), set())
    marks = _scope_marks(tree.body)
    out: dict[str, TestInfo] = {}
    for name, fn, classes, inherited in found:
        decs = _behavioural_decorators(fn, classes) + marks
        members = "".join(ast.dump(m) for c in classes for m in c.body
                          if not (isinstance(m, _FUNC) and m.name.startswith("test")) and not _is_pytestmark(m))
        blob = "|".join((
            members, ast.dump(fn.args), ast.dump(ast.Module(body=_body(fn), type_ignores=[])),
            ast.dump(ast.Module(body=[ast.Expr(value=d) for d in decs], type_ignores=[]))))
        own = _covers(list(fn.decorator_list))
        key, n = name, 1
        while key in out:  # duplicate names in one file stay distinct, in source order
            n += 1
            key = f"{name}#{n}"
        out[key] = TestInfo(hashlib.sha256(blob.encode("utf-8")).hexdigest(), _frs(own | inherited))
    return out


def _file_index(rev: GitRev, path: str, side: str, touch: TestTouch) -> dict[str, TestInfo]:
    text = rev.read(path, side)
    if text is None:
        touch.unreadable.append(f"{path}@{side}")
        return {}
    indexed = index_tests(text) if text else {}
    if indexed is None:
        touch.unreadable.append(f"{path}@{side}")
        return {}
    return indexed


def test_touched(rev: GitRev, changes: list[tuple[str, str, str]]) -> TestTouch:
    """Compare every changed test file; fill the FRs touched and the moves."""
    touch = TestTouch()
    base_all: dict[str, TestInfo] = {}
    head_all: dict[str, TestInfo] = {}
    for status, old, new in changes:
        if not (is_test_path(old) or is_test_path(new)):
            continue
        if status != "A":
            base_all.update({f"{old}::{k}": v for k, v in _file_index(rev, old, "base", touch).items()})
        if status != "D":
            head_all.update({f"{new}::{k}": v for k, v in _file_index(rev, new, "head", touch).items()})
    gone = {k: v for k, v in base_all.items() if k not in head_all}
    fresh = {k: v for k, v in head_all.items() if k not in base_all}
    claimed: set[str] = set()
    retagged: list[tuple[str, frozenset[str]]] = []
    for hid, info in sorted(fresh.items()):
        origin = next((b for b, bi in sorted(gone.items()) if b not in claimed and bi.digest == info.digest), None)
        if origin is None:
            continue
        claimed.add(origin)
        if gone[origin].frs == info.frs:
            touch.moved.append((origin, hid))
        else:  # relocated AND re-tagged: not a pure move, both bindings are affected
            retagged.append((hid, gone[origin].frs | info.frs))

    def hit(test_id: str, frs) -> None:
        for fr in frs:
            touch.touched.setdefault(fr, set()).add(test_id)

    for hid, frs in retagged:
        hit(hid, frs)
    for tid, bi in base_all.items():
        hi = head_all.get(tid)
        if hi is None:
            if tid not in claimed:
                hit(tid, bi.frs)  # deleted
        elif hi != bi:
            hit(tid, bi.frs | hi.frs)  # edited, or re-tagged: both bindings are affected
    return touch
