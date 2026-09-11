"""Four /shipwright-project Step-8 gates the AC-evidence ledger walk found
nowhere in code
(``.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md``,
FR-01.02, sub-iterate ``e2-checks-project-elicitation``). Mirrors the shape of
``plan_gate_extras.py`` / ``design_gate_extras.py``: pure ``GateResult``-
returning functions over already-read spec text, composed by
``project_checks.py`` so this module does no filesystem I/O of its own beyond
``starting_guidance_present`` (which, like ``design_gate_extras.uploads_preserved``,
needs the project root directly).

* :func:`basis_forbids_assumed` — **#4 + #15, merged 2026-09-11.** #4's own
  text ("Reworded 2026-07-24 to the greenfield teeth ... we banned
  'assumed' for greenfield") and #15's later retro-pass amendment
  ("the basis stays available but only together with what would settle
  it") name a real tension the ledger itself flags as unresolved
  ("Both scenarios hit a contradiction the phase carries with itself").
  Rather than build a semantic "does this AC actually name a settlement"
  oracle (no deterministic check for aboutness exists — the campaign's own
  abort condition), this keeps the simpler, already-operator-decided,
  already-shipped-at-the-grill-trace-layer rule (P4.2's
  ``check_greenfield_assumed`` — "no exceptions in this surface"): a
  greenfield spec's ``Basis`` column may never read a bare ``assumed``.
  Extending the SAME absolute ban to the FR-row layer, not inventing a
  second rule, is the buildable half of both #4 and #15 — see the ledger
  entry for the full resolution note.
* :func:`criteria_free_of_implementation_detail` — **#5** "No
  symbol/path/ADR/verb in the sentence." ``fr_hygiene_detectors.violations``
  (I1) already exists but is applied only to the FR Name/Description
  (``group_i`` advisory, ``check_fr_hygiene_on_touched_rows`` for
  /shipwright-iterate's own touched rows) — never to the acceptance
  CRITERIA text, and never as a block on /shipwright-project's own Step 8.
  Reuses the identical detector against every active FR's criteria.
* :func:`no_empty_split` — **#10** "Divided into cohesive parts, or
  single-unit." ``split-heuristics.md`` states the rule; nothing checked
  that a declared split actually carries at least one requirement. A split
  with zero active FR rows is not a cohesive part of anything.
* :func:`starting_guidance_present` — **#11** "Starting guidance exists."
  Step 7 writes CLAUDE.md + the agent_docs trio; Step 8's own prose lists
  their existence as a manual verification step, never code-enforced, and
  never checked for non-empty content either.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib import fr_basis  # noqa: E402
from lib import fr_criteria  # noqa: E402
from lib import fr_hygiene_detectors  # noqa: E402
from lib import fr_table_reader  # noqa: E402

__all__ = [
    "GateResult",
    "basis_forbids_assumed",
    "criteria_free_of_implementation_detail",
    "no_empty_split",
    "starting_guidance_present",
]


@dataclass(frozen=True)
class GateResult:
    ok: bool
    detail: str


# --------------------------------------------------------------------------- #
# #4 + #15 — Basis forbids a bare 'assumed' in a greenfield spec
# --------------------------------------------------------------------------- #


def basis_forbids_assumed(spec_texts: dict[str, str]) -> GateResult:
    """``spec_texts`` maps a display path (for the failure message) to the
    already-read ``spec.md`` body. Only rows whose Basis cell came from a
    NAMED ``Basis`` column are scored (mirrors ``fr_basis``'s own contract —
    a legacy ``Source`` cell never claimed to be a basis).

    Catches both a bare ``assumed`` cell (``fr_basis`` kind ``known``) and a
    QUALIFIED one like ``assumed: nobody could answer`` (kind ``malformed``
    — ``fr_basis`` rejects the qualifier as a parse error, not as a basis
    value, so its own vocabulary check alone doesn't ban it). External code
    review (e2-checks-project-elicitation, round 3, low, GLM): the ban is
    "no exceptions" — a malformed-but-recognizably-assumed cell is exactly
    the qualifier-smuggling loophole that wording exists to close, not a
    different problem this gate can ignore."""
    hits: list[str] = []
    for path, text in spec_texts.items():
        for row in fr_table_reader.read_active_fr_rows(text):
            if not row.basis_from_named_col:
                continue
            verdict = fr_basis.classify(row.basis_cell)
            is_bare_assumed = verdict.kind == "known" and verdict.value == "assumed"
            is_qualified_assumed = (
                verdict.kind == "malformed"
                and verdict.value.strip().lower().startswith("assumed")
            )
            if is_bare_assumed or is_qualified_assumed:
                hits.append(f"{path}:{row.id}")
    if hits:
        return GateResult(
            False,
            f"Basis='assumed' in a greenfield /shipwright-project spec (banned, "
            f"no exceptions — matches P4.2's grill-trace-layer rule): {hits}",
        )
    return GateResult(True, "no Basis cell reads 'assumed' across every spec")


# --------------------------------------------------------------------------- #
# #5 — acceptance criteria free of implementation detail
# --------------------------------------------------------------------------- #


def criteria_free_of_implementation_detail(spec_texts: dict[str, str]) -> GateResult:
    hits: list[str] = []
    for path, text in spec_texts.items():
        for row in fr_table_reader.read_active_fr_rows(text):
            for criterion in fr_criteria.criteria_for(text, row.id, strict=False):
                found = fr_hygiene_detectors.violations(criterion)
                if found:
                    hits.append(f"{path}:{row.id} ({'/'.join(found)})")
    if hits:
        shown = hits[:5]
        suffix = f" (+{len(hits) - 5} more)" if len(hits) > 5 else ""
        return GateResult(
            False,
            f"{len(hits)} acceptance criterion/criteria carry implementation "
            f"detail: {'; '.join(shown)}{suffix}",
        )
    return GateResult(
        True,
        "no acceptance criterion carries a code symbol, file path, ADR "
        "number, iterate slug, or HTTP verb",
    )


# --------------------------------------------------------------------------- #
# #10 — no split with zero active requirements
# --------------------------------------------------------------------------- #


def no_empty_split(spec_texts: dict[str, str]) -> GateResult:
    empty = sorted(
        path for path, text in spec_texts.items()
        if not fr_table_reader.read_active_fr_rows(text)
    )
    if empty:
        return GateResult(
            False,
            f"split(s) with zero active FR rows — not a cohesive part of "
            f"anything: {empty}",
        )
    return GateResult(
        True, f"{len(spec_texts)} split(s), each with at least one active FR row",
    )


# --------------------------------------------------------------------------- #
# #11 — starting guidance present and non-empty
# --------------------------------------------------------------------------- #

#: The files Step 7 (project-scaffolding.md) writes for Full Application
#: scope. Relative to project_root.
_STARTING_GUIDANCE_FILES = (
    "CLAUDE.md",
    ".shipwright/agent_docs/architecture.md",
    ".shipwright/agent_docs/decision_log.md",
    ".shipwright/agent_docs/conventions.md",
)


def starting_guidance_present(project_root: Path) -> GateResult:
    """Extension scope never writes these (they already exist) — the caller
    is responsible for skipping this check on that scope, exactly like
    Step 8's own "Full Application only" annotations on items 3 and 4."""
    candidates = [project_root / rel for rel in _STARTING_GUIDANCE_FILES]
    missing = [str(p) for p in candidates if not p.exists()]
    if missing:
        return GateResult(False, f"starting-guidance file(s) missing: {missing}")
    empty: list[str] = []
    for p in candidates:
        try:
            content = p.read_text(encoding="utf-8")
        except OSError as exc:
            return GateResult(False, f"{p} exists but could not be read: {exc}")
        if not content.strip():
            empty.append(str(p))
    if empty:
        return GateResult(False, f"starting-guidance file(s) exist but are empty: {empty}")
    return GateResult(
        True, f"{len(candidates)} starting-guidance file(s) present and non-empty",
    )
