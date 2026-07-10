"""§6 Phase-Matrix pinning + run_id validation for the session plan (B2).

Split from test_session_plan.py to keep each test module under the 300-line
guideline. This file owns:
- the drift guard that pins session_plan's projection to the NORMATIVE SKILL.md
  §6 Phase Matrix (an unmirrored §6 edit fails a test), and
- run_id validation / fail-soft + the .gitignore rule assertion.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import sys

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "scripts" / "lib"),
)

from session_plan import (  # noqa: E402
    build_session_plan,
    persist_session_plan,
    persist_session_plan_safe,
    plan_path,
)


def _phase_ids(entries):
    return {e["id"] for e in entries}


# --- §6 Phase Matrix pinning (FIX 2 — make SSoT drift detectable) ------------

# Always-on §6 rows (present at every complexity, independent of risk flags).
_ALWAYS = {"repo_scout", "build", "self_review", "test", "finalize"}
# The complexity/risk-gated rows the projection encodes.
_GATED = {"interview", "iterate_spec", "external_plan_review",
          "code_review", "confidence_calibration"}
_RISK = {"none": [], "generic": ["touches_auth"], "io": ["touches_io_boundary"]}

# (complexity, risk_kind) -> the GATED phases §6 (SKILL.md Phase Matrix) says are
# PLANNED. A §6 edit not mirrored in session_plan._PHASE_CATALOG fails this test.
_SIX_MATRIX = {
    ("trivial", "none"): set(),
    ("trivial", "generic"): {"code_review"},
    ("trivial", "io"): {"code_review"},
    ("small", "none"): {"interview"},
    ("small", "generic"): {"interview", "code_review"},
    ("small", "io"): {"interview", "code_review", "confidence_calibration"},
    ("medium", "none"): _GATED,
    ("medium", "generic"): _GATED,
    ("medium", "io"): _GATED,
}


class TestSixPhaseMatrixPinning:
    @pytest.mark.parametrize(("complexity", "kind"), list(_SIX_MATRIX))
    def test_gated_phases_match_phase_matrix(self, complexity, kind):
        plan = build_session_plan(
            {"estimate": complexity, "risk_flags": _RISK[kind]},
            "iterate-2026-07-10-pin",
        )
        planned, skipped = _phase_ids(plan["phases"]), _phase_ids(plan["skips"])
        assert _ALWAYS <= planned, f"{complexity}/{kind}: always-on phase missing"
        expected_planned = _SIX_MATRIX[(complexity, kind)]
        for phase in _GATED:
            if phase in expected_planned:
                assert phase in planned, f"{complexity}/{kind}: {phase} must be PLANNED (§6)"
            else:
                assert phase in skipped, f"{complexity}/{kind}: {phase} must be SKIPPED (§6)"
        for sk in plan["skips"]:
            assert sk["reason"], f"{complexity}/{kind}: {sk['id']} skip has no reason"


# --- run_id validation + fail-soft (FIX 3 / FIX 4) ---------------------------


class TestRunIdValidation:
    _BAD = ["../../evil", "/etc/passwd", r"C:\Windows\x", "a/b/c",
            "iterate-2026-07-10-x\x00y", "not-an-iterate", "", None]

    def test_plan_path_crafted_run_ids_stay_under_iterates(self, tmp_path):
        iterates = tmp_path / ".shipwright" / "agent_docs" / "iterates"
        for rid in ["../../evil", "/etc/passwd", r"C:\Windows\system32\x", "a/b/c"]:
            p = plan_path(tmp_path, rid)
            assert p.parent == iterates, f"{rid!r} escaped to {p}"
            assert p.name.endswith(".plan.json")

    def test_persist_raises_on_bad_run_id(self, tmp_path):
        with pytest.raises(ValueError):
            persist_session_plan({"estimate": "small"}, "../../evil", tmp_path)

    @pytest.mark.parametrize("rid", _BAD)
    def test_safe_returns_none_and_writes_nothing_for_bad_run_id(self, tmp_path, rid):
        assert persist_session_plan_safe({"estimate": "small"}, rid, tmp_path) is None
        iterates = tmp_path / ".shipwright" / "agent_docs" / "iterates"
        assert not iterates.exists() or not list(iterates.glob("*.plan.json"))

    def test_safe_returns_none_for_none_project_root(self):
        # Path(None) raises TypeError -> must be swallowed, not propagated.
        assert persist_session_plan_safe(
            {"estimate": "small"}, "iterate-2026-07-10-x", None) is None


def test_gitignore_ignores_plan_files():
    repo_root = Path(__file__).resolve().parents[3]
    gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
    assert "/.shipwright/agent_docs/iterates/*.plan.json" in gitignore
