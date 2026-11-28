"""One resolver module object, whatever name loads it (campaign root-files-into-config R1a, BRIEF 12.3).

Each scenario runs in a fresh interpreter: module identity depends on ``sys.modules`` history, which
a shared pytest process cannot reset honestly.
"""

from __future__ import annotations

import itertools
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SHARED = Path(__file__).resolve().parents[1]
SCRIPTS = SHARED / "scripts"
LIB = SCRIPTS / "lib"

_PRELUDE = f"""
import importlib, importlib.util, json, sys
SCRIPTS, LIB = {str(SCRIPTS)!r}, {str(LIB)!r}
sys.path[:0] = [SCRIPTS, LIB]

def load(form):
    if form == "bare":
        import shipwright_paths as m
    elif form == "lib":
        import lib.shipwright_paths
        m = lib.shipwright_paths
    elif form == "from_lib":
        from lib import shipwright_paths as m
    elif form == "review":  # review_record_tier.py's private package
        if "_shipwright_shared_review_lib" not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                "_shipwright_shared_review_lib", LIB + "/__init__.py", submodule_search_locations=[LIB])
            pkg = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = pkg
            spec.loader.exec_module(pkg)
        from _shipwright_shared_review_lib import shipwright_paths as m
    elif form == "private":  # shared_lib_loader's fallback package, reached through a relative import
        import shared_lib_loader
        m = shared_lib_loader.load_shared_lib("events_layout_ci", prefer_private=True)._sp
    return m
"""


def _run(body: str) -> dict:
    code = _PRELUDE + textwrap.dedent(body)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=60)
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")
    return json.loads(out.stdout.decode("utf-8", "replace").strip().splitlines()[-1])


FORMS = ("bare", "lib", "from_lib", "review", "private")


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("order", list(itertools.permutations(FORMS, 2)) + [FORMS, FORMS[::-1]],
                         ids=lambda o: ">".join(o))
def test_every_import_name_yields_one_object_in_any_order(order):
    res = _run(f"""
        mods = [load(f) for f in {list(order)!r}]
        names = [n for n in sys.modules if n == "shipwright_paths" or n.endswith(".shipwright_paths")]
        parents = []
        for n in names:
            if "." in n:
                pkg, _, child = n.rpartition(".")
                if pkg in sys.modules and hasattr(sys.modules[pkg], child):
                    parents.append(getattr(sys.modules[pkg], child))
        objs = mods + [sys.modules[n] for n in names] + parents
        print(json.dumps({{"ids": len({{id(o) for o in objs}}), "rels": sorted({{m.rel("run_config") for m in mods}}),
                          "names": names}}))
    """)
    assert res["ids"] == 1, res
    assert res["rels"] == ["shipwright_run_config.json"]


@pytest.mark.covers("FR-01.11")
def test_a_bare_reload_after_the_bare_entry_was_dropped_rejoins_the_loaded_alias():
    """``lib.`` loaded first (bare -> that object), the bare entry removed by hand, then ``import shipwright_paths``."""
    res = _run("""
        lib_obj = load("lib")
        del sys.modules["shipwright_paths"]
        bare = load("bare")
        print(json.dumps({"same": bare is lib_obj, "bare_entry": sys.modules["shipwright_paths"] is lib_obj}))
    """)
    assert res == {"same": True, "bare_entry": True}


@pytest.mark.covers("FR-01.11")
def test_every_private_package_over_the_shared_lib_is_an_alias():
    """A package built over ``shared/scripts/lib`` (``_shipwright_*_lib``) that is not in ``_ALIASES`` would get
    its own resolver copy the moment one of its modules imports the resolver relatively."""
    import re
    names = set()
    for root in (SCRIPTS, *sorted((SHARED.parent / "plugins").glob("*/scripts"))):
        for f in root.rglob("*.py"):
            if "tests" not in f.parts:
                names |= set(re.findall(r"[\"'](_shipwright_[a-z_]+_lib)[\"']", f.read_text(encoding="utf-8")))
    res = _run("""
        print(json.dumps({"aliases": list(load("lib")._ALIASES)}))
    """)
    assert names >= {"_shipwright_shared_lib", "_shipwright_shared_review_lib", "_shipwright_brief_dir_lib"}
    assert {f"{n}.shipwright_paths" for n in names} <= set(res["aliases"])


@pytest.mark.covers("FR-01.11")
def test_a_probe_name_stays_a_separate_object():
    res = _run("""
        canon = load("bare")
        spec = importlib.util.spec_from_file_location("shipwright_paths_probe", LIB + "/shipwright_paths.py")
        probe = importlib.util.module_from_spec(spec); sys.modules[spec.name] = probe; spec.loader.exec_module(probe)
        print(json.dumps({"same": probe is canon, "bare_is_canon": sys.modules["shipwright_paths"] is canon}))
    """)
    assert res == {"same": False, "bare_is_canon": True}


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("first", ["probe", "canon"])
def test_a_dotted_probe_name_stays_separate_in_either_order(first, tmp_path):
    """Only the repo's own alias names unify; ``probe.shipwright_paths`` - the SAME file, reached through a
    package whose ``__path__`` is the shared lib dir - does not."""
    pkg = tmp_path / "probe"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(f"__path__ = [{str(LIB)!r}]\n", encoding="utf-8")
    res = _run(f"""
        sys.path.insert(0, {str(tmp_path)!r})
        got = {{}}
        for o in (["probe", "canon"] if {first!r} == "probe" else ["canon", "probe"]):
            if o == "probe":
                import probe.shipwright_paths
                got[o] = probe.shipwright_paths
            else:
                got[o] = load("lib")
        print(json.dumps({{"same": got["probe"] is got["canon"],
                          "probe_entry": sys.modules["probe.shipwright_paths"] is got["probe"]}}))
    """)
    assert res == {"same": False, "probe_entry": True}


@pytest.mark.covers("FR-01.11")
def test_a_hidden_bare_name_is_left_hidden():
    """A test hiding the resolver (``sys.modules[name] = None``) must keep it hidden: the hook
    fallback tests would otherwise pass for the wrong reason."""
    res = _run("""
        sys.modules["shipwright_paths"] = None
        m = load("lib")
        try:
            import shipwright_paths  # noqa: F401
            hidden = False
        except ImportError:
            hidden = True
        print(json.dumps({"hidden": hidden, "lib_loaded": m.rel("events") == "shipwright_events.jsonl"}))
    """)
    assert res == {"hidden": True, "lib_loaded": True}


@pytest.mark.covers("FR-01.11")
def test_a_fake_bare_module_without_a_registry_is_not_adopted():
    res = _run("""
        import types
        fake = types.ModuleType("shipwright_paths"); sys.modules["shipwright_paths"] = fake
        m = load("lib")
        print(json.dumps({"adopted": m is fake, "fake_kept": sys.modules["shipwright_paths"] is fake}))
    """)
    assert res == {"adopted": False, "fake_kept": True}


@pytest.mark.covers("FR-01.11")
def test_a_resolver_from_another_tree_is_not_adopted(tmp_path):
    """Plugin cache version A next to a dev tree B: a ``lib.`` import must not get A's registry."""
    other = tmp_path / "other"
    other.mkdir()
    for n in ("shipwright_paths.py", "shipwright_layout.py", "shipwright_pointer.py"):  # the resolver + its siblings
        (other / n).write_text((LIB / n).read_text(encoding="utf-8"), encoding="utf-8")
    res = _run(f"""
        sys.path.remove(LIB); sys.path.insert(0, {str(other)!r})
        import shipwright_paths as foreign
        m = load("lib")
        print(json.dumps({{"adopted": m is foreign, "foreign_bare": sys.modules["shipwright_paths"] is foreign}}))
    """)
    assert res == {"adopted": False, "foreign_bare": True}


@pytest.mark.covers("FR-01.11")
def test_importlib_hands_back_whatever_a_module_left_in_sys_modules(tmp_path):
    """The mechanism _unify relies on (pinned so a future interpreter fails HERE, not in a symptom):
    after exec, ``import pkg.mod`` and ``from pkg import mod`` return ``sys.modules["pkg.mod"]`` and
    bind it on the parent package."""
    pkg = tmp_path / "toypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "mod.py").write_text("import sys\nREPLACEMENT = object()\n"
                                "sys.modules[__name__] = sys.modules['canon_mod']\n", encoding="utf-8")
    res = _run(f"""
        import types
        canon = types.ModuleType("canon_mod"); sys.modules["canon_mod"] = canon
        sys.path.insert(0, {str(tmp_path)!r})
        import toypkg.mod
        a = toypkg.mod
        del sys.modules["toypkg.mod"]; delattr(sys.modules["toypkg"], "mod")
        from toypkg import mod as b
        print(json.dumps({{"import_form": a is canon, "from_form": b is canon,
                          "parent_attr": sys.modules["toypkg"].mod is canon}}))
    """)
    assert res == {"import_form": True, "from_form": True, "parent_attr": True}


@pytest.mark.covers("FR-01.11")
def test_known_locations():
    """In a fresh interpreter like the rest of this file (this pytest process has its own import history)."""
    res = _run("""
        sp = load("lib")
        stays = ("events", "audit_config", "dev_server", "audit_report", "plan_snapshot")
        every = sp.all_known_rels()
        print(json.dumps({
            "run": sp.new_rel("run_config"),
            "bloat": list(sp.known_rels("bloat_baseline")),
            "stays": all(sp.new_rel(k) is None and sp.known_rels(k) == (sp.legacy_rel(k),) for k in stays),
            "dev_target": sp.spec("dev_server").target,
            "every_is_concat": every == tuple(r for k in sp.keys_of() for r in sp.known_rels(k)),
            "every_count": len(every) == len(sp.names_of()) + len(sp.keys_of(moves=True)),
            "baseline_first": list(sp.all_known_rels(("baseline",))[:2]) == list(sp.known_rels("bloat_baseline")),
            "unchanged": all(sp.rel(k) == sp.legacy_rel(k) == sp.name(k) for k in sp.SPECS)}))
    """)
    assert res == {"run": ".shipwright/config/shipwright_run_config.json",
                   "bloat": [".shipwright/config/shipwright_bloat_baseline.json", "shipwright_bloat_baseline.json"],
                   "stays": True, "dev_target": ".shipwright/runtime", "every_is_concat": True,
                   "every_count": True, "baseline_first": True, "unchanged": True}
