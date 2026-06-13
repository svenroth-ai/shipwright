"""End-to-end integration for the shared behavior_snapshot.py gate.

`snapshot -> (edit) -> verify` against a real synthetic pytest project. Proves
the ONE shared tool (`shared/scripts/tools/behavior_snapshot.py`) serves BOTH
gates that the unify-simplify-reducibility iterate joined:

- the **simplify** path (OS1): a behavior-preserving simplify stays green;
- the **reducibility/bloat** path: a catalog reduction (X dead-code delete)
  proven green->green is the mechanical proof of the catalog's "keeps tests
  green" / G3 clause; a coverage-destroying reduction is rejected.

Lives in integration-tests/ (CI runs this dir unfiltered, so the slow,
subprocess-spawning arms execute) — see conftest.py for the shared sys.path.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "shared" / "scripts" / "tools" / "behavior_snapshot.py"

from tools.behavior_snapshot import read_snapshot, snapshot_path  # noqa: E402


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


class TestBehaviorSnapshotCli:
    """Full snapshot -> (edit) -> verify cycle against a real pytest suite.

    Each arm spawns pytest subprocesses. Per the integration-tests convention
    (e.g. test_shipwright_run_e2e.py) such tests stay UNMARKED — the root
    ``-m 'not slow'`` default that CI's integration step inherits would otherwise
    deselect them, so marking this ``slow`` would silently skip it in CI.

    The class proves the ONE shared tool serves BOTH unified gates:
    ``test_clean_simplify_stays_green`` is the **simplify** side;
    ``test_catalog_reduction_dead_code_stays_green`` is the **reducibility**
    side (mechanical proof of the catalog's "keeps tests green" / G3 clause);
    ``test_hidden_side_effect_rejected`` + ``test_removed_coverage_rejected``
    are the fail-closed arms common to both.
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

    def test_catalog_reduction_dead_code_stays_green(self, tmp_path):
        """Reducibility side: the SAME shared tool accepts a catalog **X
        (dead-code)** reduction green->green — and uniquely drives the
        'LOC dropped + coverage intact -> OK' branch end-to-end (the simplify
        arm is LOC-neutral). X is the easy case (deleting unreferenced code can't
        flip a covered test); the gate's *discrimination* on live, covered code is
        proven by the drift / removed-coverage reject arms below, not here."""
        proj = tmp_path / "reduction"
        proj.mkdir()
        # sample.py carries a DEAD (unreferenced) helper alongside live code.
        (proj / "sample.py").write_text(
            "def add(a, b):\n    return a + b\n\n"
            "def _legacy_unused(x):  # dead: no caller, no test\n    return x * 0\n",
            encoding="utf-8",
        )
        (proj / "test_sample.py").write_text(
            "from sample import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
            encoding="utf-8",
        )
        run_id = "iterate-2026-06-13-probe-reduction"
        assert self._snapshot(proj, run_id).returncode == 0

        # Apply the X reduction: delete the dead helper. Behavior preserved.
        (proj / "sample.py").write_text(
            "def add(a, b):\n    return a + b\n", encoding="utf-8",
        )
        verify = self._verify(proj, run_id)
        assert verify.returncode == 0, (
            f"dead-code reduction wrongly rejected: {verify.stdout}\n{verify.stderr}"
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
