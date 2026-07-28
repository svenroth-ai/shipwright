"""Reading committed content safely — the primitives behind the CI supply-chain
fingerprint (iterate-2026-07-28-ci-ack-per-run-home).

`git show <commit>:<path>` has two defects this module exists to avoid, and both
were live in this repo. The MAX_PATH trap was found by a round-trip test failing
with `Filename too long`; the absent-vs-broken conflation was found by Stage-2
review, which observed that the iterate had fixed one of the spelling's two
occurrences and left the other in `commit_reader` — the reader feeding the
security-load-bearing fingerprint, where a failed read hashed as the same
`<absent>` sentinel a genuinely deleted path gets.

These tests pin the distinctions that fix depends on.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_ci_supplychain_ack_per_run_home import (  # noqa: E402
    _RUN,
    _ack,
    _write_per_run_ack,
)
from test_integrate_main import _git, _write  # noqa: E402
from tools.verifiers import ci_supplychain as cs  # noqa: E402
from tools.verifiers.git_blob_read import (  # noqa: E402
    GitReadError,
    blob_oid,
    committed_bytes_reader,
    content_fingerprint,
    worktree_bytes_reader,
)
from tools.verifiers.integration_coverage import _iterate_changed_paths  # noqa: E402

_WF = ".github/workflows/ci.yml"


def _commit(wt: Path, *paths: str) -> str:
    _git(wt, "config", "user.email", "iterate@test.invalid")
    _git(wt, "config", "user.name", "Iterate Test")
    _git(wt, "add", *(paths or ("-A",)))
    _git(wt, "commit", "-m", "c")
    return _git(wt, "rev-parse", "HEAD").stdout.strip()


# --- absent is not the same as broken --------------------------------------

def test_absent_path_is_absent_not_an_error(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    wt = make_worktree(work, "gbr-absent")
    _write(wt, _WF, "on: push\n")
    commit = _commit(wt, _WF)

    oid, err = blob_oid(wt, commit, ".github/workflows/nope.yml")
    assert (oid, err) == (None, None), "genuine absence must permit a fallback"


def test_unreadable_commit_is_an_error_not_an_absence(git_origin_repo, make_worktree):
    """If a broken repo read looked like 'absent', an infrastructure fault would
    become a trust path — the working copy would answer for the commit."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "gbr-badcommit")
    _write(wt, _WF, "on: push\n")
    _commit(wt, _WF)

    oid, err = blob_oid(wt, "0" * 40, _WF)
    assert oid is None
    assert err and "refusing" in err


def test_a_tree_is_not_a_regular_file(git_origin_repo, make_worktree):
    """Mode/type are checked, so a non-blob at the path cannot be read as content."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "gbr-tree")
    _write(wt, ".github/workflows/ci.yml", "on: push\n")
    commit = _commit(wt, ".github")

    oid, err = blob_oid(wt, commit, ".github/workflows")
    assert oid is None
    assert err and "not a regular file" in err


def test_reader_raises_rather_than_reporting_absent(git_origin_repo, make_worktree):
    """The fail-open this replaced: every failure became None, and None hashes as
    the `<absent>` sentinel that a genuinely DELETED path gets."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "gbr-raise")
    _write(wt, _WF, "on: push\n")
    _commit(wt, _WF)

    read = committed_bytes_reader(wt, "0" * 40)
    with pytest.raises(GitReadError):
        read(_WF)


def test_pathspec_metacharacters_do_not_glob_onto_another_entry(
        git_origin_repo, make_worktree):
    """`git show <rev>:<path>` took a LITERAL path; `ls-tree -- <path>` takes a
    PATHSPEC with wildmatch, so swapping them made `ci[1].yml` glob-match `ci1.yml`
    and hash the wrong file's bytes under the right file's label — a regression the
    OID rewrite introduced (Stage-3 doubt review)."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "gbr-glob")
    (wt / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (wt / ".github" / "workflows" / "ci1.yml").write_text("on: push\n# decoy\n")
    commit = _commit(wt, ".github")

    # `ci[1].yml` does NOT exist; as a pathspec it would match `ci1.yml`.
    oid, err = blob_oid(wt, commit, ".github/workflows/ci[1].yml")
    assert oid is None, "a non-existent name must not resolve via glob"
    assert err is None, "and it is genuinely absent, not an error"


def test_worktree_ack_path_that_is_a_directory_is_an_error(
        git_origin_repo, make_worktree):
    """"The first PRESENT source is terminal" must hold as written: a path that
    exists but is not a regular file used to advance silently to the legacy leg
    (Stage-3 doubt review)."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "gbr-ackdir")
    (wt / cs.ack_relpath(_RUN)).mkdir(parents=True, exist_ok=True)

    ack, err, source = cs.load_ack(wt, _RUN, "")
    assert ack is None and source == ""
    assert err and "not a regular file" in err


# --- the fingerprint --------------------------------------------------------

def test_crlf_and_lf_hash_alike():
    """Under core.autocrlf the worktree file is CRLF while its blob is LF. git
    treats those as the same file, so the fingerprint must too — otherwise every
    Windows author red-lines on a file they never edited."""
    crlf = content_fingerprint([_WF], lambda _r: b"on: push\r\njobs:\r\n")
    lf = content_fingerprint([_WF], lambda _r: b"on: push\njobs:\n")
    assert crlf == lf


def test_bytes_and_str_readers_agree_for_valid_utf8():
    """Keeps acks recorded before the bytes switch valid on in-flight branches."""
    as_bytes = content_fingerprint([_WF], lambda _r: b"on: push\n")
    as_text = content_fingerprint([_WF], lambda _r: "on: push\n")
    assert as_bytes == as_text


def test_non_utf8_content_is_stable_across_the_real_seam(git_origin_repo, make_worktree):
    """The bug bytes fixed: the worktree side decoded with errors='replace' and the
    git side with errors='ignore', so one latin-1 byte produced two digests and the
    gate red-lined permanently, naming the wrong cause.

    The first version of this test compared `content_fingerprint` to ITSELF with the
    same lambda — it touched neither reader, so restoring both pre-change text
    readers left it green (Stage-3 doubt review). It now drives the two real readers
    across a real commit, which is the only thing that can prove a seam.
    """
    work, _o = git_origin_repo
    wt = make_worktree(work, "gbr-latin1")
    (wt / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (wt / _WF).write_bytes(b"# caf\xe9\non: push\n")   # deliberately not UTF-8
    commit = _commit(wt, _WF)

    from_worktree = content_fingerprint([_WF], worktree_bytes_reader(wt))
    from_commit = content_fingerprint([_WF], committed_bytes_reader(wt, commit))
    assert from_worktree == from_commit


def test_non_ascii_workflow_name_still_binds_content(git_origin_repo, make_worktree):
    """The measured false-green (Stage-3 doubt review). git quotes a non-ASCII path
    and escapes its bytes octally; the escaped name addressed no file, so BOTH
    readers reported "absent" and the fingerprint stopped depending on content —
    ack a benign workflow, then commit `pull_request_target:` under the same name,
    same digest. Pinned end-to-end through the real path producer."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "gbr-nonascii")
    (wt / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    target = wt / ".github" / "workflows" / "résumé-check.yml"
    target.write_text("on: push\n# benign\n", encoding="utf-8")
    base = _commit(wt, ".github")

    changed = _iterate_changed_paths(wt, base) or []
    benign = cs.ci_supplychain_fingerprint(changed, committed_bytes_reader(wt, base))

    target.write_text("on: pull_request_target\n# echo secret\n", encoding="utf-8")
    evil_commit = _commit(wt, ".github")
    changed2 = _iterate_changed_paths(wt, evil_commit) or []
    evil = cs.ci_supplychain_fingerprint(
        changed2, committed_bytes_reader(wt, evil_commit))

    assert benign != evil, (
        "a non-ASCII workflow name must still bind CONTENT — equal digests here "
        "mean the ack licenses any edit to that file")


def test_absent_is_distinct_from_empty():
    """Deleting a security workflow must not hash like an empty one."""
    absent = content_fingerprint([_WF], lambda _r: None)
    empty = content_fingerprint([_WF], lambda _r: b"")
    assert absent != empty


# --- the gate fails closed on an unreadable CI file -------------------------

def test_gate_fails_closed_when_ci_content_cannot_be_read(
        git_origin_repo, make_worktree, monkeypatch):
    """End of the fail-open chain: a read failure must STOP the run, never be
    hashed as `<absent>` and silently compared against an ack recorded for a
    deletion. Patched by MODULE OBJECT, never by dotted string (ADR-045)."""
    work, _o = git_origin_repo
    wt = make_worktree(work, "gbr-gate-closed")
    _write(wt, _WF, "on: push\n")
    # A VALID ack, so the run reaches the fingerprint step instead of stopping
    # earlier on "no acknowledgement recorded" — otherwise this would pass for the
    # wrong reason and prove nothing about the read failure.
    rel = _write_per_run_ack(wt, _ack())
    commit = _commit(wt, _WF, rel)

    def exploding_reader(_root, _commit):
        def read(rel_):
            raise GitReadError(f"{rel_} is present but unreadable")
        return read

    monkeypatch.setattr(cs, "committed_bytes_reader", exploding_reader)
    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is False
    assert "could not" in res.detail and "refusing" in res.detail
