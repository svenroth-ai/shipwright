"""The pre-build AC decision (Q1): answers bound to stable content, unattended state, the hold, counts and the CLI (the ask rule: test_ac_decision.py)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from shared.tests.ac_test_helpers import ans
from lib import ac_decision as ad
from lib import ac_hold
from tools import ac_decision as cli

_ROOT = Path(__file__).resolve().parents[2]
_CLI = _ROOT / "shared" / "scripts" / "tools" / "ac_decision.py"
_OUTCOME = "A person who loses a connection sees a clear message instead of a blank page"
_OLD = "Given a draft, when saved, then it is kept."
_CAT = {"acs": {"FR-01.03.AC05": "- (E) [AC05] " + _OLD}, "frs": {"FR-01.03", "FR-01.04"}, "titles": {"FR-01.03": "Saving drafts", "FR-01.04": "Sharing drafts"}, "unparsed": False}
_FITS = "A draft is kept for a year"  # shares words with an existing requirement, so the question names it


def _add(**kw) -> dict:
    return {"kind": "add", "owner_fr": "FR-01.03", "new_text": _OUTCOME, **kw}


def _change(**kw) -> dict:
    return {"kind": "change", "ac": "FR-01.03.AC05", "old_text": _OLD, "new_text": "A saved draft is kept for 30 days", **kw}


def _ask(item: dict, run_id: str = "") -> dict:
    return ad.decide([item], _CAT, bind_id=run_id)["questions"][0]


def _tree(root: Path) -> None:
    spec = root / ".shipwright/planning/01-adopted/spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("### FR-01.03 - Drafts\n\n- (E) [AC05] " + _OLD + "\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"], check=True)


# --- answers: only through the operator channel, bound to run + item + question text ----------------

@pytest.mark.covers("FR-01.11/AC49")
def test_a_bound_answer_closes_the_question_and_keeps_the_owner_on_no():
    q = _ask(_change())
    yes = ad.decide([_change()], _CAT, answers=[ans(q, "yes")])
    assert yes["status"] == "ok" and yes["ac_decisions"][0]["mode"] == "asked" and yes["counts"]["asked"] == 1
    assert yes["ac_decisions"][0]["answered_via"] == "self-reported"  # an unsigned file answer is never "operator"
    item = {"kind": "add", "owner_fr": "FR-09.99", "new_text": _FITS}
    q0 = _ask(item)
    declined = ad.decide([item], _CAT, answers=[ans(q0, "no")])
    assert declined["status"] == "invalid" and "ask them in the chat" in declined["errors"][0]   # "No" hands the work back to the chat; nothing is reworded here
    chosen = ad.decide([item], _CAT, answers=[ans(q0, "yes", q0["options"]["1"]["text"])])
    assert chosen["status"] == "ok" and chosen["resolved_items"][0]["owner_fr"] == q0["options"]["1"]["text"] and chosen["resolved_items"][0]["new_text"] == _FITS
    owned = {"kind": "change", "ac": "FR-01.03.AC05", "old_text": _OLD, "new_text": "A saved draft is kept for 30 days", "owner_fr": "FR-01.03"}
    assert ad.decide([owned], _CAT, answers=[ans(_ask(owned), "no")])["status"] == "invalid"    # a changed promise the operator declines is not recorded


@pytest.mark.covers("FR-01.11/AC49")
def test_the_answer_is_bound_to_run_item_promise_and_options_not_to_the_rendered_text():
    q = _ask(_change(), run_id="run-a")
    ok = ad.decide([_change()], _CAT, answers=[ans(q, "yes")], bind_id="run-a")
    assert ok["status"] == "ok"
    for items, bind, item in (([_change()], "run-b", 0), ([_add(), _change()], "run-a", 1), ([_change(new_text="A saved draft is kept for 60 days")], "run-a", 0)):
        r = ad.decide(items, _CAT, answers=[{**ans(q, "yes"), "item": item}], bind_id=bind)
        assert r["status"] == "invalid" and "different question" in r["errors"][0]
    moved = {**_CAT, "titles": {**_CAT["titles"], "FR-01.05": "Brand new area"}, "frs": _CAT["frs"] | {"FR-01.05"}}  # the catalog moved: the rendered question would differ
    assert ad.decide([_change()], moved, answers=[ans(q, "yes")], bind_id="run-a")["status"] == "ok"


@pytest.mark.covers("FR-01.11/AC49")
def test_unattended_runs_refuse_inline_answers_and_unmarked_answer_files(monkeypatch):
    item = {**_change(), "answer": {"choice": "yes"}}
    r = ad.decide([item], _CAT, unattended=True)
    assert r["status"] == "invalid" and "inline answer is refused" in r["errors"][0]
    inline = ad.decide([item], _CAT, unattended=False)
    assert inline["status"] == "ok" and inline["ac_decisions"][0]["answered_via"] == "inline"
    q = _ask(_change(), "r")
    sha = q["question_sha256"]
    filed = ad.decide([_change()], _CAT, unattended=True, bind_id="r", answers=[ans(q, "yes")])
    assert filed["status"] == "invalid" and "operator channel" in filed["errors"][0]
    claimed = {**ans(q, "yes"), "via": "operator"}  # a "via" field proves nothing
    assert ad.decide([_change()], _CAT, unattended=True, bind_id="r", answers=[claimed])["status"] == "invalid"
    signed = {**claimed, "text": "", "signature": ac_hold.sign(ac_hold.load_key(create=True), sha, "yes", "")}
    op = ad.decide([_change()], _CAT, unattended=True, bind_id="r", answers=[signed])
    assert op["status"] == "ok" and op["ac_decisions"][0]["answered_via"] == "operator"
    forged = {**signed, "choice": "yes", "text": "tampered"}  # the signature covers question, choice and text
    assert ad.decide([_change()], _CAT, unattended=True, bind_id="r", answers=[forged])["status"] == "invalid"


@pytest.mark.covers("FR-01.11/AC49")
def test_unattended_is_read_from_state_the_agent_does_not_type(monkeypatch, tmp_path):
    assert ac_hold.is_unattended(tmp_path) is False
    monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "loop-1")
    assert ac_hold.is_unattended(tmp_path) is False  # one variable alone is not the loop
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "Q1")
    assert ac_hold.is_unattended("") is True
    monkeypatch.delenv("SHIPWRIGHT_LOOP_ID")
    monkeypatch.delenv("SHIPWRIGHT_LOOP_UNIT_ID")
    unit = tmp_path / ".worktrees" / "campaign-demo--Q1"
    orchestrator = tmp_path / ".worktrees" / "campaign-demo"
    lookalike = tmp_path / "campaign-demo--Q1"  # right name, wrong parent folder
    for d in (unit, orchestrator, lookalike):
        d.mkdir(parents=True)
    assert ac_hold.is_unattended(unit) is True and ac_hold.is_unattended("") is False
    assert ac_hold.is_unattended(orchestrator) is False and ac_hold.is_unattended(lookalike) is False  # the orchestrator's own worktree is attended
    dashed = tmp_path / ".worktrees" / "campaign-a--b"  # an orchestrator whose own slug contains "--": no sibling campaign-a, so not a unit
    dashed.mkdir()
    assert ac_hold.is_unattended(dashed) is False
    (tmp_path / ".worktrees" / "campaign-a").mkdir()
    assert ac_hold.is_unattended(dashed) is True  # split at the LAST "--": campaign-a with unit b
    assert ac_hold.operator_channel_open() is False
    monkeypatch.setenv(ac_hold.OPERATOR_ENV, "1")
    assert ac_hold.operator_channel_open() is True


@pytest.mark.covers("FR-01.11/AC49")
def test_the_hold_needs_a_well_formed_escalation():
    promise = {"old": "", "new": "A draft is kept", "title": ""}
    q = {"item": 0, "question": "Should it hold?", "kind": "add", "promise": promise, "options": {}, "question_sha256": ac_hold.question_sha("camp--Q1", 0, "add", promise, {})}
    good = {"status": "escalated", "reason_code": ac_hold.AC_HOLD_REASON, "bind_id": "camp--Q1", "ac_questions": [q]}
    assert ac_hold.is_ac_hold(good)
    assert ac_hold.is_ac_hold({**good, "ac_questions": [{**q, "question": "Other words, same content"}]})  # the rendered text is display only
    wrong = {**q, "question_sha256": "sha256:" + "a" * 64}  # well-formed, but not the hash of this question
    for broken in ({**good, "ac_questions": []}, {**good, "ac_questions": "x"}, {**good, "ac_questions": [{"item": 0}]}, {**good, "ac_questions": [wrong]},
                   {**good, "ac_questions": [{**q, "item": 1}]}, {**good, "ac_questions": [{**q, "promise": {**promise, "new": "other"}}]},
                   {**good, "ac_questions": [{**q, "options": {"A": {"choice": "yes", "text": "FR-01.03"}}}]}, {**good, "ac_questions": [{**q, "kind": "change"}]}, {**good, "bind_id": "x"},
                   {**good, "ac_questions": [{"question_sha256": "sha256:zz"}]}, {**good, "ac_questions": ["x"]},
                   {k: v for k, v in good.items() if k != "ac_questions"}, {**good, "reason_code": "other"}, {**good, "status": "failed"}, "x"):
        assert not ac_hold.is_ac_hold(broken)


# --- counts, stub lines ------------------------------------------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_one_counting_producer_has_exempt_restore_and_auto_buckets():
    d = [{"mode": "auto", "kind": "exempt"}, {"mode": "auto", "kind": "add"}, {"mode": "asked", "kind": "change"}, {"mode": "auto", "kind": "restore"}, {"mode": "auto", "kind": "exempt"}]
    assert ad.count_decisions(d) == {"total": 5, "auto": 1, "asked": 1, "exempt": 2, "restore": 1, "unchanged": 0, "answered_inline": 0, "unconfirmed": 0, "exempt_share": 0.4, "restore_share": 0.2}
    assert ad.count_decisions(d + [{"mode": "auto", "kind": "unchanged"}])["unchanged"] == 1
    empty = {"total": 0, "auto": 0, "asked": 0, "exempt": 0, "restore": 0, "unchanged": 0, "answered_inline": 0, "unconfirmed": 0, "exempt_share": 0.0, "restore_share": 0.0}
    assert ad.count_decisions("junk") == ad.count_decisions(None) == empty
    assert ad.count_decisions([1, "x", {}])["total"] == 1
    assert ad.count_decisions([{"mode": "asked", "kind": "change", "answered_via": "inline"}, {"mode": "asked", "kind": "change", "answered_via": "operator"}])["answered_inline"] == 1


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
    assert cli.main(["--project-root", str(tmp_path), "--from-json", str(tmp_path.parent / f"{tmp_path.name}-ac.json"), "--base-ref", "HEAD", "--autonomous"]) == 2  # no --sub-iterate-id
    assert "--sub-iterate-id" in capsys.readouterr().err


@pytest.mark.covers("FR-01.11/AC49")
def test_cli_reads_the_campaign_environment_not_only_the_flag(tmp_path, capsys, monkeypatch):
    _tree(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "loop-1")
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "Q1")
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
    capsys.readouterr()
    assert cli.main(["answer", "--decided", str(bad), "--item", "0", "--choice", "yes", "--answers", str(tmp_path / "a.json")]) == 2
    assert "is not valid JSON" in capsys.readouterr().err
    assert cli.main(["answer", "--decided", str(ok), "--item", "0", "--choice", "yes", "--answers", str(tmp_path / "a.json")]) == 2
    assert "holds no open question for item 0" in capsys.readouterr().err
    assert cli.main([*base, "--from-json", str(ok), "--run-id", "../../x"]) == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err and "plain run id" in err                                           # a path-like run id is refused before anything is written
    assert not (tmp_path.parent.parent / "x").exists()


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
    payload = {"items": [{"kind": "add", "new_text": _FITS}]}
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
    entry = json.loads(answers.read_text(encoding="utf-8"))["answers"][0]
    assert entry["via"] == "operator" and entry["signature"] == ac_hold.sign(ac_hold.load_key(), entry["question_sha256"], "yes", "FR-01.03")
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
    assert code == 2 and out["surface"]["files"] == ["tool.py"] and out["exemption_check"].startswith("tested against the current diff (1 file(s)")


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
