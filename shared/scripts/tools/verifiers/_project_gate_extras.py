"""Four /shipwright-project Step-8 gates the AC-evidence ledger walk found
nowhere in code
(``.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md``,
FR-01.02, sub-iterate ``e2-checks-project-elicitation``). Mirrors the shape of
``plan_gate_extras.py`` / ``design_gate_extras.py``: pure ``GateResult``-
returning functions over already-read spec text, composed by
``project_checks.py`` so this module does no filesystem I/O of its own beyond
``starting_guidance_present`` (which, like ``design_gate_extras.uploads_preserved``,
needs the project root directly).

This module holds **#4/#15 and #11** — :func:`basis_forbids_assumed` and
:func:`starting_guidance_present`, neither of which are rollout-transition-
aware (see their own docstrings for why each already has a different,
subject-matter-specific carve-out). **#5 and #10** —
:func:`criteria_free_of_implementation_detail` and :func:`no_empty_split`,
both rollout-transition-aware since 2026-09-12 (``trg-9583d3a8``) — split out
into the sibling ``_project_gate_extras_rollout.py`` the moment internal plan
review's revisions grew this file past the 300-LOC guideline (same precedent
as every other split in this gate family).

* :func:`basis_forbids_assumed` — **#4 + #15, revised 2026-09-11 (Stage-1
  spec-review REJECT on PR #729).** The first cut copied P4.2's
  grill-trace-layer "no exceptions" ban wholesale to the FR-row layer — an
  outright ban on Basis=``assumed``. That is stricter than the
  already-operator-decided ceiling FR-01.02 #4 itself records: "only where
  the answer could not be obtained", not "never". ``fr-authoring.md``
  §4a, ``requirement-elicitation.md`` §8 (its three-row availability
  table — availability is context-dependent, e.g. ``/shipwright-adopt``
  legitimately has nobody to ask) and ``spec-generation.md``'s worked
  FR-01.05 example are unanimous and deliberate: ``assumed`` is legal,
  ``assumed`` is never BARE — it is available only paired with what would
  settle it, and that settlement belongs in an ACCEPTANCE CRITERION on the
  same row, never smuggled into the Basis cell itself. So the gate keeps
  its qualifier-smuggling half (``assumed: <reason>`` stays a malformed,
  banned cell — the settlement is in the wrong place) and replaces the
  outright ban on a bare ``assumed`` cell with the FORM obligation the
  docs actually state: the row must carry at least one acceptance
  criterion. Whether that criterion actually NAMES a settlement (vs. a
  vapid "someone should check this") is a judgement call about
  reachability this module's own docstring already rules out building an
  oracle for (no deterministic "aboutness" check exists) — checking for
  *some* recorded criterion is as far as a mechanical gate can honestly
  go, and is documented as such rather than silently pretending to verify
  content.
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
from lib import fr_table_reader  # noqa: E402

__all__ = [
    "GateResult",
    "basis_forbids_assumed",
    "starting_guidance_present",
]


@dataclass(frozen=True)
class GateResult:
    ok: bool
    detail: str
    #: Set only by a gate that grants rollout-transition grace (see
    #: ``_project_gate_extras_rollout.py``, 2026-09-12) to a
    #: hit-but-fully-graced result: the literal string ``"warning"`` (never
    #: ``common.Severity`` — kept import-light, matching this module's
    #: existing zero-``common``-import shape). The wiring layer
    #: (`_project_gate_wiring.py`) forwards it onto the `CheckResult` it
    #: builds. ``None`` (the default) means "let the caller use its own
    #: default severity", unaffected for every other gate.
    severity: str | None = None
    #: Companion to ``severity`` — set alongside it so a fully-graced result
    #: is visible but never promoted to a hard failure under ``--strict``,
    #: the same ``strict_exempt`` contract `layer_coverage_binding.py`'s own
    #: advisory branch already uses.
    strict_exempt: bool = False


# --------------------------------------------------------------------------- #
# #4 + #15 — Basis forbids a bare 'assumed' in a greenfield spec
# --------------------------------------------------------------------------- #


def basis_forbids_assumed(spec_texts: dict[str, str]) -> GateResult:
    """``spec_texts`` maps a display path (for the failure message) to the
    already-read ``spec.md`` body. Only rows whose Basis cell came from a
    NAMED ``Basis`` column are scored (mirrors ``fr_basis``'s own contract —
    a legacy ``Source`` cell never claimed to be a basis).

    Two independent failure shapes, not one ban:

    1. A QUALIFIED ``assumed`` cell (``fr_basis`` kind ``malformed``, e.g.
       ``assumed: nobody could answer``) is always a hit, regardless of
       criteria. ``fr-authoring.md`` §4a: the Basis cell takes one bare
       vocabulary value; a settlement written INTO the cell is smuggled
       into the wrong place even when a real settlement exists elsewhere —
       this is what closes the qualifier-smuggling loophole (external code
       review, e2-checks-project-elicitation round 3, low, GLM).
    2. A BARE ``assumed`` cell (``fr_basis`` kind ``known``) is a hit ONLY
       when the row carries zero acceptance criteria. ``assumed`` is legal
       — ``fr-authoring.md`` §4a / ``requirement-elicitation.md`` §8 — but
       "never bare": it must be paired with a criterion naming what would
       settle it. This gate cannot judge whether a given criterion truly
       names a settlement (no deterministic "aboutness" oracle exists, per
       this module's own docstring) or is a vapid "someone should check
       this" — that is a judgement about reachability, not a shape a
       regex can see. Checking for the PRESENCE of a criterion is the
       honest mechanical ceiling; it does not, and must not, pretend to
       verify the criterion's content."""
    hits: list[str] = []
    for path, text in spec_texts.items():
        for row in fr_table_reader.read_active_fr_rows(text):
            if not row.basis_from_named_col:
                continue
            verdict = fr_basis.classify(row.basis_cell)
            is_bare_assumed = verdict.kind == "known" and verdict.value == "assumed"
            # Stage-2 code review (round 3, PR #729, low): a raw
            # `.startswith("assumed")` on `verdict.value` also matches an
            # unrelated out-of-vocabulary typo with no word boundary (e.g.
            # a glued "assumedallowed"), which `fr_basis` classifies under
            # its OTHER `malformed` branch ("not in the vocabulary") — not
            # the qualifier-smuggling one. `verdict.note` textually names
            # which branch fired (`` `assumed` takes no qualifier... ``
            # only for the true qualifier case — `reason` is always "" on
            # both `malformed` branches, it is populated only for `other`),
            # so checking `note` instead of `value` cannot cross the two.
            is_qualified_assumed = (
                verdict.kind == "malformed"
                and verdict.note.startswith("`assumed`")
            )
            if is_qualified_assumed:
                hits.append(f"{path}:{row.id} (settlement smuggled into the Basis cell)")
            elif is_bare_assumed and not fr_criteria.has_criteria(
                text, row.id, strict=False,  # fr_criteria.py: legacy label-paragraph exception
            ):
                hits.append(f"{path}:{row.id} (assumed with no acceptance criterion)")
    if hits:
        return GateResult(
            False,
            f"Basis='assumed' without a named settlement in a greenfield "
            f"/shipwright-project spec: {hits}",
        )
    return GateResult(
        True,
        "every 'assumed' Basis cell (if any) is paired with an acceptance "
        "criterion, and none smuggles its settlement into the Basis cell itself",
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
    Step 8's own "Full Application only" annotations on items 3 and 4.

    Tier-3 review (PR #729, round 9) — the same class of finding round 7
    fixed in ``_read_spec_texts`` (``_project_gate_manifest.py``) applies
    here too: this gate ran against untrusted PR content in CI, and its
    fixed, well-known relative paths made checking ``exists()``/calling
    ``read_text()`` without resolving them a symlink escape — a hostile PR
    could commit ``CLAUDE.md`` (or an agent-doc file) as a symlink
    resolving outside the project root, satisfying "present and
    non-empty" while reading an arbitrary host file. Each candidate is now
    resolved and checked against the resolved project root before being
    read; an escape is treated the same as "missing"."""
    resolved_root = project_root.resolve()
    candidates = [project_root / rel for rel in _STARTING_GUIDANCE_FILES]
    missing: list[str] = []
    escaped: list[str] = []
    readable: list[Path] = []
    for p in candidates:
        try:
            resolved = p.resolve(strict=False)
        except OSError:
            missing.append(str(p))
            continue
        if resolved != resolved_root and resolved_root not in resolved.parents:
            escaped.append(str(p))
            continue
        if not p.exists():
            missing.append(str(p))
            continue
        readable.append(p)
    if escaped:
        return GateResult(
            False, f"starting-guidance file(s) resolve outside the project root: {escaped}",
        )
    if missing:
        return GateResult(False, f"starting-guidance file(s) missing: {missing}")
    empty: list[str] = []
    for p in readable:
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
