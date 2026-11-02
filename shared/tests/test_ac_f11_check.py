"""Q1: the F11 check on the committed record (warning-only, never a crash) and the per-unit hold of an AC question."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.tests.ac_test_helpers import ans, git as _git, repo
from lib import ac_decision as ad
from lib import ac_hold
from lib import ac_record as ar
from lib import loop_state
from tools.verifiers import pre_build_ac_check as chk

_RUN = "iterate-2026-11-01-q1-test"
_SPEC = ".shipwright/planning/01-adopted/spec.md"
_BASE_SPEC = "### FR-01.03 - Drafts\n\n- (E) [AC05] Given a draft, when saved, then it is kept.\n"
_SHA = "sha256:" + "b" * 64


def _repo(tmp_path: Path) -> Path:
    return repo(tmp_path, _BASE_SPEC)


def _result(**kw) -> dict:
    return ad.decide([{"kind": "add", "owner_fr": "FR-01.03", "new_text": "A saved draft survives a restart", **kw}], {"acs": {}, "frs": {"FR-01.03"}})


# --- the F11 check ----------------------------------------------------------------------------------

@pytest.fixture
def branch(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD").strip()
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: {"source": "iterate", "intent": "bug"})
    monkeypatch.setattr(chk, "_branch_base_commit", lambda r, c: base)

    def commit(files: dict[str, str], amend: bool = False) -> str:
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, *(["commit", "-q", "--amend", "--no-edit"] if amend else ["commit", "-qm", "work"]))
        return _git(root, "rev-parse", "HEAD").strip()
    return root, commit


def _record(root, commit, result) -> str:
    """Append the run's AC record and fold it into the last commit (F11 reads the COMMITTED record)."""
    ar.append_record(root, _RUN, result)
    return commit({}, amend=True)


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
    head = _record(root, commit, ad.decide([{"kind": "exempt"}], {"acs": {}, "frs": {"FR-01.03"}}))
    assert "recorded as no observable change" in chk.check_pre_build_ac_recorded(root, _RUN, head).detail


@pytest.mark.covers("FR-01.11/AC49")
def test_check_restore_needs_a_base_catalog_ac_and_a_test_that_names_it(branch):
    root, commit = branch
    head = commit({"shared/scripts/a.py": "x = 1\n"})
    head = _record(root, commit, ad.decide([{"kind": "restore", "restores_ac": "FR-01.03.AC05"}], {"acs": {"FR-01.03.AC05": "t"}, "frs": {"FR-01.03"}}))
    assert "no test file in the diff mentions that AC id" in chk.check_pre_build_ac_recorded(root, _RUN, head).detail
    head = commit({"shared/tests/test_a.py": '@pytest.mark.covers("FR-01.03/AC05")\ndef test_x(): ...\n'})
    assert chk.check_pre_build_ac_recorded(root, _RUN, head).ok
    path = ar.record_path(root, _RUN)
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["items"][0]["restores_ac"] = "FR-01.03.AC99"
    path.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    head = commit({}, amend=True)
    assert "not in the catalog at the base" in chk.check_pre_build_ac_recorded(root, _RUN, head).detail


@pytest.mark.covers("FR-01.11/AC49")
def test_check_compares_the_frozen_text_with_the_catalog_in_the_diff(branch):
    root, commit = branch
    head = commit({"shared/scripts/a.py": "x = 1\n", _SPEC: _spec_with("A saved draft survives a restart")})
    head = _record(root, commit, _result())
    assert chk.check_pre_build_ac_recorded(root, _RUN, head).ok
    head = _record(root, commit, _result(new_text="Drafts never vanish"))
    res = chk.check_pre_build_ac_recorded(root, _RUN, head)
    assert not res.ok and "Drafts never vanish" in res.detail and "survives a restart" in res.detail and "superseded 1 time" in res.detail


@pytest.mark.covers("FR-01.11/AC49")
def test_check_warns_on_a_catalog_edit_no_item_names_even_without_an_observable_diff(branch):
    root, commit = branch
    head = commit({_SPEC: _BASE_SPEC.replace("then it is kept", "then nothing is kept")})  # an existing AC reworded, nothing else changed
    res = chk.check_pre_build_ac_recorded(root, _RUN, head)
    assert not res.ok and "FR-01.03.AC05" in res.detail and "no record item names" in res.detail
    change = {"kind": "change", "ac": "FR-01.03.AC05", "old_text": "Given a draft, when saved, then it is kept.", "new_text": "Given a draft, when saved, then nothing is kept."}
    cat = {"acs": {"FR-01.03.AC05": "- (E) [AC05] Given a draft, when saved, then it is kept."}, "frs": {"FR-01.03"}}
    q = ad.decide([change], cat)["questions"][0]
    head = _record(root, commit, ad.decide([change], cat, answers=[ans(q, "yes")]))
    res = chk.check_pre_build_ac_recorded(root, _RUN, head)
    assert "no record item names" not in res.detail and "answered_via" not in res.detail  # named now; an attended unsigned answer is only counted, never warned


@pytest.mark.covers("FR-01.11/AC49")
def test_check_reruns_the_wording_check_against_identifiers_of_the_committed_diff(branch):
    root, commit = branch
    head = commit({"shared/scripts/plan2go.py": "x = 1\n", "shared/scripts/review-gate.py": "y = 1\n", _SPEC: _spec_with("The plan2go keeps a draft")})
    head = _record(root, commit, _result(new_text="The plan2go keeps a draft"))
    assert "does not read as an outcome" in chk.check_pre_build_ac_recorded(root, _RUN, head).detail
    # a plain hyphenated file name is ordinary prose, not a banned code name
    head = _record(root, commit, _result(new_text="The review-gate keeps a draft"))
    assert "does not read as an outcome" not in chk.check_pre_build_ac_recorded(root, _RUN, head).detail


@pytest.mark.covers("FR-01.11/AC49")
def test_check_warns_about_an_unsigned_asked_decision_only_in_an_unattended_run(branch, monkeypatch):
    root, commit = branch
    head = commit({"shared/scripts/a.py": "x = 1\n", _SPEC: _spec_with("A saved draft survives a restart")})
    base = {"kind": "add", "new_text": "A saved draft survives a restart"}
    cat = {"acs": {}, "frs": {"FR-01.03"}, "titles": {}}
    q = ad.decide([base], cat, bind_id="r")["questions"][0]
    key = ac_hold.load_key(create=True)
    signed = {**ans(q, "yes", "FR-01.03"), "via": "operator", "signature": ac_hold.sign(key, q["question_sha256"], "yes", "FR-01.03")}
    forged = {k: v for k, v in signed.items() if k != "signature"}  # "via": "operator" is only a claim
    for answer, unattended, expect_warning in ((signed, True, False), (forged, True, True), (forged, False, False)):
        monkeypatch.setattr(ar, "is_unattended", lambda root, flag=unattended: flag)
        ar.record_path(root, _RUN).unlink(missing_ok=True)
        head = _record(root, commit, ad.decide([base], cat, bind_id="r", answers=[answer]))
        detail = chk.check_pre_build_ac_recorded(root, _RUN, head).detail
        assert ("signed operator channel" in detail) is expect_warning
    # inline answers (attended) are counted for the PR body, never warned
    monkeypatch.setattr(ar, "is_unattended", lambda root: False)
    ar.record_path(root, _RUN).unlink(missing_ok=True)
    inline = ad.decide([{**base, "answer": {"choice": "yes", "text": "FR-01.03"}}], cat, bind_id="r")
    assert inline["counts"]["answered_inline"] == 1
    head = _record(root, commit, inline)
    assert "answered_via" not in chk.check_pre_build_ac_recorded(root, _RUN, head).detail


@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("line", ["[1, 2]", '{"items": "x"}', '{"items": ["junk"]}', '{"items": [{"kind": "add", "new_text": 5}], "decisions": "x"}', '{"items": [{"kind": 7}]}'])
def test_malformed_record_data_is_a_warning_never_a_crash(branch, line):
    root, commit = branch
    path = ar.record_path(root, _RUN)
    path.parent.mkdir(parents=True)
    path.write_text(line + "\n", encoding="utf-8")
    head = commit({"shared/scripts/a.py": "x = 1\n"})
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

_PROMISE = {"old": "", "new": "A draft is kept", "title": ""}


def _q(**kw) -> dict:
    q = {"item": 0, "row": 1, "question": "q", "kind": "add", "promise": _PROMISE, "options": {}, **kw}
    return {**q, "question_sha256": kw.get("question_sha256") or ac_hold.question_sha("camp--Q1", q["item"], q["kind"], q["promise"], q["options"])}


def _esc(**kw) -> dict:
    return {"sub_iterate_id": "Q1", "status": "escalated", "reason": "ac_question_requires_operator: x", "reason_code": "ac_question_requires_operator", "bind_id": "camp--Q1",
            "ac_questions": [_q()], **kw}


def _hold_state(tmp_path: Path, units=("Q1",)) -> Path:
    state = tmp_path / "loop_state.json"
    rows = [{"id": u, "status": "running", "attempt": 0, "attempt_id": f"A-{u}", "branch": "b", "finished_at": None, "commit": None} for u in units]
    state.write_text(json.dumps({"loop_id": "loop-1", "kind": "sub_iterate", "units": rows}), encoding="utf-8")
    return state


class _Args:
    def __init__(self, state: Path, result: dict, unit: str = "Q1"):
        self.state, self.unit, self.attempt_id, self.result = str(state), unit, f"A-{unit}", json.dumps(result)


@pytest.mark.covers("FR-01.11/AC49")
def test_only_a_well_formed_ac_question_holds_its_own_unit():
    assert ac_hold.is_ac_hold(_esc()) and not ac_hold.is_ac_hold({**_esc(), "reason_code": "architecture_review_rejected"})
    assert not ac_hold.is_ac_hold({"status": "failed"}) and not ac_hold.is_ac_hold("x")
    # the hash is RECOMPUTED from the stable id, item index, kind, promise and options: a well-formed but wrong hash holds nothing
    assert not ac_hold.is_ac_hold(_esc(ac_questions=[_q(question_sha256=_SHA)]))
    assert not ac_hold.is_ac_hold(_esc(bind_id="other")) and not ac_hold.is_ac_hold(_esc(ac_questions=[{**_q(), "item": 1}]))
    claimed = {"attempt_id": "a"}
    assert loop_state.resolve_record_status("sub_iterate", claimed, "escalated", True) == "held"
    assert loop_state.resolve_record_status("sub_iterate", claimed, "escalated", False) == "failed"
    assert loop_state.resolve_record_status("sub_iterate", claimed, "complete") == "built"
    assert loop_state.resolve_record_status("section", {}, "escalated", True) == "escalated"
    assert loop_state.resolve_record_status("sub_iterate", {}, "escalated", True) == "escalated"  # never claimed: no attempt_id


@pytest.mark.covers("FR-01.11/AC49")
def test_record_holds_only_the_unit_on_a_well_formed_question_else_the_wave_stops(tmp_path, capsys):
    from autonomous_loop import cmd_record
    state = _hold_state(tmp_path)
    assert cmd_record(_Args(state, _esc())) == 0  # no wave STRICT-STOP
    row = json.loads(state.read_text(encoding="utf-8"))["units"][0]
    assert row["status"] == "held" and row["result_path"].endswith("result.json")
    for broken in ({**_esc(), "reason_code": "architecture_review_rejected"}, _esc(ac_questions=[]), _esc(ac_questions=[{"item": 0, "question": "q"}]),
                   {k: v for k, v in _esc().items() if k != "ac_questions"}):
        other = _hold_state(tmp_path)
        assert cmd_record(_Args(other, broken)) == 3
        assert json.loads(other.read_text(encoding="utf-8"))["units"][0]["status"] == "failed"
    capsys.readouterr()


@pytest.mark.covers("FR-01.11/AC49")
def test_integration_an_unattended_question_flows_from_the_tool_to_a_held_unit_and_the_wave_goes_on(tmp_path, capsys):
    """Real scenario: the CLI asks in a campaign run, its escalation is recorded for unit Q1 (held, exit 0), a second unit still completes."""
    from autonomous_loop import cmd_record
    from tools import ac_decision as cli
    root = _repo(tmp_path)
    ask = tmp_path / "ask.json"
    ask.write_text(json.dumps({"items": [{"kind": "add", "new_text": "A saved draft survives a restart"}]}), encoding="utf-8")
    assert cli.main(["--project-root", str(root), "--from-json", str(ask), "--base-ref", "HEAD", "--autonomous", "--sub-iterate-id", "Q1", "--run-id", "r1", "--bind-id", "camp--Q1"]) == 10
    escalation = json.loads(capsys.readouterr().out)["escalation"]
    state = _hold_state(tmp_path, ("Q1", "Q2"))
    assert cmd_record(_Args(state, escalation)) == 0
    assert cmd_record(_Args(state, {"status": "complete", "commit": "abc", "tests_passed": 1, "tests_total": 1, "branch": "b2"}, "Q2")) == 0
    rows = {u["id"]: u["status"] for u in json.loads(state.read_text(encoding="utf-8"))["units"]}
    assert rows == {"Q1": "held", "Q2": "built"}
    capsys.readouterr()
