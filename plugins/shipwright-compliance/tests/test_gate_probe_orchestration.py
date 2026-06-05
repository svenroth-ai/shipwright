"""Decision-tree unit tests for the A5.8 gate behavioral probe.

These exercise ``probe()``'s scenario sequencing (CLEAN sanity → CRITICAL →
EMPTY → INVALID) and verdicts WITHOUT bash/jq, by stubbing ``_run_gate`` to
return chosen exit codes in call order. They run everywhere (including Windows
dev where the end-to-end ``test_audit_gate_behavior_probe`` cases skip), so the
probe's control flow is empirically pinned locally; the sibling file pins the
real gate shells against real fixtures in CI.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import gate_behavior_probe as gbp  # noqa: E402

GATE_ID = "shipwright-critical-gate"


def _wf(body: str) -> dict:
    return {"jobs": {"scan": {"steps": [{"id": GATE_ID, "run": body}]}}}


class _FakeRun:
    """Return a CompletedProcess with exit codes drawn in call order.

    ``probe`` invokes ``_run_gate`` once per scenario in a fixed order and
    short-circuits on the first verdict, so a flat list of return codes maps
    one-to-one onto the scenarios it reaches.
    """

    def __init__(self, codes: list[int]) -> None:
        self._codes = list(codes)
        self._i = 0

    def __call__(self, body, files, timeout):  # noqa: ANN001 - test stub
        rc = self._codes[self._i]
        self._i += 1
        return subprocess.CompletedProcess(args=["bash"], returncode=rc,
                                           stdout="", stderr="diag")


def _patch(monkeypatch, codes: list[int]) -> None:
    monkeypatch.setattr(gbp, "tools_available", lambda: True)
    monkeypatch.setattr(gbp, "_run_gate", _FakeRun(codes))


def test_clean_pass_critical_block_empty_invalid_closed_is_pass(monkeypatch):
    # clean=0(pass), critical=1(block), empty=1(closed), invalid=1(closed)
    _patch(monkeypatch, [0, 1, 1, 1])
    status, detail, _ = gbp.probe(_wf("x"), GATE_ID)
    assert status == "pass", detail


def test_critical_not_blocking_is_fail(monkeypatch):
    # clean=0(pass), critical=0(does NOT block) -> the false-green class
    _patch(monkeypatch, [0, 0])
    status, detail, _ = gbp.probe(_wf("x"), GATE_ID)
    assert status == "fail"
    assert "CRITICAL" in detail


def test_clean_not_passing_is_skip(monkeypatch):
    # clean=1 -> sanity fails -> inconclusive SKIP (not a FAIL)
    _patch(monkeypatch, [1])
    status, detail, _ = gbp.probe(_wf("x"), GATE_ID)
    assert status == "skip"
    assert "CLEAN" in detail or "inconclusive" in detail.lower()


def test_empty_not_failing_closed_is_fail(monkeypatch):
    # clean=0, critical=1, empty=0(does NOT fail closed)
    _patch(monkeypatch, [0, 1, 0])
    status, detail, _ = gbp.probe(_wf("x"), GATE_ID)
    assert status == "fail"
    assert "EMPTY" in detail


def test_invalid_not_failing_closed_is_fail(monkeypatch):
    # clean=0, critical=1, empty=1, invalid=0(does NOT fail closed)
    _patch(monkeypatch, [0, 1, 1, 0])
    status, detail, _ = gbp.probe(_wf("x"), GATE_ID)
    assert status == "fail"
    assert "INVALID" in detail


def test_github_expression_body_is_skip(monkeypatch):
    # A gate body that interpolates ${{ … }} can't be run verbatim as bash →
    # SKIP (inconclusive), determined before any subprocess (no tools needed).
    monkeypatch.setattr(gbp, "tools_available", lambda: True)
    monkeypatch.setattr(gbp, "_run_gate",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran")))
    status, detail, _ = gbp.probe(_wf("echo ${{ github.sha }}\n"), GATE_ID)
    assert status == "skip"
    assert "${{" in detail


def test_timeout_is_skip(monkeypatch):
    monkeypatch.setattr(gbp, "tools_available", lambda: True)

    def boom(body, files, timeout):  # noqa: ANN001 - test stub
        raise subprocess.TimeoutExpired(cmd="bash", timeout=timeout)

    monkeypatch.setattr(gbp, "_run_gate", boom)
    status, detail, _ = gbp.probe(_wf("x"), GATE_ID)
    assert status == "skip"
    assert "timed out" in detail.lower()


def test_oserror_is_skip(monkeypatch):
    monkeypatch.setattr(gbp, "tools_available", lambda: True)

    def boom(body, files, timeout):  # noqa: ANN001 - test stub
        raise OSError("cannot spawn")

    monkeypatch.setattr(gbp, "_run_gate", boom)
    status, detail, _ = gbp.probe(_wf("x"), GATE_ID)
    assert status == "skip"
    assert "inconclusive" in detail.lower()
