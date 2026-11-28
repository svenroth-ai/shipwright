"""Guard: a frozen name of a MOVING file is never joined to a root (campaign root-files-into-config, R1c-2).

R1b routed every direct ``root / _sp.rel(key)`` join through ``_sp.path(key, root)``. A module constant
``NAME = _sp.rel(key)`` joined later as ``root / NAME`` escaped that rule (BRIEF 12.10b): it would keep
reading the root after R3 moves the file. R1c-2 rewrote those joins; this test keeps them out. It sees a
join in the defining module, in every module that imports the name (``from m import NAME``), and through a
module alias (``root / _bb.NAME``); joins by ``/``, ``/=``, ``os.path.join``, ``Path(a, b)`` and
``joinpath``; and a parameter default bound to such a name. Files that stay at the root (the event log)
are not checked: their joins are correct forever.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))  # for _shipwright_paths_scan

import _shipwright_paths_scan as scan  # noqa: E402

sp = scan.sp


def _moving_binding(value: ast.expr) -> str | None:
    """The key when *value* is ``<sp>.rel/legacy_rel/name("<key>")`` of a key that moves, also behind a
    stale-cache fallback (``"lit" if _sp is None else ...``) or a ``Path(...)`` / ``str(...)`` wrapper."""
    if isinstance(value, ast.IfExp):
        return _moving_binding(value.orelse)
    if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in ("Path", "str")
            and len(value.args) == 1):
        return _moving_binding(value.args[0])
    if (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
            and value.func.attr in ("rel", "legacy_rel", "name") and value.args
            and isinstance(value.args[0], ast.Constant)):
        key = value.args[0].value
        if key in sp.SPECS and sp.new_rel(key):
            return key
    return None


def _module_level(tree: ast.Module):
    """Statements of module-level code, also inside a module-level ``if`` / ``try`` / ``with``."""
    stack = list(tree.body)
    while stack:
        s = stack.pop()
        yield s
        if isinstance(s, (ast.If, ast.Try, ast.With)):
            stack += [*s.body, *getattr(s, "orelse", []), *getattr(s, "finalbody", []),
                      *(x for h in getattr(s, "handlers", []) for x in h.body)]


def _bindings(tree: ast.Module) -> dict[str, str]:
    out = {}
    for s in _module_level(tree):
        if isinstance(s, (ast.Assign, ast.AnnAssign)) and s.value is not None:
            key = _moving_binding(s.value)
            targets = s.targets if isinstance(s, ast.Assign) else [s.target]
            out.update({t.id: key for t in targets if key and isinstance(t, ast.Name)})
    return out


def _joined(n: ast.AST) -> list[ast.expr]:
    """What *n* joins onto a path: ``a / b``, ``a /= b``, ``os.path.join(a, b)``, ``Path(a, b)``, ``a.joinpath(b)``."""
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div):
        return [n.right]
    if isinstance(n, ast.AugAssign) and isinstance(n.op, ast.Div):
        return [n.value]
    if isinstance(n, ast.Call):
        f = n.func
        if isinstance(f, ast.Attribute) and f.attr == "joinpath":
            return list(n.args)
        if (isinstance(f, ast.Attribute) and f.attr == "join" and isinstance(f.value, ast.Attribute)
                and f.value.attr == "path"):
            return list(n.args[1:])
        if isinstance(f, ast.Name) and f.id == "Path" and len(n.args) > 1:
            return list(n.args[1:])
    return []


def _aliases(tree: ast.Module) -> dict[str, str]:
    """Local module alias -> module stem (``import lib.x as y`` / ``from lib import x as y``)."""
    out = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out.update({(a.asname or a.name.split(".")[0]): a.name.rsplit(".", 1)[-1] for a in n.names})
        elif isinstance(n, ast.ImportFrom):
            out.update({(a.asname or a.name): a.name for a in n.names})
    return out


def joins(files: list[str]) -> list[str]:
    trees = {f: ast.parse((scan.REPO / f).read_text(encoding="utf-8")) for f in files}
    defined = {f: _bindings(t) for f, t in trees.items()}
    by_stem: dict[str, dict[str, str]] = {}
    for f, names in defined.items():
        by_stem.setdefault(Path(f).stem, {}).update(names)
    out = []
    for f, tree in trees.items():
        names, mods = dict(defined[f]), _aliases(tree)
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module:
                src = by_stem.get(n.module.rsplit(".", 1)[-1], {})
                names.update({(a.asname or a.name): src[a.name] for a in n.names if a.name in src})

        def key_of(x: ast.expr) -> tuple[str, str] | None:
            if isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id in ("Path", "str") and len(x.args) == 1:
                return key_of(x.args[0])   # a wrapper at the use site: root / Path(NAME)
            if isinstance(x, ast.JoinedStr) and len(x.values) == 1 and isinstance(x.values[0], ast.FormattedValue):
                return key_of(x.values[0].value)   # root.joinpath(f"{NAME}")
            if isinstance(x, ast.Name) and x.id in names:
                return x.id, names[x.id]
            if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name):
                key = by_stem.get(mods.get(x.value.id, ""), {}).get(x.attr)
                return (f"{x.value.id}.{x.attr}", key) if key else None
            return None

        for n in ast.walk(tree):
            for x in _joined(n):
                hit = key_of(x)
                if hit:
                    out.append(f"{f}:{n.lineno}: root / {hit[0]} -> _sp.path({hit[1]!r}, root)")
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                params = [*n.args.posonlyargs, *n.args.args]
                pairs = list(zip(params[len(params) - len(n.args.defaults):], n.args.defaults))
                pairs += [(a, d) for a, d in zip(n.args.kwonlyargs, n.args.kw_defaults) if d is not None]
                used = {x.id for s in ast.walk(n) for x in _joined(s) if isinstance(x, ast.Name)}
                for arg, d in pairs:
                    hit = key_of(d)
                    if hit and arg.arg in used:   # a default that is only a message label is fine
                        out.append(f"{f}:{n.lineno}: default {hit[0]} -> take a registry key, resolve with _sp.path()")
    return [x for x in out if x.split(":", 1)[0] not in ALLOWED]


#: A file of the same NAME that is not the root file. Reason per entry.
ALLOWED = {
    # the session config inside a PLANNING dir (``planning_dir / name``), not the root plan config
    "plugins/shipwright-plan/scripts/lib/config.py",
}


@pytest.mark.covers("FR-01.11")
def test_no_root_join_of_a_frozen_moving_name():
    found = joins(scan.production_py())
    assert not found, "join through the resolver so the file is found in either layout:\n" + "\n".join(found)


@pytest.mark.covers("FR-01.11")
def test_the_guard_sees_a_join_here_and_in_an_importer(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text('NAME = _sp.rel("run_config")\nEV = _sp.rel("events")\n'
                                   'def f(r):\n    return r / NAME, r / EV\n', encoding="utf-8")
    (tmp_path / "b.py").write_text('from pkg.a import NAME as N\ndef g(r):\n    return r / N\n', encoding="utf-8")
    monkeypatch.setattr(scan, "REPO", tmp_path)
    found = joins(["a.py", "b.py"])
    assert found == ["a.py:4: root / NAME -> _sp.path('run_config', root)",
                     "b.py:3: root / N -> _sp.path('run_config', root)"], found


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("src", [
    'NAME = "shipwright_run_config.json" if _sp is None else _sp.rel("run_config")\ndef f(r):\n    return r / NAME\n',
    'NAME = Path(_sp.name("run_config"))\ndef f(r):\n    return os.path.join(r, NAME)\n',
    'try:\n    NAME = _sp.rel("run_config")\nexcept ImportError:\n    pass\ndef f(r):\n    return Path(r, NAME)\n',
    'NAME = _sp.rel("run_config")\ndef f(r):\n    r /= NAME\n    return r\n',
    'NAME = _sp.rel("run_config")\ndef f(r):\n    return r.joinpath(NAME)\n',
    'NAME = str(_sp.rel("run_config"))\ndef f(r):\n    return r / NAME\n',
    'if True:\n    NAME = _sp.rel("run_config")\ndef f(r):\n    return r / NAME\n',
    'NAME = _sp.legacy_rel("run_config")\ndef f(r):\n    return r / NAME\n',
    'NAME = _sp.rel("run_config")\ndef f(r):\n    return r / Path(NAME)\n',
    'NAME = _sp.rel("run_config")\ndef f(r):\n    return r.joinpath(f"{NAME}")\n',
    'NAME = _sp.rel("run_config")\ndef f(r, filename=NAME):\n    return os.path.join(r, filename)\n',
])
def test_the_guard_sees_every_join_shape(tmp_path, monkeypatch, src):
    (tmp_path / "a.py").write_text(src, encoding="utf-8")
    monkeypatch.setattr(scan, "REPO", tmp_path)
    assert len(joins(["a.py"])) == 1, src


@pytest.mark.covers("FR-01.11")
def test_the_guard_sees_a_module_attribute(tmp_path, monkeypatch):
    (tmp_path / "bb.py").write_text('BASELINE_FILENAME = _sp.rel("bloat_baseline")\n', encoding="utf-8")
    (tmp_path / "c.py").write_text('from lib import bb as _bb\ndef f(r):\n    return r / _bb.BASELINE_FILENAME\n',
                                   encoding="utf-8")
    monkeypatch.setattr(scan, "REPO", tmp_path)
    assert joins(["bb.py", "c.py"]) == ["c.py:3: root / _bb.BASELINE_FILENAME -> _sp.path('bloat_baseline', root)"]


@pytest.mark.covers("FR-01.11")
def test_a_default_used_only_as_a_label_is_not_a_join(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text('NAME = _sp.rel("run_config")\ndef f(r, origin=NAME):\n    return r / "x", origin\n',
                                   encoding="utf-8")
    monkeypatch.setattr(scan, "REPO", tmp_path)
    assert joins(["a.py"]) == []
