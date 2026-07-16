"""Adopt traceability-baseline — pure helpers (traceability TT7).

Filesystem-light logic for adopt's traceability-baseline step (Spec §6 adopt row,
§11-R5): scaffold the ``@FR`` tag convention and build triage specs from the backfill
report (orphan/unmapped/proposal candidates) + the standing skip rot. The **repo-wide
skip inventory** lives in the sibling ``traceability_skip_inventory`` module (re-exported
here); the ``required_layers`` ambiguity resolver lives in ``traceability_layers``.

ADR-045 discipline (precise): this module imports no ``lib`` package at all. Its
consumer (``seed_traceability_baseline.py``) is the ADR-045 boundary — the ONLY ``lib``
that binds in that interpreter is ``shared/scripts/lib`` (lazily, via ``triage``); the
compliance ``scripts.lib`` (collector) and the backfill's ``shared/scripts/lib`` both run
in SUBPROCESSES, so no two ``lib`` packages ever coexist in one interpreter.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

# Repo-wide skip inventory lives in the sibling module (kept ≤300 LOC); re-exported so
# callers keep importing it off ``traceability_baseline``.
from traceability_skip_inventory import enumerate_test_files, repo_wide_skip_inventory

# The rule templates adopt scaffolds so the target repo learns the @FR convention
# (TT1 shipped the convention section into tests.md.template). Copied verbatim from
# shared/templates/rules/ — the SSoT — to `.claude/rules/`, matching the project phase.
_CONVENTION_RULES = ("tests", "integration-tests")

# Skip-finding pattern → triage severity. A focused test (.only/fit) narrows the whole
# suite → high; an expired/undocumented skip hides a rotted layer → medium; a plain
# pytest.skip without a CI-gated fail is low standing rot. Errors (could_not_lex /
# read_error / syntax_error) surface at low so a garbled file is still visible.
_SKIP_SEVERITY = {
    "js.only": "high",
    "js.skip.expired": "medium",
    "js.skip.no_quarantine": "medium",
    "js.skip.expiry_too_far": "low",
    "pytest.skip": "low",
    "pytest.mark.skipif": "low",
    "pytest.mark.skip": "medium",   # an unconditional decorator disable — standing rot
}

# Above this many skip findings, roll the whole inventory into ONE summary triage card
# instead of one-per-finding — a skipif-heavy cross-platform lib must not flood the Inbox
# with hundreds of cards on first adopt (doubt LOW#4).
_SKIP_ROLLUP_THRESHOLD = 10
_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass(frozen=True)
class TriageSpec:
    """A neutral, git-tracked triage card the tool appends idempotently.

    ``dedup_key`` makes a re-adopt/re-run a no-op (same finding = same card until an
    operator resolves it). ``category`` carries the TT6 orphan distinction so an
    ``unmapped`` test is never rendered as a stale-feature accusation (§11-R4).
    """

    dedup_key: str
    severity: str
    kind: str
    title: str
    detail: str
    fr_id: str | None = None
    category: str | None = None


@dataclass
class ScaffoldResult:
    written: list[str] = field(default_factory=list)
    appended: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 1. Tag-convention scaffold
# ---------------------------------------------------------------------------

_FR_MARKER = "@FR"
_CONVENTION_BEGIN = "<!-- shipwright:@FR-tag-convention BEGIN -->"
_CONVENTION_END = "<!-- shipwright:@FR-tag-convention END -->"


def _fr_convention_section(template_text: str) -> str:
    """Extract the ``## Requirement traceability tags (@FR)`` section from a rule
    template (heading → next ``## `` heading), so a pre-existing rule file gets ONLY
    the convention appended, not the whole boilerplate template."""
    out: list[str] = []
    capturing = False
    for line in template_text.splitlines():
        if line.startswith("## ") and "@FR" in line:
            capturing = True
        elif capturing and line.startswith("## "):
            break
        if capturing:
            out.append(line)
    return "\n".join(out).strip()


def scaffold_tag_convention(project_root: Path, templates_dir: Path, *, dry_run: bool = False) -> ScaffoldResult:
    """Scaffold the ``@FR`` tag-convention rule docs into ``<root>/.claude/rules/``.

    Non-destructive, three outcomes per rule file:
    - **written** — the file is absent → copy the template verbatim.
    - **appended** — the file EXISTS but lacks the ``@FR`` convention (a brownfield repo
      that already curates its own test rules) → append ONLY the convention section under
      a managed marker, preserving the user's content (G-Med/O5: silently skipping would
      leave the repo without the convention it must learn).
    - **skipped_existing** — the file already carries the ``@FR`` convention → untouched
      (idempotent; a re-adopt never double-appends).

    ``dry_run`` classifies each file into the same buckets but touches NOTHING on disk
    (O-C2: a preview must not mutate the adopted repo). Mirrors the project phase's
    ``.claude/rules/`` layout (references/step-7-scaffolding.md).
    """
    result = ScaffoldResult()
    rules_dir = project_root / ".claude" / "rules"
    for name in _CONVENTION_RULES:
        template = templates_dir / f"{name}.md.template"
        if not template.exists():
            continue
        dest = rules_dir / f"{name}.md"
        rel = dest.relative_to(project_root).as_posix()
        if not dest.exists():
            if not dry_run:
                rules_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(template, dest)
            result.written.append(rel)
            continue
        existing = dest.read_text(encoding="utf-8")
        section = _fr_convention_section(template.read_text(encoding="utf-8"))
        if _FR_MARKER in existing or not section:
            result.skipped_existing.append(rel)
            continue
        if not dry_run:
            dest.write_text(
                existing.rstrip() + f"\n\n{_CONVENTION_BEGIN}\n{section}\n{_CONVENTION_END}\n",
                encoding="utf-8")
        result.appended.append(rel)
    return result


# ---------------------------------------------------------------------------
# 2. Triage specs from the backfill report + skip inventory
# ---------------------------------------------------------------------------


def build_orphan_triage_items(report: dict) -> list[TriageSpec]:
    """Build triage specs from a TT6 backfill report, carrying the orphan category.

    - ``confirmed_orphan`` → medium: a live tag points at a removed/absent FR (the
      session rot class).
    - ``possible_orphan`` → low: heuristic-only; flagged for review.
    - ``unmapped`` → low: no live FR maps. Framed as a **review candidate, never a
      stale-feature accusation** (§11-R4).
    - low-confidence ``proposals`` → low: a suggested ``@FR`` tag to confirm.
    """
    orphans = report.get("orphans", {}) or {}
    items: list[TriageSpec] = []
    for o in orphans.get("confirmed_orphan", []):
        test = o.get("test", "?")
        items.append(TriageSpec(
            dedup_key=f"adopt-orphan-confirmed::{test}", severity="medium", kind="maintenance",
            title=f"Orphaned test: {test} tags a removed/absent FR",
            detail=(f"Backfill flagged `{test}` (tagged {o.get('tagged_fr')}, "
                    f"{o.get('reason')}). Retarget or retire — never auto-deleted."),
            category="confirmed_orphan"))
    for o in orphans.get("possible_orphan", []):
        test = o.get("test", "?")
        items.append(TriageSpec(
            dedup_key=f"adopt-orphan-possible::{test}", severity="low", kind="maintenance",
            title=f"Possible orphan test: {test}",
            detail=(f"Heuristic-only: `{test}` most-resembles {o.get('candidate_fr')} "
                    f"({o.get('reason')}). Review — not a confirmed stale test."),
            category="possible_orphan"))
    for test in orphans.get("unmapped", []):
        items.append(TriageSpec(
            dedup_key=f"adopt-unmapped::{test}", severity="low", kind="maintenance",
            title=f"Untagged/unmapped test: {test}",
            detail=(f"`{test}` maps to no live FR. Review candidate for an `@FR` tag — "
                    "NOT a stale-feature accusation; never auto-delete."),
            category="unmapped"))
    for p in report.get("proposals", []):
        test = p.get("test", "?")
        cands = ", ".join(c.get("fr", "?") for c in p.get("candidates", [])) or "—"
        items.append(TriageSpec(
            dedup_key=f"adopt-proposal::{test}", severity="low", kind="maintenance",
            title=f"Backfill proposal: confirm @FR tag for {test}",
            detail=f"Low-confidence candidate(s): {cands}. Confirm + tag, or leave untagged.",
            category="proposal"))
    return items


def build_skip_triage_items(inventory: list[dict]) -> list[TriageSpec]:
    """Build triage specs from the skip inventory.

    Above ``_SKIP_ROLLUP_THRESHOLD`` findings, emit ONE rolled-up summary card (with a
    per-pattern count) instead of one-per-finding, so a skipif-heavy cross-platform lib
    does not flood the WebUI Inbox with hundreds of cards on first adopt (doubt LOW#4).
    At or below the threshold, one granular card per finding.
    """
    if len(inventory) <= _SKIP_ROLLUP_THRESHOLD:
        return [
            TriageSpec(
                dedup_key=f"adopt-skip::{f['file']}:{f['line']}::{f['pattern']}",
                severity=_SKIP_SEVERITY.get(f["pattern"], "low"), kind="maintenance",
                title=f"Pre-existing test skip ({f['pattern']}) at {f['file']}:{f['line']}",
                detail=f"[{f['language']}] {f['reason']}", category="skip")
            for f in inventory
        ]
    by_pattern: dict[str, int] = {}
    for f in inventory:
        by_pattern[f["pattern"]] = by_pattern.get(f["pattern"], 0) + 1
    severity = max((_SKIP_SEVERITY.get(f["pattern"], "low") for f in inventory),
                   key=lambda s: _SEVERITY_RANK.get(s, 0))
    breakdown = ", ".join(f"{n}× {pat}" for pat, n in sorted(by_pattern.items()))
    return [TriageSpec(
        dedup_key="adopt-skip-summary", severity=severity, kind="maintenance",
        title=f"{len(inventory)} pre-existing skipped/focused tests found at onboarding",
        detail=(f"Repo-wide skip inventory ({breakdown}). Standing test rot the SDLC gates "
                "will not have caught. Review + quarantine-with-expiry or delete; rolled up "
                "to one card to avoid flooding the Inbox."),
        category="skip")]


__all__ = [
    "ScaffoldResult", "TriageSpec", "build_orphan_triage_items",
    "build_skip_triage_items", "enumerate_test_files",
    "repo_wide_skip_inventory", "scaffold_tag_convention",
]
