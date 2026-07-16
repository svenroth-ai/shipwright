"""Per-test execution-evidence reader (traceability TT-EV — Spec §11 R1, closes G5).

Core: assemble a normalized, schema-validated per-test evidence index keyed to the
``test_links`` collector's stable ``path::name`` ids, so "covered at a layer" means a
tagged test that is **enabled AND observed passing** in that layer's runner evidence.
The runner parsers live in ``_evidence_readers`` and the vocab/reduction primitives in
``_evidence_vocab`` (ADR-099 300-LOC split); this module owns ``build_index``,
``normalize_index``, schema validation, and the expiring-waiver primitives, and
re-exports the reader API for callers/tests.

The ``status`` / ``executed`` vocabulary is a VALIDATED FROZEN boundary: runner-
specific raw statuses are normalized into the closed enums at ingestion and an
out-of-vocab value is coerced fail-closed (``executed`` → ``not_run``, ``status`` →
``quarantined``) — never trusted. The assembled index is validated against
``evidence_index_schema.json`` before it is returned. The committed artifact is
derived/RTM-visibility only (R3); enforcing gates regenerate base+head themselves.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from ._evidence_readers import read_junit, read_playwright, read_vitest
from ._evidence_vocab import (
    EVIDENCE_INDEX_VERSION,
    EXECUTED_VOCAB,
    LAYER_VOCAB,
    STATUS_VOCAB,
    entry as _entry,
    merge_into,
)

__all__ = [
    "EVIDENCE_INDEX_VERSION", "STATUS_VOCAB", "EXECUTED_VOCAB",
    "read_junit", "read_playwright", "read_vitest",
    "build_index", "normalize_index", "validate_index",
    "waiver_state", "layer_satisfied",
]


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "evidence_index_schema.json"


def validate_index(index: dict) -> None:
    """Fail-closed schema check: raise if the index is not evidence-index-v2-valid."""
    import jsonschema  # noqa: PLC0415 — compliance dep; lazy so light imports stay light

    schema = json.loads(_schema_path().read_text(encoding="utf-8"))
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(index))
    if errors:
        raise ValueError("evidence index failed v2-schema validation: " + errors[0].message)


def build_index(
    *,
    junit: str | None = None,
    playwright: dict | None = None,
    vitest: dict | None = None,
    root: Path | None = None,
    bases: dict | None = None,
    generated_at: str | None = None,
    source_reports: list[str] | None = None,
    waivers: list[dict] | None = None,
) -> dict:
    """Merge parsed runner evidence into one schema-validated index (pure; no writes).

    ``root`` (+ optional per-runner ``bases``) normalize runner-emitted paths to
    project_root-relative ids so real Vitest/pytest evidence actually joins. Cross-
    report merges go through the fail-closed reduction (a later pass can't mask an
    earlier failure). ``generated_at`` / ``source_reports`` make staleness auditable;
    ``waivers`` (operator-authored) are carried through verbatim so the layer gate
    (TT2/TT5) can honor a valid one via ``layer_satisfied``.
    """
    bases = bases or {}
    parsed_sets = []
    if junit:
        parsed_sets.append(read_junit(junit, root=root, base=bases.get("junit", "")))
    if playwright:
        parsed_sets.append(read_playwright(playwright, root=root, base=bases.get("playwright", "")))
    if vitest:
        parsed_sets.append(read_vitest(vitest, root=root, base=bases.get("vitest", "")))
    results: dict = {}
    for parsed in parsed_sets:
        for tid, ent in parsed.items():
            merge_into(results, tid, ent)
    index: dict = {"schema_version": EVIDENCE_INDEX_VERSION, "results": results}
    if generated_at is not None:
        index["generated_at"] = generated_at
    if source_reports is not None:
        index["source_reports"] = sorted(source_reports)
    if waivers:
        index["waivers"] = waivers
    validate_index(index)
    return index


def normalize_index(raw: dict) -> dict:
    """Coerce an arbitrary/untrusted evidence index to the frozen vocab (fail-closed).

    The ingestion boundary for an *already-normalized* index (a hand-authored or
    merged ``test-evidence-index.json``): every ``status``/``executed`` is run through
    the closed-vocab coercion so a value like ``executed:"passed"`` can never be
    trusted as a real pass. Operator ``waivers`` survive verbatim.
    """
    results: dict = {}
    for tid, ev in (raw.get("results") or {}).items():
        if not isinstance(ev, dict):
            continue
        ent = _entry(ev.get("status"), ev.get("executed"), "")
        if ev.get("runner"):
            ent["runner"] = str(ev["runner"])
        else:
            del ent["runner"]
        results[tid] = ent
    index: dict = {"schema_version": EVIDENCE_INDEX_VERSION, "results": results}
    if raw.get("waivers"):
        index["waivers"] = raw["waivers"]
    validate_index(index)
    return index


def waiver_state(waiver: dict, *, now: date | None = None) -> str:
    """``valid`` | ``expired`` | ``invalid``.

    A waiver missing any accountability field (layer/reason/owner/ticket/expires),
    naming an unknown layer, or carrying an unparseable date is ``invalid`` — an
    incomplete waiver is never honored (fail-closed). Date comparison is UTC.
    """
    required = ("layer", "reason", "owner", "ticket", "expires")
    if not isinstance(waiver, dict) or any(not str(waiver.get(k, "")).strip() for k in required):
        return "invalid"
    if waiver.get("layer") not in LAYER_VOCAB:
        return "invalid"
    try:
        expires = date.fromisoformat(str(waiver["expires"]))
    except ValueError:
        return "invalid"
    today = now or datetime.now(timezone.utc).date()
    return "valid" if today <= expires else "expired"


def layer_satisfied(links: list[dict], *, waiver: dict | None = None, now: date | None = None) -> bool:
    """R1 layer decision for a gate: satisfied iff an enabled+pass link exists, else a
    VALID waiver honors it. An expired/invalid/absent waiver → fail-closed False.

    CARRY-FORWARD (TT5): the waiver ``scope`` field is NOT consulted here — the TT2/TT5
    gate MUST pre-filter waivers by layer AND scope before passing one in, or a broad
    waiver would over-cover.
    """
    if any(l.get("status") == "enabled" and l.get("executed") == "pass" for l in links):
        return True
    return waiver is not None and waiver_state(waiver, now=now) == "valid"
