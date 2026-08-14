"""Render and write the adopted project's planning spec.

Extracted from ``artifact_writer`` for the same reason ``spec_table`` was: that
module is grandfathered at its bloat ceiling, and the spec document grew a
second output — the machine-readable summary of the very table it renders.

Keeping both writes here is deliberate. ``spec.md``'s provenance block and
``.shipwright/adopt/derived-catalogue.json`` are two views of one claim (*these
are the requirements, and nobody has confirmed them*), so they are produced from
a single ``summarize`` pass and written by a single function. A pair like that
derived at two call sites is precisely how a reported count comes to describe a
different table than the one handed over.

**Quality requirements are Functional Requirement rows, not a second table**
(trg-8db840a6, decided at trg-8ba54b66/P2.62: one requirement id space, one
table shape — the same convergence ``shipwright-project``'s greenfield
generator made). They used to render as a prose bullet list under a
``QR-{i:02d}`` label nothing in the framework parses — ``fr_gates.
collect_known_fr_ids`` reads only requirement TABLE rows, so an iterate that
implemented a quality requirement could never name it via ``--affected-frs``
and fell through to the FR-less ``change_type`` branch. :func:`fold_features`
is the one place a QR item becomes a table row, continuing the same
``FR-GG.MM`` sequence the detected features already use.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.derived_catalogue import (  # noqa: E402
    DerivedCatalogue,
    render_provenance_banner,
    summarize,
)
from lib.derived_catalogue_doc import write_summary  # noqa: E402
from lib.fr_id_sequence import canonical_fr_id, sequence_of  # noqa: E402
from lib.render_helpers import _utc_today  # noqa: E402
from lib.spec_table import _load_shared, effective_features, render_fr_table  # noqa: E402


def fold_features(
    features: list[dict[str, Any]],
    qr_items: list[str],
    *,
    existing_fr_ids: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """The full row list the FR table renders: detected features (or the
    zero-detection placeholder), then quality-requirement rows continuing the
    same ``FR-GG.MM`` sequence.

    A QR item is inferred free text with no priority, no layers, no basis and
    no acceptance criteria — turning it into a row does not manufacture rigor
    it doesn't have, it just makes it *addressable*: ``basis_for`` reads no
    ``source_file``/``url`` on a QR row and correctly falls back to
    ``assumed``, and ``infer_required_layers`` reads no surface signal and
    correctly falls back to ``unit``-only. Every FR-table consumer (the
    ``fr_gates`` existence gate, the RTM, traceability) then reaches a QR item
    for free — it was never worth a second id space or a second parser.

    ``existing_fr_ids`` is what makes a QR id assignment additive across
    *regenerations*, not just within one call: without it, a re-run whose
    fresh AST/crawl detects fewer features than a prior run would renumber
    QR ids down into a range an id from that PRIOR run's spec already means
    to ``events.jsonl`` / the RTM / a test tag / a closed PR (trg-8db840a6's
    hazard, measured on leadwright). A QR id continues past whichever is
    higher — this call's own detected features, or whatever a caller already
    found on disk.

    **What this does NOT protect against** (doubt-review, trg-8db840a6):
    ``base``'s own ids are assigned by the CALLER (``generate_adoption_
    artifacts.canonical_fr_id``, purely positional over this run's freshly
    detected features) and are never cross-checked against
    ``existing_fr_ids`` here. If a later run's detected feature COUNT grows
    enough that a base feature's freshly assigned id lands on a number a
    PRIOR run's QR row occupied, that id's meaning silently changes — the
    same "regeneration doesn't preserve row identity" characteristic
    ``generate_adoption_artifacts.py`` has always had for base features
    colliding with base features across runs (positional, no route-matching
    across generations), now also reachable through a QR row because a QR
    row has a real id to collide with at all. Closing that fully needs
    identity-preserving id assignment across regenerations — out of scope
    here (campaign-sized: "making QRs first-class across the requirement
    model", explicitly deferred by the operator's own decided direction).
    """
    base = effective_features(features)
    if not qr_items:
        return base
    known = {f.get("fr_id") for f in base} | set(existing_fr_ids)
    positions = [p for fid in known if fid and (p := sequence_of(fid)) is not None]
    next_position = max(positions, default=0) + 1
    qr_rows: list[dict[str, Any]] = []
    for qr in qr_items:
        qr_rows.append({
            "fr_id": canonical_fr_id(next_position),
            "label": qr,
            "description": qr,
        })
        next_position += 1
    return base + qr_rows


def _existing_fr_ids(spec_path: Path) -> frozenset[str]:
    """FR ids already live in ``spec_path`` — active AND removed — read via
    the shared FR-table reader so a QR id assigned on a regeneration never
    reuses one.

    ``read_fr_rows``, not ``read_active_fr_rows``: a ``## Removed
    Requirements`` row is exactly the case this function exists to protect.
    Its own docstring is explicit that a retired FR number is never reused
    because the id still means something to ``events.jsonl`` / the RTM / a
    test tag / a closed PR — the identical hazard trg-8db840a6 closes for a
    live row, reached through the removed-row path instead of the
    fewer-detected-features path (caught in code review, since no existing
    test exercised a spec carrying a removed section).

    Absent (first adoption) reads as nothing to avoid — there is nothing on
    disk yet to collide with. A read or parse failure is deliberately NOT
    caught here: trg-8db840a6's hazard note is explicit that an inability to
    determine what a prior run already meant must refuse the write rather
    than silently renumber over it, so the exception propagates.
    """
    if not spec_path.is_file():
        return frozenset()
    text = spec_path.read_text(encoding="utf-8")
    read_fr_rows = _load_shared("fr_table_reader").read_fr_rows
    return frozenset(row.id for row in read_fr_rows(text))


def _render_spec_md(
    *,
    project_name: str,
    split_name: str,
    product_description: str,
    features: list[dict[str, Any]],
    qr_items: list[str],
    constraints: list[str],
    catalogue: DerivedCatalogue | None = None,
) -> str:
    today = _utc_today()
    all_features = fold_features(features, qr_items)
    # The table — header, separator and rows — is rendered by `spec_table` in the
    # ONE converged shape (campaign S5). Not inlined here: the header is a shared
    # constant both generators emit, and the cells need Markdown escaping that a
    # bare f-string never applied.
    fr_table = render_fr_table(all_features, split_name=split_name)
    # …and above it, the block that says the catalogue was DERIVED and nobody has
    # confirmed it (trg-1aa5a8ab). Prose, never a table row: every FR-table
    # consumer is line-based on a leading `|`. `catalogue` is threaded in when the
    # caller already computed it, so the count reported at handover and the count
    # printed here come from one derivation.
    banner = render_provenance_banner(
        catalogue if catalogue is not None
        else summarize(all_features, split_name=split_name)
    )
    constraint_block = ""
    for idx, c in enumerate(constraints, start=1):
        constraint_block += f"- **C-{idx:02d}**: {c}\n"
    if not constraint_block:
        constraint_block = "_No constraints inferred._\n"

    # Acceptance Criteria block. When any FR carries non-empty
    # `acceptance_criteria`, render a per-FR sub-list with origin marker
    # (enrichment / tests). FRs without ACs keep today's "TBD" placeholder.
    has_any_ac = any(f.get("acceptance_criteria") for f in all_features)
    ac_block = ""
    if has_any_ac:
        for f in all_features:
            fr_id = f.get("fr_id", "FR-01.?")
            label = f.get("label", "")
            acs = f.get("acceptance_criteria") or []
            source = f.get("acceptance_source") or ""
            if not acs:
                ac_block += (
                    f"### {fr_id} — {label}\n\n"
                    "_TBD — refine via /shipwright-iterate._\n\n"
                )
                continue
            origin_note = (
                f"_Source: {source}._" if source else ""
            )
            ac_block += f"### {fr_id} — {label}\n\n{origin_note}\n\n"
            for ac in acs:
                ac_block += f"- {ac}\n"
            ac_block += "\n"
    else:
        ac_block = (
            "Acceptance criteria per FR are placeholders (`TBD`) — refine them "
            "with explicit behavior expectations as features evolve via "
            "`/shipwright-iterate`.\n\n"
            "The auto-generated E2E baseline at `e2e/flows/adopted-baseline.spec.ts` "
            "(if Playwright crawl succeeded) covers mechanical rendering / "
            "visibility checks, not semantic behavior.\n"
        )

    return f"""# Specification — {project_name} / {split_name}

_Generated by /shipwright-adopt on {today}. Refine via /shipwright-iterate._

## Abstract

{product_description}

## Functional Requirements

{banner}

{fr_table}

## Constraints

{constraint_block}

## Acceptance Criteria

{ac_block}"""

def write_spec(
    project_root: Path,
    *,
    project_name: str,
    split_name: str,
    product_description: str,
    features: list[dict[str, Any]],
    qr_items: list[str],
    constraints: list[str],
) -> list[Path]:
    """Write the planning spec **and** the machine-readable summary of it.

    Both, from one ``summarize`` pass, because they are two views of a single
    claim — *these are the requirements, and nobody has confirmed them*. Writing
    them together is what makes it structurally impossible for the count reported
    at handover to describe a different table than the one handed over
    (trg-1aa5a8ab); two call sites deriving it independently is exactly how such
    a pair drifts.

    Returns both paths, spec first.

    There is deliberately **no** caller-supplied catalogue override. One existed
    and was removed: it let a caller hand in a summary derived from different
    features, which would then be written beside a table rendered from these —
    two artifacts disagreeing by construction, which is precisely the drift this
    pairing exists to prevent (external code review).

    ``qr_items`` are folded into FR-table rows here — before ``summarize`` runs
    — via :func:`fold_features`, reading the spec already on disk (if any) so a
    regeneration's QR ids never collide with one an earlier run's spec already
    means elsewhere (trg-8db840a6). The fold happens exactly once, in this one
    place, for the same reason the catalogue override was removed: a second
    independent fold (in a caller, or inside the renderer) is how the table and
    the summary would come to disagree about which rows exist.
    """
    split_dir = project_root / ".shipwright" / "planning" / split_name
    spec = split_dir / "spec.md"
    all_features = fold_features(
        features, qr_items, existing_fr_ids=_existing_fr_ids(spec),
    )
    catalogue = summarize(all_features, split_name=split_name)
    split_dir.mkdir(parents=True, exist_ok=True)
    spec.write_text(_render_spec_md(
        project_name=project_name, split_name=split_name,
        product_description=product_description, features=all_features,
        qr_items=[], constraints=constraints, catalogue=catalogue,
    ), encoding="utf-8")
    return [spec, write_summary(project_root, catalogue)]


__all__ = ["fold_features", "write_spec"]
