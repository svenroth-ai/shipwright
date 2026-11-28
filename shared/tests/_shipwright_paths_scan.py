"""Scanner behind ``test_shipwright_paths_guard.py`` (campaign root-files-into-config, R0b).

Finds every way a module can name a root ``shipwright_*`` file WITHOUT going through
``lib/shipwright_paths.py``, so the resolver stays the only place that knows where
those files live. Pure functions over ``git ls-files``; the test file owns the
allowlists and the assertions.

What counts as a reference (BRIEF 11.2 classes 1-4, 8 and 11.9 6c):

- **Python, name-like string constants** (no whitespace, so prose/messages are out): any
  registry basename, its regex-escaped form, or a ``shipwright_<stem>`` prefix of one
  (``_OMIT = r"^(...|shipwright_events|...)"``); f-string / ``+`` construction of
  ``shipwright_`` names; ``.lock`` / ``.json.lock`` construction (``X + ".lock"``,
  ``with_suffix(".json.lock")``, ``f"{p}.lock"``).
- **class 8**: a function that reads a git object / compares git output (``git show``,
  ``cat-file``, ``ls-tree``, ``--porcelain``, a ``blob(...)`` helper) and builds the path with
  ``rel()`` instead of ``rel_at()``.
- **``.shipwright/`` prefix rules** (regex, glob, ``startswith``) that cover the whole tree.
- **R1b joins**: ``<x> / _sp.rel(...)`` (also ``name()``/``legacy_rel()``, ``joinpath``, ``os.path.join``,
  through a conditional fallback) - a root join bypasses ``path()``, where R1c's lookup lives; and
  module-level constants bound to ``rel()`` (frozen at import), held to a closed inventory.
- **Carriers** (bash, YAML, JSON data, md, templates): a per-file COUNT of registry names,
  held to a ratchet baseline; they cannot call a Python resolver, so they flip with the
  plugin version in R3.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO / "shared" / "scripts" / "lib"))
import shipwright_paths as sp  # noqa: E402

BASENAMES = sorted(sp.all_basenames())
# the event log stays at the root (operator decision 0.2): only its exact name is a reference,
# not the ``shipwright_events`` prefix of its sibling dirs / module names
STEMS = sorted({b.rsplit(".", 1)[0] for b in BASENAMES if b.startswith("shipwright_") and "events" not in b})
_NAMELIKE = re.compile("|".join(re.escape(x) for x in [*STEMS, "audit_config.json"]))
_NAME_TOKEN = re.compile("|".join(re.escape(b) for b in sorted(BASENAMES, key=len, reverse=True)))
_WS = re.compile(r"\s")
_NAME_PREFIX = re.compile(r"(?:^|[^_A-Za-z])shipwright_$")
_TREE_PREFIX = re.compile(r"^\^?\(?(?:\?:)?\\?\.shipwright(?:/|\\/)(?:\*\*?|\.\*)?(?:$|[|)])")
_GIT_SHAPES = {"show", "cat-file", "ls-tree", "--porcelain", "--porcelain=v1"}
_BLOB_CALLS = {"blob", "blob_oid", "committed_bytes_reader", "read_committed_text", "_read_at_commit"}
BASELINE = Path(__file__).parent / "fixtures" / "shipwright_paths_carriers.json"
CARRIER_SUFFIXES = {".md", ".yml", ".yaml", ".json", ".sh", ".template", ".ps1", ".toml", ".txt"}
CARRIER_EXCLUDED_TOP = {"docs", ".shipwright", "integration-tests"}


def tracked(*pathspec: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "--", *pathspec],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return [p for p in out.split("\0") if p]


def is_test_path(rel: str) -> bool:
    parts = rel.split("/")
    return "tests" in parts or "testkit" in parts or parts[-1] == "conftest.py" or parts[0] == "integration-tests"


def production_py() -> list[str]:
    return [p for p in tracked("*.py") if not is_test_path(p) and p != "shared/scripts/lib/shipwright_paths.py"]


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body:
            first = n.body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant):
                ids.add(id(first.value))
    return ids


def _is_rel_call(n: ast.AST) -> bool:
    return (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in {"rel", "name", "path"} and isinstance(n.func.value, ast.Name)
            and n.func.value.id in {"_sp", "sp", "shipwright_paths"})


def _in_git_call(fn: ast.AST, target: ast.AST) -> bool:
    """True when *target* sits inside the arguments of a blob reader, a ``*git*`` call, or a call whose argv
    names git (``subprocess.run(["git", "show", ...])``) in *fn*."""
    for c in ast.walk(fn):
        if not isinstance(c, ast.Call) or c is target:
            continue
        argv_git = any(isinstance(x, ast.Constant) and x.value == "git" for a in c.args for x in ast.walk(a))
        if _call_name(c) in _BLOB_CALLS or "git" in _call_name(c) or argv_git:
            if any(target is x for arg in [*c.args, *(k.value for k in c.keywords)] for x in ast.walk(arg)):
                return True
    return False


def _call_name(n: ast.Call) -> str:
    return n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")


def _has_rel(n: ast.AST, attrs: frozenset[str] = frozenset({"rel"})) -> bool:
    """*n* is, or (through a conditional fallback) yields, a resolver call named in *attrs*."""
    if isinstance(n, ast.IfExp):
        return _has_rel(n.body, attrs) or _has_rel(n.orelse, attrs)
    if isinstance(n, ast.Starred):
        return _has_rel(n.value, attrs)
    if isinstance(n, (ast.Tuple, ast.List)):
        return any(_has_rel(e, attrs) for e in n.elts)
    if isinstance(n, ast.Call) and _call_name(n) in _WRAPPERS:
        return any(_has_rel(a, attrs) for a in n.args)  # Path(_sp.rel(k)), Path(_sp.rel(k), "sub"), str(...)
    return (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in attrs
            and isinstance(n.func.value, ast.Name) and n.func.value.id in _RECEIVERS)


def _is_guarded_fallback(n: ast.AST) -> bool:
    """Exactly ``"<literal>" if <resolver> is None else <resolver>.rel(...)`` (the R1a-pinned shape)."""
    return (isinstance(n, ast.IfExp) and isinstance(n.test, ast.Compare) and isinstance(n.test.left, ast.Name)
            and n.test.left.id in _RECEIVERS and len(n.test.ops) == 1 and isinstance(n.test.ops[0], ast.Is)
            and isinstance(n.test.comparators[0], ast.Constant) and n.test.comparators[0].value is None
            and isinstance(n.body, ast.Constant) and isinstance(n.body.value, str) and _has_rel(n.orelse))


#: a root joined with any of these bypasses ``path()`` (``name()`` / ``legacy_rel()`` give a root-file name too)
_JOINED = frozenset({"rel", "name", "legacy_rel"})
#: a module constant bound to any of these is frozen at import (``name()`` gives a basename: matching, not a path)
_FROZEN = frozenset({"rel", "legacy_rel", "path", "main_path"})
_WRAPPERS = {"Path", "PurePath", "PurePosixPath", "PureWindowsPath", "str"}
#: only these receivers are seen (``m.rel`` via another module alias or attribute access is a blind spot, BRIEF 12.10d)
_RECEIVERS = {"_sp", "sp", "shipwright_paths"}


def _is_path_join(n: ast.Call) -> bool:
    """``os.path.join`` / ``posixpath.join`` / ``ntpath.join``, or ``"/".join`` / ``os.sep.join``; never a message
    or pathspec join (``", ".join``, ``shlex.join``)."""
    if _call_name(n) != "join" or not isinstance(n.func, ast.Attribute):
        return False
    recv = ast.unparse(n.func.value)
    return recv in {"os.path", "posixpath", "ntpath", "os.sep", "'/'", "'\\\\'"}


def _rel_joins(n: ast.AST) -> tuple[str, str] | None:
    """R1b: a filesystem join on ``rel()`` bypasses ``path()`` and with it R1c's new-then-old lookup.
    ``(rule, text)``: the guarded fallback ``root / ("<lit>" if _sp is None else _sp.rel(k))`` is its own rule
    (``rel-join-fallback``) so a file allowed that shape still fails on a plain join."""
    if isinstance(n, (ast.BinOp, ast.AugAssign)) and isinstance(n.op, ast.Div):
        sides = [n.right, n.left] if isinstance(n, ast.BinOp) else [n.value]  # rel() on either side of "/"
        operand = next((s for s in sides if _has_rel(s, _JOINED)), None)
        text = "<x> / rel(...)"
    elif isinstance(n, ast.Call) and (_call_name(n) == "joinpath" or _is_path_join(n) or (
            _call_name(n) in _WRAPPERS - {"str"} and (len(n.args) > 1 or any(isinstance(a, ast.Starred) for a in n.args)))):
        receiver = [n.func.value] if _call_name(n) == "joinpath" and isinstance(n.func, ast.Attribute) else []
        operand = next((a for a in [*n.args, *receiver] if _has_rel(a, _JOINED)), None)
        text = f"{_call_name(n)}(..., rel(...))"
    else:
        return None
    if operand is None:
        return None
    return ("rel-join-fallback" if _is_guarded_fallback(operand) else "rel-join"), text


def _module_assigns(body: list[ast.stmt]):
    for s in body:
        if isinstance(s, (ast.Assign, ast.AnnAssign)) and s.value is not None:
            yield s
        elif isinstance(s, ast.If):
            yield from _module_assigns(s.body + s.orelse)
        elif isinstance(s, ast.Try):
            yield from _module_assigns(s.body + s.orelse + s.finalbody + [x for h in s.handlers for x in h.body])


def _walk_eager(n: ast.AST):
    """``ast.walk`` that does not descend into a lambda (its body is not evaluated at import)."""
    if isinstance(n, ast.Lambda):
        return
    yield n
    for c in ast.iter_child_nodes(n):
        yield from _walk_eager(c)


def rel_constants(tree: ast.Module) -> list[tuple[int, str]]:
    """Module-level names bound to a value built from ``rel()`` / ``legacy_rel()`` / ``path()`` (BRIEF 12.1:
    frozen at import). A lambda body runs at use time, so it is skipped. Not seen: class bodies, default arguments,
    module-level for/with (none exist today). One entry per binding, so rebinding a name counts again."""
    out = []
    for s in _module_assigns(tree.body):
        if any(_has_rel(c, _FROZEN) for c in _walk_eager(s.value)):
            targets = s.targets if isinstance(s, ast.Assign) else [s.target]
            names = [x for t in targets for x in ast.walk(t) if isinstance(x, ast.Name)]
            out += [(s.lineno, x.id) for x in names]
    return out


def scan_python(rel: str) -> list[tuple[str, int, str]]:
    """``(rule, line, text)`` violations in one production file."""
    tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
    skip = _docstring_ids(tree)
    out: list[tuple[str, int, str]] = [("rel-constant", line, name) for line, name in rel_constants(tree)]
    for n in ast.walk(tree):
        join = _rel_joins(n)
        if join:
            out.append((join[0], n.lineno, f"{join[1]}: use _sp.path(key, root)"))
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip:
            v = n.value
            if not _WS.search(v) and (_NAMELIKE.search(v) or sp.rel("events") in v):
                out.append(("literal", n.lineno, v[:80]))
            if not _WS.search(v) and (_TREE_PREFIX.match(v) or v in {".shipwright/**", ".shipwright/*", "**/.shipwright/**"}):
                out.append(("shipwright-prefix-rule", n.lineno, v[:80]))
        if isinstance(n, ast.JoinedStr):
            consts = [x.value for x in n.values if isinstance(x, ast.Constant) and isinstance(x.value, str)]
            if any(_NAME_PREFIX.search(c) for c in consts):
                out.append(("constructed-name", n.lineno, "f-string builds shipwright_<name>"))
            if any(c.endswith(".lock") for c in consts) and len(n.values) > 1:
                out.append(("lock-construction", n.lineno, "f-string ends in .lock"))
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            for side in (n.left, n.right):
                if isinstance(side, ast.Constant) and isinstance(side.value, str):
                    if _NAME_PREFIX.search(side.value):
                        out.append(("constructed-name", n.lineno, "concatenation builds shipwright_<name>"))
                    if side.value in {".lock", ".json.lock"}:
                        out.append(("lock-construction", n.lineno, side.value))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr == "with_suffix" and n.args and isinstance(n.args[0], ast.Constant) \
                    and "lock" in str(n.args[0].value):
                out.append(("lock-construction", n.lineno, f"with_suffix({n.args[0].value!r})"))
            if n.func.attr == "startswith":
                for a in n.args:
                    elts = [a] if isinstance(a, ast.Constant) else (a.elts if isinstance(a, ast.Tuple) else [])
                    if any(isinstance(e, ast.Constant) and e.value in {".shipwright/", ".shipwright"} for e in elts):
                        out.append(("shipwright-prefix-rule", n.lineno, "startswith('.shipwright/')"))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            consts = {c.value for c in ast.walk(n) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
            git_shape = bool(consts & _GIT_SHAPES) or any(
                isinstance(c, ast.Call) and _call_name(c) in _BLOB_CALLS for c in ast.walk(n))
            if git_shape:
                for c in ast.walk(n):
                    # path() is a working-tree read beside the git one (R1c-2); it counts only as a git ARGUMENT
                    if _is_rel_call(c) and (c.func.attr != "path" or _in_git_call(n, c)):
                        out.append(("class8-uses-rel", c.lineno, f"{n.name}: reads git objects/status but calls rel(); use rel_at()"))
    return out


def carrier_files() -> list[str]:
    out = []
    for p in tracked():
        top = p.split("/")[0]
        if top in CARRIER_EXCLUDED_TOP or is_test_path(p) or p.endswith(".py") or p.startswith("CHANGELOG"):
            continue
        if "/tests/" in p or p == "shared/tests/fixtures/shipwright_paths_carriers.json":
            continue
        if Path(p).suffix in CARRIER_SUFFIXES or p.startswith("scripts/hooks/"):
            out.append(p)
    return out


def carrier_counts() -> dict[str, dict[str, int]]:
    """path -> {root file name: occurrences}; per NAME so swapping one reference for another fails."""
    counts: dict[str, dict[str, int]] = {}
    for p in carrier_files():
        try:
            text = (REPO / p).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found = _NAME_TOKEN.findall(text)
        if found:
            counts[p] = {n: found.count(n) for n in sorted(set(found))}
    return counts


def load_baseline() -> dict[str, dict[str, int]]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))["files"]


if __name__ == "__main__":  # regenerate: uv run python shared/tests/_shipwright_paths_scan.py --write
    if "--write" in sys.argv:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        data = {"_about": "Ratchet for non-Python carriers of root shipwright_* names (bash, YAML, JSON data, md, "
                          "templates): per-file, per-name COUNT may only fall. R3 flips these with the plugin version.",
                "files": dict(sorted(carrier_counts().items()))}
        BASELINE.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(len(carrier_counts()), "carrier files")
