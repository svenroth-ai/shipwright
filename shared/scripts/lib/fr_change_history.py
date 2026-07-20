"""Which recorded changes touched a requirement — derived from the event log.

Campaign ``2026-07-18-requirements-catalog``, S7. Decision D4 moved change
history *out* of the requirement text on the grounds that it already exists in
commits, the changelog and ``shipwright_events.jsonl``. S6 executed the removal.
This module is where that claim is made operable: given an FR id, return the
recorded changes that named it, in order.

Three outcomes, never two
-------------------------
The failure this module is built to avoid is the campaign's recurring one — an
empty set read as a positive claim. So :func:`change_history_for_fr` reports a
**status**, not just a list:

``found``
    The log names this requirement; ``changes`` is non-empty. If the id is not a
    live catalog row, this is a RETIRED requirement — still answerable, and
    flagged ``in_catalog=False`` rather than denied.
``no_recorded_changes``
    The requirement is a live catalog row and no recorded change names it. A
    legitimate answer, and a *different* one from "found nothing because you
    typoed".
``unknown_requirement``
    The id names no live row AND appears in no event. Returning an empty list
    here would let a typo read as "this requirement was never touched" — the
    same silent-green shape as FV-1/FV-2 in the golden corpus.

The log is asked before the catalog is judged: see
:func:`change_history_for_fr`.

Existence can itself be unverifiable (no planning tree, or specs that parse to
zero rows). That degrades to ``existence_verified=False``, ``in_catalog`` is not
asserted, and the id is NOT called unknown — the graduated policy
``lib.fr_gates`` already applies to the write-side gate, kept identical here so
the read side cannot be stricter than the gate that admitted the data.

Coverage is partial, and that is data
-------------------------------------
The event log carries an FR link on a minority of ``work_completed`` events, and
run-id-shaped ``adr_id`` values only from 2026-05-16 (earlier events are
identified ``ADR-NNN``). So a short answer for an old requirement means the log
is thin there, not that the requirement was stable. :func:`coverage_summary`
exists so a caller can state that alongside the result instead of implying
completeness it does not have.

The measured gap against the pre-S6 prose — including three run ids the log
cannot account for at all — is pinned in
``integration-tests/test_fr_change_history_recovers_compacted_history.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lib._fr_history_events import read_work_events, sort_key
from lib.tty_sanitize import strip_control_chars

#: ``relation`` values. ``introduced`` is ``new_frs`` — the change that minted
#: the requirement; ``affected`` is ``affected_frs``. Kept distinct because
#: "introduced but never touched since" is a real and reportable state (it is
#: what compliance D1/D3 flag for FR-01.15 today).
RELATION_INTRODUCED = "introduced"
RELATION_AFFECTED = "affected"

STATUS_FOUND = "found"
STATUS_NO_CHANGES = "no_recorded_changes"
STATUS_UNKNOWN_FR = "unknown_requirement"


@dataclass(frozen=True)
class FrChange:
    """One recorded change that named the requirement."""

    event_id: str
    run_id: str
    ts: str
    relation: str
    summary: str
    commit: str
    spec_impact: str

    @property
    def label(self) -> str:
        """The id a reader recognises: the run id, else the event id.

        Pre-2026-05-16 events carry an ``ADR-NNN`` ``adr_id`` rather than a run
        id, and ten events carry neither. Falling back to the event id keeps
        every row addressable instead of rendering a blank cell.
        """
        return self.run_id or self.event_id


@dataclass(frozen=True)
class CoverageSummary:
    """How much of the log can answer this question at all."""

    work_events: int
    fr_linked_events: int

    @property
    def unlinked_events(self) -> int:
        return self.work_events - self.fr_linked_events


@dataclass(frozen=True)
class FrHistory:
    """The answer to "which changes touched this requirement"."""

    fr_id: str
    status: str
    changes: tuple[FrChange, ...]
    existence_verified: bool
    #: False when the id names no LIVE row in the catalog. Only meaningful when
    #: ``existence_verified``. A ``found`` history with ``in_catalog=False`` is a
    #: retired requirement — its history is still answerable.
    in_catalog: bool = True
    #: Unrecoverable bytes seen while reading the log. Surfaced rather than
    #: swallowed: a fragment means some record could not be read, and on an
    #: append-only audit trail that must never be indistinguishable from
    #: "there was nothing there".
    corrupt_fragments: int = 0
    #: Link coverage of the SAME read that produced ``changes``.
    #:
    #: Carried here rather than fetched separately because the log is
    #: append-only and is appended to while it is read — including by the
    #: campaign that produced this module. Two reads can legitimately differ, so
    #: a history from one snapshot presented beside a coverage figure from
    #: another would be an answer no single state of the log ever supported.
    #: One read, one answer.
    #:
    #: NEVER ``None``. It was declared optional while both CLI paths
    #: dereferenced it unconditionally — a type that documented a state the code
    #: could not survive. An empty log yields ``CoverageSummary(0, 0)``, which
    #: renders as "no completed changes are recorded".
    coverage: CoverageSummary = CoverageSummary(0, 0)

    @property
    def found(self) -> bool:
        return self.status == STATUS_FOUND


def _relation_for(event: dict, fr_id: str) -> str | None:
    """``introduced`` / ``affected`` / ``None``. ``new_frs`` wins a tie."""
    for key, relation in (
        ("new_frs", RELATION_INTRODUCED),
        ("affected_frs", RELATION_AFFECTED),
    ):
        value = event.get(key)
        if not isinstance(value, list):
            continue
        if any(isinstance(x, str) and x.strip() == fr_id for x in value):
            return relation
    return None


def _clean(value) -> str:
    """Coerce to ``str``, strip terminal control sequences, collapse whitespace.

    Applied to EVERY field at the boundary, not to the summary at render time.
    The event log is fed partly by imported code-host findings — external data —
    so any field can carry ANSI escapes or newlines. A control sequence in
    ``adr_id`` repaints the terminal just as effectively as one in ``summary``,
    and sanitising at the boundary means no future caller can reintroduce the
    hole by rendering a field the renderer does not currently touch.

    **Whitespace collapse is load-bearing, not tidiness.**
    ``strip_control_chars`` deliberately PRESERVES ``\\n`` and ``\\t`` (it
    targets ANSI/CR), so it alone does not stop a newline in ``adr_id`` from
    rendering as an extra numbered row — the exact forgery the renderer claims
    to prevent. Every field here is single-line by contract, so folding
    whitespace runs to one space closes that without losing information.
    ``summary`` survived only because its renderer happens to ``split()``.
    """
    return " ".join(strip_control_chars(str(value or "")).split())


def _to_change(event: dict, relation: str) -> FrChange:
    return FrChange(
        event_id=_clean(event.get("id")),
        run_id=_clean(event.get("adr_id") or event.get("run_id")),
        ts=_clean(event.get("ts")),
        relation=relation,
        # ``summary`` is the operator-facing sentence; ``description`` is the
        # terser generated one. Prefer the former, fall back rather than render
        # an empty cell.
        summary=_clean(event.get("summary") or event.get("description")),
        commit=_clean(event.get("commit")),
        spec_impact=_clean(event.get("spec_impact")),
    )


def coverage_summary(project_root: Path | str) -> CoverageSummary:
    """How many recorded changes carry an FR link at all, read fresh.

    For callers that want only the figure. A caller that also wants a history
    should read ``FrHistory.coverage`` instead — see the note there on why two
    reads must not be mixed into one answer.
    """
    return _coverage_of(read_work_events(project_root)[0])


def _coverage_of(events: list[dict]) -> CoverageSummary:
    linked = 0
    for e in events:
        for key in ("affected_frs", "new_frs"):
            value = e.get(key)
            if isinstance(value, list) and any(
                isinstance(x, str) and x.strip() for x in value
            ):
                linked += 1
                break
    return CoverageSummary(work_events=len(events), fr_linked_events=linked)


def change_history_for_fr(project_root: Path | str, fr_id: str) -> FrHistory:
    """Recorded changes naming ``fr_id``, oldest first.

    An id that names no requirement AND appears in no event yields
    ``unknown_requirement`` — never an empty ``found``.

    **The log is asked first, and it outranks the catalog.** An id absent from
    the live catalog but present in the log is a RETIRED requirement, and its
    history is exactly what a reader is entitled to ask for; the catalog only
    lists live rows (``collect_requirements_from_planning`` projects
    ``read_active_fr_rows``), so judging on catalog membership alone would
    answer "that requirement does not exist" about a requirement that demonstrably
    did. Typo detection survives untouched — a mistyped id names no row and
    appears in no event, so it still lands in ``unknown_requirement``. Found by
    external plan review (Gemini #3 / GPT #3), which is also why it is tested.
    """
    # `_clean`, not `.strip()`. On a well-formed id the two are identical, so
    # this is behaviour-neutral — but `fr_id` was previously sanitised only by
    # the CLI, which was sound while the renderer was private to that tool.
    # Both now live in `lib/` and read as a usable pair, so
    # `_render_text(change_history_for_fr(root, hostile_id), cov)` would emit a
    # raw escape into the heading with no CLI in the path. The module docstring
    # says sanitising is "applied to EVERY field at the boundary"; the queried
    # id is a field, and this makes that sentence true rather than conventional.
    wanted = _clean(fr_id)
    known, specs_found = _collect_known()(project_root)
    existence_verified = bool(specs_found and known)
    in_catalog = (wanted in known) if existence_verified else True

    events, corrupt = read_work_events(project_root)
    changes: list[FrChange] = []
    for event in sorted(events, key=sort_key):
        relation = _relation_for(event, wanted)
        if relation:
            changes.append(_to_change(event, relation))

    if changes:
        status = STATUS_FOUND
    elif not in_catalog:
        status = STATUS_UNKNOWN_FR
    else:
        status = STATUS_NO_CHANGES

    return FrHistory(
        wanted, status, tuple(changes), existence_verified,
        in_catalog=in_catalog, corrupt_fragments=corrupt,
        coverage=_coverage_of(events),
    )


def _collect_known():
    """Late-bound ``fr_gates.collect_known_fr_ids``.

    Imported at call time, not module scope: ``fr_gates`` reaches the drift
    parsers and the planning walk, and this module is also loaded by the CLI in
    contexts where that chain is heavier than the query needs. Keeping it lazy
    also means a collector that cannot import degrades to "unverifiable"
    (below) instead of taking the whole query down.
    """
    try:
        from lib.fr_gates import collect_known_fr_ids  # noqa: PLC0415

        return collect_known_fr_ids
    except Exception:
        return lambda _root: (frozenset(), False)
