"""Q1 last fix round: signed operator answers, base-ref catalog, fail-closed record checks, catalog shapes, resume path, unchanged kind, plain questions."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pytest

from lib import ac_catalog as cat
from lib import ac_decision as ad
from lib import ac_gloss
from lib import ac_hold
from lib import ac_record as ar
from lib import ac_surface as sf
from tools import ac_decision as cli
from tools.verifiers import pre_build_ac_check as chk

_RUN = "iterate-2026-11-01-q1-round3"
_SPEC = ".shipwright/planning/01-adopted/spec.md"
_BASE_SPEC = "### FR-01.03 - Saving drafts\n\n- (E) [AC05] Given a draft, when saved, then it is kept.\n\n### FR-01.04 - Sharing drafts\n\n- (E) [AC01] Given a link, when opened, then the draft shows.\n"
_PROMISE = "A saved draft survives a restart"


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path_factory):
    for name in ("SHIPWRIGHT_LOOP_ID", "SHIPWRIGHT_LOOP_UNIT_ID", ac_hold.OPERATOR_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(ac_hold.KEY_ENV, str(tmp_path_factory.mktemp("k") / "ac_operator.key"))


def _git(root: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *a], capture_output=True, text=True, check=True).stdout.strip()


def _repo(tmp_path: Path, spec: str = _BASE_SPEC) -> Path:
    root = tmp_path / "repo"
    (root / _SPEC).parent.mkdir(parents=True)
    (root / _SPEC).write_text(spec, encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root


def _commit(root: Path, files: dict[str, str], amend: bool = False) -> str:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, *(["commit", "-q", "--amend", "--no-edit"] if amend else ["commit", "-qm", "work"]))
    return _git(root, "rev-parse", "HEAD")


def _decided(items: list[dict], catalog: dict | None = None, **kw) -> dict:
    return ad.decide(items, catalog or cat_of(_BASE_SPEC), **kw)


def cat_of(spec: str) -> dict:
    acs, frs = cat.parse_catalog(spec)
    return {"acs": acs, "frs": set(frs), "titles": frs, "unparsed": False}


# --- 1: a "via" field proves nothing; the signature does --------------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_only_a_signed_answer_is_operator_and_the_signature_covers_question_choice_and_text():
    item = {"kind": "add", "new_text": _PROMISE}
    sha = ad.decide([item], cat_of(_BASE_SPEC), bind_id="b")["questions"][0]["question_sha256"]
    key = ac_hold.load_key(create=True)
    assert ac_hold.load_key(create=True) == key and len(key) == 32  # created once, then read back
    ans = {"item": 0, "question_sha256": sha, "choice": "yes", "text": "FR-01.03"}
    signed = {**ans, "via": "operator", "signature": ac_hold.sign(key, sha, "yes", "FR-01.03")}
    assert ac_hold.signature_ok(key, signed) and not ac_hold.signature_ok(key, ans) and not ac_hold.signature_ok(None, signed)
    assert not ac_hold.signature_ok(key, {**signed, "text": "FR-01.04"}) and not ac_hold.signature_ok(key, {**signed, "signature": 7})
    via = lambda a, **kw: _decided([item], bind_id="b", answers=[a], **kw)["ac_decisions"][0]["answered_via"]  # noqa: E731
    assert via(signed) == "operator" and via({**ans, "via": "operator"}) == "self-reported" and via(ans) == "self-reported"
    assert via(signed | {"signature": "00"}) == "self-reported"
    inline = _decided([{**item, "answer": {"choice": "yes", "text": "FR-01.03"}}])
    assert inline["ac_decisions"][0]["answered_via"] == "inline"


@pytest.mark.covers("FR-01.11/AC49")
def test_the_answer_tool_creates_the_key_signs_and_a_letter_never_exposes_an_area_id(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)  # hermetic: a unit-worktree cwd would make `answer` refuse as unattended
    root = _repo(tmp_path)
    ask = tmp_path / "ask.json"
    ask.write_text(json.dumps({"items": [{"kind": "add", "new_text": _PROMISE}]}), encoding="utf-8")
    out = tmp_path / "decided.json"
    assert cli.main(["--project-root", str(root), "--from-json", str(ask), "--base-ref", "HEAD", "--run-id", "r", "--out", str(out)]) == 10
    q = json.loads(out.read_text(encoding="utf-8"))["questions"][0]
    assert q["options"]["A"] == {"choice": "yes", "text": "FR-01.03"} and "FR-" not in q["question"]
    assert not Path(ac_hold.key_path()).exists()
    answers = tmp_path / "a.json"
    assert cli.main(["answer", "--decided", str(out), "--item", "0", "--choice", "A", "--answers", str(answers)]) == 0
    entry = json.loads(answers.read_text(encoding="utf-8"))["answers"][0]
    assert entry["choice"] == "yes" and entry["text"] == "FR-01.03" and ac_hold.signature_ok(ac_hold.load_key(), entry)
    assert cli.main(["answer", "--decided", str(out), "--item", "0", "--choice", "Z", "--answers", str(answers)]) == 2
    assert cli.main(["--project-root", str(root), "--from-json", str(ask), "--base-ref", "HEAD", "--run-id", "r", "--answers", str(answers)]) == 0


# --- 2: an add may only claim a new id ---------------------------------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_an_add_naming_an_existing_id_is_refused_and_never_names_an_edit():
    r = _decided([{"kind": "add", "ac": "FR-01.03.AC05", "owner_fr": "FR-01.03", "new_text": _PROMISE}])
    assert r["status"] == "invalid" and "already exists" in r["errors"][0]
    base = {"FR-01.03.AC05": "old"}
    changed = {"FR-01.03.AC05": "- (E) [AC05] " + _PROMISE}
    sneaky = [{"kind": "add", "ac": "FR-01.03.AC05", "new_text": _PROMISE}, {"kind": "add", "new_text": _PROMISE}]
    assert ar.undeclared_edits(sneaky, changed, set(), base) == ["FR-01.03.AC05"]   # a changed existing id matched only by an add
    assert ar.undeclared_edits(sneaky, changed, set()) == []                         # (without the base catalog the old rule applied)
    assert ar.undeclared_edits([{"kind": "change", "ac": "FR-01.03.AC05", "new_text": _PROMISE}], changed, set(), base) == []
    assert "already exists" in ar.freeze_differences([{"kind": "add", "ac": "FR-01.03.AC05", "new_text": _PROMISE}], changed, set(), base)[0]
    assert "no AC with this wording" in ar.freeze_differences([{"kind": "add", "new_text": _PROMISE}], changed, set(), base)[0]


# --- 4: the base is the merge-base, required, and a moved base is not inherited ------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_base_ref_is_required_and_resolved_to_the_merge_base(tmp_path, capsys):
    root = _repo(tmp_path)
    _git(root, "checkout", "-qb", "unit")
    _git(root, "checkout", "-q", "main")
    (root / _SPEC).write_text(_BASE_SPEC + "\n### FR-01.09 - Later work\n\n- (E) [AC01] Given x, when y, then z.\n", encoding="utf-8")
    _git(root, "commit", "-qam", "main moves on")                      # an earlier unit's edit lands on the base branch
    _git(root, "checkout", "-q", "unit")
    assert sf.merge_base(root, "main", "HEAD") == _git(root, "rev-parse", "unit")
    spec = tmp_path / "s.json"
    spec.write_text(json.dumps({"items": [{"kind": "restore", "restores_ac": "FR-01.09.AC01"}]}), encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main(["--project-root", str(root), "--from-json", str(spec)])  # --base-ref is required
    capsys.readouterr()
    # the catalog is the unit's fork point, not the moved tip of main: FR-01.09 is not there
    assert cli.main(["--project-root", str(root), "--from-json", str(spec), "--base-ref", "main"]) == 2
    assert "not in the catalog" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["verify", "--project-root", str(root), "--run-id", "r"])
    assert cli.main(["verify", "--project-root", str(root), "--run-id", "r", "--base-ref", "main"]) == 0
    assert json.loads(capsys.readouterr().out) == {"problems": []}
    with pytest.raises(RuntimeError):
        sf.merge_base(root, "no-such-ref")


@pytest.mark.covers("FR-01.11/AC49")
def test_a_stacked_unit_is_compared_against_its_own_fork_point(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    trunk = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-qb", "unit-a")
    _commit(root, {_SPEC: _BASE_SPEC + "- (E) [AC06] Given a, when b, then c.\n"})   # the earlier unit edits the catalog
    _git(root, "checkout", "-qb", "unit-b")
    head = _commit(root, {"docs/b.md": "words\n"})
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: {"source": "iterate", "stack_base_ref": "unit-a"})
    monkeypatch.setattr(chk, "_branch_base_commit", lambda r, c: trunk)
    assert chk.check_pre_build_ac_recorded(root, _RUN, head).ok                       # no inherited "undeclared edit" of FR-01.03.AC06
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: {"source": "iterate"})
    assert "FR-01.04.AC06" in chk.check_pre_build_ac_recorded(root, _RUN, head).detail


# --- 8: append-only and order ---------------------------------------------------------------------------------

def _rec_result() -> dict:
    return _decided([{"kind": "add", "owner_fr": "FR-01.03", "new_text": _PROMISE}])


@pytest.mark.covers("FR-01.11/AC49")
def test_the_record_is_read_from_the_commit_and_must_be_append_only_and_not_after_the_code(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: {"source": "iterate"})
    monkeypatch.setattr(chk, "_branch_base_commit", lambda r, c: base)
    spec_new = _BASE_SPEC + f"- (E) [AC06] {_PROMISE}\n"
    # code first, record in a LATER commit: out of order
    _commit(root, {"shared/scripts/a.py": "x = 1\n", _SPEC: spec_new})
    ar.append_record(root, _RUN, _rec_result())
    head = _commit(root, {})
    detail = chk.check_pre_build_ac_recorded(root, _RUN, head).detail
    assert "committed after the first code commit" in detail
    # the record in the same commit as the code is fine (a squashed iterate)
    head = _commit(root, {}, amend=True)
    _git(root, "reset", "-q", "--soft", base)
    head = _commit(root, {})
    assert chk.check_pre_build_ac_recorded(root, _RUN, head).ok
    # an uncommitted record is not what F11 sees
    ar.record_path(root, _RUN).write_text("", encoding="utf-8")
    assert chk.check_pre_build_ac_recorded(root, _RUN, head).ok
    # a record present at the base whose line is altered on the branch is not append-only
    other = _repo(tmp_path / "second")
    ar.append_record(other, "iterate-old", _rec_result())
    old_base = _commit(other, {})
    path = ar.record_path(other, "iterate-old")
    path.write_text(path.read_text(encoding="utf-8").replace("survives", "outlives"), encoding="utf-8")
    head2 = _commit(other, {"shared/scripts/b.py": "y = 1\n"})
    assert "not append-only" in "; ".join(ar.verify(other, "iterate-old", old_base, head2))
    path.write_text(path.read_text(encoding="utf-8").replace("outlives", "survives"), encoding="utf-8")
    ar.append_record(other, "iterate-old", _rec_result())
    head3 = _commit(other, {})
    assert "append-only" not in "; ".join(ar.verify(other, "iterate-old", old_base, head3))


# --- 9: git calls time out; one batch read; oversize untracked files fail closed ---------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_git_calls_have_a_timeout_batch_reads_report_missing_and_big_untracked_files_are_observable(tmp_path, monkeypatch):
    root = _repo(tmp_path)

    def hang(*a, **k):
        assert k["timeout"] == sf._GIT_TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired("git", 1)
    monkeypatch.setattr(sf.subprocess, "run", hang)
    with pytest.raises(RuntimeError, match="did not run"):
        sf.run_git(root, "status")
    monkeypatch.undo()
    got = sf.read_blobs(root, "HEAD", [_SPEC, "nope/missing.md", "has space.md"])
    assert got[_SPEC] and got["nope/missing.md"] is None and got["has space.md"] is None and sf.read_blobs(root, "HEAD", []) == {}
    (root / "big.txt").write_text("x" * (sf._MAX_UNTRACKED_BYTES + 10), encoding="utf-8")
    assert sf.git_changes(root, "HEAD")["big.txt"]["added"] == ["<oversize>"]
    monkeypatch.setattr(cat, "read_blobs", lambda *a, **k: {_SPEC: None})
    with pytest.raises(RuntimeError, match="cannot read .shipwright/planning/01-adopted/spec.md"):
        cat.load_catalog(root, "HEAD")


# --- 10: every catalog shape the product writes -----------------------------------------------------------------

_GREENFIELD = """## Functional Requirements

| ID | Area | Name | Priority | Requirement |
|----|------|------|----------|-------------|
| FR-01.01 | Auth | User registration | Must | The system SHALL allow users to register |
| FR-01.02 | Auth | User login | Must | The system SHALL authenticate users |

### Acceptance Criteria

**FR-01.01: User Registration**
- [ ] User can register with valid email and password
- [ ] Duplicate email returns clear error message

**FR-01.02: User Login**
- [ ] Valid credentials return session token
"""
_ADOPTED = """### FR-01.01 — Org-chart validation

- (E) Given a document declaring version two, when it is validated, then it is accepted.
  It continues on a second line.
- (E) Given a lead whose manages links form a cycle, when validated, then it is rejected.

### FR-01.02 Task detail
- (E) **(iterate-2026-05-14 lead-foundation)** Given a viewer, when opened, then three panes show.
"""
_TABLE_ONLY = "| FR-01.01 | The system SHALL initialize a project | Must |\n| FR-01.02 | The system SHALL connect to a database | Must |\n\n- [ ] All tables use a prefix\n"


@pytest.mark.covers("FR-01.11/AC49")
def test_the_parser_reads_this_repos_shape_the_greenfield_shape_adopted_repos_and_table_only_specs():
    acs, frs = cat.parse_catalog(_BASE_SPEC)
    assert set(acs) == {"FR-01.03.AC05", "FR-01.04.AC01"} and frs == {"FR-01.03": "Saving drafts", "FR-01.04": "Sharing drafts"}
    acs, frs = cat.parse_catalog(_GREENFIELD)   # **FR-xx.yy: title** headings, "- [ ]" criteria numbered by position, table rows
    assert set(acs) == {"FR-01.01.AC01", "FR-01.01.AC02", "FR-01.02.AC01"} and frs["FR-01.01"] == "User Registration" and frs["FR-01.02"] == "User Login"
    assert "register with valid email" in acs["FR-01.01.AC01"]
    acs, frs = cat.parse_catalog(_ADOPTED)      # unmarked "- (E)" criteria, em-dash and plain-space titles
    assert set(acs) == {"FR-01.01.AC01", "FR-01.01.AC02", "FR-01.02.AC01"} and frs == {"FR-01.01": "Org-chart validation", "FR-01.02": "Task detail"}
    assert "second line" in acs["FR-01.01.AC01"] and cat.ac_body(acs["FR-01.02.AC01"]).startswith("given a viewer")
    acs, frs = cat.parse_catalog(_TABLE_ONLY)   # FRs from the table, criteria not addressable without a heading
    assert acs == {} and set(frs) == {"FR-01.01", "FR-01.02"}
    assert cat.parse_catalog("") == ({}, {}) and cat.parse_catalog("## Notes\n\n- a bullet\n") == ({}, {})


@pytest.mark.covers("FR-01.11/AC49")
def test_a_greenfield_catalog_can_be_changed_and_restored_by_position_id():
    catalog = cat_of(_GREENFIELD)
    old = "User can register with valid email and password"
    r = ad.decide([{"kind": "change", "ac": "FR-01.01.AC01", "old_text": old, "new_text": "A visitor can sign up with an email and a password"}], catalog)
    assert r["status"] == "ask" and r["questions"][0]["row"] == 1
    assert ad.decide([{"kind": "restore", "restores_ac": "FR-01.02.AC01"}], catalog)["status"] == "ok"


@pytest.mark.covers("FR-01.11/AC49")
def test_a_catalog_with_text_but_no_readable_fr_is_skipped_never_asked_or_refused(tmp_path, capsys, monkeypatch):
    root = _repo(tmp_path, "# Spec\n\nRequirement one is described in prose only.\n")
    loaded = cat.load_catalog(root, "HEAD")
    assert loaded["unparsed"] and loaded["frs"] == set()
    skipped = ad.decide([{"kind": "add", "new_text": _PROMISE}], loaded)
    assert skipped["status"] == "skipped" and "nothing is asked or refused" in skipped["note"]
    spec = tmp_path / "s.json"
    spec.write_text(json.dumps({"items": [{"kind": "add", "new_text": _PROMISE}]}), encoding="utf-8")
    assert cli.main(["--project-root", str(root), "--from-json", str(spec), "--base-ref", "HEAD"]) == 0
    capsys.readouterr()
    assert cli.main(["verify", "--project-root", str(root), "--run-id", "r", "--base-ref", "HEAD"]) == 0
    assert "skipped" in json.loads(capsys.readouterr().out)["note"]
    head = _commit(root, {"shared/scripts/a.py": "x = 1\n"})
    base = _git(root, "rev-parse", "HEAD~1")
    assert ar.verify(root, _RUN, base, head) == []
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: {"source": "iterate"})
    monkeypatch.setattr(chk, "_branch_base_commit", lambda r, c: base)
    assert chk.check_pre_build_ac_recorded(root, _RUN, head).severity == "skipped"
    empty = cat_of("")
    assert not cat.load_catalog(_repo(tmp_path / "e", ""), "HEAD")["unparsed"] and empty["acs"] == {}


# --- 11: hold -> answer -> pending -> complete, with the same question hashes --------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_resume_path_hold_answer_pending_complete(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from lib.autonomous_loop import cmd_record
    from lib.loop_mark import cmd_mark
    root = _repo(tmp_path)
    ask = tmp_path / "ask.json"
    ask.write_text(json.dumps({"items": [{"kind": "add", "new_text": _PROMISE}]}), encoding="utf-8")
    stable = "camp--Q1"
    common = ["--project-root", str(root), "--from-json", str(ask), "--base-ref", "HEAD", "--sub-iterate-id", "Q1", "--bind-id", stable]
    decided = tmp_path / "decided.json"
    assert cli.main([*common, "--autonomous", "--run-id", "run-attempt-0", "--out", str(decided)]) == 10
    escalation = json.loads(decided.read_text(encoding="utf-8"))["escalation"]
    state = tmp_path / "loop_state.json"
    state.write_text(json.dumps({"loop_id": "loop-1", "kind": "sub_iterate", "units": [
        {"id": "Q1", "status": "running", "attempt": 0, "attempt_id": "A0", "branch": "b", "finished_at": None, "commit": None}]}), encoding="utf-8")
    args = argparse.Namespace(state=str(state), unit="Q1", attempt_id="A0", result=json.dumps(escalation))
    assert cmd_record(args) == 0 and json.loads(state.read_text(encoding="utf-8"))["units"][0]["status"] == "held"
    held = tmp_path / "result.json"
    held.write_text(json.dumps(escalation), encoding="utf-8")
    answers = tmp_path / "answers.json"
    assert cli.main(["answer", "--decided", str(held), "--item", "0", "--choice", "A", "--answers", str(answers)]) == 0   # the operator
    assert cmd_mark(argparse.Namespace(state=str(state), unit="Q1", status="pending", reason="answered", operator="sven", reason_code=None,
                                       merged_commit=None, force=True, confirm_no_task_running=True, campaign_worktree=None)) == 0
    # the unit is claimed again under a NEW attempt and a NEW run id; the stable id keeps the question hashes equal
    rows = json.loads(state.read_text(encoding="utf-8"))
    rows["units"][0].update({"status": "running", "attempt": 1, "attempt_id": "A1"})
    state.write_text(json.dumps(rows), encoding="utf-8")
    capsys.readouterr()
    assert cli.main([*common, "--autonomous", "--run-id", "run-attempt-1", "--answers", str(answers), "--out", str(decided)]) == 0
    result = json.loads(decided.read_text(encoding="utf-8"))
    assert result["status"] == "ok" and result["ac_decisions"][0]["answered_via"] == "operator" and result["resolved_items"][0]["owner_fr"] == "FR-01.03"
    done = argparse.Namespace(state=str(state), unit="Q1", attempt_id="A1", result=json.dumps(
        {"status": "complete", "commit": "abc", "tests_passed": 1, "tests_total": 1, "branch": "b"}))
    assert cmd_record(done) == 0 and json.loads(state.read_text(encoding="utf-8"))["units"][0]["status"] == "built"
    capsys.readouterr()


# --- 12: unchanged = observable files change, the promise stays ---------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_unchanged_needs_an_existing_ac_and_a_file_list_and_has_its_own_bucket():
    catalog = cat_of(_BASE_SPEC)
    ok = _decided([{"kind": "unchanged", "ac": "FR-01.03.AC05", "files": ["shared/scripts/a.py", "shared/scripts/b.py"]}])
    assert ok["status"] == "ok" and ok["counts"]["unchanged"] == 1 and ok["counts"]["auto"] == 0 and ok["ac_decisions"][0]["kind"] == "unchanged"
    assert ad.frozen_fields(ok["resolved_items"][0])["files"] == ["shared/scripts/a.py", "shared/scripts/b.py"]
    for bad in ({"kind": "unchanged", "ac": "FR-01.03.AC05"}, {"kind": "unchanged", "ac": "FR-01.03.AC05", "files": []},
                {"kind": "unchanged", "ac": "FR-01.03.AC05", "files": [3]}, {"kind": "unchanged", "ac": "FR-09.09.AC01", "files": ["a.py"]},
                {"kind": "unchanged", "files": ["a.py"]}):
        assert ad.decide([bad], catalog)["status"] == "invalid"


@pytest.mark.covers("FR-01.11/AC49")
def test_the_unchanged_record_is_checked_against_the_diff_and_a_test_naming_the_ac(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: {"source": "iterate"})
    monkeypatch.setattr(chk, "_branch_base_commit", lambda r, c: base)
    _commit(root, {"shared/scripts/a.py": "x = 1\n", "shared/scripts/b.py": "y = 1\n"})
    ar.append_record(root, _RUN, _decided([{"kind": "unchanged", "ac": "FR-01.03.AC05", "files": ["shared/scripts/a.py"]}]))
    head = _commit(root, {}, amend=True)
    detail = chk.check_pre_build_ac_recorded(root, _RUN, head).detail
    assert "shared/scripts/b.py" in detail and "no test file in the diff mentions" in detail and "not a behaviour-preserving refactor" in detail
    ar.record_path(root, _RUN).unlink()
    ar.append_record(root, _RUN, _decided([{"kind": "unchanged", "ac": "FR-01.03.AC05", "files": ["shared/scripts/a.py", "shared/scripts/b.py"]}]))
    head = _commit(root, {"shared/tests/test_a.py": '@pytest.mark.covers("FR-01.03/AC05")\n'}, amend=True)
    assert chk.check_pre_build_ac_recorded(root, _RUN, head).ok


# --- 13: the plain-language pick list ----------------------------------------------------------------------------

_AREAS = ("### FR-01.03 - Saving drafts\n\n- (E) [AC05] Given a draft, when it is saved, then it is kept after a restart of the application.\n\n"
          "### FR-01.04 - Sharing drafts\n\n- (E) [AC01] Given a link, when it is opened, then the draft shows.\n\n"
          "### FR-01.05 - Billing\n\n- (E) [AC01] Given an invoice, when it is due, then it is sent.\n")


@pytest.mark.covers("FR-01.11/AC49")
def test_a_no_owner_question_is_a_lettered_pick_list_in_everyday_words():
    catalog = cat_of(_AREAS)
    r = ad.decide([{"kind": "add", "new_text": "A saved draft survives a restart"}], catalog, bind_id="b")
    q = r["questions"][0]
    text = q["question"]
    for jargon in ("feature", "FR-", "feature id"):
        assert jargon not in text
    assert text.startswith("This change adds a new promise: A saved draft survives a restart. Where does it belong?")
    lines = text.splitlines()[1:]
    assert lines[0].startswith("A Saving drafts: ") and "It is kept after a restart" in lines[0]
    assert lines[-3].startswith("C Somewhere new") and lines[-2].startswith("D It is not a promise") and lines[-1].startswith("E Not wanted:")
    assert q["options"]["A"] == {"choice": "yes", "text": "FR-01.03"} and q["options"]["C"] == {"choice": "other"} and q["options"]["D"] == {"choice": "not_a_promise"}
    again = ad.decide([{"kind": "add", "new_text": "A saved draft survives a restart"}], catalog, bind_id="b")["questions"][0]
    assert again == q                                                   # deterministic
    none = ad.decide([{"kind": "add", "new_text": "Orbits remain stable"}], catalog)["questions"][0]
    assert none["question"].splitlines()[1].startswith("A An area that already exists") and none["options"]["A"] == {"choice": "yes"}


@pytest.mark.covers("FR-01.11/AC49")
def test_picking_new_area_or_not_a_promise_or_a_name_resolves_or_explains():
    catalog = cat_of(_AREAS)
    item = {"kind": "add", "new_text": "A saved draft survives a restart"}
    sha = ad.decide([item], catalog, bind_id="b")["questions"][0]["question_sha256"]
    def go(choice, text=""):
        return ad.decide([item], catalog, bind_id="b", answers=[{"item": 0, "question_sha256": sha, "choice": choice, "text": text}])
    assert "new_fr" in go("other", "Offline mode")["errors"][0]
    assert "not a promise" in go("not_a_promise")["errors"][0]
    assert go("yes", "sharing drafts")["resolved_items"][0]["owner_fr"] == "FR-01.04"   # by the area's name, case-insensitively
    assert go("yes", "No such area")["status"] == "invalid"


@pytest.mark.covers("FR-01.11/AC49")
def test_the_gloss_explains_at_most_two_jargon_terms_once_and_only_from_the_data_file(tmp_path):
    g = ac_gloss.load_glossary()
    assert {"commit", "pull request", "stack profile", "gate", "phase", "pipeline", "review model", "build", "deployment", "coordinator"} <= set(g)
    text = "A commit is checked at the gate before the pull request opens, and the commit is kept"
    assert ac_gloss.jargon_terms(text) == ["commit", "gate", "pull request"]
    out = ac_gloss.gloss(text)
    assert out.startswith(" (commit: ") and "gate: " in out and "pull request" not in out and out.count(";") == 1 and out.count("commit:") == 1
    assert ac_gloss.gloss("Drafts are kept") == "" and ac_gloss.gloss("") == ""
    assert ac_gloss.jargon_terms("Commits are saved") == ["commit"] and ac_gloss.jargon_terms("a decommissioned thing") == []
    bad = tmp_path / "g.json"
    bad.write_text("{not json", encoding="utf-8")
    assert ac_gloss.load_glossary(bad) == {} and ac_gloss.load_glossary(tmp_path / "none.json") == {}
    custom = {"widget": "a small part"}
    assert ac_gloss.gloss("The widget works", custom) == " (widget: a small part)"
    q = ad.decide([{"kind": "add", "new_text": "Every commit is checked by a gate"}], cat_of(_AREAS))["questions"][0]["question"]
    assert "a saved snapshot of the work" in q.splitlines()[0] and "an automatic check" in q.splitlines()[0]
    assert "(commit:" not in ad.render_question({"kind": "change", "old_text": "Every commit is kept", "new_text": "Every commit is kept long"})   # changed promises stay as they were


@pytest.mark.covers("FR-01.11/AC49")
def test_candidate_areas_rank_by_shared_words_and_the_blurb_is_one_short_line():
    catalog = cat_of(_AREAS)
    assert [fr for fr, _ in cat.candidates("Drafts are saved and shared", catalog)] == ["FR-01.03", "FR-01.04"]
    assert cat.candidates("nothing alike here", catalog) == []
    assert cat.area_blurb("FR-01.04", catalog) == "The draft shows."
    assert cat.area_blurb("FR-01.03", {"acs": {"FR-01.03.AC01": "- [AC01] " + "word " * 60}}) == ""   # too long: the name alone
    assert cat.area_blurb("FR-01.03", {"acs": {"FR-01.03.AC01": "- [AC01] Given x, when y, then it is kept — built, tested and reviewed."}}) == "It is kept."
    assert cat.area_blurb("FR-09.09", catalog) == ""
