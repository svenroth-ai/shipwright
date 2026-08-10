"""`lib.compliance_audit_spawn.spawn_compliance_audit` (P2.59; doubt review
round 3, HIGH #1): a `uv run` grandchild is not bounded by a plain
`subprocess.run(capture_output=True, timeout=...)` — this pins the real
Popen/wait/kill-tree behavior with actual subprocesses, not mocks, since the
whole point of the fix is process-tree semantics a mock cannot exercise.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import lib.compliance_audit_spawn as spawn_module  # noqa: E402
from lib.compliance_audit_spawn import spawn_compliance_audit  # noqa: E402


def test_success_captures_output_and_reports_ran_true():
    result = spawn_compliance_audit([sys.executable, "-c", "print('hello-from-child')"])
    assert result["ran"] is True
    assert "hello-from-child" in result["detail"]


def test_nonzero_exit_reports_ran_false():
    result = spawn_compliance_audit([sys.executable, "-c", "import sys; sys.exit(1)"])
    assert result["ran"] is False


def test_failure_to_start_reports_ran_false():
    result = spawn_compliance_audit(["definitely-not-a-real-executable-xyz"])
    assert result["ran"] is False
    assert result["detail"]


def test_timeout_with_a_failed_kill_command_is_reported_honestly(monkeypatch):
    """A real `taskkill`/`killpg` failure must not be reported as
    'process tree killed' — that string is a caller-facing claim that a
    merge/release audit is genuinely no longer running (doubt review round 5,
    MEDIUM). The wrapped process here sleeps 2s and is never actually killed —
    it dies of its OWN natural completion during the 30s follow-up wait, not
    because of anything the (mocked, no-op) kill did. `confirmed` therefore
    ends up True, and the assertion is that the status string still reads
    'kill not confirmed' because the kill command itself never reported
    success — isolating the STATUS-STRING logic from process-tree semantics,
    which the two tests above already cover with a real, unmocked kill."""
    monkeypatch.setattr(spawn_module, "_kill_tree", lambda pid: False)
    result = spawn_compliance_audit(
        [sys.executable, "-c", "import time; time.sleep(2)"], timeout=1,
    )
    assert result == {"ran": False, "detail": "audit timed out after 1s (kill not confirmed)"}


def test_timeout_kills_the_child_and_returns_promptly():
    started = time.monotonic()
    result = spawn_compliance_audit(
        [sys.executable, "-c", "import time; time.sleep(30)"], timeout=1,
    )
    elapsed = time.monotonic() - started
    assert result == {"ran": False, "detail": "audit timed out after 1s (process tree killed)"}
    # Bounded well under the child's 30s sleep — proves the process was
    # actually killed, not merely detached from and waited out.
    assert elapsed < 15


def test_timeout_kills_a_grandchild_too(tmp_path):
    """The scenario the fix exists for: `uv run <script>` is a DIRECT child
    that itself spawns a further grandchild. A direct-child-only kill (what
    a plain `subprocess.run(timeout=...)` does) would leave this grandchild
    running unsupervised (doubt review round 4, LOW — the sibling test above
    only proves a direct child dies)."""
    counter = tmp_path / "counter.txt"
    grandchild_script = tmp_path / "grandchild.py"
    grandchild_script.write_text(
        "import time\n"
        f"path = {str(counter)!r}\n"
        "i = 0\n"
        "while True:\n"
        "    i += 1\n"
        "    with open(path, 'w') as f:\n"
        "        f.write(str(i))\n"
        "    time.sleep(0.1)\n",
        encoding="utf-8",
    )
    parent_script = tmp_path / "parent.py"
    parent_script.write_text(
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, {str(grandchild_script)!r}])\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )

    result = spawn_compliance_audit([sys.executable, str(parent_script)], timeout=2)
    assert result["ran"] is False

    deadline = time.monotonic() + 5
    while not counter.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert counter.exists(), "grandchild never wrote its counter file — test setup issue"

    reading_1 = counter.read_text(encoding="utf-8")
    time.sleep(0.5)
    reading_2 = counter.read_text(encoding="utf-8")
    # Unchanged across the pause — the grandchild stopped running, it did
    # not merely become an orphan that keeps going unsupervised.
    assert reading_1 == reading_2
