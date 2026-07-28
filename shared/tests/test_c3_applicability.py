"""Canon **C3** — which phases it applies to, and what a whole-run audit reports.

Split from ``test_c3_handoff_freshness.py`` to keep both inside the 300-LOC
limit. This half covers the three properties a naive key would break:

* **Applicability.** The Stop-hook canon runner invokes C3 for every phase in
  ``PLUGIN_TO_PHASE``, including three that write no canon marker at all.
* **A producer for every phase C3 checks.** ``iterate`` was checked for a
  ``phase_history`` bucket it has never written — F5c moved to
  ``append_iterate_entry.py`` long before — so it warned on every Stop and the
  remediation named a tool its pipeline had abandoned. The registry drift guard
  below is what stops that recurring.
* **Whole-run audits.** ``verify_phase.py --phase all`` checks every phase
  against ONE handoff. Every phase must get an honest answer: the owner passes,
  phases it superseded are named skips, and a phase that ran later and wrote
  nothing still warns. Asserted separately so uniformity cannot swallow
  applicability.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

import pytest  # noqa: E402

from _c3_fixtures import (  # noqa: E402
    EARLY,
    ITERATE_RUN,
    LATE,
    RUN,
    record_completions,
    run_for,
    write_handoff,
)
from lib.phase_history import COMPLETION_PRODUCER  # noqa: E402
from verifiers.handoff_phase_canon import (  # noqa: E402
    C3_CANON_PHASES,
    check_c3_session_handoff_fresh_after_phase as check_c3,
)

#: Phases the Stop-hook canon runner audits that write no canon marker.
NON_PRODUCERS = ("security", "compliance", "adopt")


def _write(root: Path, *, marker_phase: str, marker_ts: str,
           completions: dict[str, str], marker_run: str = RUN) -> Path:
    write_handoff(root, phase=marker_phase, run_id=marker_run, timestamp=marker_ts)
    record_completions(root, completions)
    return root


def _all_phases_at(when: str) -> dict[str, str]:
    return {phase: when for phase in sorted(C3_CANON_PHASES)}


# --- applicability ------------------------------------------------------------

@pytest.mark.parametrize("phase", NON_PRODUCERS)
def test_a_phase_with_no_canon_producer_is_skipped_not_warned(tmp_path, phase):
    _write(tmp_path, marker_phase="build", marker_ts=EARLY, completions={"build": EARLY})

    result = check_c3(tmp_path, phase)

    assert result.is_skipped
    assert result.ok is not True
    assert phase in result.detail and "canon-marker" in result.detail


@pytest.mark.parametrize("phase", sorted(C3_CANON_PHASES))
def test_every_canon_phase_that_wrote_its_own_note_passes(tmp_path, phase):
    _write(tmp_path, marker_phase=phase, marker_ts=EARLY,
           completions={phase: EARLY}, marker_run=run_for(phase))

    result = check_c3(tmp_path, phase)

    assert result.ok is True, result.detail
    assert not result.is_skipped


def test_c3_canon_phases_align_with_plugin_to_phase():
    """Registry drift guard, BOTH directions (the repo's SSoT meta-test rule)."""
    from lib.phase_quality import PLUGIN_TO_PHASE

    known = set(PLUGIN_TO_PHASE.values())
    assert C3_CANON_PHASES <= known, (
        f"C3 names phases no plugin produces: {sorted(C3_CANON_PHASES - known)}"
    )
    assert known - C3_CANON_PHASES == set(NON_PRODUCERS), (
        "the set of phases without a canon-marker producer changed — give the new "
        f"phase a producer or add it to NON_PRODUCERS deliberately: "
        f"{sorted(known - C3_CANON_PHASES)}"
    )


def test_every_c3_phase_has_a_completion_producer():
    """A phase C3 checks whose completions nothing records can only ever WARN.

    That is what ``iterate`` did: in ``C3_CANON_PHASES``, never in
    ``phase_history``. Forward direction of the same drift guard —
    ``test_completion_producers_all_exist`` walks the other way.
    """
    missing = sorted(C3_CANON_PHASES - set(COMPLETION_PRODUCER))
    assert not missing, (
        f"C3 checks {missing} but nothing records their completions — give each "
        "one a producer in COMPLETION_PRODUCER or drop it from C3_CANON_PHASES"
    )


def test_completion_producers_all_exist():
    """Reverse direction: every named producer resolves to a file on disk."""
    tools = REPO_ROOT / "shared" / "scripts" / "tools"
    missing = sorted({
        tool for tool in COMPLETION_PRODUCER.values() if not (tools / tool).is_file()
    })
    assert not missing, f"COMPLETION_PRODUCER names tools that do not exist: {missing}"


@pytest.mark.parametrize("producer", sorted(set(COMPLETION_PRODUCER.values())))
def test_every_named_producer_actually_runs(producer):
    """Existing on disk is not enough — a producer C3's remediation names must be
    something the operator can run. Parametrised over the DISTINCT tools: eight
    phases name two of them, and six duplicate interpreter spawns buy nothing."""
    tool = REPO_ROOT / "shared" / "scripts" / "tools" / producer

    result = subprocess.run(
        [sys.executable, str(tool), "--help"], capture_output=True, text=True, timeout=120,
    )

    assert result.returncode == 0, f"{tool.name} --help failed: {result.stderr}"


# --- auditing a whole finished run --------------------------------------------

def test_a_whole_run_audit_passes_the_owner_and_skips_the_rest(tmp_path):
    """`--phase all` after a finished pipeline: changelog wrote the note last,
    every other phase completed before it. Nobody should warn."""
    completions = _all_phases_at(EARLY)
    completions["changelog"] = LATE
    _write(tmp_path, marker_phase="changelog", marker_ts=LATE, completions=completions)

    verdicts = {p: check_c3(tmp_path, p) for p in sorted(C3_CANON_PHASES)}

    assert verdicts["changelog"].ok is True, verdicts["changelog"].detail
    others = {p: v for p, v in verdicts.items() if p != "changelog"}
    assert all(v.is_skipped for v in others.values()), {
        p: v.detail for p, v in others.items() if not v.is_skipped
    }
    assert not any(v.ok is False for v in verdicts.values())
    assert len(verdicts) == len(C3_CANON_PHASES), "every canon phase must be audited"


def test_a_whole_run_audit_still_skips_non_producer_phases(tmp_path):
    """The companion assertion: uniformity must not swallow applicability."""
    _write(tmp_path, marker_phase="changelog", marker_ts=LATE,
           completions=_all_phases_at(EARLY))

    for phase in NON_PRODUCERS:
        assert check_c3(tmp_path, phase).is_skipped


def test_a_phase_that_ran_after_the_owner_still_warns_in_a_whole_run_audit(tmp_path):
    """The skip must not become a blanket amnesty: `deploy` completed AFTER the
    note was written and left none of its own."""
    completions = _all_phases_at(EARLY)
    completions["deploy"] = LATE
    _write(tmp_path, marker_phase="changelog", marker_ts=EARLY, completions=completions)

    result = check_c3(tmp_path, "deploy")

    assert result.ok is False, result.detail
    assert "left no note of its own" in result.detail


def test_the_iterate_phase_is_checked_against_its_own_ledger(tmp_path):
    """HIGH-3: iterate has never written `phase_history` — F5c moved to
    `append_iterate_entry.py`. Reading the bucket gave a permanent WARN whose
    remediation named a tool iterate's pipeline had abandoned."""
    _write(tmp_path, marker_phase="iterate", marker_ts=EARLY,
           completions={"iterate": EARLY}, marker_run=ITERATE_RUN)
    config = json.loads((tmp_path / "shipwright_run_config.json").read_text(encoding="utf-8"))

    result = check_c3(tmp_path, "iterate")

    assert "iterate" not in config["phase_history"], "the fixture must not fake a bucket"
    assert result.ok is True, result.detail


def test_an_iterate_with_no_ledger_entry_names_the_right_producer(tmp_path):
    """The remediation must name the tool iterate actually runs."""
    _write(tmp_path, marker_phase="iterate", marker_ts=EARLY,
           completions={}, marker_run=ITERATE_RUN)

    result = check_c3(tmp_path, "iterate")

    assert result.ok is False
    assert "append_iterate_entry.py" in result.detail
    assert "append_phase_history.py" not in result.detail
