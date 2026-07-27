"""Canon **C3** — which phases it applies to, and what a whole-run audit reports.

Split out of ``test_c3_handoff_freshness.py`` (which pins the content key itself)
in iterate-2026-07-27-c3-phase-content-key to keep both files inside the 300-LOC
limit. This half covers the two properties that a naive port of the F11 content
key would have broken:

* **Applicability.** The Stop-hook canon runner invokes C3 for every phase in
  ``PLUGIN_TO_PHASE``, including three that write no canon marker at all. Without
  an applicability set, a content key turns a schedule-driven false fire into a
  permanent one.
* **Whole-run audits.** ``verify_phase.py --phase all`` checks every phase against
  ONE handoff, so the answer must be uniform across producing phases — while
  still skipping the non-producers. The two are asserted separately on purpose:
  a single "every phase agrees" assertion would mask an applicability regression.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

import pytest  # noqa: E402

from verifiers.handoff_freshness import (  # noqa: E402
    C3_CANON_PHASES,
    check_c3_session_handoff_fresh_after_phase as check_c3,
)

RUN = "iterate-2026-07-27-c3-phase-content-key"
OTHER = "iterate-2026-07-01-something-else"

#: Phases the Stop-hook canon runner audits that write no canon marker.
NON_PRODUCERS = ("security", "compliance", "adopt")


def _write(root: Path, run_id: str, phase: str = "build") -> Path:
    docs = root / ".shipwright" / "agent_docs"
    docs.mkdir(parents=True, exist_ok=True)
    path = docs / "session_handoff.md"
    path.write_text(
        f'---\ncanon_generated: true\nrun_id: "{run_id}"\nphase: "{phase}"\n'
        f'reason: "phase complete"\ntimestamp: "2026-07-27T09:00:00+00:00"\n---\n\n'
        "# Session Handoff\n",
        encoding="utf-8",
    )
    return path


# --- applicability ------------------------------------------------------------

@pytest.mark.parametrize("phase", NON_PRODUCERS)
def test_a_phase_with_no_canon_producer_is_skipped_not_warned(tmp_path, phase):
    _write(tmp_path, RUN)

    result = check_c3(tmp_path, phase, run_id=RUN)

    assert result.is_skipped
    assert result.ok is not True
    assert phase in result.detail and "canon-marker" in result.detail


@pytest.mark.parametrize("phase", sorted(C3_CANON_PHASES))
def test_every_canon_phase_is_actually_evaluated(tmp_path, phase):
    _write(tmp_path, RUN, phase=phase)

    result = check_c3(tmp_path, phase, run_id=RUN)

    assert result.ok is True
    assert not result.is_skipped


def test_c3_canon_phases_align_with_plugin_to_phase():
    """Registry drift guard, BOTH directions (the repo's SSoT meta-test rule).

    The constant cannot live beside C4_PHASES/C5_PHASES in
    ``phase_quality/_constants.py`` — ``phase_quality.__init__`` imports
    ``_runners``, which imports the module this constant lives in, so importing
    it back would close the cycle. This test keeps the two in step instead.
    """
    from lib.phase_quality import PLUGIN_TO_PHASE

    known = set(PLUGIN_TO_PHASE.values())
    assert C3_CANON_PHASES <= known, (
        f"C3 names phases no plugin produces: {sorted(C3_CANON_PHASES - known)}"
    )
    assert known - C3_CANON_PHASES == set(NON_PRODUCERS), (
        "the set of phases without a canon-marker producer changed — give the "
        "new phase a producer or add it to NON_PRODUCERS deliberately: "
        f"{sorted(known - C3_CANON_PHASES)}"
    )


# --- auditing a whole finished run --------------------------------------------

def test_auditing_a_whole_run_gives_every_canon_phase_the_same_answer(tmp_path):
    """`verify_phase.py --phase all` checks every phase against ONE handoff. The
    rejected phase-key design would pass `changelog` here and warn on seven."""
    _write(tmp_path, RUN, phase="changelog")

    verdicts = {p: check_c3(tmp_path, p, run_id=RUN) for p in sorted(C3_CANON_PHASES)}

    assert all(v.ok is True for v in verdicts.values()), {
        p: v.detail for p, v in verdicts.items() if v.ok is not True
    }


def test_auditing_a_whole_run_still_skips_non_producer_phases(tmp_path):
    """The companion assertion: uniformity must not swallow applicability."""
    _write(tmp_path, RUN, phase="changelog")

    for phase in NON_PRODUCERS:
        assert check_c3(tmp_path, phase, run_id=RUN).is_skipped


def test_a_whole_run_audit_of_a_stale_handoff_warns_for_every_canon_phase(tmp_path):
    _write(tmp_path, OTHER, phase="changelog")

    verdicts = {p: check_c3(tmp_path, p, run_id=RUN) for p in sorted(C3_CANON_PHASES)}

    assert all(v.ok is False for v in verdicts.values())
