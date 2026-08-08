"""P2.43 — the SKIP and FAILURE branches of `_absorb_dirty_triage_log`.

Sibling of `test_ensure_current_triage_absorb.py` (which covers the happy
paths), split for the same 300-line reason that module names.

These branches are the guard's whole safety argument: it commits into a live
repository, so every reason it declines to, and every way its two git calls can
fail, has to behave exactly as documented. They were originally argued as
"defensive, degrades no worse than pre-fix" and left to indirect coverage —
the F0 diff-coverage gate measured that at 65% and named the lines, which is
how the argument was found to be weaker than the docstring claimed: the
`triage-absorb-skipped-invalid` branch was credited to
`test_triage_validate.py`, but that suite exercises the VALIDATOR, never this
guard's decision to call it. Each test below drives a real git repository and
asserts the index afterwards, because "the index is left exactly as it was" is
the actual promise.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared/tests (helper)
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))  # shared/scripts — wins for `tools`

from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402
from tools import ensure_current as ec  # noqa: E402
from tools import integrate_main  # noqa: E402

_TRIAGE = ".shipwright/triage.jsonl"
_HEADER = '{"v":1,"schema":"triage","created":"2026-08-06T00:00:00Z"}'
_APPEND = (
    '{"event":"append","id":"trg-1","source":"compliance","severity":"low",'
    '"kind":"compliance","title":"t","detail":"d","ts":"2026-08-06T00:00:00Z"}'
)


def _staged(root: Path) -> str:
    return _git(root, "diff", "--cached", "--name-only").stdout


def _seed_tracked_log(work: Path) -> None:
    """A committed triage log plus an unrelated tracked file, so HEAD exists."""
    _set_repo_identity(work)
    _write(work, _TRIAGE, f"{_HEADER}\n")
    _write(work, "seed.txt", "seed\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed triage log")


def test_absorb_skips_an_untracked_triage_log(git_origin_repo) -> None:
    """Stage-3 doubt review, low: `git status --porcelain` reports an untracked
    file as `??`, and a guard that only asked "is it dirty?" would silently
    promote a brand-new log to tracked — shipping it in the PR as a side effect
    of a MERGE guard. Deciding a fresh log should start being tracked is not
    this function's job."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "seed.txt", "seed\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")

    _write(work, _TRIAGE, f"{_HEADER}\n{_APPEND}\n")  # never added

    assert ec._absorb_dirty_triage_log(work) is None
    assert _TRIAGE not in _staged(work), "an untracked log must not be staged"
    assert _git(work, "status", "--porcelain", "--", _TRIAGE).stdout.startswith("??"), \
        "it must still be untracked -- confirms the fixture set up the ?? state"


def test_absorb_skips_a_deleted_triage_log(git_origin_repo) -> None:
    """External review (openai, low): this log is append-only and nothing in the
    pipeline legitimately deletes it, so a deletion is not a background write to
    absorb — committing one would propagate the deletion to `main` through a
    guard the operator never asked to delete anything."""
    work, _origin = git_origin_repo
    _seed_tracked_log(work)

    (work / _TRIAGE).unlink()

    assert ec._absorb_dirty_triage_log(work) is None
    assert _TRIAGE not in _staged(work), "a deletion must never be staged"


def test_absorb_skips_when_the_log_cannot_be_read(git_origin_repo, monkeypatch) -> None:
    """The content is validated before staging, so an unreadable file must
    decline rather than stage bytes nothing checked."""
    work, _origin = git_origin_repo
    _seed_tracked_log(work)
    _write(work, _TRIAGE, f"{_HEADER}\n{_APPEND}\n")

    real_read_text = Path.read_text

    def _unreadable(self: Path, *a, **kw):
        if self.name == "triage.jsonl":
            raise OSError("simulated unreadable log")
        return real_read_text(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", _unreadable)

    assert ec._absorb_dirty_triage_log(work) is None
    assert _TRIAGE not in _staged(work)


def test_absorb_refuses_to_commit_torn_content(git_origin_repo) -> None:
    """Stage-3 doubt review, low: a torn write racing this call must not become
    the log's permanent next line. Pre-fix an invalid dirty file could still be
    thrown away with a plain `git checkout --`; committing it removes that
    escape. The sibling primitive `resolve_churn_conflicts` validates before it
    commits for the same reason."""
    work, _origin = git_origin_repo
    _seed_tracked_log(work)
    _write(work, _TRIAGE, f'{_HEADER}\n{_APPEND}\n{{"event":"appen\n')  # truncated record

    assert ec._absorb_dirty_triage_log(work) == "triage-absorb-skipped-invalid"
    assert _TRIAGE not in _staged(work), "torn content must never reach the index"


def test_absorb_skips_an_orphan_amend_same_as_an_orphan_status(git_origin_repo) -> None:
    """iterate-2026-08-08-triage-amend-event, AC11: an `amend` whose id has no
    `append` anywhere surfaces through `_absorb_dirty_triage_log` the same way
    an orphan `status` already does — both are non-empty
    `validate_triage_text` errors, so the guard declines to stage either."""
    work, _origin = git_origin_repo
    _seed_tracked_log(work)
    orphan_amend = '{"event":"amend","id":"trg-ghost","by":"cli","title":"x"}'
    _write(work, _TRIAGE, f"{_HEADER}\n{orphan_amend}\n")

    assert ec._absorb_dirty_triage_log(work) == "triage-absorb-skipped-invalid"
    assert _TRIAGE not in _staged(work), "an orphan amend must never reach the index"


def test_absorb_reports_a_failed_stage_and_leaves_the_index_alone(
    git_origin_repo, monkeypatch, capsys,
) -> None:
    """A failed `git add` never ran, so there is nothing to undo — but the
    failure must be DIAGNOSABLE. Stage-3 doubt review, medium: the original code
    discarded git's stderr entirely, so an operator saw a bare step token
    followed by the pre-fix `merge_failed` symptom with no hint that staging had
    been refused (this repo's own pre-commit anti-ratchet hook is one way it
    can be)."""
    work, _origin = git_origin_repo
    _seed_tracked_log(work)
    _write(work, _TRIAGE, f"{_HEADER}\n{_APPEND}\n")

    real_git = integrate_main._git

    def _add_fails(root, *args, **kw):
        if args and args[0] == "add":
            return subprocess.CompletedProcess(list(args), 1, "", "fatal: simulated add failure")
        return real_git(root, *args, **kw)

    monkeypatch.setattr(integrate_main, "_git", _add_fails)

    assert ec._absorb_dirty_triage_log(work) == "triage-absorb-add-failed"

    monkeypatch.undo()
    assert _TRIAGE not in _staged(work), "a failed add must leave the index untouched"
    assert "simulated add failure" in capsys.readouterr().err, \
        "git's stderr must reach the operator, not be swallowed"


def test_absorb_resets_the_index_when_the_commit_fails(
    git_origin_repo, monkeypatch, capsys,
) -> None:
    """Stage-3 doubt review, medium: `git add` mutates the index BEFORE the
    commit is attempted, so a commit-failure path that simply returned would
    leave the log STAGED — strictly worse than the dirty state the guard started
    from, because a later `git merge --abort` can refuse on a staged,
    not-up-to-date path exactly as the original merge did. The reset is what
    keeps the failure no worse than not having run.

    Recorded in the spec's ledger as `untestable` on the grounds that forcing a
    real `git commit` to fail would destabilize the shared fixture. Monkeypatching
    the module-object seam `integrate_main._git` (ADR-045) tests it without
    touching the repository at all, so the row is now `tested`."""
    work, _origin = git_origin_repo
    _seed_tracked_log(work)
    _write(work, _TRIAGE, f"{_HEADER}\n{_APPEND}\n")

    real_git = integrate_main._git

    def _commit_fails(root, *args, **kw):
        if args and args[0] == "commit":
            return subprocess.CompletedProcess(list(args), 1, "", "fatal: simulated commit refusal")
        return real_git(root, *args, **kw)

    monkeypatch.setattr(integrate_main, "_git", _commit_fails)

    assert ec._absorb_dirty_triage_log(work) == "triage-absorb-commit-failed"

    monkeypatch.undo()
    assert _TRIAGE not in _staged(work), \
        "the reset must have run -- a staged-but-uncommitted log is the worse state"
    assert (work / _TRIAGE).read_text(encoding="utf-8").endswith(f"{_APPEND}\n"), \
        "the reset unstages only; the producer's content must survive in the worktree"
    assert "simulated commit refusal" in capsys.readouterr().err


def test_a_failed_diagnostic_never_crashes_the_guard(git_origin_repo, monkeypatch) -> None:
    """`_diag` swallows its own errors on purpose. The guard runs immediately
    before a merge and is documented as never raising, so a stderr that refuses
    the write must still yield the ordinary failure token — a best-effort
    diagnostic that could propagate would be strictly worse than no diagnostic."""
    work, _origin = git_origin_repo
    _seed_tracked_log(work)
    _write(work, _TRIAGE, f"{_HEADER}\n{_APPEND}\n")

    real_git = integrate_main._git

    def _add_fails(root, *args, **kw):
        if args and args[0] == "add":
            return subprocess.CompletedProcess(list(args), 1, "", "fatal: simulated add failure")
        return real_git(root, *args, **kw)

    class _BrokenStderr:
        def write(self, _text: str) -> int:
            raise OSError("stderr is gone")

    monkeypatch.setattr(integrate_main, "_git", _add_fails)
    monkeypatch.setattr(ec.sys, "stderr", _BrokenStderr())

    assert ec._absorb_dirty_triage_log(work) == "triage-absorb-add-failed"
