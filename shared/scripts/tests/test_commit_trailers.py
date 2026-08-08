from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.commit_trailers import build_run_id_commit_map, resolve_base_ref  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                    capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "checkout", "-q", "-b", "main")


def _commit(repo: Path, filename: str, content: str, message: str) -> str:
    (repo / filename).parent.mkdir(parents=True, exist_ok=True)
    (repo / filename).write_text(content, encoding="utf-8")
    _git(repo, "add", filename)
    _git(repo, "commit", "-q", "-m", message)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


def test_resolve_base_ref_falls_back_to_head_with_no_origin(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    sha = _commit(repo, "a.txt", "1", "chore: init")
    assert resolve_base_ref(repo) == ("HEAD", sha)


def test_resolve_base_ref_none_for_non_repo(tmp_path: Path) -> None:
    assert resolve_base_ref(tmp_path / "not-a-repo") is None


def test_build_map_backfills_sha_and_files_from_run_id_trailer(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit(repo, "a.txt", "1", "chore: init")
    sha = _commit(repo, "src/thing.py", "2",
                  "feat(thing): add\n\nRun-ID: iterate-2026-01-01-thing\nCo-Authored-By: x")
    result = build_run_id_commit_map(repo, resolve_base_ref(repo))
    assert result["status"] == "ok"
    assert result["commits_scanned"] == 1  # --grep=Run-ID: excludes the trailer-less init commit
    entry = result["map"]["iterate-2026-01-01-thing"]
    assert entry["sha"] == sha
    assert entry["changed_files"] == ["src/thing.py"]
    assert entry["changed_files_truncated"] is False


def test_build_map_no_repo_status(tmp_path: Path) -> None:
    result = build_run_id_commit_map(tmp_path / "nope", None)
    assert result["status"] == "no-repo"
    assert result["map"] == {}
    assert result["commits_scanned"] == 0


def test_merge_commit_run_id_excluded_from_map(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit(repo, "a.txt", "1", "chore: init")
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "b.txt", "2", "feat: b")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "c.txt", "3", "feat: c")
    _git(repo, "merge", "--no-ff", "-q", "feature",
        "-m", "Merge feature\n\nRun-ID: iterate-2026-01-01-merged")
    result = build_run_id_commit_map(repo, resolve_base_ref(repo))
    assert "iterate-2026-01-01-merged" not in result["map"]


def test_default_git_revert_carries_no_trailer_so_original_run_id_wins(tmp_path: Path) -> None:
    # `git revert --no-edit`'s default message copies only the subject line,
    # never the body — verified empirically — so the reverted commit itself
    # never matches `_RUN_ID_TRAILER_RE` and the original entry is untouched
    # without the "Revert " guard doing any work here.
    repo = tmp_path / "repo"
    _init_repo(repo)
    original_sha = _commit(repo, "src/one.py", "2",
                           "feat: one\n\nRun-ID: iterate-2026-01-01-reverted")
    _git(repo, "revert", "--no-edit", original_sha)
    result = build_run_id_commit_map(repo, resolve_base_ref(repo))
    entry = result["map"]["iterate-2026-01-01-reverted"]
    assert entry["sha"] == original_sha
    assert entry["changed_files"] == ["src/one.py"]


def test_revert_subject_commit_with_its_own_run_id_recovers_normally(tmp_path: Path) -> None:
    # A `git revert` commit whose fix genuinely IS the revert can carry its
    # own, legitimately fresh Run-ID trailer (e.g. F6 stamps it via -e or
    # amend). The spec's only stated exclusion is merge commits -- a broader
    # "skip every Revert-subject commit" guard was tried and then removed
    # (external review, iterate-2026-08-07-events-context-backfill-keys): it
    # would have discarded exactly this legitimate case.
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit(repo, "src/one.py", "2", "feat: one")
    sha = _commit(repo, "src/two.py", "3",
                  'Revert "feat: one"\n\nThis reverts a bad change.\n\n'
                  "Run-ID: iterate-2026-01-01-genuinerevert")
    result = build_run_id_commit_map(repo, resolve_base_ref(repo))
    entry = result["map"]["iterate-2026-01-01-genuinerevert"]
    assert entry["sha"] == sha
    assert entry["changed_files"] == ["src/two.py"]


def test_lowercase_trailer_matches_the_case_insensitive_git_grep_prefilter(tmp_path: Path) -> None:
    # _RUN_ID_TRAILER_RE is `(?i)` (case-insensitive); the git-side --grep
    # prefilter must match with the same case-insensitivity or it silently
    # narrows what the Python regex would have matched (external review
    # openai finding, iterate-2026-08-07-events-context-backfill-keys).
    repo = tmp_path / "repo"
    _init_repo(repo)
    sha = _commit(repo, "src/one.py", "2", "feat: one\n\nrun-id: iterate-2026-01-01-lowercase")
    result = build_run_id_commit_map(repo, resolve_base_ref(repo))
    entry = result["map"]["iterate-2026-01-01-lowercase"]
    assert entry["sha"] == sha
    assert entry["changed_files"] == ["src/one.py"]


def test_duplicate_run_id_unions_files_newest_sha_wins(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit(repo, "a.txt", "1", "chore: init")
    first_sha = _commit(repo, "src/one.py", "2",
                        "feat: one\n\nRun-ID: iterate-2026-01-01-dup")
    second_sha = _commit(repo, "src/two.py", "3",
                         "fix: repair\n\nRun-ID: iterate-2026-01-01-dup")
    result = build_run_id_commit_map(repo, resolve_base_ref(repo))
    entry = result["map"]["iterate-2026-01-01-dup"]
    assert entry["sha"] == second_sha
    assert entry["sha"] != first_sha
    assert entry["changed_files"] == ["src/one.py", "src/two.py"]


def test_changed_files_capped_and_truncation_flagged(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    for i in range(60):
        (repo / f"file{i}.txt").write_text(str(i), encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "feat: many\n\nRun-ID: iterate-2026-01-01-many")
    result = build_run_id_commit_map(repo, resolve_base_ref(repo))
    entry = result["map"]["iterate-2026-01-01-many"]
    assert len(entry["changed_files"]) == 50
    assert entry["changed_files_truncated"] is True


def test_truncation_prefers_source_paths_over_dot_prefixed_bookkeeping(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    for i in range(40):
        (repo / f".shipwright/bookkeeping{i}.json").parent.mkdir(parents=True, exist_ok=True)
        (repo / f".shipwright/bookkeeping{i}.json").write_text(str(i), encoding="utf-8")
    for i in range(20):
        (repo / f"shared/src{i}.py").parent.mkdir(parents=True, exist_ok=True)
        (repo / f"shared/src{i}.py").write_text(str(i), encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "feat: many\n\nRun-ID: iterate-2026-01-01-bias")
    result = build_run_id_commit_map(repo, resolve_base_ref(repo))
    entry = result["map"]["iterate-2026-01-01-bias"]
    assert len(entry["changed_files"]) == 50
    assert entry["changed_files_truncated"] is True
    kept_source = [p for p in entry["changed_files"] if p.startswith("shared/")]
    assert len(kept_source) == 20  # all 20 source paths survive the cap; only bookkeeping is dropped


def test_base_ref_is_pinned_to_a_sha_before_scanning(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    sha = _commit(repo, "a.txt", "1", "feat: a\n\nRun-ID: iterate-2026-01-01-pin")
    result = build_run_id_commit_map(repo, resolve_base_ref(repo))
    assert result["resolved_sha"] == sha
    assert result["base_ref_used"] == "HEAD"


def test_commit_without_trailer_is_absent_from_map(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit(repo, "a.txt", "1", "chore: no trailer here")
    result = build_run_id_commit_map(repo, resolve_base_ref(repo))
    assert result["map"] == {}
    assert result["commits_scanned"] == 0  # --grep=Run-ID: excludes it before either walk
