"""BP unit BL0 - per-hit labels and the measurements behind the REPLAY numbers (real git, tmp repos)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools
sys.path.insert(0, str(Path(__file__).resolve().parent))

import measure_baseline  # noqa: E402
from _baseline_repo import SPEC, SPEC_TEXT, commit, make_repo  # noqa: E402
from verifiers import _baseline_label_hits as L  # noqa: E402
from verifiers import _baseline_measure as M  # noqa: E402
from verifiers._baseline_touch_git import GitRev  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")

TEST_A = '''import pytest


@pytest.mark.covers("FR-01.09/AC01")
def test_price():
    assert round(1.005, 2) == 1.0


@pytest.mark.covers("FR-01.10")
def test_other():
    assert 1 == 1
'''
HELPER = "import pytest\n\nVALUE = 1\n\n\ndef helper():\n    return VALUE\n"
USER = 'import pytest\nfrom pkg.tests.helper import helper\n\n\n@pytest.mark.covers("FR-01.09")\ndef test_uses():\n    assert helper() == 1\n'
FILES = {SPEC: SPEC_TEXT, "pkg/tests/test_a.py": TEST_A, "pkg/tests/helper.py": HELPER, "pkg/tests/test_u.py": USER}


def _rev(tmp_path, head_files):
    root = make_repo(tmp_path, FILES)
    base = commit(root, {"README.md": "x"}, "pad")
    head = commit(root, head_files, "change")
    return GitRev(root, base, head)


def test_changed_bound_test_is_a_correct_test_hit(tmp_path):
    rev = _rev(tmp_path, {"pkg/tests/test_a.py": TEST_A.replace("== 1.0", "== 1.01")})
    ok, why = L.label_test_hit(rev, "FR-01.09", ["pkg/tests/test_a.py::test_price"])
    assert ok and "changed" in why


def test_unchanged_or_wrongly_bound_test_is_wrong(tmp_path):
    rev = _rev(tmp_path, {"pkg/tests/test_a.py": TEST_A.replace("== 1", "== 2").replace("== 2.0", "== 1.0")})
    assert not L.label_test_hit(rev, "FR-01.09", ["pkg/tests/test_a.py::test_price"])[0]  # price untouched
    assert not L.label_test_hit(rev, "FR-01.10", ["pkg/tests/test_a.py::test_price"])[0]  # bound to another FR
    assert not L.label_test_hit(rev, "FR-01.09", ["pkg/tests/test_a.py::nope"])[0]
    assert not L.label_test_hit(rev, "FR-01.09", [])[0]


def test_deleted_bound_test_counts(tmp_path):
    rev = _rev(tmp_path, {"pkg/tests/test_a.py": TEST_A.split("@pytest.mark.covers(\"FR-01.10\")")[0]})
    assert L.label_test_hit(rev, "FR-01.10", ["pkg/tests/test_a.py::test_other"])[0]


def test_helper_change_reaches_a_bound_test_only_when_its_names_are_used(tmp_path):
    used = _rev(tmp_path / "a", {"pkg/tests/helper.py": HELPER.replace("VALUE = 1", "VALUE = 2")})
    item = "pkg/tests/helper.py (fixture/helper) -> pkg/tests/test_u.py"
    assert L.label_static_hit(used, "FR-01.09", [item])[0]
    other = _rev(tmp_path / "b", {"pkg/tests/helper.py": HELPER + "\n\ndef unrelated():\n    return 3\n"})
    ok, why = L.label_static_hit(other, "FR-01.09", [item])
    assert not ok and "not used" in why
    assert not L.label_static_hit(other, "FR-01.10", [item])[0]  # no test bound to that FR in the consumer


def test_added_import_alone_does_not_reach_existing_tests(tmp_path):
    item = "pkg/tests/test_u.py (fixture/helper) -> same module"
    rev = _rev(tmp_path / "a", {"pkg/tests/test_u.py": USER.replace("import pytest\n", "import os\nimport pytest\n", 1)})
    assert not L.label_static_hit(rev, "FR-01.09", [item])[0]
    swapped = _rev(tmp_path / "b", {"pkg/tests/test_u.py": USER.replace("import pytest\n", 'import pytest\n\npytest.skip("x", allow_module_level=True)\n', 1)})
    assert L.label_static_hit(swapped, "FR-01.09", [item])[0]


def test_autouse_conftest_and_deleted_helper_are_wide(tmp_path):
    conf = "import pytest\n\n\n@pytest.fixture(autouse=True)\ndef env():\n    return 1\n"
    rev = _rev(tmp_path / "a", {"pkg/tests/conftest.py": conf})
    assert L.label_static_hit(rev, "FR-01.09", ["pkg/tests/conftest.py (fixture/helper) -> pkg/tests/test_u.py"])[0]
    gone = _rev(tmp_path / "b", {"pkg/tests/helper.py": None})
    assert L.label_static_hit(gone, "FR-01.09", ["pkg/tests/helper.py (fixture/helper) -> pkg/tests/test_u.py"])[0]
    assert not L.label_static_hit(gone, "FR-01.09", ["pkg/tests/helper.py (fixture/helper) -> pkg/tests/missing.py"])[0]


def test_spec_hit_needs_normative_text_not_bookkeeping(tmp_path):
    marker = _rev(tmp_path / "a", {SPEC: SPEC_TEXT.replace("unit (inferred)", "unit").replace("| code |", "| inferred |", 1)})
    assert not L.label_spec_hit(marker, "FR-01.09")[0]
    real = _rev(tmp_path / "b", {SPEC: SPEC_TEXT.replace("Prepare a release.", "Prepare and sign a release.")})
    assert L.label_spec_hit(real, "FR-01.09")[0]
    assert not L.label_spec_hit(real, "FR-01.10")[0]


def test_code_hit_needs_a_bound_test_executing_the_changed_function(tmp_path):
    prod = "def price():\n    return 1\n\n\ndef other():\n    return 2\n"
    root = make_repo(tmp_path, {**FILES, "pkg/prod.py": prod})
    base = commit(root, {"README.md": "x"}, "pad")
    head = commit(root, {"pkg/prod.py": prod.replace("return 1", "return 11")}, "change")
    rev = GitRev(root, base, head)
    ctx = {"pkg/prod.py": {2: {"pkg/tests/test_a.py::test_price"}, 6: {"pkg/tests/test_a.py::test_other"}}}
    bound = lambda tid, fr: fr == "FR-01.09" and tid.endswith("test_price")  # noqa: E731
    assert L.label_code_hit(rev, "FR-01.09", ["pkg/prod.py::price"], ctx, bound)[0]
    assert not L.label_code_hit(rev, "FR-01.09", ["pkg/prod.py::other"], ctx, bound)[0]  # not the changed function
    assert not L.label_code_hit(rev, "FR-01.10", ["pkg/prod.py::price"], ctx, bound)[0]


def test_label_all_counts_wrong_per_100_prs_and_samples(tmp_path):
    root = make_repo(tmp_path, FILES)
    base = commit(root, {"README.md": "x"}, "pad")
    head = commit(root, {"pkg/tests/test_a.py": TEST_A.replace("== 1.0", "== 1.01")}, "change")
    rec = {"pr": 1, "merge": head, "declared": ["FR-01.09"], "sources": {"FR-01.09": ["test"], "FR-01.10": ["test"]},
           "evidence": {"test": {"FR-01.09": ["pkg/tests/test_a.py::test_price"], "FR-01.10": ["pkg/tests/test_a.py::test_other"]}, "static": {}}}
    subprocess.run(["git", "-C", str(root), "tag", "-f", "m", head], check=True, capture_output=True)
    assert base  # the squash first parent is `head^`
    data = {"records": [rec]}
    L.label_all(root, data, None)
    labels = {h["fr"]: h["label"] for h in data["records"][0]["hits"]}
    assert labels == {"FR-01.09": "correct-benign", "FR-01.10": "wrong"}
    block = data["measure"]["hit_labels"]
    assert block["by_source"] == {"test": {"correct-benign": 1, "wrong": 1}} and block["wrong_per_100_prs"] == {"test": 100.0}
    assert len(block["sample"]) == 2


def test_fanout_changed_counts_functions_and_the_unattributed():
    prs = [{"fan_out": {"a.py::f": ["FR-1"], "a.py::g": ["FR-1", "FR-2", "FR-3"]}, "unattributed": ["b.py::h: executed by no FR-bound test", "c.py: no coverage at base"]}, {"fan_out": {}}]
    out = M.fanout_changed(prs)
    assert (out["changed_functions_attributed"], out["changed_unattributed"], out["max"], out["histogram"]) == (2, 1, 3, {1: 1, 3: 1})
    assert out["over_n"]["2"] == 1


def test_fanout_executed_reads_bindings_from_the_test_files(tmp_path):
    (tmp_path / "pkg" / "tests").mkdir(parents=True)
    (tmp_path / "pkg" / "prod.py").write_text("def a():\n    return 1\n\n\ndef b():\n    return 2\n", encoding="utf-8")
    (tmp_path / "pkg" / "tests" / "test_p.py").write_text(TEST_A, encoding="utf-8")
    ctx = {"pkg/prod.py": {2: {"pkg/tests/test_p.py::test_price", "pkg/tests/test_p.py::test_other"}}, "pkg/tests/test_p.py": {2: {"x"}}}
    out = M.fanout_executed(ctx, tmp_path)
    assert (out["functions_in_measured_files"], out["functions_executed_by_any_test"], out["max"], out["histogram"]) == (2, 1, 2, {2: 1})


def test_verifier_and_root_timing_run_the_named_commands(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "pytest" in cmd:
            Path(kw["env"]["COVERAGE_FILE"]).write_bytes(b"db")
        return subprocess.CompletedProcess(cmd, 0, stdout="== 3 passed in 0.1s ==\n", stderr="")

    monkeypatch.setattr(M.subprocess, "run", fake_run)
    recs = [{"pr": n, "run_id": f"iterate-{n}", "merge": f"sha{n}", "class": "iterate"} for n in range(1, 8)] + [{"pr": 9, "class": "docs"}]
    out = M.verifier_wallclock(tmp_path, recs, 5)
    assert [r["pr"] for r in out["runs"]] == [7, 6, 5, 4, 3] and calls[0][-2:] == ["--commit", "sha7"]
    assert M.verifier_wallclock(tmp_path, recs, 1, tmp_path / "wt")["tree"].startswith("detached") and "worktree" in calls[-3]
    timed = M.time_root(tmp_path, "pkg/tests", tmp_path / "w", contexts=True, env={})
    assert timed["summary"] == "3 passed in 0.1s" and "--cov-context=test" in calls[-1] and timed["db_bytes"] == 2
    assert "--cov-context=test" not in (M.time_root(tmp_path, "pkg/tests", tmp_path / "w", contexts=False, env={}) and calls[-1])
    (tmp_path / "plugins" / "p" / "tests").mkdir(parents=True)
    (tmp_path / "shared" / "tests").mkdir(parents=True)
    assert M.discover_roots(tmp_path) == ["shared/tests", "plugins/p/tests"]


def test_cli_merges_results_into_the_replay_json(tmp_path, monkeypatch):
    out = tmp_path / "replay.json"
    out.write_text(json.dumps({"records": [{"pr": 1, "run_id": "iterate-1", "merge": "s", "class": "iterate"}], "code": {"prs": [{"fan_out": {"f": ["FR-1"]}}]}}), encoding="utf-8")
    monkeypatch.setattr(M.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""))
    assert measure_baseline.main(["verifier", "--repo", str(tmp_path), "--out", str(out)]) == 0
    assert measure_baseline.main(["roots", "--repo", str(tmp_path), "--out", str(out), "--workdir", str(tmp_path / "w"), "--only", "x/tests", "--plain", "x/tests"]) == 0
    measure = json.loads(out.read_text(encoding="utf-8"))["measure"]
    assert measure["verifier"]["runs"][0]["pr"] == 1 and [r["contexts"] for r in measure["roots"]["runs"]] == [True, False]
    with pytest.raises(SystemExit):
        measure_baseline.main(["fanout", "--repo", str(tmp_path), "--out", str(out)])
