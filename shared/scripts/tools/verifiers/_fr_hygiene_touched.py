"""Pure per-FR touched/clean judgment for the FR-row hygiene gate
(iterate-2026-09-06-fr-hygiene-touched-rows).

Split out of ``fr_hygiene.py`` (which crossed the 300-line guideline): this
half holds the row/criteria comparison logic — deciding WHICH FR ids a run
touched and WHETHER what it touched is clean — while ``fr_hygiene.py`` keeps
the git-facing orchestration (resolving the merge-base, reading either side,
assembling the ``CheckResult``). No I/O here beyond the parsers it calls;
every function takes already-read text.
"""

from __future__ import annotations

import hashlib
import sys
from collections import Counter
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib import fr_criteria  # noqa: E402
from lib import fr_criterion_shape  # noqa: E402
from lib import fr_hygiene_detectors  # noqa: E402
from lib import fr_table_reader  # noqa: E402


def _row_map(
    text: str, rejects: list | None = None,
) -> dict[str, fr_table_reader.FrTableRow]:
    """Active (non-removed) FR rows, keyed by id. A later duplicate id in the
    same text wins — I4 is the check that flags that as a defect; this reader
    only needs SOME row to compare, not to adjudicate the duplicate.

    ``rejects``, when passed, collects every row the shared reader declined to
    parse as a governed requirement (bad id shape, no governing header, a row
    narrower than its own header) — see :func:`_new_reject_findings`."""
    return {
        row.id: row
        for row in fr_table_reader.read_fr_rows(text, rejects=rejects)
        if not row.removed
    }


def _whole_doc_criteria_texts(text: str) -> dict[str, list[str]]:
    """FR id → every criterion text pooled for that requirement, scanned over
    the WHOLE document — the same scope :func:`_row_findings` uses via
    ``fr_criteria.criteria_for``. Shared by :func:`_whole_doc_criteria_digests`
    (hashes this for change-detection) and :func:`_orphan_anchor_findings`
    (needs the raw texts, not a digest, to tell a real criterion from an empty
    anchor)."""
    texts_by_id: dict[str, list[str]] = {}
    for fr_id, block in fr_criteria.iter_anchored_blocks(text or ""):
        texts_by_id.setdefault(fr_id, []).extend(
            fr_criteria.block_criteria(block, strict=False),
        )
    return texts_by_id


def _whole_doc_criteria_digests(text: str) -> dict[str, str]:
    """FR id → digest of that requirement's pooled acceptance criteria,
    scanned over the WHOLE document — the same scope :func:`_row_findings`
    uses via ``fr_criteria.criteria_for``.

    ``_layer_coverage_ac.criteria_digests`` almost fits (same pooling, same
    ``strict=False``) but restricts to a recognised ``## Acceptance Criteria``
    REGION when that region's anchor id-set matches the whole document's — a
    cross-layer-gate-specific narrowing this gate never asked for. The guard
    only compares which IDS are found, not which BLOCKS: a spec with one
    top-level AC section covering every id, plus a stray extra anchor for one
    of those same ids somewhere else in the document (a hand-edited spec is
    exactly what this gate exists to police), passes the guard unchanged while
    still losing that stray block — invisible to this touched-detection half
    while `_row_findings`'s whole-document `criteria_for` would still see it
    (doubt review, medium). Reimplemented here at whole-document scope with
    the same underlying primitives so both halves of one judgment share one
    scope, rather than pulling in the region-restricted reader and its
    own guard for a use it was not written for."""
    return {
        fr_id: hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()
        for fr_id, texts in _whole_doc_criteria_texts(text).items()
    }


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


def _new_duplicate_id_findings(base_text: str, head_text: str) -> list[str]:
    """An id with more than one ACTIVE row at HEAD is an ambiguous identity no
    dict-based lookup can safely resolve: `_row_map` keeps whichever
    occurrence is LAST in document order, so a dirty row this run adds ABOVE
    an existing clean legacy row with the same id is silently shadowed by the
    clean one — `_touched_ids`/`_row_findings` never see the dirty occurrence
    at all (doubt review, high; `fr-authoring.md` names this an I4 defect, but
    I4 is never wired into `run_all_checks`, so nothing at F11 sees it
    either). Only a duplication NEW at HEAD is reported — an id already
    duplicated at base is legacy content this run did not create, same
    "touched only" boundary as everywhere else in this gate.

    This does not try to judge which occurrence is the dirty one (an
    unsound question — dict-based comparison cannot tell); it reports the
    ambiguity itself as unconditionally blocking, so the only way past it is
    to make the id unique again, at which point there is exactly one row
    left for this gate to judge honestly."""

    def _dupes(text: str) -> set[str]:
        counts = Counter(row.id for row in fr_table_reader.read_fr_rows(text or "") if not row.removed)
        return {fr_id for fr_id, n in counts.items() if n > 1}

    new_dupes = _dupes(head_text) - _dupes(base_text)
    return [
        f"{fr_id}: duplicate id — more than one active row shares this id at "
        "HEAD; this gate cannot honestly tell which is which, and a dict-"
        "based lookup elsewhere would silently pick one — rename one "
        "occurrence to a distinct FR id before this row can be certified"
        for fr_id in sorted(new_dupes)
    ]


def _touched_ids(base_text: str, head_text: str) -> set[str]:
    """FR ids whose Name/Description changed, or whose acceptance-criteria
    digest changed, between ``base_text`` and ``head_text``. Union of both —
    see ``fr_hygiene``'s module docstring for why the criteria half is
    required too."""
    base_rows, head_rows = _row_map(base_text), _row_map(head_text)
    touched = {
        fr_id for fr_id in set(base_rows) | set(head_rows)
        if (base_rows.get(fr_id).name if fr_id in base_rows else None,
            base_rows.get(fr_id).text if fr_id in base_rows else None)
        != (head_rows.get(fr_id).name if fr_id in head_rows else None,
            head_rows.get(fr_id).text if fr_id in head_rows else None)
    }
    base_digests = _whole_doc_criteria_digests(base_text)
    head_digests = _whole_doc_criteria_digests(head_text)
    touched |= {
        fr_id for fr_id in set(base_digests) | set(head_digests)
        if base_digests.get(fr_id) != head_digests.get(fr_id)
    }
    # Only ids that still have a live row at HEAD are judgeable — a touch that
    # turned out to be a REMOVAL (row moved to `## Removed Requirements`) is
    # not a hygiene target; `check_removal_coverage` owns that case.
    return {fr_id for fr_id in touched if fr_id in head_rows}


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
    already present at base is reported as new."""
    base_counts = Counter((r["id"], r["reason"]) for r in base_rejects)
    seen: Counter = Counter()
    findings = []
    for r in head_rejects:
        key = (r["id"], r["reason"])
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


def _row_findings(
    base_row: fr_table_reader.FrTableRow | None,
    head_row: fr_table_reader.FrTableRow,
    base_texts: list[str],
    head_text: str,
) -> list[str]:
    """Hygiene findings for one touched row — judged on the DELTA, not the
    whole row. A row can be "touched" by a Name/Description edit OR by a
    criteria-digest change (the FOLD pattern) without the other half moving;
    judging the untouched half's HEAD content would make this run inherit a
    legacy violation it never wrote (the FOLD pattern `fr-authoring.md` §3
    recommends is exactly "append a criterion, leave everything else"). So:

    * Name (I1) is checked only when the Name cell changed vs base, or the
      row is new (``base_row is None``).
    * Description (I2) is checked only when the Description cell changed vs
      base, or the row is new.
    * Criteria (I7) are checked only for criteria that are NEW at HEAD — a
      criterion whose exact text was already present at base is untouched by
      this run even if the row's OTHER criteria changed around it. ``base_row
      is None`` does NOT mean "no criteria at base": ``_row_map`` filters to
      ACTIVE rows only, so an id restored from `## Removed Requirements` has
      ``base_row is None`` while its `### FR-xx.yy` criteria section was
      present at base all along. ``base_criteria`` is therefore pooled from
      EVERY touched spec's base text (``base_texts``), not just the one the
      row currently lives in at HEAD: an id that moved from one `spec.md` to
      another between base and HEAD keeps its true prior criteria on the
      caller's side (``fr_hygiene``'s ``global_base_rows`` fallback does the
      same for ``base_row`` itself) — pooling only the row's OWN HEAD path
      would make a moved-but-unchanged row's untouched criteria look "new"
      purely because they used to live in a different file (doubt review,
      high). A genuinely new FR's id simply does not appear in any of
      ``base_texts``, so it naturally yields ``[]`` without a special case.
    """
    findings: list[str] = []
    name_changed = base_row is None or base_row.name != head_row.name
    if name_changed and head_row.name:
        name_hits = fr_hygiene_detectors.name_violations(head_row.name)
        if name_hits:
            findings.append(f"name carries {'/'.join(name_hits)}")
    desc_changed = base_row is None or base_row.text != head_row.text
    if desc_changed:
        desc_hits = fr_hygiene_detectors.description_violations(head_row.text)
        if desc_hits:
            findings.append(f"description carries {'/'.join(desc_hits)}")
    base_criteria: set[str] = set()
    for base_text in base_texts:
        base_criteria |= set(fr_criteria.criteria_for(base_text, head_row.id, strict=False))
    head_criteria = fr_criteria.criteria_for(head_text, head_row.id, strict=False)
    new_criteria = [c for c in head_criteria if c not in base_criteria]
    malformed = [c for c in new_criteria if not fr_criterion_shape.is_well_formed_criterion(c)]
    if malformed:
        findings.append(
            f"{len(malformed)} new criterion/criteria not in `(E) Given ... "
            "when ... then ...` shape",
        )
    return findings


__all__ = [
    "_new_duplicate_id_findings",
    "_new_reject_findings",
    "_orphan_anchor_findings",
    "_row_findings",
    "_row_map",
    "_touched_ids",
    "_whole_doc_criteria_digests",
    "_whole_doc_criteria_texts",
]
