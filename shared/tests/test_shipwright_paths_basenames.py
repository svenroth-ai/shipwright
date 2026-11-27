"""File NAMES stay names when paths move (campaign root-files-into-config R1a, BRIEF 12.2).

``rel()`` (a repo-relative path) and ``name()`` (a bare file name) return the same string until R3,
so a consumer that compares ``Path.name`` with ``rel()`` is wrong today and only fails after the move.
Two checks make that visible now:

* runtime - each named basename consumer is loaded in a fresh interpreter with the WHOLE layout moved
  (``rel``, ``names_of``/``rels_of_kind``, ``snapshot_paths`` answer ``.shipwright/config/...``): its
  basename sets must not change, while a path table (``lib.config.CONFIG_FILES``) must follow;
* static - no production comparison of a basename expression with a path-returning resolver call.
  Limits: a path constant imported from ANOTHER module, and ``fnmatch`` patterns, are not traced.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "shared" / "scripts"
LIB = SCRIPTS / "lib"

_MOVED = f"""
import importlib.util, json, pathlib, sys, tempfile
sys.path[:0] = [{str(SCRIPTS.parent)!r}, {str(SCRIPTS)!r}, {str(LIB)!r}]
import shipwright_paths as sp
# every key gets a directory-bearing path, even one that never moves: rel() and name() must differ for all
_cur = lambda k: sp.new_rel(k) or ".shipwright/elsewhere/" + sp.legacy_rel(k)
sp.rel = _cur
sp.names_of = sp.rels_of_kind = lambda kinds=None, **kw: tuple(_cur(k) for k in sp.keys_of(kinds, **kw))
sp.snapshot_paths = lambda kind=sp.DERIVED: frozenset(sp.names_of((kind,)))
def by_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod)
    return mod
"""


def _moved(body: str) -> dict:
    out = subprocess.run([sys.executable, "-c", _MOVED + textwrap.dedent(body)], capture_output=True, timeout=60, cwd=str(REPO))
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")
    return json.loads(out.stdout.decode("utf-8", "replace").strip().splitlines()[-1])


@pytest.mark.covers("FR-01.11")
def test_basename_sets_survive_a_moved_layout_while_path_tables_follow():
    res = _moved(f"""
        from lib import ac_surface, config
        from scripts.tools import suite_worktree_diff as swd
        prg = by_file("prg_probe", {str(REPO / "plugins/shipwright-security/scripts/lib/pr_review_generated.py")!r})
        from tools.generate_session_handoff import generate_handoff
        with tempfile.TemporaryDirectory() as proj:
            text = generate_handoff(pathlib.Path(proj), session_id="s")
        handoff_run_line = next(x for x in text.splitlines() if "shipwright_run_config.json" in x)
        seed = by_file("seed_probe", {str(REPO / "plugins/shipwright-adopt/scripts/lib/event_seeder.py")!r})
        routed = []
        seed._drops_layout = lambda parent: True
        seed._append_drop = lambda parent, event: routed.append(event["type"])
        with tempfile.TemporaryDirectory() as tmp:
            seed._append_jsonl(pathlib.Path(tmp) / "shipwright_events.jsonl", {{"type": "probe"}})
        print(json.dumps({{
            "ledgers": sorted(ac_surface._LEDGERS),
            "measurement": "shipwright_test_config.json" in swd._MEASUREMENT_CONFIG_NAMES,
            "generated": sorted(prg._GENERATED_BASENAMES),
            "seeder_routed_by_name": routed,
            "run_path": config.CONFIG_FILES["run"],
            "handoff_line": handoff_run_line,
            "moved": sp.rel("run_config")}}))
    """)
    assert res["moved"] == ".shipwright/config/shipwright_run_config.json"     # the layout really moved
    assert res["run_path"] == res["moved"]                                     # a path table follows
    assert res["handoff_line"] == f"- `{res['moved']}` — missing"                # ...and the handoff list with it
    assert {"shipwright_events.jsonl", "shipwright_test_results.json",
            "shipwright_bloat_baseline.json"} <= set(res["ledgers"])
    assert all("/" not in n for n in res["ledgers"] + res["generated"])
    assert res["measurement"] is True
    assert {"shipwright_test_results.json", "shipwright_events.jsonl"} <= set(res["generated"])
    assert res["seeder_routed_by_name"] == ["probe"]   # matched the bare file name, not rel()


_PATH_FNS = {"rel", "names_of", "rels_of_kind", "snapshot_paths", "rel_at", "legacy_rel", "new_rel",
             "known_rels", "all_known_rels"}


def _is_path_call(n: ast.AST) -> bool:
    return (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in _PATH_FNS
            and isinstance(n.func.value, ast.Name) and n.func.value.id in ("_sp", "sp", "shipwright_paths"))


def _is_basename(n: ast.AST) -> bool:
    if isinstance(n, ast.Attribute) and n.attr == "name":
        return True
    if isinstance(n, ast.Call):
        f = n.func
        return (isinstance(f, ast.Name) and f.id == "basename_of") or (
            isinstance(f, ast.Attribute) and f.attr in ("basename", "basename_of"))
    return isinstance(n, ast.Subscript) and isinstance(n.value, ast.Attribute) and n.value.attr == "parts"


def misuses(source: str) -> list[int]:
    """Line numbers where a basename is compared with (or ``endswith``-matched against) a path."""
    tree = ast.parse(source)
    consts = {t.id for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None
              and any(_is_path_call(x) for x in ast.walk(node.value))
              for t in (node.targets if isinstance(node, ast.Assign) else [node.target]) if isinstance(t, ast.Name)}

    def pathy(n: ast.AST) -> bool:
        return not _is_basename(n) and any(_is_path_call(x) or (isinstance(x, ast.Name) and x.id in consts)
                                           for x in ast.walk(n))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            sides = [node.left, *node.comparators]
            if any(_is_basename(s) for s in sides) and any(pathy(s) for s in sides):
                hits.append(node.lineno)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "endswith"
              and _is_basename(node.func.value) and any(pathy(a) for a in node.args)):
            hits.append(node.lineno)
    return hits


def _production_files():
    for root in (SCRIPTS, *sorted((REPO / "plugins").glob("*/scripts"))):
        for f in sorted(root.rglob("*.py")):
            if "tests" not in f.relative_to(REPO).parts and f.name != "shipwright_paths.py":
                yield f


@pytest.mark.covers("FR-01.11")
def test_the_rule_catches_each_misuse_shape():
    src = textwrap.dedent("""
        CONFIG_NAME = _sp.rel("run_config")
        SNAP = _sp.snapshot_paths()
        a = p.name == CONFIG_NAME
        b = p.name in {CONFIG_NAME, "x"}
        c = basename_of(q) == _sp.rel("events")
        d = p.name.endswith(_sp.rel("events"))
        e = p.parts[-1] in SNAP
        ok1 = p.name == _sp.name("events")
        ok2 = p == root / CONFIG_NAME
    """)
    assert misuses(src) == [4, 5, 6, 7, 8]


@pytest.mark.covers("FR-01.11")
def test_no_production_code_compares_a_basename_with_a_path():
    hits = [f"{f.relative_to(REPO).as_posix()}:{ln}" for f in _production_files()
            for ln in misuses(f.read_text(encoding="utf-8"))]
    assert hits == [], "compare basenames with _sp.name()/all_basenames(), not a path: " + ", ".join(hits)
