"""`suite_resume_state` - what a red F0 run leaves behind, and when it is refused."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.suite_resume_state as st  # noqa: E402
from scripts.tools.suite_units import Unit  # noqa: E402

_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
_UNIT_KEYS = {"sig": "s", "outcome": "pass", "lastfailed": None, "test_files": [], "reuses": 0}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(root), env=_ENV, capture_output=True,
                   text=True, check=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "plugins" / "p" / "tests").mkdir(parents=True)
    (root / "plugins" / "p" / "tests" / "test_x.py").write_text("def test_x(): pass\n")
    (root / "plugins" / "p" / "scripts").mkdir()
    (root / "plugins" / "p" / "scripts" / "m.py").write_text("x = 1\n")
    (root / "SKILL.md").write_text("# skill\n")
    (root / ".gitignore").write_text(".shipwright/\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    return root


def _save(root: Path, snap, **kw) -> bool:
    args = {"run_id": "r", "invocation": "r@1", "snapshot": snap, "chain": (),
            "entries": {"u": {**_UNIT_KEYS, "report": None, "cov": None}}}
    args.update(kw)
    return st.save_state(root, **args)


def test_the_snapshot_hashes_every_file_not_only_python(repo):
    before = st.tree_snapshot(repo)
    (repo / "SKILL.md").write_text("# skill, edited\n")
    (repo / "notes.json").write_text("{}")  # untracked, not ignored
    after = st.tree_snapshot(repo)

    assert before.digest != after.digest
    assert st.changed_files(before.files, after.files) == ["SKILL.md", "notes.json"]
    assert after.base_sha == before.base_sha and len(after.base_sha) == 40


def test_ignored_files_do_not_enter_the_snapshot(repo):
    (repo / ".shipwright").mkdir()
    (repo / ".shipwright" / "scratch").write_text("x")
    assert not any(p.startswith(".shipwright") for p in st.tree_snapshot(repo).files)


def test_no_snapshot_outside_git_or_without_a_merge_base(tmp_path, repo):
    assert st.tree_snapshot(tmp_path) is None
    assert st.tree_snapshot(repo, base_ref="origin/nope") is None


def test_a_deleted_tracked_file_is_marked_not_fatal(repo):
    (repo / "SKILL.md").unlink()
    assert st.tree_snapshot(repo).files["SKILL.md"] == "-"


def test_state_round_trips_with_its_files(repo, tmp_path):
    snap = st.tree_snapshot(repo)
    report, cov = tmp_path / "r.xml", tmp_path / "c"
    report.write_text("<testsuites/>")
    cov.write_bytes(b"cov")
    entry = {**_UNIT_KEYS, "outcome": "test_failure", "lastfailed": ["t::a"],
             "report": report, "cov": cov}
    assert _save(repo, snap, chain=("a@0",), entries={"shared/tests": entry})

    state, why = st.load_state(repo)

    assert why == "" and state.manifest["chain"] == ["a@0"]
    rec = state.manifest["units"]["shared/tests"]
    assert rec["lastfailed"] == ["t::a"]
    assert (state.directory / rec["report"]).read_text() == "<testsuites/>"
    assert (state.directory / rec["cov"]).read_bytes() == b"cov"
    assert state.tree == snap.files and state.manifest["base_sha"] == snap.base_sha


def test_a_missing_pointer_means_no_state(repo):
    assert st.load_state(repo) == (None, st.NO_STATE)


def test_an_edited_stored_file_is_torn_and_refused(repo, tmp_path):
    report = tmp_path / "r.xml"
    report.write_text("<a/>")
    _save(repo, st.tree_snapshot(repo),
          entries={"u": {**_UNIT_KEYS, "report": report, "cov": None}})
    state, _ = st.load_state(repo)
    (state.directory / "reports" / "u.xml").write_text("<tampered/>")

    assert st.load_state(repo) == (None, "saved state is torn or edited (reports/u.xml)")


def _repin(root: Path, state) -> None:
    """Re-point CURRENT at the (edited) manifest: the way a forger who also fixed the pin
    would look, so the check UNDER test is the one after the pin."""
    pin = st._sha((state.directory / "manifest.json").read_bytes())
    (st.store_dir(root) / "CURRENT").write_text(f"{state.directory.name}\n{pin}")


def test_a_manifest_edit_that_stays_valid_json_is_refused(repo, tmp_path):
    report = tmp_path / "r.xml"
    report.write_text("<a/>")
    _save(repo, st.tree_snapshot(repo), entries={
        "u": {**_UNIT_KEYS, "outcome": "test_failure", "lastfailed": ["t::a"],
              "report": report, "cov": None}})
    state, _ = st.load_state(repo)
    path = state.directory / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["units"]["u"]["outcome"] = "pass"  # a red unit made to look green
    path.write_text(json.dumps(manifest))

    assert st.load_state(repo) == (None, "saved state is torn or edited (manifest.json)")


@pytest.mark.parametrize("pointer", ["..", ".", "x/..", ""])
def test_a_pointer_must_name_a_directory_inside_the_store(repo, pointer):
    _save(repo, st.tree_snapshot(repo))
    (st.store_dir(repo) / "CURRENT").write_text(pointer)
    assert st.load_state(repo) == (None, "saved state is unreadable (bad pointer)")


def test_a_manifest_from_the_future_is_refused(repo):
    _save(repo, st.tree_snapshot(repo))
    assert st.load_state(repo, now=0)[0] is None


@pytest.mark.parametrize("break_it, expected", [
    (lambda m: m.write_text("{not json"), "saved state is unreadable or torn"),
    (lambda m: m.write_text(json.dumps({"schema_version": 99})),
     "saved state has another schema version"),
])
def test_an_unreadable_or_foreign_manifest_is_refused(repo, break_it, expected):
    _save(repo, st.tree_snapshot(repo))
    state, _ = st.load_state(repo)
    break_it(state.directory / "manifest.json")
    _repin(repo, state)
    assert st.load_state(repo) == (None, expected)


def test_a_manifest_naming_an_unverified_file_is_refused(repo, tmp_path):
    report = tmp_path / "r.xml"
    report.write_text("<a/>")
    _save(repo, st.tree_snapshot(repo),
          entries={"u": {**_UNIT_KEYS, "report": report, "cov": None}})
    state, _ = st.load_state(repo)
    path = state.directory / "manifest.json"
    manifest = json.loads(path.read_text())
    del manifest["sha256"]["reports/u.xml"]
    path.write_text(json.dumps(manifest))
    _repin(repo, state)

    assert st.load_state(repo) == (None, "saved state is malformed")


def test_a_state_older_than_a_day_is_refused(repo):
    _save(repo, st.tree_snapshot(repo))
    assert st.load_state(repo, now=10**12) == (None, "saved state is older than 24 hours")


def test_a_pointer_that_escapes_the_store_is_refused(repo):
    _save(repo, st.tree_snapshot(repo))
    (st.store_dir(repo) / "CURRENT").write_text("..")
    assert st.load_state(repo)[0] is None


def test_the_new_state_replaces_the_old_one_and_prunes_it(repo):
    snap = st.tree_snapshot(repo)
    _save(repo, snap, run_id="one")
    first = st.load_state(repo)[0].directory
    _save(repo, snap, run_id="two")

    state, _ = st.load_state(repo)
    assert state.manifest["run_id"] == "two" and not first.exists()


def test_a_failed_publication_keeps_the_old_state_intact(repo, monkeypatch):
    snap = st.tree_snapshot(repo)
    _save(repo, snap, run_id="keep")

    def boom(*_a, **_k):
        raise OSError("disk full")
    monkeypatch.setattr(st.os, "replace", boom)
    with pytest.warns(UserWarning, match="could not save state"):
        assert _save(repo, snap, run_id="lost") is False
    monkeypatch.undo()

    assert st.load_state(repo)[0].manifest["run_id"] == "keep"
    assert len(list(st.store_dir(repo).iterdir())) == 2  # CURRENT + the kept directory


def test_clear_state_spends_the_token(repo):
    _save(repo, st.tree_snapshot(repo))
    st.clear_state(repo)
    assert st.load_state(repo) == (None, st.NO_STATE)
    assert [p for p in st.store_dir(repo).iterdir()] == []


def test_state_is_keyed_by_checkout(repo, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    assert st.store_dir(repo) != st.store_dir(other)


def test_unit_files_and_signature(repo):
    snap = st.tree_snapshot(repo)
    unit = Unit(id="p", cwd="plugins/p", target="tests")
    shared = Unit(id="shared/tests", cwd=".", target="plugins/p/tests")

    [only] = st.unit_test_files(snap, unit)
    assert only.startswith("plugins/p/tests/test_x.py:")
    assert st.unit_test_files(snap, shared) == [only]
    assert st.unit_signature(unit) == st.unit_signature(unit)
    assert st.unit_signature(unit) != st.unit_signature(
        Unit(id="p", cwd="plugins/p", target="tests", markers=("-m", "x")))
