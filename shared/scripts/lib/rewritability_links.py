"""M7 (Rewritability): does a requirement's recorded history carry a linked rationale?

Campaign ``req3-04c-ac-identity-wave2``, sub-iterate p3.8. The campaign's own
design spec (``Spec/design/2026-07-22-req3-campaign-SPEC.md``, mechanism M7)
states the goal in prose: "Requirement -> *Warum* verlinkt (ADR/Rationale),
nicht nur *Was*" -- can a requirement be REWRITTEN with confidence, because
the reason it exists is recorded somewhere a reader can find, not only its
current wording?

**Interpretation adopted here, stated explicitly because the spec leaves it
open** ("Prosa-Regel, unklar ob real" -- "pruefen, nicht annehmen"). Verified
first, not assumed: neither ``shared/schemas/decision_drop.schema.json`` nor
``shared/scripts/lib/requirement_model.py`` carries any field that links an
FR id to a decision drop / ADR in either direction. The linkage this
mechanism is meant to "check for real" does not exist as a first-class field
anywhere in the codebase today -- that absence is itself the M7 finding this
module was built to measure, not a gap this module tries to close by
inventing a new schema field (out of scope for an advisory-only check, and
the campaign's own D7 rules out a judgement-based / LLM substitute).

The nearest ACTUAL, mechanical linkage already in the codebase is transitive,
through the run that produced a change:

1. ``shared/scripts/lib/fr_change_history.py`` already answers "which
   ``work_completed`` events named this FR" (via their ``affected_frs`` /
   ``new_frs`` lists), and each such event carries the run's own ``adr_id``
   (== its ``run_id``, ADR-059).
2. A decision drop -- the record ADR-029's F3 mandates for a run's *why* --
   is filed under ``.shipwright/agent_docs/decision-drops/<run_id>_NNN.json``
   and, once ``/shipwright-changelog`` aggregates it, folded into
   ``decision_log.md`` with a ``**Run-ID:**`` bullet naming the same run_id.

So: a requirement counts as **linked** here if ANY run recorded as having
changed it (step 1) also produced a decision drop or an aggregated ADR entry
(step 2) -- the same run_id appearing on both sides is the whole signal.
This is a PROXY, not a guarantee that the ADR's prose actually explains THIS
FR (a run can touch several FRs and write one ADR that discusses only one of
them) -- named as a limitation here and in the Group I finding text, not
glossed over.

**Three outcomes, never two** -- the same discipline
``lib/fr_change_history.py`` already applies to "which changes touched this
requirement": a requirement with recorded changes, none of them
rationale-linked, is ``unlinked`` -- a real, if approximate, answer. A
requirement with NO recorded changes at all is ``could_not_determine`` -- the
event log's FR-link coverage is a MINORITY of events (see that module's own
docstring), so "no recorded change" must never be silently folded into
"confirmed unlinked": the two make different claims, and this campaign has
re-learned three times over (the p3.6/p3.7 review rounds) that a silent
exclusion is worse than a loud one.

**Coverage gap, named rather than hidden:** the ``**Run-ID:**`` bullet only
exists on ADRs written from 2026-05-16 onward (the same cutoff
``fr_change_history`` documents for ``adr_id``) -- an older ADR's rationale
is real but invisible to this scan, and would read as ``unlinked``.

**Advisory only, per M7's own spec note** ("M7 bleibt advisory, kein
Hart-Gate" -- an ADR requirement for every requirement would be bloat). This
module only classifies; it never raises a verdict. ``group_i.py``'s I9 is the
sole caller, and always renders ``pass``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from lib._fr_history_events import EventLogUnreadable, read_work_events
from lib.decision_drops_index import drop_dir, pending_drops

#: Duplicated from ``lib/decision_log_index.py`` (same constant, read-only
#: use here) rather than imported, to avoid pulling in that module's
#: write-side machinery (``file_lock``, ``durable_atomic_write``) for a
#: reference that only ever reads the file.
DECISION_LOG_RELPATH = ".shipwright/agent_docs/decision_log.md"

#: Anchored to the aggregator's own bullet shape (`- **Run-ID:** <value>`,
#: line-start, optional leading whitespace) rather than matching
#: ``**Run-ID:**`` anywhere in the file. External code review (two
#: independent providers, openai medium + glm low) found the unanchored
#: form would read an unrelated ADR's PROSE or a quoted example inside a
#: fenced code block (e.g. one design doc's own commit-message excerpt) as
#: a real rationale record — a false positive that silences exactly the
#: "unlinked" signal I9 exists to report. `re.MULTILINE` so `^`/`$` match
#: per line in the whole file, not just start/end of the string.
_RUN_ID_BULLET_RE = re.compile(r"^\s*-\s*\*\*Run-ID:\*\*\s*(\S+)\s*$", re.MULTILINE)


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _pending_drop_run_ids(dd: Path) -> set[str]:
    """Run ids named by pending (not-yet-aggregated) decision-drop files
    that carry non-blank rationale content.

    Delegates directory scanning to ``decision_drops_index.pending_drops``
    (promoted to public for this caller, external plan review finding —
    a fourth independent copy of the same scan was rejected in favor of
    reusing the existing one). ``pending_drops`` already tolerates a
    malformed individual file; the ``try`` here additionally guards against
    ``dd.iterdir()`` itself raising (e.g. a permission-denied directory),
    which neither that function nor a bare ``Path.is_dir()``/``is_file()``
    check catches — this check must never crash the advisory audit over a
    filesystem fault on a directory it does not own.

    A drop with an empty ``decision`` field does not count (external plan
    review, openai, medium): presence of a file is not evidence of a real
    rationale if the field the schema requires is blank, e.g. a hand-edited
    or partially-written drop that bypassed ``write_decision_drop.py``'s own
    validation.
    """
    out: set[str] = set()
    try:
        drops = pending_drops(dd)
    except OSError:
        return out
    for _name, payload in drops:
        rid = _clean(payload.get("run_id"))
        decision_text = _clean(payload.get("decision"))
        if rid and decision_text:
            out.add(rid)
    return out


def rationale_run_ids(project_root: Path | str) -> frozenset[str]:
    """Run ids with a recorded rationale: a pending decision-drop, or an
    aggregated ``decision_log.md`` ADR entry naming that run_id.
    """
    root = Path(project_root)
    ids = _pending_drop_run_ids(drop_dir(root))
    log_path = root / DECISION_LOG_RELPATH
    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        text = ""
    ids.update(m.strip() for m in _RUN_ID_BULLET_RE.findall(text) if m.strip())
    return frozenset(ids)


@dataclass(frozen=True)
class RewritabilityScan:
    """Per-FR verdict, in the three-outcome shape (see module docstring)."""

    linked: tuple[str, ...]
    unlinked: tuple[str, ...]
    could_not_determine: tuple[str, ...]
    #: Unreadable event-log fragments seen while reading -- surfaced, never
    #: swallowed (same discipline as ``fr_change_history.FrHistory``).
    corrupt_fragments: int = 0


def scan_fr_rationale_links(
    project_root: Path | str, fr_ids: Iterable[str],
) -> RewritabilityScan:
    """Classify every id in ``fr_ids`` as linked / unlinked / could_not_determine.

    One pass over the event log for every id, rather than
    ``fr_change_history.change_history_for_fr`` per id (which re-reads and
    re-sorts the whole log on every call): Group I calls this once per audit
    run over every live FR in the catalog, and the log is append-only and can
    run to thousands of records.

    Raises
    ------
    :class:`lib._fr_history_events.EventLogUnreadable`
        Propagated, not swallowed -- same contract as
        ``fr_change_history.change_history_for_fr``. A caller that turned
        this into an empty scan would report "every requirement is linked"
        or "every requirement is unlinked" from a log it never actually read.
    """
    events, corrupt = read_work_events(project_root)
    # `touched_frs` records every FR named in ANY event's `affected_frs`/
    # `new_frs`, regardless of whether that event's own run_id was usable.
    # `fr_run_ids` records only the (FR, usable run_id) pairs. Kept SEPARATE
    # deliberately (external code review, glm, low): an event that names an
    # FR but carries no `adr_id`/`run_id` used to be skipped entirely, so
    # that FR fell into `could_not_determine` ("no recorded change") instead
    # of `unlinked` ("a change was recorded, but it cannot be tied to any
    # rationale") — silently narrowing the module's own "recorded changes"
    # set and conflating two outcomes the three-outcome discipline exists to
    # keep apart.
    touched_frs: set[str] = set()
    fr_run_ids: dict[str, set[str]] = {}
    for event in events:
        run_id = _clean(event.get("adr_id") or event.get("run_id"))
        for key in ("affected_frs", "new_frs"):
            value = event.get(key)
            if not isinstance(value, list):
                continue
            for fr in value:
                if not (isinstance(fr, str) and fr.strip()):
                    continue
                fr_id = fr.strip()
                touched_frs.add(fr_id)
                if run_id:
                    fr_run_ids.setdefault(fr_id, set()).add(run_id)

    rationale_ids = rationale_run_ids(project_root)

    linked: set[str] = set()
    unlinked: set[str] = set()
    unknown: set[str] = set()
    for fr_id in fr_ids:
        if fr_id not in touched_frs:
            unknown.add(fr_id)
        elif fr_run_ids.get(fr_id, set()) & rationale_ids:
            linked.add(fr_id)
        else:
            unlinked.add(fr_id)

    return RewritabilityScan(
        linked=tuple(sorted(linked)),
        unlinked=tuple(sorted(unlinked)),
        could_not_determine=tuple(sorted(unknown)),
        corrupt_fragments=corrupt,
    )


__all__ = [
    "EventLogUnreadable",
    "RewritabilityScan",
    "rationale_run_ids",
    "scan_fr_rationale_links",
]
