"""The fingerprint of a promise test, for the promise lock (programme P21). Stdlib only.

A promise test is locked by hash: a change to what it asserts must be a decision, a change to how it is written must not.
``fingerprint`` hashes a *normalized* form of the test function that

* ignores formatting, comments (the parser drops them), docstrings, the import block (order, additions) and descriptive
  ``pytest.mark.*`` decorators such as ``covers`` (the tag names the AC: a re-anchor shows as an id change, never as a
  body change). Marks that change what runs or counts - parametrize, skip, skipif, xfail, usefixtures, filterwarnings -
  are part of the hash, because adding one is the commonest way to weaken a test;
* includes, transitively, every module-level function, class and constant the test names, and every fixture it
  requests (a parameter that is a ``@pytest.fixture`` function of the module or of a ``conftest.py`` handed in), so an
  assertion that lives in a helper or a fixture changes the fingerprint of every test that uses it.

The serialization is written by hand (not ``ast.dump``): ``ast.dump`` prints version-specific fields (``type_params``
since 3.12), so a lock written on one interpreter would read as a diff on another. Here a field that is ``None`` or an
empty list is left out, and ``type_comment`` / ``kind`` are never read.

Known limits (a test cannot tell these apart from a real change, and the lock's reviewer must know): a helper imported
from another module is NOT followed (the golden helper modules are frozen files in their own right); a method of a test
class is not found (the golden tests are plain functions); names bound at run time (``getattr``, ``request.getfixturevalue``)
are invisible; a helper's parameter that shadows a module-level name still pulls that name in (over-inclusion: a harmless extra hash
change, never a missed one).

AC ids: ``covers_of`` reads the ids a test declares, ``resolve_acs`` follows them through the spec's ``## AC-Move-Map``
(``| `FR-01.11/AC21` | `FR-01.22/AC21` |`` rows; the same format ``shared/scripts/lib/ac_move_map.py`` parses - a test pins the two
parsers together), and ``lock_entry`` joins the two: the id is stored beside the hash, never inside it.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

AC_ID = re.compile(r"^FR-\d{2}\.\d{2}/AC\d{2,}$")
MOVE_HEADING = "## AC-Move-Map"
_SKIP_FIELDS = frozenset({"type_comment", "kind", "lineno", "col_offset", "end_lineno", "end_col_offset"})
_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _dotted(node: ast.AST) -> str:
    """``pytest.mark.covers`` for an attribute chain (calls are looked through), else ``""``."""
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return f"{head}.{node.attr}" if head else ""
    return node.id if isinstance(node, ast.Name) else ""


# marks that change what runs or whether it counts: weakening a test with one of them must move the hash
_BEHAVIOUR_MARKS = ("parametrize", "skip", "skipif", "xfail", "usefixtures", "filterwarnings")


def _is_marker(decorator: ast.AST) -> bool:
    """A descriptive ``pytest.mark.*`` decorator (``covers``, ``slow``, ...); the behaviour marks above are kept."""
    name = _dotted(decorator)
    return name.startswith(("pytest.mark.", "mark.")) and name.rsplit(".", 1)[-1] not in _BEHAVIOUR_MARKS


def _is_fixture(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
        _dotted(d).endswith("fixture") for d in node.decorator_list)


def _is_autouse(node: ast.AST) -> bool:
    return _is_fixture(node) and any(
        isinstance(d, ast.Call) and any(k.arg == "autouse" and isinstance(k.value, ast.Constant) and k.value.value is True for k in d.keywords)
        for d in node.decorator_list)


def _docstring_free(body: list[ast.stmt]) -> list[ast.stmt]:
    first = body[0] if body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return body[1:] or [ast.Pass()]
    return body


def _canon(node: Any) -> Any:
    """A JSON-able, version-independent form of an AST node."""
    if isinstance(node, ast.AST):
        out: dict[str, Any] = {"_": type(node).__name__}
        for name, value in ast.iter_fields(node):
            if name in _SKIP_FIELDS or value is None or value == []:
                continue
            if name == "body" and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                value = _docstring_free(value)
            if name == "decorator_list":
                value = [d for d in value if not _is_marker(d)]
                if not value:
                    continue
            out[name] = _canon(value)
        return out
    if isinstance(node, list):
        return [_canon(item) for item in node]
    if isinstance(node, (bytes, complex)) or node is Ellipsis:
        return {"repr": repr(node)}
    if isinstance(node, float):
        return {"float": repr(node)}
    return node


class Module:
    """The module-level definitions of one source file, by name."""

    def __init__(self, source: str) -> None:
        self.defs: dict[str, ast.AST] = {}
        self.consts: dict[str, ast.AST] = {}
        self.marks: list[ast.AST] = []  # module-level ``pytestmark`` marks that change what runs (skip, xfail, parametrize ...)
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign) and any(isinstance(x, ast.Name) and x.id == "pytestmark" for x in node.targets):
                value = node.value
                self.marks += [m for m in (value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]) if not _is_marker(m)]
            elif isinstance(node, _DEFS):
                self.defs[node.name] = node
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.consts[target.id] = node
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                self.consts[node.target.id] = node

    def lookup(self, name: str) -> ast.AST | None:
        return self.defs.get(name) or self.consts.get(name)


def _names(node: ast.AST) -> set[str]:
    found = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    for call in (n for n in ast.walk(node) if isinstance(n, ast.Call) and _dotted(n.func).endswith("usefixtures")):
        found |= {a.value for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)}  # named by string
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        found |= {a.arg for a in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)}
    return found


def closure(test: str, source: str, conftests: Sequence[str] = ()) -> dict[str, ast.AST]:
    """The test and everything it needs: helpers, constants, classes, fixtures and the module's behaviour marks, transitively.

    Keys are the names found; a name found in a ``conftest.py`` is keyed ``name@<n>`` (n = its position in ``conftests``,
    from 1), so the same name in two modules never collapses into one entry."""
    modules = [Module(source), *(Module(text) for text in conftests)]
    start = modules[0].defs.get(test)
    if not isinstance(start, (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise ValueError(f"{test}: no module-level test function of that name")

    def key(name: str, index: int) -> str:
        return name if index == 0 else f"{name}@{index}"

    seen: dict[str, ast.AST] = {test: start}
    origin = {test: 0}  # which module each entry lives in: its own names are looked up there first
    todo = [test]

    def add(name: str, node: ast.AST, index: int) -> None:
        seen[key(name, index)], origin[key(name, index)] = node, index
        todo.append(key(name, index))

    for index, module in enumerate(modules):
        if module.marks and key("<pytestmark>", index) not in seen:  # a module-level skip or xfail applies to every test in it
            add("<pytestmark>", ast.List(elts=module.marks, ctx=ast.Load()), index)
        for name, node in module.defs.items():
            if _is_autouse(node) and key(name, index) not in seen:  # applies to every test of its scope without being named
                add(name, node, index)
    while todo:
        current = todo.pop()
        for name in sorted(_names(seen[current])):
            # the module the node lives in first (any definition), then the others (a conftest only by its fixtures)
            for index in [origin[current], *(i for i in range(len(modules)) if i != origin[current])]:
                found = modules[index].lookup(name)
                if found is not None and (index == origin[current] or index == 0 or _is_fixture(found)):
                    if key(name, index) not in seen:
                        add(name, found, index)
                    break
    return seen


def fingerprint(test: str, source: str, conftests: Sequence[str] = ()) -> str:
    """sha256 of the normalized test with its helpers, constants and fixtures (see the module docstring)."""
    parts = closure(test, source, conftests)
    # the test's own name is left out (a rename is not a change of the promise); helpers are named by what calls them
    body = {name: _canon(node) for name, node in sorted(parts.items()) if name != test}
    own = _canon(parts[test])
    own.pop("name")
    body["<test>"] = own
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def tests_in(source: str, prefix: str = "test_") -> list[str]:
    """The module-level test functions of a source file, in file order."""
    return [n.name for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith(prefix)]


def _covers_ids(decorators: Iterable[ast.AST]) -> list[str]:
    ids: list[str] = []
    for d in decorators:
        if _dotted(d).endswith("mark.covers") and isinstance(d, ast.Call):
            ids += [a.value for a in d.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    return ids


def covers_of(test: str, source: str) -> list[str]:
    """The AC ids the test declares: its own ``covers`` marks, then the module-level ``pytestmark``."""
    tree = ast.parse(source)
    ids: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == test:
            ids += _covers_ids(node.decorator_list)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            value = node.value
            ids += _covers_ids(value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value])
    return list(dict.fromkeys(ids))


def parse_move_map(spec_text: str) -> dict[str, str]:
    """``{old id: new id}`` from the ``## AC-Move-Map`` section of a spec (``{}`` when there is none)."""
    moves: dict[str, str] = {}
    inside = False
    for line in (spec_text or "").splitlines():
        if line.startswith("#"):
            inside = line.strip().lower() == MOVE_HEADING.lower()
        elif inside and line.startswith("|"):
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and AC_ID.match(cells[0]) and AC_ID.match(cells[1]):
                moves[cells[0]] = cells[1]
    return moves


def resolve_ac(ac_id: str, moves: Mapping[str, str]) -> str:
    """Follow ``ac_id`` through the move map to where it lives now (a cycle stops at the last id reached)."""
    seen = {ac_id}
    while ac_id in moves and moves[ac_id] not in seen:
        ac_id = moves[ac_id]
        seen.add(ac_id)
    return ac_id


def resolve_acs(ids: Iterable[str], moves: Mapping[str, str]) -> list[str]:
    return sorted({resolve_ac(i, moves) for i in ids})


def lock_entry(test: str, source: str, spec_text: str = "", conftests: Sequence[str] = ()) -> dict[str, Any]:
    """``{"acs": [...current ids...], "hash": ...}``: the AC ids sit beside the hash, never inside it."""
    ids = covers_of(test, source)
    bad = [i for i in ids if not AC_ID.match(i)]
    if bad or not ids:
        raise ValueError(f"{test}: a promise test needs well-formed covers ids (got {ids!r})")
    return {"acs": resolve_acs(ids, parse_move_map(spec_text)), "hash": fingerprint(test, source, conftests)}
