"""Q1: the observable surface computed from a diff (fail-closed), the append-only AC record, the F11 compare, and the per-unit hold."""

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
_SHA = "sha256:" + "b" * 64


@pytest.fixture(autouse=True)
def _attended(monkeypatch):
    for name in ("SHIPWRIGHT_LOOP_ID", "SHIPWRIGHT_LOOP_UNIT_ID", ac_hold.OPERATOR_ENV):
        monkeypatch.delenv(name, raising=False)


def _diff(path: str, added=(), removed=(), extra="") -> str:
    body = "".join(f"-{x}\n" for x in removed) + "".join(f"+{x}\n" for x in added)
    return f"diff --git a/{path} b/{path}\n{extra}--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n{body}"


def _hunks(path: str, *pairs: tuple[list[str], list[str]]) -> str:
    out = f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
    for removed, added in pairs:
        out += "@@ -1 +1 @@\n" + "".join(f"-{x}\n" for x in removed) + "".join(f"+{x}\n" for x in added)
    return out


def _obs(text: str, file_text: str | None = None) -> bool:
    """Observable? ``file_text`` is what the file holds (both sides), so a Python ``#`` line can be told from string text."""
    changes = sf.parse_diff(text)
    if file_text is not None:
        for rec in changes.values():
            rec["read"] = lambda side, t=file_text: t
    return sf.observable_files(changes)["observable"]


# --- the observable surface: fail-closed ---------------------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("path,expected", [
    ("plugins/x/scripts/a.py", True), ("plugins/x/hooks/hooks.json", True), ("plugins/x/agents/r.md", True),
    ("plugins/x/skills/y/SKILL.md", True), ("plugins/x/skills/y/references/F5.md", True), ("shared/prompts/p.md", True),
    ("shared/schemas/s.schema.json", True), ("shared/templates/t.md", True), ("shared/constitution.md", True),
    (".github/workflows/ci.yml", True),
    # unknown or missing extension outside docs/tests roots is observable (fail-closed)
    ("Dockerfile", True), ("Makefile", True), (".pre-commit-config", True), ("cmd/main.go", True), ("src/lib.rs", True), ("src/App.java", True),
    ("db/schema.sql", True), ("uv.lock", True), ("requirements.txt", True), ("assets/logo.png", True), ("data.bin", True), ("scripts/run", True),
    # docs, tests and ledgers are excluded by DIRECTORY root, never by file name
    ("docs/guide.md", False), (".shipwright/planning/x/spec.md", False), ("shared/tests/test_a.py", False), ("plugins/x/tests/conftest.py", False),
    ("integration-tests/fixtures/a.json", False), ("CHANGELOG-unreleased.d/x/y.md", False), ("README.md", False), ("CHANGELOG.md", False),
    ("shipwright_events.jsonl", False), ("notes/todo.md", False),
    # names that merely look like tests or changelogs are production code
    # docs and tests are roots, not any directory with that name; the project's own profiles are behaviour
    ("src/docs/router.ts", True), ("src/tests/helper.py", True), ("app/__tests__/a.ts", True), (".shipwright/profiles/stack.json", True),
    ("plugins/x/docs/a.md", False), ("shared/scripts/tools/tests/test_a.py", False), ("shared/scripts/lib/test_gate.py", True), ("shared/scripts/lib/changelog.py", True), ("plugins/x/scripts/readme_builder.py", True),
    ("shared/scripts/shipwright_helper.py", True), ("src/conftest.py", True), ("src/a_test.py", True),
])
def test_path_classes(path, expected):
    assert sf.is_observable_path(path) is expected


@pytest.mark.covers("FR-01.11/AC49")
def test_is_test_path_is_by_directory_only():
    assert sf.is_test_path("shared/tests/test_a.py") and sf.is_test_path("integration-tests/x.py")
    assert not sf.is_test_path("shared/scripts/lib/test_gate.py")


@pytest.mark.covers("FR-01.11/AC49")
def test_only_docs_tests_comments_whitespace_and_renames_are_exempt():
    text = "".join([
        _diff("docs/guide.md", ["new"]), _diff("shared/tests/test_a.py", ["assert 1"]),
        _diff("shared/scripts/a.py", ["# only a comment", ""], ["", "# the old comment"]),
        "diff --git a/shared/scripts/old.py b/shared/scripts/new.py\nsimilarity index 100%\nrename from shared/scripts/old.py\nrename to shared/scripts/new.py\n",
    ])
    changes = sf.parse_diff(text)
    changes["shared/scripts/a.py"]["read"] = lambda side: "x = 1\n"
    assert sf.observable_files(changes) == {"observable": False, "files": [], "ignored": 4}


@pytest.mark.covers("FR-01.11/AC49")
def test_a_behaviour_change_and_new_deleted_or_textless_changes_are_observable():
    text = _diff("shared/scripts/a.py", ["return 2"], ["return 1"]) + "diff --git a/plugins/x/agents/n.md b/plugins/x/agents/n.md\nnew file mode 100644\n--- /dev/null\n+++ b/plugins/x/agents/n.md\n@@ -0,0 +1 @@\n+# heading\n"
    got = sf.observable_files(sf.parse_diff(text))
    assert got["observable"] and got["files"] == ["plugins/x/agents/n.md", "shared/scripts/a.py"]
    assert _obs("diff --git a/assets/logo.png b/assets/logo.png\nBinary files a/assets/logo.png and b/assets/logo.png differ\n")
    assert _obs("diff --git a/scripts/run.sh b/scripts/run.sh\nold mode 100644\nnew mode 100755\n")
    rec = sf.parse_diff(_diff("shared/scripts/c.py", ["++ not a header"]))["shared/scripts/c.py"]
    assert rec["added"] == ["++ not a header"]  # a "+++"-looking content line inside a hunk is content, not a header
    assert sf.parse_diff("") == {} and sf.parse_diff("stray\n+line") == {}


@pytest.mark.covers("FR-01.11/AC49")
def test_a_rename_that_crosses_the_boundary_is_observable_and_one_inside_a_class_is_not():
    def rename(old: str, new: str) -> str:
        return f"diff --git a/{old} b/{new}\nsimilarity index 100%\nrename from {old}\nrename to {new}\n"
    assert _obs(rename("shared/tests/test_gate.py", "shared/scripts/lib/gate.py"))   # test -> production
    assert _obs(rename("shared/scripts/lib/gate.py", "docs/gate.md"))                # production -> docs
    assert not _obs(rename("shared/scripts/lib/a.py", "shared/scripts/lib/b.py"))    # inside production
    assert not _obs(rename("docs/a.md", "docs/b.md"))                                # inside docs


@pytest.mark.covers("FR-01.11/AC49")
def test_the_compare_is_per_hunk_in_order_keeping_indentation_and_shebangs():
    # indentation is syntax in Python and YAML
    assert _obs(_diff("shared/scripts/a.py", ["    return 1"], ["return 1"]))
    assert _obs(_diff("conf/a.yml", ["  key: 1"], ["key: 1"]))
    assert _obs(_diff("shared/scripts/a.py", ["    return  1"], ["    return 1"]))      # inner spacing can sit inside a string: kept
    assert not _obs(_diff("shared/scripts/a.js", ["  return 1;"], ["return 1;"]))        # indentation free elsewhere
    assert _obs(_diff("shared/scripts/a.js", ["  return  1;"], ["return 1;"]))
    # a swap of two lines is a change: order matters, a whole-file multiset would call it a no-op
    assert _obs(_hunks("shared/scripts/a.py", (["a = 1", "b = 2"], ["b = 2", "a = 1"])))
    # lines moved BETWEEN hunks are a change too
    assert _obs(_hunks("shared/scripts/a.py", (["x = 1"], []), ([], ["x = 1"])))
    # a shebang is code, an ordinary comment is not
    assert _obs(_diff("scripts/run.sh", ["#!/bin/bash"], ["#!/bin/sh"]))
    assert not _obs(_diff("scripts/run.sh", ["# note"], ["# other note"]))
    assert not _obs(_hunks("shared/scripts/a.py", (["# old"], ["# new"]), ([""], [])), "x = 1\n")


@pytest.mark.covers("FR-01.11/AC49")
def test_comments_are_full_lines_of_the_extensions_own_syntax_and_never_text_inside_a_string():
    # a Python "#" line inside a triple-quoted string is text: changing it changes behaviour
    src = 'DOC = """\n# heading\n"""\nx = 1\n'
    assert _obs(_diff("shared/scripts/a.py", ["# heading"], ["# other"]), src)
    assert not _obs(_diff("shared/scripts/a.py", ["# heading"], ["# other"]), "# heading\nx = 1\n")
    # undecidable (no file text, or a file that does not tokenize): fail closed
    assert _obs(_diff("shared/scripts/a.py", ["# heading"], ["# other"]))
    assert _obs(_diff("shared/scripts/a.py", ["# heading"], ["# other"]), "x = (\n")
    # "*" counts as a comment only inside a /* */ block of the same hunk; "//" is a comment, "#" is code in JS
    assert not _obs(_hunks("shared/scripts/a.js", (["/* old", " * note", " */"], ["/* new", " * other", " */"])))
    assert _obs(_diff("shared/scripts/a.js", ["* total"], ["* count"]))
    assert not _obs(_diff("shared/scripts/a.js", ["// old"], ["// new"]))
    assert _obs(_diff("shared/scripts/a.js", ["# old"], ["# new"]))
    # a Makefile keeps tab-versus-space; inner spacing inside a string literal is kept
    assert _obs(_diff("Makefile", ["\tgo"], ["    go"]))
    assert not _obs(_diff("Makefile", ["# old"], ["# new"]))
    assert _obs(_diff("shared/scripts/a.sh", ['echo "a  b"'], ['echo "a b"']))
    # markdown has no comment syntax: a changed prompt line is a change
    assert _obs(_diff("plugins/x/agents/r.md", ["<!-- old -->"], ["<!-- new -->"]))


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
    return ad.decide([{"kind": "add", "owner_fr": "FR-01.03", "new_text": "A saved draft survives a restart", **kw}], {"acs": {}, "frs": {"FR-01.03"}})


@pytest.mark.covers("FR-01.11/AC49")
def test_force_appends_a_superseded_record_and_never_replaces(tmp_path):
    first = ar.append_record(tmp_path, _RUN, {**_result(), "unattended": True})
    second = ar.append_record(tmp_path, _RUN, _result(new_text="A saved draft survives two restarts"))
    assert (first["kind"], first["seq"], first["supersedes"], first["unattended"]) == ("frozen", 1, None, True)
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


@pytest.mark.covers("FR-01.11/AC49")
def test_undeclared_catalog_edits_are_found_from_the_diff_not_from_a_label():
    changed = {"FR-01.03.AC05": "- (E) [AC05] reworded", "FR-01.03.AC06": "- (E) [AC06] A saved draft survives a restart"}
    named = [{"kind": "change", "ac": "FR-01.03.AC05", "new_text": "reworded"}, {"kind": "add", "new_text": "A saved draft survives a restart"}]
    assert ar.undeclared_edits(named, changed, set()) == []
    assert ar.undeclared_edits(named[:1], changed, set()) == ["FR-01.03.AC06"]       # a new AC nobody declared
    assert ar.undeclared_edits([{"kind": "restore", "restores_ac": "FR-01.03.AC05"}], changed, {"FR-01.03.AC09"}) == ["FR-01.03.AC05", "FR-01.03.AC06", "FR-01.03.AC09"]
    assert ar.undeclared_edits("junk", {}, {"FR-01.03.AC09"}) == ["FR-01.03.AC09"]


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
    head = _record(root, commit, ad.decide([change], cat, answers=[{"item": 0, "question_sha256": ad.question_sha(ad.render_question(change), "", 0), "choice": "yes"}]))
    res = chk.check_pre_build_ac_recorded(root, _RUN, head)
    assert "no record item names" not in res.detail and "answered_via: self-reported" in res.detail  # named now; the unsigned answer is the only warning left


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
def test_check_warns_for_any_asked_decision_that_is_not_operator_signed(branch, monkeypatch, tmp_path):
    root, commit = branch
    monkeypatch.setenv(ac_hold.KEY_ENV, str(tmp_path / "key"))
    head = commit({"shared/scripts/a.py": "x = 1\n", _SPEC: _spec_with("A saved draft survives a restart")})
    base = {"kind": "add", "new_text": "A saved draft survives a restart"}
    sha = ad.question_sha(ad.render_question(base, {"acs": {}, "frs": {"FR-01.03"}, "titles": {}}), "r", 0)
    key = ac_hold.load_key(create=True)
    signed = {"item": 0, "question_sha256": sha, "choice": "yes", "text": "FR-01.03", "via": "operator", "signature": ac_hold.sign(key, sha, "yes", "FR-01.03")}
    forged = {k: v for k, v in signed.items() if k != "signature"}  # "via": "operator" is only a claim
    for ans, expect_warning in ((signed, False), (forged, True)):
        ar.record_path(root, _RUN).unlink(missing_ok=True)
        res = ad.decide([base], {"acs": {}, "frs": {"FR-01.03"}, "titles": {}}, bind_id="r", answers=[ans])
        head = _record(root, commit, res)
        detail = chk.check_pre_build_ac_recorded(root, _RUN, head).detail
        assert ("signed operator channel" in detail) is expect_warning
    # inline answers (attended) are also self-reported: the warning does not depend on the run being unattended
    ar.record_path(root, _RUN).unlink(missing_ok=True)
    head = _record(root, commit, ad.decide([{**base, "answer": {"choice": "yes", "text": "FR-01.03"}}], {"acs": {}, "frs": {"FR-01.03"}, "titles": {}}, bind_id="r"))
    assert "answered_via: inline" in chk.check_pre_build_ac_recorded(root, _RUN, head).detail


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

def _esc(**kw) -> dict:
    return {"sub_iterate_id": "Q1", "status": "escalated", "reason": "ac_question_requires_operator: x", "reason_code": "ac_question_requires_operator", "bind_id": "camp--Q1",
            "ac_questions": [{"item": 0, "row": 1, "question": "q", "question_sha256": ac_hold.question_sha("q", "camp--Q1", 0)}], **kw}


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
    # the hash is RECOMPUTED from question text + stable id + item index: a well-formed but wrong hash holds nothing
    assert not ac_hold.is_ac_hold(_esc(ac_questions=[{"item": 0, "row": 1, "question": "q", "question_sha256": _SHA}]))
    assert not ac_hold.is_ac_hold(_esc(bind_id="other")) and not ac_hold.is_ac_hold(_esc(ac_questions=[{"item": 1, "row": 1, "question": "q", "question_sha256": ac_hold.question_sha("q", "camp--Q1", 0)}]))
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
