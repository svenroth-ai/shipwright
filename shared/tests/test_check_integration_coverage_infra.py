"""`check_integration_coverage` — the infrastructure fail-closed paths.

Split from ``test_check_integration_coverage.py`` (300-line file limit); that
module owns the enforcement + message-content half. This one owns the three ways
the gate can be unable to see, and pins that only ONE of them is a green skip:

* **not a git work tree** → SKIP at every complexity. Inapplicable, not a dodge —
  an F11 run outside a repo has nothing to merge, and the CLI sandbox tests
  depend on it.
* **git subprocess failure / timeout** → ERROR at every complexity. A broken git
  binary, a permission failure or a wedged ``index.lock`` all return non-zero
  from INSIDE a repository, so a binary "non-zero means not a repo" probe would
  green-skip a real infrastructure fault (external plan review r1#2). The
  tri-state ``git_helpers.git_context`` is what keeps the two apart.
* **diff unobtainable** (``_iterate_changed_paths`` → ``None``) → ERROR.
  ``[]`` is NOT ``None``: it means the branch has no net change vs the trunk and
  must still pass, or a commit-then-revert branch would hard-fail.

Monkeypatching is by MODULE OBJECT throughout (ADR-045) — never by a
``"tools.verifiers.…"`` string, which binds whichever copy of the package loaded
first.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402
from tools.verifiers import integration_coverage as icov  # noqa: E402
from tools.verifiers import iterate_checks as ic  # noqa: E402

_RUN = "iterate-xc"
_ALL_COMPLEXITIES = ("trivial", "small", "medium", "large")
_FAKE_SHA = "deadbeef" * 5


def _seed_entry(wt: Path, complexity: str) -> None:
    _write(wt, f".shipwright/agent_docs/iterates/{_RUN}.json",
           json.dumps({"run_id": _RUN, "complexity": complexity, "type": "change"}))


def _seed_ledger(wt: Path, behaviors: list[dict]) -> None:
    _write(wt, "shipwright_test_results.json",
           json.dumps({"iterate_latest": {"run_id": _RUN,
                       "test_completeness": {"status": "complete", "behaviors": behaviors}}}))


def _commit_change(wt: Path, path: str, msg: str) -> str:
    _write(wt, path, "x\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", msg)
    return _git(wt, "rev-parse", "HEAD").stdout.strip()


# --- git context: exactly one of the three is a green skip --------------------


def test_outside_a_git_repo_skips(tmp_path):
    res = ic.check_integration_coverage(tmp_path, _RUN, "")
    assert res.is_skipped, res


@pytest.mark.parametrize("complexity", _ALL_COMPLEXITIES)
def test_git_subprocess_failure_errors_at_every_complexity(complexity, tmp_path, monkeypatch):
    """The fail-open class the reorder must not reintroduce: a git fault INSIDE a
    repo is not "no repo".

    The entry IS seeded per parameter so the sweep actually varies the field under
    test. It is still non-differential by construction — the gate returns on the git
    branch before `find_entry_by_run_id` is reached — and that is precisely the
    property being pinned: no recorded complexity may buy its way past a git fault.
    If someone reintroduces a complexity read above this branch, seeding is what
    lets these four cases diverge and fail."""
    _seed_entry(tmp_path, complexity)
    monkeypatch.setattr(icov, "git_context", lambda root: "git_error")
    res = ic.check_integration_coverage(tmp_path, _RUN, _FAKE_SHA)
    assert res.ok is False and not res.is_skipped, res


def test_git_timeout_is_a_git_error_not_a_missing_repo(tmp_path, monkeypatch):
    """`_run_git` converts OSError / ValueError / TimeoutExpired into (1, "", ""),
    which must classify as `git_error` — an exception must not escape unstructured
    and must not be read as a clean non-git context (external plan review r2#2).

    Patches `git_helpers._run_git`, not `icov`'s: `git_context` resolves `_run_git`
    from its OWN module globals, so this drives the real classifier end-to-end
    rather than stubbing the answer."""
    from tools.verifiers import git_helpers as gh  # noqa: PLC0415

    monkeypatch.setattr(gh, "_run_git", lambda *a, **k: (1, "", ""))
    assert gh.git_context(tmp_path) == "git_error"

    res = ic.check_integration_coverage(tmp_path, _RUN, _FAKE_SHA)
    assert res.ok is False and not res.is_skipped, res


def test_a_definitive_non_repo_answer_is_not_a_git_error(tmp_path, monkeypatch):
    """The other side of the same seam: git RAN and said "not a git repository",
    which is the one non-zero result that legitimately means SKIP."""
    from tools.verifiers import git_helpers as gh  # noqa: PLC0415

    monkeypatch.setattr(
        gh, "_run_git",
        lambda *a, **k: (128, "", "fatal: not a git repository (or any of the parent directories)"),
    )
    assert gh.git_context(tmp_path) == "not_git"
    assert ic.check_integration_coverage(tmp_path, _RUN, _FAKE_SHA).is_skipped


def test_a_localized_non_repo_answer_is_still_not_a_git_error(tmp_path, monkeypatch):
    """git uses gettext and Git-for-Windows ships translations, so on a localized
    install a genuine non-git directory returns a `fatal:` matching NEITHER English
    phrase. Classifying that as git_error would turn the documented SKIP into a hard
    block on every non-git project — and, since this change makes that block
    reachable for two gates at four tiers, would red the CLI sandbox suite (which
    seeds bare tmp dirs) on that machine while staying green here.

    `tmp_path` genuinely has no `.git` anywhere above it, so the structural fallback
    is what must answer. Stubs ONLY the prose, leaving the filesystem oracle real."""
    from tools.verifiers import git_helpers as gh  # noqa: PLC0415

    monkeypatch.setattr(
        gh, "_run_git",
        lambda *a, **k: (128, "", "fatal: Kein Git-Repository (oder eines der Elternverzeichnisse)"),
    )
    assert gh.git_context(tmp_path) == "not_git"
    assert ic.check_integration_coverage(tmp_path, _RUN, _FAKE_SHA).is_skipped


def test_a_localized_failure_INSIDE_a_repo_is_a_git_error(git_origin_repo, make_worktree):
    """The other half — the fallback must not hand out `not_git` just because the
    prose did not match. Inside a real work tree with a real `.git`, an unparseable
    failure stays fail-CLOSED. Uses a real repo so the filesystem oracle sees `.git`;
    only the first probe is forced to fail."""
    from tools.verifiers import git_helpers as gh  # noqa: PLC0415

    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "xc-localized-inside")
    real = gh._run_git

    def _fail_first(root, *args, **kw):
        if args[:2] == ("rev-parse", "--is-inside-work-tree"):
            return 128, "", "fatal: etwas ist schiefgelaufen"
        return real(root, *args, **kw)

    gh._run_git = _fail_first
    try:
        assert gh.git_context(wt) == "git_error"
    finally:
        gh._run_git = real


# --- commit resolution --------------------------------------------------------


def test_unresolvable_head_without_commit_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(icov, "git_context", lambda root: "work_tree")
    monkeypatch.setattr(icov, "_run_git", lambda *a, **k: (1, "", ""))
    res = ic.check_integration_coverage(tmp_path, _RUN, "")
    assert res.ok is False and not res.is_skipped, res


def test_absent_commit_falls_back_to_head_and_still_enforces(git_origin_repo, make_worktree):
    """No --commit inside a repo is not a licence to stand down: HEAD is resolved
    and the gate enforces against it. Before this change an absent commit was an
    unconditional green SKIP — the cheapest input was the safest one for a dodger."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "xc-headfallback")
    _commit_change(wt, "shared/scripts/tools/integrate_main.py", "touch merge machinery")
    _seed_entry(wt, "medium")
    _seed_ledger(wt, [{"behavior": "unit only", "disposition": "tested", "evidence": "t"}])

    res = ic.check_integration_coverage(wt, _RUN, "")  # no commit supplied
    assert res.ok is False and not res.is_skipped, res
    assert "integration" in res.detail.lower()


def test_invalid_supplied_commit_reaches_the_fail_closed_path(git_origin_repo, make_worktree):
    """A bad --commit is a realistic CI invocation error (external plan review
    r2#5). It must reach the None → ERROR path, never read as an empty diff."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "xc-badrev")
    _commit_change(wt, "shared/scripts/tools/integrate_main.py", "touch merge machinery")
    _seed_entry(wt, "medium")

    res = ic.check_integration_coverage(wt, _RUN, "not-a-real-revision")
    assert res.ok is False and not res.is_skipped, res


# --- the None / [] / paths contract -------------------------------------------


def test_unobtainable_diff_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(icov, "git_context", lambda root: "work_tree")
    monkeypatch.setattr(icov, "_iterate_changed_paths", lambda root, commit: None)
    res = ic.check_integration_coverage(tmp_path, _RUN, _FAKE_SHA)
    assert res.ok is False and not res.is_skipped, res
    assert "diff" in res.detail.lower()


def test_empty_diff_is_not_unobtainable(tmp_path, monkeypatch):
    """The half that keeps the refusal honest: `[]` is a fact, `None` is ignorance."""
    monkeypatch.setattr(icov, "git_context", lambda root: "work_tree")
    monkeypatch.setattr(icov, "_iterate_changed_paths", lambda root, commit: [])
    res = ic.check_integration_coverage(tmp_path, _RUN, _FAKE_SHA)
    assert res.ok is True and not res.is_skipped, res


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
