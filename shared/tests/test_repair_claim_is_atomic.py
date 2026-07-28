"""Is the repair claim actually a lock — and which operation is the lock?

@FR-01.19

AC-7 says two agents starting at the same moment must not both repair the same
breakage. The first draft of this file asserted that pushing the claim branch
was the lock, and it PASSED — because the test created a distinct repair commit
before pushing, so the second push was a non-fast-forward and git rejected it.

The documented procedure does the opposite: it claims **before** doing any work.
Two agents then hold the *same* `HEAD`, push the *same object* to the same ref,
and git answers the second one "Everything up-to-date" with exit 0. Both would
believe they own the claim. The test validated a sequence the procedure never
produces — a green test over a race that was still wide open (external code
review, round 1, high).

So this file now pins the falsification: **a same-SHA push is not a lock.** That
is the fact the procedure's choice of operation rests on, and if git's behaviour
ever changed, the reason for that choice should be re-examined rather than
silently outlived.

The lock itself is GitHub's create-ref endpoint, which fails with *422 Reference
already exists* whatever the target sha. That is a property of the host, not of
git, so it is not reachable from a local bare repo — recorded as `untestable`
(`requires-external-nondeterministic-service`) rather than faked with a mock
that would only assert what the mock was told to do.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

if shutil.which("git") is None:  # pragma: no cover - environment guard
    if os.environ.get("CI", "").lower() in ("true", "1"):
        pytest.fail("git is required for the claim probe — install git")
    pytest.skip("git not on PATH", allow_module_level=True)

BAD_SHA12 = "3ed41047c2f4"
CLAIM_REF = f"refs/heads/iterate/fix-main-{BAD_SHA12}"


def _git(root: Path, *args: str, check: bool = True):
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, check=check)


def _clone(origin: Path, root: Path, name: str) -> Path:
    subprocess.run(["git", "clone", "-q", str(origin), str(root)],
                   check=True, capture_output=True, text=True)
    _git(root, "config", "user.email", f"{name}@example.com")
    _git(root, "config", "user.name", name)
    return root


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)],
                   check=True, capture_output=True, text=True)
    seed = _clone(bare, tmp_path / "seed", "seed")
    (seed / "README.md").write_text("base\n", encoding="utf-8")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-qm", "base")
    _git(seed, "push", "-q", "origin", "main")
    return bare


def test_pushing_the_claim_branch_before_working_is_NOT_a_lock(origin, tmp_path):
    """The falsification the procedure's design rests on.

    Both agents are at the same `HEAD` — which is exactly the state the
    procedure prescribes, because the claim is made BEFORE any repair work. Both
    pushes succeed, so `git push` cannot be the mechanism that decides who
    repairs.
    """
    a = _clone(origin, tmp_path / "agent-a", "agent-a")
    b = _clone(origin, tmp_path / "agent-b", "agent-b")

    first = _git(a, "push", "origin", f"HEAD:{CLAIM_REF}", check=False)
    second = _git(b, "push", "origin", f"HEAD:{CLAIM_REF}", check=False)

    assert first.returncode == 0
    assert second.returncode == 0, (
        "if this ever starts failing, git gained create-only semantics for an "
        "identical push and the procedure could be simplified — re-read it "
        "rather than deleting this test"
    )


def test_a_push_only_rejects_once_the_histories_have_diverged(origin, tmp_path):
    """Why the first version of this test passed while the race was open.

    Rejection needs divergent history. It therefore protects an agent that
    already did the work — which is precisely the agent that no longer needs
    protecting.
    """
    a = _clone(origin, tmp_path / "agent-a", "agent-a")
    b = _clone(origin, tmp_path / "agent-b", "agent-b")
    for worker, name in ((a, "agent-a"), (b, "agent-b")):
        (worker / f"{name}.txt").write_text(name, encoding="utf-8")
        _git(worker, "add", "-A")
        _git(worker, "commit", "-qm", f"fix(main): repair by {name}")

    assert _git(a, "push", "origin", f"HEAD:{CLAIM_REF}", check=False).returncode == 0
    late = _git(b, "push", "origin", f"HEAD:{CLAIM_REF}", check=False)
    assert late.returncode != 0
    assert "rejected" in (late.stderr or "").lower()


def test_the_loser_can_read_who_holds_the_claim(origin, tmp_path):
    """A refusal that told you nothing would just become a retry loop. Whatever
    operation wins the race, the ref is afterwards there to be read — which is
    what the procedure's "someone is on it, just proceed" depends on."""
    a = _clone(origin, tmp_path / "agent-a", "agent-a")
    b = _clone(origin, tmp_path / "agent-b", "agent-b")
    _git(a, "push", "origin", f"HEAD:{CLAIM_REF}")

    listed = _git(b, "ls-remote", "--heads", "origin",
                  CLAIM_REF.removeprefix("refs/heads/"))
    assert BAD_SHA12 in listed.stdout


def test_a_released_claim_lets_the_next_repairer_through(origin, tmp_path):
    """A claim that outlives its worker wedges the mechanism for everyone, so
    the procedure requires releasing it on failure. Deleting the ref restores
    the state in which a claim can be taken."""
    a = _clone(origin, tmp_path / "agent-a", "agent-a")
    b = _clone(origin, tmp_path / "agent-b", "agent-b")
    _git(a, "push", "origin", f"HEAD:{CLAIM_REF}")

    before = _git(b, "ls-remote", "--heads", "origin",
                  CLAIM_REF.removeprefix("refs/heads/"))
    assert before.stdout.strip(), "precondition: the claim exists"

    _git(a, "push", "origin", "--delete", CLAIM_REF)

    after = _git(b, "ls-remote", "--heads", "origin",
                 CLAIM_REF.removeprefix("refs/heads/"))
    assert after.stdout.strip() == "", "released: the next repairer can claim"


def test_both_agents_derive_the_same_claim_name_from_the_same_breakage():
    """Two agents must compute the SAME ref from the same bad commit — if each
    claimed its own lane the lock could never engage, whatever operation
    creates it."""
    from lib import main_health_diagnosis as dx

    for candidate in (f"iterate/fix-main-{BAD_SHA12}", f"fix-main-{BAD_SHA12}"):
        m = dx.REPAIR_BRANCH_RE.search(candidate)
        assert m and m.group("sha") == BAD_SHA12
