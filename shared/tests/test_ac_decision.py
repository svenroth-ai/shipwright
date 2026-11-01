"""The pre-build AC decision (Q1): lexical HOW test, the ask/auto table, validation, freezing, the stub record, the F11 warning."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib import ac_decision as ad
from lib import spec_chain as sc
from tools.verifiers import _finalization_claims as claims
from tools.verifiers.pre_build_ac_check import CHECK_NAME, check_pre_build_ac_recorded

_ROOT = Path(__file__).resolve().parents[2]
_RUN = "iterate-2026-11-01-q1-pre-build-ac"
_CATALOG = {"FR-01.03.AC05", "FR-01.03.AC06"}
_CLI = _ROOT / "shared" / "scripts" / "tools" / "ac_decision.py"
_STUB = _ROOT / "shared" / "scripts" / "tools" / "write_plan_stub.py"

_PLAIN = "A person who loses a connection sees a clear message instead of a blank page"


def _add(**kw) -> dict:
    return {"kind": "add", "owner_fr": "FR-01.03", "new_text": _PLAIN, **kw}


@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("text,shape", [
    ("Saved under shared/scripts/x.py", "path"), ("reads config.json first", "path"),
    ("uses the write_plan_stub helper", "snake_case"), ("pass --force to skip", "flag"), ("see ADR-045", "adr_number"),
    ("in iterate-2026-10-31-p3-spec-chain", "slug"), ("within 30 seconds", "number_with_unit"), ("under 5 %", "number_with_unit"),
    ("a GET request", "http_verb"),
])
def test_how_test_flags_each_shape(text, shape):
    assert shape in ad.how_hits(text)


@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("text", [
    _PLAIN, "Opening a saved draft shows the last version you edited", "Two people can edit at once without losing work",
    "Dates read 2026-10-31 style", "A well-known, user-friendly message appears", "The three best matches are listed first",
    "", None,
])
def test_how_test_passes_plain_outcome_sentences(text):
    assert ad.how_hits(text) == []


@pytest.mark.covers("FR-01.11/AC49")
def test_table_first_matching_row_wins():
    # row 1 (changed AC) beats rows 2-4 even when all would match
    r = ad.decide([{"kind": "change", "ac": "FR-01.03.AC05", "old_text": "old", "new_text": "uses a_b_c",
                    "plain_new": "x", "plain_old": "y", "request_open": True}], _CATALOG)
    assert r["status"] == "ask" and [q["row"] for q in r["questions"]] == [1]
    # row 2 (no single owner) beats rows 3-4
    r = ad.decide([{"kind": "add", "new_text": "uses a_b_c", "plain_new": _PLAIN, "request_open": True}], _CATALOG)
    assert [q["row"] for q in r["questions"]] == [2]
    # row 3 (HOW test) beats row 4
    r = ad.decide([_add(new_text="takes under 30 seconds", plain_new=_PLAIN, request_open=True)], _CATALOG)
    assert [q["row"] for q in r["questions"]] == [3]
    # row 4
    r = ad.decide([_add(request_open=True)], _CATALOG)
    assert [q["row"] for q in r["questions"]] == [4]
    # nothing matches: auto
    r = ad.decide([_add()], _CATALOG)
    assert r["status"] == "ok" and r["ac_decisions"] == [{"ac": "FR-01.03.new", "mode": "auto", "answer": "auto"}]


@pytest.mark.covers("FR-01.11/AC49")
def test_removal_variant_and_three_answers_in_the_question():
    r = ad.decide([{"kind": "remove", "ac": "FR-01.03.AC05", "old_text": "t", "plain_old": "Drafts are kept for a week"}], _CATALOG)
    q = r["questions"][0]["text"]
    assert "Until now this held: Drafts are kept for a week." in q and "After this change it no longer holds." in q
    assert "2 No, instead: <your wording>" in q and "3 This is only how it is built, not a promise." in q
    r = ad.decide([{"kind": "change", "ac": "FR-01.03.AC05", "old_text": "t", "new_text": "n", "plain_new": "Drafts are kept for a month",
                    "plain_old": "Drafts are kept for a week"}], _CATALOG)
    q = r["questions"][0]["text"]
    assert q.startswith("This change gives the product a new promise: Drafts are kept for a month. Until now: Drafts are kept for a week. Should it hold like this?")
    assert "1 Yes, write it." in q


@pytest.mark.covers("FR-01.11/AC49")
def test_question_sentence_must_be_plain():
    r = ad.decide([{"kind": "change", "ac": "FR-01.03.AC05", "old_text": "t", "new_text": "n", "plain_new": "Waits 30 seconds", "plain_old": "x"}], _CATALOG)
    assert r["status"] == "invalid" and "reword" in r["errors"][0]
    # a how-trippy AC text with no plain sentence cannot be put to the operator as is
    r = ad.decide([_add(new_text="stores it in data/drafts.json")], _CATALOG)
    assert r["status"] == "invalid"


@pytest.mark.covers("FR-01.11/AC49")
def test_restore_must_name_an_ac_in_the_catalog():
    ok = ad.decide([{"kind": "restore", "restores_ac": "FR-01.03.AC05"}], _CATALOG)
    assert ok["status"] == "ok" and ok["ac_decisions"][0] == {"ac": "FR-01.03.AC05", "mode": "auto", "answer": "auto"}
    gap = ad.decide([{"kind": "restore", "restores_ac": "FR-01.03.AC99"}], _CATALOG)
    assert gap["status"] == "invalid" and "catalog gap" in gap["errors"][0]
    assert ad.decide([{"kind": "restore"}], _CATALOG)["status"] == "invalid"
    assert ad.decide([{"kind": "restore", "restores_ac": "FR-01.03.AC05"}], set())["status"] == "invalid"  # no catalog = nothing to restore


@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("reason", ["bug", "trivial fix", "tooling", "small change", "refactor", "", "docs only", "tiny, minor"])
def test_exemption_by_label_is_refused(reason):
    r = ad.decide([{"kind": "exempt", "exempt_kind": "no-observable-change", "exempt_reason": reason}], _CATALOG)
    assert r["status"] == "invalid" and "label" in r["errors"][0]


@pytest.mark.covers("FR-01.11/AC49")
def test_exemption_by_outcome_is_auto_and_how_only_asks():
    reason = "no user- or operator-observable behaviour changes: the same checks run in the same order"
    r = ad.decide([{"kind": "exempt", "exempt_kind": "no-observable-change", "exempt_reason": reason}], _CATALOG)
    assert r["status"] == "ok" and r["ac_decisions"][0]["ac"] == "none"
    r = ad.decide([{"kind": "exempt", "exempt_kind": "how-only", "exempt_reason": reason, "plain_new": "Reports load from a faster source"}], _CATALOG)
    assert r["status"] == "ask" and r["questions"][0]["row"] == "exempt"
    assert "2 No, it is a promise: <your wording>" in r["questions"][0]["text"] and "\n3 " not in r["questions"][0]["text"]
    assert ad.decide([{"kind": "exempt", "exempt_kind": "other", "exempt_reason": reason}], _CATALOG)["status"] == "invalid"


@pytest.mark.covers("FR-01.11/AC49")
def test_answers_close_the_question_and_are_recorded():
    base = {"kind": "change", "ac": "FR-01.03.AC05", "old_text": "old text", "new_text": "new text", "plain_new": "n", "plain_old": "o"}
    yes = ad.decide([{**base, "answer": {"choice": "yes"}}], _CATALOG)
    assert yes["status"] == "ok" and yes["ac_decisions"] == [{"ac": "FR-01.03.AC05", "mode": "asked", "answer": "yes"}]
    no = ad.decide([{**base, "answer": {"choice": "no", "text": "The operator wording"}}], _CATALOG)
    assert no["status"] == "ok" and no["resolved_items"][0]["new_text"] == "The operator wording"
    how = ad.decide([{**base, "answer": {"choice": "only-how"}}], _CATALOG)
    assert how["status"] == "ok" and how["resolved_items"][0]["kind"] == "exempt" and how["resolved_items"][0]["exempt_kind"] == "how-only"
    assert yes["frozen_hash"] != no["frozen_hash"]


@pytest.mark.covers("FR-01.11/AC49")
def test_answers_are_validated_and_follow_the_original_operation():
    base = {"kind": "change", "ac": "FR-01.03.AC05", "old_text": "old text", "new_text": "new text", "plain_new": "n", "plain_old": "o"}
    assert ad.decide([{**base, "answer": {"choice": "later"}}], _CATALOG)["status"] == "invalid"  # no bypass by a made-up answer
    assert ad.decide([{**base, "answer": {"choice": "no"}}], _CATALOG)["status"] == "invalid"  # 'no' needs wording
    rm = {"kind": "remove", "ac": "FR-01.03.AC05", "old_text": "old text", "plain_old": "o"}
    refused = ad.decide([{**rm, "answer": {"choice": "no", "text": "keep it"}}], _CATALOG)
    assert refused["status"] == "invalid" and "kept" in refused["errors"][0]
    ex = {"kind": "exempt", "exempt_kind": "how-only", "exempt_reason": "the same pages render from a faster source", "plain_new": "p"}
    promoted = ad.decide([{**ex, "owner_fr": "FR-01.03", "answer": {"choice": "no", "text": "Pages load from a faster source"}}], _CATALOG)
    assert promoted["status"] == "ok" and promoted["resolved_items"][0]["kind"] == "add"


@pytest.mark.covers("FR-01.11/AC49")
def test_old_text_must_match_the_catalog_text():
    catalog = {"FR-01.03.AC05": "- (E) [AC05] Given a draft when saved then kept. (iterate-2026-10-31-x)"}
    item = {"kind": "change", "ac": "FR-01.03.AC05", "new_text": "n", "plain_new": "n", "plain_old": "o"}
    assert ad.decide([{**item, "old_text": "invented promise"}], catalog)["status"] == "invalid"
    assert ad.decide([{**item, "old_text": "Given a draft when saved"}], catalog)["status"] == "invalid"  # a fragment is not the text
    assert ad.decide([{**item, "old_text": "Given a draft when saved then kept."}], catalog)["status"] == "ask"
    spec = "### FR-01.03 - X\n\n- (E) [AC05] Given a draft,\n  when saved, then kept.\n\n## 3. Other\n"
    assert ad._catalog_texts(spec)["FR-01.03.AC05"] == "- (E) [AC05] Given a draft, when saved, then kept."


@pytest.mark.covers("FR-01.11/AC49")
def test_frozen_hash_is_stable_and_sees_a_text_edit():
    a = ad.decide([_add()], _CATALOG)
    assert a["frozen_hash"] == ad.decide([_add(new_text="  " + _PLAIN + "  ")], _CATALOG)["frozen_hash"]  # whitespace only
    assert a["frozen_hash"] != ad.decide([_add(new_text=_PLAIN + " and a warning")], _CATALOG)["frozen_hash"]
    assert ad.decide([], _CATALOG)["status"] == "invalid"


@pytest.mark.covers("FR-01.11/AC49")
def test_stub_lines_round_trip_and_detect_an_edit():
    r = ad.decide([_add(), {"kind": "restore", "restores_ac": "FR-01.03.AC05"}], _CATALOG)
    text = "\n".join(ad.stub_lines(r)) + "\n"
    parsed = ad.parse_stub_ac(text)
    assert parsed["hash_ok"] and parsed["frozen"] == r["frozen_hash"] and len(parsed["items"]) == 2
    assert not ad.parse_stub_ac(text.replace("loses a connection", "loses power"))["hash_ok"]
    assert ad.parse_stub_ac("Goal: g\nReason: r\n")["frozen"] == ""


def _catalog_tree(root: Path) -> None:
    spec = root / ".shipwright/planning/01-adopted/spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("### FR-01.03 - Drafts\n\n- (E) [AC05] Given a draft, when saved, then kept.\n", encoding="utf-8")


def _run_cli(tmp: Path, payload: dict, *extra: str) -> tuple[int, dict]:
    f = tmp / "ac.json"
    f.write_text(json.dumps(payload), encoding="utf-8")
    p = subprocess.run([sys.executable, str(_CLI), "--project-root", str(tmp), "--from-json", str(f), *extra],
                       capture_output=True, text=True, check=False)
    return p.returncode, json.loads(p.stdout) if p.stdout.strip() else {}


@pytest.mark.covers("FR-01.11/AC49")
def test_cli_exit_codes_and_autonomous_escalation(tmp_path):
    _catalog_tree(tmp_path)
    code, out = _run_cli(tmp_path, {"items": [{"kind": "restore", "restores_ac": "FR-01.03.AC05"}]})
    assert code == 0 and out["status"] == "ok"
    ask = {"items": [{"kind": "remove", "ac": "FR-01.03.AC05", "old_text": "Given a draft, when saved, then kept.", "plain_old": "Drafts are kept"}]}
    code, out = _run_cli(tmp_path, ask)
    assert code == 10 and "escalation" not in out
    code, out = _run_cli(tmp_path, ask, "--autonomous")
    esc = out["escalation"]
    assert code == 10 and esc["status"] == "escalated" and esc["reason_code"] == "ac_question_requires_operator"
    assert esc["ac_questions"][0]["row"] == 1 and "no longer holds" in esc["ac_questions"][0]["question"]
    code, out = _run_cli(tmp_path, {"items": [{"kind": "restore", "restores_ac": "FR-01.03.AC77"}]})
    assert code == 2 and out["status"] == "invalid"


@pytest.mark.covers("FR-01.11/AC49")
def test_escalation_matches_the_runner_contract_schema(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((_ROOT / "plugins/shipwright-iterate/agents/sub_iterate_runner_contract.schema.json").read_text(encoding="utf-8"))
    _catalog_tree(tmp_path)
    _, out = _run_cli(tmp_path, {"items": [{"kind": "remove", "ac": "FR-01.03.AC05", "old_text": "Given a draft, when saved, then kept.", "plain_old": "Drafts are kept"}]}, "--autonomous")
    result = {"sub_iterate_id": "Q1", **out["escalation"]}
    validator = jsonschema.Draft202012Validator({**schema, "$ref": "#/definitions/escalated"} if "definitions" in schema else {**schema, "$ref": "#/$defs/escalated"})
    validator.validate(result)
    bad = {k: v for k, v in result.items() if k != "ac_questions"}
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad)


@pytest.mark.covers("FR-01.11/AC49")
def test_write_plan_stub_carries_the_frozen_record_and_refuses_an_undecided_one(tmp_path):
    _catalog_tree(tmp_path)
    decided = tmp_path / "decided.json"
    _, out = _run_cli(tmp_path, {"items": [_add()]}, "--out", str(decided))
    spec = tmp_path / "stub.json"
    spec.write_text(json.dumps({"run_id": _RUN, "goal": "g", "reason": "r", "ref": "x", "tiny": True, "ac_decision": str(decided)}), encoding="utf-8")
    p = subprocess.run([sys.executable, str(_STUB), "--project-root", str(tmp_path), "--from-json", str(spec)], capture_output=True, text=True, check=False)
    assert p.returncode == 0, p.stderr
    text = (tmp_path / sc.plan_rel_path(_RUN)).read_text(encoding="utf-8")
    assert text.startswith("Goal: g\nReason: r\nReference: x\n") and ad.parse_stub_ac(text)["hash_ok"]
    undecided = tmp_path / "undecided.json"
    undecided.write_text(json.dumps({"status": "ask"}), encoding="utf-8")
    spec.write_text(json.dumps({"run_id": _RUN + "-2", "goal": "g", "reason": "r", "ref": "x", "ac_decision": str(undecided)}), encoding="utf-8")
    p = subprocess.run([sys.executable, str(_STUB), "--project-root", str(tmp_path), "--from-json", str(spec)], capture_output=True, text=True, check=False)
    assert p.returncode == 2 and "not 'ok'" in p.stderr


def _seed(root: Path, plan: str | None, **event) -> None:
    evt = {"type": "work_completed", "source": "iterate", "commit": "", "adr_id": _RUN, "intent": "feature", **event}
    (root / "shipwright_events.jsonl").write_text(json.dumps(evt) + "\n", encoding="utf-8")
    if plan is not None:
        target = root / sc.plan_rel_path(_RUN)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(plan, encoding="utf-8")


def _raw_stub(items: list[dict]) -> str:
    """A stub whose record is internally consistent (valid hash) but whose items would not pass ``decide``."""
    canon = [{k: v for k, v in it.items() if v} for it in items]
    decisions = [{"ac": "x", "mode": "auto", "answer": "auto"} for _ in canon]
    lines = [f"AC frozen: {ad.frozen_hash(canon)}"] + [f"AC item: {json.dumps(i)}" for i in canon] + ["AC decisions: " + json.dumps(decisions)]
    return sc.render_stub("full", "g", "r", "x") + "\n".join(lines) + "\n"


def _stub_with(items: list[dict], tamper: tuple[str, str] | None = None) -> str:
    r = ad.decide(items, _CATALOG)
    text = sc.render_stub("full", "g", "r", "x") + "".join(line + "\n" for line in ad.stub_lines(r))
    return text.replace(*tamper) if tamper else text


@pytest.mark.covers("FR-01.11/AC49")
def test_check_warns_never_errors_on_a_missing_edited_or_label_record(tmp_path):
    _catalog_tree(tmp_path)
    _seed(tmp_path, None)
    r = check_pre_build_ac_recorded(tmp_path, _RUN)
    assert r.ok is False and r.severity == "warning" and r.strict_exempt is True
    _seed(tmp_path, sc.render_stub("three", "g", "r", "x"))
    assert "carries no 'AC frozen:'" in check_pre_build_ac_recorded(tmp_path, _RUN).detail
    _seed(tmp_path, _stub_with([_add()], ("loses a connection", "loses power")))
    assert "frozen hash" in check_pre_build_ac_recorded(tmp_path, _RUN).detail
    # label and unknown-restore stubs are built directly (a valid hash), so each branch is reached on its own
    label = {"kind": "exempt", "exempt_kind": "no-observable-change", "exempt_reason": "tooling"}
    _seed(tmp_path, _raw_stub([label]))
    assert "label" in check_pre_build_ac_recorded(tmp_path, _RUN).detail
    _seed(tmp_path, _raw_stub([{"kind": "restore", "restores_ac": "FR-01.03.AC99"}]))
    assert "catalog gap" in check_pre_build_ac_recorded(tmp_path, _RUN).detail
    text = _stub_with([_add()])
    _seed(tmp_path, "\n".join(line for line in text.splitlines() if not line.startswith("AC decisions:")) + "\n")
    assert "AC decisions" in check_pre_build_ac_recorded(tmp_path, _RUN).detail
    _seed(tmp_path, _stub_with([_add()]))
    ok = check_pre_build_ac_recorded(tmp_path, _RUN)
    assert ok.ok is True and ok.detail == "recorded"


@pytest.mark.covers("FR-01.11/AC49")
def test_check_skips_other_intents_and_is_registered(tmp_path):
    assert check_pre_build_ac_recorded(tmp_path, _RUN).severity == "skipped"
    _seed(tmp_path, None, intent="bug")
    assert check_pre_build_ac_recorded(tmp_path, _RUN).severity == "skipped"
    assert check_pre_build_ac_recorded in claims.CLAIM_CHECKS and CHECK_NAME
