"""BP unit BL0 - replay aggregation, PR selection, mutation operator and the fail-closed git layer."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _baseline_repo import SPEC, SPEC_TEXT, commit, git, make_repo  # noqa: E402
from verifiers._baseline_touch_core import evaluate_hold, touched_set  # noqa: E402
from verifiers._baseline_touch_git import GitRev  # noqa: E402
import replay_baseline_lock as replay  # noqa: E402
from verifiers._baseline_touch_replay_code import _mutate, select_prs  # noqa: E402
from verifiers._baseline_touch_replay_stats import declared_frs, pr_class, sample_for_operator, summarise  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")


def _rec(pr, cls="iterate", held=True, sources=None, declared=(), source="affected_frs", **kw):
    return {"pr": pr, "class": cls, "held": held, "sources": sources or {}, "declared": list(declared),
            "declared_from": source, "incomplete": [], "moved": [], **kw}


def test_pr_classes():
    assert pr_class("release/v1", "x") == "release"
    assert pr_class("dependabot/npm/x", "bump") == "dependency-bot"
    assert pr_class("iterate/campaign-a--U1", "feat") == "campaign-unit"
    assert pr_class("fix/x", "Revert thing") == "revert"
    assert pr_class("iterate/x", "feat: promote layer coverage") == "layer-promotion"
    assert pr_class("someone/x", "misc") == "manual"


def test_declared_frs_prefers_fr_impact_and_ignores_none():
    assert declared_frs({"fr_impact": {"FR-01.10": "modify", "FR-01.14": "none"}, "affected_frs": ["FR-01.01"]}) == (["FR-01.10"], "fr_impact")
    assert declared_frs({"affected_frs": ["FR-01.02"]}) == (["FR-01.02"], "affected_frs")
    assert declared_frs(None) == ([], "no-event")


def test_summary_counts_hold_rate_per_class_and_agreement():
    recs = [_rec(1, sources={"FR-01.09": ["test"]}, declared=["FR-01.09"]),
            _rec(2, sources={"FR-01.10": ["static"]}),
            _rec(3, cls="docs", held=False),
            {"pr": 4, "error": "boom"}]
    s = summarise(recs)
    assert s["prs_ok"] == 3 and s["errors"] == [4] and s["hold_rate"] == round(2 / 3, 3)
    assert s["hold_by_class"]["docs"]["rate"] == 0.0
    assert s["agree_prs"] == 1 and s["derived_only_prs"] == 1
    assert s["hits_by_source"]["test"] == {"hits": 1, "also_declared": 1}


def test_sample_is_reproducible_and_only_held():
    recs = [_rec(n) for n in range(40)] + [_rec(99, held=False)]
    a, b = sample_for_operator(recs, 5), sample_for_operator(recs, 5)
    assert [r["pr"] for r in a] == [r["pr"] for r in b] and 99 not in {r["pr"] for r in a}


def test_select_prs_takes_only_measured_targets_newest_first():
    recs = [{"pr": 1, "code_files": ["shared/a.py"]}, {"pr": 2, "code_files": ["plugins/other/scripts/x.py"]},
            {"pr": 3, "code_files": ["plugins/shipwright-iterate/scripts/y.py"]}, {"pr": 4, "error": "x"}]
    assert [r["pr"] for r in select_prs(recs, 5)] == [3, 1]
    assert [r["pr"] for r in select_prs(recs, 1)] == [3]
    assert select_prs(recs, 0) == []


def test_mutation_operator_changes_the_line_or_inserts_a_statement():
    assert "!=" in _mutate("def f(a):\n    return a == 1\n", 2)
    assert "_probe = 1" in _mutate("def f(a):\n    x = a\n", 2)


def test_missing_contexts_fail_closed_when_code_is_required(tmp_path):
    root = make_repo(tmp_path, {SPEC: SPEC_TEXT})
    base = commit(root, {"a.md": "x"}, "pad")
    head = commit(root, {"a.md": "y"}, "change")
    t = touched_set(GitRev(root, base, head), require_code=True)
    assert evaluate_hold(t)["held"] and "incomplete" in evaluate_hold(t)["incomplete"][0]
    assert not evaluate_hold(touched_set(GitRev(root, base, head)))["held"]


def test_unreadable_diff_raises_instead_of_reading_as_unchanged(tmp_path):
    root = make_repo(tmp_path, {SPEC: SPEC_TEXT})
    with pytest.raises(RuntimeError):
        GitRev(root, "0" * 40, "1" * 40)  # no merge base: never a silent two-dot diff
    head = commit(root, {"a.py": "x = 1\n"}, "c")
    rev = GitRev(root, head, head)
    assert rev.read("a.py", "head") == "x = 1\n" and rev.read("missing.py", "head") == ""
    assert GitRev(root, head, head).read("a.py", "base") == "x = 1\n"


def test_diff_is_taken_against_the_merge_base(tmp_path):
    root = make_repo(tmp_path, {SPEC: SPEC_TEXT})
    fork = commit(root, {"a.md": "1"}, "fork")
    main = commit(root, {"main_only.md": "m"}, "main moves")
    git(root, "checkout", "-q", "-b", "feature", fork)
    feature = commit(root, {"feat.md": "f"}, "feature")
    changed = {n for _s, _o, n in GitRev(root, main, feature).changed()}
    assert changed == {"feat.md"}


TEST_FILE = 'import pytest\n\n\n@pytest.mark.covers("FR-01.09")\ndef test_price():\n    assert 1 == 1\n'


def _history(tmp_path):
    root = make_repo(tmp_path, {SPEC: SPEC_TEXT, "pkg/tests/test_a.py": TEST_FILE})
    merge = commit(root, {"pkg/tests/test_a.py": TEST_FILE.replace("1 == 1", "2 == 2")}, "feat: change (#7)\n\nRun-ID: iterate-x")
    return root, merge


def test_replay_one_derives_the_touched_set_and_compares_with_the_declaration(tmp_path):
    root, merge = _history(tmp_path)
    events = {"iterate-x": {"affected_frs": ["FR-01.09"], "adr_id": "iterate-x"}}
    pr = {"number": 7, "title": "feat: change", "headRefName": "iterate/x", "mergeCommit": {"oid": merge}, "labels": []}
    rec = replay.replay_one(root, pr, events)
    assert rec["run_id"] == "iterate-x" and rec["declared"] == ["FR-01.09"] and rec["held"]
    assert rec["sources"] == {"FR-01.09": ["test"]} and rec["class"] == "iterate"


def test_replay_one_reports_a_broken_pr_instead_of_aborting(tmp_path):
    root, _ = _history(tmp_path)
    rec = replay.replay_one(root, {"number": 8, "title": "x", "headRefName": "b", "mergeCommit": {"oid": "f" * 40}}, {})
    assert "error" in rec


def test_cli_summarises_and_resummarises_from_json(tmp_path, capsys):
    root, merge = _history(tmp_path)
    prs = tmp_path / "prs.json"
    prs.write_text('[{"number": 7, "title": "feat", "headRefName": "iterate/x", "mergeCommit": {"oid": "%s"}, "labels": []}]' % merge)
    out = tmp_path / "out.json"
    assert replay.main(["--repo", str(root), "--prs-json", str(prs), "--out", str(out)]) == 0
    assert replay.main(["--from-json", str(out)]) == 0
    assert "hold_rate" in capsys.readouterr().out


def test_events_are_indexed_by_run_id(tmp_path):
    f = tmp_path / "e.jsonl"
    f.write_text('{"type": "work_completed", "adr_id": "r1", "affected_frs": ["FR-01.10"]}\nnot json\n{"type": "other"}\n')
    assert set(replay._events_by_run(f)) == {"r1"} and replay._events_by_run(tmp_path / "none") == {}
