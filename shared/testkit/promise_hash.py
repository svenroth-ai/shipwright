"""The fingerprint of a promise test, for the promise lock (programme P21). Stdlib only.

A promise test is locked by hash: a change to what it asserts must be a decision, a change to how it is written must not.
``fingerprint`` hashes a *normalized* form of the test function that

* ignores formatting, comments (the parser drops them), docstrings, the order of imports, the imports nothing reaches and
  the ``covers`` mark (it names the AC: a re-anchor shows as an id change, never as a body change). EVERY other mark is
  hashed - skip, xfail, parametrize, usefixtures, and also slow or cross_plugin, which CI deselects - because adding one is
  the cheapest way to weaken a locked test;
* includes, transitively, every binding of every module-level function, class, constant and IMPORT the test names (in
  file order: ``def h`` followed by ``h = lambda: None`` is two bindings, both hashed; ``from . import oracle`` and
  ``from . import scenario_support as oracle`` hash differently), and every fixture it requests (a parameter that is a
  ``@pytest.fixture`` function of the module or of a ``conftest.py`` handed in);
* includes in every closure what applies without being named: an ``autouse`` fixture (anything but the literal
  ``autouse=False``) and a module-level ``pytest_*`` hook such as ``pytest_generate_tests``.

The serialization is written by hand (not ``ast.dump``): ``ast.dump`` prints version-specific fields (``type_params``
since 3.12), so a lock written on one interpreter would read as a diff on another. Here a field that is ``None`` or an
empty list is left out, and ``type_comment`` / ``kind`` are never read. A test pins a literal digest (3.11 = 3.12 = 3.13).

Known limits (a test cannot tell these apart from a real change, and the lock's reviewer must know): a helper imported
from another module is NOT followed - only its import binding is hashed (the golden helper modules, the parent
``conftest.py`` files and ``golden/__init__.py`` are frozen files in their own right, in ``REQUIRED`` of
``test_trace_freeze.py``); a method of a test class is not found (the golden tests are plain functions); names bound at
run time (``getattr``, ``request.getfixturevalue``) are invisible; so are bindings inside a module-level if/try/with and
in-place mutations such as ``CASES.append(...)``; a helper's parameter that shadows a module-level name still pulls that
name in (over-inclusion: a harmless extra hash change, never a missed one); a test name bound twice is refused.

The AC ids and the lock's entries (``path::name``) live in ``promise_lock.py``; ``covers_of`` stays here (it reads the marks).
"""

from __future__ import annotations

import ast
import hashlib
import json
from typing import Any, Iterable, Sequence

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


# a mark can change what runs or whether it counts: weakening a test with any mark but covers must move the hash
# (CI deselects ``slow`` and ``cross_plugin``, so even those move the hash). Only a name listed here is ignored.
_DESCRIPTIVE_MARKS = ("covers",)


def _is_marker(decorator: ast.AST) -> bool:
    """The one descriptive ``pytest.mark.*`` decorator, ``covers`` (it names the AC and is stored beside the hash); every other mark is hashed."""
    name = _dotted(decorator)
    return name.startswith(("pytest.mark.", "mark.")) and name.rsplit(".", 1)[-1] in _DESCRIPTIVE_MARKS


def _is_fixture(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
        _dotted(d).endswith("fixture") for d in node.decorator_list)


def _is_autouse(node: ast.AST) -> bool:
    """A fixture that applies without being named: ``autouse=`` is anything but the literal ``False`` (a variable, ``**options``)."""
    def on(k: ast.keyword) -> bool:
        return k.arg is None or (k.arg == "autouse" and not (isinstance(k.value, ast.Constant) and k.value.value is False))
    return _is_fixture(node) and any(isinstance(d, ast.Call) and any(on(k) for k in d.keywords) for d in node.decorator_list)


def _is_hook(node: ast.AST) -> bool:
    """A module-level ``pytest_*`` function (``pytest_generate_tests`` ...): pytest calls it without any name reaching it."""
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("pytest_")


def _assign_targets(node: ast.AST) -> list[ast.expr]:
    """The targets a module-level statement binds, for ``=``, ``name: T = v`` and ``name += v`` alike (one helper for ``Module`` and ``covers_of``)."""
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, ast.AnnAssign) and node.value is not None:
        return [node.target]
    return [node.target] if isinstance(node, ast.AugAssign) else []


def _is_pytestmark(node: ast.AST) -> bool:
    return any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in _assign_targets(node))


def _mark_elements(node: ast.AST) -> list[ast.AST]:
    value = node.value  # type: ignore[attr-defined]
    return list(value.elts) if isinstance(value, (ast.List, ast.Tuple)) else [value]


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
    """The module-level bindings of one source file, by name."""

    def __init__(self, source: str) -> None:
        # every statement that binds a name - def, class, constant, import - in file order: none overwrites another
        self.bindings: dict[str, list[ast.AST]] = {}
        self.marks: list[ast.AST] = []  # module-level ``pytestmark`` marks that change what runs (skip, xfail, parametrize ...)
        for node in ast.parse(source).body:
            if _is_pytestmark(node):
                self.marks += [m for m in _mark_elements(node) if not _is_marker(m)]
            elif isinstance(node, _DEFS):
                self._bind(node.name, node)
                for d in node.decorator_list:  # ``@pytest.fixture(name="x")`` is requested as ``x``
                    if isinstance(d, ast.Call) and _dotted(d).endswith("fixture"):
                        for k in d.keywords:
                            if k.arg == "name" and isinstance(k.value, ast.Constant) and isinstance(k.value.value, str):
                                self._bind(k.value.value, node)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:  # one name of a multi-name import is hashed alone: its neighbours are none of its business
                    single = (ast.Import(names=[alias]) if isinstance(node, ast.Import)
                              else ast.ImportFrom(module=node.module, names=[alias], level=node.level))
                    self._bind(alias.asname or alias.name.split(".")[0], single)
            else:
                for target in _assign_targets(node):
                    for name in (n.id for n in ast.walk(target) if isinstance(n, ast.Name)):  # tuple unpacking binds several
                        self._bind(name, node)

    def _bind(self, name: str, node: ast.AST) -> None:
        self.bindings.setdefault(name, []).append(node)

    def lookup(self, name: str) -> ast.AST | None:
        nodes = self.bindings.get(name)
        if not nodes:
            return None
        return nodes[0] if len(nodes) == 1 else ast.Module(body=nodes, type_ignores=[])

    def always(self) -> list[str]:
        """The names that apply to every test of the module without being named: autouse fixtures and ``pytest_*`` hooks."""
        return [name for name, nodes in self.bindings.items() if any(_is_autouse(n) or _is_hook(n) for n in nodes)]


def _each(node: ast.AST) -> list[ast.AST]:
    """The statements behind a lookup result: the node itself, or every binding of a rebound name."""
    return list(node.body) if isinstance(node, ast.Module) else [node]


def _names(node: ast.AST) -> set[str]:
    found = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    for call in (n for n in ast.walk(node) if isinstance(n, ast.Call) and _dotted(n.func).endswith("usefixtures")):
        found |= {a.value for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)}  # named by string
    for each in _each(node):
        if isinstance(each, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found |= {a.arg for a in (*each.args.posonlyargs, *each.args.args, *each.args.kwonlyargs)}
    return found


def closure(test: str, source: str, conftests: Sequence[str] = ()) -> dict[str, ast.AST]:
    """The test and everything it needs: helpers, constants, classes, fixtures and the module's behaviour marks, transitively.

    Keys are the names found; a name found in a ``conftest.py`` is keyed ``name@<n>`` (n = its position in ``conftests``,
    from 1), so the same name in two modules never collapses into one entry."""
    modules = [Module(source), *(Module(text) for text in conftests)]
    if len(modules[0].bindings.get(test, [])) > 1:
        raise ValueError(f"{test}: bound more than once at module level (pytest would run only the last binding)")
    start = modules[0].lookup(test)
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
        for name in module.always():  # an autouse fixture or a pytest_* hook applies to every test without being named
            if key(name, index) not in seen:
                add(name, module.lookup(name), index)
    while todo:
        current = todo.pop()
        for name in sorted(_names(seen[current])):
            # the module the node lives in first (any definition), then the others (a conftest only by its fixtures)
            for index in [origin[current], *(i for i in range(len(modules)) if i != origin[current])]:
                found = modules[index].lookup(name)
                if found is not None and (index == origin[current] or index == 0 or any(_is_fixture(n) for n in _each(found))):
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
        elif _is_pytestmark(node):
            ids += _covers_ids(_mark_elements(node))
    return list(dict.fromkeys(ids))
