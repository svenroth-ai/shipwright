"""BP unit BL0b - HEAD-run mapping by qualified name, new-code classes, path baseline, blind probes, label packs (real git)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _baseline_repo import SPEC, SPEC_TEXT, commit, make_repo  # noqa: E402
from verifiers import _baseline_b_packs as packs  # noqa: E402
from verifiers import _baseline_b_paths as paths  # noqa: E402
from verifiers import _baseline_b_probes as probes  # noqa: E402
from verifiers._baseline_b_headmap import HeadMapper, new_code_class  # noqa: E402
from verifiers._baseline_head_run import prefix_of  # noqa: E402
from verifiers._baseline_touch_git import GitRev  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")

PROD = "def price(x):\n    a = 1\n    b = 2\n    c = 3\n    d = 4\n    e = x == 1\n    return e\n\n\ndef other(x):\n    return x\n"
TESTS = 'import pytest\n\n\n@pytest.mark.covers("FR-01.09/AC02")\ndef test_price():\n    assert True\n\n\ndef test_other():\n    assert True\n'
BASE = {SPEC: SPEC_TEXT, "shared/scripts/prod.py": PROD, "shared/scripts/tests/test_prod.py": TESTS}
BOUND = "shared/scripts/tests/test_prod.py::test_price"
UNBOUND = "shared/scripts/tests/test_prod.py::test_other"


def _history(tmp_path: Path, pr_change: dict):
    root = make_repo(tmp_path, BASE)
    base = commit(root, {"README.md": "x"}, "noise")
    pr = commit(root, pr_change, "pr")
    commit(root, {"shared/scripts/prod.py": "# a header\n# another\n" + pr_change.get("shared/scripts/prod.py", PROD)}, "later: lines shift")
    return root, GitRev(root, base, pr)


def test_function_is_found_by_name_after_the_lines_shifted(tmp_path):
    root, rev = _history(tmp_path, {"shared/scripts/prod.py": PROD.replace("x == 1", "x == 2")})
    shifted = {n + 2: {BOUND} for n in range(1, 8)}  # at HEAD `price` sits two lines lower
    mapped = HeadMapper(root, {"shared/scripts/prod.py": shifted}).map_pr(rev, rev.changed())
    assert mapped["touched"] == {"FR-01.09": ["shared/scripts/prod.py::price"]}
    assert mapped["tokens"]["shared/scripts/prod.py::price"] == ["FR-01.09/AC02"]


def test_unbound_unexecuted_and_unmeasured_are_told_apart(tmp_path):
    root, rev = _history(tmp_path, {"shared/scripts/prod.py": PROD.replace("x == 1", "x == 2").replace("return x", "return x + 1")})
    unbound = {n + 2: {UNBOUND} for n in range(10, 14)}
    kinds = {n["key"]: n["kind"] for n in HeadMapper(root, {"shared/scripts/prod.py": unbound}).map_pr(rev, rev.changed())["notes"]}
    assert kinds["shared/scripts/prod.py::price"] == "no_test" and kinds["shared/scripts/prod.py::other"] == "only_unbound_tests"
    assert {n["kind"] for n in HeadMapper(root, {}).map_pr(rev, rev.changed())["notes"]} == {"no_coverage"}


def test_new_function_called_by_a_modified_base_function_is_class_a_else_b(tmp_path):
    called = PROD.replace("e = x == 1", "e = helper(x)") + "\n\ndef helper(x):\n    return x\n"
    root, rev = _history(tmp_path / "a", {"shared/scripts/prod.py": called})
    result = new_code_class(rev, HeadMapper(root, {}).map_pr(rev, rev.changed()))
    assert result["class"] == "a" and "helper" in result["reached_via"]
    extra = {"shared/scripts/prod.py": PROD + "\n\ndef lonely(x):\n    return x\n", "shared/scripts/new_mod.py": "def z():\n    return 1\n"}
    root2, rev2 = _history(tmp_path / "b", extra)
    assert new_code_class(rev2, HeadMapper(root2, {}).map_pr(rev2, rev2.changed()))["class"] == "b"


def test_path_baseline_maps_plugins_and_importing_plugins(tmp_path):
    spec = "| FR-01.09 | Adopted | /shipwright-changelog | Must | x | code | unit |\n| FR-01.10 | Adopted | /shipwright-compliance | Must | y | code | unit |\n"
    owners = paths.plugin_owners(spec)
    assert owners == {"shipwright-changelog": "FR-01.09", "shipwright-compliance": "FR-01.10"}
    (tmp_path / "shared/scripts/lib").mkdir(parents=True)
    (tmp_path / "shared/scripts/lib/inner.py").write_text("X = 1\n")
    (tmp_path / "shared/scripts/lib/outer.py").write_text("from lib import inner\n")
    (tmp_path / "plugins/shipwright-compliance/scripts").mkdir(parents=True)
    (tmp_path / "plugins/shipwright-compliance/scripts/a.py").write_text("from lib.outer import y\n")
    reach = paths.import_owners(tmp_path, owners)
    assert reach["inner"] == {"FR-01.10"}  # transitively, through another shared module
    changed = [("M", p, p) for p in ("shared/scripts/lib/inner.py", "plugins/shipwright-changelog/scripts/z.py", "plugins/shipwright-changelog/tests/test_z.py")]
    assert sorted(paths.path_frs(changed, owners, reach)) == ["FR-01.09", "FR-01.10"]


def test_mutation_flips_a_comparison_and_classification_names_the_cause(tmp_path):
    (tmp_path / "shared/scripts").mkdir(parents=True)
    (tmp_path / "shared/scripts/m.py").write_text(PROD)
    found = probes.eligible_functions(tmp_path)
    assert [f["func"] for f in found] == ["price"]
    assert probes.mutate(tmp_path, found[0])
    assert "x != 1" in (tmp_path / "shared/scripts/m.py").read_text()
    assert probes.classify(found[0], {}, False, False, False, False) == "no_candidate_bound_test_references_module"
    assert probes.classify(found[0], {"t": True}, True, True, True, True) == "caught"
    assert probes.classify(found[0], {}, False, False, True, True) == "referenced_by_bound_test_but_not_executed_in_process"


def test_prefix_of_roots():
    assert prefix_of("plugins/shipwright-x/tests") == "plugins/shipwright-x/" and prefix_of("shared/tests") == ""


def test_pack_has_no_author_declaration_and_redacts_fr_ids_in_the_title(tmp_path):
    root = make_repo(tmp_path, {**BASE, ".shipwright/agent_docs/iterates/r.json": "{}"})
    base = commit(root, {"README.md": "x"}, "n")
    head = commit(root, {"shared/scripts/prod.py": PROD.replace("x == 1", "x == 2"), ".shipwright/agent_docs/iterates/r.json": '{"affected_frs": ["FR-01.09"]}'}, "pr")
    cat = packs.catalog(SPEC_TEXT)
    text = packs.build_pack(GitRev(root, base, head), "fix(x): per FR-01.09 AC04", 7, cat)
    assert "affected_frs" not in text and "Title: fix(x): per FR-xx" in text and "x == 2" in text
    assert cat[0]["id"] == "FR-01.09" and cat[0]["acs"][0][0] == "AC01"


def test_rule_evaluation_counts_only_pairs_both_labelers_confirm():
    from verifiers._baseline_b_eval import evaluate

    rec = lambda pr, src, decl: {"pr": pr, "sources": {fr: ["test"] for fr in src}, "declared": decl, "class": "iterate", "new_frs": []}  # noqa: E731
    replay = {"records": [rec(1, ["FR-01.09"], []), rec(2, ["FR-01.10"], []), rec(3, [], []), rec(4, ["FR-01.09"], [])]}
    held = {"hold_scope_eq_declared_fr_level": {"git+tcode_head": 25, "git": 2}, "hold_per_week_scope_eq_declared": {"git+tcode_head": 1.25}, "ac_level": {"hold_scope_eq_declared_ac_level": 5}}
    data = {"phaseA": {"headmap": {"per_pr": {}}, "paths": {"per_pr": {"3": {"FR-01.05": ["x"]}}}, "summary": held}}
    lab = lambda yn, frs: {"changed_behavior": yn, "affected_frs": frs, "affected_acs": []}  # noqa: E731
    la = {"1": lab("yes", ["FR-01.09"]), "2": lab("yes", []), "3": lab("yes", ["FR-01.05"]), "4": lab("no", [])}
    lb = {"1": lab("yes", ["FR-01.09"]), "2": lab("yes", ["FR-01.10"]), "3": lab("yes", ["FR-01.05"]), "4": lab("no", [])}
    out = evaluate(replay, data, la, lb)
    assert out["confirmed_pairs"] == [[1, "FR-01.09"], [3, "FR-01.05"]]
    assert [o["pr"] for o in out["labels"]["yes_pr_outside_every_fr"]] == [2]
    assert out["rules"]["R-recall"]["found"]["found"] == 1  # BP finds PR 1 only; PR 3 is the path baseline's
    assert out["hits_on_judged_prs"]["BP(git+tcode)"]["wrong"] == 1  # PR 4: a hit on a PR both judged "no"
    assert out["hits_on_judged_prs"]["BP(git+tcode)"]["disputed"] == 1  # PR 2: only labeler B names FR-01.10
    assert out["rules"]["R-cost"]["result"] == "FAIL"
