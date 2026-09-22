"""Meta-test for the Kern SKILL.md <-> references/*.md producer/consumer
boundary (campaign B1.iterate, 2026-05-25).

After the 1709-LOC SKILL.md is split into a thin Kern (~250 LOC) +
references/F*.md per-phase docs + topical references, two things must
hold structurally:

1. Every `references/...` link inside Kern SKILL.md resolves to an
   existing file on disk.
2. Every `references/F*.md` (per-phase reference) and every topical
   reference produced by this split is linked from Kern SKILL.md.
   Orphan reference files = dead documentation, since the agent only
   loads what Kern points at.

The set of "expected" references is intentionally minimal — we only
assert membership for the F-phase + topical references this iterate
produces. The pre-existing references (`boundary-probes.md`,
`round-trip-tests.md`, etc.) are covered by the link-resolution arm.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SKILL_PATH = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "iterate"
    / "SKILL.md"
)
REFERENCES_DIR = SKILL_PATH.parent / "references"
REPO_ROOT = Path(__file__).resolve().parents[3]
BLOAT_BASELINE_PATH = REPO_ROOT / "shipwright_bloat_baseline.json"

# F-phase references this iterate produces. The names mirror SKILL.md
# section anchors so a future reader can grep both sides.
EXPECTED_F_REFERENCES = {
    "F0.md",
    "F0.5.md",
    "F1.md",
    "F2.md",
    "F3.md",
    "F3a.md",
    "F4.md",
    "F5.md",
    "F5b.md",
    "F5c.md",
    "F6.md",
    "F6.5.md",
    "F7.md",
    "F7b.md",
    "F11.md",
    "F12.md",
}

# Topical references this iterate produces.
EXPECTED_TOPICAL_REFERENCES = {
    "context-loading.md",
    "campaign-mode.md",
    "mid-flight-escalation.md",
    "escape-hatch.md",
    "artifact-ownership.md",
    "degraded-mode.md",
    "error-handling.md",
    "path-a-feature.md",
    "path-b-change.md",
    "path-c-bug.md",
}

LINK_PATTERN = re.compile(r"references/([A-Za-z0-9_.+\-]+\.md)")


def _kern_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _linked_references() -> set[str]:
    """Extract every `references/<filename>.md` link from Kern."""
    return set(LINK_PATTERN.findall(_kern_text()))


def test_skill_md_exists() -> None:
    assert SKILL_PATH.is_file(), f"Kern SKILL.md missing at {SKILL_PATH}"


def test_references_dir_exists() -> None:
    assert REFERENCES_DIR.is_dir(), f"references dir missing at {REFERENCES_DIR}"


def test_every_kern_link_resolves() -> None:
    """Every `references/X.md` mentioned in Kern must exist on disk."""
    missing: list[str] = []
    for name in _linked_references():
        if not (REFERENCES_DIR / name).is_file():
            missing.append(name)
    assert not missing, (
        "Kern SKILL.md links to references that don't exist on disk: "
        f"{sorted(missing)}"
    )


def test_every_expected_f_reference_exists_and_is_linked() -> None:
    """Each F-phase reference file from EXPECTED_F_REFERENCES must
    exist AND be linked from Kern.
    """
    linked = _linked_references()
    missing_on_disk = sorted(
        name for name in EXPECTED_F_REFERENCES
        if not (REFERENCES_DIR / name).is_file()
    )
    assert not missing_on_disk, (
        f"Expected F-phase reference files missing on disk: {missing_on_disk}"
    )
    not_linked = sorted(EXPECTED_F_REFERENCES - linked)
    assert not not_linked, (
        f"F-phase references exist on disk but Kern does not link them: "
        f"{not_linked}. Either remove the file or link it from Kern."
    )


def test_every_expected_topical_reference_exists_and_is_linked() -> None:
    linked = _linked_references()
    missing_on_disk = sorted(
        name for name in EXPECTED_TOPICAL_REFERENCES
        if not (REFERENCES_DIR / name).is_file()
    )
    assert not missing_on_disk, (
        f"Expected topical reference files missing on disk: {missing_on_disk}"
    )
    not_linked = sorted(EXPECTED_TOPICAL_REFERENCES - linked)
    assert not not_linked, (
        f"Topical references exist on disk but Kern does not link them: "
        f"{not_linked}"
    )


_REFERENCES_REL = REFERENCES_DIR.relative_to(REPO_ROOT).as_posix()


def _bloat_exception_budgets(baseline_path: Path = BLOAT_BASELINE_PATH) -> dict[str, int]:
    """Basename -> approved LOC ceiling, for references carrying an
    accepted, ADR-backed bloat-baseline exception (an entry under this
    references dir in ``shipwright_bloat_baseline.json`` with `state:
    "exception"` and a non-empty `adr` link — the same two conditions
    Group H's H4 audit requires). Fail-open (empty dict, i.e. the
    original strict 400-cap) on a missing/malformed baseline or a
    non-UTF-8 file, matching `lib.bloat_baseline.load`'s own fail-open
    contract — this test's job is to catch a FRESH, ungrandfathered
    overage, not to second-guess the baseline file's own validity. The
    ceiling is the entry's own `current` (zero headroom, matching the
    repo's deployed anti-ratchet convention), not an unconditional
    exemption — this gate must still notice further, unapproved growth.
    ``baseline_path`` is a test seam; production callers take the default."""
    try:
        doc = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    entries = doc.get("entries") if isinstance(doc, dict) else None
    if not isinstance(entries, list):
        return {}
    budgets: dict[str, int] = {}
    for e in entries:
        if not isinstance(e, dict) or e.get("state") != "exception":
            continue
        path, current, adr = e.get("path"), e.get("current"), e.get("adr")
        if not isinstance(path, str) or not isinstance(current, int):
            continue
        if not isinstance(adr, str) or not adr.strip():
            continue
        if not path.replace("\\", "/").startswith(_REFERENCES_REL + "/"):
            continue
        budgets[Path(path).name] = current
    return budgets


def test_bloat_exception_budgets_only_exempts_approved_references(tmp_path) -> None:
    """`_bloat_exception_budgets` is the sole switch that can raise this
    gate's per-file ceiling above 400 — probe its three behaviours
    directly rather than only incidentally via the single live
    campaign-mode.md entry."""
    baseline = tmp_path / "shipwright_bloat_baseline.json"
    baseline.write_text(json.dumps({
        "entries": [
            {
                "path": "plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md",
                "limit": 400, "current": 516, "state": "exception", "adr": "ADR-pending: x.md",
            },
            {
                "path": "plugins/shipwright-iterate/skills/iterate/references/F5.md",
                "limit": 400, "current": 450, "state": "exception", "adr": None,
            },
            {
                "path": "shared/scripts/lib/review_attribution.py",
                "limit": 300, "current": 453, "state": "grandfathered", "adr": "ADR-x.md",
            },
            {
                "path": "some/other/dir/F1.md",
                "limit": 400, "current": 999, "state": "exception", "adr": "ADR-y.md",
            },
        ]
    }), encoding="utf-8")
    budgets = _bloat_exception_budgets(baseline)
    assert budgets == {"campaign-mode.md": 516}, (
        "an exception under references/ with an ADR link is exempted at its "
        "own `current`; a grandfathered (non-exception) entry, an ADR-less "
        "exception, and a same-named exception OUTSIDE references/ must "
        "each be excluded"
    )

    assert _bloat_exception_budgets(tmp_path / "missing.json") == {}, (
        "a missing baseline must fail open to no exemptions"
    )

    garbage = tmp_path / "garbage.json"
    garbage.write_text("{ not json", encoding="utf-8")
    assert _bloat_exception_budgets(garbage) == {}, "malformed JSON must fail open to no exemptions"


def test_every_new_reference_under_loc_budget() -> None:
    """Every NEW reference file produced by this split must be <= 400 LOC
    (runtime-prompt budget). The pre-existing references are covered by
    the bloat baseline; this test enforces the no-fresh-grandfathered
    rule for the files this iterate creates — a file that has since grown
    past 400 with an ADR-backed bloat-baseline exception (`state:
    "exception"` in `shipwright_bloat_baseline.json`) is not a fresh,
    ungrandfathered overage, so its approved ceiling applies here instead
    of the flat 400, rather than double-gating the same file with two
    independent, silently conflicting LOC caps."""
    budgets = _bloat_exception_budgets()
    over: list[tuple[str, int]] = []
    candidates = EXPECTED_F_REFERENCES | EXPECTED_TOPICAL_REFERENCES
    for name in candidates:
        path = REFERENCES_DIR / name
        if not path.is_file():
            continue
        loc = sum(1 for _ in path.read_text(encoding="utf-8").splitlines())
        if loc > budgets.get(name, 400):
            over.append((name, loc))
    assert not over, (
        f"Reference files exceed their LOC budget: {over}. Split them "
        f"further, or raise a bloat-baseline exception ADR if the growth "
        f"is load-bearing."
    )


def test_kern_skill_md_under_300_loc() -> None:
    """The Kern SKILL.md MUST be <= 300 LOC after the split (campaign
    cleanup-invariant rule (a)). 1709 -> ~250 was the spec target.
    """
    loc = sum(1 for _ in _kern_text().splitlines())
    assert loc <= 300, (
        f"Kern SKILL.md is {loc} LOC, must be <= 300 after split. "
        f"Move more content into references/."
    )
