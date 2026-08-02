"""How the `touches_build` guard is CONSTRUCTED, and the limits it declares.

Sibling of `test_touches_build_surface_parity.py`, which asserts that the two
`touches_build` surfaces agree entry by entry. This module covers what is not
about a particular entry:

* that `risk_taxonomy._filename_token` builds a guard an entry cannot escape,
  structurally and behaviourally;
* the two places the change deliberately stops short — case, and the sibling
  `touches_middleware` pattern — pinned so each stays a recorded decision
  rather than an oversight the next reader "fixes" or a gap nobody noticed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from classify_complexity import (  # noqa: E402
    RISK_TAXONOMY,
    detect_risk_flags,
    touches_build_files,
)
from risk_taxonomy import _filename_token  # noqa: E402


def _fires_from_message(text: str) -> bool:
    return "touches_build" in [f["flag"] for f in detect_risk_flags(text)]


# ── What this narrowing does NOT change ─────────────────────────────────────

@pytest.mark.parametrize("message", [
    "rename my-next.config.ts",
    "edit next.config to enable standalone output",
])
def test_a_refused_config_stem_still_raises_touches_middleware(message):
    """What this module's narrowing does and does not change, on the record.

    `touches_middleware` carries an unguarded `next\\.config`
    (`RISK_TAXONOMY["touches_middleware"]["patterns"]`), so both messages above
    still raise a risk flag with the same `small` floor and a mandatory review.
    This module narrows `touches_build`; it does not claim the prompt now
    classifies as unremarkable.

    What IS lost is asserted too, rather than waved past: the two flags enforce
    different things (`touches_build` → `performance_test_layer`,
    `touches_middleware` → `mandatory_review`), so the enforcement union does
    change. Saying "the outcome is unchanged" would be the same
    claims-more-than-it-holds error this run kept finding.

    That entry is deliberately left alone: it is a message-only flag with no
    diff-driven counterpart, so there is no second surface to agree with and no
    parity argument for narrowing it. Over-firing there is the safe direction.
    Pinned so the residue is a recorded decision, not an oversight — and so
    that guarding `next\\.config` later is a choice someone makes with this
    test in front of them.
    """
    flags = [f["flag"] for f in detect_risk_flags(message)]
    assert "touches_build" not in flags
    assert "touches_middleware" in flags
    # The residue is a floor + a review, NOT the performance layer.
    assert RISK_TAXONOMY["touches_middleware"]["min_complexity"] == "small"
    assert "mandatory_review" in RISK_TAXONOMY["touches_middleware"]["enforces"]
    assert "performance_test_layer" not in RISK_TAXONOMY[
        "touches_middleware"]["enforces"]


# ── Structural: no entry may be added without the guard ─────────────────────

def test_every_message_pattern_is_token_guarded():
    """Reverse drift protection for patterns with no tuple counterpart.

    The derived tests above are keyed on `TOUCHES_BUILD_FILE_PATTERNS`, so they
    hold a new entry to parity only once it exists in the detector too. A
    message-only pattern would escape them entirely — which is exactly how the
    JS half stayed unguarded while the Python half was fixed. Asserting the
    guard's presence structurally closes that gap for patterns this file cannot
    otherwise reach.

    Asserts the WHOLE constructed shape, both ends. Checking only the leading
    guard would leave `(?<![\\w.-])cargo\\.toml` passing while still firing on
    `cargo.toml.bak` from a message — the same defect class one half over.

    The expected affixes include the non-capturing group, so a pattern whose
    name fragment was spliced in without one cannot satisfy this either. That
    matters because a bare `|` binds looser than everything around it, and a
    both-ends check on the raw string is blind to the result — see
    `test_the_helper_groups_its_argument`, which pins the behaviour this
    string comparison only approximates.
    """
    lead, trail = r"(?<![\w.-])(?:", r")(?!\w)(?!\.\w)"
    unguarded = [
        p for p in RISK_TAXONOMY["touches_build"]["patterns"]
        if not (p.startswith(lead) and p.endswith(trail))
    ]
    assert not unguarded, (
        f"touches_build message patterns not built through _filename_token(): "
        f"{unguarded}. Expected {lead}<name>{trail}. A bare filename regex "
        f"matches inside a longer token (`my-package.json`, "
        f"`package.json.bak`), which the diff surface refuses."
    )


@pytest.mark.parametrize("probe,should_fire", [
    ("gemfile", True),
    ("gemfile.lock", True),
    ("my-gemfile.lock", False),
    ("gemfile.bak", False),
    ("gemfile.locked", False),
])
def test_the_helper_groups_its_argument(probe, should_fire):
    """An alternation in the name fragment must not escape the guards.

    `|` binds looser than the concatenated lookarounds, so an ungrouped
    `gemfile|gemfile\\.lock` compiles as `((?<![\\w.-])gemfile)|(gemfile\\.lock
    (?![\\w-])(?!\\.\\w))` — first branch unguarded at the end, second at the
    start. `my-gemfile.lock` and `gemfile.bak` both fire, which is precisely
    the defect `_filename_token` exists to prevent.

    Pinned behaviourally on a fragment shape no current entry uses, because the
    entries that WILL use it are named as the deliberate next additions in
    `risk_detectors` (Rust/Go/Ruby/PHP), and because the structural test cannot
    see this: the ungrouped string still starts and ends with the guards.
    """
    pattern = _filename_token(r"gemfile|gemfile\.lock")
    assert bool(re.search(pattern, probe)) is should_fire


# ── The one asymmetry that is deliberate ────────────────────────────────────

@pytest.mark.parametrize("name", ["PACKAGE.JSON", "UV.LOCK", "PyProject.toml"])
def test_the_two_surfaces_deliberately_disagree_on_case(name):
    """Parity is on token boundaries, NOT on case — and that is on purpose.

    The diff surface is case-SENSITIVE by decision (`fnmatchcase`, pinned by
    `test_build_input_matching_is_case_sensitive_on_every_platform`): a risk
    gate whose verdict depends on whether the developer is on Windows is a
    defect. The message surface lowercases the whole prompt before matching,
    for every flag in the taxonomy — and a human writing "Package.json" in a
    sentence plainly means the file.

    Making the message surface case-sensitive too would be a narrowing in the
    unsafe direction, for a divergence that costs nothing: over-firing on a
    prompt buys a spurious `small` floor, while under-firing loses the gate.
    Pinned so the asymmetry is a recorded decision rather than an oversight the
    next reader "fixes".
    """
    assert touches_build_files([f"some/path/{name}"]) is False
    assert _fires_from_message(f"bump the pinned dep in {name}")