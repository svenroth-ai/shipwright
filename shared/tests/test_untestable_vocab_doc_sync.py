"""Reverse-drift guard for the closed UNTESTABLE vocabulary.

iterate-2026-05-30-test-completeness-gate.

The vocabulary of structural reasons a behavior may be UNTESTABLE has a
single source of truth — ``UNTESTABLE_REASON_CODES`` in
``shared/scripts/tools/verifiers/iterate_checks.py``. The operator-facing
documentation lists the same codes in
``plugins/shipwright-iterate/skills/iterate/references/confidence-anti-patterns.md``.

Per the Registry-driven SSoT meta-test rule (SKILL.md Step 6), BOTH
directions of drift protection must exist:

- **forward** — every code in the frozenset appears verbatim in the doc.
- **reverse** — every reason-code-shaped token the doc lists is a real
  member of the frozenset (no doc-only ghost codes).

If a future code is added to one side but not the other, this fails.
"""

import re
from pathlib import Path

from tools.verifiers.iterate_checks import UNTESTABLE_REASON_CODES

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOC = (
    _REPO_ROOT
    / "plugins" / "shipwright-iterate" / "skills" / "iterate"
    / "references" / "confidence-anti-patterns.md"
)

# Reason codes share two stable prefixes (`requires-…`, `covered-…`). The
# reverse scan keys off those so it never sweeps up unrelated kebab tokens
# (e.g. `round-trip`, `boundary-probes`). A future code MUST keep one of
# these prefixes or this test must be updated alongside it.
_CODE_IN_DOC = re.compile(r"`(requires-[a-z-]+|covered-[a-z-]+)`")


def test_doc_exists():
    assert _DOC.exists(), f"confidence-anti-patterns.md missing at {_DOC}"


def test_forward_every_code_documented():
    """Forward: each frozenset code appears verbatim (in backticks) in the doc."""
    text = _DOC.read_text(encoding="utf-8")
    missing = [c for c in UNTESTABLE_REASON_CODES if f"`{c}`" not in text]
    assert not missing, (
        f"UNTESTABLE_REASON_CODES not documented in confidence-anti-patterns.md: "
        f"{sorted(missing)}"
    )


def test_reverse_no_ghost_codes_in_doc():
    """Reverse: every reason-code token the doc lists is a real frozenset member."""
    text = _DOC.read_text(encoding="utf-8")
    doc_codes = set(_CODE_IN_DOC.findall(text))
    ghosts = doc_codes - set(UNTESTABLE_REASON_CODES)
    assert not ghosts, (
        f"confidence-anti-patterns.md lists reason codes absent from "
        f"UNTESTABLE_REASON_CODES (ghost codes): {sorted(ghosts)}"
    )


def test_exact_set_equivalence():
    """Belt-and-suspenders: the doc's reason-code set equals the frozenset."""
    text = _DOC.read_text(encoding="utf-8")
    doc_codes = set(_CODE_IN_DOC.findall(text))
    assert doc_codes == set(UNTESTABLE_REASON_CODES), (
        f"doc {sorted(doc_codes)} != code {sorted(UNTESTABLE_REASON_CODES)}"
    )
