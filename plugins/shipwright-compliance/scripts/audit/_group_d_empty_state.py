"""WHICH empty-requirement state produced zero rows (requirements-catalog S6).

Group D sources its requirement set from ``collect_requirements_from_planning``,
which returns a plain list. An empty list conflates several materially different
situations, and before S6 that did not matter: D1, D2 and D4 all answered *"no FR
table rows in any spec.md"* and all **skipped**, so the message was inert.

S6 made D2 FAIL when the set is empty and events still reference requirements.
That is correct — every such reference is unresolvable — but it turned an inert
message into an accusation, and an accusation has to name the right thing. The
difference that matters to an operator is between *"you have no requirements"*
and *"your requirements exist but the table could not be read"*: the second is a
table-shape repair, and reporting it as a stale reference points away from the
defect while naming the very ids the project has.

**This module owns no classification.** ``group_i_scan.SpecScan`` already decides
which of six no-rows states a repo is in, from raw parse facts in a fixed
precedence, and already carries the wording for each — including two states
(``rows_too_narrow``, ``all_rows_retired``) that exist precisely because an
earlier cut reported the wrong cause. State and sentence are READ from there.

That is not a stylistic preference, and this module learned it the hard way. Its
first version branched on raw ``any_spec`` / ``rejects`` while this very
docstring warned against doing so, and it answered *"spec.md present but its
requirements table holds no rows"* for a spec whose rows are all RETIRED — a file
that plainly holds rows, which had been read successfully, reported to the
operator as a non-zero exit. Group I had classified that case correctly the whole
time as ``all_rows_retired``. A second answer to a question that already has one
does not stay agreeing with it.

Fail-soft: any error resolving the state degrades to the historical wording
rather than crashing the audit. A worse message is not worth a red group — and
the degradation is pinned by a test, so it cannot become a silent default.
"""

from __future__ import annotations

from pathlib import Path

#: The pre-S6 wording, kept verbatim as the fallback so a resolution failure is a
#: loss of PRECISION, never a change of meaning. D1 and D4 answer with this
#: literal on their (unchanged, non-blocking) skip paths and import it from here
#: rather than restating it, so the three cannot drift apart under a one-sided
#: edit — the same reason ``LEGACY_SOURCES`` has a single home.
GENERIC = "no FR table rows in any spec.md"


def describe_empty_requirements(project_root: Path) -> str:
    """One line naming which no-rows state the project is in.

    Delegates to ``SpecScan.detail``: the S5-owned sentence for the state
    ``SpecScan.state`` resolved, including its mixed-cause variants and its rule
    about quoting only the ids that actually caused the state.
    """
    try:
        from scripts.audit.group_i import scan_specs
        return scan_specs(project_root).detail or GENERIC
    except Exception:  # noqa: BLE001 — precision is optional, the audit is not
        return GENERIC


def empty_requirements_skip(project_root: Path, severity: str = "MEDIUM"):
    """The Group-D skip tuple for 'no requirements', with the state named."""
    return "skip", severity, describe_empty_requirements(project_root), []


def stale_ref_report(stale: dict[str, int], spec_ids: set[str],
                     project_root: Path) -> tuple[str, list[str]]:
    """``(detail, evidence)`` for D2's fail branch.

    Splits the two causes apart. With requirements present, an unresolvable
    reference IS a stale reference and the historical wording is right. With no
    live requirement readable, the same references are unresolvable for a
    different reason, and saying "not in current spec" would assert something
    about a spec that was never successfully read.
    """
    items = sorted(stale.items(), key=lambda kv: (-kv[1], kv[0]))
    head = ", ".join(f"{k} (×{v})" for k, v in items[:3])
    if len(items) > 3:
        head += f", … (+{len(items) - 3})"
    evidence = [f"{k}: {v} event(s)" for k, v in items]
    if spec_ids:
        return f"events reference FR-IDs not in current spec — {head}", evidence
    return (f"no live requirement could be read, so every event FR-ref is "
            f"unresolvable — {describe_empty_requirements(project_root)}; "
            f"refs: {head}"), evidence


__all__ = ["GENERIC", "describe_empty_requirements", "empty_requirements_skip",
           "stale_ref_report"]
