"""Hook fallbacks for a missing resolver stay equal to it (campaign root-files-into-config R1a, BRIEF 12.7b).

Hooks run from the plugin cache; after a plugin update the shared cache can lag, the resolver import
fails, and a hook falls back to its own literal names. Those literals must name the same files.
They are compared with ``legacy_rel`` (identical to ``rel`` today): when R1c changes ``rel()`` it also
decides what a fallback should name after the move (12.7a) - this test must then change on purpose,
not drift.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "shared" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lib import shipwright_paths as sp  # noqa: E402

_NAME = re.compile(r"(?:shipwright_[A-Za-z0-9_]+\.(?:json|jsonl|yaml)(?:\.lock)?|audit_config\.json)")


def _production_files():
    roots = [SCRIPTS, *sorted((REPO / "plugins").glob("*/scripts"))]
    for root in roots:
        for f in sorted(root.rglob("*.py")):
            if "tests" not in f.relative_to(REPO).parts and f.name != "shipwright_paths.py":
                yield f


def _is_sp_none(test: ast.expr) -> bool:
    return (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "_sp"
            and isinstance(test.ops[0], ast.Is) and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value is None)


def _catches_import_error(h: ast.ExceptHandler) -> bool:
    types = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
    return any(isinstance(t, ast.Name) and t.id in ("ImportError", "ModuleNotFoundError") for t in types)


def _is_sp_call(call: ast.expr) -> bool:
    return (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name) and call.func.value.id == "_sp")


def _unwrap_path(x: ast.expr) -> ast.expr:
    """``Path(root)`` -> ``root``: the fallback may wrap the root it joins, ``path()`` takes it bare."""
    if isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id == "Path" and len(x.args) == 1:
        return x.args[0]
    return x


def _join_shape(lit: ast.expr, call: ast.expr):
    """R1c-2 shape ``root / "<literal>" if _sp is None else _sp.path("<key>", root)`` (same root on both
    sides): ``(literal, "path", key)``, else ``None``."""
    if not (isinstance(lit, ast.BinOp) and isinstance(lit.op, ast.Div) and isinstance(lit.right, ast.Constant)
            and _is_sp_call(call) and call.func.attr == "path" and len(call.args) == 2
            and isinstance(call.args[0], ast.Constant)):
        return None
    if ast.dump(_unwrap_path(lit.left)) != ast.dump(_unwrap_path(call.args[1])):
        return None
    return lit.right.value, "path", call.args[0].value


def _scan():
    pairs, loose, odd = [], [], []
    for f in _production_files():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        rel = f.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and _is_sp_none(node.test):
                odd.append(f"{rel}:{node.lineno}")   # a statement-form fallback cannot be paired
            elif isinstance(node, ast.IfExp) and _is_sp_none(node.test):
                lit, call = node.body, node.orelse
                join = _join_shape(lit, call)
                if join:
                    pairs.append((f"{rel}:{node.lineno}", *join))
                elif (isinstance(lit, ast.Constant) and _is_sp_call(call) and call.args
                        and isinstance(call.args[0], ast.Constant)):
                    pairs.append((f"{rel}:{node.lineno}", lit.value, call.func.attr, call.args[0].value))
                else:
                    odd.append(f"{rel}:{node.lineno}")
            elif isinstance(node, ast.ExceptHandler) and _catches_import_error(node):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and _NAME.fullmatch(sub.value):
                        loose.append((f"{rel}:{sub.lineno}", sub.value))
    return pairs, loose, odd


PAIRS, LOOSE, ODD = _scan()


@pytest.mark.covers("FR-01.11")
def test_every_resolver_fallback_has_the_one_checkable_shape():
    """``"<literal>" if _sp is None else _sp.rel("<key>")`` or, for a join (R1c-2), ``root / "<literal>" if _sp
    is None else _sp.path("<key>", root)``: the only shapes this file can verify."""
    assert ODD == [], f"rewrite these fallbacks in the checkable shape: {ODD}"


@pytest.mark.covers("FR-01.11")
def test_the_scan_sees_the_known_fallbacks():
    files = {p[0].rsplit(":", 1)[0] for p in PAIRS} | {x[0].rsplit(":", 1)[0] for x in LOOSE}
    assert len(PAIRS) >= 10, PAIRS  # 11 `"<lit>" if _sp is None else _sp.rel(...)` sites at R1a, 10 since R1c-1 (check_file_size)
    for must in ("shared/scripts/hooks/suggest_iterate.py", "shared/scripts/hooks/session_start_using_shipwright.py",
                 "plugins/shipwright-run/scripts/hooks/master_stop_check.py",
                 "shared/scripts/hooks/track_tool_calls.py", "shared/scripts/hooks/check_required_checks_hook.py"):
        assert must in files, must


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("site, literal, fn, key", PAIRS, ids=[p[0] for p in PAIRS])
def test_each_paired_fallback_names_the_resolver_file(site, literal, fn, key):
    assert fn in ("rel", "name", "path"), site
    # the stale-cache fallback names the LEGACY root file (R1c-2): an old cache predates every move
    assert literal == sp.legacy_rel(key) == sp.rel(key), f"{site}: fallback {literal!r} != resolver {sp.rel(key)!r}"


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("site, literal", LOOSE, ids=[x[0] for x in LOOSE])
def test_each_literal_in_an_import_error_handler_is_a_registry_file(site, literal):
    assert literal in sp.all_basenames() or literal in {sp.lock_rel(k) for k in sp.SPECS}, site


_HOOKS = SCRIPTS / "hooks"
_HIDDEN = """
import importlib.util, json, sys, tempfile, pathlib
sys.modules["shipwright_paths"] = None          # the stale-cache case: the resolver import fails
def load(path):
    sys.path.insert(0, str(pathlib.Path(path).parent))   # a hook runs as a script: its own dir comes first
    spec = importlib.util.spec_from_file_location("hook_under_test", path)
    mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
    return mod
"""


def _hidden(body: str) -> dict:
    out = subprocess.run([sys.executable, "-c", _HIDDEN + textwrap.dedent(body)], capture_output=True, timeout=60, cwd=str(REPO))
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")
    return json.loads(out.stdout.decode("utf-8", "replace").strip().splitlines()[-1])


@pytest.mark.covers("FR-01.11")
def test_resolver_hidden_branch_session_start_finds_the_project_by_the_literal(tmp_path):
    """R1c-2: the hook names the root config inline (no frozen constant); hidden resolver, legacy layout."""
    (tmp_path / sp.legacy_rel("run_config")).write_text("{}", encoding="utf-8")
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "using-shipwright.md").write_text("hello", encoding="utf-8")
    res = _hidden(f"""
        a = load({str(_HOOKS / "session_start_using_shipwright.py")!r})
        root = pathlib.Path({str(tmp_path)!r})
        out = a.run(project_root=root, session_id="s-hidden", prompts_dir=root / "p")
        print(json.dumps({{"sp": a._sp is None, "speaks": bool(out)}}))
    """)
    assert res == {"sp": True, "speaks": True}


@pytest.mark.covers("FR-01.11")
def test_resolver_hidden_branch_reads_the_fallback_file(tmp_path):
    """The deferred fallback is USED, not only importable: the hook reads its config by the literal."""
    (tmp_path / sp.legacy_rel("run_config")).write_text(
        json.dumps({"triage": {"required_checks_throttle_hours": 7.5}}), encoding="utf-8")
    res = _hidden(f"""
        rcs = load({str(_HOOKS / "required_checks_state.py")!r})
        print(json.dumps({{"sp": rcs._sp is None, "throttle": rcs.throttle_hours(pathlib.Path({str(tmp_path)!r}))}}))
    """)
    assert res == {"sp": True, "throttle": 7.5}


# check_file_size has NO resolver fallback since R1c-1 (BRIEF 12.8): it needs lib.bloat_baseline, which
# stays strict because the pre-commit anti-ratchet and the CI gate read the baseline through it.


@pytest.mark.covers("FR-01.11")
def test_resolver_hidden_branch_suggest_iterate_imports():
    res = _hidden(f"""
        m = load({str(_HOOKS / "suggest_iterate.py")!r})
        print(json.dumps({{"sp": m._sp is None}}))
    """)
    assert res == {"sp": True}


# Hooks with an `_sp` fallback (PAIRS): must take it. Hooks whose literals sit in an ImportError handler for
# ANOTHER import (LOOSE only, e.g. track_tool_calls): import-only check; their literals are checked statically.
_SP_HOOKS = sorted({s.rsplit(":", 1)[0] for s, *_ in PAIRS if "/hooks/" in s})
_HOOK_FILES = [f for f in sorted({s.rsplit(":", 1)[0] for s, _ in LOOSE if "/hooks/" in s} | set(_SP_HOOKS))]


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("hook", _HOOK_FILES)
def test_every_hook_with_a_fallback_imports_with_the_resolver_hidden(hook):
    res = _hidden(f"""
        m = load({str(REPO / hook)!r})
        print(json.dumps({{"sp": getattr(m, "_sp", "absent")}}, default=str))
    """)
    assert res["sp"] is None if hook in _SP_HOOKS else res["sp"] == "absent", res
