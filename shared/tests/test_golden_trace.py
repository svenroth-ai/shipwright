"""The trace: normalization, masking, whitelist, refs and commit content (golden-trace harness)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.covers("FR-01.09/AC14")  # test support for the changelog pilot (programme P2a)
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "shared" / "testkit"))

import golden_trace as gt  # noqa: E402
import release_scratch as rs  # noqa: E402

SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture
def scratch(tmp_path: Path) -> rs.Scratch:
    return rs.build_scratch(tmp_path / "s")


def commit(s: rs.Scratch, name: str, text: str, message: str) -> None:
    (s.repo / name).parent.mkdir(parents=True, exist_ok=True)
    (s.repo / name).write_text(text, encoding="utf-8")
    s.git("add", "-A")
    s.git("commit", "-q", "-m", message)


def test_normalize_replaces_what_differs_between_runs():
    text = f"commit {SHA} at 2026-11-17T10:15:56.264589+00:00 on 2026-11-17 run project-20261117-125101955883"
    text += " id 123e4567-e89b-12d3-a456-426614174000 session s-42\r\n"
    got = gt.normalize_text(text, literals={"s-42": "session"})
    assert got == "commit <sha> at <ts> on <date> run project-<stamp> id <uuid> session <session>\n"


def test_normalize_maps_every_path_form_to_its_label(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    text = f"{repo.as_posix()}/a {repo} {repo.as_uri()}/b {tmp_path.as_posix()}/origin.git"
    got = gt.normalize_text(text, paths={"root": tmp_path, "repo": repo})
    assert got == "<repo>/a <repo> <repo>/b <root>/origin.git"
    assert gt.normalize_text(f"{repo}\\sub\\n.md", paths={"repo": repo}) == "<repo>/sub/n.md"  # one separator on every OS


def test_two_scratches_in_different_directories_give_the_same_trace(tmp_path):
    a, b = rs.build_scratch(tmp_path / "a" / "deep"), rs.build_scratch(tmp_path / "b")
    assert gt.dumps(gt.collect(a, files=["CHANGELOG.md"])) == gt.dumps(gt.collect(b, files=["CHANGELOG.md"]))


def test_the_trace_records_commits_changed_content_refs_and_status(scratch):
    scratch.git("tag", "-a", "v0.2.0", "-m", "Release v0.2.0", "HEAD~1")
    commit(scratch, "docs/new.md", "hello 2026-11-17\n", "docs: add new")
    (scratch.repo / "stray.txt").write_text("x", encoding="utf-8")
    trace = gt.collect(scratch, files=["docs/*.md"])
    last = trace["commits"][-1]
    assert last["subject"] == "docs: add new" and last["changes"] == [{"status": "A", "path": "docs/new.md"}]
    assert last["blobs"] == {"docs/new.md": "hello <date>\n"}
    tag = trace["refs"]["tags"]["v0.2.0"]
    assert (tag["type"], tag["message"], tag["target"].startswith("release 0.1.0@2#")) == ("tag", "Release v0.2.0", True)
    assert trace["refs"]["tags"]["v0.1.0"]["type"] == "commit"
    assert trace["refs"]["branches"]["main"].startswith("docs: add new@4#")
    assert trace["origin"]["branches"]["main"].startswith("chore: record phase state@3#")  # origin has not seen the new commit
    assert trace["status"] == ["?? stray.txt"] and trace["files"] == {"docs/new.md": "hello <date>\n"}


def test_a_tag_on_the_wrong_commit_changes_the_trace(scratch):
    commit(scratch, "a.txt", "a", "feat: a")
    right = gt.collect(scratch)
    scratch.git("tag", "v0.2.0", "HEAD")
    tagged_right = gt.collect(scratch)
    scratch.git("tag", "-f", "v0.2.0", "HEAD~1")
    assert gt.collect(scratch) != tagged_right and tagged_right != right


def test_judgement_files_and_release_notes_are_masked_but_still_present(scratch):
    commit(scratch, "notes/upgrade.md", "the model wrote this", "docs: upgrade note")
    (scratch.repo / "n.md").write_text("model prose", encoding="utf-8")
    scratch.run([*json.loads(scratch.env["SHIPWRIGHT_TEST_GH_ARGV_PREFIX"]), "release", "create", "v0.1.0",
                 "--notes-file", str(scratch.repo / "n.md")], check=True)
    trace = gt.collect(scratch, files=["notes/*.md"], judgement_globs=["notes/*.md"])
    assert trace["commits"][-1]["blobs"] == {"notes/upgrade.md": gt.MASK}
    assert trace["files"] == {"notes/upgrade.md": gt.MASK}
    assert trace["stub"]["releases"] == {"v0.1.0": {"title": "v0.1.0", "notes": gt.MASK}}
    assert "model prose" not in gt.dumps(trace)
    create = trace["stub"]["argv"][0]["argv"]
    assert create[create.index("--notes-file") + 1] == "<repo>/n.md"  # the temp path is normalized in the argv log


def test_only_whitelisted_output_fields_are_recorded_and_a_reason_keeps_its_prefix():
    out = {"status": "failed", "reason": "seam_invalid:/abs/path detail", "version": "1.2.0", "noise": "x",
           "pathspec": ["a"], "elapsed": 1.2}
    assert gt._fields(out, gt.OUTPUT_WHITELIST) == {"status": "failed", "reason": "seam_invalid", "version": "1.2.0",
                                                    "pathspec": ["a"]}


def test_steps_and_the_argv_log_are_part_of_the_trace(scratch):
    prefix = json.loads(scratch.env["SHIPWRIGHT_TEST_GH_ARGV_PREFIX"])
    scratch.run([*prefix, "release", "view", "v9.9.9", "--repo", rs.FAKE_SLUG])
    steps = [gt.StepResult("prepare", 0, {"status": "ok", "junk": 1}), gt.StepResult("sync", 1, {})]
    trace = gt.collect(scratch, steps)
    assert trace["steps"] == [{"step": "prepare", "exit_code": 0, "fields": {"status": "ok"}},
                              {"step": "sync", "exit_code": 1, "fields": {}}]
    assert trace["stub"]["argv"] == [{"argv": ["release", "view", "v9.9.9", "--repo", rs.FAKE_SLUG], "exit": 1}]


def test_dumps_is_one_stable_form():
    text = gt.dumps({"b": 1, "a": ["é"]})
    assert text == '{\n  "a": [\n    "é"\n  ],\n  "b": 1\n}\n'


def test_a_judgement_file_committed_and_then_deleted_is_still_masked(scratch):
    commit(scratch, "notes/upgrade.md", "the model wrote this", "docs: upgrade note")
    scratch.git("rm", "-q", "notes/upgrade.md")
    scratch.git("commit", "-q", "-m", "docs: drop it")
    trace = gt.collect(scratch, judgement_globs=["notes/*.md"])
    assert trace["commits"][-2]["blobs"] == {"notes/upgrade.md": gt.MASK}
    assert "the model wrote this" not in gt.dumps(trace)


def test_step_output_is_normalized_and_inline_release_notes_are_masked(scratch):
    path = str(scratch.repo / "a.txt")
    trace = gt.collect(scratch, [gt.StepResult("aggregate", 0, {"status": "ok", "pathspec": [path]})])
    assert trace["steps"][0]["fields"]["pathspec"] == ["<repo>/a.txt"]
    prefix = json.loads(scratch.env["SHIPWRIGHT_TEST_GH_ARGV_PREFIX"])
    scratch.run([*prefix, "release", "create", "v0.1.0", "--notes", "model prose one"], check=True)
    scratch.run([*prefix, "release", "view", "v0.1.0"], check=True)
    scratch.run([*prefix, "release", "create", "v9.9.9", "--notes=model prose two"])
    scratch.run([*prefix, "release", "create", "v9.9.8", "-n", "model prose three"])
    text = gt.dumps(gt.collect(scratch))
    assert "model prose" not in text and "--notes=" + gt.MASK in text


def test_a_short_sha_of_a_known_commit_is_normalized_and_a_release_date_literal_is_kept_distinct(scratch):
    head = scratch.git("rev-parse", "HEAD")
    text = gt.dumps(gt.collect(scratch, [gt.StepResult("x", 0, {"status": head[:9]})]))
    assert head[:9] not in text and '"status": "<sha>"' in text
    assert gt.normalize_text("released 2026-11-17", literals={"2026-11-17": "release_date"}) == "released <release_date>"
    assert gt.normalize_text("released 2026-11-18", literals={"2026-11-17": "release_date"}) == "released <date>"


def test_the_recorder_reads_git_under_its_own_environment_not_the_users(scratch, tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    config = "[status]\n\tshowUntrackedFiles = no\n"
    (home / ".gitconfig").write_text(config, encoding="utf-8")
    for name in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(name, str(home))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "elsewhere"))
    (scratch.repo / "stray.txt").write_text("x", encoding="utf-8")
    assert gt.collect(scratch)["status"] == ["?? stray.txt"]


def test_a_path_with_non_ascii_characters_keeps_its_blob(scratch):
    commit(scratch, "docs/über.md", "hello", "docs: umlaut")
    assert gt.collect(scratch)["commits"][-1]["blobs"] == {"docs/über.md": "hello"}


def test_a_commit_amended_after_it_was_tagged_changes_the_trace(scratch):
    commit(scratch, "a.txt", "a", "chore(release): v0.2.0")
    scratch.git("tag", "v0.2.0")
    before = gt.collect(scratch)
    (scratch.repo / "events.jsonl").write_text("{}", encoding="utf-8")
    scratch.git("add", "-A")
    scratch.git("commit", "-q", "--amend", "--no-edit")  # same subject, same depth, one more file
    assert gt.collect(scratch)["refs"]["branches"] != before["refs"]["branches"]
    assert gt.collect(scratch)["all_commits"] != before["all_commits"]


def test_an_extra_commit_on_a_branch_merged_and_deleted_still_changes_the_trace(scratch):
    prefix = json.loads(scratch.env["SHIPWRIGHT_TEST_GH_ARGV_PREFIX"])

    def run(extra: bool):
        s = rs.build_scratch(scratch.root.parent / f"m{int(extra)}")
        s.git("checkout", "-q", "-b", "release/x")
        commit(s, "a.txt", "a", "chore(release): v0.2.0")
        if extra:
            commit(s, "b.txt", "b", "chore: stray")
        s.git("push", "-q", "origin", "release/x")
        for args in (["pr", "create", "--title", "t", "--body", "b", "--base", "main"],
                     ["pr", "merge", "--merge", "--delete-branch"]):
            s.run([*prefix, *args], check=True)
        s.git("checkout", "-q", "main")
        return gt.collect(s)

    plain, stray = run(False), run(True)
    assert plain["origin"]["branches"] != stray["origin"]["branches"] or plain["all_commits"]["origin"] != stray["all_commits"]["origin"]
    assert len(stray["all_commits"]["origin"]) == len(plain["all_commits"]["origin"]) + 1


def test_the_git_bash_form_of_a_path_is_normalized_too(tmp_path):
    root = Path("C:/Users/x/repo") if sys.platform == "win32" else tmp_path
    posix = root.as_posix()
    msys = "/" + posix[0].lower() + posix[2:] if sys.platform == "win32" else posix
    assert gt.normalize_text(f"cd {msys}/sub", paths={"repo": root}) == "cd <repo>/sub"
