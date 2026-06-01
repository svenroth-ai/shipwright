"""AC-7 (Test-Update-Klausel) — the iterate SKILL documents the churn-aware
`origin/main` integration procedure and points at the `integrate_main.py`
wrapper (never a bare `git merge`).

If a future edit removes the procedure or renames the wrapper, this fails so the
recurring hand-resolution of churn conflicts cannot silently return.
"""

from __future__ import annotations

from pathlib import Path

_REF = (
    Path(__file__).resolve().parents[1]
    / "skills" / "iterate" / "references" / "mid-flight-escalation.md"
)


def _text() -> str:
    return _REF.read_text(encoding="utf-8")


def test_integrate_procedure_section_present() -> None:
    assert _REF.exists()
    assert "## Integrate origin/main" in _text()


def test_procedure_names_the_wrapper_not_bare_merge() -> None:
    body = _text()
    assert "integrate_main.py" in body
    # The procedure must explicitly steer away from a bare merge.
    assert "bare `git merge origin/main`" in body


def test_procedure_states_hard_safety_gate() -> None:
    body = _text().lower()
    assert "safety gate" in body
    assert "abort" in body
