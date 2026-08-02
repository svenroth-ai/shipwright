"""`check_ci_supplychain_ack` — the infrastructure fail-closed paths.

Sibling of ``test_check_integration_coverage_infra.py``, and deliberately the same
shape: this gate was the LAST of the three ``git_context`` callers still opening
with the binary ``rev-parse --git-dir`` probe, where any non-zero rc read as "not a
git repository". A broken git binary, a ``safe.directory`` / dubious-ownership
refusal, a permission failure, corrupt repo metadata or a timeout all return
non-zero from INSIDE a real repository — so the one gate whose whole premise is
that a complexity floor must not be a dodge green-SKIPped on an infrastructure
fault, at every complexity, while printing "skipped (not a git repository)" about a
directory that was one (trg-20cc9ec8).

The two ways the gate can be unable to see, and only ONE of them is a green skip:

* **not a git work tree** → SKIP at every complexity. Inapplicable, not a dodge —
  an F11 run outside a repo has nothing to merge, and the CLI sandbox tests
  depend on it.
* **git subprocess failure / timeout / unparseable refusal** → ERROR at every
  complexity.

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
from tools.verifiers import ci_supplychain as cs  # noqa: E402

_RUN = "iterate-cs-infra"
_ALL_COMPLEXITIES = ("trivial", "small", "medium", "large")
_FAKE_SHA = "deadbeef" * 5


# --- git context: exactly one of the states is a green skip -------------------


def test_outside_a_git_repo_skips(tmp_path):
    """The one legitimate stand-down, and it must survive the migration: the CLI
    sandbox suites seed bare tmp dirs and depend on this skip."""
    res = cs.check_ci_supplychain_ack(tmp_path, _RUN, "")
    assert res.is_skipped, res


def _seed_entry(wt: Path, complexity: str) -> None:
    _write(wt, f".shipwright/agent_docs/iterates/{_RUN}.json",
           json.dumps({"run_id": _RUN, "complexity": complexity, "type": "change"}))


@pytest.mark.parametrize("complexity", _ALL_COMPLEXITIES)
def test_a_git_fault_inside_a_repo_errors_at_every_complexity(
        complexity, tmp_path, monkeypatch):
    """The fail-open class this migration removes.

    The entry IS seeded per parameter so the sweep actually varies the field under
    test — without it the four runs are byte-identical and the guarantee below is
    false, because a reintroduced complexity read would see the same absent value
    four times and nothing would diverge (Stage-2 review). It stays non-differential
    against the CURRENT code by construction, since the gate returns on the git
    branch before any entry is read, and that is the property being pinned: no
    recorded tier may buy its way past a git fault. If someone reintroduces a
    complexity read above this branch, the seeding is what lets these four cases
    diverge and fail.
    """
    _seed_entry(tmp_path, complexity)
    monkeypatch.setattr(cs, "git_context", lambda root: "git_error")
    res = cs.check_ci_supplychain_ack(tmp_path, _RUN, _FAKE_SHA)
    assert res.ok is False and not res.is_skipped, (complexity, res)


def test_an_unrecognised_git_context_fails_closed(tmp_path, monkeypatch):
    """Proceed only on an EXPLICIT ``work_tree``.

    Branching on ``== "git_error"`` and falling through otherwise would put any
    future state on the fail-OPEN path — the one direction the tri-state exists to
    close. A value that is neither known name must still refuse.
    """
    monkeypatch.setattr(cs, "git_context", lambda root: "something_new")
    res = cs.check_ci_supplychain_ack(tmp_path, _RUN, _FAKE_SHA)
    assert res.ok is False and not res.is_skipped, res


def test_git_timeout_is_a_git_error_not_a_missing_repo(tmp_path, monkeypatch):
    """``_run_git`` converts OSError / ValueError / TimeoutExpired into ``(1, "", "")``,
    which must classify as ``git_error`` — an exception must not escape unstructured
    and must not be read as a clean non-git context.

    Patches ``git_helpers._run_git``, not ``cs``'s: ``git_context`` resolves
    ``_run_git`` from its OWN module globals, so this drives the real classifier
    end-to-end rather than stubbing the answer.
    """
    from tools.verifiers import git_helpers as gh  # noqa: PLC0415

    monkeypatch.setattr(gh, "_run_git", lambda *a, **k: (1, "", ""))
    assert gh.git_context(tmp_path) == "git_error"

    res = cs.check_ci_supplychain_ack(tmp_path, _RUN, _FAKE_SHA)
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
    assert cs.check_ci_supplychain_ack(tmp_path, _RUN, _FAKE_SHA).is_skipped


def test_a_localized_non_repo_answer_is_still_not_a_git_error(tmp_path, monkeypatch):
    """git uses gettext and Git-for-Windows ships translations, so on a localized
    install a genuine non-git directory returns a `fatal:` matching NEITHER English
    phrase. Classifying that as git_error would turn the documented SKIP into a hard
    block on every non-git project — and, since this migration makes that block
    reachable for a THIRD gate, would red the CLI sandbox suite (which seeds bare
    tmp dirs) on that machine while staying green here.

    ``tmp_path`` genuinely has no ``.git`` anywhere above it, so the structural
    fallback is what must answer. Stubs ONLY the prose, leaving the filesystem
    oracle real."""
    from tools.verifiers import git_helpers as gh  # noqa: PLC0415

    monkeypatch.setattr(
        gh, "_run_git",
        lambda *a, **k: (128, "", "fatal: Kein Git-Repository (oder eines der Elternverzeichnisse)"),
    )
    assert gh.git_context(tmp_path) == "not_git"
    assert cs.check_ci_supplychain_ack(tmp_path, _RUN, _FAKE_SHA).is_skipped


def test_a_localized_failure_INSIDE_a_repo_is_a_git_error(
        git_origin_repo, make_worktree, monkeypatch):
    """The other half — the fallback must not hand out ``not_git`` just because the
    prose did not match. Inside a real work tree with a real ``.git``, an unparseable
    failure stays fail-CLOSED, and the GATE must refuse with it. Uses a real repo so
    the filesystem oracle sees ``.git``; only the first probe is forced to fail."""
    from tools.verifiers import git_helpers as gh  # noqa: PLC0415

    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "cs-localized-inside")
    real = gh._run_git

    def _fail_first(root, *args, **kw):
        if args[:2] == ("rev-parse", "--is-inside-work-tree"):
            return 128, "", "fatal: etwas ist schiefgelaufen"
        return real(root, *args, **kw)

    # monkeypatch, not raw assignment + try/finally: this file's docstring mandates
    # module-object patching and the fixture cannot leak a patched global this way.
    monkeypatch.setattr(gh, "_run_git", _fail_first)
    assert gh.git_context(wt) == "git_error"
    res = cs.check_ci_supplychain_ack(wt, _RUN, _FAKE_SHA)
    assert res.ok is False and not res.is_skipped, res


def test_the_refusal_does_not_claim_the_directory_is_not_a_repo(tmp_path, monkeypatch):
    """The message is half the defect: the old probe printed "skipped (not a git
    repository)" about a directory that WAS one, which is what made the fail-open
    unreadable in an F11 report. A git fault must not be described as a missing
    repository."""
    monkeypatch.setattr(cs, "git_context", lambda root: "git_error")
    detail = cs.check_ci_supplychain_ack(tmp_path, _RUN, _FAKE_SHA).detail.lower()
    assert "not a git repository" not in detail, detail
    assert "git" in detail


def test_a_bare_repo_is_not_a_work_tree_and_skips(tmp_path):
    """A deliberate, disclosed consequence of the probe swap — recorded, not accidental.

    The old probe asked ``rev-parse --git-dir``, which exits 0 inside a BARE repo and
    inside a ``.git`` directory, so the gate proceeded and then refused further down
    (with these arguments, on the unresolvable unborn HEAD rather than on the diff).
    ``--is-inside-work-tree`` answers ``false`` there, so those contexts now SKIP —
    nominally a fail-open shift. They are two members of an open set; the rule and the
    others are on ``git_helpers.git_context``.

    Accepted for the same reason the non-repo SKIP is: an F11 finalization cannot run
    where there is no work tree, because nothing was built and there is nothing to
    merge. Both sibling gates already took this branch via the same helper (#520);
    diverging here would recreate the contradiction this migration removes.
    """
    import subprocess  # noqa: PLC0415

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    assert cs.check_ci_supplychain_ack(bare, _RUN, "").is_skipped


# --- the SKIP that must survive: a real work tree still enforces ---------------


def test_a_real_work_tree_still_reaches_enforcement(git_origin_repo, make_worktree):
    """Guards the direction the parametrized sweep cannot: the migration must not
    turn every run into an ERROR. A genuine work tree touching the CI boundary with
    no ack still fails for the ACK reason, not a git one."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "cs-realtree")
    _write(wt, ".github/workflows/ci.yml", "on: push\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "touch CI boundary")
    commit = _git(wt, "rev-parse", "HEAD").stdout.strip()

    res = cs.check_ci_supplychain_ack(wt, _RUN, commit)
    assert res.ok is False and not res.is_skipped, res
    # Pin the REASON, not just the refusal: asserting only the absence of the git
    # phrase would also pass on "cannot obtain the diff", a different refusal and a
    # plausible fixture regression (merge-base resolution can return None).
    assert "no acknowledgement was" in res.detail, res.detail


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
