"""``source_state_capture`` — WHAT the capture answers (``trg-f5ae5371``).

The defect this pins: every automatic producer writes TRACKED files before a
``grade_snapshot`` is emitted, so measuring at emit time reads ``dirty=true`` on a
pristine tree. Measured on four producers, reproduced end-to-end with zero
uncommitted source.

Run against a REAL git repo, because "the first capture wins" is a claim about
process behaviour rather than about a mock. HOW the answer travels — environment
inheritance, and the run+tree binding that makes an inherited value safe — is the
sibling module ``test_source_state_capture_transport.py``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from source_state_capture import (  # noqa: E402
    ENV_DIRTY, ENV_DIRTY_ROOT, ENV_DIRTY_RUN, capture_dirty, captured_dirty,
)

RUN = "iterate-2026-08-01-grade-snapshot-dirty-capture"
OTHER_RUN = "iterate-2026-07-31-some-other-run"


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", "-C", str(cwd), *args],
                   check=True, capture_output=True, text=True, timeout=30)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repo with one commit and a clean tree."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)],
                   check=True, capture_output=True, text=True, timeout=30)
    _git(["config", "user.email", "t@example.com"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    # A developer with commit.gpgsign=true globally would otherwise fail every
    # commit here and error the whole module out rather than test anything.
    _git(["config", "commit.gpgsign", "false"], tmp_path)
    (tmp_path / "tracked.txt").write_text("v1\n", encoding="utf-8")
    _git(["add", "tracked.txt"], tmp_path)
    _git(["commit", "-qm", "initial"], tmp_path)
    return tmp_path


def _dirty_the_tree(repo: Path) -> None:
    """Modify a TRACKED file — exactly what an automatic producer does."""
    (repo / "tracked.txt").write_text("v2\n", encoding="utf-8")


# --------------------------------------------------------------------------
# AC1 — at most one measurement per run: the first capture wins
# --------------------------------------------------------------------------


class TestFirstCaptureWins:
    def test_clean_tree_captures_false(self, repo: Path):
        env: dict[str, str] = {}
        assert capture_dirty(repo, RUN, env=env) is False

    def test_second_call_after_producer_wrote_returns_the_first_value(self, repo: Path):
        """THE regression test. Capture on a pristine tree, then dirty it the way a
        producer does, then ask again: the answer must still describe the tree as it
        was BEFORE the producer ran."""
        env: dict[str, str] = {}
        first = capture_dirty(repo, RUN, env=env)
        _dirty_the_tree(repo)
        second = capture_dirty(repo, RUN, env=env)
        assert first is False
        assert second is False, "a later ask re-measured — this is the withdrawn bug"

    def test_a_genuinely_dirty_tree_still_captures_true(self, repo: Path):
        """The fix must not blanket-report clean: real uncommitted source is dirt."""
        _dirty_the_tree(repo)
        env: dict[str, str] = {}
        assert capture_dirty(repo, RUN, env=env) is True

    def test_untracked_files_are_not_dirt(self, repo: Path):
        """Inherited from resolve_git_state: a scratch file does not change which
        code ran. Pinned here because the whole fix rests on it."""
        (repo / "scratch.tmp").write_text("x", encoding="utf-8")
        assert capture_dirty(repo, RUN, env={}) is False


# --------------------------------------------------------------------------
# AC2 — the capture round-trips, and is bound to its run
# --------------------------------------------------------------------------


class TestWithoutRunId:
    def test_measures_now(self, repo: Path):
        assert capture_dirty(repo, None, env={}) is False

    def test_records_nothing(self, repo: Path):
        env: dict[str, str] = {}
        capture_dirty(repo, None, env=env)
        assert ENV_DIRTY_RUN not in env
        assert ENV_DIRTY not in env

    def test_an_unusable_run_id_is_treated_as_absent(self, repo: Path):
        """``safe_run_id`` refuses an unsubstituted ``{run_id}`` placeholder — the
        realistic failure, since every caller here is a runtime prompt."""
        env: dict[str, str] = {}
        assert capture_dirty(repo, "{run_id}", env=env) is False
        assert ENV_DIRTY_RUN not in env

    def test_does_not_inherit_a_foreign_capture(self, repo: Path):
        env = {ENV_DIRTY_RUN: OTHER_RUN, ENV_DIRTY: "0"}
        _dirty_the_tree(repo)
        assert capture_dirty(repo, None, env=env) is True


# --------------------------------------------------------------------------
# AC4 — malformed input reads as unknown; nothing raises into the producer
# --------------------------------------------------------------------------


class TestDegradesHonestly:
    @pytest.mark.parametrize("value", ["", "true", "yes", "2", "01", " 1", "None"])
    def test_a_malformed_flag_reads_as_unknown(self, value: str):
        env = {ENV_DIRTY_RUN: RUN, ENV_DIRTY: value}
        assert captured_dirty(RUN, env=env) is None

    def test_a_recorded_unknown_stays_unknown_and_is_not_re_measured(self, repo: Path):
        """A run marker with no usable flag means "this run was captured and git
        could not answer". Re-measuring would let a producer's own writes turn an
        honest unknown into a false ``true``."""
        env = {ENV_DIRTY_RUN: RUN, ENV_DIRTY_ROOT: str(repo.resolve())}
        _dirty_the_tree(repo)
        assert capture_dirty(repo, RUN, env=env) is None

    @pytest.mark.parametrize("value", ["true", "", "2", "None"])
    def test_a_malformed_flag_under_a_matching_marker_is_not_re_measured(
        self, repo: Path, value: str,
    ):
        """The marker and the value are separate facts (AC4). The marker says THIS
        RUN WAS CAPTURED; a malformed value only means the answer is unreadable.
        Measuring again here would read the tree the producer has since dirtied and
        report ``true`` — the precise defect this module exists to prevent, arrived
        at through the back door."""
        env = {
            ENV_DIRTY_RUN: RUN,
            ENV_DIRTY_ROOT: str(repo.resolve()),
            ENV_DIRTY: value,
        }
        _dirty_the_tree(repo)
        assert capture_dirty(repo, RUN, env=env) is None

    def test_a_malformed_flag_under_NO_marker_does_measure(self, repo: Path):
        """The other half of the rule: with no matching marker there is nothing to
        preserve, so a fresh measurement is correct."""
        env = {ENV_DIRTY: "true"}
        assert capture_dirty(repo, RUN, env=env) is False
        assert env[ENV_DIRTY] == "0"

    def test_unresolvable_git_records_the_unknown(self, tmp_path: Path):
        """Not a repo at all: the answer is unknown, and it is recorded as such so a
        later ask cannot measure a by-then-dirty tree."""
        env: dict[str, str] = {}
        assert capture_dirty(tmp_path, RUN, env=env) is None
        assert env[ENV_DIRTY_RUN] == RUN
        assert ENV_DIRTY not in env

    def test_a_stale_flag_is_cleared_when_the_new_capture_is_unknown(self, tmp_path: Path):
        """A previous run's ``"1"`` must not be left behind to be read as this run's."""
        env = {ENV_DIRTY_RUN: OTHER_RUN, ENV_DIRTY: "1"}
        capture_dirty(tmp_path, RUN, env=env)
        assert ENV_DIRTY not in env
        assert captured_dirty(RUN, env=env) is None

    @pytest.mark.parametrize("bad", [None, 42, object()])
    def test_a_nonsense_project_root_never_raises(self, bad):
        assert capture_dirty(bad, RUN, env={}) is None

    @pytest.mark.parametrize("failure", ["set", "pop"])
    def test_environment_transport_failure_never_reaches_the_producer(
        self, tmp_path: Path, failure: str,
    ):
        """A broken environment mapping becomes unknown, even after a partial write."""
        class FaultyEnv(dict):
            def __setitem__(self, key, value):
                if failure == "set":
                    raise OSError("environment block full")
                super().__setitem__(key, value)

            def pop(self, key, default=None):
                if failure == "pop":
                    raise OSError("environment cleanup failed")
                return super().pop(key, default)

        assert capture_dirty(tmp_path, RUN, env=FaultyEnv()) is None

    def test_captured_dirty_with_no_run_id_is_unknown(self):
        assert captured_dirty(None, env={ENV_DIRTY_RUN: RUN, ENV_DIRTY: "1"}) is None


# --------------------------------------------------------------------------
# The default environment is the real one
# --------------------------------------------------------------------------


class TestDefaultEnv:
    def test_defaults_to_os_environ(self, repo: Path, monkeypatch: pytest.MonkeyPatch):
        # setenv, not delenv: this test makes the CODE write to the real os.environ,
        # and monkeypatch only restores names it was told about. Registering them
        # first is what stops the capture leaking into later tests in this process.
        monkeypatch.setenv(ENV_DIRTY, "sentinel")
        monkeypatch.setenv(ENV_DIRTY_RUN, "sentinel")
        monkeypatch.setenv(ENV_DIRTY_ROOT, "sentinel")
        monkeypatch.delenv(ENV_DIRTY, raising=False)
        monkeypatch.delenv(ENV_DIRTY_RUN, raising=False)
        monkeypatch.delenv(ENV_DIRTY_ROOT, raising=False)
        assert capture_dirty(repo, RUN) is False
        assert os.environ[ENV_DIRTY_RUN] == RUN
        assert os.environ[ENV_DIRTY] == "0"
        assert captured_dirty(RUN, repo) is False
