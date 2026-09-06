"""Pure per-FR touched/clean judgment for the FR-row hygiene gate
(iterate-2026-09-06-fr-hygiene-touched-rows).

Split out of ``fr_hygiene.py`` (which crossed the 300-line guideline): this
half holds the row/criteria comparison logic — deciding WHICH FR ids a run
touched and WHETHER what it touched is clean — while ``fr_hygiene.py`` keeps
the git-facing orchestration (resolving the merge-base, reading either side,
assembling the ``CheckResult``). The structural-anomaly detectors (orphan
criteria anchors, duplicate ids, unparseable rows — defects that make a row
INVISIBLE to the comparison below rather than judging what it says) live in
the sibling ``_fr_hygiene_anomalies.py``, split out in turn once this module
itself crossed 300 lines. No I/O here beyond the parsers it calls; every
function takes already-read text.
"""

from __future__ import annotations

import hashlib
import sys
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
    narrower than its own header) — see
    ``_fr_hygiene_anomalies._new_reject_findings``."""
    return {
        row.id: row
        for row in fr_table_reader.read_fr_rows(text, rejects=rejects)
        if not row.removed
    }


def _whole_doc_criteria_texts(text: str) -> dict[str, list[str]]:
    """FR id → every criterion text pooled for that requirement, scanned over
    the WHOLE document — the same scope :func:`_row_findings` uses via
    ``fr_criteria.criteria_for``. Shared by :func:`_whole_doc_criteria_digests`
    (hashes this for change-detection) and
    ``_fr_hygiene_anomalies._orphan_anchor_findings`` (needs the raw texts,
    not a digest, to tell a real criterion from an empty anchor)."""
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
    "_row_findings",
    "_row_map",
    "_touched_ids",
    "_whole_doc_criteria_digests",
    "_whole_doc_criteria_texts",
]
