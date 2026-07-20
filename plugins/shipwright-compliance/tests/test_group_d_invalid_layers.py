"""D-layer ``invalid_layers``: which malformed cell BLOCKS and which only reports.

Campaign S5 turned ``invalid_layers`` into a MIXED channel and these tests pin the
split. It had been designed as the hard path — its only reason was
``no_canonical_layer``, whose rows are deliberately kept ``explicit`` so the
post-rollout gate fires. S5 added ``marker_glued`` and ``unknown_layer_token``,
both of which ride on ``inferred_legacy`` rows and are advisory by design.

Two ways to get this wrong, and both were live at some point in this campaign:

* route an advisory diagnostic into the hard branch, and a dropped space in an
  ``(inferred)`` cell fails the audit while three separate documents promise it
  never blocks;
* close the HARD set instead of the ADVISORY one, and a typo'd or newly-added
  reason silently stops blocking — a fail-open gate.

A NEW module, not an extraction: all three tests below were written for this
change, and nothing was removed from ``test_group_d_traceability.py`` (which
keeps its own `no_canonical_layer` hard-path test). They live here because
adding them inline would have pushed that file past the 300-line guideline —
which is a reason to open a module, not a claim to have split one.

@FR-01.10
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from scripts.audit import _group_d_traceability as gdt  # noqa: E402
from tests.test_group_d_traceability import _manifest, _node  # noqa: E402


def test_layer_marker_glued_is_visible_but_does_not_fail():
    """`invalid_layers` became a MIXED channel in campaign S5 and must be split.

    It was designed as the hard path — its only reason was `no_canonical_layer`,
    whose rows are deliberately kept `explicit` so this gate fires. S5 added
    `marker_glued`, which is `inferred_legacy` and which ADR-108,
    `fr-authoring.md` §4a and `path-a-feature.md` all describe as advisory.
    Routing it unfiltered meant an author dropping ONE SPACE in an `(inferred)`
    cell failed the audit — a blocking path its own documentation denied.

    Visibility was the point of recording it, so the evidence line stays; the
    block does not.
    """
    m = _manifest(
        [("01-a", _node("FR-05.01", source="inferred_legacy", required=("unit",),
                        coverage={"unit": "ok"}))],
        invalid_layers=[{"fr": "FR-01.16", "spec_path": "s",
                         "raw": "unit,e2e(inferred)", "reason": "marker_glued",
                         "lost": ["e2e"]}],
    )
    status, _sev, detail, ev, _cmd = gdt.check_layer(m)
    assert status == "pass"
    line = next(e for e in ev if "FR-01.16" in e)
    # Right tag, right provenance -- NOT the old hardcoded `[HARD, explicit]`.
    assert "[advisory, inferred_legacy]" in line
    assert "[HARD" not in line
    # The `lost` layer is the only NEW information the diagnostic carries.
    assert "lost: e2e" in line
    assert "advisory layer-cell defect" in detail


def test_layer_an_unrecognised_invalid_reason_fails_closed():
    """The ADVISORY set is the closed one, so an unknown reason BLOCKS.

    Closing the hard set instead would mean a typo'd or newly-added reason
    silently stops blocking — a fail-open gate. Raised by the Codex leg.
    """
    m = _manifest(
        [("01-a", _node("FR-05.01", source="inferred_legacy", required=("unit",),
                        coverage={"unit": "ok"}))],
        invalid_layers=[{"fr": "FR-05.03", "spec_path": "s", "raw": "???",
                         "reason": "some_future_reason"}],
    )
    status, _sev, _detail, ev, _cmd = gdt.check_layer(m)
    assert status == "fail"
    line = next(e for e in ev if "FR-05.03" in e)
    # The EVIDENCE must agree with the verdict. This assertion is the one that
    # was missing: the renderer's fallback tagged an unrecognised reason
    # `advisory` while `check_layer` failed the audit for it, so the operator
    # was told "advisory" on a line that had just blocked the build — the same
    # wrong-severity defect the hardcoded `[HARD, explicit]` was fixed for,
    # re-introduced in the opposite direction. The tag is now DERIVED from the
    # one closed set both sides share, so they cannot disagree again.
    assert "[HARD, unknown]" in line
    assert "advisory" not in line


def test_layer_a_hard_reason_still_decides_when_mixed_with_an_advisory_one():
    m = _manifest(
        [("01-a", _node("FR-05.01", source="explicit", required=("unit",),
                        coverage={"unit": "ok"}))],
        invalid_layers=[
            {"fr": "FR-05.02", "spec_path": "s", "raw": "int, db",
             "reason": "no_canonical_layer"},
            {"fr": "FR-01.16", "spec_path": "s", "raw": "unit,e2e(inferred)",
             "reason": "marker_glued", "lost": ["e2e"]},
        ],
    )
    status, _sev, _detail, ev, _cmd = gdt.check_layer(m)
    assert status == "fail"
    # Both are surfaced; only the hard one decides the verdict.
    assert any("[HARD, explicit]" in e for e in ev)
    assert any("[advisory, inferred_legacy]" in e for e in ev)
