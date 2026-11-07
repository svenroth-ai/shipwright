"""The pre-build AC decision (Q1): the one ask rule, outcome wording and the base-ref catalog (answers, counts and the CLI: test_ac_decision_answers.py)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from shared.tests.ac_test_helpers import ans
from lib import ac_decision as ad
from lib import ac_wording as aw

_OUTCOME = "A person who loses a connection sees a clear message instead of a blank page"
_OLD = "Given a draft, when saved, then it is kept."
_CAT = {"acs": {"FR-01.03.AC05": "- (E) [AC05] " + _OLD}, "frs": {"FR-01.03", "FR-01.04"}, "titles": {"FR-01.03": "Saving drafts", "FR-01.04": "Sharing drafts"}, "unparsed": False}


def _add(**kw) -> dict:
    return {"kind": "add", "owner_fr": "FR-01.03", "new_text": _OUTCOME, **kw}


def _change(**kw) -> dict:
    return {"kind": "change", "ac": "FR-01.03.AC05", "old_text": _OLD, "new_text": "A saved draft is kept for 30 days", **kw}


def _ask(item: dict, run_id: str = "", n: int = 0) -> dict:
    return ad.decide([item], _CAT, bind_id=run_id)["questions"][0]


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
    assert r["ac_decisions"] == [{"ac": "FR-01.03.new", "mode": "auto", "answer": "auto", "kind": "add", "answered_via": "none", "decided_by": "operator", "confirmed": True}]


@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("item,row", [(_change(), 1), ({"kind": "remove", "ac": "FR-01.03.AC05", "old_text": _OLD}, 1),
                                      ({"kind": "add", "new_text": _OUTCOME}, 2), (_add(owner_fr="FR-09.99"), 2),
                                      (_add(owner_fr=None, new_fr={"id": "FR-01.30", "title": "Offline drafts"}), 3)])
def test_ask_when_an_ac_changes_has_no_single_owner_or_opens_a_new_area(item, row):
    r = ad.decide([item], _CAT)
    assert r["status"] == "ask" and [q["row"] for q in r["questions"]] == [row]
    q = r["questions"][0]
    assert q["question_sha256"] == ad.question_sha("", 0, q["kind"], q["promise"], q["options"])  # stable content, not the rendered text


@pytest.mark.covers("FR-01.11/AC49")
def test_a_new_area_is_asked_once_and_can_be_approved_or_refused():
    item = _add(owner_fr=None, new_fr={"id": "FR-01.30", "title": "Offline drafts"})
    q = _ask(item)
    assert "Finding: this change needs a requirement that does not exist yet." in q["question"] and "New requirement: Offline drafts" in q["question"]
    yes = ad.decide([item], _CAT, answers=[ans(q, "yes")])
    assert yes["status"] == "ok" and yes["resolved_items"][0]["owner_fr"] == "FR-01.30" and yes["ac_decisions"][0]["ac"] == "FR-01.30.new"
    no = ad.decide([item], _CAT, answers=[ans(q, "no")])
    assert no["status"] == "invalid" and "ask them in the chat" in no["errors"][0]
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
    assert ad.load_catalog(tmp_path / "nope") == {"acs": {}, "frs": set(), "titles": {}, "fr_text": {}, "groups": {}, "unparsed": True}  # no spec at all: skipped, never asked
