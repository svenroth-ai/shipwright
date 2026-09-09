"""Pure per-requirement evaluator for the ``Layers`` promotion mechanism (P3.5,
campaign req3-04c-ac-identity-wave2, SPEC D5/D12). Full design rationale:
``.shipwright/planning/adr/iterate-2026-09-08-p3-5-promote-layers-per-fr-layers-promotion-mechanism.md``.

**The predicate, decidable per requirement, never in a sweep:** this FR has
evidence of a highest observable layer, that layer (and everything the binding
already required) ran executed-passing, and nothing about the evidence is
ambiguous. Where it holds, :func:`evaluate_fr` returns a ``promote`` action;
elsewhere it returns ``skip`` (not yet eligible — the common case) or
``escalate`` (one of the three named undecidable cases).

**Reuses P3.3's own eligibility contract** (``_layer_coverage_binding``'s
``"ok"`` verdict) via a DIRECT import, not a kept-in-step copy — both modules
live under the SAME ``shared/scripts`` tree, so no cross-tree boundary bars
it (``lib/phase_quality`` already imports ``tools.verifiers`` this same way).
``LAYER_RANK``/``highest_ok_layer`` below are re-exports, not an independent
copy — a canonical layer added to ``LAYERS`` can no longer silently diverge
the promoter from the gate it promotes into.

**FR-level only (D12).** The manifest's ``acs`` breakdown is deliberately NOT
consulted: D12 settles that FR-level ``required_layers`` is the coarse gate,
AC-level an ADDITIONAL index on top, never a precondition for it.

**Never writes anything.** The CLI is the only writer. An FR already
``already_explicit`` — or already settled by a ledger entry — is never
revisited: no code path here ever narrows ``required_layers`` or reinstates
the ``(inferred)`` marker, which is what makes "cannot silently demote" true
by construction, not by a runtime check.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

try:  # Package context (shared/tests: `shared/scripts` on sys.path).
    from .fr_layer_cell_writer import _LAYER_TOKEN_RE
    from .layer_promotion_ledger import fingerprint_drifted
except ImportError:  # Loaded by file path.
    from fr_layer_cell_writer import _LAYER_TOKEN_RE  # type: ignore
    from layer_promotion_ledger import fingerprint_drifted  # type: ignore

from tools.verifiers._layer_coverage_binding import (  # noqa: E402
    _highest_ok_layer as _shared_highest_ok_layer,
)
from tools.verifiers._layer_coverage_binding import _LAYER_RANK as LAYER_RANK  # noqa: E402

#: The three — and only three — undecidable cases the sub-iterate spec names.
REASON_LAYER_UNDETERMINABLE = "layer_undeterminable"
REASON_BOUND_TEST_ABSENT = "bound_test_absent_from_ci"
REASON_CONTRADICTS_DECISION = "contradicts_recorded_decision"

#: Non-escalating outcomes, named so a caller need not string-compare prose.
SKIP_ALREADY_EXPLICIT = "already_explicit"
SKIP_ALREADY_EXPLICIT_CONSISTENT = "already_explicit_consistent"
SKIP_DEMOTED_CONSISTENT = "demoted_consistent"
SKIP_NO_EVIDENCE_YET = "no_evidence_yet"
SKIP_EXISTING_REQUIRED_NOT_VERIFIED = "existing_required_layer_not_verified"
SKIP_LIVE_CELL_HAS_RESIDUAL_TEXT = "live_cell_has_residual_text"


def _rank(layer: str | None) -> int:
    return LAYER_RANK.get(layer, -1) if layer is not None else -1


def highest_ok_layer(coverage: dict) -> str | None:
    """The highest-ranked layer reporting an executed-passing tagged test
    (``"ok"``, case-sensitive — ``_cov_status`` never emits a lower-case
    ``"missing"``), or ``None`` when no layer does. Delegates to
    ``_layer_coverage_binding._highest_ok_layer`` directly (see module
    docstring) — same function, not a re-implementation of it."""
    return _shared_highest_ok_layer(coverage)


def bound_but_absent_layers(tests: dict) -> set[str]:
    """Layers carrying a tagged, enabled link whose evidence is not a DECIDED
    ``"pass"`` or ``"fail"`` — "absent ≠ green": a binding that exists but was
    never observed running, distinct from a layer with no binding at all. Any
    ``executed`` value other than the two decided ones counts (not only the
    literal ``"not_run"`` sentinel) — a missing key, ``None``, or an
    unrecognised value is exactly as undecided. Every layer name reported
    counts, canonical or not — an unrecognised layer carrying such a
    binding is exactly the "bound test never ran" case the spec names. A
    layer whose only evidence is ``executed == "fail"`` is DELIBERATELY not
    reported here: a failing test is a DECIDED
    "not green" needing no human judgement; it simply never becomes
    ``highest_ok_layer``, same as no binding at all — see
    ``test_a_failing_test_is_a_decided_non_promotion_not_an_escalation``.
    """
    absent: set[str] = set()
    for layer, links in (tests or {}).items():
        if any(
            isinstance(link, dict)
            and link.get("status") == "enabled"
            and link.get("executed") not in ("pass", "fail")
            for link in links
        ):
            absent.add(layer)
    return absent


def _unrecognised_ok_layers(coverage: dict) -> set[str]:
    """Coverage keys reporting ``"ok"`` that this module has no canonical rank
    for. An unranked "ok" layer can't be placed relative to the canonical
    ones, so the highest OBSERVABLE layer is structurally unreadable from
    the manifest — the same undecidable case a collision produces, not a
    promotable value."""
    return {layer for layer, status in (coverage or {}).items()
            if status == "ok" and layer not in LAYER_RANK}


def _skip(fr_id: str, reason_code: str) -> dict:
    return {"fr": fr_id, "action": "skip", "reason_code": reason_code}


def _escalate(fr_id: str, reason_code: str, detail: str) -> dict:
    return {"fr": fr_id, "action": "escalate", "reason_code": reason_code, "detail": detail}


def _canonical_layer_tokens(values: list[str]) -> set[str]:
    """Re-tokenise every element of ``values`` on the shared separator regex,
    lowercased -- not a bare ``set(values)``. An element from
    ``live_required_layers`` (comma-only split) can still be a compound,
    un-split token like ``"unit integration"``.

    Fails closed with ``ValueError`` on a non-``str`` element (a hand-
    corrupted ledger entry, e.g. ``null``/an int in ``required_layers``)
    rather than a raw ``AttributeError`` from ``.strip()`` -- matching
    ``load_ledger``'s own "fail closed rather than guess" contract."""
    tokens: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise ValueError(f"required_layers element is not a string: {value!r}")
        for tok in _LAYER_TOKEN_RE.split(value.strip()):
            low = tok.lower()
            if low:
                tokens.add(low)
    return tokens


def _narrowed_since_promotion(ledger_entry: dict, live_required_layers: list[str] | None) -> bool:
    """Whether the LIVE spec.md cell no longer includes every layer the
    ledger's ``promoted`` entry recorded — a stronger, content-based check
    than the evidence fingerprint alone: a maintainer hand-shrinking an
    explicit cell (``unit, integration`` → ``unit``) changes nothing about
    the FR's *evidence*, so a fingerprint comparison alone would miss it
    entirely. ``None`` for either side means "nothing to compare" — never a
    narrowing.

    Both sides canonicalised before comparing: comma-only splitting an
    already-explicit cell that a maintainer cosmetically reformats
    (``unit, integration`` → ``unit integration`` or ``unit/integration``,
    both still canonical) previously read as ONE token -- a false narrowing
    over a no-op edit. Re-split both sides here rather than change
    ``live_required_layers``'s own comma-only contract (see that function's
    docstring for why it stays that way).
    """
    recorded = ledger_entry.get("required_layers")
    if recorded is None or live_required_layers is None:
        return False
    return not _canonical_layer_tokens(recorded) <= _canonical_layer_tokens(live_required_layers)


def evaluate_fr(
    node: dict, *, is_collision: bool, ledger_entry: dict | None = None,
    live_required_layers: list[str] | None = None,
    live_cell_has_non_canonical_content: bool = False,
) -> dict:
    """Decide ONE requirement's promotion outcome from its manifest node.

    ``node`` is one ``test-traceability.json`` requirement node (``id``,
    ``required_layers``, ``required_layers_source``, ``coverage``, ``tests``).
    ``is_collision`` is whether this FR's display id is an ambiguous
    fan-out (``_layer_coverage_core.collision_display_ids``) — the manifest
    itself cannot credit an ``"ok"`` to a collision id reliably, so its highest
    layer is structurally undeterminable regardless of what ``coverage`` shows.
    ``ledger_entry`` is the LATEST recorded decision for this FR
    (``layer_promotion_ledger``), or ``None`` if this FR has never been decided.
    ``live_required_layers`` is the ACTUAL layer list read straight from the
    live spec.md cell right now (``fr_layer_cell_writer.live_required_layers``),
    used only to detect a hand narrowing of an already-promoted FR.
    ``live_cell_has_non_canonical_content`` is whether the live cell CURRENTLY
    carries text a promotion's rewrite would silently delete
    (``fr_layer_cell_writer.live_cell_has_non_canonical_content``) — checked
    only on the path that would otherwise promote (Stage-3 doubt-review round
    2, P3.5 post-push round): "widen never narrow" holds over the canonical
    layer SET this mechanism computes, not over the cell's raw TEXT, and
    ``render_layers`` regenerates the whole cell from that set alone. Reports
    :data:`SKIP_LIVE_CELL_HAS_RESIDUAL_TEXT` — a named SKIP, not an escalation
    (Stage-1 spec-review REJECT, P3.5 post-push round, on an earlier version
    of this same fix): the predicate DOES hold here, so this is not one of
    the spec's three named undecidable cases, and ``REASON_LAYER_
    UNDETERMINABLE`` would misreport a manifest-evidence gap that does not
    exist — what is actually true is that the live spec.md cell, not the
    manifest, carries text this run will not overwrite.

    Returns one of three action shapes: ``{"action": "promote", "required_layers": [...],
    "highest_ok": ...}``, ``{"action": "skip", "reason_code": ...}``, or
    ``{"action": "escalate", "reason_code": ..., "detail": ...}``.
    """
    fr_id = node["id"]
    already_explicit = node.get("required_layers_source") == "explicit"
    ledger_action = ledger_entry.get("action") if ledger_entry else None

    # A collision's own "undeterminable" wall must be exitable — checked
    # AGAINST the ledger, not before it, so a recorded operator decision
    # (made via the human-only CLI, which itself now refuses an ambiguous
    # `--fr-id`) permanently clears it rather than re-escalating forever.
    if is_collision:
        if ledger_action == "demoted":
            return _skip(fr_id, SKIP_DEMOTED_CONSISTENT)
        if ledger_action == "promoted":
            # Deliberately NOT the `_narrowed_since_promotion` check below:
            # `live_required_layers` for a collision id is keyed by DISPLAY
            # id, and a fan-out can span more than one spec_path — comparing
            # against "whichever file happened to be read last" would be
            # unreliable. Also currently unreachable in practice: the human
            # CLI already refuses `--action promoted` for an ambiguous id, so
            # a collision can only ever carry a `demoted` entry — kept as
            # defense-in-depth, not exercised by any live path today.
            if already_explicit:
                return _skip(fr_id, SKIP_ALREADY_EXPLICIT_CONSISTENT)
            return _escalate(
                fr_id, REASON_CONTRADICTS_DECISION,
                "the ledger records a prior operator promotion for this "
                "collision id, but the spec no longer shows an explicit "
                "binding — promoting again would silently paper over "
                "whatever changed it back",
            )
        return _escalate(
            fr_id, REASON_LAYER_UNDETERMINABLE,
            "this FR's display id is an ambiguous collision fan-out; its "
            "coverage 'ok' is never credited, so the highest observable "
            "layer cannot be read from the manifest — only an operator's "
            "recorded decision (record_layer_promotion_decision.py) clears "
            "this, a rerun alone never will",
        )

    coverage = node.get("coverage") or {}
    tests = node.get("tests") or {}
    highest_ok = highest_ok_layer(coverage)
    absent = bound_but_absent_layers(tests)
    unrecognised_ok = _unrecognised_ok_layers(coverage)
    # ANY bound-but-unexecuted layer is ambiguous, regardless of its rank
    # relative to the highest passing layer: the spec's rule is unconditional
    # — "the named test did not run in the CI evidence at all" — not "...and
    # it outranks what's already green". A same- or lower-ranked absent
    # binding is just as much "not green" as a higher-ranked one.
    evidence_ambiguous = bool(absent) or bool(unrecognised_ok)

    required_before = set(node.get("required_layers") or [])
    ok_layers = {layer for layer, status in coverage.items() if status == "ok"}
    # Every layer THIS FR's binding already required must independently show
    # fresh passing evidence before a promotion may assert the whole set as
    # explicit — a new "ok" layer elsewhere never papers over an existing
    # required layer that is not currently green.
    unverified_required = required_before - ok_layers
    predicate_holds = (
        highest_ok is not None and not evidence_ambiguous and not unverified_required
    )

    if ledger_action == "promoted":
        if already_explicit and not _narrowed_since_promotion(ledger_entry, live_required_layers):
            return _skip(fr_id, SKIP_ALREADY_EXPLICIT_CONSISTENT)
        return _escalate(
            fr_id, REASON_CONTRADICTS_DECISION,
            "the ledger records a prior promotion for this FR, but the spec "
            "no longer shows an explicit binding, or was narrowed since — "
            "promoting again would silently paper over whatever changed it "
            "back",
        )

    if ledger_action == "demoted":
        # "Exitable" AND scoped to the three named cases only (spec L11/L21/
        # L25/L40): drift alone is not enough — drift toward WORSE evidence
        # (still not promotable) stays a plain decided skip. Only drift into
        # a state `predicate_holds` would NOW promote is a genuinely new
        # situation the veto never saw.
        if already_explicit or (fingerprint_drifted(ledger_entry, node) and predicate_holds):
            return _escalate(
                fr_id, REASON_CONTRADICTS_DECISION,
                "the ledger records an operator demotion for this FR, but "
                "the spec is explicit again or the evidence has since moved "
                "into a state that would now be promotable — a genuinely "
                "new situation the operator has not yet seen, needing a "
                "new, human-recorded decision rather than a silent "
                "re-promotion",
            )
        return _skip(fr_id, SKIP_DEMOTED_CONSISTENT)

    if already_explicit:
        return _skip(fr_id, SKIP_ALREADY_EXPLICIT)

    if unrecognised_ok:
        return _escalate(
            fr_id, REASON_LAYER_UNDETERMINABLE,
            "coverage reports 'ok' for unrecognised layer name(s) "
            f"{sorted(unrecognised_ok)} — this module has no canonical rank "
            "for them, so the highest observable layer cannot be placed",
        )

    if evidence_ambiguous:
        return _escalate(
            fr_id, REASON_BOUND_TEST_ABSENT,
            f"a bound test at layer(s) {sorted(absent)} did not run in this "
            "evidence at all — absent is not green",
        )

    if highest_ok is None:
        return _skip(fr_id, SKIP_NO_EVIDENCE_YET)

    if unverified_required:
        return _skip(fr_id, SKIP_EXISTING_REQUIRED_NOT_VERIFIED)

    if live_cell_has_non_canonical_content:
        # A named SKIP, not an escalation (Stage-1 spec-review REJECT, P3.5
        # post-push round): the predicate demonstrably HOLDS here (highest_ok
        # is not None, evidence is unambiguous, every existing required layer
        # is verified, no ledger contradiction) -- the spec's escalation list
        # is closed to the three named undecidable cases, and "the predicate
        # holds but the cell has other text" is not one of them. Reporting
        # REASON_LAYER_UNDETERMINABLE here was also untruthful: that code
        # means "the highest observable layer cannot be determined from the
        # manifest" -- it WAS determined, just above. What is actually true
        # is narrower and different in kind: the live spec.md cell (not the
        # manifest) carries text an automated rewrite would silently delete,
        # so this run defers rather than overwrites it -- same data-
        # protection outcome as before, reported honestly as a skip.
        return _skip(fr_id, SKIP_LIVE_CELL_HAS_RESIDUAL_TEXT)

    # Widen by the single highest observable layer only, never by every
    # currently-ok layer: the spec's predicate names ONE layer ("the binding
    # includes the highest observable layer"), and binding a layer the FR
    # never asked for just because it happens to be green this run creates a
    # HARD gate obligation (P3.3's own enforcement) this promotion never
    # justified.
    new_required = sorted(required_before | {highest_ok}, key=_rank)
    return {
        "fr": fr_id,
        "action": "promote",
        "required_layers": new_required,
        "highest_ok": highest_ok,
    }


__all__ = [
    "LAYER_RANK",
    "REASON_LAYER_UNDETERMINABLE",
    "REASON_BOUND_TEST_ABSENT",
    "REASON_CONTRADICTS_DECISION",
    "SKIP_ALREADY_EXPLICIT",
    "SKIP_ALREADY_EXPLICIT_CONSISTENT",
    "SKIP_DEMOTED_CONSISTENT",
    "SKIP_NO_EVIDENCE_YET",
    "SKIP_EXISTING_REQUIRED_NOT_VERIFIED",
    "SKIP_LIVE_CELL_HAS_RESIDUAL_TEXT",
    "highest_ok_layer",
    "bound_but_absent_layers",
    "evaluate_fr",
]
