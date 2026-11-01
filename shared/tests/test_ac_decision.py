"""The pre-build AC decision (Q1): the one ask rule, outcome wording, answers by the operator channel, counts, CLI.

Most tests call the functions in-process (diff coverage sees them); a few run the CLI as a subprocess.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib import ac_decision as ad
from lib import ac_wording as aw
from tools import ac_decision as cli

_ROOT = Path(__file__).resolve().parents[2]
_CLI = _ROOT / "shared" / "scripts" / "tools" / "ac_decision.py"
_OUTCOME = "A person who loses a connection sees a clear message instead of a blank page"
_CAT = {"acs": {"FR-01.03.AC05": "- (E) [AC05] Given a draft, when saved, then it is kept."}, "frs": {"FR-01.03", "FR-01.04"}}


def _add(**kw) -> dict:
    return {"kind": "add", "owner_fr": "FR-01.03", "new_text": _OUTCOME, **kw}


def _change(**kw) -> dict:
    return {"kind": "change", "ac": "FR-01.03.AC05", "old_text": "Given a draft, when saved, then it is kept.", "new_text": "A saved draft is kept for 30 days", **kw}


# --- wording: a hard validation, both directions -------------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("text,needle", [
    ("Saved under shared/scripts/x.py", "file path"), ("It lives in plugins/shipwright-iterate", "file path"),
    ("reads config.json first", "file name"), ("uses the write_plan_stub helper", "snake_case"),
    ("pass --force to skip", "flag"), ("see ADR-045", "ADR/AC/FR number"), ("covers FR-01.11.AC49", "ADR/AC/FR number"),
    ("calls `decide` first", "backticked"), ("the MAX_RETRY_COUNT limit", "UPPER_SNAKE"), ("the planStub value", "camelCase"),
    ("the PlanStub value", "camelCase"),
])
def test_wording_refuses_code_shapes(text, needle):
    assert any(needle in v for v in aw.wording_violations(text))


@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("text", [
    _OUTCOME, "Run `/shipwright-plan` to start planning", "Works end-to-end without manual steps", "Use this and/or that", "Read/write access is kept",
    "Files from GitHub show up in CI", "The API answers within a second", "", None, 42,
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
def test_a_how_wording_is_invalid_not_a_question():
    r = ad.decide([_add(new_text="Writes to shared/scripts/x.py")], _CAT)
    assert r["status"] == "invalid" and "outcome" in r["errors"][0]


# --- the one ask rule ------------------------------------------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_a_new_ac_with_one_owner_is_decided_alone():
    r = ad.decide([_add()], _CAT)
    assert r["status"] == "ok" and r["ac_decisions"] == [{"ac": "FR-01.03.new", "mode": "auto", "answer": "auto", "kind": "add"}]


@pytest.mark.covers("FR-01.11/AC49")
def test_no_label_and_no_how_test_ever_asks():
    # a number with a unit, a long sentence, an open request: none of it is an ask trigger any more
    r = ad.decide([_add(new_text="A saved draft is kept for 30 days", request_open=True)], _CAT)
    assert r["status"] == "ok"


@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("item,row", [(_change(), 1), ({"kind": "remove", "ac": "FR-01.03.AC05", "old_text": "Given a draft, when saved, then it is kept."}, 1),
                                      ({"kind": "add", "new_text": _OUTCOME}, 2), (_add(owner_fr="FR-09.99"), 2),
                                      (_add(owner_fr=["FR-01.03", "FR-01.04"]), 2)])
def test_ask_when_an_ac_changes_or_has_no_single_owner(item, row):
    r = ad.decide([item], _CAT)
    assert r["status"] == "ask" and [q["row"] for q in r["questions"]] == [row]
    q = r["questions"][0]
    assert q["question_sha256"] == ad.question_sha(q["question"])


@pytest.mark.covers("FR-01.11/AC49")
def test_restore_must_name_an_ac_in_the_catalog():
    assert ad.decide([{"kind": "restore", "restores_ac": "FR-01.03.AC05"}], _CAT)["status"] == "ok"
    bad = ad.decide([{"kind": "restore", "restores_ac": "FR-01.03.AC99"}], _CAT)
    assert bad["status"] == "invalid" and "catalog gap" in bad["errors"][0]
    assert ad.decide([{"kind": "restore"}], _CAT)["status"] == "invalid"


@pytest.mark.covers("FR-01.11/AC49")
def test_old_text_must_match_the_catalog_and_kinds_are_checked():
    assert "copy it exactly" in ad.decide([_change(old_text="something else")], _CAT)["errors"][0]
    assert ad.decide([{"kind": "bogus"}], _CAT)["status"] == "invalid"
    assert ad.decide([_change(ac="nonsense")], _CAT)["status"] == "invalid"
    assert ad.decide([{"kind": "add"}], _CAT)["status"] == "invalid"
    assert ad.decide([], _CAT)["status"] == "invalid" and ad.decide("x", _CAT)["status"] == "invalid"
    assert ad.decide(["not a dict"], _CAT)["status"] == "invalid"


@pytest.mark.covers("FR-01.11/AC49")
def test_exemption_is_refused_when_the_diff_is_observable_and_free_when_it_is_not():
    assert ad.decide([{"kind": "exempt"}], _CAT, surface={"observable": False, "files": []})["ac_decisions"][0]["outcome"] == "no-observable-change"
    r = ad.decide([{"kind": "exempt"}], _CAT, surface={"observable": True, "files": ["shared/scripts/x.py"]})
    assert r["status"] == "invalid" and "shared/scripts/x.py" in r["errors"][0]


# --- answers: only through the operator channel, bound to the question text ------------------------

def _asked(item=None):
    r = ad.decide([item or _change()], _CAT)
    return r["questions"][0]


@pytest.mark.covers("FR-01.11/AC49")
def test_a_bound_answer_closes_the_question():
    q = _asked()
    yes = ad.decide([_change()], _CAT, answers=[{"item": 0, "question_sha256": q["question_sha256"], "choice": "yes"}])
    assert yes["status"] == "ok" and yes["ac_decisions"][0]["mode"] == "asked" and yes["counts"]["asked"] == 1
    no = ad.decide([_change()], _CAT, answers=[{"item": 0, "question_sha256": q["question_sha256"], "choice": "no", "text": "Drafts are kept"}])
    assert no["resolved_items"][0]["new_text"] == "Drafts are kept"


@pytest.mark.covers("FR-01.11/AC49")
def test_an_answer_for_other_question_text_is_refused():
    r = ad.decide([_change(new_text="A saved draft is kept for 60 days")], _CAT,
                  answers=[{"item": 0, "question_sha256": _asked()["question_sha256"], "choice": "yes"}])
    assert r["status"] == "invalid" and "different question text" in r["errors"][0]


@pytest.mark.covers("FR-01.11/AC49")
def test_inline_answers_are_refused_under_autonomous_and_allowed_interactively():
    item = {**_change(), "answer": {"choice": "yes"}}
    r = ad.decide([item], _CAT, autonomous=True)
    assert r["status"] == "invalid" and "refused under --autonomous" in r["errors"][0]
    assert ad.decide([item], _CAT, autonomous=False)["status"] == "ok"


@pytest.mark.covers("FR-01.11/AC49")
def test_answers_are_validated():
    sha = _asked()["question_sha256"]
    def run(choice, text="", item=None):
        q = _asked(item)["question_sha256"] if item else sha
        return ad.decide([item or _change()], _CAT, answers=[{"item": 0, "question_sha256": q, "choice": choice, "text": text}])
    assert run("maybe")["status"] == "invalid"
    assert "needs the operator's wording" in run("no")["errors"][0]
    rm = {"kind": "remove", "ac": "FR-01.03.AC05", "old_text": "Given a draft, when saved, then it is kept."}
    assert "kept" in run("no", "x", rm)["errors"][0]
    assert run("yes", "", rm)["status"] == "ok"
    ownerless = {"kind": "add", "new_text": _OUTCOME}
    assert "owning feature" in run("yes", "", ownerless)["errors"][0]
    assert run("yes", "FR-01.04", ownerless)["resolved_items"][0]["owner_fr"] == "FR-01.04"
    assert run("no", "Ships with code in `x`")["status"] == "invalid"  # the operator's wording gets the wording check too


# --- counts, stub lines ------------------------------------------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_one_counting_producer_makes_the_exempt_share_visible():
    d = [{"mode": "auto", "kind": "exempt"}, {"mode": "auto", "kind": "add"}, {"mode": "asked", "kind": "change"}, {"mode": "auto", "kind": "exempt"}]
    assert ad.count_decisions(d) == {"total": 4, "auto": 3, "asked": 1, "exempt": 2, "exempt_share": 0.5}
    assert ad.count_decisions("junk") == ad.count_decisions(None) == {"total": 0, "auto": 0, "asked": 0, "exempt": 0, "exempt_share": 0.0}
    assert ad.count_decisions([1, "x", {}])["total"] == 1


@pytest.mark.covers("FR-01.11/AC49")
def test_stub_lines_carry_items_and_decisions():
    r = ad.decide([_add()], _CAT)
    lines = ad.stub_lines(r)
    assert lines[0].startswith("AC item: ") and lines[1].startswith("AC decisions: ")
    assert r["counts"]["total"] == 1


@pytest.mark.covers("FR-01.11/AC49")
def test_catalog_loading_reads_acs_and_frs(tmp_path):
    spec = tmp_path / ".shipwright/planning/01-adopted/spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("## Group\n### FR-01.03 - Drafts\n\n- (E) [AC05] Given a draft, when saved, then kept.\n  continues here (iterate-x)\n### FR-01.04 - Empty\n", encoding="utf-8")
    cat = ad.load_catalog(tmp_path)
    assert cat["frs"] == {"FR-01.03", "FR-01.04"} and "continues here" in cat["acs"]["FR-01.03.AC05"]
    assert ad.ac_body(cat["acs"]["FR-01.03.AC05"]).endswith("continues here")
    assert ad.load_catalog(tmp_path / "nope") == {"acs": {}, "frs": set()}


# --- CLI: in-process (main) and as a subprocess -----------------------------------------------------

def _tree(root: Path) -> None:
    spec = root / ".shipwright/planning/01-adopted/spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("### FR-01.03 - Drafts\n\n- (E) [AC05] Given a draft, when saved, then it is kept.\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"], check=True)


def _call(tmp: Path, payload: dict, capsys, *extra: str) -> tuple[int, dict]:
    f = tmp.parent / f"{tmp.name}-ac.json"  # outside the repo: an untracked json inside it would itself be an observable change
    f.write_text(json.dumps(payload), encoding="utf-8")
    code = cli.main(["--project-root", str(tmp), "--from-json", str(f), "--base-ref", "HEAD", *extra])
    out = capsys.readouterr().out
    return code, json.loads(out)


@pytest.mark.covers("FR-01.11/AC49")
def test_cli_exit_codes_and_the_unit_hold_escalation(tmp_path, capsys):
    _tree(tmp_path)
    assert _call(tmp_path, {"items": [_add()]}, capsys)[0] == 0
    code, out = _call(tmp_path, {"items": [{"kind": "add", "new_text": _OUTCOME}]}, capsys, "--autonomous", "--sub-iterate-id", "Q1")
    assert code == 10
    esc = out["escalation"]
    assert esc["sub_iterate_id"] == "Q1" and esc["reason_code"] == "ac_question_requires_operator" and esc["ac_questions"][0]["question_sha256"].startswith("sha256:")
    assert _call(tmp_path, {"items": [_add(new_text="Writes to shared/scripts/x.py")]}, capsys)[0] == 2
    with pytest.raises(SystemExit):
        cli.main(["--project-root", str(tmp_path), "--from-json", str(tmp_path.parent / f"{tmp_path.name}-ac.json"), "--autonomous"])  # no --sub-iterate-id


@pytest.mark.covers("FR-01.11/AC49")
def test_exempt_is_checked_against_the_real_working_tree(tmp_path, capsys):
    _tree(tmp_path)
    assert _call(tmp_path, {"items": [{"kind": "exempt"}]}, capsys)[0] == 0
    (tmp_path / "tool.py").write_text("print('hi')\n", encoding="utf-8")
    code, out = _call(tmp_path, {"items": [{"kind": "exempt"}]}, capsys)
    assert code == 2 and out["surface"]["files"] == ["tool.py"]


@pytest.mark.covers("FR-01.11/AC49")
def test_the_answer_subcommand_binds_the_answer_and_the_run_accepts_it(tmp_path, capsys):
    _tree(tmp_path)
    payload = {"items": [{"kind": "add", "new_text": _OUTCOME}]}
    code, _ = _call(tmp_path, payload, capsys, "--out", str(tmp_path / "decided.json"))
    assert code == 10
    wording = tmp_path / "w.txt"
    wording.write_text("FR-01.03\n", encoding="utf-8")
    answers = tmp_path / "answers.json"
    assert cli.main(["answer", "--decided", str(tmp_path / "decided.json"), "--item", "0", "--choice", "yes", "--text-file", str(wording), "--answers", str(answers)]) == 0
    capsys.readouterr()
    code, out = _call(tmp_path, payload, capsys, "--answers", str(answers), "--autonomous", "--sub-iterate-id", "Q1")
    assert code == 0 and out["resolved_items"][0]["owner_fr"] == "FR-01.03" and out["ac_decisions"][0]["mode"] == "asked"
    with pytest.raises(SystemExit):  # no open question for that item
        cli.main(["answer", "--decided", str(tmp_path / "decided.json"), "--item", "5", "--choice", "yes", "--answers", str(answers)])


@pytest.mark.covers("FR-01.11/AC49")
def test_cli_prints_non_ascii_without_crashing_and_keeps_the_exit_codes(tmp_path):
    _tree(tmp_path)
    f = tmp_path / "ac.json"
    f.write_text(json.dumps({"items": [_add(new_text="Nutzer sehen eine klare Meldung – schön und verständlich")]}, ensure_ascii=False), encoding="utf-8")
    env = {"PYTHONIOENCODING": "cp1252", "PATH": __import__("os").environ["PATH"], "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")}
    p = subprocess.run([sys.executable, str(_CLI), "--project-root", str(tmp_path), "--from-json", str(f), "--base-ref", "HEAD"],
                       capture_output=True, check=False, env=env)
    assert p.returncode in (0, 10, 2) and p.returncode == 0
    assert "verständlich" in p.stdout.decode("utf-8")
