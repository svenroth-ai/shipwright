"""Comparator helpers for the FR-01.02 #5/#10 rollout-transition grace
(``trg-9583d3a8``) — split out of ``_project_gate_extras.py`` at the
300-LOC guideline the moment internal plan review's revisions grew it past
cap (same precedent as every other split in this gate family). Pure
functions only: no git I/O of its own (that lives in
``_project_gate_rollout_snapshot.py``, consumed here via the
``RolloutSnapshot`` interface), so this module stays trivially unit-testable
against hand-built fixtures.

**Per-criterion membership, not whole-row equality (internal plan review,
opus, medium).** An earlier draft compared a row's FULL criteria tuple for
byte-identity between rollout and HEAD — which would forfeit grace for an
untouched, pre-existing violating criterion the moment an UNRELATED later
touch adds a new criterion to the same row (count/order changes, tuple
inequality). :func:`graced_criteria_for_row` instead grants grace per
CRITERION STRING: a violating criterion is graced only if that exact string
(post-parser, never raw file bytes — see module note below) already
appeared in the row's rollout-snapshot criteria, regardless of what else
was added to the row since.

**Identity requires BOTH a row match by id AND a title/body match — refused
when unverifiable (internal plan review, opus, medium).** ``row.name`` (the
FR table's ``Name`` column) is ``""`` for any table that has no such column
at all (``_fr_table_row.FrTableRow.name`` — common in a plain
``| ID | Requirement | Priority | ...``-shaped table), which would make the
title-match guard vacuous — a repurposed FR id would silently inherit its
predecessor's grace whenever neither side had a Name column, exactly the
hole the guard exists to close. :func:`_row_identity_matches` compares the
pair ``(Name, body-text)`` instead of ``Name`` alone, and refuses (no
grace) whenever BOTH are empty on either side — an unverifiable identity
must never default to "matches"."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib import fr_criteria  # noqa: E402
from lib import fr_table_reader  # noqa: E402

from ._project_gate_manifest import _PLANNING_DIRNAME  # noqa: E402
from ._project_gate_rollout_snapshot import RolloutSnapshot  # noqa: E402

_PLANNING_PREFIX = tuple(_PLANNING_DIRNAME.split("/"))


def norm_title(title: str) -> str:
    """Whitespace/case-insensitive comparison — a cosmetic re-wording of the
    same title should not, by itself, forfeit grace, but a genuinely
    different title (the id was repurposed for a new requirement) must."""
    return " ".join(title.split()).casefold()


def _row_identity_matches(rollout_row: object, row: object) -> bool:
    rollout_id = (norm_title(rollout_row.name), norm_title(rollout_row.text))
    head_id = (norm_title(row.name), norm_title(row.text))
    if rollout_id == ("", "") or head_id == ("", ""):
        return False  # unverifiable identity — never default to "matches"
    return rollout_id == head_id


def graced_criteria_for_row(
    rollout: RolloutSnapshot | None, path: str, row: object,
) -> frozenset[str]:
    """The SET of criterion strings ``row`` already carried, verbatim
    (post-parser), in the rollout snapshot — empty when the row's identity
    cannot be matched there (new row, repurposed id, unverifiable identity,
    or no rollout snapshot at all). A caller grants grace to a violating
    criterion iff its exact string is a member of this set."""
    if rollout is None:
        return frozenset()
    rollout_text = rollout.spec_text(path)
    if rollout_text is None:
        return frozenset()
    rollout_rows = {r.id: r for r in fr_table_reader.read_active_fr_rows(rollout_text)}
    rollout_row = rollout_rows.get(row.id)
    if rollout_row is None or not _row_identity_matches(rollout_row, row):
        return frozenset()
    # fr_criteria.py: legacy label-paragraph exception
    return frozenset(fr_criteria.criteria_for(rollout_text, row.id, strict=False))


def split_name_from_path(path: str) -> str | None:
    """Recover the split NAME from a ``_read_spec_texts``-produced display
    path (``.shipwright/planning/<name>/spec.md``, OS-separator-agnostic)."""
    parts = tuple(path.replace("\\", "/").split("/"))
    if len(parts) >= 3 and parts[0] == _PLANNING_PREFIX[0] and parts[1] == _PLANNING_PREFIX[1]:
        return parts[2]
    return None


def split_predates_rollout(
    rollout: RolloutSnapshot | None, path: str, name: str | None,
) -> bool:
    """True when ``name`` was already DECLARED (present in the project's own
    manifest) at the rollout instant, with zero active FR rows there too —
    or not yet even written, vacuously empty. Requires manifest
    DECLARATION, never merely "some file happens to sit at this path"
    (internal plan review, opus, HIGH): a split whose name was never
    declared at rollout gets no grace regardless of what its ``spec.md``
    path happens to contain there — otherwise a newly-declared split that
    happens to reuse an old, unrelated, already-empty path would inherit a
    stranger's grace, inverting the fail-closed direction this whole
    mechanism depends on."""
    if rollout is None or name is None:
        return False
    if name not in rollout.declared_split_names():
        return False
    rollout_text = rollout.spec_text(path)
    if rollout_text is None:
        return True  # declared at rollout, spec.md not yet written — vacuously empty
    return not fr_table_reader.read_active_fr_rows(rollout_text)


__all__ = [
    "norm_title",
    "graced_criteria_for_row",
    "split_name_from_path",
    "split_predates_rollout",
]
