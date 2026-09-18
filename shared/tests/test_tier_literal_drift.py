"""Drift guard: every hand-written enumeration of the Claude `TIERS` set
names `fable`.

`TIERS` (`lib.model_tier_config`) is the single source of truth, but six
other sites restate its members in prose/CLI-usage text for a human reader —
nothing type-checks those against `TIERS` itself. A future tier addition
that updates `TIERS` but forgets one of these sites would silently document
a stale enumeration.

The expected literal at each site is built from `_TIER_ORDER` below, never
hand-typed twice — `_TIER_ORDER`'s own membership is cross-checked against
`TIERS` at import time, so adding a tier to `TIERS` without updating
`_TIER_ORDER` fails LOUDLY here before it can reach (and silently pass) the
per-site checks. `TIERS` itself is an unordered `frozenset`, so the
presentation order (ranked tiers by descending capability, then the unranked
ones) cannot be derived mechanically from it — only the membership can, and
that is exactly the property this test enforces.

iterate-2026-09-18-codex-review-tier-config, mini-plan Step 4 (fixed after
spec-reviewer REJECT 2026-09-18: the original version hardcoded the expected
literal instead of deriving it from `TIERS`, so it could not catch the
staleness bug AC34 names).

**Known residual gap (doubt-reviewer LOW, 2026-09-18):** the per-site check
is substring containment, so it catches a MISSING current literal but not a
SURVIVING stale one at a site that restates the enumeration more than once
(confirmed no such site exists today, by inspection — `docs/guide.md` is the
one site actually structured that way, hence its own `== 6` count test
below). Accepted: a full stale-literal sweep would need a bespoke check per
site's prose shape, disproportionate to a latent-only risk.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.model_tier_config import TIERS  # noqa: E402

_TIER_ORDER: tuple[str, ...] = ("opus", "sonnet", "haiku", "inherit", "fable")

assert set(_TIER_ORDER) == TIERS, (
    f"_TIER_ORDER {_TIER_ORDER} and TIERS {sorted(TIERS)} have drifted apart — "
    "a tier was added to one without the other"
)

# (file relative to repo root, separator as it appears at that site)
_SITES: list[tuple[str, str]] = [
    ("shared/scripts/tools/resolve_model_tier.py", "/"),
    ("shared/scripts/lib/review_record_core.py", "/"),
    ("shared/scripts/lib/external_review_routing.py", "/"),
    ("plugins/shipwright-iterate/skills/iterate/SKILL.md", "|"),
    ("plugins/shipwright-build/skills/build/SKILL.md", "|"),
]

_GUIDE_MD_SEPARATOR = r"\|"  # markdown-table-escaped pipe, as it appears in docs/guide.md


def test_every_tier_enumeration_site_names_fable() -> None:
    missing = []
    for rel_path, sep in _SITES:
        literal = sep.join(_TIER_ORDER)
        text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
        if literal not in text:
            missing.append(f"{rel_path}: expected literal {literal!r} not found")
    assert not missing, "\n".join(missing)


def test_guide_md_has_the_literal_at_every_flag_occurrence() -> None:
    """`docs/guide.md` restates the enumeration three times per row (review /
    finalization / plan_review or execution) across two rows — a single
    presence check would pass even if only one of the six occurrences were
    updated."""
    text = (_REPO_ROOT / "docs/guide.md").read_text(encoding="utf-8")
    literal = _GUIDE_MD_SEPARATOR.join(_TIER_ORDER)
    assert text.count(literal) == 6, (
        f"expected 6 occurrences of {literal!r} in docs/guide.md, found {text.count(literal)}"
    )
