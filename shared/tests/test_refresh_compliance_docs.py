"""Where the recomputed evidence goes — staging, the docs-only PR, and restore.

Subject: ``shared/scripts/tools/refresh_compliance_docs.py``
(iterate-2026-07-31-derived-docs-at-release, AC-7 / AC-8 / AC-8b / AC-9b / AC-13).

The claim under test throughout is **"nothing else can ride along"**, and it is
tested by planting something else and proving it did not.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# Unconditional, and in this order: `shared/tests` carries its own `tools/`
# package and must never sit ahead of `shared/scripts` (ADR-045).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from _compliance_refresh_fixtures import (  # noqa: E402
    DASHBOARD, RUN, all_ok, git, head_sha, seed_repo,
)
from lib.churn_merge import COMPLIANCE_MDS  # noqa: E402
from lib.compliance_refresh import REFRESH_SET  # noqa: E402
from source_state import parse_banner_line  # noqa: E402
from tools import compliance_refresh_produce as produce_mod  # noqa: E402
from tools import compliance_git as gitmod  # noqa: E402
from tools import refresh_compliance_docs as docs  # noqa: E402


@pytest.fixture
def compliance_refresh_repo(tmp_path: Path) -> Path:
    """:func:`seed_repo` as a fixture — see that module for why it is declared
    here rather than shared."""
    return seed_repo(tmp_path / "repo")

@pytest.fixture
def cloned(compliance_refresh_repo: Path, tmp_path: Path) -> Path:
    """The seeded repo with a bare ``origin`` it is up to date with — the state
    ``--pr`` requires before it will do anything."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   check=True, capture_output=True)
    git(compliance_refresh_repo, "remote", "add", "origin", str(origin))
    git(compliance_refresh_repo, "push", "-u", "origin", "main")
    git(compliance_refresh_repo, "remote", "set-head", "origin", "main")
    return compliance_refresh_repo


def _committed_paths(root: Path, ref: str = "HEAD") -> set[str]:
    out = git(root, "show", "--name-only", "--pretty=format:", ref).stdout
    return {line.strip() for line in out.splitlines() if line.strip()}


# --- AC-7: the release path --------------------------------------------------


def test_stage_reports_only_what_actually_differed(compliance_refresh_repo):
    (compliance_refresh_repo / DASHBOARD).write_text("# dashboard\n\n" + "row\n" * 60, encoding="utf-8")
    result = docs.deliver_stage(compliance_refresh_repo, {"status": "ok"},
                                produce_mod.capture(compliance_refresh_repo), "v0.5.2")
    assert result["staged"] == [DASHBOARD], (
        "reporting every path that exists is the most misleading possible answer "
        "to 'did anything change?'"
    )


def test_the_staged_bytes_are_the_STAMPED_ones(compliance_refresh_repo, capsys):
    """The headline deliverable, end to end (Stage-1 spec review, HIGH-1).

    `produce` stamps the captured bytes; an earlier version then staged whatever
    the generator had left on disk instead — so the release committed UNstamped
    documents while the run reported `stamped: [...]`. A run that reports a fixed
    point the documents do not carry is worse than one that does not stamp.
    """
    assert docs.main([
        "--project-root", str(compliance_refresh_repo),
        "--stage", "--release", "v0.5.2",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "ok"
    assert sorted(result["stamped"]) == sorted(COMPLIANCE_MDS)

    head = head_sha(compliance_refresh_repo)
    for rel in sorted(COMPLIANCE_MDS):
        # The INDEX, not the worktree: staging is what the release commit reads.
        blob = git(compliance_refresh_repo, "show", f":{rel}").stdout
        state = parse_banner_line(blob)
        assert state is not None, f"{rel} lost its banner"
        assert state.base == head[:12], f"{rel} was staged without base="
        assert state.release == "v0.5.2", f"{rel} was staged without release="


def test_an_on_demand_stage_carries_a_base_but_no_release(compliance_refresh_repo, capsys):
    """AC-9b's other half: no `--release`, no `release=` token."""
    assert docs.main(["--project-root", str(compliance_refresh_repo), "--stage"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    state = parse_banner_line(
        git(compliance_refresh_repo, "show", f":{DASHBOARD}").stdout)
    assert state.base == head_sha(compliance_refresh_repo)[:12]
    assert state.release is None


def test_the_release_version_is_never_resolved_from_git(compliance_refresh_repo, capsys):
    """The tag does not exist when Step 5.5 runs, so nothing may go looking for
    one. Pinned because a later hand 'improving' this into a `git describe` would
    silently stamp the PREVIOUS release onto this one's evidence.

    Quoted argv TOKENS, never a substring: `describes` is ordinary prose here, and
    a substring test would fail on the documentation rather than the behaviour."""
    tag_reading = re.compile(r"""["'](describe|--tags|tag|for-each-ref|rev-list)["']""")
    scanned = [
        REPO_ROOT / "shared" / "scripts" / "lib" / "compliance_refresh.py",
        REPO_ROOT / "shared" / "scripts" / "source_state.py",
        *(REPO_ROOT / "shared" / "scripts" / "tools").glob("*compliance*.py"),
        REPO_ROOT / "shared" / "scripts" / "tools" / "refresh_compliance_docs.py",
    ]
    assert len(scanned) >= 5, "the scan lost its subjects"
    for path in scanned:
        hit = tag_reading.search(path.read_text(encoding="utf-8"))
        assert hit is None, f"{path.name} resolves a tag from git: {hit.group(0)}"
    # ...and the value that lands really is the one passed in.
    docs.main(["--project-root", str(compliance_refresh_repo),
               "--stage", "--release", "v9.9.9-rc1"])
    capsys.readouterr()
    state = parse_banner_line(
        git(compliance_refresh_repo, "show", f":{DASHBOARD}").stdout)
    assert state.release == "v9.9.9-rc1"


def test_stage_hands_back_a_pathspec_that_bounds_the_release_commit(compliance_refresh_repo):
    """AC-7. `git add` is additive, so staging alone does not bound the commit —
    the pathspec is what makes it exact."""
    result = docs.deliver_stage(compliance_refresh_repo, {"status": "ok"},
                                produce_mod.capture(compliance_refresh_repo), "v0.5.2")
    assert result["evidence_pathspec"] == sorted(REFRESH_SET), (
        "the tool owns the seven; the release skill adds its own artifacts"
    )
    assert "v0.5.2" in result["note"]


def test_the_release_commit_pathspec_excludes_unrelated_staged_work(compliance_refresh_repo):
    """The measured worry: something an earlier step staged rides the commit.
    Proven by planting one and committing with the printed pathspec."""
    (compliance_refresh_repo / "unrelated.txt").write_text("do not ship me\n", encoding="utf-8")
    git(compliance_refresh_repo, "add", "unrelated.txt")
    (compliance_refresh_repo / DASHBOARD).write_text("# dashboard\n\n" + "row\n" * 60, encoding="utf-8")
    (compliance_refresh_repo / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")

    result = docs.deliver_stage(compliance_refresh_repo, {"status": "ok"},
                                produce_mod.capture(compliance_refresh_repo), "v0.5.2")
    git(compliance_refresh_repo, "add", "CHANGELOG.md")
    git(compliance_refresh_repo, "commit", "-m", "chore(release): v0.5.2",
        "--", "CHANGELOG.md", *result["evidence_pathspec"])

    committed = _committed_paths(compliance_refresh_repo)
    assert "unrelated.txt" not in committed
    assert {"CHANGELOG.md", DASHBOARD} <= committed


def test_a_failed_git_add_is_not_reported_as_nothing_to_do(compliance_refresh_repo, monkeypatch):
    """The fail-open this whole change exists to remove, found inside it:
    `staged_difference` returned `[]` when `git add` failed, which both deliveries
    read as "already match" — green, having shipped nothing."""
    monkeypatch.setattr(docs, "staged_difference", lambda root, rels: None)
    result = docs.deliver_stage(compliance_refresh_repo, {"status": "ok"},
                                produce_mod.capture(compliance_refresh_repo), "v0.5.2")
    assert result["status"] == "stage_failed"
    assert "do NOT tag" in result["detail"]


def test_staged_difference_distinguishes_clean_from_blind(compliance_refresh_repo, monkeypatch):
    """`[]` and `None` must come from different causes, not the same one."""
    assert gitmod.staged_difference(compliance_refresh_repo, sorted(REFRESH_SET)) == [], (
        "an unchanged tree is a FACT, and must stay an empty list"
    )
    monkeypatch.setattr(
        gitmod, "git",
        lambda root, *a: subprocess.CompletedProcess(list(a), 1, "", "boom"))
    assert gitmod.staged_difference(compliance_refresh_repo, sorted(REFRESH_SET)) is None


# --- AC-13: the second regeneration does not win -----------------------------


def test_restore_puts_the_committed_copies_back(compliance_refresh_repo):
    """AC-13. The changelog skill's phase-completion call regenerates all seven a
    second time, unstamped and at a different commit. Without this the release
    ends with a permanently dirty worktree."""
    before = (compliance_refresh_repo / DASHBOARD).read_text(encoding="utf-8")
    (compliance_refresh_repo / DASHBOARD).write_text("# regenerated again, unstamped\n", encoding="utf-8")
    moved, unresolved = gitmod.restore_to_head(compliance_refresh_repo)
    assert unresolved == []
    assert DASHBOARD in moved
    assert (compliance_refresh_repo / DASHBOARD).read_text(encoding="utf-8") == before
    assert not git(compliance_refresh_repo, "status", "--porcelain").stdout.strip()


def test_restore_also_unstages(compliance_refresh_repo):
    """`checkout` not `restore`: a copy a producer already staged must be unstaged
    too, or the next commit carries it."""
    (compliance_refresh_repo / DASHBOARD).write_text("# staged rubbish\n", encoding="utf-8")
    git(compliance_refresh_repo, "add", "--", DASHBOARD)
    gitmod.restore_to_head(compliance_refresh_repo)
    assert not git(compliance_refresh_repo, "diff", "--cached", "--name-only").stdout.strip()


# --- AC-9b: the CLI refuses the combination it cannot mean -------------------


def test_pr_and_release_together_are_refused(compliance_refresh_repo, capsys):
    """AC-9b. A documents-only branch shipped with no release. Naming the latest
    tag would claim a membership it does not have; choosing silently would give
    one producer two meanings."""
    with pytest.raises(SystemExit):
        docs.main(["--project-root", str(compliance_refresh_repo), "--pr", "--release", "v0.5.2"])
    assert "must not claim one" in capsys.readouterr().err


def test_a_release_that_is_not_a_single_token_is_refused(compliance_refresh_repo, capsys):
    with pytest.raises(SystemExit):
        docs.main(["--project-root", str(compliance_refresh_repo), "--stage", "--release", "v1 clean"])
    assert "single usable token" in capsys.readouterr().err


def test_an_unsubstituted_placeholder_release_is_refused(compliance_refresh_repo, capsys):
    """The realistic failure: a runtime prompt whose `{version}` never got
    substituted. Otherwise a perfectly well-formed token."""
    with pytest.raises(SystemExit):
        docs.main(["--project-root", str(compliance_refresh_repo), "--stage", "--release", "{version}"])
    assert "single usable token" in capsys.readouterr().err


def test_restore_mode_needs_no_producer_and_reports_what_it_moved(compliance_refresh_repo, capsys):
    (compliance_refresh_repo / DASHBOARD).write_text("# rubbish\n", encoding="utf-8")
    assert docs.main(["--project-root", str(compliance_refresh_repo), "--restore"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "restored"
    assert DASHBOARD in payload["restored"]
    # ...and RESTORED means the committed bytes are back, not that the path was
    # dealt with. The destructive branch also lands a path in `restored`, so
    # without this the test passes when the file was DELETED (Stage-3, test 5).
    assert (compliance_refresh_repo / DASHBOARD).is_file()
    assert not git(compliance_refresh_repo, "status", "--porcelain").stdout.strip()


def test_a_refused_regeneration_leaves_no_untrusted_content_behind(compliance_refresh_repo, capsys, monkeypatch):
    """A refusal that leaves its own rejected output in the tree hands the next
    `git add` exactly the content this run declined to trust."""
    def emptying(root, run_id):
        (root / DASHBOARD).write_text("", encoding="utf-8")
        return all_ok()

    monkeypatch.setattr(produce_mod, "converge",
                        lambda root, *a, **k: (emptying(root, RUN), (True, 2, all_ok()))[1])
    assert docs.main(["--project-root", str(compliance_refresh_repo), "--stage"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "content_floor"
    # `produce` rewinds to what it FOUND, and it found a clean tree here — so a
    # clean tree is the correct outcome. The operator-edit case (where rewinding
    # to HEAD would have destroyed work) is pinned in test_compliance_refresh_produce.
    assert not git(compliance_refresh_repo, "status", "--porcelain").stdout.strip()


# --- the commit, not the index (Stage-3 doubt D2) ----------------------------


def test_verify_commit_reads_the_COMMIT_and_catches_an_unstamped_one(
    compliance_refresh_repo,
):
    """`git commit -- <paths>` records the WORKTREE, so every index-based check in
    this change proves nothing about what shipped. This is the one check that
    reads the artifact."""
    git(compliance_refresh_repo, "commit", "--allow-empty", "-m", "unstamped release")
    sha = head_sha(compliance_refresh_repo)
    report = docs.verify_commit(compliance_refresh_repo, sha)
    assert report["status"] == "unstamped_in_commit"
    assert sorted(report["unstamped"]) == sorted(COMPLIANCE_MDS)


def test_verify_commit_passes_on_a_commit_that_really_carries_the_stamp(
    compliance_refresh_repo, capsys,
):
    assert docs.main(["--project-root", str(compliance_refresh_repo),
                      "--stage", "--release", "v0.5.2"]) == 0
    staged = json.loads(capsys.readouterr().out)
    # Commit with the pathspec the tool printed — the whole point of emitting it.
    git(compliance_refresh_repo, "commit", "-m", "chore(release): v0.5.2",
        "--", *staged["evidence_pathspec"])
    report = docs.verify_commit(compliance_refresh_repo,
                                head_sha(compliance_refresh_repo))
    assert report["status"] == "verified"
    assert report["unstamped"] == []
