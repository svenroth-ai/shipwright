"""Drift test for the two FR-01.06 constitution-duplicate mentions of "test
every acceptance criterion at the layer that can falsify it", downgraded
from ``prompt-only (mechanisable)`` to ``prompt-only (judgement)`` by
sub-iterate ``e3-checks-test-security``
(``.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md``,
the FR-01.06 section, note above ``## FR-01.07``).

**Why a drift test and not a gate.** The rule is cross-cutting across five
phases ("five phases touch it, so no per-phase FR can own it" — the ledger's
own words); no per-phase check can mechanically confirm the RIGHT layer was
picked for the RIGHT promise without reading comprehension over what the
criterion actually promises (a UI flow vs. a calculation vs. a row-access
policy vs. reachability). Real mechanical enforcement is a seeded row in the
named Phase-3 enforcement-register design
(``2026-07-24-req3-constitution-enforcement-register-DESIGN.md``); building
one here, ahead of that design, would be exactly the "weaker gate that
pretends" the campaign's abort condition forbids. Per campaign decision D7
(see sub-iterate ``e6-judgement-drift-tests``), a judgement line gets a
drift test on its instruction text and NOTHING ELSE.
"""

from __future__ import annotations

from pathlib import Path

_CONSTITUTION = Path(__file__).resolve().parents[1] / "constitution.md"

_LEDGER = (
    Path(__file__).resolve().parents[2]
    / ".shipwright" / "planning" / "campaigns"
    / "2026-07-23-req3-ac-evidence-ledger-mono.md"
)


def _read_constitution() -> str:
    assert _CONSTITUTION.exists(), f"constitution.md missing at {_CONSTITUTION}"
    return _CONSTITUTION.read_text(encoding="utf-8")


def test_constitution_exists():
    _read_constitution()


def test_ac_layer_rule_instruction_present():
    """The ALWAYS rule this ledger note names — pinned at the sentence
    level, so a wording drift (not just a deletion) fails this test."""
    text = _read_constitution()
    assert (
        "Test every acceptance criterion at the layer that can actually "
        "falsify it" in text
    ), (
        "constitution.md's ALWAYS list no longer instructs testing every AC "
        "at the layer that can falsify it (FR-01.06 judgement mention — "
        "instruction drifted)"
    )
    assert "Testing one layer too low looks like coverage and proves nothing" in text, (
        "constitution.md's AC-layer rule lost its 'looks like coverage and "
        "proves nothing' clause (FR-01.06 judgement mention — instruction "
        "drifted)"
    )


def test_ledger_records_both_mentions_as_judgement_with_a_reason():
    """A wording-preserving ledger regression on the STATUS field alone
    (flipping back to mechanisable without touching constitution.md) would
    go undetected by the instruction-text assertion above. Assert the
    ledger's own rows separately."""
    assert _LEDGER.exists(), f"AC-evidence ledger missing at {_LEDGER}"
    text = _LEDGER.read_text(encoding="utf-8")
    assert "makes it `prompt-only (judgement)`, not `unimplemented`" in text, (
        "ledger's constitution-rule prose mention no longer records "
        "prompt-only (judgement)"
    )
    assert (
        '| "every AC tested at the layer that can falsify it" | constitution '
        "**ALWAYS** — added this round | `prompt-only (judgement)`"
        in text
    ), "ledger's constitution-rule table row no longer records prompt-only (judgement)"
    assert "Downgraded from prompt-only mechanisable, sub-iterate" in text, (
        "ledger no longer carries the downgrade reason for the two "
        "FR-01.06 constitution mentions"
    )
