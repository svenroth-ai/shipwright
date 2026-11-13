"""Whole-system scenarios of the per-run drops layout (issue 978, S8, KC3).

Bare origin + clone + real worktrees; the REAL ``record_event``, ``ensure_current``, ``fold_events``,
``check_events_integrity`` and ``check_events_layout_ci`` run as subprocesses, with the flip done the way an
operator does it (``events_layout`` in ``shipwright_sync_config.json``, no test override). ``git merge-tree``
without attributes judges mergeability the way GitHub does.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_events_drops_harness import BASE_LOG, EMPTY_TREE, _git, _git_version

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "shared" / "scripts"))
TOOLS, CHECKS = REPO / "shared" / "scripts" / "tools", REPO / "shared" / "scripts" / "checks"
CONFIG = "shipwright_sync_config.json"

pytestmark = [pytest.mark.covers("FR-01.11"), pytest.mark.skipif(
    _git_version() < (2, 40), reason="needs git >= 2.40")]


def _env(run_id: str = "", session: str = "sess-wave") -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("SHIPWRIGHT_")}
    env.update({"PYTHONIOENCODING": "utf-8", "SHIPWRIGHT_SESSION_ID": session})
    if run_id:
        env["SHIPWRIGHT_RUN_ID"] = run_id
    return env


def _run(script: Path, root: Path, *args: str, run_id: str = "", ok: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run([sys.executable, str(script), "--project-root", str(root), *args], cwd=root, env=_env(run_id),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    assert not ok or r.returncode == 0, f"{script.name} {args}: {r.stdout[-600:]} {r.stderr[-600:]}"
    return r


def _record(wt: Path, run_id: str, kind: str = "task_created", ok: bool = True) -> subprocess.CompletedProcess:
    extra = ["--description", f"event of {run_id}", "--source", "wave"]
    if kind == "work_completed":
        extra = ["--source", "iterate", "--intent", "change", "--description", f"work of {run_id}", "--adr-id", run_id,
                 "--change-type", "tooling", "--none-reason", "tooling only", "--spec-impact", "none",
                 "--spec-impact-justification", "tooling only", "--spec-impact-reason-code", "tooling-only"]
    return _run(TOOLS / "record_event.py", wt, "--type", kind, *extra, run_id=run_id, ok=ok)


def _identity(path: Path) -> None:
    for k, v in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false"), ("core.autocrlf", "false")):
        _git(path, "config", k, v)


def _commit(wt: Path, msg: str) -> None:
    _git(wt, "add", "-A")
    _git(wt, "commit", "-q", "-m", msg)


def _main(tmp_path: Path, layout: str | None) -> Path:
    """A clone of a bare origin holding the legacy base log; ``layout`` goes into the sync config (``None``: no key)."""
    origin, main = tmp_path / "o.git", tmp_path / "m"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(main))
    _identity(main)
    (main / "shipwright_events.jsonl").write_text(BASE_LOG, encoding="utf-8", newline="\n")
    (main / ".gitignore").write_text("*.lock\n.worktrees/\n", encoding="utf-8")
    if layout:
        (main / CONFIG).write_text(json.dumps({"events_layout": layout}) + "\n", encoding="utf-8")
    _commit(main, "base")
    _git(main, "push", "-q", "origin", "main")
    return main


def _worktree(main: Path, name: str, base: str = "origin/main") -> Path:
    wt = main.parent / name
    _git(main, "worktree", "add", "-q", "-b", f"iterate/{name}", str(wt), base)
    _identity(wt)
    return wt


def _clean(cwd: Path, a: str, b: str) -> bool:
    r = _git(cwd, f"--attr-source={EMPTY_TREE}", "merge-tree", "--write-tree", "--name-only", a, b, check=False)
    assert r.returncode in (0, 1), r.stderr
    return r.returncode == 0


def _squash(main: Path, branch: str) -> None:
    _git(main, "fetch", "-q", "origin")
    _git(main, "reset", "-q", "--hard", "origin/main")
    _git(main, "merge", "--squash", branch)
    _git(main, "commit", "-q", "-m", f"squash {branch}")
    _git(main, "push", "-q", "origin", "main")


def _read(root: Path):
    from lib.events_read import read_events_assembled
    return read_events_assembled(root)


def _runs(root: Path, kind: str = "work_completed") -> set[str]:
    return {e.get("adr_id") for e in _read(root).records if e.get("type") == kind}


def test_campaign_wave_squash_sequence_and_retried_unit(tmp_path):
    main = _main(tmp_path, "drops")
    wts = [_worktree(main, f"w{n}") for n in (1, 2, 3, 4)]
    for n, wt in enumerate(wts, 1):                                   # a wave: one session id, one run id per unit
        _record(wt, f"run-{n}")
        _record(wt, f"run-{n}", "work_completed")
        _commit(wt, f"unit {n}")
    retry = _worktree(main, "w1-retry")                               # the SAME run id again, another worktree
    _record(retry, "run-1", "work_completed")
    _commit(retry, "retry of unit 1")
    branches = [f"iterate/w{n}" for n in (1, 2, 3, 4)] + ["iterate/w1-retry"]
    assert all(_clean(main, a, b) for i, a in enumerate(branches) for b in branches[i + 1:])
    names = {p.name.split("--")[0] for w in wts for p in (w / ".shipwright/events/drops").glob("*.jsonl")}
    assert names == {"run-1", "run-2", "run-3", "run-4"}
    assert len(list((retry / ".shipwright/events/drops").glob("run-1--*"))) == 1
    _squash(main, "iterate/w1")
    _squash(main, "iterate/w2")
    third = _run(TOOLS / "ensure_current.py", wts[2], "--run-id", "run-3", "--default-branch", "main", "--no-regenerate", run_id="run-3")
    assert json.loads(third.stdout)["status"] == "ok"
    assert _runs(wts[2]) >= {"run-1", "run-2", "run-3"} and "run-4" not in _runs(wts[2])
    assert _git(wts[2], "status", "--porcelain").stdout.strip() == ""
    # continue-after-squash-merge: the squashed branch writes again; its closed file is not edited
    _record(wts[0], "run-1")
    assert len(list((wts[0] / ".shipwright/events/drops").glob("run-1--*"))) == 2
    assert _run(CHECKS / "check_events_integrity.py", wts[2], "--base-ref", "origin/main", "--head-ref", "HEAD").returncode == 0
    assert _run(CHECKS / "check_events_layout_ci.py", wts[2], "--base-ref", "origin/main", "--head-ref", "HEAD").returncode == 0


def test_old_writer_branch_and_a_pr_in_flight_at_the_flip(tmp_path):
    main = _main(tmp_path, None)                                      # pre-flip repo: no layout key = legacy
    old = _worktree(main, "old")
    _record(old, "run-old")                                           # legacy append, as every pre-change plugin does
    assert (old / "shipwright_events.jsonl").read_text(encoding="utf-8").count("event of run-old") == 1
    _commit(old, "old-style run")
    (main / CONFIG).write_text('{"events_layout": "drops"}\n', encoding="utf-8")     # THE FLIP lands on main
    _commit(main, "flip")
    _git(main, "push", "-q", "origin", "main")
    _git(old, "fetch", "-q", "origin")
    assert _clean(main, "iterate/old", "origin/main")                 # legacy append vs the flip commit: no conflict
    # judged at the merge-base: the PR that started before the flip is not failed
    assert _run(CHECKS / "check_events_layout_ci.py", old, "--base-ref", "origin/main", "--head-ref", "HEAD").returncode == 0
    # a branch started AFTER the flip that appends the legacy log is failed
    fresh = _worktree(main, "fresh")
    with open(fresh / "shipwright_events.jsonl", "a", encoding="utf-8", newline="\n") as fp:
        fp.write('{"ts":"2026-11-07T09:00:00Z","type":"task_created","id":"0000000a","description":"legacy after flip"}\n')
    _commit(fresh, "old plugin after the flip")
    assert _run(CHECKS / "check_events_layout_ci.py", fresh, "--base-ref", "origin/main", "--head-ref", "HEAD", ok=False).returncode == 1
    # mid-run flip: the old branch takes main in and its NEXT write goes to a drop; both histories stay readable
    _git(old, "merge", "-q", "--no-edit", "origin/main")
    _record(old, "run-old")
    assert list((old / ".shipwright/events/drops").glob("run-old--*.jsonl"))
    texts = [e.get("description") for e in _read(old).records]
    assert texts.count("event of run-old") == 2
    # S7 follow-up closed here: taking main in must not blame the pre-flip appends (the layout at each commit's parent decides)
    assert _run(CHECKS / "check_events_layout_ci.py", old, "--base-ref", "origin/main", "--head-ref", "HEAD").returncode == 0
    _commit(old, "after the flip")
    with open(old / "shipwright_events.jsonl", "a", encoding="utf-8", newline="\n") as fp:     # but a NEW legacy append is
        fp.write('{"ts":"2026-11-07T09:30:00Z","type":"task_created","id":"0000000b","description":"late legacy"}\n')
    _commit(old, "legacy append on top of the flip")
    assert _run(CHECKS / "check_events_layout_ci.py", old, "--base-ref", "origin/main", "--head-ref", "HEAD", ok=False).returncode == 1


def test_mid_run_rollback_by_emergency_fold_then_full_fold(tmp_path):
    main = _main(tmp_path, "drops")
    for n in (1, 2):
        wt = _worktree(main, f"m{n}")
        _record(wt, f"run-m{n}", "work_completed")
        _commit(wt, f"m{n}")
        _squash(main, f"iterate/m{n}")
    open_pr = _worktree(main, "open")
    _record(open_pr, "run-open")
    _commit(open_pr, "open pr")
    before = _git(main, "rev-parse", "HEAD").stdout.strip()
    assert json.loads(_run(TOOLS / "fold_events.py", main, "emergency", "--stage").stdout)["status"].startswith("folded")
    _commit(main, "chore(events): emergency fold")
    _git(main, "push", "-q", "origin", "main")
    assert json.loads((main / CONFIG).read_text(encoding="utf-8"))["events_layout"] == "legacy"
    assert _run(CHECKS / "check_events_integrity.py", main, "--base-ref", before, "--head-ref", "HEAD").returncode == 0
    _git(open_pr, "fetch", "-q", "origin")
    assert _clean(main, "iterate/open", "origin/main")                # the open PR still merges cleanly with the fold
    assert _run(CHECKS / "check_events_layout_ci.py", main, "--base-ref", before, "--head-ref", "HEAD").returncode == 0   # rollback shape
    _git(open_pr, "merge", "-q", "--no-edit", "origin/main")
    _record(open_pr, "run-open")                                      # mid-run rollback: the next write is legacy
    assert (open_pr / "shipwright_events.jsonl").read_text(encoding="utf-8").count("event of run-open") == 1
    assert _runs(open_pr) == {"run-m1", "run-m2"}
    assert len([e for e in _read(open_pr).records if e.get("description") == "event of run-open"]) == 2
    _run(TOOLS / "fold_events.py", open_pr, "full", "--stage")
    _commit(open_pr, "full fold")
    plain = [json.loads(ln) for ln in (open_pr / "shipwright_events.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert {e.get("adr_id") for e in plain if e.get("type") == "work_completed"} == {"run-m1", "run-m2"}
    assert len(plain) == len({json.dumps(e, sort_keys=True) for e in plain}) == len(_read(open_pr).records)


def test_a_corrupt_drop_on_main_is_repaired_by_quarantine_and_blocks_only_its_own_run(tmp_path):
    main = _main(tmp_path, "drops")
    (main / ".shipwright/events/drops").mkdir(parents=True, exist_ok=True)
    (main / ".shipwright/events/drops" / "run-bad--aaaaaaaa--00000001.jsonl").write_bytes(b"\x00\x00 not json at all \xff\n")
    _commit(main, "a torn drop reached main")
    _git(main, "push", "-q", "origin", "main")
    from lib.events_read import EventLogNotReadable, require_readable_for_absence
    read = _read(main)
    with pytest.raises(EventLogNotReadable):
        require_readable_for_absence(read, "run-bad")
    require_readable_for_absence(read, "run-other")                   # another run's absence gate is not blocked
    before = _git(main, "rev-parse", "HEAD").stdout.strip()
    done = json.loads(_run(TOOLS / "fold_events.py", main, "quarantine", "--base-ref", "HEAD", "--stage").stdout)
    assert done["status"] == "quarantined"
    _commit(main, "chore(events): quarantine")
    assert _run(CHECKS / "check_events_integrity.py", main, "--base-ref", before, "--head-ref", "HEAD").returncode == 0
    require_readable_for_absence(_read(main), "run-bad")


def test_mixed_versions_fail_closed_through_the_real_writer_cli(tmp_path):
    main = _main(tmp_path, "v99")                                     # a layout this plugin does not know
    wt = _worktree(main, "mixed")
    refused = _record(wt, "run-x", ok=False)
    assert refused.returncode != 0
    assert not (wt / ".shipwright/events/drops").exists()
    assert (wt / "shipwright_events.jsonl").read_text(encoding="utf-8") == BASE_LOG
    # live drops with the key removed: legacy writes are refused rather than silently splitting the log
    (wt / CONFIG).unlink()
    (wt / ".shipwright/events/drops").mkdir(parents=True)
    (wt / ".shipwright/events/drops" / "run-y--aaaaaaaa--00000001.jsonl").write_text(
        '{"v":1,"id":"evt-y","ts":"2026-11-01T00:00:00+00:00","type":"task_created","run":"run-y"}\n', encoding="utf-8", newline="\n")
    assert _record(wt, "run-z", ok=False).returncode != 0
    assert (wt / "shipwright_events.jsonl").read_text(encoding="utf-8") == BASE_LOG


def test_fault_injection_corrupt_empty_duplicate_and_future_timestamps(tmp_path):
    main = _main(tmp_path, "drops")
    folder = main / ".shipwright/events/drops"
    folder.mkdir(parents=True, exist_ok=True)
    good = '{"v":1,"id":"evt-dup","ts":"2026-11-01T00:00:00+00:00","type":"task_created","run":"run-a"}\n'
    (folder / "run-a--aaaaaaaa--00000001.jsonl").write_text(good, encoding="utf-8", newline="\n")
    (folder / "run-a--bbbbbbbb--00000002.jsonl").write_text(good, encoding="utf-8", newline="\n")      # duplicate id, same content
    (folder / "run-empty--aaaaaaaa--00000003.jsonl").write_bytes(b"")
    (folder / "run-torn--aaaaaaaa--00000004.jsonl").write_text(
        '{"v":1,"id":"evt-t1","ts":"2026-11-02T00:00:00+00:00","type":"task_created","run":"run-torn"}\n{"v":1,"id":"evt-t2","ts":', encoding="utf-8", newline="\n")
    (folder / "run-future--aaaaaaaa--00000005.jsonl").write_text(
        '{"v":1,"id":"evt-f","ts":"2099-01-01T00:00:00+00:00","type":"task_created","run":"run-future"}\n', encoding="utf-8", newline="\n")
    from lib.events_log import latest_event_dt
    from lib.events_read import EventLogNotReadable, require_readable_for_absence
    read = _read(main)
    ids = [r.get("id") for r in read.records]
    assert ids.count("evt-dup") == 1 and "evt-t1" in ids and ids[-1] == "evt-f"      # dedup, recovery, future ts sorts last
    status = {Path(f.path).name.split("--")[0]: f.status for f in read.files if f.kind == "drop"}
    assert status["run-empty"] == "empty" and status["run-torn"] == "corrupt" and status["run-a"] == "ok"
    assert latest_event_dt(main).year == 2099
    for key in ("run-empty", "run-torn"):
        with pytest.raises(EventLogNotReadable):
            require_readable_for_absence(read, key)
    require_readable_for_absence(read, "run-a")
    assert _record(main, "run-a").returncode == 0                     # a healthy run keeps writing around the damage


def test_two_run_ids_in_one_shared_worktree_f6_stages_only_its_own_key(tmp_path, monkeypatch):
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)
    from lib.events_stage import commit_drops, own_drops

    main = _main(tmp_path, "drops")
    wt = _worktree(main, "shared")
    for run in ("run-a", "run-b"):
        _record(wt, run)
    _record(wt, "run-b", "work_completed")      # run-b's gate event: shipping it is run-b's F6 job, the absorb must leave it
    mine = own_drops(wt, "run-a")
    assert [Path(p).name.split("--")[0] for p in mine] == ["run-a"]
    assert commit_drops(wt, mine, "F6 run-a")[0]
    _record(wt, "run-a")                                              # a post-F6 write rotates into a NEW file
    assert len(list((wt / ".shipwright/events/drops").glob("run-a--*"))) == 2
    left = _git(wt, "status", "--porcelain").stdout.splitlines()
    assert sum("run-b--" in ln for ln in left) == 1 and sum("run-a--" in ln for ln in left) == 1
    assert not [ln for ln in _git(wt, "ls-files", ".shipwright/events/drops").stdout.split() if "run-b--" in ln]
    # the hop: a sibling lands on main, then the real ensure_current runs for run-a with run-b's leftover drop in the tree
    sib = main.parent / "sib"
    _git(main.parent, "clone", "-q", str(main.parent / "o.git"), str(sib))
    _identity(sib)
    (sib / "sibling.txt").write_text("merged", encoding="utf-8")
    _commit(sib, "sibling")
    _git(sib, "push", "-q", "origin", "main")
    _record(wt, "run-a", "work_completed")
    _commit_own = commit_drops(wt, [p for p in own_drops(wt, "run-a")], "F6 again")
    assert _commit_own[0]
    hop = _run(TOOLS / "ensure_current.py", wt, "--run-id", "run-a", "--default-branch", "main", "--no-regenerate", run_id="run-a")
    assert json.loads(hop.stdout)["status"] == "ok", hop.stdout[-600:]
    assert (wt / "sibling.txt").exists()
    committed = _git(wt, "ls-tree", "-r", "--name-only", "HEAD", ".shipwright/events/drops").stdout.split()
    assert not [n for n in committed if "run-b--" in n], "the absorb committed a sibling run's gate event"


def test_stacked_base_branch_inherits_the_parent_drop_and_stays_clean(tmp_path):
    main = _main(tmp_path, "drops")
    first = _worktree(main, "stack1")
    _record(first, "run-s1", "work_completed")
    _commit(first, "stack 1")
    second = _worktree(main, "stack2", base="iterate/stack1")          # branched off the previous unit, not off main
    _record(second, "run-s2", "work_completed")
    _commit(second, "stack 2")
    other = _worktree(main, "other")
    _record(other, "run-o", "work_completed")
    _commit(other, "other")
    assert _clean(main, "iterate/stack2", "iterate/other")
    assert _runs(second) == {"run-s1", "run-s2"}
    assert _run(CHECKS / "check_events_integrity.py", second, "--base-ref", "iterate/stack1", "--head-ref", "HEAD").returncode == 0
    _squash(main, "iterate/stack1")                                    # the base is squash-merged; the stacked branch still reads clean
    _git(second, "fetch", "-q", "origin")
    assert _clean(main, "iterate/stack2", "origin/main")
