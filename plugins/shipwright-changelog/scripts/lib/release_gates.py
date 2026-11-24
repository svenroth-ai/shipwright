"""What each question of the release asks, read from the gate catalog (second pass A2 and C1).

``shared/config/gate_catalog.json`` is the one source of the gate policy. ``release.py prepare`` reads its
changelog rows through ``resolve_gate_policy.py --phase changelog --list`` and answers each question with
``auto`` (do not ask: take the default the catalog names) or ``ask``. The two prose copies of this rule (Step 3 and
Step 5 of ``SKILL.md``, the gate lines of ``first-actions.md``) are gone: the skill says "do what ``gates`` says".

Rule, the one the two prose copies stated: a gate is ``auto`` only when its catalog policy is ``auto-default`` AND
the release is a dispatched (pipeline) run or its autonomy is ``autonomous`` / ``unattended``; every other case,
a missing row and an unknown policy included, is ``ask`` (the safe side).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

GATE_IDS = {"version": "changelog.version-suggestion", "preview": "changelog.entry-preview",
            "out_of_sequence": "changelog.out-of-sequence-continue"}
AUTONOMOUS = ("autonomous", "unattended")
AUTO_DEFAULT = "auto-default"


def answers(rows: Iterable[Mapping[str, Any]], *, mode: str, autonomy: str | None) -> dict[str, str]:
    """``{version, preview, out_of_sequence}`` -> ``auto`` | ``ask``, from the resolver's rows."""
    policy = {r.get("gate_id"): r.get("policy") for r in rows if isinstance(r, Mapping)}
    unattended = mode == "pipeline" or autonomy in AUTONOMOUS
    return {name: "auto" if policy.get(gate) == AUTO_DEFAULT and unattended else "ask" for name, gate in GATE_IDS.items()}
