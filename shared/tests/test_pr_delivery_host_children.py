"""The delivery ladder's child processes and its host bundle
(iterate-2026-07-31-f11-delivery-truth).

Two rules, both learned the hard way: nothing here raises for an ordinary failure
(a missing binary is an OSError, which escaped the ladder's handlers as a traceback),
and nothing here runs without a timeout (the polling clock is consulted only AFTER a
call returns, so an untimed one escapes every stated bound).

Split out of ``test_pr_delivery_host.py`` to keep both files under the 300-line source
limit (constitution; the Group H audit fails an oversize file with no baseline entry).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import subprocess  # noqa: E402

from lib import pr_delivery_host as host  # noqa: E402


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _recorder(*results):
    """A `run`/`gh` stand-in that records argv and returns each result in turn."""
    calls: list[list[str]] = []
    queue = list(results)

    def run(argv, **kwargs):
        calls.append(list(argv))
        return queue.pop(0) if len(queue) > 1 else queue[0]

    run.calls = calls  # type: ignore[attr-defined]
    return run


def _guard(stdout, *rest):
    """HEAD before the guard runs, then ensure_current's result, then the rest.

    The order matters: `head_before` is read BEFORE `ensure_current` — reading it
    afterwards could never detect the commit the comparison exists to detect
    (external code review).
    """
    return _recorder(_Proc(0, "sha-before\n"), _Proc(0, stdout), *rest)


# --- reverify: the invariant's enforcement arm --------------------------------

def test_reverify_passes_the_run_id_project_root_and_commit():
    """Gem-3's finding: the re-verification must be the SAME check as the original,
    which means it needs the run's identity, not just a commit."""
    run = _recorder(_Proc(0))
    assert host.reverify(Path("/wt"), "iterate-x", "deadbeef", run=run) is True
    argv = run.calls[0]
    assert "verify_iterate_finalization.py" in " ".join(argv)
    assert argv[argv.index("--run-id") + 1] == "iterate-x"
    assert argv[argv.index("--commit") + 1] == "deadbeef"
    assert argv[argv.index("--project-root") + 1] == str(Path("/wt"))


def test_reverify_is_false_when_the_verifier_is_red(capsys):
    run = _recorder(_Proc(1, "check X failed", "stderr detail"))
    assert host.reverify(Path("/wt"), "iterate-x", "deadbeef", run=run) is False
    # The verifier's own output must reach the operator, not be swallowed.
    captured = capsys.readouterr()
    assert "check X failed" in captured.err


# --- refresh_branch: integrate, then push only if something was integrated ----



def test_a_branch_already_current_is_a_no_op_and_pushes_nothing():
    run = _guard('{"action": "already-current", "integrated": false}')
    result = host.refresh_branch(Path("/wt"), "iterate-x", "iterate/x", run=run)
    assert result["ok"] is True and result["pushed"] is False
    assert not any("push" in c for c in run.calls), (
        "nothing to integrate must mean nothing to push")


def test_an_integrated_branch_is_pushed():
    run = _guard('{"action": "integrated", "integrated": true}', _Proc(0))
    result = host.refresh_branch(Path("/wt"), "iterate-x", "iterate/x", run=run)
    assert result["ok"] is True and result["pushed"] is True
    push = next(c for c in run.calls if "push" in c)
    # `git -C <root>`, never a bare `git`: a Bash cwd silently resets between calls
    # and a bare command would push from the MAIN tree.
    assert push[:3] == ["git", "-C", str(Path("/wt"))]
    assert push[3:] == ["push", "origin", "iterate/x"]


def test_a_failed_integrate_is_reported_not_pushed():
    run = _recorder(_Proc(1, "", "source conflict in a real file"))
    result = host.refresh_branch(Path("/wt"), "iterate-x", "iterate/x", run=run)
    assert result["ok"] is False and result["pushed"] is False
    assert "source conflict" in result["error"]
    assert not any("push" in c for c in run.calls)


def test_an_unreadable_guard_whose_head_moved_names_that_and_not_a_third_party():
    """Reporting "nothing integrated" here surfaced downstream as "something else pushed
    to this branch" — naming a cause that did not happen, and sending the operator hunting
    for a third party who was never there (Stage 3)."""
    run = _recorder(_Proc(0, "not json"), _Proc(0, "before\n"), _Proc(0, "after\n"))
    result = host.refresh_branch(Path("/wt"), "iterate-x", "iterate/x", run=run)
    assert result["ok"] is False and result["pushed"] is False
    assert "could not be read" in result["error"] and "HEAD moved" in result["error"]


def test_a_failed_push_is_reported_as_not_ok():
    run = _guard('{"integrated": true}', _Proc(1, "", "rejected: non-fast-forward"))
    result = host.refresh_branch(Path("/wt"), "iterate-x", "iterate/x", run=run)
    assert result["ok"] is False
    assert "non-fast-forward" in result["error"]


def test_unparseable_guard_output_is_treated_as_nothing_integrated():
    """Never guess that a commit was made: pushing on a guess could push an unrelated
    local commit. (With HEAD unmoved, so this is the benign half.)"""
    # HEAD must read the SAME before and after, so the third result is stated explicitly
    # rather than left to the recorder repeating its last one.
    run = _guard("this is not json", _Proc(0, "sha-before\n"))
    result = host.refresh_branch(Path("/wt"), "iterate-x", "iterate/x", run=run)
    assert result["ok"] is True and result["pushed"] is False


def test_refresh_names_the_run_in_its_reason():
    run = _guard('{"integrated": false}')
    host.refresh_branch(Path("/wt"), "iterate-2026-07-31-x", "iterate/x", run=run)
    argv = next(c for c in run.calls if "ensure_current.py" in " ".join(c))
    assert "iterate-2026-07-31-x" in argv[argv.index("--reason") + 1]


# --- head_sha ----------------------------------------------------------------

def test_head_sha_uses_git_dash_C_and_strips():
    run = _recorder(_Proc(0, "abc123\n"))
    assert host.head_sha(Path("/wt"), run=run) == "abc123"
    assert run.calls[0][:3] == ["git", "-C", str(Path("/wt"))]


def test_head_sha_is_empty_when_git_fails():
    """Empty, not a guess — the caller refuses an unpinned merge on it."""
    run = _recorder(_Proc(128, "", "not a git repository"))
    assert host.head_sha(Path("/wt"), run=run) == ""


# --- gh: the cwd contract ----------------------------------------------------

def test_gh_is_told_which_directory_to_act_in(monkeypatch):
    """`gh` has no `-C` analog and acts on the cwd's repo, which is why F11 cds into
    the worktree at all. The cwd must be passed through, not inherited."""
    seen = {}

    def fake_run(argv, **kwargs):
        seen.update(argv=argv, cwd=kwargs.get("cwd"))
        return _Proc(0, "{}")

    monkeypatch.setattr(subprocess, "run", fake_run)
    host.gh(["pr", "view", "7"], cwd=Path("/wt"))
    assert seen["argv"][0] == "gh"
    assert seen["cwd"] == str(Path("/wt"))


# --- nothing here raises for an ordinary failure, and nothing hangs ------------
#
# Stage 2: `timeout_seconds` bounds the POLLING clock, and that clock is consulted only
# after a fetch returns — so an untimed `gh` blocking on a TLS handshake or a misbehaving
# credential helper escaped every stated bound and the run neither delivered nor failed.
# And `gh` missing from PATH is an OSError, which escaped the ladder's RuntimeError
# handlers as a traceback instead of the documented exit 5.

def test_every_child_process_is_given_a_timeout(monkeypatch):
    seen = []

    def fake_run(argv, **kwargs):
        seen.append(kwargs.get("timeout"))
        return _Proc(0, '{"integrated": false}')

    monkeypatch.setattr(subprocess, "run", fake_run)
    host.gh(["pr", "view", "7"])
    host.head_sha(Path("/wt"))
    host.reverify(Path("/wt"), "r", "sha")
    host.refresh_branch(Path("/wt"), "r", "b")
    assert seen, "no child processes observed"
    assert all(t is not None and t > 0 for t in seen), seen


def test_a_timeout_becomes_a_failed_result_not_an_exception(monkeypatch):
    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout", 1))

    monkeypatch.setattr(subprocess, "run", fake_run)
    proc = host.gh(["pr", "view", "7"])
    assert proc.returncode != 0
    assert "timed out" in proc.stderr
    assert host.gh_json(["api", "x"]) is None       # unreadable, not false
    assert host.head_sha(Path("/wt")) == ""         # empty, not a guess


def test_a_missing_binary_becomes_a_failed_result_not_an_exception(monkeypatch):
    def fake_run(argv, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", argv[0])

    monkeypatch.setattr(subprocess, "run", fake_run)
    proc = host.gh(["pr", "view", "7"])
    assert proc.returncode != 0
    assert "could not run" in proc.stderr


def test_gh_json_rejects_a_zero_exit_with_blank_stdout(monkeypatch):
    """The shape `lib/pr_blockers._gh_json` already guards: a zero exit with nothing on
    stdout is an unreadable answer, not an empty one."""
    monkeypatch.setattr(host, "gh", lambda args, cwd=None: _Proc(0, "   \n"))
    assert host.gh_json(["api", "x"]) is None


def test_the_default_host_binds_capability_to_its_own_reader():
    """The footgun this bundle removes: `read_capability`'s default used to close over
    the MODULE-level `gh_json`, so faking one member left another talking to the real
    GitHub (Stage 2)."""
    bundle = host.Host.default(repo="o/r")
    assert bundle.repo_args == ("--repo", "o/r")
    for member in ("gh", "gh_json", "capability", "verify", "refresh", "head_sha"):
        assert getattr(bundle, member) is not None, member

    calls = []
    faked = host.Host(gh=bundle.gh, gh_json=lambda args, cwd=None: calls.append(args),
                      capability=bundle.capability, verify=bundle.verify,
                      refresh=bundle.refresh, head_sha=bundle.head_sha,
                      repo_args=bundle.repo_args)
    faked.capability("o/r", "main", reader=faked.gh_json)
    assert len(calls) == 2, "the capability read must go through the injected reader"


def test_the_bundle_pins_the_repository_on_every_call():
    seen = []
    bundle = host.Host(gh=lambda args, cwd=None: seen.append(args) or _Proc(0),
                       gh_json=lambda args, cwd=None: seen.append(args) or {},
                       repo_args=("--repo", "o/r"))
    bundle.call(["pr", "merge", "7", "--squash"])
    bundle.call_json(["pr", "view", "7", "--json", "state"])
    assert all(argv[-2:] == ["--repo", "o/r"] for argv in seen), seen


def test_host_errors_covers_every_shape_an_ordinary_failure_takes():
    """The tuple the ladder catches. If a shape is missing from it, that failure
    surfaces as a traceback and F11 reports 'unrecognised delivery outcome'."""
    for exc in (RuntimeError, OSError, subprocess.SubprocessError,
                subprocess.TimeoutExpired, ValueError):
        assert issubclass(exc, host.HOST_ERRORS), exc
