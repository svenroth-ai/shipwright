"""D2V evidence-write opt-in gate (iterate-2026-06-10-d2v-evidence-write-optin).

The session-scoped `_d2v_evidence` fixture flushes the TRACKED artifact
`.shipwright/planning/iterate/campaigns/.../D2V-empirical-results.md` at teardown
whenever any D2V method recorded. Methods 2–4 (the e2e proofs) are NOT slow-marked,
so a normal `pytest shared/tests` run regenerated that tracked file → a dirty
working tree on every run (test-isolation leak). The write is now gated behind
`SHIPWRIGHT_D2V_WRITE_EVIDENCE`: the test ASSERTIONS still run (CI coverage
preserved) — only the markdown side-effect is opt-in.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _d2v_helpers as ev  # noqa: E402

_VAR = "SHIPWRIGHT_D2V_WRITE_EVIDENCE"


@pytest.mark.parametrize(
    "val,expected",
    [("1", True), ("true", True), ("TRUE", True), ("yes", True), ("on", True),
     ("0", False), ("false", False), ("", False), ("no", False)],
)
def test_evidence_write_enabled_parses_env(monkeypatch, val: str, expected: bool) -> None:
    monkeypatch.setenv(_VAR, val)
    assert ev.evidence_write_enabled() is expected


def test_evidence_write_enabled_false_when_unset(monkeypatch) -> None:
    monkeypatch.delenv(_VAR, raising=False)
    assert ev.evidence_write_enabled() is False


def _recorded() -> "ev.Evidence":
    e = ev.Evidence()
    e.record(ev.MethodResult(name="METHOD 1 — concurrency stress", passed=True, iterations=1))
    return e


def test_flush_skips_write_without_optin(tmp_path: Path, monkeypatch) -> None:
    """The fix: a default run records methods but must NOT touch the tracked file."""
    monkeypatch.delenv(_VAR, raising=False)
    monkeypatch.setattr(ev, "EVIDENCE_PATH", tmp_path / "D2V.md")
    _recorded().flush(node_ids=["x::y"])
    assert not (tmp_path / "D2V.md").exists()


def test_flush_writes_with_optin(tmp_path: Path, monkeypatch) -> None:
    """Intentional regen (opt-in) still produces the auditable artifact."""
    monkeypatch.setenv(_VAR, "1")
    monkeypatch.setattr(ev, "EVIDENCE_PATH", tmp_path / "D2V.md")
    _recorded().flush(node_ids=["x::y"])
    out = tmp_path / "D2V.md"
    assert out.exists()
    assert "Overall verdict" in out.read_text(encoding="utf-8")
