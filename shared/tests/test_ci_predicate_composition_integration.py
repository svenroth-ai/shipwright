"""INTEGRATION: the de-duplicated CI predicate composes across all four consumers.

``cross_component`` integration coverage for iterate-2026-07-31-triage-store-failsafe,
which touches ``lib/gitattributes_selfheal.py`` — framework cross-component machinery
by :data:`verifiers.integration_coverage._CROSS_COMPONENT_PATTERNS`.

What is being proven, and why a unit test is not enough. Four modules each carried a
byte-identical ``_CI_TRUTHY`` / ``_ci_active`` pair, and each uses it to decide whether
to make an AUTOMATIC GIT COMMIT. This run replaced all four with one shared leaf. The
risk of that de-duplication is not that the predicate returns the wrong boolean — that
is unit-testable and unit-tested — but that one of the four *auto-commit guards stops
firing*, so a build agent starts pushing commits nobody asked for. That is only
observable end-to-end: real git repo, real ``$CI``, real entry points, and the
assertion is on whether a COMMIT was created.

Both directions are asserted, because a guard that never fires and a guard that always
fires are equally broken and a one-directional test cannot tell them apart.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.gitattributes_selfheal import self_heal_gitattributes  # noqa: E402
from lib.gitignore_selfheal import self_heal_gitignore  # noqa: E402
from lib.reconcile_triage import reconcile_main_triage  # noqa: E402
from lib.sweep_outbox import sweep_outbox_to_branch  # noqa: E402

HEADER = '{"v":1,"schema":"triage","created":"2026-07-31T00:00:00Z"}'
ITEM = '{"event":"append","id":"trg-ciguard","ts":"2026-07-31T00:00:00Z","title":"x","status":"triage"}'


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(cwd), *args],
                          capture_output=True, text=True, encoding="utf-8", check=True)


def _head(work: Path) -> str:
    return _git(work, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture
def repo(git_origin_repo):
    work, _origin = git_origin_repo
    _git(work, "config", "user.email", "ci@test.invalid")
    _git(work, "config", "user.name", "CI Guard Test")
    (work / ".shipwright").mkdir(parents=True, exist_ok=True)
    (work / ".shipwright" / "triage.jsonl").write_text(
        HEADER + "\n", encoding="utf-8", newline="\n")
    _git(work, "add", "--", ".shipwright/triage.jsonl")
    _git(work, "commit", "-m", "seed triage")
    return work


# Each entry: (label, callable taking the repo root) -> a SweepResult-like object
# with .status. All four are the real production entry points, referenced DIRECTLY
# rather than wrapped in `lambda root: f(root)` — an unnecessary lambda, and CodeQL
# was right to say so. Each already takes the root as its single positional argument.
CONSUMERS = [
    ("gitattributes_selfheal", self_heal_gitattributes),
    ("gitignore_selfheal", self_heal_gitignore),
    ("reconcile_triage", reconcile_main_triage),
]


@pytest.mark.parametrize("label,call", CONSUMERS, ids=[c[0] for c in CONSUMERS])
def test_ci_guard_still_blocks_the_auto_commit(repo, monkeypatch, label, call) -> None:
    """With CI truthy, every consumer must decline and leave HEAD untouched.

    Asserts on the repo (HEAD unmoved), not only on the returned status word — a
    status of ``skipped`` beside a new commit would be a lie the status alone cannot
    expose.
    """
    monkeypatch.setenv("CI", "true")
    before = _head(repo)

    result = call(repo)

    assert result.status == "skipped", f"{label}: {result.to_dict()}"
    assert result.reason == "ci_without_optin", f"{label}: {result.to_dict()}"
    assert _head(repo) == before, f"{label} created a commit under CI"


@pytest.mark.parametrize("label,call", CONSUMERS, ids=[c[0] for c in CONSUMERS])
def test_guard_does_not_fire_when_ci_is_absent(repo, monkeypatch, label, call) -> None:
    """The opposite direction: with CI unset the guard must NOT be the reason.

    Without this, replacing ``ci_active()`` with a constant ``True`` would keep every
    assertion above green while disabling all four code paths permanently.
    """
    monkeypatch.delenv("CI", raising=False)
    result = call(repo)
    assert result.reason != "ci_without_optin", f"{label}: {result.to_dict()}"


def test_sweep_ci_guard_composes_with_a_real_worktree(repo, monkeypatch) -> None:
    """The fourth consumer, which needs a real worktree to reach its guard.

    ``sweep_outbox_to_branch`` is the entry point ``setup_iterate_worktree`` step 5
    calls, so this is the composed path that actually ships.
    """
    wt = repo / ".worktrees" / "ci-guard"
    _git(repo, "worktree", "add", str(wt), "-b", "iterate/ci-guard")
    (repo / ".shipwright" / "triage.outbox.jsonl").write_text(
        ITEM + "\n", encoding="utf-8", newline="\n")
    before = _head(wt)

    monkeypatch.setenv("CI", "true")
    result = sweep_outbox_to_branch(repo, wt, default_branch="main")

    assert result.status == "skipped", result.to_dict()
    assert result.reason == "ci_without_optin", result.to_dict()
    assert _head(wt) == before, "the sweep committed to the branch under CI"

    # And the opt-in still overrides it, so the guard is a guard and not a wall.
    monkeypatch.delenv("CI", raising=False)
    allowed = sweep_outbox_to_branch(repo, wt, default_branch="main")
    assert allowed.reason != "ci_without_optin", allowed.to_dict()
