"""The pre-build AC decision (Q1): the one ask rule, outcome wording, base-ref catalog, answers by the operator channel, counts, CLI.

Most tests call the functions in-process (diff coverage sees them); a few run the CLI as a subprocess.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from lib import ac_decision as ad
from lib import ac_hold
from lib import ac_wording as aw
from tools import ac_decision as cli

_ROOT = Path(__file__).resolve().parents[2]
_CLI = _ROOT / "shared" / "scripts" / "tools" / "ac_decision.py"
_OUTCOME = "A person who loses a connection sees a clear message instead of a blank page"
_OLD = "Given a draft, when saved, then it is kept."
_CAT = {"acs": {"FR-01.03.AC05": "- (E) [AC05] " + _OLD}, "frs": {"FR-01.03", "FR-01.04"}}


@pytest.fixture(autouse=True)
def _attended(monkeypatch):
    """These tests run inside campaign units too: start from an attended session unless a test says otherwise."""
    for name in ("SHIPWRIGHT_LOOP_ID", "SHIPWRIGHT_LOOP_UNIT_ID", ac_hold.OPERATOR_ENV):
        monkeypatch.delenv(name, raising=False)


def _add(**kw) -> dict:
    return {"kind": "add", "owner_fr": "FR-01.03", "new_text": _OUTCOME, **kw}


def _change(**kw) -> dict:
    return {"kind": "change", "ac": "FR-01.03.AC05", "old_text": _OLD, "new_text": "A saved draft is kept for 30 days", **kw}


def _ask(item: dict, run_id: str = "", n: int = 0) -> dict:
    return ad.decide([item], _CAT, run_id=run_id)["questions"][0]


# --- wording: a hard validation, both directions -------------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("text,needle", [
    ("Saved under shared/scripts/x.py", "file path"), ("It lives in plugins/shipwright-iterate", "file path"),
    ("reads config.json first", "file name"), ("uses the write_plan_stub helper", "snake_case"),
    ("pass --force to skip", "flag"), ("see ADR-045", "ADR/AC/FR number"), ("covers FR-01.11.AC49", "ADR/AC/FR number"),
    ("owned by FR-01.11", "ADR/AC/FR number"), ("calls `decide` first", "backticked"), ("the MAX_RETRY_COUNT limit", "UPPER_SNAKE"),
    ("the planStub value", "camelCase"), ("the PlanStub value", "camelCase"),
])
def test_wording_refuses_code_shapes(text, needle):
    assert any(needle in v for v in aw.wording_violations(text))


@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("text", [
    _OUTCOME, "Run `/shipwright-plan` to start planning", "Run /shipwright-iterate to start", "Works end-to-end without manual steps",
    "Use this and/or that", "Read/write access is kept", "Files from GitHub show up in CI", "The API answers within a second",
    "The WebUI shows CodeQL results from PostgreSQL", "It runs on Node.js and Next.js", "Check the input/output and the error text", "", None, 42,
])
def test_wording_passes_plain_prose(text):
    assert aw.wording_violations(text) == []


@pytest.mark.covers("FR-01.11/AC49")
def test_wording_refuses_a_name_taken_from_the_changed_code():
    changes = {"shared/scripts/lib/plan_writer.py": {"added": ["def render_stub(x):", "LIMIT_SIZE = 3", "p.add_argument('--keep-all')"], "removed": []}}
    idents = aw.diff_identifiers(changes)
    assert {"render_stub", "LIMIT_SIZE", "--keep-all", "plan_writer"} <= idents
    assert aw.wording_violations("the plan_writer keeps the draft", idents)
    assert aw.wording_violations("the draft is kept", idents) == []


@pytest.mark.covers("FR-01.11/AC49")
def test_wording_covers_every_text_field_and_types_are_checked():
    r = ad.decide([{"kind": "restore", "restores_ac": "FR-01.03.AC05", "new_text": "Writes to shared/scripts/x.py"}], _CAT)
    assert r["status"] == "invalid" and "outcome" in r["errors"][0]
    for field, value in (("new_text", 5), ("old_text", ["x"]), ("owner_fr", ["FR-01.03", "FR-01.04"]), ("ac", 7)):
        r = ad.decide([_add(**{field: value})], _CAT)
        assert r["status"] == "invalid" and "must be text" in r["errors"][0]
    assert ad.decide([_add(new_text="Writes to shared/scripts/x.py")], _CAT)["status"] == "invalid"


# --- the one ask rule ------------------------------------------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_a_new_ac_with_one_owner_is_decided_alone_and_records_how():
    r = ad.decide([_add(new_text="A saved draft is kept for 30 days", request_open=True)], _CAT)
    assert r["status"] == "ok"
    assert r["ac_decisions"] == [{"ac": "FR-01.03.new", "mode": "auto", "answer": "auto", "kind": "add", "answered_via": "none"}]


@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("item,row", [(_change(), 1), ({"kind": "remove", "ac": "FR-01.03.AC05", "old_text": _OLD}, 1),
                                      ({"kind": "add", "new_text": _OUTCOME}, 2), (_add(owner_fr="FR-09.99"), 2),
                                      (_add(owner_fr=None, new_fr={"id": "FR-01.30", "title": "Offline drafts"}), 3)])
def test_ask_when_an_ac_changes_has_no_single_owner_or_opens_a_new_area(item, row):
    r = ad.decide([item], _CAT)
    assert r["status"] == "ask" and [q["row"] for q in r["questions"]] == [row]
    q = r["questions"][0]
    assert q["question_sha256"] == ad.question_sha(q["question"], "", 0)


@pytest.mark.covers("FR-01.11/AC49")
def test_a_new_area_is_asked_once_and_can_be_approved_or_refused():
    item = _add(owner_fr=None, new_fr={"id": "FR-01.30", "title": "Offline drafts"})
    q = _ask(item)
    assert "new area of the product: Offline drafts" in q["question"]
    yes = ad.decide([item], _CAT, answers=[{"item": 0, "question_sha256": q["question_sha256"], "choice": "yes"}])
    assert yes["status"] == "ok" and yes["resolved_items"][0]["owner_fr"] == "FR-01.30" and yes["ac_decisions"][0]["ac"] == "FR-01.30.new"
    no = ad.decide([item], _CAT, answers=[{"item": 0, "question_sha256": q["question_sha256"], "choice": "no"}])
    assert no["status"] == "invalid" and "did not approve" in no["errors"][0]
    for bad in ({"id": "FR-01.03", "title": "x"}, {"id": "nope", "title": "x"}, {"id": "FR-01.30", "title": ""}, "x", {"id": "FR-01.30", "title": "uses plan_writer"}):
        assert ad.decide([_add(owner_fr=None, new_fr=bad)], _CAT)["status"] == "invalid"
    assert ad.decide([_add(new_fr={"id": "FR-01.30", "title": "Offline drafts"})], _CAT)["status"] == "invalid"  # owner AND new area
    assert ad.decide([{**_change(), "new_fr": {"id": "FR-01.30", "title": "x"}}], _CAT)["status"] == "invalid"


@pytest.mark.covers("FR-01.11/AC49")
def test_restore_must_name_an_ac_in_the_catalog_and_checks_types():
    assert ad.decide([{"kind": "restore", "restores_ac": "FR-01.03.AC05"}], _CAT)["status"] == "ok"
    bad = ad.decide([{"kind": "restore", "restores_ac": "FR-01.03.AC99"}], _CAT)
    assert bad["status"] == "invalid" and "catalog gap" in bad["errors"][0]
    assert ad.decide([{"kind": "restore"}], _CAT)["status"] == "invalid"
    assert "copy it exactly" in ad.decide([_change(old_text="something else")], _CAT)["errors"][0]
    for junk in ([{"kind": "bogus"}], [_change(ac="nonsense")], [{"kind": "add"}], [], "x", ["not a dict"]):
        assert ad.decide(junk, _CAT)["status"] == "invalid"


@pytest.mark.covers("FR-01.11/AC49")
def test_exemption_is_refused_when_a_diff_exists_and_is_observable_else_only_a_claim():
    assert ad.decide([{"kind": "exempt"}], _CAT, surface={"observable": False, "files": []})["ac_decisions"][0]["outcome"] == "no-observable-change"
    r = ad.decide([{"kind": "exempt"}], _CAT, surface={"observable": True, "files": ["shared/scripts/x.py"]})
    assert r["status"] == "invalid" and "shared/scripts/x.py" in r["errors"][0]


# --- the catalog is the base ref's, not the working tree's ------------------------------------------

def _tree(root: Path) -> None:
    spec = root / ".shipwright/planning/01-adopted/spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("### FR-01.03 - Drafts\n\n- (E) [AC05] " + _OLD + "\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"], check=True)


@pytest.mark.covers("FR-01.11/AC49")
def test_the_catalog_comes_from_the_base_ref_not_the_working_tree(tmp_path):
    _tree(tmp_path)
    spec = tmp_path / ".shipwright/planning/01-adopted/spec.md"
    spec.write_text(spec.read_text(encoding="utf-8") + "- (E) [AC06] A claim made true by editing the catalog first.\n", encoding="utf-8")
    assert "FR-01.03.AC06" in ad.load_catalog(tmp_path)["acs"]  # working tree
    base = ad.load_catalog(tmp_path, "HEAD")
    assert "FR-01.03.AC06" not in base["acs"] and base["frs"] == {"FR-01.03"}
    assert ad.decide([{"kind": "restore", "restores_ac": "FR-01.03.AC06"}], base)["status"] == "invalid"
    with pytest.raises(RuntimeError):
        ad.load_catalog(tmp_path, "no-such-ref")


@pytest.mark.covers("FR-01.11/AC49")
def test_catalog_loading_reads_acs_and_frs(tmp_path):
    spec = tmp_path / ".shipwright/planning/01-adopted/spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("## Group\n### FR-01.03 - Drafts\n\n- (E) [AC05] Given a draft, when saved, then kept.\n  continues here (iterate-x)\n### FR-01.04 - Empty\n", encoding="utf-8")
    cat = ad.load_catalog(tmp_path)
    assert cat["frs"] == {"FR-01.03", "FR-01.04"} and "continues here" in cat["acs"]["FR-01.03.AC05"]
    assert ad.ac_body(cat["acs"]["FR-01.03.AC05"]).endswith("continues here")
    assert ad.load_catalog(tmp_path / "nope") == {"acs": {}, "frs": set()}


# --- answers: only through the operator channel, bound to run + item + question text ----------------

@pytest.mark.covers("FR-01.11/AC49")
def test_a_bound_answer_closes_the_question_and_keeps_the_owner_on_no():
    q = _ask(_change())
    yes = ad.decide([_change()], _CAT, answers=[{"item": 0, "question_sha256": q["question_sha256"], "choice": "yes"}])
    assert yes["status"] == "ok" and yes["ac_decisions"][0]["mode"] == "asked" and yes["counts"]["asked"] == 1
    assert yes["ac_decisions"][0]["answered_via"] == "answer-file"
    item = {"kind": "add", "owner_fr": "FR-09.99", "new_text": _OUTCOME}
    sha = _ask(item)["question_sha256"]
    no = ad.decide([item], _CAT, answers=[{"item": 0, "question_sha256": sha, "choice": "no", "text": "Drafts are kept"}])
    assert no["resolved_items"][0]["new_text"] == "Drafts are kept" and no["resolved_items"][0]["owner_fr"] == "FR-09.99"


@pytest.mark.covers("FR-01.11/AC49")
def test_the_answer_is_bound_to_run_item_and_wording():
    sha = _ask(_change(), run_id="run-a")["question_sha256"]
    ok = ad.decide([_change()], _CAT, answers=[{"item": 0, "question_sha256": sha, "choice": "yes"}], run_id="run-a")
    assert ok["status"] == "ok"
    for kwargs in ({"run_id": "run-b"}, {"run_id": "run-a", "items": [_add(), _change()], "item": 1}):
        items = kwargs.get("items", [_change()])
        r = ad.decide(items, _CAT, answers=[{"item": kwargs.get("item", 0), "question_sha256": sha, "choice": "yes"}], run_id=kwargs["run_id"])
        assert r["status"] == "invalid" and "different question" in r["errors"][0]
    other = ad.decide([_change(new_text="A saved draft is kept for 60 days")], _CAT, answers=[{"item": 0, "question_sha256": sha, "choice": "yes"}], run_id="run-a")
    assert other["status"] == "invalid"


@pytest.mark.covers("FR-01.11/AC49")
def test_unattended_runs_refuse_inline_answers_and_unmarked_answer_files(monkeypatch):
    item = {**_change(), "answer": {"choice": "yes"}}
    r = ad.decide([item], _CAT, unattended=True)
    assert r["status"] == "invalid" and "inline answer is refused" in r["errors"][0]
    inline = ad.decide([item], _CAT, unattended=False)
    assert inline["status"] == "ok" and inline["ac_decisions"][0]["answered_via"] == "inline"
    sha = _ask(_change(), "r")["question_sha256"]
    filed = ad.decide([_change()], _CAT, unattended=True, run_id="r", answers=[{"item": 0, "question_sha256": sha, "choice": "yes"}])
    assert filed["status"] == "invalid" and "operator channel" in filed["errors"][0]
    op = ad.decide([_change()], _CAT, unattended=True, run_id="r", answers=[{"item": 0, "question_sha256": sha, "choice": "yes", "via": "operator"}])
    assert op["status"] == "ok" and op["ac_decisions"][0]["answered_via"] == "operator"


@pytest.mark.covers("FR-01.11/AC49")
def test_unattended_is_read_from_state_the_agent_does_not_type(monkeypatch, tmp_path):
    assert ac_hold.is_unattended(tmp_path) is False
    monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "loop-1")
    assert ac_hold.is_unattended(tmp_path) is True
    monkeypatch.delenv("SHIPWRIGHT_LOOP_ID")
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "Q1")
    assert ac_hold.is_unattended("") is True
    monkeypatch.delenv("SHIPWRIGHT_LOOP_UNIT_ID")
    wt = tmp_path / "campaign-demo--Q1"
    wt.mkdir()
    assert ac_hold.is_unattended(wt) is True and ac_hold.is_unattended("") is False
    assert ac_hold.operator_channel_open() is False
    monkeypatch.setenv(ac_hold.OPERATOR_ENV, "1")
    assert ac_hold.operator_channel_open() is True


@pytest.mark.covers("FR-01.11/AC49")
def test_the_hold_needs_a_well_formed_escalation():
    sha = "sha256:" + "a" * 64
    good = {"status": "escalated", "reason_code": ac_hold.AC_HOLD_REASON, "ac_questions": [{"item": 0, "question_sha256": sha}]}
    assert ac_hold.is_ac_hold(good)
    for broken in ({**good, "ac_questions": []}, {**good, "ac_questions": "x"}, {**good, "ac_questions": [{"item": 0}]}, {**good, "ac_questions": [{"question_sha256": "sha256:zz"}]},
                   {**good, "ac_questions": ["x"]}, {k: v for k, v in good.items() if k != "ac_questions"}, {**good, "reason_code": "other"}, {**good, "status": "failed"}, "x"):
        assert not ac_hold.is_ac_hold(broken)


# --- counts, stub lines ------------------------------------------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_one_counting_producer_has_exempt_restore_and_auto_buckets():
    d = [{"mode": "auto", "kind": "exempt"}, {"mode": "auto", "kind": "add"}, {"mode": "asked", "kind": "change"}, {"mode": "auto", "kind": "restore"}, {"mode": "auto", "kind": "exempt"}]
    assert ad.count_decisions(d) == {"total": 5, "auto": 1, "asked": 1, "exempt": 2, "restore": 1, "exempt_share": 0.4, "restore_share": 0.2}
    empty = {"total": 0, "auto": 0, "asked": 0, "exempt": 0, "restore": 0, "exempt_share": 0.0, "restore_share": 0.0}
    assert ad.count_decisions("junk") == ad.count_decisions(None) == empty
    assert ad.count_decisions([1, "x", {}])["total"] == 1


@pytest.mark.covers("FR-01.11/AC49")
def test_stub_lines_carry_items_decisions_and_a_new_area():
    r = ad.decide([_add()], _CAT)
    lines = ad.stub_lines(r)
    assert lines[0].startswith("AC item: ") and lines[1].startswith("AC decisions: ") and r["counts"]["total"] == 1
    fr = ad.frozen_fields(_add(owner_fr=None, new_fr={"id": "FR-01.30", "title": "Offline drafts"}))
    assert fr["new_fr"] == {"id": "FR-01.30", "title": "Offline drafts"}


# --- CLI: in-process (main) and as a subprocess -----------------------------------------------------

def _call(tmp: Path, payload: dict, capsys, *extra: str) -> tuple[int, dict]:
    f = tmp.parent / f"{tmp.name}-ac.json"  # outside the repo: an untracked json inside it would itself be an observable change
    f.write_text(json.dumps(payload), encoding="utf-8")
    code = cli.main(["--project-root", str(tmp), "--from-json", str(f), "--base-ref", "HEAD", *extra])
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip() else {}


@pytest.mark.covers("FR-01.11/AC49")
def test_cli_exit_codes_and_the_unit_hold_escalation(tmp_path, capsys):
    _tree(tmp_path)
    code, out = _call(tmp_path, {"items": [_add()]}, capsys)
    assert code == 0 and "claim only" in out["exemption_check"]
    code, out = _call(tmp_path, {"items": [{"kind": "add", "new_text": _OUTCOME}]}, capsys, "--autonomous", "--sub-iterate-id", "Q1", "--run-id", "r1")
    assert code == 10
    esc = out["escalation"]
    assert esc["sub_iterate_id"] == "Q1" and esc["reason_code"] == "ac_question_requires_operator" and ac_hold.is_ac_hold(esc)
    assert _call(tmp_path, {"items": [_add(new_text="Writes to shared/scripts/x.py")]}, capsys)[0] == 2
    capsys.readouterr()
    assert cli.main(["--project-root", str(tmp_path), "--from-json", str(tmp_path.parent / f"{tmp_path.name}-ac.json"), "--autonomous"]) == 2  # no --sub-iterate-id
    assert "--sub-iterate-id" in capsys.readouterr().err


@pytest.mark.covers("FR-01.11/AC49")
def test_cli_reads_the_campaign_environment_not_only_the_flag(tmp_path, capsys, monkeypatch):
    _tree(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "loop-1")
    code, out = _call(tmp_path, {"items": [{"kind": "add", "new_text": _OUTCOME}]}, capsys, "--sub-iterate-id", "Q1", "--run-id", "r1")
    assert code == 10 and out["unattended"] is True and out["escalation"]["sub_iterate_id"] == "Q1"
    assert _call(tmp_path, {"items": [_add()]}, capsys)[0] == 2  # unattended without the unit id


@pytest.mark.covers("FR-01.11/AC49")
def test_cli_never_prints_a_traceback_for_bad_input(tmp_path, capsys):
    _tree(tmp_path)
    bad = tmp_path.parent / f"{tmp_path.name}-bad.json"
    bad.write_text("{not json", encoding="utf-8")
    base = ["--project-root", str(tmp_path), "--base-ref", "HEAD"]
    assert cli.main([*base, "--from-json", str(bad)]) == 2
    assert cli.main([*base, "--from-json", str(tmp_path / "missing.json")]) == 2
    arr = tmp_path.parent / f"{tmp_path.name}-arr.json"
    arr.write_text("[1]", encoding="utf-8")
    assert cli.main([*base, "--from-json", str(arr)]) == 2
    assert cli.main(["--project-root", str(tmp_path), "--base-ref", "no-such-ref", "--from-json", str(arr)]) == 2
    ok = tmp_path.parent / f"{tmp_path.name}-ok.json"
    ok.write_text(json.dumps({"items": [_add()]}), encoding="utf-8")
    assert cli.main([*base, "--from-json", str(ok), "--answers", str(bad), "--run-id", "r"]) == 2
    assert cli.main(["answer", "--decided", str(bad), "--item", "0", "--choice", "yes", "--answers", str(tmp_path / "a.json")]) == 2
    assert cli.main(["answer", "--decided", str(ok), "--item", "0", "--choice", "yes", "--answers", str(tmp_path / "a.json")]) == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err and err.count('"error"') >= 6


@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16", "utf-8"])
def test_text_files_are_read_with_or_without_a_byte_order_mark(tmp_path, encoding):
    f = tmp_path / "w.txt"
    f.write_bytes('{"items": "Nutzer sehen eine klare Meldung – schön"}'.encode(encoding))
    assert "schön" in cli.read_text(str(f))
    with pytest.raises(cli._Fail):
        cli.read_text(str(tmp_path / "missing.txt"))
    (tmp_path / "bad.txt").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(cli._Fail):
        cli.read_text(str(tmp_path / "bad.txt"))


@pytest.mark.covers("FR-01.11/AC49")
def test_the_answer_subcommand_is_an_operator_channel_that_works_from_a_held_result(tmp_path, capsys, monkeypatch):
    _tree(tmp_path)
    payload = {"items": [{"kind": "add", "new_text": _OUTCOME}]}
    code, _ = _call(tmp_path, payload, capsys, "--autonomous", "--sub-iterate-id", "Q1", "--run-id", "r1", "--out", str(tmp_path / "decided.json"))
    assert code == 10
    held = tmp_path / "result.json"  # what the held unit wrote
    held.write_text(json.dumps(json.loads((tmp_path / "decided.json").read_text(encoding="utf-8"))["escalation"]), encoding="utf-8")
    wording = tmp_path / "w.txt"
    wording.write_text("FR-01.03\n", encoding="utf-8")
    answers = tmp_path / "answers.json"
    argv = ["answer", "--decided", str(held), "--item", "0", "--choice", "yes", "--text-file", str(wording), "--answers", str(answers)]
    monkeypatch.setattr(ac_hold, "is_unattended", lambda *_a, **_k: True)  # the agent's own session
    monkeypatch.setattr(cli, "is_unattended", ac_hold.is_unattended)
    assert cli.main(argv) == 2 and "unattended" in capsys.readouterr().err
    monkeypatch.setenv(ac_hold.OPERATOR_ENV, "1")  # the operator side
    assert cli.main(argv) == 0
    capsys.readouterr()
    assert json.loads(answers.read_text(encoding="utf-8"))["answers"][0]["via"] == "operator"
    code, out = _call(tmp_path, payload, capsys, "--answers", str(answers), "--autonomous", "--sub-iterate-id", "Q1", "--run-id", "r1")
    assert code == 0 and out["resolved_items"][0]["owner_fr"] == "FR-01.03" and out["ac_decisions"][0]["answered_via"] == "operator"
    code, out = _call(tmp_path, payload, capsys, "--answers", str(answers), "--autonomous", "--sub-iterate-id", "Q1", "--run-id", "OTHER")
    assert code == 2 and "different question" in out["errors"][0]
    assert cli.main(["answer", "--decided", str(held), "--item", "5", "--choice", "yes", "--answers", str(answers)]) == 2


@pytest.mark.covers("FR-01.11/AC49")
def test_exempt_is_a_claim_before_the_build_and_checked_once_a_diff_exists(tmp_path, capsys):
    _tree(tmp_path)
    assert _call(tmp_path, {"items": [{"kind": "exempt"}]}, capsys)[0] == 0
    (tmp_path / "tool.py").write_text("print('hi')\n", encoding="utf-8")
    code, out = _call(tmp_path, {"items": [{"kind": "exempt"}]}, capsys)
    assert code == 2 and out["surface"]["files"] == ["tool.py"] and out["exemption_check"] == "tested against the current diff"


@pytest.mark.covers("FR-01.11/AC49")
def test_verify_subcommand_reports_the_finalize_compare(tmp_path, capsys):
    _tree(tmp_path)
    assert cli.main(["verify", "--project-root", str(tmp_path), "--run-id", "r", "--base-ref", "HEAD"]) == 0
    assert json.loads(capsys.readouterr().out) == {"problems": []}
    (tmp_path / "tool.py").write_text("print('hi')\n", encoding="utf-8")
    cli.main(["verify", "--project-root", str(tmp_path), "--run-id", "r", "--base-ref", "HEAD"])
    assert "no AC record exists" in json.loads(capsys.readouterr().out)["problems"][0]
    assert cli.main(["verify", "--project-root", str(tmp_path), "--run-id", "r", "--base-ref", "no-such-ref"]) == 2


@pytest.mark.covers("FR-01.11/AC49")
def test_cli_prints_non_ascii_without_crashing_and_keeps_the_exit_codes(tmp_path):
    _tree(tmp_path)
    f = tmp_path.parent / f"{tmp_path.name}-na.json"
    f.write_text(json.dumps({"items": [_add(new_text="Nutzer sehen eine klare Meldung – schön und verständlich")]}, ensure_ascii=False), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("SHIPWRIGHT_")} | {"PYTHONIOENCODING": "cp1252"}
    p = subprocess.run([sys.executable, str(_CLI), "--project-root", str(tmp_path), "--from-json", str(f), "--base-ref", "HEAD"],
                       capture_output=True, check=False, env=env)
    assert p.returncode in (0, 10, 2) and p.returncode == 0
    assert "verständlich" in p.stdout.decode("utf-8")
