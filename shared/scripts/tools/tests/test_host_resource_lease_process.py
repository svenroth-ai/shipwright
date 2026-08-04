"""Real-process, sibling-worktree, fairness, heartbeat, and crash probes."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.lib.host_resource_lease import host_resource_lease, repository_identity

_SHARED = str(Path(__file__).resolve().parent.parent.parent.parent)
_PROBE = r"""
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from scripts.lib.host_resource_lease import host_resource_lease
root, lease_root = Path(sys.argv[2]), Path(sys.argv[3])
weight, capacity, hold = int(sys.argv[4]), int(sys.argv[5]), float(sys.argv[6])
run_id, marker, heartbeat, resource, release = (sys.argv[7], sys.argv[8],
                                                float(sys.argv[9]), sys.argv[10],
                                                sys.argv[11])
with host_resource_lease(root, resource=resource, capacity=capacity, weight=weight,
                         owner=f'pid-{os.getpid()}', run_id=run_id,
                         heartbeat_seconds=heartbeat, poll_seconds=.02,
                         lease_root=lease_root) as grant:
    payload = {'event':'acquired','run_id':run_id,'time':time.monotonic(),
               'weight':grant.weight}
    if marker != '-': Path(marker).write_text(json.dumps(payload), encoding='utf-8')
    print(json.dumps(payload), flush=True)
    if release != '-':
        release_path = Path(release)
        while not release_path.exists():
            time.sleep(.02)
    else:
        time.sleep(hold)
"""


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                          text=True, errors="replace", check=True)
    return proc.stdout.strip()


def _worktrees(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-m", "seed")
    sibling = tmp_path / "sibling"
    _git(repo, "worktree", "add", "-b", "sibling", str(sibling), "HEAD")
    return repo, sibling


def _start(root: Path, lease_root: Path, *, weight: int, capacity: int,
           hold: float, run_id: str, marker: Path | None = None,
           heartbeat: float = 30.0, resource: str = "cpu",
           release: Path | None = None) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", _PROBE, _SHARED, str(root), str(lease_root),
         str(weight), str(capacity), str(hold), run_id,
         str(marker) if marker else "-", str(heartbeat), resource,
         str(release) if release else "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")


def _wait_marker(path: Path, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        time.sleep(.02)
    raise AssertionError(f"timed out waiting for {path}")


def _wait_queue_entry(lease_root: Path, repo: Path, run_id: str,
                      timeout: float = 8.0, resource: str = "cpu") -> dict:
    state_path = lease_root / repository_identity(repo) / f"{resource}.state.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            entry = next((item for item in state["entries"]
                          if item["run_id"] == run_id), None)
            if entry is not None:
                return entry
        except (OSError, KeyError, json.JSONDecodeError):
            pass
        time.sleep(.02)
    raise AssertionError(f"timed out waiting for queued run {run_id}")


def _stop(*processes: subprocess.Popen) -> None:
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    for proc in processes:
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=5)


def test_sibling_worktrees_share_identity_but_separate_clone_does_not(tmp_path):
    repo, sibling = _worktrees(tmp_path)
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "--quiet", str(repo), str(clone)], check=True)
    assert repository_identity(repo) == repository_identity(sibling)
    assert repository_identity(repo) != repository_identity(clone)


def test_repository_identity_ignores_inherited_git_context(tmp_path, monkeypatch):
    repo, sibling = _worktrees(tmp_path)
    expected = repository_identity(repo)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "foreign.git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "foreign-tree"))
    monkeypatch.setenv("GIT_COMMON_DIR", str(tmp_path / "foreign-common"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "foreign-index"))
    assert repository_identity(sibling) == expected


def test_compatible_weights_overlap_across_sibling_worktrees(tmp_path):
    repo, sibling = _worktrees(tmp_path)
    lease_root, m1, m2 = tmp_path / "leases", tmp_path / "one", tmp_path / "two"
    release = tmp_path / "release-one"
    p1 = _start(repo, lease_root, weight=2, capacity=4, hold=.8,
                run_id="run-one", marker=m1, release=release)
    p2 = None
    try:
        _wait_marker(m1)
        p2 = _start(sibling, lease_root, weight=2, capacity=4, hold=.1,
                    run_id="run-two", marker=m2)
        _wait_marker(m2)
        assert p1.poll() is None, "compatible lease acquired only after holder exited"
        release.touch()
    finally:
        _stop(*[p for p in (p1, p2) if p])


def test_uv_warmups_serialize_then_compatible_cpu_leases_overlap(tmp_path):
    repo, sibling = _worktrees(tmp_path)
    lease_root = tmp_path / "leases"
    marks = [tmp_path / name for name in ("uv-one", "uv-two", "cpu-one", "cpu-two")]
    uv_release, cpu_release = tmp_path / "uv-release", tmp_path / "cpu-release"
    uv_one = _start(repo, lease_root, weight=1, capacity=1, hold=.5,
                    run_id="uv-one", marker=marks[0], resource="uv-warmup",
                    release=uv_release)
    uv_two = cpu_one = cpu_two = None
    try:
        _wait_marker(marks[0])
        uv_two = _start(sibling, lease_root, weight=1, capacity=1, hold=.05,
                        run_id="uv-two", marker=marks[1], resource="uv-warmup")
        waiting = _wait_queue_entry(lease_root, repo, "uv-two", resource="uv-warmup")
        assert waiting["status"] == "waiting"
        uv_release.touch()
        _wait_marker(marks[1])
        uv_one.wait(timeout=5)
        uv_two.wait(timeout=5)

        cpu_one = _start(repo, lease_root, weight=1, capacity=2, hold=.4,
                         run_id="cpu-one", marker=marks[2], release=cpu_release)
        _wait_marker(marks[2])
        cpu_two = _start(sibling, lease_root, weight=1, capacity=2, hold=.05,
                         run_id="cpu-two", marker=marks[3])
        _wait_marker(marks[3])
        assert cpu_one.poll() is None
        cpu_release.touch()
    finally:
        _stop(*[p for p in (uv_one, uv_two, cpu_one, cpu_two) if p])


def test_fifo_head_cannot_be_bypassed_by_a_smaller_request(tmp_path):
    repo, sibling = _worktrees(tmp_path)
    lease_root = tmp_path / "leases"
    marks = [tmp_path / name for name in ("holder", "head", "small")]
    holder_release, head_release = tmp_path / "holder-release", tmp_path / "head-release"
    holder = _start(repo, lease_root, weight=3, capacity=4, hold=.8,
                    run_id="holder", marker=marks[0], release=holder_release)
    head = small = None
    try:
        _wait_marker(marks[0])
        head = _start(sibling, lease_root, weight=2, capacity=4, hold=.15,
                      run_id="head", marker=marks[1], heartbeat=.1,
                      release=head_release)
        head_entry = _wait_queue_entry(lease_root, repo, "head")
        assert head_entry["status"] == "waiting"
        small = _start(repo, lease_root, weight=1, capacity=4, hold=.05,
                       run_id="small", marker=marks[2], heartbeat=.1)
        small_entry = _wait_queue_entry(lease_root, repo, "small")
        assert head_entry["seq"] < small_entry["seq"]
        assert small_entry["status"] == "waiting"
        assert not marks[2].exists(), "later smaller request bypassed the FIFO head"
        holder_release.touch()
        _wait_marker(marks[1])
        head_release.touch()
        _wait_marker(marks[2])
    finally:
        _stop(*[p for p in (holder, head, small) if p])


def test_crashed_holder_releases_capacity_without_lock_file_deletion(tmp_path):
    repo, sibling = _worktrees(tmp_path)
    lease_root, held, next_mark = tmp_path / "leases", tmp_path / "held", tmp_path / "next"
    holder = _start(repo, lease_root, weight=2, capacity=2, hold=30,
                    run_id="crash-owner", marker=held)
    waiter = None
    try:
        _wait_marker(held)
        ticket_dir = lease_root / repository_identity(repo) / "tickets"
        holder_tickets = list(ticket_dir.glob("*.owner.lock"))
        assert len(holder_tickets) == 1
        crashed_ticket = holder_tickets[0]
        waiter = _start(sibling, lease_root, weight=2, capacity=2, hold=.05,
                        run_id="waiter", marker=next_mark, heartbeat=.1)
        time.sleep(.2)
        assert not next_mark.exists(), "waiter acquired before the holder was killed"
        holder.kill()
        holder.wait(timeout=5)
        _wait_marker(next_mark)
        assert crashed_ticket.exists(), (
            "crash recovery must not require deleting the crashed holder ticket")
    finally:
        _stop(*[p for p in (holder, waiter) if p])


def test_waiting_lease_ignores_a_closed_diagnostic_stream(tmp_path):
    class _Closed:
        def write(self, _value):
            raise BrokenPipeError("channel closed")

        def flush(self):
            raise BrokenPipeError("channel closed")

    repo, sibling = _worktrees(tmp_path)
    lease_root, held = tmp_path / "leases", tmp_path / "held"
    holder = _start(repo, lease_root, weight=1, capacity=1, hold=.35,
                    run_id="holder", marker=held)
    try:
        _wait_marker(held)
        with host_resource_lease(
                sibling, resource="cpu", capacity=1, weight=1,
                owner="closed-stream", run_id="waiter", heartbeat_seconds=.05,
                poll_seconds=.02, stream=_Closed(), lease_root=lease_root):
            pass
    finally:
        _stop(holder)


def test_dead_owner_is_reaped_before_capacity_change_is_adopted(tmp_path):
    repo, _sibling = _worktrees(tmp_path)
    lease_root = tmp_path / "leases"
    namespace = lease_root / repository_identity(repo)
    tickets = namespace / "tickets"
    tickets.mkdir(parents=True)
    for directory in (lease_root, namespace, tickets):
        directory.chmod(0o700)
    ticket = "a" * 32
    ticket_path = tickets / f"{ticket}.owner.lock"
    ticket_path.write_bytes(b"0")
    ticket_path.chmod(0o600)
    state = {
        "version": 1, "capacity": 8, "next_seq": 2,
        "entries": [{"ticket": ticket, "seq": 1, "weight": 8,
                     "owner": "dead", "run_id": "old", "pid": 1,
                     "status": "granted"}],
    }
    state_path = namespace / "cpu.state.json"
    state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
    state_path.chmod(0o600)
    marker = tmp_path / "changed"
    proc = _start(repo, lease_root, weight=4, capacity=4, hold=.01,
                  run_id="new-capacity", marker=marker)
    try:
        _wait_marker(marker)
        assert proc.wait(timeout=8) == 0
    finally:
        _stop(proc)


def test_wait_output_names_queue_owner_run_id_and_heartbeats(tmp_path):
    repo, sibling = _worktrees(tmp_path)
    lease_root, held = tmp_path / "leases", tmp_path / "held"
    holder = _start(repo, lease_root, weight=1, capacity=1, hold=.45,
                    run_id="blocking-run", marker=held)
    waiter = None
    try:
        _wait_marker(held)
        waiter = _start(sibling, lease_root, weight=1, capacity=1, hold=.01,
                        run_id="queued-run", heartbeat=.1)
        _out, err = waiter.communicate(timeout=8)
        assert waiter.returncode == 0
        assert "waiting:" in err and "heartbeat:" in err
        assert "queue_run_id=blocking-run" in err and "queue_owner=pid-" in err
    finally:
        _stop(*[p for p in (holder, waiter) if p])
