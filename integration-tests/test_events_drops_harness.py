"""Bare-origin harness for the per-run drops layout (issue 978, campaign S0).

Real ``record_event.py`` runs in three worktrees of a clone of a bare origin; each
branch records events and commits them (an F6-like step); ``git merge-tree``
WITHOUT union (``--attr-source`` = empty tree, what GitHub's mergeability check
effectively does) then judges every branch pair.

* legacy layout: every pair CONFLICTS (the #978 symptom, reproduced);
* drops layout (test-only override): every pair is CLEAN;
* the plain env var WITHOUT the test flag changes nothing (still legacy).

Not an S0 pass condition: a real ``ensure_current`` on drops (it works only after
S3 migrates the classifier and ``_reconcile_events``).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RECORD_EVENT = REPO / "shared" / "scripts" / "tools" / "record_event.py"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
PAIRS = ((1, 2), (1, 3), (2, 3))
BASE_LOG = "".join(
    '{"ts":"2026-10-01T09:00:00Z","type":"task_created","id":"0000000%d","description":"base %d"}\n' % (i, i)
    for i in range(1, 4)
)


def _git(cwd, *args, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    if check and r.returncode:
        raise AssertionError(f"git {args} failed: {r.stdout[-600:]} {r.stderr[-600:]}")
    return r


def _git_version() -> tuple[int, ...]:
    out = subprocess.run(["git", "--version"], capture_output=True, text=True).stdout
    digits = [p for p in out.split()[2].split(".")[:3] if p.isdigit()]
    return tuple(int(p) for p in digits)


pytestmark = pytest.mark.skipif(
    _git_version() < (2, 40), reason="git merge-tree --write-tree with --attr-source needs git >= 2.40")


def _record(wt: Path, run_id: str, desc: str, env_extra: dict[str, str]) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("SHIPWRIGHT_EVENTS_LAYOUT")}
    env.update({"SHIPWRIGHT_RUN_ID": run_id, "PYTHONIOENCODING": "utf-8", **env_extra})
    r = subprocess.run(
        [sys.executable, str(RECORD_EVENT), "--project-root", str(wt), "--type", "task_created",
         "--description", desc, "--source", "harness"],
        cwd=wt, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, f"record_event failed: {r.stdout[-400:]} {r.stderr[-600:]}"


def _world(tmp_path: Path, env_extra: dict[str, str]) -> dict[int, Path]:
    origin, main = tmp_path / "o.git", tmp_path / "m"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(main))
    for key, val in (("user.email", "t@t"), ("user.name", "t")):
        _git(main, "config", key, val)
    (main / "shipwright_events.jsonl").write_text(BASE_LOG, encoding="utf-8", newline="\n")
    (main / ".gitignore").write_text("*.lock\n.worktrees/\n")
    (main / ".gitattributes").write_text("shipwright_events.jsonl merge=union" + chr(10))
    _git(main, "add", "-A")
    _git(main, "commit", "-q", "-m", "base")
    _git(main, "push", "-q", "origin", "main")
    wts = {}
    for n in (1, 2, 3):
        wt = tmp_path / f"w{n}"
        _git(main, "worktree", "add", "-q", "-b", f"iterate/r{n}", str(wt), "origin/main")
        for key, val in (("user.email", "t@t"), ("user.name", "t")):
            _git(wt, "config", key, val)
        for i in range(2):
            _record(wt, f"run-{n}", f"event {i} of run {n}", env_extra)
        _git(wt, "add", "shipwright_events.jsonl")
        if (wt / "shipwright_events.d").exists():
            _git(wt, "add", "shipwright_events.d")
        _git(wt, "commit", "-q", "-m", f"run {n}")
        wts[n] = wt
    return wts


def _merge_tree(main_wt: Path, a: int, b: int, *, honour_attributes: bool = False) -> bool:
    """True = clean merge, False = content conflict. Any OTHER git failure raises.

    Default: attributes are NOT consulted (empty attr-source), as GitHub's check.
    """
    head = [] if honour_attributes else [f"--attr-source={EMPTY_TREE}"]
    r = _git(main_wt, *head, "merge-tree", "--write-tree", "--name-only",
             f"iterate/r{a}", f"iterate/r{b}", check=False)
    assert r.returncode in (0, 1), f"merge-tree errored (rc={r.returncode}): {r.stderr[-400:]}"
    return r.returncode == 0


def _merged_tree_files(main_wt: Path, a: int, b: int) -> dict[str, bytes]:
    """File contents of the clean merge result of branches a and b (drops only)."""
    out = _git(main_wt, f"--attr-source={EMPTY_TREE}", "merge-tree", "--write-tree",
               f"iterate/r{a}", f"iterate/r{b}").stdout.split()[0]
    names = _git(main_wt, "ls-tree", "-r", "--name-only", out).stdout.split()
    return {n: subprocess.run(["git", "show", f"{out}:{n}"], cwd=main_wt, capture_output=True, check=True).stdout
            for n in names if n.startswith("shipwright_events.d/")}


def test_legacy_layout_conflicts_on_every_pair(tmp_path):
    wts = _world(tmp_path, {})
    assert [_merge_tree(wts[1], a, b) for a, b in PAIRS] == [False, False, False]
    # the conflict is caused by GitHub not honouring merge=union: locally it merges
    assert [_merge_tree(wts[1], a, b, honour_attributes=True) for a, b in PAIRS] == [True, True, True]
    assert not (wts[1] / "shipwright_events.d").exists()


def test_drops_layout_is_clean_on_every_pair(tmp_path):
    wts = _world(tmp_path, {"SHIPWRIGHT_EVENTS_LAYOUT": "drops", "SHIPWRIGHT_EVENTS_LAYOUT_TEST": "1"})
    assert [_merge_tree(wts[1], a, b) for a, b in PAIRS] == [True, True, True]
    for a, b in PAIRS:  # the merge result holds BOTH runs' events, byte for byte
        merged = _merged_tree_files(wts[1], a, b)
        assert len(merged) == 2
        for n in (a, b):
            (own,) = sorted((wts[n] / "shipwright_events.d").glob("*.jsonl"))
            assert merged[f"shipwright_events.d/{own.name}"] == own.read_bytes().replace(bytes([13, 10]), bytes([10]))
            assert merged[f"shipwright_events.d/{own.name}"].count(b"of run %d" % n) == 2
    for n, wt in wts.items():
        files = sorted((wt / "shipwright_events.d").glob("*.jsonl"))
        assert len(files) == 1 and files[0].name.startswith(f"run-{n}--")
        assert len(files[0].read_text(encoding="utf-8").splitlines()) == 2
        # the legacy log is untouched by the drops writer
        assert (wt / "shipwright_events.jsonl").read_text(encoding="utf-8") == BASE_LOG
        # the lock lives outside the tracked folder
        assert not list((wt / "shipwright_events.d").glob("*.lock"))


def test_plain_env_var_without_test_flag_stays_legacy(tmp_path):
    wts = _world(tmp_path, {"SHIPWRIGHT_EVENTS_LAYOUT": "drops"})
    assert [_merge_tree(wts[1], a, b) for a, b in PAIRS] == [False, False, False]
    assert not (wts[1] / "shipwright_events.d").exists()
