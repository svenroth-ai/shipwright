"""F11 spec-impact gate: `none_reason` is accepted as a fallback justification.

`spec_impact_justification` and the FR-gate's `none_reason` are the same
semantic field ("why spec_impact=none"); the FR-gate already REQUIRES
none_reason, and it's the only field finalize_iterate's --event-extras-json
documents. The verifier must accept either. Kept in its own module so the
already-oversized ``test_verify_iterate_finalization.py`` (bloat-baselined)
isn't grown further.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Belt-and-suspenders with conftest: shared/scripts on path for `tools.*`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from tools.verifiers.iterate_checks import check_spec_impact_recorded  # noqa: E402


def _seed_entry_with_intent(proj: Path, run_id: str, intent: str) -> None:
    """Seed an iterate_history entry with a chosen intent/type."""
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [
            {"run_id": run_id, "complexity": "medium", "type": intent},
        ],
    }))


def _write_work_event(proj: Path, commit: str, **fields) -> None:
    """Write a single work_completed event referencing `commit`."""
    evt = {"type": "work_completed", "source": "iterate", "commit": commit}
    evt.update(fields)
    (proj / "shipwright_events.jsonl").write_text(
        json.dumps(evt) + "\n", encoding="utf-8"
    )


def test_spec_impact_none_with_none_reason_passes(tmp_path):
    proj = tmp_path / "p"
    _seed_entry_with_intent(proj, "r1", "feature")
    _write_work_event(proj, "abc1234", intent="feature", spec_impact="none",
                      none_reason="plugin-internal tooling; no target-app FR")
    result = check_spec_impact_recorded(proj, "r1", "abc1234")
    assert result.ok is True


def test_spec_impact_none_prefers_explicit_justification(tmp_path):
    """When both are present, the explicit spec_impact_justification is used
    (the none_reason fallback only fills in when it's absent)."""
    proj = tmp_path / "p"
    _seed_entry_with_intent(proj, "r1", "change")
    _write_work_event(proj, "abc1234", intent="change", spec_impact="none",
                      spec_impact_justification="explicit reason",
                      none_reason="fallback reason")
    result = check_spec_impact_recorded(proj, "r1", "abc1234")
    assert result.ok is True
