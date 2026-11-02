"""Q1: the observable surface computed from a diff (fail-closed) and the append-only AC record (the F11 check and the per-unit hold: test_ac_f11_check.py)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from lib import ac_decision as ad
from lib import ac_record as ar
from lib import ac_surface as sf
from tools import write_plan_stub as wps

_RUN = "iterate-2026-11-01-q1-test"
_SPEC = ".shipwright/planning/01-adopted/spec.md"
_BASE_SPEC = "### FR-01.03 - Drafts\n\n- (E) [AC05] Given a draft, when saved, then it is kept.\n"
_SHA = "sha256:" + "b" * 64


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
