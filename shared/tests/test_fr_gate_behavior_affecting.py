"""BP-1: the FR-gate blocks behavior-affecting changes that dodge FR-linkage.

A behavior-affecting change (spec_impact ∈ add/modify/remove) cannot satisfy the
gate via the no-FR change_type escape hatch — it must name an FR. Enforced at the
CLI AND finalize, intent-independently. Lives in its own file (not appended to
the baseline-capped test_record_event.py) to avoid ratcheting it.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1] / "scripts" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from record_event import _fr_or_change_type_gate_error  # noqa: E402


class TestBehaviorAffectingRequiresFr:
    def _iterate_event(self, **overrides) -> dict:
        event = {"type": "work_completed", "source": "iterate", "intent": "change"}
        event.update(overrides)
        return event

    def test_behavior_affecting_without_fr_or_reason_blocked(self):
        # The AC's literal scenario: behavior-affecting + empty FR + no reason.
        event = self._iterate_event(spec_impact="modify")
        err = _fr_or_change_type_gate_error(event)
        assert err is not None
        assert err["error"] == "fr_gate_behavior_affecting_requires_fr"

    def test_behavior_affecting_with_change_type_still_blocked(self):
        # The closed loophole: can't dodge FR-linkage by labeling "tooling".
        event = self._iterate_event(
            spec_impact="modify", change_type="compliance", none_reason="realign",
        )
        err = _fr_or_change_type_gate_error(event)
        assert err is not None
        assert err["error"] == "fr_gate_behavior_affecting_requires_fr"

    def test_behavior_affecting_with_fr_passes(self):
        event = self._iterate_event(spec_impact="modify", affected_frs=["FR-01.10"])
        assert _fr_or_change_type_gate_error(event) is None

    def test_behavior_affecting_with_new_fr_passes(self):
        event = self._iterate_event(spec_impact="add", new_frs=["FR-02.07"])
        assert _fr_or_change_type_gate_error(event) is None

    def test_behavior_preserving_no_fr_still_passes(self):
        # spec_impact none → the no-FR branch remains available.
        event = self._iterate_event(
            spec_impact="none", change_type="tooling", none_reason="CI fix",
        )
        assert _fr_or_change_type_gate_error(event) is None

    def test_rule_is_intent_independent_bug(self):
        # A BUG iterate that is behavior-affecting must also link an FR.
        event = self._iterate_event(
            intent="bug", spec_impact="modify", change_type="tooling",
            none_reason="fix",
        )
        err = _fr_or_change_type_gate_error(event)
        assert err is not None
        assert err["error"] == "fr_gate_behavior_affecting_requires_fr"
