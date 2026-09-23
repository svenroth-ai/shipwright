"""ADR-045 single-module-identity regression for ``lib.loop_claim``'s
``mark``/``mark-running``/``mark-merged`` dispatch into ``lib.loop_mark``.
Moved out of ``test_loop_claim_release_cleanup.py`` (round 12) purely to
keep that file under the 300-line guideline after its ``--max-attempts``
validation regression tests — this class was never about ``cmd_release``
in the first place, just co-located there historically; no baseline
implication, this file never existed before.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from lib import loop_claim


def _write_state(tmp_path: Path, **overrides) -> Path:
    state_path = tmp_path / ".shipwright" / "loop_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "loop_id": "test-loop", "kind": "sub_iterate", "branch_strategy": "independent",
        "units": [{"id": "A", "status": "pending", "attempt": 0}],
    }
    state.update(overrides)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return state_path


class TestMarkDispatchIsSingleModuleIdentity:
    """ADR-045 regression (Stage-1 spec-reviewer re-check, 2026-09-23):
    `loop_claim.py`'s `cmd_map` must dispatch into the SAME `lib.loop_mark`
    module object `test_loop_mark.py` patches — not a second, bare-imported
    copy with its own independent globals. A prior version of this file
    imported `from loop_mark import ...` (bare-sibling), a second, distinct
    module identity for the same file; a patch on `lib.loop_mark` would
    have silently had zero effect on that copy's functions."""

    def test_dispatch_names_are_the_lib_loop_mark_module_object(self):
        import lib.loop_mark as canonical

        assert loop_claim.cmd_mark_running is canonical.cmd_mark_running
        assert loop_claim.cmd_mark_merged is canonical.cmd_mark_merged
        assert loop_claim.cmd_mark is canonical.cmd_mark
        # Only ONE `loop_mark` identity ever loads — no bare-sibling
        # `loop_mark` entry alongside `lib.loop_mark` in `sys.modules`.
        assert "loop_mark" not in sys.modules or sys.modules["loop_mark"] is canonical

    def test_patching_lib_loop_mark_is_honored_through_main_dispatch(self, tmp_path, monkeypatch):
        """End-to-end proof, not just an identity assert: patch a function
        `cmd_mark_running` actually calls, invoke it through
        `loop_claim.main()`'s own `cmd_map`, and observe the patch take
        effect — exactly the path silently broken before the ADR-045 fix."""
        import lib.loop_mark as canonical

        state_path = _write_state(tmp_path, units=[
            {"id": "A", "status": "claimed", "attempt": 0, "attempt_id": "test-loop-A-a0"},
        ])
        monkeypatch.setattr(canonical, "now_iso", lambda: "PATCHED-TIMESTAMP")
        monkeypatch.setattr(sys, "argv", [
            "loop_claim.py", "mark-running", "--state", str(state_path),
            "--unit", "A", "--attempt-id", "test-loop-A-a0",
        ])
        rc = loop_claim.main()
        assert rc == 0
        unit = json.loads(state_path.read_text(encoding="utf-8"))["units"][0]
        assert unit["running_at"] == "PATCHED-TIMESTAMP"
