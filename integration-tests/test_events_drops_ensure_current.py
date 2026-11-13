"""A REAL ``ensure_current`` on a behind-main branch that carries its own drop (issue 978, S3).

S0's harness proves two PRs never conflict under the drops layout. This is the other half
(DESIGN 10.2): after a sibling PR was squash-merged, the branch is behind ``origin/main`` and
``ensure_current`` must integrate it WITHOUT either of the two spots the spike hit:

* ``resolve_churn_conflicts._reconcile_events`` validated the legacy file only and reported
  "work_completed absent - the merge dropped it" (exit 4) on every refresh;
* ``change_type_paths`` did not list the folder, so ``record_event`` refused ``work_completed``.

Also here: campaign-status regeneration from a drop, and the reconcile gate's negative case
(the run's own event really is gone -> still refused).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_events_drops_harness import BASE_LOG, _git, _git_version

REPO = Path(__file__).resolve().parents[1]
RECORD_EVENT = REPO / "shared" / "scripts" / "tools" / "record_event.py"
ENSURE_CURRENT = REPO / "shared" / "scripts" / "tools" / "ensure_current.py"
DROPS = {"SHIPWRIGHT_EVENTS_LAYOUT": "drops", "SHIPWRIGHT_EVENTS_LAYOUT_TEST": "1"}

pytestmark = [pytest.mark.covers("FR-01.11"), pytest.mark.skipif(
    _git_version() < (2, 40), reason="needs git >= 2.40")]

CAMPAIGN_MD = """---
campaign: demo
status: active
---

# Campaign: demo

## Sub-Iterates

| ID | Slug | Title | Status |
|---|---|---|---|
| S1 | alpha | First | pending |
"""


def _env(run_id: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("SHIPWRIGHT_")}
    env.update({"SHIPWRIGHT_RUN_ID": run_id, "PYTHONIOENCODING": "utf-8", **DROPS})
    return env


def _record_work_completed(wt: Path, run_id: str, *extra: str) -> None:
    r = subprocess.run(
        [sys.executable, str(RECORD_EVENT), "--project-root", str(wt), "--type", "work_completed",
         "--source", "iterate", "--intent", "change", "--description", f"work of {run_id}",
         "--adr-id", run_id, "--change-type", "tooling", "--none-reason", "tooling only", "--spec-impact", "none",
         "--spec-impact-justification", "tooling only", "--spec-impact-reason-code", "tooling-only", *extra],
        cwd=wt, env=_env(run_id), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, f"record_event refused: {r.stdout[-500:]} {r.stderr[-500:]}"


def _identity(path: Path) -> None:
    for key, val in (("user.email", "t@t"), ("user.name", "t")):
        _git(path, "config", key, val)


def _world(tmp_path: Path) -> tuple[Path, Path, Path]:
    """(branch worktree with its own committed drop, sibling clone, bare origin); origin is then ahead."""
    origin, main, sibling, branch = (tmp_path / "o.git", tmp_path / "m", tmp_path / "sib", tmp_path / "branch")
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(main))
    _identity(main)
    (main / "shipwright_events.jsonl").write_text(BASE_LOG, encoding="utf-8", newline="\n")
    (main / ".gitignore").write_text("*.lock\n.worktrees/\n")
    campaign = main / ".shipwright" / "planning" / "iterate" / "campaigns" / "demo"
    campaign.mkdir(parents=True)
    (campaign / "campaign.md").write_text(CAMPAIGN_MD, encoding="utf-8")
    _git(main, "add", "-A")
    _git(main, "commit", "-q", "-m", "base")
    _git(main, "push", "-q", "origin", "main")
    _git(main, "worktree", "add", "-q", "-b", "iterate/ra", str(branch), "origin/main")
    _identity(branch)
    _record_work_completed(branch, "run-a")
    _git(branch, "add", ".shipwright/events/drops")
    _git(branch, "commit", "-q", "-m", "run a")
    # a sibling PR lands on main (squash-like: one commit adding its own drop and a file)
    _git(tmp_path, "clone", "-q", str(origin), str(sibling))
    _identity(sibling)
    _record_work_completed(sibling, "run-b")
    (sibling / "sibling.txt").write_text("merged\n")
    _git(sibling, "add", "-A")
    _git(sibling, "commit", "-q", "-m", "run b (squashed)")
    _git(sibling, "push", "-q", "origin", "main")
    return branch, sibling, origin


def _ensure_current(branch: Path, run_id: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ENSURE_CURRENT), "--project-root", str(branch), "--run-id", run_id,
         "--default-branch", "main", "--no-regenerate"],
        cwd=branch, env=_env(run_id), capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300)


def _runs(branch: Path) -> set[str]:
    sys.path.insert(0, str(REPO / "shared" / "scripts"))
    from lib.events_read import read_events_assembled
    return {e.get("adr_id") for e in read_events_assembled(branch).records if e.get("type") == "work_completed"}


def test_ensure_current_integrates_main_and_keeps_both_runs_drops(tmp_path):
    branch, _sibling, _origin = _world(tmp_path)
    _git(branch, "fetch", "-q", "origin")
    assert _git(branch, "rev-list", "--count", "HEAD..origin/main").stdout.strip() == "1"  # behind main
    result = _ensure_current(branch, "run-a")
    assert result.returncode == 0, f"ensure_current failed: {result.stdout[-800:]} {result.stderr[-800:]}"
    assert json.loads(result.stdout)["status"] == "ok"
    assert (branch / "sibling.txt").exists(), "main was not integrated"
    assert _runs(branch) == {"run-a", "run-b"}
    drops = sorted(p.name.split("--")[0] for p in (branch / ".shipwright/events/drops").glob("*.jsonl"))
    assert drops == ["run-a", "run-b"]
    assert _git(branch, "status", "--porcelain").stdout.strip() == ""


def test_ensure_current_still_refuses_when_the_runs_own_event_is_gone(tmp_path):
    branch, _sibling, _origin = _world(tmp_path)
    result = _ensure_current(branch, "run-never-recorded")
    assert result.returncode == 4, f"{result.stdout[-600:]} {result.stderr[-600:]}"
    assert json.loads(result.stdout)["status"] == "events_invalid"


def test_campaign_status_is_regenerated_from_a_drop(tmp_path):
    sys.path.insert(0, str(REPO / "shared" / "scripts"))
    from lib.campaign_status_io import regenerate_campaign_statuses

    branch, _sibling, _origin = _world(tmp_path)
    _record_work_completed(branch, "run-s1", "--commit", "abc1234")
    log = branch / ".shipwright/events/drops"
    stamped = []
    for path in sorted(log.glob("run-s1--*.jsonl")):
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for event in events:
            event.update({"campaign": "demo", "sub_iterate_id": "S1"})
        path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8", newline="\n")
        stamped.append(path.name)
    assert stamped
    rel = ".shipwright/planning/iterate/campaigns/demo/status.json"
    out = regenerate_campaign_statuses(branch, branch / "shipwright_events.jsonl", [rel])
    assert out == {rel: "regenerated"}
    status = json.loads((branch / rel).read_text(encoding="utf-8"))
    assert {s["id"]: s["status"] for s in status["sub_iterates"]} == {"S1": "complete"}


def test_another_runs_damaged_drop_on_main_does_not_block_the_refresh(tmp_path):
    branch, sibling, _origin = _world(tmp_path)
    (drop,) = sorted((sibling / ".shipwright/events/drops").glob("run-b--*.jsonl"))
    drop.write_bytes(drop.read_bytes() + b"{not json at all\n")
    _git(sibling, "add", "-A")
    _git(sibling, "commit", "-q", "-m", "damage run-b's drop")
    _git(sibling, "push", "-q", "origin", "main")
    result = _ensure_current(branch, "run-a")
    assert result.returncode == 0, f"{result.stdout[-800:]} {result.stderr[-800:]}"
    assert "run-a" in _runs(branch)


def test_ensure_current_is_idempotent(tmp_path):
    branch, _sibling, _origin = _world(tmp_path)
    assert _ensure_current(branch, "run-a").returncode == 0
    head = _git(branch, "rev-parse", "HEAD").stdout.strip()
    again = _ensure_current(branch, "run-a")
    assert again.returncode == 0
    assert _git(branch, "rev-parse", "HEAD").stdout.strip() == head
    assert _runs(branch) == {"run-a", "run-b"}


def _tree(tmp_path: Path, *, own: bytes | None, other: bytes | None) -> Path:
    drops = tmp_path / ".shipwright/events/drops"
    drops.mkdir(parents=True)
    if own is not None:
        (drops / "run-a--aaaaaaaa--00000001.jsonl").write_bytes(own)
    if other is not None:
        (drops / "run-b--bbbbbbbb--00000001.jsonl").write_bytes(other)
    return tmp_path


def _validate(root: Path, run_id: str) -> list[str]:
    sys.path.insert(0, str(REPO / "shared" / "scripts"))
    from lib.churn_events import validate_event_folders
    return validate_event_folders(root, run_id)


GOOD = b'{"type":"work_completed","adr_id":"run-a","id":"1","ts":"2026-01-01T00:00:00Z"}\n'


def test_validate_event_folders_scopes_blocking_to_the_runs_own_drop(tmp_path):
    # present event: nothing is reported, whatever else is damaged
    (tmp_path / "t1").mkdir()
    assert _validate(_tree(tmp_path / "t1", own=GOOD, other=b"{broken\n"), "run-a") == []
    # own drop damaged and the event not recoverable: "cannot conclude", never "absent"
    (tmp_path / "t2").mkdir()
    errs = _validate(_tree(tmp_path / "t2", own=b"{broken\n", other=GOOD.replace(b"run-a", b"run-b")), "run-a")
    assert errs and "cannot be concluded" in errs[0]
    # ANOTHER run's drop damaged while this run's event is missing: plainly absent
    (tmp_path / "t3").mkdir()
    errs = _validate(_tree(tmp_path / "t3", own=None, other=b"{broken\n"), "run-a")
    assert errs and "is absent" in errs[0]
    # a drop whose name does not follow the writer's shape cannot be ruled out: blocks
    (tmp_path / "t4").mkdir()
    root = _tree(tmp_path / "t4", own=None, other=None)
    (root / ".shipwright/events/drops" / "oddname.jsonl").write_bytes(b"{broken\n")
    errs = _validate(root, "run-a")
    assert errs and "cannot be concluded" in errs[0]
