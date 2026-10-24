"""Rules of the ``*.py`` guard (campaign stack-profile-resolver S5); the tests are in
``test_stack_profile_py_guard.py``, the markdown half is ``test_stack_profile_prose_guard.py``.

Two rules over every tracked, non-test module under ``plugins/`` and ``shared/scripts/``
("test" means a ``tests``/``test`` directory or ``conftest.py``: a production module such as
``plugins/shipwright-test/scripts/lib/test_runner.py`` is scanned):

1. **No hand-built stack-profile path.** A string constant that is a path through a ``profiles``
   directory (``"profiles"``, ``".shipwright/profiles/x.json"``, ``shared/profiles``) outside the
   resolver family bypasses the resolver (project > user > bundled order, validation, shadow
   warning). Docstrings, dict keys, subscripts and the key argument of ``.get/.pop/.setdefault``
   are not paths; prose with whitespace is not a path. Every ``ALLOWLIST`` entry must still excuse
   a real finding (reverse test). **Accepted blind spot:** public helpers that return a profile
   directory (``bundled_dir``, ``search_dirs``, ``_PROFILES_DIR``, ``_profiles_dir``) are not flagged.
2. **No swallowed resolver error.** A ``try`` whose body calls the resolver API (or a wrapper of it,
   see below) and whose handler catches ``ValueError`` / ``Exception`` / a bare ``except`` / a
   ``Profile*`` error class must: re-raise; exit non-zero; return a non-zero int; return a call that
   RECEIVES the caught exception (``return _fail(exc)``); or branch on ``.kind`` / ``.exit_code``
   (read in an ``if`` / conditional / comparison / ``match`` test, or returned / passed as the exit
   code). A mere mention of ``.kind`` in a message is not a branch; ``return {}``, ``return default()``
   and ``return _skipped(...)`` are swallows. Keyed on the pattern, not on exception class identity
   (the classes are not nameable across import paths, D2), except the ``Profile*`` suffix check.
   The exceptions are listed in ``SWALLOW_ALLOWLIST`` with a reason (BRIEF S5 item 3 names the S3
   matcher's ``warnings[]``; the others are the same family, see the ADR).

   **Wrappers.** A function that calls the resolver outside its own protective ``try`` is itself a
   resolver call for the rest of its module (one-level closure, run to a fixpoint). Cross-module
   wrappers are pinned by name in ``PINNED_WRAPPERS`` (reverse-checked: each must still be defined).

Reads the git INDEX (``index_files``). Tagged to FR-01.06; see test_profile_resolver.py for the FR note.
"""

from __future__ import annotations

import ast
import functools

from shared.tests.index_files import read_index, tracked

# Rule 1 -- files that may name a "profiles" directory, and why. Reverse-checked.
ALLOWLIST: dict[str, str] = {
    "shared/scripts/profile_model.py": "the resolver itself: search dirs (project, user, bundled)",
    "shared/scripts/dev_server/_paths.py": "bundled dir handed to the resolver (search_dirs_with_bundled); the "
                                           "dev_server._profiles_dir monkeypatch surface of the existing tests",
    "shared/scripts/tools/validate_deploy_profile.py": "deploy profiles have their own schema and validator",
}

# Rule 2 -- calls that raise the resolver's ValueError family (resolver API + the shared consumer layer).
RESOLVER_CALLS = frozenset({
    "resolve_profile", "list_profiles", "load_profile_file", "validate_profile_data",
    "resolve_named", "load_explicit", "resolve_effective", "resolve_in_dir", "check_name", "config_profile",
})
# Names that are also ordinary helpers elsewhere (pr_readiness.check_name): only an ATTRIBUTE call counts.
ATTRIBUTE_ONLY = frozenset({"check_name"})
# Cross-module wrappers of the resolver, pinned by name (reverse-checked to still exist).
PINNED_WRAPPERS = frozenset({"load_resolved", "get_test_command", "resolve_profile_name", "_resolve_profile"})
PROFILE_ERRORS = ("ProfileError", "ProfileNotFound", "ProfileInvalid", "ProfileSchemaDrift")

# (file, function) pairs allowed to swallow, with the reason. Reverse-checked.
SWALLOW_ALLOWLIST: dict[tuple[str, str], str] = {
    ("plugins/shipwright-adopt/scripts/lib/profile_matcher.py", "_discover"):
        "S3 discovery: an invalid candidate becomes a warnings[] entry and keeps its name (D1)",
    ("plugins/shipwright-adopt/scripts/lib/adopt_profile.py", "hint_warning"):
        "its string is appended to the snapshot's profile.warnings[] (same S3 family); the hint is resolved "
        "again, loudly, at generation",
    ("shared/scripts/profile_resolver.py", "_row"):
        "resolver discovery (`list`): an invalid candidate becomes a valid:false row carrying error and kind (D1)",
    ("plugins/shipwright-project/scripts/lib/profile_check.py", "profile_error"):
        "returns the failure reason string; both callers exit 4 on it (write_run_config, write-project-config)",
}


def _is_test_file(rel: str) -> bool:
    """By LOCATION only: a ``test_`` file name does not make a production module a test."""
    parts = rel.split("/")
    return "tests" in parts[:-1] or "test" in parts[:-1] or parts[-1] == "conftest.py"


@functools.lru_cache(maxsize=1)
def _modules() -> dict[str, str]:
    names = [n for n in tracked("plugins/*.py", "shared/scripts/*.py") if not _is_test_file(n)]
    return {n: b.decode("utf-8") for n, b in read_index(names).items()}


# ---------------------------------------------------------------------------------- rule 1


def _skipped_constants(tree: ast.AST) -> set[int]:
    """ids of string constants that are not paths: docstrings, dict keys, subscripts, .get(key) args."""
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                skip.add(id(body[0].value))
        elif isinstance(node, ast.Dict):
            skip.update(id(k) for k in node.keys if k is not None)
        elif isinstance(node, ast.Subscript):
            skip.add(id(node.slice))
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr in ("get", "pop", "setdefault") and node.args):
            skip.add(id(node.args[0]))
    return skip


def _is_profiles_path(value: str) -> bool:
    flat = value.replace("\\", "/")
    if any(c.isspace() for c in flat):  # prose (help text, messages) is not a path
        return False
    return "/profiles/" in f"/{flat}/" or "shared/profiles" in flat  # a directory OR a file below it


def path_findings(source: str, rel: str = "<src>") -> list[str]:
    tree = ast.parse(source)
    skip = _skipped_constants(tree)
    return [f"{rel}:{n.lineno}: {n.value[:80]!r}" for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip
            and _is_profiles_path(n.value)]


# ---------------------------------------------------------------------------------- rule 2


def _call_name(node: ast.Call) -> str:
    f = node.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def _is_resolver_call(node: ast.AST, wrappers: frozenset[str] | set[str]) -> bool:
    if not isinstance(node, ast.Call):
        return False
    name = _call_name(node)
    if name in ATTRIBUTE_ONLY and not isinstance(node.func, ast.Attribute):
        return False
    return name in RESOLVER_CALLS or name in wrappers


def _handler_names(handler: ast.ExceptHandler) -> list[str]:
    t = handler.type
    if t is None:
        return []
    return [e.id if isinstance(e, ast.Name) else e.attr
            for e in (t.elts if isinstance(t, ast.Tuple) else [t]) if isinstance(e, (ast.Name, ast.Attribute))]


def _catches_value_error(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    return any(n in ("ValueError", "Exception", "BaseException") or n.endswith(PROFILE_ERRORS)
               for n in _handler_names(handler))


def _is_exit_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _call_name(node) in ("exit", "_exit", "SystemExit")


def _exits_zero(call: ast.Call) -> bool:
    """``sys.exit()``, ``sys.exit(0)``, ``SystemExit(None)``: success is not a failure exit."""
    return not call.args or (isinstance(call.args[0], ast.Constant) and call.args[0].value in (0, None))


def _mentions_kind(tree: ast.AST) -> bool:
    return any((isinstance(n, ast.Attribute) and n.attr in ("kind", "exit_code"))
               or (isinstance(n, ast.Constant) and n.value in ("kind", "exit_code")) for n in ast.walk(tree))


def _branches_on_kind(handler: ast.ExceptHandler) -> bool:
    """``.kind`` / ``.exit_code`` read in a test, or returned directly as the code."""
    for stmt in handler.body:
        for n in ast.walk(stmt):
            tests = []
            if isinstance(n, (ast.If, ast.IfExp, ast.While, ast.Assert)):
                tests.append(n.test)
            elif isinstance(n, ast.Compare):
                tests.append(n)
            elif isinstance(n, ast.Match):
                tests.append(n.subject)
            elif isinstance(n, ast.Return) and n.value is not None:
                v = n.value
                if isinstance(v, ast.Attribute) or (isinstance(v, ast.Call) and _call_name(v) == "getattr"):
                    tests.append(v)
            if any(_mentions_kind(t) for t in tests):
                return True
    return False


def _receives(call: ast.Call, name: str | None) -> bool:
    if not name:
        return False
    args = [*call.args, *(k.value for k in call.keywords)]
    return any(isinstance(a, ast.Name) and a.id == name for a in args)


def _handles_loudly(handler: ast.ExceptHandler) -> bool:
    for n in (m for stmt in handler.body for m in ast.walk(stmt)):
        if isinstance(n, ast.Raise):
            if not (_is_exit_call(n.exc) and _exits_zero(n.exc)):  # `raise SystemExit(0)` swallows
                return True
        elif _is_exit_call(n) and not _exits_zero(n):
            return True
        elif isinstance(n, ast.Return) and n.value is not None:
            v = n.value
            if isinstance(v, ast.Constant) and isinstance(v.value, int) and not isinstance(v.value, bool) and v.value != 0:
                return True
            if isinstance(v, ast.Call) and _receives(v, handler.name):
                return True
    return _branches_on_kind(handler)


def _scope_nodes(scope: ast.AST):
    """Nodes of ``scope`` itself: nested functions and classes (methods) are their own scopes."""
    todo = list(ast.iter_child_nodes(scope))
    while todo:
        node = todo.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            todo.extend(ast.iter_child_nodes(node))


def _unprotected_resolver_call(fn: ast.AST, wrappers: set[str]) -> bool:
    """True when ``fn`` calls the resolver outside a ``try`` body that catches ValueError."""
    protected: set[int] = set()
    nodes = list(_scope_nodes(fn))
    for t in (n for n in nodes if isinstance(n, ast.Try) and any(_catches_value_error(h) for h in n.handlers)):
        protected.update(id(m) for s in t.body for m in ast.walk(s))
    return any(_is_resolver_call(n, wrappers) and id(n) not in protected for n in nodes)


def module_wrappers(tree: ast.AST) -> set[str]:
    """One-level closure, to a fixpoint: functions of this module that let a resolver error through."""
    funcs = {f.name: f for f in ast.walk(tree) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
    found: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, fn in funcs.items():
            if name not in found and _unprotected_resolver_call(fn, found):
                found.add(name)
                changed = True
    return found


def swallow_findings(source: str, rel: str = "<src>") -> list[str]:
    tree = ast.parse(source)
    wrappers = module_wrappers(tree) | PINNED_WRAPPERS
    found = []
    for fn in (n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module))):
        scope = fn.name if not isinstance(fn, ast.Module) else "<module>"
        for node in (n for n in _scope_nodes(fn) if isinstance(n, ast.Try)):
            if not any(_is_resolver_call(c, wrappers) for s in node.body for c in ast.walk(s)):
                continue
            for h in node.handlers:
                if _catches_value_error(h) and not _handles_loudly(h):
                    found.append(f"{rel}:{h.lineno}: {scope}")
    return sorted(set(found))


def _all_swallows() -> list[tuple[str, str, str]]:
    out = []
    for rel, src in _modules().items():
        for f in swallow_findings(src, rel):
            out.append((rel, f.rsplit(": ", 1)[1], f))
    return out


