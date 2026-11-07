"""Integrity check of the event folders (issue 978, campaign S6, kill criterion 6)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`
from _events_fold_helpers import NEW, commit, drop, ev, git, make_repo, put  # noqa: E402

from lib.events_fold import apply_fold, apply_quarantine, plan_fold, plan_quarantine  # noqa: E402
from lib.events_fold_full import apply_full_fold  # noqa: E402
from lib.events_fold_io import name_problem  # noqa: E402
from lib.events_integrity import check_integrity  # noqa: E402
from lib.events_log import ARCHIVE_DIR, DROPS_DIR, QUARANTINE_DIR  # noqa: E402
from tools.verifiers.events_integrity_check import check_events_integrity  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
CHECKER = Path(__file__).resolve().parents[1] / "scripts" / "checks" / "check_events_integrity.py"
OLD_DROP = "run-old--aaaaaaaa--00000001.jsonl"


@pytest.fixture(name="repo")
def _repo(tmp_path):
    """main carries two committed drops; HEAD is a branch off it."""
    root = make_repo(tmp_path)
    drop(root, "run-old", ev("e1"), ev("e2"))
    drop(root, "run-two", ev("e3", NEW))
    commit(root, "drops on main")
    git(root, "branch", "base")
    git(root, "switch", "-q", "-c", "pr")
    return root


def _codes(root: Path, **kw) -> list[str]:
    return sorted({v.code for v in check_integrity(root, "base", "HEAD", **kw)})


def test_no_event_folders_anywhere_is_a_noop(tmp_path):
    root = make_repo(tmp_path)
    git(root, "branch", "base")
    (root / "x.txt").write_text("y\n", encoding="utf-8")
    commit(root)
    assert check_integrity(root, "base", "HEAD") == []


def test_adding_a_drop_is_clean(repo):
    drop(repo, "run-mine", ev("n1", NEW))
    commit(repo)
    assert _codes(repo) == []


def test_modifying_a_file_that_exists_at_the_merge_base_is_blocked(repo):
    path = repo / DROPS_DIR / OLD_DROP
    path.write_text(path.read_text(encoding="utf-8") + json.dumps(ev("sneaky")) + "\n", encoding="utf-8")
    commit(repo)
    assert _codes(repo) == ["modified_existing"]


def test_a_forged_run_id_append_to_another_runs_file_is_blocked(repo):
    """Appending as run X to the file of run X (key matches) is still a modify of a merge-base file."""
    path = repo / DROPS_DIR / OLD_DROP
    path.write_text(path.read_text(encoding="utf-8") + json.dumps(ev("fake", run="run-old")) + "\n", encoding="utf-8")
    commit(repo)
    assert _codes(repo, own_keys=("run-old",)) == ["modified_existing"]


def test_a_new_file_stamped_with_another_runs_id_is_a_forgery(repo):
    put(repo, DROPS_DIR, "run-mine--aaaaaaaa--00000009.jsonl", ev("f1", NEW, run="run-two"))
    commit(repo)
    assert _codes(repo) == ["forged_run_id"]


def test_a_file_under_a_key_the_change_does_not_own_is_flagged_when_owned_keys_are_given(repo):
    drop(repo, "run-other", ev("o1", NEW))
    commit(repo)
    assert _codes(repo) == [] and _codes(repo, own_keys=("run-mine",)) == ["foreign_key"]


def test_deleting_a_file_that_exists_at_the_merge_base_is_blocked(repo):
    (repo / DROPS_DIR / OLD_DROP).unlink()
    commit(repo)
    assert _codes(repo) == ["deleted_existing"]


def test_the_same_files_are_also_protected_in_archive_and_quarantine(tmp_path):
    root = make_repo(tmp_path)
    put(root, ARCHIVE_DIR, "fold-0123456789ab.jsonl", ev("a1"))
    put(root, QUARANTINE_DIR, "run-q--aaaaaaaa--00000001.jsonl", "junk")
    commit(root)
    git(root, "branch", "base")
    git(root, "switch", "-q", "-c", "pr")
    (root / ARCHIVE_DIR / "fold-0123456789ab.jsonl").unlink()
    put(root, QUARANTINE_DIR, "run-q--aaaaaaaa--00000001.jsonl", "edited")
    commit(root)
    got = {v.path: v.code for v in check_integrity(root, "base", "HEAD")}
    assert got == {f"{ARCHIVE_DIR}/fold-0123456789ab.jsonl": "deleted_existing",
                   f"{QUARANTINE_DIR}/run-q--aaaaaaaa--00000001.jsonl": "modified_existing"}


@pytest.mark.parametrize("name", ["../evil.jsonl", "a/../b.jsonl", "sub/x--aaaaaaaa--00000001.jsonl", "a\\b.jsonl",
                                  ".hidden--aaaaaaaa--00000001.jsonl", ("k" * 81) + "--aaaaaaaa--00000001.jsonl",
                                  "run--zz--00000001.jsonl", "run.jsonl", "", "..", "x\x00y.jsonl",
                                  "run--aaaaaaaa--00000001.jsonl\n"])   # a trailing newline must not slip through ($ would allow it)
def test_name_validation_refuses_traversal_and_malformed_keys(name):
    assert name_problem(DROPS_DIR, name)


def test_a_key_of_exactly_80_chars_and_dotted_keys_are_legal():
    assert name_problem(DROPS_DIR, ("k" * 80) + "--aaaaaaaa--00000001.jsonl") is None
    assert name_problem(DROPS_DIR, "campaign-x--S6.v1.2--aaaaaaaa--00000001.jsonl") is None
    assert name_problem(ARCHIVE_DIR, "fold-0123456789ab.jsonl") is None


def test_nested_and_malformed_paths_in_a_change_are_blocked(repo):
    put(repo, DROPS_DIR + "/sub", "x--aaaaaaaa--00000001.jsonl", ev("n1", NEW))
    put(repo, DROPS_DIR, ("k" * 90) + "--aaaaaaaa--00000001.jsonl", ev("n2", NEW))
    put(repo, DROPS_DIR, "notes.txt", ev("n3", NEW))
    commit(repo)
    assert _codes(repo) == ["bad_path"] and len(check_integrity(repo, "base", "HEAD")) == 3


def test_a_symlink_added_under_the_folder_is_blocked(repo):
    sha = subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--stdin"], input="../../etc/passwd",
                         capture_output=True, text=True, check=True).stdout.strip()
    git(repo, "update-index", "--add", "--cacheinfo", f"120000,{sha},{DROPS_DIR}/link--aaaaaaaa--00000001.jsonl")
    git(repo, "commit", "-q", "-m", "symlink")
    assert _codes(repo) == ["not_a_regular_file"]


def test_a_fold_commit_made_by_the_tool_is_clean(repo):
    assert apply_fold(repo, plan_fold(repo, base_ref="base", now=NOW))["status"] == "folded"
    commit(repo, "fold")
    assert _codes(repo) == []


def test_an_emergency_fold_commit_is_clean(repo):
    apply_fold(repo, plan_fold(repo, mode="emergency"))
    commit(repo, "emergency")
    assert _codes(repo) == []


def test_a_fold_that_loses_an_event_is_blocked(repo):
    apply_fold(repo, plan_fold(repo, base_ref="base", now=NOW))
    archive = next((repo / ARCHIVE_DIR).glob("*.jsonl"))
    archive.write_text(archive.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")   # drop e2
    commit(repo, "lossy fold")
    assert _codes(repo) == ["deleted_existing"]


def test_a_fold_with_a_tampered_event_is_blocked(repo):
    apply_fold(repo, plan_fold(repo, base_ref="base", now=NOW))
    archive = next((repo / ARCHIVE_DIR).glob("*.jsonl"))
    archive.write_text(archive.read_text(encoding="utf-8").replace("d e1", "d EDITED"), encoding="utf-8")
    commit(repo, "tampered fold")
    assert _codes(repo) == ["archive_injection", "deleted_existing"]


def test_a_quarantine_commit_made_by_the_tool_is_clean(tmp_path):
    root = make_repo(tmp_path)
    put(root, DROPS_DIR, "run-junk--aaaaaaaa--00000001.jsonl", "not json")
    drop(root, "run-fine", ev("f1"))
    commit(root, "main with a corrupt drop")
    git(root, "branch", "base")
    git(root, "switch", "-q", "-c", "pr")
    assert apply_quarantine(root, plan_quarantine(root, base_ref="base"))["status"] == "quarantined"
    commit(root, "quarantine")
    assert _codes(root) == []


def test_deleting_a_healthy_file_dressed_as_quarantine_is_blocked(repo):
    """The twin is byte-identical but the file had recoverable records at the base: not a quarantine."""
    src = repo / DROPS_DIR / OLD_DROP
    put(repo, QUARANTINE_DIR, OLD_DROP, *src.read_text(encoding="utf-8").splitlines())
    src.unlink()
    commit(repo)
    assert _codes(repo) == ["deleted_existing"]


def test_quarantine_needs_the_byte_identical_twin(tmp_path):
    root = make_repo(tmp_path)
    put(root, DROPS_DIR, "run-junk--aaaaaaaa--00000001.jsonl", "not json")
    commit(root)
    git(root, "branch", "base")
    git(root, "switch", "-q", "-c", "pr")
    (root / DROPS_DIR / "run-junk--aaaaaaaa--00000001.jsonl").unlink()
    put(root, QUARANTINE_DIR, "run-junk--aaaaaaaa--00000001.jsonl", "different bytes")
    commit(root)
    assert _codes(root) == ["deleted_existing"]


def test_a_full_fold_is_refused_unless_the_operator_allows_it(repo):
    apply_full_fold(repo)
    commit(repo, "full fold")
    assert _codes(repo) == ["deleted_existing"] and _codes(repo, allow_full_fold=True) == []


def test_cli_exit_codes_and_unresolvable_refs(repo):
    def run(*args):
        return subprocess.run([sys.executable, str(CHECKER), "--project-root", str(repo), *args],
                              capture_output=True, text=True, encoding="utf-8", timeout=120)

    assert run("--base-ref", "base").returncode == 0
    (repo / DROPS_DIR / OLD_DROP).unlink()
    commit(repo)
    bad = run("--base-ref", "base")
    assert bad.returncode == 1 and json.loads(bad.stdout)["violations"][0]["code"] == "deleted_existing"
    gone = run("--base-ref", "no-such-ref")
    assert gone.returncode == 2 and json.loads(gone.stdout)["status"] == "error"


def test_old_dates_are_not_part_of_the_rules(repo):
    """The integrity check never looks at age: only the fold TOOL does."""
    drop(repo, "run-ancient", ev("a1", "2001-01-01T00:00:00+00:00"))
    commit(repo)
    assert _codes(repo) == []


def test_the_keep_file_must_be_empty_and_can_never_be_deleted(repo):
    put(repo, DROPS_DIR, ".keep", "not empty")
    commit(repo)
    assert _codes(repo) == ["bad_path"]
    git(repo, "switch", "-q", "main")
    git(repo, "switch", "-q", "-c", "pr2")
    (repo / DROPS_DIR / ".keep").write_bytes(b"")
    commit(repo, "keep")
    git(repo, "branch", "base2")
    (repo / DROPS_DIR / ".keep").unlink()
    commit(repo, "remove keep")
    assert sorted({v.code for v in check_integrity(repo, "base2", "HEAD")}) == ["deleted_existing"]


def test_a_fold_that_also_edits_an_unrelated_drop_is_blocked(repo):
    """The fold exception is per deleted file: a mixed commit cannot smuggle a modification through it."""
    apply_fold(repo, plan_fold(repo, base_ref="base", now=NOW))
    survivor = repo / DROPS_DIR / "run-two--aaaaaaaa--00000001.jsonl"
    survivor.write_text(survivor.read_text(encoding="utf-8") + json.dumps(ev("sneaky")) + "\n", encoding="utf-8")
    commit(repo, "fold plus edit")
    got = {v.path: v.code for v in check_integrity(repo, "base", "HEAD")}
    assert got == {f"{DROPS_DIR}/run-two--aaaaaaaa--00000001.jsonl": "modified_existing"}


def test_an_archive_added_on_its_own_cannot_inject_events(repo):
    """A forged gate event hidden in an archive file (readers load the archive) is blocked."""
    put(repo, ARCHIVE_DIR, "fold-0123456789ab.jsonl", ev("forged", NEW, type="work_completed", adr_id="someone-elses-run"))
    commit(repo)
    assert _codes(repo) == ["archive_injection"] and _codes(repo, allow_full_fold=True) == []


def test_an_archive_must_carry_the_fold_name(repo):
    apply_fold(repo, plan_fold(repo, base_ref="base", now=NOW))
    archive = next((repo / ARCHIVE_DIR).glob("*.jsonl"))
    archive.rename(archive.with_name("my-archive.jsonl"))
    commit(repo)
    assert _codes(repo) == ["bad_path"]


@pytest.mark.parametrize("folder", ["Shipwright_Events.D", "SHIPWRIGHT_EVENTS.ARCHIVE"])
def test_a_case_variant_of_a_folder_name_is_blocked(repo, folder):
    """On a case-insensitive checkout these paths land inside the real folder and are read."""
    sha = subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--stdin"], input=json.dumps(ev("c1", NEW)),
                         capture_output=True, text=True, check=True).stdout.strip()
    git(repo, "update-index", "--add", "--cacheinfo", f"100644,{sha},{folder}/run-x--aaaaaaaa--00000001.jsonl")
    git(repo, "commit", "-q", "-m", "case variant")
    assert _codes(repo) == ["bad_path"]


def test_a_crlf_checkout_still_folds(repo):
    """core.autocrlf=true: the working copy is CRLF, the blob LF -- the drop is unchanged, not modified."""
    path = repo / DROPS_DIR / OLD_DROP
    path.write_bytes(path.read_bytes().replace(bytes([10]), bytes([13, 10])))
    assert len(plan_fold(repo, base_ref="base", now=NOW).selected) == 1


def test_the_full_fold_and_the_checker_agree_when_only_the_run_stamp_differs(repo):
    legacy = repo / "shipwright_events.jsonl"
    legacy.write_text(json.dumps(ev("e1")) + chr(10) + json.dumps(ev("e2")) + chr(10), encoding="utf-8")  # no run stamp
    commit(repo, "legacy log holds the same events without the stamp")
    git(repo, "branch", "-f", "base")
    apply_full_fold(repo)
    commit(repo, "full fold")
    assert _codes(repo, allow_full_fold=True) == []


def test_the_f11_check_catches_a_case_variant_and_passes_a_clean_branch(repo):
    git(repo, "update-index", "--add", "--cacheinfo",
        "100644," + subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--stdin"], input="x", capture_output=True,
                                   text=True, check=True).stdout.strip() + ",Shipwright_Events.D/x--aaaaaaaa--00000001.jsonl")
    git(repo, "commit", "-q", "-m", "case variant")
    git(repo, "update-ref", "refs/remotes/origin/main", "base")
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    bad = check_events_integrity(repo, "run-x")
    assert bad.ok is False and "case variant" in bad.detail
    git(repo, "reset", "-q", "--hard", "base")
    drop(repo, "run-mine", ev("n1", NEW))
    commit(repo)
    assert check_events_integrity(repo, "run-mine").ok is True      # the run id now decides which keys are the branch's own


def test_a_second_fold_of_an_overlapping_set_is_not_an_injection(repo):
    """Main already folded run-old; a branch that folded {run-old, run-two} must still pass once rebased."""
    apply_fold(repo, plan_fold(repo, mode="emergency"))
    commit(repo, "fold A (now on the trunk)")
    git(repo, "branch", "-f", "base")
    drop(repo, "run-two", ev("e3", NEW))                     # the overlap: run-two's event is already archived
    drop(repo, "run-three", ev("e9", NEW), nonce="00000002")
    commit(repo, "branch adds drops")
    git(repo, "branch", "-f", "base2", "HEAD")
    apply_fold(repo, plan_fold(repo, mode="emergency"))
    commit(repo, "fold B")
    assert sorted({v.code for v in check_integrity(repo, "base2", "HEAD")}) == []


def test_two_identical_quarantined_files_are_both_recognised(tmp_path):
    root = make_repo(tmp_path)
    for n in ("00000001", "00000002"):
        put(root, DROPS_DIR, f"run-junk--aaaaaaaa--{n}.jsonl", "not json")
    commit(root)
    git(root, "branch", "base")
    git(root, "switch", "-q", "-c", "pr")
    assert apply_quarantine(root, plan_quarantine(root, base_ref="base"))["status"] == "quarantined"
    commit(root, "quarantine two")
    assert _codes(root) == []


def test_an_added_drop_record_without_a_run_stamp_or_with_a_foreign_adr_id_is_a_forgery(repo):
    put(repo, DROPS_DIR, "run-a--aaaaaaaa--00000007.jsonl", ev("n1", NEW))                       # no run stamp
    put(repo, DROPS_DIR, "run-b--aaaaaaaa--00000008.jsonl",
        ev("n2", NEW, run="run-b", type="work_completed", adr_id="someone-elses-run"))
    commit(repo)
    assert [v.code for v in check_integrity(repo, "base", "HEAD")] == ["forged_run_id", "forged_run_id"]


def test_a_file_name_differing_only_in_case_from_an_existing_drop_is_blocked(repo):
    line = json.dumps(ev("n1", NEW, run="RUN-OLD"))
    sha = subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--stdin"], input=line, capture_output=True,
                         text=True, check=True).stdout.strip()
    git(repo, "update-index", "--add", "--cacheinfo", f"100644,{sha},{DROPS_DIR}/RUN-OLD--aaaaaaaa--00000001.jsonl")
    git(repo, "commit", "-q", "-m", "case-colliding name")
    assert "case_collision" in _codes(repo)
