"""Structural-anomaly detectors for the FR-row hygiene gate
(iterate-2026-09-06-fr-hygiene-touched-rows).

Split out of ``_fr_hygiene_touched.py`` (which crossed the 300-line
guideline): this half holds the detectors for defects that make a row
INVISIBLE to the touched/clean judgment in the sibling module — an anchor
that will never join its row, a duplicate id no dict-based lookup can
resolve, a row the shared reader declined to parse at all — while
``_fr_hygiene_touched.py`` keeps the core "which id did this run touch, and
is what it touched clean" comparison. No I/O here beyond the parsers each
function calls; every function takes already-read text or an already-built
reject list.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib import fr_criteria  # noqa: E402
from lib import fr_table_reader  # noqa: E402


def _orphan_anchor_findings(base_text: str, head_text: str) -> list[str]:
    """A criterion anchored under an id that will never join any table row's
    pool is silently invisible to `_row_findings` on BOTH sides of the id
    join — `fr_table_reader` enforces the canonical `FR-XX.YY` shape on TABLE
    row ids, but `fr_criteria`'s heading/bold anchor regex accepts any
    `FR[-\\s]?\\d+(?:\\.\\d+)*` and does not zero-pad (`normalise_fr_id` only
    turns a space into a dash). A criterion folded in under a mistyped anchor
    (``### FR-1.02`` for the canonical ``FR-01.02``) pools under a key no
    table row or check will ever look up — it does not classify as touched,
    is never judged for shape, and is not even the "no criteria" case I6
    reports, because from I6's point of view the row simply has none (doubt
    review, medium).

    This does not judge the criterion's own shape (that is `_row_findings`'s
    job once it can find it) — it only surfaces a NEW anchor id, added by
    this run, that carries a real criterion and does not match the canonical
    row-id shape, so the mismatch is visible instead of silently dropping the
    content it guards."""
    base_ids = {fr_id for fr_id, _ in fr_criteria.iter_anchored_blocks(base_text or "")}
    out: list[str] = []
    seen: set[str] = set()
    for fr_id, block in fr_criteria.iter_anchored_blocks(head_text or ""):
        if fr_id in seen or fr_id in base_ids:
            continue
        if fr_table_reader.CANONICAL_FR_RE.match(fr_id):
            continue
        if not fr_criteria.block_criteria(block, strict=False):
            continue
        seen.add(fr_id)
        out.append(
            f"{fr_id}: a new criterion is anchored under a non-canonical id "
            "(not `FR-XX.YY` shape) — it will never join its intended row's "
            "criteria pool and is invisible to every FR-catalogue check; fix "
            "the heading/bold anchor id",
        )
    return out


def _pooled_occurrences(texts: list[str]) -> dict[str, list[tuple[str, str]]]:
    """Every ACTIVE row's ``(name, description)`` content, pooled by id across
    every given text — FR ids are catalog-wide, not scoped to one file, so a
    caller comparing duplicate occurrences must pool across every touched
    spec, not scan one file at a time (see :func:`_new_duplicate_id_findings`).
    Content, not just a count, so a caller can tell an UNCHANGED duplicate
    (same occurrences on both sides) from one where some occurrence's content
    moved — a count alone collapses both to "still 2"."""
    out: dict[str, list[tuple[str, str]]] = {}
    for text in texts:
        for row in fr_table_reader.read_fr_rows(text or ""):
            if not row.removed:
                out.setdefault(row.id, []).append((row.name, row.text))
    return out


def _new_duplicate_id_findings(base_texts: list[str], head_texts: list[str]) -> list[str]:
    """An id with more than one ACTIVE row at HEAD is an ambiguous identity no
    dict-based lookup can safely resolve: `_row_map` keeps whichever
    occurrence is LAST in document order, so a dirty row this run adds ABOVE
    an existing clean legacy row with the same id is silently shadowed by the
    clean one — `_touched_ids`/`_row_findings` never see the dirty occurrence
    at all (doubt review, high; `fr-authoring.md` names this an I4 defect, but
    I4 is never wired into `run_all_checks`, so nothing at F11 sees it
    either).

    This does not try to judge which occurrence is the dirty one (an
    unsound question — dict-based comparison cannot tell); it reports the
    ambiguity itself as unconditionally blocking, so the only way past it is
    to make the id unique again, at which point there is exactly one row
    left for this gate to judge honestly.

    **Pooled across every touched spec, not scanned per file** (Tier-3 PR
    review, PR #679): FR ids are catalog-wide, not scoped to one file, so a
    NEW duplicate split across two touched ``spec.md`` files — one occurrence
    added to each — has exactly one occurrence per file and was invisible to
    a per-file count. The caller now passes every touched path's base/head
    text as a list, pooled together.

    **A duplication already present at base is reported too, when this run
    edited one of its occurrences** (Tier-3 PR review, PR #679, second
    finding): an id duplicated at base is normally legacy this run did not
    create and stays out of scope — but if this run edited the CONTENT of one
    of those occurrences (still the same two-or-more ids, different cell
    text), `_row_map`'s last-wins collapse means the edit can land on a
    non-surviving occurrence and never reach `_touched_ids`/`_row_findings` at
    all — a silent bypass, not merely an untouched legacy row. Comparing the
    pooled occurrence CONTENT (not just the count) catches this: an unchanged
    duplicate (identical occurrence multiset both sides) stays excluded, same
    "touched only" boundary as everywhere else; a duplicate whose occurrence
    multiset differs is reported, whether it is new at HEAD or pre-existing
    with an edited member."""
    base_occ = _pooled_occurrences(base_texts)
    head_occ = _pooled_occurrences(head_texts)
    findings: list[str] = []
    for fr_id, occurrences in sorted(head_occ.items()):
        if len(occurrences) <= 1:
            continue
        base_occurrences = base_occ.get(fr_id, [])
        if sorted(occurrences) == sorted(base_occurrences):
            continue
        findings.append(
            f"{fr_id}: duplicate id — more than one active row shares this id "
            "at HEAD (possibly across separate touched spec files), and this "
            "run changed what one of those occurrences says; this gate "
            "cannot honestly tell which occurrence its edit belongs to, and "
            "a dict-based lookup elsewhere would silently pick one — rename "
            "one occurrence to a distinct FR id before this row can be "
            "certified"
        )
    return findings


def _new_reject_findings(base_rejects: list, head_rejects: list) -> list[str]:
    """A row this run's edit made unparseable is invisible to `_row_map` and
    therefore to `_touched_ids`/`_row_findings` — the shared reader never
    returns a ``FrTableRow`` for it, so there is nothing to judge Name/
    Description/criteria on (doubt review: a hand-typed id like `FR-1.02` for
    the canonical `FR-01.02` silently drops the row, and everything after it
    that reads by id, from this run's own edit).

    Compared via the reader's own ``rejects`` accumulator rather than the row
    text itself, because a row that fails to parse has no reliable cells to
    diff. A reject already present at base is a legacy shape issue outside
    this run's "touched" boundary, same as everywhere else in this module; one
    that is new at head is this run's own edit.

    Compared by MULTIPLICITY (``Counter``), not set membership (doubt review,
    low): a set collapses two rejects sharing the same ``(id, reason)`` into
    one, so a run duplicating or re-typing an already-malformed legacy row
    under the same id/reason pair was invisible — the legacy occurrence
    masked the run's own new one. Only the SURPLUS beyond however many were
    already present at base is reported as new.

    Keyed by ``(id, reason, raw)`` — the reject's own content fingerprint
    (``raw``, the pipe-joined cell text the reader already captures), not
    just ``(id, reason)`` (Tier-3 PR review, PR #679): a run that EDITS an
    already-rejected row's content while its id and rejection reason stay the
    same (e.g. still `non_canonical_id`, still that id) previously matched an
    existing base key and was silently absorbed as "already there" — the
    content changed, but nothing about the changed row was ever judged,
    because a rejected row never produces an `FrTableRow` for `_row_findings`
    to see either. Including `raw` makes an edited row's fingerprint NEW
    even when `(id, reason)` alone stayed identical."""
    def _key(r: dict) -> tuple[str, str, str]:
        return (r["id"], r["reason"], r.get("raw", ""))

    base_counts = Counter(_key(r) for r in base_rejects)
    seen: Counter = Counter()
    findings = []
    for r in head_rejects:
        key = _key(r)
        seen[key] += 1
        if seen[key] <= base_counts[key]:
            continue
        findings.append(
            f"{r['id'] or '(blank id)'}: row does not parse as a governed FR "
            f"requirement ({r['reason']}) — an unparseable row is invisible "
            "to every FR-catalogue check, not just this one; fix the id/"
            "table shape"
        )
    return findings


__all__ = [
    "_new_duplicate_id_findings",
    "_new_reject_findings",
    "_orphan_anchor_findings",
    "_pooled_occurrences",
]
