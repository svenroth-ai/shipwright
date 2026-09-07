"""The git-correlation half of ``tools/backfill_ac_provenance.py`` --
``_commits_for_run_id`` / ``_added_test_files`` / ``_is_shallow_clone`` --
against a REAL, throwaway git repo built in ``tmp_path``. Split out of
``test_backfill_ac_provenance_cli.py`` at the 300-LOC bloat-baseline threshold
(same precedent as the production module's own ``_backfill_ac_provenance_apply.py``
split); the pure-logic tests (conflict marking, apply/validate, status
accounting) stay in the sibling file.

External code review (P3.4, glm medium): an earlier version of the production
module claimed the git join was "exercised indirectly by running the tool
against this repo's own history" with no such test actually committed, and
the join's own real-repo behaviour had already produced one wrong batch of 7
files (reverted; see ``lib.backfill_ac_provenance``'s "document-wide, not
per-FR" note) before this test existed.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

_SPEC = importlib.util.spec_from_file_location(
    "backfill_ac_provenance_cli_git", _TOOLS / "backfill_ac_provenance.py",
)
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)  # type: ignore[union-attr]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                    capture_output=True, text=True)


def _init_repo_with_commit(repo: Path, message: str, filename: str = "a.txt") -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / filename).write_text("x", encoding="utf-8")
    _git(repo, "add", filename)
    _git(repo, "commit", "-q", "-m", message)


def test_commits_for_run_id_finds_the_exact_trailer_line(tmp_path):
    _init_repo_with_commit(tmp_path, "fix: a thing\n\nRun-ID: iterate-2026-01-01-real-slug\n")
    commits = mod._commits_for_run_id(tmp_path, "iterate-2026-01-01-real-slug")
    assert len(commits) == 1


def test_commits_for_run_id_does_not_cross_match_a_prefix_slug(tmp_path):
    # "iterate-2026-01-01-real-slug" is a PREFIX of the actual trailer below --
    # a naive substring/regex match would over-report; the exact whole-line
    # check must not.
    _init_repo_with_commit(
        tmp_path, "fix: a thing\n\nRun-ID: iterate-2026-01-01-real-slug-follow-up\n",
    )
    commits = mod._commits_for_run_id(tmp_path, "iterate-2026-01-01-real-slug")
    assert commits == []


def test_commits_for_run_id_reports_nothing_for_an_unknown_slug(tmp_path):
    _init_repo_with_commit(tmp_path, "fix: a thing\n\nRun-ID: iterate-2026-01-01-real-slug\n")
    commits = mod._commits_for_run_id(tmp_path, "iterate-2026-09-09-never-happened")
    assert commits == []


def test_added_test_files_reports_only_status_a_python_test_files(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-q", "-m", "init")

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_new.py").write_text("def test_x(): pass\n", encoding="utf-8")
    (tmp_path / "not_a_test.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("changed", encoding="utf-8")  # modified, not added
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "add a test file and touch other things")
    head = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
                           check=True, capture_output=True, text=True).stdout.strip()

    added = mod._added_test_files(tmp_path, head)
    assert added == ["tests/test_new.py"]


def test_is_shallow_clone_is_false_for_a_normal_repo(tmp_path):
    _init_repo_with_commit(tmp_path, "init")
    assert mod._is_shallow_clone(tmp_path) is False


# --------------------------------------------------------------------------- #
# git-command-failure branches (never a fake stub -- a real git call that     #
# genuinely fails, e.g. against a directory that is not a repo at all)        #
# --------------------------------------------------------------------------- #

def test_commit_has_own_run_id_line_is_false_on_a_git_failure(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)  # not a git repo at all
    assert mod._commit_has_own_run_id_line(tmp_path, "deadbeef", "iterate-x") is False


def test_commits_for_run_id_is_empty_on_a_git_failure(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    assert mod._commits_for_run_id(tmp_path, "iterate-x") == []


def test_added_test_files_is_none_on_a_git_failure(tmp_path):
    _init_repo_with_commit(tmp_path, "init")
    assert mod._added_test_files(tmp_path, "0000000000000000000000000000000000000000") is None


# --------------------------------------------------------------------------- #
# derive() / main() end to end, against a REAL repo (GLM code-review medium:  #
# "no test exercises derive()'s real git-join path")                         #
# --------------------------------------------------------------------------- #

_DERIVE_SPEC = (
    "### FR-01.01 — /shipwright-run\n\n"
    "- (E) [AC01] Given a described change, when the pipeline is run, then\n"
    "  the phases are carried out in order. (iterate-2026-01-01-real-slug)\n"
    "- (E) [AC02] Given a slug nobody ever committed, when derive runs, then\n"
    "  it is reported, never guessed. (iterate-2026-09-09-never-happened)\n"
    "- (E) [AC03] Given a commit that touched no test file, when derive runs,\n"
    "  then it is reported, never guessed. (iterate-2026-02-02-docs-only)\n"
)


def _build_derive_repo(tmp_path: Path) -> Path:
    """A repo with ONE resolvable candidate (AC01, a real commit that ADDED a
    test file), one that resolves to NO commit at all (AC02), and one whose
    commit exists but added no test-shaped file (AC03) -- so a single
    `derive()`/`main()` call exercises the ``candidate`` path AND both
    non-candidate accounting branches in the same run."""
    _init_repo_with_commit(tmp_path, "init")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_new.py").write_text("def test_x(): pass\n", encoding="utf-8")
    _git(tmp_path, "add", "tests/test_new.py")
    _git(tmp_path, "commit", "-q", "-m", "add a test\n\nRun-ID: iterate-2026-01-01-real-slug\n")
    (tmp_path / "README.md").write_text("docs only\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-q", "-m", "docs only\n\nRun-ID: iterate-2026-02-02-docs-only\n")
    spec = tmp_path / "spec.md"
    spec.write_text(_DERIVE_SPEC, encoding="utf-8")
    return spec


def test_derive_end_to_end_against_a_real_repo(tmp_path):
    spec = _build_derive_repo(tmp_path)
    report = mod.derive(tmp_path, spec)
    assert report["candidate_count"] == 1
    candidate = next(c for c in report["candidates"] if c["status"] == "candidate")
    assert candidate == {
        "fr_id": "FR-01.01", "ac_id": "AC01", "slug": "iterate-2026-01-01-real-slug",
        "commit": candidate["commit"], "status": "candidate",
        "test_files": ["tests/test_new.py"],
    }
    assert report["status_counts"] == {
        "candidate": 1, "no_commit_found": 1, "no_added_test_file_in_commit": 1,
    }


def test_main_write_end_to_end_against_a_real_repo(tmp_path):
    spec = _build_derive_repo(tmp_path)
    rc = mod.main(["--project-root", str(tmp_path), "--spec-file", str(spec), "--write"])
    assert rc == 0
    text = (tmp_path / "tests" / "test_new.py").read_text(encoding="utf-8")
    assert 'covers("FR-01.01/AC01")' in text


def test_main_dry_run_end_to_end_against_a_real_repo(tmp_path):
    spec = _build_derive_repo(tmp_path)
    rc = mod.main(["--project-root", str(tmp_path), "--spec-file", str(spec)])
    assert rc == 0
    # dry run: nothing written
    text = (tmp_path / "tests" / "test_new.py").read_text(encoding="utf-8")
    assert "covers" not in text


def test_main_refuses_a_shallow_clone(tmp_path, monkeypatch):
    spec = _build_derive_repo(tmp_path)
    monkeypatch.setattr(mod, "_is_shallow_clone", lambda *_: True)
    rc = mod.main(["--project-root", str(tmp_path), "--spec-file", str(spec)])
    assert rc == 1
