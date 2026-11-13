"""A fold racing an open PR is clean; the integrity check blocks what would not be (issue 978, S6, KC6).

Bare origin + two clones. Main holds two old merged drops. An open PR adds its own drop while main folds
(real ``fold_events.py``, real ``check_events_integrity.py``). ``git merge-tree`` WITHOUT attributes judges the
pair the way GitHub's mergeability check does. A PR that edited a folded file is the conflicting case the
integrity rule exists to forbid.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FOLD = REPO / "shared" / "scripts" / "tools" / "fold_events.py"
CHECK = REPO / "shared" / "scripts" / "checks" / "check_events_integrity.py"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
DROPS = ".shipwright/events/drops"
OLD_TS = "2026-01-05T10:00:00+00:00"
pytestmark = pytest.mark.covers("FR-01.11")


def _git(cwd, *args, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert not check or r.returncode == 0, f"git {args}: {r.stderr[-500:]}"
    return r


def _put(root: Path, name: str, event_id: str, ts: str = OLD_TS) -> None:
    key = name.split("--")[0]
    (root / DROPS).mkdir(parents=True, exist_ok=True)
    line = json.dumps({"v": 1, "id": event_id, "ts": ts, "type": "task_created", "run": key}, separators=(",", ":"))
    (root / DROPS / name).write_text(line + "\n", encoding="utf-8", newline="\n")


def _tool(script: Path, root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), "--project-root", str(root), *args],
                          capture_output=True, text=True, encoding="utf-8", timeout=120)


def _merge_tree_clean(cwd: Path, a: str, b: str) -> bool:
    r = _git(cwd, f"--attr-source={EMPTY_TREE}", "merge-tree", "--write-tree", "--name-only", a, b, check=False)
    assert r.returncode in (0, 1), r.stderr
    return r.returncode == 0


@pytest.fixture(name="world")
def _world(tmp_path):
    origin, main = tmp_path / "o.git", tmp_path / "m"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(main))
    for k, v in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false"), ("core.autocrlf", "false")):
        _git(main, "config", k, v)
    (main / ".gitignore").write_text("*.lock\n", encoding="utf-8")
    _put(main, "run-a--aaaaaaaa--00000001.jsonl", "evt-a")
    _put(main, "run-b--aaaaaaaa--00000001.jsonl", "evt-b")
    _git(main, "add", "-A")
    _git(main, "commit", "-q", "-m", "two merged drops")
    _git(main, "push", "-q", "origin", "main")
    return main


def _open_pr(main: Path, branch: str, edit_old: bool) -> None:
    _git(main, "switch", "-q", "-c", branch, "origin/main")
    if edit_old:
        old = main / DROPS / "run-a--aaaaaaaa--00000001.jsonl"
        old.write_text(old.read_text(encoding="utf-8") + '{"v":1,"id":"evt-x","ts":"2026-11-01T00:00:00+00:00"}\n',
                       encoding="utf-8", newline="\n")
    else:
        _put(main, f"{branch}--bbbbbbbb--00000002.jsonl", "evt-pr", "2026-11-06T09:00:00+00:00")
    _git(main, "add", "-A")
    _git(main, "commit", "-q", "-m", branch)
    _git(main, "switch", "-q", "main")


def _fold_on_main(main: Path) -> str:
    before = _git(main, "rev-parse", "HEAD").stdout.strip()
    done = _tool(FOLD, main, "fold", "--stage", "--base-ref", "HEAD")
    assert done.returncode == 0, done.stdout + done.stderr
    assert json.loads(done.stdout)["status"] == "folded"
    _git(main, "commit", "-q", "-m", "chore(events): fold")
    _git(main, "push", "-q", "origin", "main")
    return before


def test_a_fold_racing_an_open_pr_that_only_adds_is_clean(world):
    main = world
    _open_pr(main, "pr-add", edit_old=False)
    before = _fold_on_main(main)
    _git(main, "fetch", "-q", "origin")
    assert _merge_tree_clean(main, "pr-add", "origin/main")
    # the fold commit itself passes the integrity check, and so does the PR
    assert _tool(CHECK, main, "--base-ref", before, "--head-ref", "origin/main").returncode == 0
    assert _tool(CHECK, main, "--base-ref", "origin/main", "--head-ref", "pr-add").returncode == 0
    merged = _git(main, f"--attr-source={EMPTY_TREE}", "merge-tree", "--write-tree", "pr-add", "origin/main").stdout.split()[0]
    names = _git(main, "ls-tree", "-r", "--name-only", merged).stdout.split()
    # the fold emptied the drops folder, so it left the empty .keep: without it git reads the fold as a
    # directory rename (drops -> archive) and flags the PR's new drop as a "file location" conflict
    assert [n for n in names if n.startswith(DROPS)] == [f"{DROPS}/.keep", f"{DROPS}/pr-add--bbbbbbbb--00000002.jsonl"]
    assert any(n.startswith(".shipwright/events/archive/fold-") for n in names)


def test_a_pr_that_edited_a_folded_file_conflicts_and_the_checker_blocks_it(world):
    main = world
    _open_pr(main, "pr-edit", edit_old=True)
    _fold_on_main(main)
    _git(main, "fetch", "-q", "origin")
    assert not _merge_tree_clean(main, "pr-edit", "origin/main")       # modify/delete: the conflict the rule prevents
    blocked = _tool(CHECK, main, "--base-ref", "origin/main~1", "--head-ref", "pr-edit")
    assert blocked.returncode == 1
    assert [v["code"] for v in json.loads(blocked.stdout)["violations"]] == ["modified_existing"]
