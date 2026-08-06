"""The declined register target must stay a DECISION, not fold back into prose.

Three files state the position that inline `# nosemgrep` suppressions have no
`target` in the accepted-risk register. Before
`iterate-2026-08-05-inline-suppression-ratchet` all three stated it as a bare
assertion, which is exactly why triage card `trg-095cd2bf` existed: the position
was being *inherited* rather than decided, and nobody could tell from the code
whether it had ever been weighed.

Each must therefore name the decision AND the control that stands in its place.
Without that trail a reader who asks "why is there no target for this?" finds an
assertion and no answer — which is the state this run was opened to end. These
are cheap string assertions on purpose: the risk is silent removal during an
unrelated edit, not subtle drift.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_DECISION = "iterate-2026-08-05-inline-suppression-ratchet"
_BASELINE = "shipwright_inline_suppressions.json"


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_the_register_module_names_the_decision_and_the_control():
    text = _read("shared/scripts/accepted_risks.py")
    assert _DECISION in text, "the declined target must cite its decision"
    assert "inline_suppressions" in text, "and name the control replacing it"


def test_the_discovery_module_calls_it_a_decision_not_a_gap():
    text = _read("shared/scripts/accepted_risk_scan.py")
    assert _DECISION in text
    assert "DECISION, not a gap" in text, (
        "the wording matters: an unexplained omission reads as unfinished work "
        "and invites someone to 'fix' it by adding the target"
    )


def test_the_register_file_header_points_operators_at_the_baseline():
    """The register is the file an operator opens when they want to record a
    suppression. It must tell them where an inline one goes instead."""
    text = _read("shipwright_accepted_risks.yaml")
    assert _DECISION in text
    assert _BASELINE in text
    assert "inline_suppressions_cli.py" in text, "and how to check it"


def test_the_baseline_readme_points_back_at_the_register():
    """Both directions, or a reader who starts at the baseline never learns
    why the register does not cover this."""
    doc = json.loads(_read(_BASELINE))
    readme = "\n".join(doc["_readme"])
    assert "shipwright_accepted_risks.yaml" in readme
    assert _DECISION in readme
