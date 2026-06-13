"""End-to-end CLI integration for behavior_snapshot.py (OS1 probe-iterate).

snapshot -> (edit) -> verify against a real synthetic pytest project: a clean
simplify stays green; behavior drift / removed coverage is rejected. Split out of
test_behavior_snapshot.py (these are slow, subprocess-spawning) to keep each file
focused and under the 300-LOC guideline.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
LIB = PLUGIN_ROOT / "scripts" / "lib"
MODULE_PATH = LIB / "behavior_snapshot.py"
sys.path.insert(0, str(LIB))

from behavior_snapshot import read_snapshot, snapshot_path  # noqa: E402


def _cli(*args: str) -> subprocess.CompletedProcess:
    # PYTHONDONTWRITEBYTECODE stops the snapshot run from caching sample.pyc;
    # otherwise a same-second source overwrite can let the verify run import
    # stale bytecode and mask the very drift it must catch.
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, str(MODULE_PATH), *args],
        capture_output=True, text=True, env=env,
    )


def _write_project(root: Path, *, test_body: str) -> None:
    (root / "sample.py").write_text(
        textwrap.dedent(
            """
            def add(a, b):
                return a + b

            def is_even(n):
                return n % 2 == 0
            """
        ).strip() + "\n",
        encoding="utf-8",
    )
    (root / "test_sample.py").write_text(textwrap.dedent(test_body).strip() + "\n", encoding="utf-8")


GREEN_TESTS = """
    from sample import add, is_even

    def test_add():
        assert add(2, 3) == 5

    def test_is_even():
        assert is_even(4) is True
"""


@pytest.mark.slow
class TestBehaviorSnapshotCli:
    """Full snapshot -> (edit) -> verify cycle against a real pytest suite.

    Marked ``slow`` (spawns pytest subprocesses). CI per-plugin runs it; a local
    fast loop skips it with ``-m 'not slow'``.
    """

    def _snapshot(self, proj: Path, run_id: str) -> subprocess.CompletedProcess:
        return _cli(
            "snapshot", "--project-root", str(proj), "--run-id", run_id,
            "--test-cmd", f"{sys.executable} -m pytest",
        )

    def _verify(self, proj: Path, run_id: str) -> subprocess.CompletedProcess:
        return _cli(
            "verify", "--project-root", str(proj), "--run-id", run_id,
            "--test-cmd", f"{sys.executable} -m pytest",
        )

    def test_clean_simplify_stays_green(self, tmp_path):
        proj = tmp_path / "clean"
        proj.mkdir()
        _write_project(proj, test_body=GREEN_TESTS)
        run_id = "iterate-2026-06-13-probe-clean"

        snap = self._snapshot(proj, run_id)
        assert snap.returncode == 0, snap.stderr
        assert snapshot_path(proj, run_id).is_file()

        # Behavior-preserving simplify: collapse is_even to a one-liner expression.
        (proj / "sample.py").write_text(
            "def add(a, b):\n    return a + b\n\ndef is_even(n):\n    return not n % 2\n",
            encoding="utf-8",
        )
        verify = self._verify(proj, run_id)
        assert verify.returncode == 0, f"clean simplify rejected: {verify.stdout}\n{verify.stderr}"

    def test_hidden_side_effect_rejected(self, tmp_path):
        proj = tmp_path / "sideeffect"
        proj.mkdir()
        _write_project(proj, test_body=GREEN_TESTS)
        run_id = "iterate-2026-06-13-probe-side"

        assert self._snapshot(proj, run_id).returncode == 0

        # Behavior drift in a COVERED path: add now multiplies, so test_add flips
        # red. (Un-covered drift can't be caught by any gate — hence F-simplify.md's
        # Chesterton-Fence + Five-Principles reasoning + hard removed-coverage reject.)
        (proj / "sample.py").write_text(
            "def add(a, b):\n    return a * b\n\ndef is_even(n):\n    return n % 2 == 0\n",
            encoding="utf-8",
        )
        verify = self._verify(proj, run_id)
        assert verify.returncode != 0, "behavior drift was NOT rejected"

    def test_removed_coverage_rejected(self, tmp_path):
        proj = tmp_path / "covloss"
        proj.mkdir()
        _write_project(proj, test_body=GREEN_TESTS)
        run_id = "iterate-2026-06-13-probe-cov"

        assert self._snapshot(proj, run_id).returncode == 0

        # Drop a test (removed coverage).
        _write_project(
            proj,
            test_body="""
                from sample import add

                def test_add():
                    assert add(2, 3) == 5
            """,
        )
        verify = self._verify(proj, run_id)
        assert verify.returncode != 0, "removed test coverage was NOT rejected"

    def test_verify_replays_snapshot_command_without_test_cmd(self, tmp_path):
        """The documented verify invocation omits --test-cmd and replays the
        snapshot's stored command (review 6.2 — the production path)."""
        proj = tmp_path / "replay"
        proj.mkdir()
        _write_project(proj, test_body=GREEN_TESTS)
        run_id = "iterate-2026-06-13-probe-replay"
        assert self._snapshot(proj, run_id).returncode == 0

        (proj / "sample.py").write_text(
            "def add(a, b):\n    return a + b\n\ndef is_even(n):\n    return not n % 2\n",
            encoding="utf-8",
        )
        verify = _cli("verify", "--project-root", str(proj), "--run-id", run_id)
        assert verify.returncode == 0, f"{verify.stdout}\n{verify.stderr}"

    def test_snapshot_warns_when_no_node_ids(self, tmp_path):
        """A non-pytest runner collects no node-ids → snapshot WARNs that the
        coverage/count guards are inert, and records it (review 1.2)."""
        proj = tmp_path / "nonpytest"
        proj.mkdir()
        (proj / "sample.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        run_id = "iterate-2026-06-13-probe-noids"

        snap = _cli(
            "snapshot", "--project-root", str(proj), "--run-id", run_id,
            "--test-cmd", f"{sys.executable} -c pass",
        )
        assert snap.returncode == 0, snap.stderr  # green: exit 0
        assert "inert" in snap.stderr.lower() or "node-id" in snap.stderr.lower()
        assert read_snapshot(proj, run_id)["node_ids_collected"] is False

    def test_snapshot_refuses_red_baseline(self, tmp_path):
        proj = tmp_path / "red"
        proj.mkdir()
        _write_project(
            proj,
            test_body="""
                from sample import add

                def test_broken():
                    assert add(2, 3) == 999
            """,
        )
        snap = self._snapshot(proj, "iterate-2026-06-13-probe-red")
        assert snap.returncode != 0, "snapshot must refuse a red baseline (no green state to store)"
