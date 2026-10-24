"""``*.py`` guard (campaign stack-profile-resolver S5; the markdown half is
``test_stack_profile_prose_guard.py``).

Two rules over every tracked, non-test module under ``plugins/`` and ``shared/scripts/``:

1. **No hand-built stack-profile path.** A string constant ``"profiles"`` (or a path containing
   ``/profiles/``) outside the resolver family is a lookup that bypasses the resolver (project >
   user > bundled order, validation, shadow warning). Docstrings, dict keys and subscripts are not
   paths and are ignored. Every ``ALLOWLIST`` entry must still excuse a real finding (reverse test).
2. **No swallowed resolver error.** A ``try`` whose body calls the resolver API and whose handler
   catches ``ValueError`` (or ``Exception`` / a bare ``except``) must re-raise, exit non-zero, return
   a non-zero code / a call (``return _fail(exc)``), or branch on ``.kind`` / ``.exit_code``. Keyed on
   the pattern, not on exception class names: the classes are not nameable across import paths
   (D2). Single allowlisted exception: the S3 matcher's ``warnings[]`` (D1: discovery skips an
   invalid candidate, a selection never does).

Reads the git INDEX (``index_files``). Tagged to FR-01.06; see test_profile_resolver.py for the FR note.
"""

from __future__ import annotations

import ast
import functools

import pytest

from shared.tests.index_files import read_index, tracked

pytestmark = pytest.mark.covers("FR-01.06")

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
    "resolve_named", "load_explicit", "resolve_effective",
})
# (file, function) pairs allowed to swallow, with the reason. Reverse-checked.
SWALLOW_ALLOWLIST: dict[tuple[str, str], str] = {
    ("plugins/shipwright-adopt/scripts/lib/profile_matcher.py", "_discover"):
        "S3 discovery: an invalid candidate becomes a warnings[] entry and keeps its name (D1)",
}


def _is_test_file(rel: str) -> bool:
    parts = rel.split("/")
    name = parts[-1]
    return ("tests" in parts or "test" in parts or name.startswith("test_") or name == "conftest.py")


@functools.lru_cache(maxsize=1)
def _modules() -> dict[str, str]:
    names = [n for n in tracked("plugins/*.py", "shared/scripts/*.py") if not _is_test_file(n)]
    return {n: b.decode("utf-8") for n, b in read_index(names).items()}


def _skipped_constants(tree: ast.AST) -> set[int]:
    """ids of string constants that are not paths: docstrings, dict keys, subscript indexes."""
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


def _call_name(node: ast.Call) -> str:
    f = node.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def _catches_value_error(handler: ast.ExceptHandler) -> bool:
    t = handler.type
    if t is None:
        return True
    names = [e.id for e in (t.elts if isinstance(t, ast.Tuple) else [t]) if isinstance(e, ast.Name)]
    return any(n in ("ValueError", "Exception", "BaseException") for n in names)


def _is_exit_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _call_name(node) in ("exit", "_exit", "SystemExit")


def _exits_zero(call: ast.Call) -> bool:
    """``sys.exit()``, ``sys.exit(0)``, ``SystemExit(None)``: success is not a failure exit."""
    return not call.args or (isinstance(call.args[0], ast.Constant) and call.args[0].value in (0, None))


def _handles_loudly(handler: ast.ExceptHandler) -> bool:
    for n in (m for stmt in handler.body for m in ast.walk(stmt)):
        if isinstance(n, ast.Raise):
            if not (_is_exit_call(n.exc) and _exits_zero(n.exc)):  # `raise SystemExit(0)` swallows
                return True
        elif _is_exit_call(n) and not _exits_zero(n):
            return True
        if isinstance(n, ast.Attribute) and n.attr in ("kind", "exit_code"):
            return True
        if isinstance(n, ast.Constant) and n.value in ("kind", "exit_code"):  # getattr(exc, "kind", ...)
            return True
        if isinstance(n, ast.Return) and n.value is not None:
            v = n.value
            if isinstance(v, ast.Call) or (isinstance(v, ast.Constant) and isinstance(v.value, int)
                                           and not isinstance(v.value, bool) and v.value != 0):
                return True
    return False


def _scope_nodes(scope: ast.AST):
    """Nodes of ``scope`` itself: nested functions and classes (methods) are their own scopes."""
    todo = list(ast.iter_child_nodes(scope))
    while todo:
        node = todo.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            todo.extend(ast.iter_child_nodes(node))


def swallow_findings(source: str, rel: str = "<src>") -> list[str]:
    tree = ast.parse(source)
    found = []
    for fn in (n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module))):
        scope = fn.name if not isinstance(fn, ast.Module) else "<module>"
        for node in (n for n in _scope_nodes(fn) if isinstance(n, ast.Try)):
            calls = {_call_name(c) for s in node.body for c in ast.walk(s) if isinstance(c, ast.Call)}
            if not calls & RESOLVER_CALLS:
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


def test_no_module_builds_a_stack_profile_path_outside_the_resolver():
    bad = [f for rel, src in _modules().items() if rel not in ALLOWLIST for f in path_findings(src, rel)]
    assert not bad, "go through profile_resolver / profile_consumer, not a hand-built path:\n" + "\n".join(bad)


def test_every_path_allowlist_entry_still_excuses_a_real_finding():
    stale = [rel for rel in ALLOWLIST if not path_findings(_modules().get(rel, ""), rel)]
    assert not stale, f"allowlist entries excuse no finding: {stale}"


def test_no_caller_swallows_a_resolver_error():
    bad = [f for rel, scope, f in _all_swallows() if (rel, scope) not in SWALLOW_ALLOWLIST]
    assert not bad, (
        "an `except ValueError` around a resolver call must re-raise, exit non-zero, return a failure "
        "or branch on .kind:\n" + "\n".join(bad))


def test_every_swallow_allowlist_entry_still_excuses_a_real_finding():
    live = {(rel, scope) for rel, scope, _ in _all_swallows()}
    stale = [k for k in SWALLOW_ALLOWLIST if k not in live]
    assert not stale, f"swallow allowlist entries excuse no finding: {stale}"


def test_path_rule_is_red_on_planted_forms_and_green_on_the_neighbours():
    for planted in ('os.path.join(root, "profiles", "x.json")', 'Path(root) / "shared" / "profiles"',
                    'p = "shared/profiles/vite-hono.json"', 'join(home, ".shipwright", "profiles")',
                    'd = root + "/.shipwright/profiles/"', 'p = Path(root) / ".shipwright/profiles/my-stack.json"',
                    'p = "~/.shipwright/profiles/user-stack.json"'):
        assert path_findings(planted), planted
    for fine in ('"""Docstring about shared/profiles."""', 'x = listing["profiles"]', 'd = {"profiles": rows}',
                 '# shared/profiles in a comment', 'p = "profile_resolver"', 'p = "deploy-profile.json"'):
        assert not path_findings(fine), fine


def test_swallow_rule_is_red_on_planted_handlers_and_green_on_the_loud_ones():
    swallowed = [
        "def f():\n    try:\n        pr.resolve_profile(n)\n    except ValueError:\n        return None\n",
        "def f():\n    try:\n        pc.resolve_named(n, r)\n    except Exception:\n        pass\n",
        "def f():\n    try:\n        load_profile_file(p)\n    except:\n        data = {}\n",
        "def f():\n    try:\n        pr.list_profiles(r)\n    except ValueError as e:\n        print(e)\n        return 0\n",        "def f():\n    try:\n        pr.resolve_profile(n)\n    except ValueError:\n        sys.exit(0)\n",
        "def f():\n    try:\n        pr.resolve_profile(n)\n    except ValueError:\n        sys.exit()\n",
        "def f():\n    try:\n        pr.resolve_profile(n)\n    except ValueError:\n        raise SystemExit(0)\n",
        "class C:\n    def f(self):\n        try:\n            pr.resolve_profile(n)\n        except ValueError:\n            return None\n",
    ]
    for src in swallowed:
        assert swallow_findings(src), src
    loud = [
        "def f():\n    try:\n        pr.resolve_profile(n)\n    except ValueError:\n        raise\n",
        "def f():\n    try:\n        pr.resolve_profile(n)\n    except ValueError as e:\n        sys.exit(getattr(e, 'exit_code', 1))\n",
        "def f():\n    try:\n        pr.resolve_profile(n)\n    except ValueError as e:\n        return _fail(e)\n",
        "def f():\n    try:\n        pr.resolve_profile(n)\n    except ValueError as e:\n        return 3\n",
        "def f():\n    try:\n        pr.resolve_profile(n)\n    except ValueError as e:\n        if e.kind == 'not_found':\n            return None\n        raise\n",
        "def f():\n    try:\n        json.loads(s)\n    except ValueError:\n        return None\n",  # not a resolver call
    ]
    for src in loud:
        assert not swallow_findings(src), src
