"""Real 12-process SessionStart fan-out through immediate cache consumers."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Thread

import pytest

_REPO = Path(__file__).resolve().parents[1]
_CANONICAL = _REPO / "shared" / "templates" / "hooks" / "ensure_shared_cache.py"
_LOCK_HELPER = _CANONICAL.with_name("cache_repair_lock.py")
_READY_GUARD = _CANONICAL.with_name("run_if_cache_ready.py")
_PLUGINS = (
    "project", "design", "plan", "build", "test", "security", "deploy",
    "changelog", "compliance", "iterate", "adopt", "run",
)

_HEALER_WRAPPER = r"""
import os, runpy, shutil, sys, time
script = sys.argv[1]
target_args = sys.argv[2:]
sys.argv = [script, *target_args]
sys.path.insert(0, os.path.dirname(script))
scan_log = os.environ.get("SHIPWRIGHT_TEST_SCAN_LOG")
scan_logged = [False]
def trace(frame, event, arg):
    if event == "call" and frame.f_code.co_name == "_delivered" and not scan_logged[0]:
        with open(scan_log, "a", encoding="ascii") as handle:
            handle.write(f"{os.getpid()}\n")
        scan_logged[0] = True
    return trace
if scan_log:
    sys.settrace(trace)
delay = float(os.environ.get("SHIPWRIGHT_TEST_COPY_DELAY", "0"))
copy_log = os.environ.get("SHIPWRIGHT_TEST_COPY_LOG")
if delay or copy_log:
    real_copytree = shutil.copytree
    remaining = [delay]
    def slow_copytree(*args, **kwargs):
        if copy_log:
            with open(copy_log, "a", encoding="ascii") as handle:
                handle.write(f"{os.getpid()}\n")
        if remaining[0]:
            time.sleep(remaining.pop())
            remaining.append(0)
        return real_copytree(*args, **kwargs)
    shutil.copytree = slow_copytree
try:
    runpy.run_path(script, run_name="__main__")
except SystemExit as exc:
    if exc.code not in (None, 0):
        raise
"""

_CONSUMER = """\
import json, os
for name in ("SHIPWRIGHT_TEST_SHARED_FILE", "SHIPWRIGHT_TEST_MIRROR_FILE"):
    with open(os.environ[name], "r", encoding="utf-8") as handle:
        assert handle.read() == "ready\\n", os.environ[name]
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "consumer-ok"}}))
"""


def _write(path: Path, text: str = "ready\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _context(output: str) -> str:
    if not output.strip():
        return ""
    return json.loads(output)["hookSpecificOutput"]["additionalContext"]


def _event_digest(
    session_id: str, payload_fields: dict[str, object] | None = None,
) -> str:
    fields = payload_fields or {}
    source = fields.get("source") if isinstance(fields.get("source"), str) else ""
    transcript = fields.get("transcript_path")
    transcript = transcript if isinstance(transcript, str) else ""
    event_key = json.dumps(
        [session_id, source, transcript],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(event_key.encode("utf-8")).hexdigest()[:32]


def _layout(tmp_path: Path) -> tuple[list[Path], Path, Path, Path]:
    plugins_root = tmp_path / "plugins"
    cache = plugins_root / "cache" / "shipwright"
    clone_shared = plugins_root / "marketplaces" / "shipwright" / "shared"
    _write(clone_shared / "scripts" / "lib" / "project_root.py", "# sentinel\n")
    shared_late = clone_shared / "scripts" / "tools" / "verifiers" / "late.py"
    _write(shared_late, _CONSUMER)
    shared_data = clone_shared / "data" / "ready.txt"
    _write(shared_data)

    scripts: list[Path] = []
    for slug in _PLUGINS:
        name = f"shipwright-{slug}"
        version = cache / name / "1.0.0"
        script = version / "scripts" / "hooks" / "ensure_shared_cache.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_bytes(_CANONICAL.read_bytes())
        script.with_name("cache_repair_lock.py").write_bytes(_LOCK_HELPER.read_bytes())
        script.with_name("run_if_cache_ready.py").write_bytes(_READY_GUARD.read_bytes())
        _write(version / "payload" / f"{name}.txt")
        scripts.append(script)

    consumer_target = cache / "shared" / shared_late.relative_to(clone_shared)
    shared_target = cache / "shared" / shared_data.relative_to(clone_shared)
    mirror_target = cache / "plugins" / "shipwright-run" / "payload" / "shipwright-run.txt"
    return scripts, consumer_target, shared_target, mirror_target


def _fire(
    script: Path,
    consumer_target: Path | tuple[Path, ...],
    shared_target: Path,
    mirror_target: Path,
    session_id: object = "fanout-session",
    copy_delay: float = 0.0,
    payload_fields: dict[str, object] | None = None,
):
    env = os.environ.copy()
    env["SHIPWRIGHT_TEST_COPY_DELAY"] = str(copy_delay)
    env["SHIPWRIGHT_TEST_SHARED_FILE"] = str(shared_target)
    env["SHIPWRIGHT_TEST_MIRROR_FILE"] = str(mirror_target)
    payload_data = {"session_id": session_id}
    payload_data.update(payload_fields or {})
    payload = json.dumps(payload_data)
    targets = (consumer_target,) if isinstance(consumer_target, Path) \
        else consumer_target
    guard = subprocess.run(
        [sys.executable, "-c", _HEALER_WRAPPER,
         str(script.with_name("run_if_cache_ready.py")),
         *(str(target) for target in targets)],
        input=payload,
        text=True,
        capture_output=True,
        cwd=str(script.parents[3]),
        env=env,
        timeout=30,
    )
    return subprocess.CompletedProcess(
        guard.args, guard.returncode, guard.stdout, guard.stderr,
    )


def test_twelve_consolidated_hook_processes_heal_once_before_consumers(
    tmp_path: Path, monkeypatch,
):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    scan_log = tmp_path / "repair-scanners.log"
    transcript = tmp_path / "transcript.jsonl"
    _write(transcript, "first\n")
    monkeypatch.setenv("SHIPWRIGHT_TEST_SCAN_LOG", str(scan_log))

    def mutate_transcript_during_launch() -> None:
        time.sleep(0.05)
        transcript.write_text("first\nsecond\n", encoding="utf-8")

    mutator = Thread(target=mutate_transcript_during_launch)
    mutator.start()
    with ThreadPoolExecutor(max_workers=len(scripts)) as pool:
        results = list(pool.map(
            lambda script: _fire(
                script, consumer_target, shared_target, mirror_target,
                payload_fields={
                    "source": "startup", "transcript_path": str(transcript),
                },
            ),
            scripts,
        ))
    mutator.join()

    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    assert all(_context(r.stdout) == "consumer-ok" for r in results), [
        r.stdout for r in results
    ]
    healed = [r for r in results if "self-healed the plugin cache" in r.stderr]
    assert len(healed) == 1, [r.stderr for r in results]
    assert len(set(scan_log.read_text(encoding="ascii").splitlines())) == 1
    assert shared_target.read_text(encoding="utf-8") == "ready\n"
    assert mirror_target.read_text(encoding="utf-8") == "ready\n"


def test_healthy_cache_fanout_elects_one_scanner_and_copies_nothing(
    tmp_path: Path, monkeypatch,
):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    warmup = _fire(scripts[0], consumer_target, shared_target, mirror_target,
                   "warmup-session")
    assert warmup.returncode == 0, warmup.stderr
    scan_log = tmp_path / "healthy-scanners.log"
    copy_log = tmp_path / "healthy-copies.log"
    monkeypatch.setenv("SHIPWRIGHT_TEST_SCAN_LOG", str(scan_log))
    monkeypatch.setenv("SHIPWRIGHT_TEST_COPY_LOG", str(copy_log))

    with ThreadPoolExecutor(max_workers=len(scripts)) as pool:
        results = list(pool.map(
            lambda script: _fire(
                script, consumer_target, shared_target, mirror_target,
                "healthy-session",
            ),
            scripts,
        ))

    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    assert all(_context(r.stdout) == "consumer-ok" for r in results)
    assert not any("self-healed the plugin cache" in r.stderr for r in results)
    assert len(set(scan_log.read_text(encoding="ascii").splitlines())) == 1
    assert not copy_log.exists(), "healthy fan-out must call copytree zero times"
    claims = scripts[0].parents[4] / ".sessionstart-claims"
    assert len(list(claims.glob("*.claim"))) == 2
    assert len(list(claims.glob("*.done"))) == 2


def test_consolidated_wrapper_runs_all_targets_in_manifest_order(tmp_path: Path):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    second_target = consumer_target.with_name("second-consumer.py")
    _write(second_target, "import json\nprint(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': 'second-ok'}}))\n")

    result = _fire(
        scripts[0], (consumer_target, second_target), shared_target,
        mirror_target, "ordered-targets",
    )

    assert result.returncode == 0, result.stderr
    assert _context(result.stdout) == "consumer-ok\nsecond-ok"


def test_consolidated_wrapper_warns_invalid_outputs_and_continues(tmp_path: Path):
    scripts, _, shared_target, mirror_target = _layout(tmp_path)
    targets = tuple(tmp_path / f"target-{index}.py" for index in range(4))
    marker = tmp_path / "last-target-ran"
    _write(targets[0], "import json,sys\nprint(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': 'first'}}))\nsys.exit(7)\n")
    _write(targets[1], "import json\nprint(json.dumps({'hookSpecificOutput': 'invalid'}))\n")
    _write(targets[2], "import json\nprint(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': 42}}))\n")
    _write(targets[3], f"import json\nfrom pathlib import Path\nPath({str(marker)!r}).write_text('yes')\nprint(json.dumps({{'hookSpecificOutput': {{'hookEventName': 'SessionStart', 'additionalContext': 'last'}}}}))\n")

    result = _fire(
        scripts[0], targets, shared_target, mirror_target, "invalid-outputs",
    )

    assert result.returncode == 7
    assert _context(result.stdout) == "first\nlast"
    assert result.stderr.count("invalid SessionStart output skipped") == 2
    assert marker.read_text(encoding="utf-8") == "yes"


def test_two_sessions_share_one_cache_writer(tmp_path: Path):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda args: _fire(*args, copy_delay=0.02),
            (
                (scripts[0], consumer_target, shared_target, mirror_target,
                 "session-a"),
                (scripts[1], consumer_target, shared_target, mirror_target,
                 "session-b"),
            ),
        ))

    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    assert all(_context(r.stdout) == "consumer-ok" for r in results)
    assert sum("self-healed the plugin cache" in r.stderr for r in results) == 1


def test_dead_claim_owner_is_recovered_before_consumers(tmp_path: Path):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    cache = scripts[0].parents[4]
    session_id = "dead-owner-session"
    key = _event_digest(session_id)
    claims = cache / ".sessionstart-claims"
    claims.mkdir(parents=True)
    dead_claim = claims / f"ensure-shared-cache-{key}.claim"
    creator = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os,sys; p=sys.argv[1]; " +
            "fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600); "
            "os.write(fd,b'f'*32); os.fsync(fd); os.close(fd); os._exit(17)",
            str(dead_claim),
        ],
        check=False,
    )
    assert creator.returncode == 17 and dead_claim.is_file()

    with ThreadPoolExecutor(max_workers=len(scripts)) as pool:
        results = list(pool.map(
            lambda script: _fire(
                script, consumer_target, shared_target, mirror_target,
                session_id,
            ),
            scripts,
        ))

    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    assert all(_context(r.stdout) == "consumer-ok" for r in results)
    assert sum("self-healed the plugin cache" in r.stderr for r in results) == 1
    assert not any("cache repair incomplete" in r.stderr for r in results)
    assert list(claims.glob(f"ensure-shared-cache-{key}-*.done"))


def test_live_hung_writer_times_out_without_mutating(tmp_path: Path):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    cache = scripts[0].parents[4]
    lock_path = cache / ".sessionstart-cache-repair.lock"
    holder_code = (
        "import sys,time; sys.path.insert(0,sys.argv[1]); "
        "from cache_repair_lock import acquire_cache_lock,release_cache_lock; "
        "from pathlib import Path; fd=acquire_cache_lock(Path(sys.argv[2]),1); "
        "print('locked',flush=True); time.sleep(6); release_cache_lock(fd)"
    )
    holder = subprocess.Popen(
        [sys.executable, "-c", holder_code, str(scripts[0].parent), str(lock_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout is not None and holder.stdout.readline().strip() == "locked"

    result = _fire(scripts[1], consumer_target, shared_target, mirror_target,
                   "hung-writer-session")
    holder.wait(timeout=10)

    assert result.returncode == 0
    assert "writer lock unavailable" in result.stderr
    assert "dependent hook skipped" in result.stderr
    assert "consumer-ok" not in result.stdout
    assert not shared_target.exists() and not mirror_target.exists()


def test_eleven_second_live_repair_holds_loser_consumer_until_ready(tmp_path: Path):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(
            _fire, scripts[0], consumer_target, shared_target, mirror_target,
            "slow-live-owner", 11.0,
        )
        time.sleep(0.2)
        loser = pool.submit(
            _fire, scripts[1], consumer_target, shared_target, mirror_target,
            "slow-live-owner",
        )
        loser_result = loser.result(timeout=20)
        owner_result = owner.result(timeout=20)

    assert owner_result.returncode == 0, owner_result.stderr
    assert _context(owner_result.stdout) == "consumer-ok"
    assert loser_result.returncode == 0, loser_result.stderr
    assert _context(loser_result.stdout) == "consumer-ok"


def test_malformed_session_fallback_scans_before_consumer(tmp_path: Path):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    result = _fire(
        scripts[0], consumer_target, shared_target, mirror_target, None,
    )

    assert result.returncode == 0, result.stderr
    assert _context(result.stdout) == "consumer-ok"


def test_valid_uncompleted_session_never_bypasses_claim_with_healthy_cache(
    tmp_path: Path,
):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    warmup = _fire(
        scripts[0], consumer_target, shared_target, mirror_target, "warmup",
    )
    assert warmup.returncode == 0, warmup.stderr
    payload = json.dumps({"session_id": "valid-without-claim"})
    env = os.environ.copy()
    env["SHIPWRIGHT_TEST_SHARED_FILE"] = str(shared_target)
    env["SHIPWRIGHT_TEST_MIRROR_FILE"] = str(mirror_target)
    scripts[1].unlink()

    result = subprocess.run(
        [sys.executable, str(scripts[1].with_name("run_if_cache_ready.py")),
         str(consumer_target)],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""
    assert "cache repair not ready" in result.stderr


def test_valid_unreadable_claim_falls_back_to_locked_cache_scan(tmp_path: Path):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    warmup = _fire(
        scripts[0], consumer_target, shared_target, mirror_target, "warmup",
    )
    assert warmup.returncode == 0, warmup.stderr
    session_id = "unreadable-claim"
    cache = scripts[0].parents[4]
    claims = cache / ".sessionstart-claims"
    claim = claims / f"ensure-shared-cache-{_event_digest(session_id)}.claim"
    claim.write_text("not-a-token", encoding="ascii")

    env = os.environ.copy()
    env["SHIPWRIGHT_TEST_SHARED_FILE"] = str(shared_target)
    env["SHIPWRIGHT_TEST_MIRROR_FILE"] = str(mirror_target)
    result = subprocess.run(
        [sys.executable, str(scripts[1].with_name("run_if_cache_ready.py")),
         str(consumer_target)],
        input=json.dumps({"session_id": session_id}),
        text=True,
        capture_output=True,
        env=env,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr
    assert _context(result.stdout) == "consumer-ok"


def test_guard_skips_when_shared_source_cannot_verify_existing_cache(tmp_path: Path):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    warmup = _fire(
        scripts[0], consumer_target, shared_target, mirror_target, "warmup",
    )
    assert warmup.returncode == 0, warmup.stderr
    shutil.rmtree(tmp_path / "plugins" / "marketplaces")

    result = _fire(
        scripts[0], consumer_target, shared_target, mirror_target, None,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""
    assert "cache repair not ready" in result.stderr


@pytest.mark.parametrize("field", ["session_id", "source", "transcript_path"])
def test_lone_surrogate_payload_stays_safe_through_ready_guard(
    tmp_path: Path, field: str,
):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    session_id = "surrogate-session"
    fields = {"source": "startup", "transcript_path": "transcript.jsonl"}
    if field == "session_id":
        session_id = "\ud800"
    else:
        fields[field] = "\ud800"

    result = _fire(
        scripts[0], consumer_target, shared_target, mirror_target,
        session_id, payload_fields=fields,
    )

    assert result.returncode == 0, result.stderr
    assert _context(result.stdout) == "consumer-ok"


def test_ready_guard_holds_reader_lease_through_target(tmp_path: Path):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    session_id = "reader-lease-session"
    warmup = _fire(
        scripts[0], consumer_target, shared_target, mirror_target, session_id,
    )
    assert warmup.returncode == 0, warmup.stderr

    slow_target = consumer_target.with_name("slow-consumer.py")
    started = tmp_path / "slow-consumer.started"
    _write(slow_target, "import json,os,time\nfrom pathlib import Path\nPath(os.environ['SHIPWRIGHT_TEST_STARTED']).write_text('yes')\ntime.sleep(2)\nprint(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': 'started'}}))\n")
    payload = json.dumps({"session_id": session_id})
    env = os.environ.copy()
    env["SHIPWRIGHT_TEST_STARTED"] = str(started)
    guard = subprocess.Popen(
        [sys.executable, str(scripts[0].with_name("run_if_cache_ready.py")),
         str(slow_target)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert guard.stdin is not None
    guard.stdin.write(payload)
    guard.stdin.close()
    guard.stdin = None
    deadline = time.monotonic() + 2
    while not started.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert started.is_file()

    cache = scripts[0].parents[4]
    lock_path = cache / ".sessionstart-cache-repair.lock"
    writer_probe = (
        "import sys; sys.path.insert(0,sys.argv[1]); "
        "from cache_repair_lock import acquire_cache_lock,release_cache_lock; "
        "from pathlib import Path; fd=acquire_cache_lock(Path(sys.argv[2]),.2); "
        "print('blocked' if fd is None else 'acquired'); "
        "release_cache_lock(fd) if fd is not None else None"
    )
    probe = subprocess.run(
        [sys.executable, "-c", writer_probe, str(scripts[0].parent), str(lock_path)],
        text=True,
        capture_output=True,
        timeout=5,
    )
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip() == "blocked"
    assert guard.wait(timeout=5) == 0


def test_guard_started_before_healer_waits_for_ready_cache(tmp_path: Path):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    session_id = "guard-first-session"
    payload = json.dumps({"session_id": session_id})
    env = os.environ.copy()
    env["SHIPWRIGHT_TEST_SHARED_FILE"] = str(shared_target)
    env["SHIPWRIGHT_TEST_MIRROR_FILE"] = str(mirror_target)
    guard = subprocess.Popen(
        [sys.executable, str(scripts[1].with_name("run_if_cache_ready.py")),
         str(consumer_target)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert guard.stdin is not None
    guard.stdin.write(payload)
    guard.stdin.close()
    guard.stdin = None
    time.sleep(0.2)
    healer = subprocess.run(
        [sys.executable, "-c", _HEALER_WRAPPER, str(scripts[0])],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        timeout=10,
    )
    assert healer.returncode == 0, healer.stderr
    stdout, stderr = guard.communicate(timeout=10)
    assert guard.returncode == 0, stderr
    assert _context(stdout) == "consumer-ok"


def test_guard_rejects_expired_done_until_successor_repairs(tmp_path: Path):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    session_id = "resumed-reaped-session"
    warmup = _fire(
        scripts[0], consumer_target, shared_target, mirror_target, session_id,
    )
    assert warmup.returncode == 0, warmup.stderr
    cache = scripts[0].parents[4]
    key = _event_digest(session_id)
    old_done = next((cache / ".sessionstart-claims").glob(
        f"ensure-shared-cache-{key}-*.done"
    ))
    old = time.time() - 31
    os.utime(old_done, (old, old))
    consumer_target.unlink()
    shared_target.unlink()

    payload = json.dumps({"session_id": session_id})
    env = os.environ.copy()
    env["SHIPWRIGHT_TEST_SHARED_FILE"] = str(shared_target)
    env["SHIPWRIGHT_TEST_MIRROR_FILE"] = str(mirror_target)
    guard = subprocess.Popen(
        [sys.executable, str(scripts[1].with_name("run_if_cache_ready.py")),
         str(consumer_target)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert guard.stdin is not None
    guard.stdin.write(payload)
    guard.stdin.close()
    guard.stdin = None
    time.sleep(0.2)
    healer = subprocess.run(
        [sys.executable, "-c", _HEALER_WRAPPER, str(scripts[0])],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        timeout=10,
    )
    assert healer.returncode == 0, healer.stderr
    stdout, stderr = guard.communicate(timeout=10)
    assert guard.returncode == 0, stderr
    assert _context(stdout) == "consumer-ok"
    assert list((cache / ".sessionstart-claims").glob(
        f"ensure-shared-cache-{key}-*.next"
    ))


def test_resume_source_gets_fresh_generation_after_startup_reap(tmp_path: Path):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    session_id = "repeat-resume-session"
    transcript = tmp_path / "transcript.jsonl"
    _write(transcript, "first\n")
    fields = {"source": "startup", "transcript_path": str(transcript)}
    warmup = _fire(
        scripts[0], consumer_target, shared_target, mirror_target, session_id,
        payload_fields=fields,
    )
    assert warmup.returncode == 0, warmup.stderr
    consumer_target.unlink()
    shared_target.unlink()

    payload = json.dumps({
        "session_id": session_id,
        "source": "resume",
        "transcript_path": str(transcript),
    })
    env = os.environ.copy()
    env["SHIPWRIGHT_TEST_SHARED_FILE"] = str(shared_target)
    env["SHIPWRIGHT_TEST_MIRROR_FILE"] = str(mirror_target)
    guard = subprocess.Popen(
        [sys.executable, str(scripts[1].with_name("run_if_cache_ready.py")),
         str(consumer_target)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert guard.stdin is not None
    guard.stdin.write(payload)
    guard.stdin.close()
    guard.stdin = None
    time.sleep(0.2)
    healer = subprocess.run(
        [sys.executable, "-c", _HEALER_WRAPPER, str(scripts[0])],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        timeout=10,
    )
    assert healer.returncode == 0, healer.stderr
    stdout, stderr = guard.communicate(timeout=10)
    assert guard.returncode == 0, stderr
    assert _context(stdout) == "consumer-ok"


def test_guard_rearms_identical_payload_after_cache_reap(tmp_path: Path):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    session_id = "identical-reaped-session"
    warmup = _fire(
        scripts[0], consumer_target, shared_target, mirror_target, session_id,
    )
    assert warmup.returncode == 0, warmup.stderr
    cache = scripts[0].parents[4]
    shared_target.unlink()
    mirror_target.unlink()

    payload = json.dumps({"session_id": session_id})
    env = os.environ.copy()
    env["SHIPWRIGHT_TEST_SHARED_FILE"] = str(shared_target)
    env["SHIPWRIGHT_TEST_MIRROR_FILE"] = str(mirror_target)
    result = subprocess.run(
        [sys.executable, str(scripts[0].with_name("run_if_cache_ready.py")),
         str(consumer_target)],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert _context(result.stdout) == "consumer-ok"
    assert shared_target.read_text(encoding="utf-8") == "ready\n"
    assert mirror_target.read_text(encoding="utf-8") == "ready\n"
    key = _event_digest(session_id)
    assert list((cache / ".sessionstart-claims").glob(
        f"ensure-shared-cache-{key}-*.next"
    ))


def test_late_participant_cannot_trust_prior_identical_completion(tmp_path: Path):
    scripts, consumer_target, shared_target, mirror_target = _layout(tmp_path)
    session_id = "late-participant-reap"
    warmup = _fire(
        scripts[0], consumer_target, shared_target, mirror_target, session_id,
    )
    assert warmup.returncode == 0, warmup.stderr
    shared_target.unlink()
    mirror_target.unlink()

    payload = json.dumps({"session_id": session_id})
    env = os.environ.copy()
    env["SHIPWRIGHT_TEST_SHARED_FILE"] = str(shared_target)
    env["SHIPWRIGHT_TEST_MIRROR_FILE"] = str(mirror_target)
    result = subprocess.run(
        [sys.executable, str(scripts[1].with_name("run_if_cache_ready.py")),
         str(consumer_target)],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert _context(result.stdout) == "consumer-ok"
    assert shared_target.read_text(encoding="utf-8") == "ready\n"
    assert mirror_target.read_text(encoding="utf-8") == "ready\n"
