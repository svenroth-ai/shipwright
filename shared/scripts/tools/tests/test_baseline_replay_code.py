"""BP unit BL0 - the T-code replay leg, the CLI branches around it, and the code-review fixes (real git, fake test runs)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools
sys.path.insert(0, str(Path(__file__).resolve().parent))

import measure_baseline  # noqa: E402
import replay_baseline_lock as replay  # noqa: E402
from _baseline_repo import SPEC, SPEC_TEXT, commit, make_repo  # noqa: E402
from verifiers import _baseline_label_all as LA  # noqa: E402
from verifiers import _baseline_measure as M  # noqa: E402
from verifiers import _baseline_touch_replay_code as rc  # noqa: E402
from verifiers._baseline_touch_coverage import code_touched  # noqa: E402
from verifiers._baseline_touch_git import GitRev  # noqa: E402
from verifiers._baseline_touch_static import _imports_module  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")

PROD = "def price(x):\n    a = 1\n    b = 2\n    c = 3\n    d = 4\n    e = x == 1\n    return e\n"
OTHER = PROD.replace("price", "other")
TESTS = (
    'import pytest\n\n\n@pytest.mark.covers("FR-01.09")\ndef test_price():\n    assert True\n\n\n'
    "def test_other():\n    assert True\n"
)
SKILL = "# Skill\n\nDo the thing.\n"
BASE = {
    SPEC: SPEC_TEXT, "shared/scripts/prod.py": PROD, "shared/scripts/other.py": OTHER,
    "shared/scripts/tests/test_prod.py": TESTS, "plugins/p/skills/s/SKILL.md": SKILL,
}
BOUND = "shared/scripts/tests/test_prod.py::test_price"
UNBOUND = "shared/scripts/tests/test_prod.py::test_other"
CONTEXTS = {"shared/scripts/prod.py": {n: {BOUND} for n in range(1, 8)}, "shared/scripts/other.py": {n: {UNBOUND} for n in range(1, 8)}}


def _repo(tmp_path):
    root = make_repo(tmp_path, BASE)
    head = commit(root, {"shared/scripts/prod.py": PROD.replace("a = 1", "a = 11")}, "feat: change (#1)")
    return root, head


def test_run_tier_reports_time_outcome_and_database_size(tmp_path, monkeypatch):
    def fake_run(cmd, **kw):
        Path(kw["env"]["COVERAGE_FILE"]).write_bytes(b"123")
        return subprocess.CompletedProcess(cmd, 0, stdout="== 4 passed ==\n", stderr="")

    monkeypatch.setattr(rc.subprocess, "run", fake_run)
    out = rc._run_tier(tmp_path, "shared/scripts/tests", "shared", tmp_path / "db", {})
    assert (out["tier"], out["rc"], out["summary"], out["db_bytes"]) == ("shared/scripts/tests", 0, "== 4 passed ==", 3)


def test_probe_reports_which_source_notices_each_seeded_change(tmp_path):
    root = make_repo(tmp_path, BASE)
    base = commit(root, {"README.md": "x"}, "pad")
    out = {p["probe"]: p for p in rc.probe(root, base, CONTEXTS)}
    bound = out["production line executed by an FR-bound test"]
    assert bound["noticed"] and bound["sources"] == {"FR-01.09": ["code"]}
    unbound = out["production line executed only by tests without an FR binding"]
    assert unbound["noticed"] is False and unbound["unattributed"]
    assert out["prose (SKILL.md) line"]["noticed"] is False
    assert subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True, check=True).stdout == ""


def test_probe_does_not_count_an_edit_that_does_not_parse(tmp_path):
    broken = PROD.replace("e = x == 1", "e = foo(\n        x)")
    root = make_repo(tmp_path, {**BASE, "shared/scripts/prod.py": broken})
    base = commit(root, {"README.md": "x"}, "pad")
    out = rc.probe(root, base, {"shared/scripts/prod.py": {n: {BOUND} for n in range(1, 9)}})
    assert out[0]["noticed"] is None and "did not parse" in out[0]["probe"]


def test_probe_reports_a_seeded_edit_git_refuses_to_commit(tmp_path, monkeypatch):
    root = make_repo(tmp_path, BASE)
    base = commit(root, {"README.md": "x"}, "pad")

    def refuse(*_a, **_k):
        raise subprocess.CalledProcessError(1, "git", stderr=b"nothing to commit")

    monkeypatch.setattr(rc, "_commit", refuse)
    out = rc.probe(root, base, CONTEXTS)
    assert all(p["noticed"] is None for p in out) and "nothing to commit" in out[0]["error"]


def test_commit_stages_only_the_seeded_file(tmp_path):
    root = make_repo(tmp_path, BASE)
    (root / "stray.txt").write_text("keep me out", encoding="utf-8")
    sha = rc._commit(root, "shared/scripts/prod.py", PROD.replace("a = 1", "a = 2"), "probe")
    shown = subprocess.run(["git", "-C", str(root), "show", "--name-only", "--format=", sha], capture_output=True, text=True, check=True).stdout
    assert shown.split() == ["shared/scripts/prod.py"]


def _stub_runs(monkeypatch, tmp_path):
    def fake_tier(wt, root, target, db, env):
        db.write_bytes(b"x")
        return {"tier": root, "seconds": 0.1, "rc": 0, "summary": "ok", "db_bytes": 1}

    monkeypatch.setattr(rc, "_run_tier", fake_tier)
    monkeypatch.setattr(rc, "load_contexts", lambda db, wt, prefix="": CONTEXTS)


def test_replay_code_attributes_the_prs_diff_through_the_base_contexts(tmp_path, monkeypatch):
    root, head = _repo(tmp_path)
    _stub_runs(monkeypatch, tmp_path)
    records = [{"pr": 1, "merge": head, "class": "iterate"}]
    tiers = (("shared/scripts/tests", "shared"), ("plugins/none/tests", "plugins/none/scripts"))
    out = rc.replay_code(root, records, 1, tmp_path / "work", 1, tiers)
    entry = out["prs"][0]
    assert entry["code"] == {"FR-01.09": ["shared/scripts/prod.py::price"]} and entry["code_files"] == ["shared/scripts/prod.py"]
    assert entry["tiers"][1] == {"tier": "plugins/none/tests", "missing_at_base": True} and entry["probes"]
    assert not (tmp_path / "work" / "pr1").exists()
    with pytest.raises(ValueError):
        rc.replay_code(root, records, 1, root / "inside", 0, tiers)


def test_rerun_probes_uses_the_databases_a_previous_run_left(tmp_path, monkeypatch):
    root, head = _repo(tmp_path)
    _stub_runs(monkeypatch, tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    (work / "cov-1-0").write_bytes(b"x")
    records = [{"pr": 1, "merge": head, "class": "iterate", "code_files": ["shared/scripts/prod.py"]}]
    out = rc.rerun_probes(root, records, 1, work, (("shared/scripts/tests", "shared"),))
    assert out[0]["pr"] == 1 and {p["probe"] for p in out[0]["probes"]} >= {"prose (SKILL.md) line"}


def test_cli_runs_the_code_leg_and_the_probe_only_branch(tmp_path, monkeypatch, capsys):
    root, head = _repo(tmp_path)
    prs = tmp_path / "prs.json"
    prs.write_text(json.dumps([{"number": 1, "title": "feat", "headRefName": "iterate/x", "mergeCommit": {"oid": head}, "labels": []}]), encoding="utf-8")
    out = tmp_path / "out.json"
    seen = {}

    def fake_replay_code(repo, records, k, workdir, probes, *a, **kw):
        seen["code"] = (k, probes)
        return {"prs": [], "tiers": []}

    monkeypatch.setattr(rc, "replay_code", fake_replay_code)
    monkeypatch.setattr(rc, "rerun_probes", lambda repo, records, k, workdir, *a: [{"pr": 1, "probes": []}])
    with pytest.raises(SystemExit):
        replay.main(["--repo", str(root), "--prs-json", str(prs), "--code-sample", "1"])
    assert replay.main(["--repo", str(root), "--prs-json", str(prs), "--code-sample", "1", "--probes", "1", "--workdir", str(tmp_path / "w"), "--out", str(out)]) == 0
    assert seen["code"] == (1, 1) and "code" in json.loads(out.read_text(encoding="utf-8"))
    with pytest.raises(SystemExit):
        replay.main(["--repo", str(root), "--prs-json", str(prs), "--probes-only"])
    probes = tmp_path / "probes.json"
    assert replay.main(["--repo", str(root), "--from-json", str(out), "--probes-only", "--workdir", str(tmp_path / "w"), "--out", str(probes)]) == 0
    assert json.loads(probes.read_text(encoding="utf-8")) == [{"pr": 1, "probes": []}]
    capsys.readouterr()


def test_cli_label_and_summary_rewrite_the_stored_json(tmp_path, capsys):
    root, head = _repo(tmp_path)
    rec = {"pr": 1, "merge": head, "class": "iterate", "held": True, "declared": [], "declared_from": "none", "incomplete": [], "moved": [],
           "sources": {}, "evidence": {"test": {}, "static": {}}}
    out = tmp_path / "replay.json"
    out.write_text(json.dumps({"records": [rec], "summary": {}}), encoding="utf-8")
    assert measure_baseline.main(["label", "--repo", str(root), "--out", str(out)]) == 0
    assert measure_baseline.main(["summary", "--repo", str(root), "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["records"][0]["hits"] == [] and data["measure"]["hit_labels"]["hits"] == 0 and data["summary"]["prs"] == 1
    capsys.readouterr()


def test_cli_fanout_reads_only_the_root_databases(tmp_path, monkeypatch):
    root = make_repo(tmp_path, BASE)
    work = tmp_path / "work"
    (work / "roots").mkdir(parents=True)
    (work / "roots" / "cov-shared_scripts_tests").write_bytes(b"x")
    (work / "cov-1-0").write_bytes(b"x")  # a per-PR database from the code leg must not be read
    import verifiers._baseline_touch_coverage as cov

    monkeypatch.setattr(cov, "load_contexts", lambda db, repo, prefix="": CONTEXTS)
    out = tmp_path / "replay.json"
    out.write_text(json.dumps({"records": [], "code": {"prs": [{"fan_out": {"f": ["FR-1"]}, "unattributed": []}]}}), encoding="utf-8")
    assert measure_baseline.main(["fanout", "--repo", str(root), "--out", str(out), "--workdir", str(work)]) == 0
    measure = json.loads(out.read_text(encoding="utf-8"))["measure"]
    assert measure["fanout_executed"]["databases"] == ["cov-shared_scripts_tests"]
    assert measure_baseline.main(["fanout", "--changed-only", "--repo", str(root), "--out", str(out)]) == 0


def test_a_pure_insertion_inside_a_function_labels_the_code_hit_correct(tmp_path):
    base = "def price():\n    return 1\n"
    root = make_repo(tmp_path, {**BASE, "shared/scripts/prod.py": base})
    pad = commit(root, {"README.md": "x"}, "pad")
    head = commit(root, {"shared/scripts/prod.py": "def price():\n    x = 2\n    return 1\n"}, "insert")
    rev = GitRev(root, pad, head)
    ctx = {"shared/scripts/prod.py": {2: {BOUND}}}
    assert LA.label_code_hit(rev, "FR-01.09", ["shared/scripts/prod.py::price"], ctx, lambda tid, fr: tid == BOUND)[0]


def test_added_code_in_a_nested_function_is_attributed_to_the_enclosing_function_that_exists_at_base(tmp_path):
    outer = "def outer():\n    return 1\n"
    root = make_repo(tmp_path, {**BASE, "shared/scripts/prod.py": outer})
    pad = commit(root, {"README.md": "x"}, "pad")
    head = commit(root, {"shared/scripts/prod.py": "def outer():\n    def inner():\n        return 2\n    return 1\n"}, "nest")
    rev = GitRev(root, pad, head)
    touch = code_touched(rev, rev.changed(), {"shared/scripts/prod.py": {2: {BOUND}}})
    assert set(touch.touched) == {"FR-01.09"} and touch.unattributed == []


def test_added_code_in_a_function_that_is_new_is_noted_not_dropped(tmp_path):
    root = make_repo(tmp_path, {**BASE, "shared/scripts/prod.py": "def outer():\n    return 1\n"})
    pad = commit(root, {"README.md": "x"}, "pad")
    head = commit(root, {"shared/scripts/prod.py": "def outer():\n    return 1\n\n\ndef fresh():\n    return 3\n"}, "new function")
    rev = GitRev(root, pad, head)
    touch = code_touched(rev, rev.changed(), {"shared/scripts/prod.py": {2: {BOUND}}})
    assert touch.touched == {} and any("fresh: new code in a function that does not exist at base" in n for n in touch.unattributed)


def test_parenthesised_multiline_imports_count_as_importing_the_module():
    text = "from pkg import (\n    alpha,\n    helper_mod,\n)\n"
    assert _imports_module(text, "helper_mod") and _imports_module("import a.helper_mod as h\n", "helper_mod")
    assert not _imports_module(text, "other") and not _imports_module("not python (", "helper_mod")


def test_percentiles_use_nearest_rank():
    out = M.fanout_changed([{"fan_out": {f"f{n}": [f"FR-{i}" for i in range(n)] for n in range(1, 16)}}])
    assert (out["p90"], out["p95"], out["median"]) == (14, 15, 8)


def test_code_wrong_rate_is_normalised_by_the_code_sample(tmp_path):
    root, head = _repo(tmp_path)
    data = {"records": [{"pr": 1, "merge": head, "declared": [], "sources": {}, "evidence": {"test": {}, "static": {}}}],
            "code": {"prs": [{"pr": 1, "code": {}, "hits": [{"fr": "FR-1", "source": "code", "label": "wrong", "reason": "x"}]}, {"pr": 2, "code": {}}]}}
    LA.label_all(root, data, None)
    block = data["measure"]["hit_labels"]
    assert block["wrong_per_100_prs"]["code"] == 50.0 and block["code_sample_prs"] == 2


def test_rederive_refreshes_the_git_leg_and_keeps_the_code_leg_inputs(tmp_path, capsys):
    root, head = _repo(tmp_path)
    stale = {"pr": 1, "title": "feat", "branch": "iterate/x", "merge": head, "labels": [], "code_files": ["shared/scripts/prod.py"],
             "sources": {"FR-01.09": ["test"]}, "held": True, "declared": [], "declared_from": "none", "class": "iterate", "incomplete": [], "moved": []}
    out = tmp_path / "replay.json"
    out.write_text(json.dumps({"records": [stale], "summary": {}, "sample": []}), encoding="utf-8")
    assert measure_baseline.main(["rederive", "--repo", str(root), "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    rec = data["records"][0]
    assert rec["sources"] == {} and rec["held"] is False and rec["code_files"] == ["shared/scripts/prod.py"]
    assert data["summary"]["held"] == 0 and data["sample"] == []
    capsys.readouterr()
