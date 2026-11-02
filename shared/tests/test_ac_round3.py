"""Q1 fix rounds: signed operator answers and the key, an add claims only new ids, base-ref and stacked units, the record from the commit, git timeouts."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from shared.tests.ac_test_helpers import BASE_SPEC as _BASE_SPEC
from shared.tests.ac_test_helpers import PROMISE as _PROMISE
from shared.tests.ac_test_helpers import SPEC as _SPEC
from shared.tests.ac_test_helpers import commit as _commit, decided as _decided, git as _git, repo as _repo
from lib import ac_catalog as cat
from lib import ac_hold
from lib import ac_record as ar
from lib import ac_surface as sf
from tools import ac_decision as cli
from tools.verifiers import pre_build_ac_check as chk

_RUN = "iterate-2026-11-01-q1-round3"


# --- 1: a "via" field proves nothing; the signature does --------------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_only_a_signed_answer_is_operator_and_the_signature_covers_question_choice_and_text():
    item = {"kind": "add", "new_text": _PROMISE}
    q = _decided([item], bind_id="b")["questions"][0]
    sha = q["question_sha256"]
    key = ac_hold.load_key(create=True)
    assert ac_hold.load_key(create=True) == key and len(key) == 32  # created once, then read back
    ans = {"item": 0, "question_sha256": sha, "options": q["options"], "choice": "yes", "text": "FR-01.03"}
    signed = {**ans, "via": "operator", "signature": ac_hold.sign(key, sha, "yes", "FR-01.03")}
    assert ac_hold.signature_ok(key, signed) and not ac_hold.signature_ok(key, ans) and not ac_hold.signature_ok(None, signed)
    assert not ac_hold.signature_ok(key, {**signed, "text": "FR-01.04"}) and not ac_hold.signature_ok(key, {**signed, "signature": 7})
    via = lambda a, **kw: _decided([item], bind_id="b", answers=[a], **kw)["ac_decisions"][0]["answered_via"]  # noqa: E731
    assert via(signed) == "operator" and via({**ans, "via": "operator"}) == "self-reported" and via(ans) == "self-reported"
    assert via(signed | {"signature": "00"}) == "self-reported"
    inline = _decided([{**item, "answer": {"choice": "yes", "text": "FR-01.03"}}])
    assert inline["ac_decisions"][0]["answered_via"] == "inline"


@pytest.mark.covers("FR-01.11/AC49")
def test_the_signing_key_is_created_exclusively_never_regenerated_and_a_bad_file_is_a_clear_error(tmp_path, monkeypatch):
    path = tmp_path / "keys" / "k"
    monkeypatch.setenv(ac_hold.KEY_ENV, str(path))
    assert ac_hold.load_key() is None and not path.exists()           # reading never creates
    key = ac_hold.load_key(create=True)
    assert path.read_text(encoding="ascii").strip() == key.hex()
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
    assert ac_hold.load_key(create=True) == key                        # an existing key is re-read, never replaced
    real_open = os.open

    def lost_race(p, flags, mode=0o777):                               # another process created it between our read and our create
        if Path(p) == path and flags & os.O_EXCL:
            raise FileExistsError(p)
        return real_open(p, flags, mode)
    path.unlink()
    monkeypatch.setattr(os, "open", lambda p, f, m=0o777: (path.write_text(key.hex() + "\n", encoding="ascii"), lost_race(p, f, m))[1])
    assert ac_hold.load_key(create=True) == key
    monkeypatch.undo()
    monkeypatch.setenv(ac_hold.KEY_ENV, str(path))
    for bad in ("", "not hex at all", "abcd"):                         # empty, malformed, too short: never regenerated
        path.write_text(bad, encoding="ascii")
        with pytest.raises(RuntimeError, match="never regenerated"):
            ac_hold.load_key(create=True)
        with pytest.raises(RuntimeError):
            ac_hold.load_key()
        assert path.read_text(encoding="ascii") == bad
    monkeypatch.setattr(cli, "load_key", lambda create=False: (_ for _ in ()).throw(RuntimeError("the signing key is empty")))
    ask = tmp_path / "ask.json"
    ask.write_text("{}", encoding="utf-8")
    held = tmp_path / "held.json"
    held.write_text(json.dumps({"questions": [{"item": 0, "question_sha256": "sha256:" + "a" * 64, "options": {}}]}), encoding="utf-8")
    assert cli.main(["answer", "--decided", str(held), "--item", "0", "--choice", "yes", "--answers", str(tmp_path / "a.json")]) == 2


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
    assert entry["options"] == q["options"]                                # the options come from the STORED question the operator saw
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
