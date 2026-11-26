"""A refused evidence refresh unstages what it staged (pilot P8b, FULLRUN-REPORT F8).

Subject: ``shared/scripts/tools/refresh_compliance_docs.py`` (``--stage``) and ``tools.compliance_git.restore_index``.
Old behaviour (scenario S16b): ``produce`` rewound the WORKING TREE of a refusal, but the producers had already ``git add``-ed
what they wrote, so six evidence paths stayed staged ("AD"/"MM" in ``git status``) while the reference said the tree was
restored. The fix puts the index of the seven back to what the run found: what the run staged is unstaged, and an entry the
operator had staged before the run stays exactly as it was.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from _compliance_refresh_fixtures import DASHBOARD, RUN, all_ok, git, seed_repo  # noqa: E402
from tools import compliance_git as gitmod  # noqa: E402
from tools import compliance_refresh_produce as produce_mod  # noqa: E402
from tools import refresh_compliance_docs as docs  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.09/AC01")

NEW = ".shipwright/compliance/ci-security.json"  # a path HEAD lacks: the producer creates it
OPERATOR = ".shipwright/compliance/test-evidence.md"


def _staged(root: Path) -> list[str]:
    return sorted(line for line in git(root, "diff", "--cached", "--name-only").stdout.splitlines() if line)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = seed_repo(tmp_path / "repo")
    git(root, "rm", "-q", "--", NEW)
    git(root, "commit", "-q", "-m", "no ci scan yet")
    return root


def test_a_refused_refresh_unstages_what_it_staged_and_keeps_what_the_operator_staged(repo, capsys, monkeypatch):
    operator = repo / OPERATOR
    operator.write_text(operator.read_text(encoding="utf-8") + "operator row\n", encoding="utf-8")
    git(repo, "add", "--", OPERATOR)
    staged_before = git(repo, "ls-files", "-s", "--", OPERATOR).stdout

    def producers_that_stage(root):  # what the real producers do: write, then `git add` what they wrote
        (root / DASHBOARD).write_text("", encoding="utf-8")  # emptied: the content floor refuses it
        (root / NEW).write_text(json.dumps({"rows": ["y"] * 40}), encoding="utf-8")
        git(root, "add", "--", DASHBOARD, NEW)
        return all_ok()

    monkeypatch.setattr(produce_mod, "converge", lambda root, *a, **k: (producers_that_stage(root), (True, 2, all_ok()))[1])
    code = docs.main(["--project-root", str(repo), "--stage", "--run-id", RUN])
    payload = json.loads(capsys.readouterr().out)
    assert (code, payload["status"]) == (1, "content_floor")
    assert sorted(payload["unstaged"]) == sorted([DASHBOARD, NEW])
    assert _staged(repo) == [OPERATOR] and git(repo, "ls-files", "-s", "--", OPERATOR).stdout == staged_before
    assert git(repo, "status", "--porcelain").stdout.splitlines() == [f"M  {OPERATOR}"]


def test_restore_index_touches_only_entries_that_moved(repo):
    before = gitmod.index_entries(repo)
    assert gitmod.restore_index(repo, before) == ([], [])
    (repo / DASHBOARD).write_text("changed\n", encoding="utf-8")
    git(repo, "add", "--", DASHBOARD)
    assert gitmod.restore_index(repo, before) == ([DASHBOARD], []) and _staged(repo) == []


def test_an_untracked_copy_the_run_found_survives_and_the_staged_output_is_unstaged(tmp_path, capsys, monkeypatch):
    """External code review (openai, high): ``git rm --cached`` refused when the restored working-tree copy matched
    neither HEAD nor the index; ``update-index --force-remove`` is index-only."""
    root = seed_repo(tmp_path / "repo")
    git(root, "rm", "-q", "--", NEW)
    git(root, "commit", "-q", "-m", "no ci scan yet")
    (root / NEW).write_text("operator's own untracked copy\n", encoding="utf-8")

    def producers_that_stage(r):
        (r / DASHBOARD).write_text("", encoding="utf-8")
        (r / NEW).write_text(json.dumps({"rows": ["y"] * 40}), encoding="utf-8")
        git(r, "add", "--", DASHBOARD, NEW)
        return all_ok()

    monkeypatch.setattr(produce_mod, "converge", lambda r, *a, **k: (producers_that_stage(r), (True, 2, all_ok()))[1])
    assert docs.main(["--project-root", str(root), "--stage", "--run-id", RUN]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert NEW in payload["unstaged"] and payload["unstage_failed"] == []
    assert _staged(root) == [] and (root / NEW).read_text(encoding="utf-8") == "operator's own untracked copy\n"


def test_a_conflicted_path_is_no_entry_is_reported_and_is_never_touched(repo):
    """Fix round 1 (code review): ``index_entries`` takes stage 0 only; a path with a merge conflict (stages 1-3) is
    reported, and ``restore_index`` leaves it as it is (writing a stage-0 entry would resolve the conflict)."""
    before = gitmod.index_entries(repo)
    blob = git(repo, "hash-object", "-w", "--", DASHBOARD).stdout.strip()
    git(repo, "update-index", "--force-remove", "--", DASHBOARD)
    for stage in (1, 2, 3):
        subprocess.run(["git", "-C", str(repo), "update-index", "--index-info"], input=f"100644 {blob} {stage}\t{DASHBOARD}\n".encode(),
                       check=True, capture_output=True)  # bytes: text mode on Windows would send "\r\n" into the path
    conflicted: list[str] = []
    assert DASHBOARD not in gitmod.index_entries(repo, conflicted) and conflicted == [DASHBOARD]
    staged = git(repo, "ls-files", "-s", "--", DASHBOARD).stdout
    assert gitmod.restore_index(repo, before) == ([], [DASHBOARD])
    assert git(repo, "ls-files", "-s", "--", DASHBOARD).stdout == staged and len(staged.splitlines()) == 3
