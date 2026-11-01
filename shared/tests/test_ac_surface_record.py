"""Q1: the observable surface computed from a diff, the append-only AC record, the F11 compare, and the per-unit hold."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from lib import ac_decision as ad
from lib import ac_hold
from lib import ac_record as ar
from lib import ac_surface as sf
from lib import loop_state
from tools import write_plan_stub as wps
from tools.verifiers import pre_build_ac_check as chk

_RUN = "iterate-2026-11-01-q1-test"
_SPEC = ".shipwright/planning/01-adopted/spec.md"
_BASE_SPEC = "### FR-01.03 - Drafts\n\n- (E) [AC05] Given a draft, when saved, then it is kept.\n"


def _diff(path: str, added=(), removed=(), extra="") -> str:
    body = "".join(f"-{x}\n" for x in removed) + "".join(f"+{x}\n" for x in added)
    return f"diff --git a/{path} b/{path}\n{extra}--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n{body}"


# --- the observable surface -----------------------------------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("path,expected", [
    ("plugins/x/scripts/a.py", True), ("plugins/x/hooks/hooks.json", True), ("plugins/x/agents/r.md", True),
    ("plugins/x/skills/y/SKILL.md", True), ("plugins/x/skills/y/references/F5.md", True), ("shared/prompts/p.md", True),
    ("shared/schemas/s.schema.json", True), ("shared/templates/t.md", True), ("shared/constitution.md", True),
    (".github/workflows/ci.yml", True), ("docs/guide.md", False), ("README.md", False), (".shipwright/planning/x/spec.md", False),
    ("shared/tests/test_a.py", False), ("plugins/x/tests/conftest.py", False), ("CHANGELOG-unreleased.d/x/y.md", False),
    ("shipwright_events.jsonl", False), ("shipwright_test_results.json", False), ("notes/todo.md", False), ("data.bin", False),
])
def test_path_classes(path, expected):
    assert sf.is_observable_path(path) is expected


@pytest.mark.covers("FR-01.11/AC49")
def test_only_docs_tests_comments_whitespace_and_renames_are_exempt():
    text = "".join([
        _diff("docs/guide.md", ["new"]), _diff("shared/tests/test_a.py", ["assert 1"]),
        _diff("shared/scripts/a.py", ["# only a comment", ""], ["", "# the old comment"]),
        _diff("shared/scripts/b.py", ["x  =  1"], ["x = 1"]),
        "diff --git a/shared/scripts/old.py b/shared/scripts/new.py\nsimilarity index 100%\nrename from shared/scripts/old.py\nrename to shared/scripts/new.py\n",
    ])
    got = sf.observable_files(sf.parse_diff(text))
    assert got == {"observable": False, "files": [], "ignored": 5}


@pytest.mark.covers("FR-01.11/AC49")
def test_a_behaviour_change_is_observable_and_new_or_deleted_files_always_are():
    text = _diff("shared/scripts/a.py", ["return 2"], ["return 1"]) + "diff --git a/plugins/x/agents/n.md b/plugins/x/agents/n.md\nnew file mode 100644\n--- /dev/null\n+++ b/plugins/x/agents/n.md\n@@ -0,0 +1 @@\n+# heading\n"
    got = sf.observable_files(sf.parse_diff(text))
    assert got["observable"] and got["files"] == ["plugins/x/agents/n.md", "shared/scripts/a.py"]
    # a "+++"-looking content line inside a hunk is content, not a header
    rec = sf.parse_diff(_diff("shared/scripts/c.py", ["++ not a header"]))["shared/scripts/c.py"]
    assert rec["added"] == ["++ not a header"]
    assert sf.parse_diff("") == {} and sf.parse_diff("stray\n+line") == {}


def _git(root: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *a], capture_output=True, text=True, check=True).stdout


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".shipwright/planning/01-adopted").mkdir(parents=True)
    (root / _SPEC).write_text(_BASE_SPEC, encoding="utf-8")
    _git(tmp_path, "init", "-q", str(root))
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root


@pytest.mark.covers("FR-01.11/AC49")
def test_git_changes_sees_committed_working_tree_and_untracked(tmp_path):
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD").strip()
    (root / "tool.py").write_text("print(1)\n", encoding="utf-8")
    assert sf.observable_files(sf.git_changes(root, base))["files"] == ["tool.py"]
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "c")
    assert sf.observable_files(sf.git_changes(root, base, "HEAD"))["files"] == ["tool.py"]
    (root / "blob.bin").write_bytes(b"\xff\xfe\x00")
    assert "blob.bin" in sf.git_changes(root, base)
    with pytest.raises(RuntimeError):
        sf.git_changes(root, "no-such-ref")


# --- the append-only record, the compare ---------------------------------------------------------

def _result(**kw) -> dict:
    return ad.decide([{"kind": "add", "owner_fr": "FR-01.03", "new_text": "A saved draft survives a restart", **kw}],
                     {"acs": {}, "frs": {"FR-01.03"}})


@pytest.mark.covers("FR-01.11/AC49")
def test_force_appends_a_superseded_record_and_never_replaces(tmp_path):
    first = ar.append_record(tmp_path, _RUN, _result())
    second = ar.append_record(tmp_path, _RUN, _result(new_text="A saved draft survives two restarts"))
    assert (first["kind"], first["seq"], first["supersedes"]) == ("frozen", 1, None)
    assert (second["kind"], second["seq"], second["supersedes"]) == ("superseded", 2, 1)
    recs = ar.read_records(tmp_path, _RUN)
    assert [r["seq"] for r in recs] == [1, 2] and "restart" in recs[0]["items"][0]["new_text"] and recs[0]["counts"]["total"] == 1
    path = ar.record_path(tmp_path, _RUN)
    path.write_text(path.read_text(encoding="utf-8") + "garbage\n[1]\n", encoding="utf-8")
    assert len(ar.read_records(tmp_path, _RUN)) == 2 and ar.read_records(tmp_path, "nope") == []


@pytest.mark.covers("FR-01.11/AC49")
def test_write_plan_stub_force_keeps_the_original_freeze(tmp_path, monkeypatch, capsys):
    decided = tmp_path / "decided.json"
    decided.write_text(json.dumps(_result()), encoding="utf-8")
    base = ["--project-root", str(tmp_path), "--run-id", _RUN, "--goal", "g", "--reason", "r", "--ref", "x", "--ac-decision", str(decided)]
    monkeypatch.setattr("sys.argv", ["write_plan_stub.py", *base])
    assert wps.main() == 0
    monkeypatch.setattr("sys.argv", ["write_plan_stub.py", *base])
    assert wps.main() == 1  # refuses to overwrite
    monkeypatch.setattr("sys.argv", ["write_plan_stub.py", *base, "--force"])
    assert wps.main() == 0
    assert [r["kind"] for r in ar.read_records(tmp_path, _RUN)] == ["frozen", "superseded"]
    stub = (tmp_path / ".shipwright/planning/iterate" / _RUN / "plan.md").read_text(encoding="utf-8")
    assert "AC item:" in stub and "AC decisions:" in stub
    capsys.readouterr()


@pytest.mark.covers("FR-01.11/AC49")
def test_freeze_compare_names_both_texts():
    changed = {"FR-01.03.AC06": "- (E) [AC06] A saved draft survives a restart (iterate-x)"}
    ok = [{"kind": "add", "ac": "FR-01.03.AC06", "new_text": "A saved draft survives a restart"}]
    assert ar.freeze_differences(ok, changed, set()) == []
    assert ar.freeze_differences([{"kind": "add", "new_text": "a saved draft survives a restart"}], changed, set()) == []
    bad = ar.freeze_differences([{"kind": "add", "ac": "FR-01.03.AC06", "new_text": "Drafts never vanish"}], changed, set())
    assert "Drafts never vanish" in bad[0] and "survives a restart" in bad[0]
    assert "no AC with this wording" in ar.freeze_differences([{"kind": "add", "new_text": "Something else"}], changed, set())[0]
    assert ar.freeze_differences([{"kind": "remove", "ac": "FR-01.03.AC05"}], {}, set())
    assert ar.freeze_differences([{"kind": "remove", "ac": "FR-01.03.AC05"}], {}, {"FR-01.03.AC05"}) == []
    assert ar.freeze_differences(["junk"], {}, set()) and ar.freeze_differences("junk", {}, set()) == []


# --- the F11 check ----------------------------------------------------------------------------------

@pytest.fixture
def branch(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD").strip()
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: {"source": "iterate", "intent": "bug"})
    monkeypatch.setattr(chk, "_branch_base_commit", lambda r, c: base)

    def commit(files: dict[str, str]) -> str:
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "work")
        return _git(root, "rev-parse", "HEAD").strip()
    return root, commit


def _spec_with(text: str) -> str:
    return _BASE_SPEC + f"- (E) [AC06] {text}\n"


@pytest.mark.covers("FR-01.11/AC49")
def test_check_passes_without_a_record_when_nothing_observable_changed_even_for_a_bug(branch):
    root, commit = branch
    head = commit({"docs/a.md": "words\n", "shared/tests/test_a.py": "x = 1\n"})
    res = chk.check_pre_build_ac_recorded(root, _RUN, head)
    assert res.ok and "no observable change" in res.detail


@pytest.mark.covers("FR-01.11/AC49")
def test_check_warns_when_an_observable_change_has_no_record_or_only_an_exemption(branch):
    root, commit = branch
    head = commit({"shared/scripts/a.py": "x = 1\n"})
    res = chk.check_pre_build_ac_recorded(root, _RUN, head)
    assert not res.ok and res.severity == "warning" and res.strict_exempt and "no AC record" in res.detail
    ar.append_record(root, _RUN, ad.decide([{"kind": "exempt"}], {"acs": {}, "frs": set()}))
    assert "recorded as no observable change" in chk.check_pre_build_ac_recorded(root, _RUN, head).detail


@pytest.mark.covers("FR-01.11/AC49")
def test_check_accepts_a_restore_of_an_existing_ac_and_flags_a_gap(branch):
    root, commit = branch
    head = commit({"shared/scripts/a.py": "x = 1\n"})
    ar.append_record(root, _RUN, ad.decide([{"kind": "restore", "restores_ac": "FR-01.03.AC05"}], {"acs": {"FR-01.03.AC05": "t"}, "frs": set()}))
    assert chk.check_pre_build_ac_recorded(root, _RUN, head).ok
    path = ar.record_path(root, _RUN)
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["items"][0]["restores_ac"] = "FR-01.03.AC99"
    path.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    assert "not in the catalog" in chk.check_pre_build_ac_recorded(root, _RUN, head).detail


@pytest.mark.covers("FR-01.11/AC49")
def test_check_compares_the_frozen_text_with_the_catalog_in_the_diff(branch):
    root, commit = branch
    head = commit({"shared/scripts/a.py": "x = 1\n", _SPEC: _spec_with("A saved draft survives a restart")})
    ar.append_record(root, _RUN, _result())
    assert chk.check_pre_build_ac_recorded(root, _RUN, head).ok
    ar.append_record(root, _RUN, _result(new_text="Drafts never vanish"))
    res = chk.check_pre_build_ac_recorded(root, _RUN, head)
    assert not res.ok and "Drafts never vanish" in res.detail and "survives a restart" in res.detail and "superseded 1 time" in res.detail


@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("line", ["[1, 2]", '{"items": "x"}', '{"items": ["junk"]}', '{"items": [{"kind": "add", "new_text": 5}], "decisions": "x"}', '{"items": [{"kind": 7}]}'])
def test_malformed_record_data_is_a_warning_never_a_crash(branch, line):
    root, commit = branch
    head = commit({"shared/scripts/a.py": "x = 1\n"})
    path = ar.record_path(root, _RUN)
    path.parent.mkdir(parents=True)
    path.write_text(line + "\n", encoding="utf-8")
    res = chk.check_pre_build_ac_recorded(root, _RUN, head)
    assert not res.ok and res.severity == "warning"


@pytest.mark.covers("FR-01.11/AC49")
def test_check_skips_cleanly_and_never_raises(branch, monkeypatch):
    root, commit = branch
    head = commit({"shared/scripts/a.py": "x = 1\n"})
    assert chk.check_pre_build_ac_recorded(root, _RUN, "").severity == "skipped"
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: None)
    assert chk.check_pre_build_ac_recorded(root, _RUN, head).severity == "skipped"
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: {"source": "build"})
    assert chk.check_pre_build_ac_recorded(root, _RUN, head).severity == "skipped"
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: (_ for _ in ()).throw(ValueError("boom")))
    res = chk.check_pre_build_ac_recorded(root, _RUN, head)
    assert not res.ok and "boom" in res.detail


# --- the per-unit hold ------------------------------------------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_only_the_ac_question_escalation_holds_its_own_unit():
    esc = {"status": "escalated", "reason_code": "ac_question_requires_operator"}
    assert ac_hold.is_ac_hold(esc) and not ac_hold.is_ac_hold({**esc, "reason_code": "architecture_review_rejected"})
    assert not ac_hold.is_ac_hold({"status": "failed"}) and not ac_hold.is_ac_hold("x")
    claimed = {"attempt_id": "a"}
    assert loop_state.resolve_record_status("sub_iterate", claimed, "escalated", "ac_question_requires_operator") == "held"
    assert loop_state.resolve_record_status("sub_iterate", claimed, "escalated", "architecture_review_rejected") == "failed"
    assert loop_state.resolve_record_status("sub_iterate", claimed, "complete") == "built"
    assert loop_state.resolve_record_status("section", {}, "escalated", "ac_question_requires_operator") == "escalated"


def _hold_state(tmp_path: Path) -> Path:
    state = tmp_path / "loop_state.json"
    unit = {"id": "Q1", "status": "running", "attempt": 0, "attempt_id": "A1", "branch": "b", "finished_at": None, "commit": None}
    state.write_text(json.dumps({"loop_id": "loop-1", "kind": "sub_iterate", "units": [unit]}), encoding="utf-8")
    return state


class _Args:
    def __init__(self, state: Path, result: dict):
        self.state, self.unit, self.attempt_id, self.result = str(state), "Q1", "A1", json.dumps(result)


@pytest.mark.covers("FR-01.11/AC49")
def test_record_holds_only_the_unit_on_an_ac_question_and_stops_the_wave_otherwise(tmp_path, capsys):
    from autonomous_loop import cmd_record
    esc = {"sub_iterate_id": "Q1", "status": "escalated", "reason": "ac_question_requires_operator: x", "reason_code": "ac_question_requires_operator",
           "ac_questions": [{"item": 0, "row": 1, "question": "q"}]}
    state = _hold_state(tmp_path)
    assert cmd_record(_Args(state, esc)) == 0  # no wave STRICT-STOP
    row = json.loads(state.read_text(encoding="utf-8"))["units"][0]
    assert row["status"] == "held" and row["result_path"].endswith("result.json")
    other = _hold_state(tmp_path)
    assert cmd_record(_Args(other, {**esc, "reason_code": "architecture_review_rejected"})) == 3
    assert json.loads(other.read_text(encoding="utf-8"))["units"][0]["status"] == "failed"
    capsys.readouterr()


@pytest.mark.covers("FR-01.11/AC49")
def test_integration_an_unattended_question_flows_from_the_tool_to_a_held_unit_and_the_wave_goes_on(tmp_path, capsys):
    """Real scenario: the CLI asks under --autonomous, its escalation is recorded for unit Q1 (held, exit 0), a second unit still completes."""
    from autonomous_loop import cmd_record
    from tools import ac_decision as cli
    root = _repo(tmp_path)
    ask = tmp_path / "ask.json"
    ask.write_text(json.dumps({"items": [{"kind": "add", "new_text": "A saved draft survives a restart"}]}), encoding="utf-8")
    assert cli.main(["--project-root", str(root), "--from-json", str(ask), "--base-ref", "HEAD", "--autonomous", "--sub-iterate-id", "Q1"]) == 10
    escalation = json.loads(capsys.readouterr().out)["escalation"]
    assert escalation["sub_iterate_id"] == "Q1"
    units = [{"id": "Q1", "status": "running", "attempt": 0, "attempt_id": "A1", "branch": "b1", "finished_at": None, "commit": None},
             {"id": "Q2", "status": "running", "attempt": 0, "attempt_id": "A2", "branch": "b2", "finished_at": None, "commit": None}]
    state = tmp_path / "loop_state.json"
    state.write_text(json.dumps({"loop_id": "loop-1", "kind": "sub_iterate", "units": units}), encoding="utf-8")

    class Args:
        def __init__(self, unit: str, attempt_id: str, result: dict):
            self.state, self.unit, self.attempt_id, self.result = str(state), unit, attempt_id, json.dumps(result)

    assert cmd_record(Args("Q1", "A1", escalation)) == 0
    done = {"status": "complete", "commit": "abc", "tests_passed": 1, "tests_total": 1, "branch": "b2"}
    assert cmd_record(Args("Q2", "A2", done)) == 0
    rows = {u["id"]: u["status"] for u in json.loads(state.read_text(encoding="utf-8"))["units"]}
    assert rows == {"Q1": "held", "Q2": "built"}
    capsys.readouterr()
