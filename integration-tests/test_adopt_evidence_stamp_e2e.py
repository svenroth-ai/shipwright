"""Integration: onboarding's evidence stamp, and a Group E remedy that runs.

iterate-2026-08-05-adopt-derived-evidence-rollout.

Drives the REAL CLIs as subprocesses, exactly as the skill prose invokes them.
Two chains are verified, and both are chains a unit test cannot close:

1. **stamp → commit → verify.** ``--stamp-adopted`` writes the worktree, the
   commit is built by pathspec, and ``--verify-commit`` reads the blobs back out
   of the commit. That last step is the whole point: ``git commit -- <paths>``
   records the WORKING TREE, so every index-based check proves nothing about what
   shipped. Asserting the tool's return value here would re-commit the exact
   defect #512 was bitten by.

2. **The Group E remedy is executable.** The audit's suggested command is only
   worth printing if running it works from the state the audit reports. Group E
   fires when the on-disk document differs from its committed snapshot — i.e.
   when the tree is dirty — and ``--refresh-pr``'s preflight refuses a dirty
   tree. So the ordered ``--restore`` → clean-tree claim is checked by running
   it, not by matching the suggestion string.

**What is deliberately NOT tested here.** Adopt's Step H is agent-driven prose,
not code — nothing orchestrates the adoption commit. A test that "runs Step F→H"
could only re-implement that prose, and would then pass while the prose said
something else. The ordering guarantee is held by the drift test over the prose
(`plugins/shipwright-adopt/tests/test_adopt_evidence_disclosure.py`); what is
mechanised here is the tool chain underneath it.

Lives in integration-tests/ (a CI-run root) per ADR-044.

@FR-01.10
@FR-01.13
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED_SCRIPTS = REPO_ROOT / "shared" / "scripts"
TOOL = SHARED_SCRIPTS / "tools" / "refresh_compliance_docs.py"

sys.path.insert(0, str(SHARED_SCRIPTS))

from lib.compliance_refresh import REFRESH_SET  # noqa: E402
from source_state import SourceState, banner_line, parse_banner_line  # noqa: E402

STAMPABLE = sorted(rel for rel in REFRESH_SET if rel.endswith(".md"))
RUN = "adopt-2026-08-06-example"


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """A git call carrying its own identity — a CI runner has none."""
    return subprocess.run(
        ["git", "-C", str(root),
         "-c", "user.name=Adopt Test", "-c", "user.email=t@test.invalid",
         *args],
        check=check, capture_output=True, text=True, encoding="utf-8",
    )


def _exists_in(root: Path, sha: str, rel: str) -> bool:
    """Is ``rel`` present in the tree of ``sha``? ``cat-file -e`` without raising."""
    return _git(root, "cat-file", "-e", f"{sha}:{rel}", check=False).returncode == 0


def _tool(root: Path, *args: str) -> tuple[int, dict]:
    """The real CLI, as a subprocess — the process boundary is the point."""
    proc = subprocess.run(
        [sys.executable, str(TOOL), "--project-root", str(root), *args],
        capture_output=True, text=True, encoding="utf-8",
    )
    try:
        return proc.returncode, json.loads(proc.stdout)
    except json.JSONDecodeError:  # pragma: no cover — diagnostic path
        pytest.fail(f"non-JSON stdout (rc={proc.returncode}):\n"
                    f"{proc.stdout}\n{proc.stderr}")


@pytest.fixture
def onboarded(tmp_path: Path) -> Path:
    """A repository as Step F leaves it: evidence seeded, banners unstamped."""
    root = tmp_path / "adopted"
    root.mkdir()
    _git(root, "init", "-b", "main")
    banner = banner_line(SourceState(run_id=RUN))
    for rel in sorted(REFRESH_SET):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith(".json"):
            path.write_text(json.dumps({"rows": ["x"] * 40}), encoding="utf-8")
        else:
            path.write_text(
                f"# {Path(rel).stem}\n\nGenerated: 2026-08-06\n{banner}\n\n"
                + "row\n" * 40, encoding="utf-8")
    # A non-evidence artifact onboarding also writes. The amend is path-limited to
    # the evidence set, so this is what proves it OVERLAYS rather than replaces.
    (root / "CLAUDE.md").write_text("# Project guidance\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "pre-adoption state")
    return root


def test_the_adoption_commit_carries_the_stamp(onboarded: Path) -> None:
    """The chain Step H describes, run for real, checked against the COMMIT."""
    base = _git(onboarded, "rev-parse", "HEAD").stdout.strip()

    code, report = _tool(onboarded, "--stamp-adopted", "--base", base)
    assert code == 0 and report["status"] == "ok", report

    # Staged AFTER the stamp, which is what Step H now prescribes — the stamp
    # writes the WORKTREE and the commit records the INDEX, so staging first
    # would ship pre-stamp blobs. (Until the Stage-1 review, this line staged by
    # pathspec and claimed that was "exactly as the skill prescribes"; the skill
    # prescribed no staging at all, so the test was passing under a discipline
    # the prose did not state.)
    _git(onboarded, "add", "-A")
    _git(onboarded, "commit", "-m", f"chore(shipwright): adopt\n\nRun-ID: {RUN}")
    sha = _git(onboarded, "rev-parse", "HEAD").stdout.strip()

    code, verified = _tool(onboarded, "--verify-commit", sha)
    assert code == 0, verified
    assert verified["status"] == "verified" and not verified["unstamped"]

    # And read the blob directly, rather than trusting the verifier that just
    # passed — one of the two must be independent or neither means anything.
    for rel in STAMPABLE:
        blob = _git(onboarded, "show", f"{sha}:{rel}").stdout
        state = parse_banner_line(blob)
        assert state is not None and state.base == base[:12], rel
        assert state.release is None, f"{rel}: onboarding shipped no release"


def test_a_writer_between_stamp_and_commit_is_caught(onboarded: Path) -> None:
    """The failure `--verify-commit` exists for, reproduced end to end.

    A hook or a second session rewriting a document after the stamp puts
    unstamped bytes in the commit while the stamp's own JSON still reports
    success. Only reading the commit finds it.
    """
    base = _git(onboarded, "rev-parse", "HEAD").stdout.strip()
    code, report = _tool(onboarded, "--stamp-adopted", "--base", base)
    assert code == 0 and report["status"] == "ok"

    victim = onboarded / STAMPABLE[0]
    victim.write_text(
        f"# clobbered\n\nGenerated: 2026-08-06\n"
        f"{banner_line(SourceState(run_id=RUN))}\n\n" + "row\n" * 40,
        encoding="utf-8")

    _git(onboarded, "add", "-A")
    _git(onboarded, "commit", "-m", f"chore(shipwright): adopt\n\nRun-ID: {RUN}")
    sha = _git(onboarded, "rev-parse", "HEAD").stdout.strip()

    code, verified = _tool(onboarded, "--verify-commit", sha)
    assert code != 0, "a clobbered document shipped and the verifier said nothing"
    assert verified["status"] == "unstamped_in_commit"
    assert STAMPABLE[0] in verified["unstamped"]

    # Step H's remedy: re-stamp, amend ONCE path-limited, re-verify. Detection
    # without a working repair is half a guarantee, and the repair is the part
    # that touches an already-made commit (external review R2-6).
    code, restamped = _tool(onboarded, "--stamp-adopted", "--base", base)
    assert code == 0 and restamped["status"] == "ok", restamped
    _git(onboarded, "commit", "--amend", "--no-edit", "--", ".shipwright/compliance/")
    amended = _git(onboarded, "rev-parse", "HEAD").stdout.strip()

    code, reverified = _tool(onboarded, "--verify-commit", amended)
    assert code == 0 and reverified["status"] == "verified", reverified
    assert amended != sha, "the amend produced no new commit"

    # And that the amend PRESERVED the rest of the adoption. `git commit --amend
    # -- <pathspec>` is git's partial-commit form: the whole commit survives only
    # because git builds the false index from HEAD and overlays the pathspec.
    # `verify_commit` looks at nothing outside the evidence set, so it would call
    # a tree containing ONLY .shipwright/compliance/ "verified" — and this is the
    # single repair instruction in a customer-facing skill (Stage-2 code review).
    for survivor in (STAMPABLE[1], "CLAUDE.md"):
        assert _exists_in(onboarded, amended, survivor), (
            f"the amend dropped {survivor} — it rewrote the adoption commit "
            "down to the pathspec instead of overlaying it"
        )


def test_a_repository_with_no_commits_can_still_be_onboarded(tmp_path: Path) -> None:
    """AC-2 end to end: no commit to name, so none is named — and it still ships.

    This is the path Step H skips verification for, and the skip is only correct
    because `--verify-commit` genuinely REJECTS a banner with no `base=`. That
    rejection is asserted here rather than assumed: if it ever stopped being true
    the skip would become dead prose and nothing else would notice
    (external review R2-5 / Stage-1 spec review, high).
    """
    root = tmp_path / "fresh"
    root.mkdir()
    _git(root, "init", "-b", "main")
    banner = banner_line(SourceState(run_id=RUN))
    for rel in STAMPABLE:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(
            f"# {Path(rel).stem}\n\nGenerated: 2026-08-06\n{banner}\n\n"
            + "row\n" * 40, encoding="utf-8")

    # `event_seeder` writes the literal "HEAD" when there is no commit to record.
    code, report = _tool(root, "--stamp-adopted", "--base", "HEAD")
    assert code == 0, "a commitless repository is legitimate to onboard"
    assert report["status"] == "no_base" and report["base"] is None

    _git(root, "add", "-A")
    _git(root, "commit", "-m", f"chore(shipwright): adopt\n\nRun-ID: {RUN}")
    sha = _git(root, "rev-parse", "HEAD").stdout.strip()

    for rel in STAMPABLE:
        state = parse_banner_line(_git(root, "show", f"{sha}:{rel}").stdout)
        assert state is not None and state.base is None, (
            f"{rel} names a commit that could not be established"
        )

    code, verified = _tool(root, "--verify-commit", sha)
    assert code != 0 and verified["status"] == "unstamped_in_commit", (
        "verify_commit ACCEPTED a banner with no base= — Step H skips this call "
        "on `no_base` precisely because it does not, so the skip would now be "
        "unnecessary prose and this rejection is what makes it load-bearing"
    )


def test_the_group_e_remedy_reaches_a_clean_tree(onboarded: Path) -> None:
    """`--restore` really does clear what a Group E finding reports.

    Group E fires when an on-disk document differs from its committed snapshot,
    which is exactly a dirty tree — and `--refresh-pr`'s preflight refuses those.
    So the suggestion's first step has to actually work, or the operator is sent
    to a refusal.

    **Declared substitution:** the plan said "verified against `preflight_pr`",
    and this asserts a clean `git status` instead. `preflight_pr` additionally
    requires an `origin`, a resolvable default branch and a committer identity, so
    calling it here would refuse for reasons that have nothing to do with the
    claim under test and would pass or fail on fixture plumbing. The dirty-tree
    condition is the ONLY one this remedy can affect, and it is the one asserted.
    Recorded rather than silently swapped (Stage-1 spec review, medium).
    """
    (onboarded / STAMPABLE[0]).write_text(
        "# locally regenerated, never committed\n" + "row\n" * 30,
        encoding="utf-8")
    assert _git(onboarded, "status", "--porcelain").stdout.strip(), (
        "fixture did not reproduce the state Group E reports"
    )

    code, restored = _tool(onboarded, "--restore")
    assert code == 0, restored

    assert not _git(onboarded, "status", "--porcelain").stdout.strip(), (
        "the remedy's first step left the tree dirty, so the second step "
        "(--refresh-pr) would refuse — the suggestion would be unrunnable"
    )


def test_restore_does_not_clear_unrelated_work(onboarded: Path) -> None:
    """Why the suggestion must ALSO say to commit or stash unrelated changes.

    `--restore` resets the evidence set and nothing else — correctly, it must not
    destroy an operator's work. But that means a tree with unrelated edits stays
    dirty and `--refresh-pr` still refuses, which is why naming only `--restore`
    would promise something it cannot deliver (external review R3).

    Every branch is asserted positively. An earlier draft checked only that
    `git status --porcelain` was still non-empty, which was already true from the
    drifted evidence file — so it passed if `--restore` did nothing at all, and
    passed even if it DELETED the unrelated file, since a staged-then-deleted path
    still shows in porcelain. It could not detect the failure its own message
    named (Stage-1 spec review, medium).
    """
    drifted = onboarded / STAMPABLE[0]
    original = _git(onboarded, "show", f"HEAD:{STAMPABLE[0]}").stdout
    drifted.write_text("# drifted\n" + "row\n" * 30, encoding="utf-8")
    unrelated = onboarded / "unrelated.py"
    unrelated.write_text("x = 1\n", encoding="utf-8")
    _git(onboarded, "add", "unrelated.py")

    code, restored = _tool(onboarded, "--restore")
    assert code == 0, restored

    assert drifted.read_text(encoding="utf-8") == original, (
        "the evidence file was not restored — the remedy's own job"
    )
    assert unrelated.is_file() and unrelated.read_text(encoding="utf-8") == "x = 1\n", (
        "restore destroyed unrelated operator work"
    )
    staged = _git(onboarded, "diff", "--cached", "--name-only").stdout.split()
    assert "unrelated.py" in staged, "restore unstaged unrelated operator work"
    assert _git(onboarded, "status", "--porcelain").stdout.strip(), (
        "the tree is clean, so `--refresh-pr` would proceed — but then the "
        "suggestion could stop at --restore, and it does not"
    )
