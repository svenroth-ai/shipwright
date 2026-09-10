"""The data model + read API for grill-trace records (schema:
``shared/grill-trace-format.md``).

Split out from ``write_grill_trace.py`` up front (not after a 300-LOC
crossing) because it has two callers from day one, the same reason
``context_md_format.py`` was promoted out of a leading-underscore module in
P4.1 (doubt-reviewer D4): the producer (``write_grill_trace.py``) and the
completeness gate (``verify_grill_trace_completeness.py``) must both read
through one parser, never fork it.

Everything here is pure data-in/data-out plus one I/O function
(:func:`read_trace_dir`) — no CLI, no locking (the producer owns locking;
a reader does not need it, the same split ``context_md_format.read_terms``
uses).
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from atomic_write import durable_read_bytes  # noqa: E402

# A ``requirement_key`` becomes a filename component (``<key>.json`` under
# ``grill-traces/``) — external plan review (P4.2) flagged an unvalidated
# slug as a filesystem-boundary risk (path separators, ``..``, reserved
# names). Lower-kebab-case only, matching the convention
# ``shared/grill-trace-format.md`` §1 documents (the slug that becomes the
# FR row's ``Name`` column) — this ALSO forecloses the injection surface,
# since neither `/`, `\`, nor `..` can ever match it.
_REQUIREMENT_KEY_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# The seven dimensions, in the order `shared/requirement-elicitation.md` §8
# tables them. A grill-trace's ``dimensions`` object must carry exactly
# these keys — no more, no fewer.
DIMENSIONS: tuple[str, ...] = (
    "outcome", "purpose", "boundaries", "failure", "glossary", "rationale", "out_of_scope",
)

# Closed vocabulary for a ``surface`` value. Only "project" is wired as of
# P4.2 (shipwright-project); "adopt"/"iterate" are reserved for the
# cross-cutting follow-up the design names but explicitly defers.
SURFACES: tuple[str, ...] = ("project", "adopt", "iterate")

GRILL_TRACES_DIRNAME = "grill-traces"


class GrillTraceError(ValueError):
    """A malformed grill-trace record — missing/blank required field, an
    unrecognized ``dimensions`` key, or a ``surface`` outside the closed
    vocabulary. Raised eagerly so a caller never operates on a partially
    valid record."""


@dataclass(frozen=True)
class GrillTrace:
    requirement_key: str
    requirement_text: str
    surface: str
    evidence: tuple[str, ...]
    dimensions: dict[str, str]
    fit_criterion: str | None
    glossary_delta: tuple[dict[str, str], ...]
    confirmed_by: str
    terms_used: tuple[str, ...]
    source_path: Path | None = None


def _require_nonblank_str(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GrillTraceError(f"'{key}' must be a non-blank string")
    return value


def _require_str_list(payload: dict, key: str, *, allow_empty: bool) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise GrillTraceError(f"'{key}' must be a list of strings")
    if not allow_empty and not value:
        raise GrillTraceError(f"'{key}' must not be empty")
    return tuple(value)


def _validate_dimensions(payload: dict) -> dict[str, str]:
    dimensions = payload.get("dimensions")
    if not isinstance(dimensions, dict):
        raise GrillTraceError("'dimensions' must be an object")
    extra = set(dimensions) - set(DIMENSIONS)
    if extra:
        raise GrillTraceError(f"'dimensions' has unrecognized key(s): {sorted(extra)}")
    # A missing key is "the same STOP as a blank one" (shared/grill-trace-format.md
    # §2) — reject it HERE, at write time, rather than letting an incomplete
    # record reach disk and only be caught later by the gate's
    # check_blank_dimension (external code review, P4.2).
    missing = set(DIMENSIONS) - set(dimensions)
    if missing:
        raise GrillTraceError(f"'dimensions' is missing key(s): {sorted(missing)}")
    for name, value in dimensions.items():
        if not isinstance(value, str) or not value.strip():
            raise GrillTraceError(f"'dimensions.{name}' must be a non-blank string")
    return dict(dimensions)


def _validate_glossary_delta(payload: dict) -> tuple[dict[str, str], ...]:
    delta = payload.get("glossary_delta", [])
    if not isinstance(delta, list):
        raise GrillTraceError("'glossary_delta' must be a list")
    out: list[dict[str, str]] = []
    for entry in delta:
        if not isinstance(entry, dict) or "term" not in entry or "recorded_in" not in entry:
            raise GrillTraceError(
                "'glossary_delta' entries must be objects with 'term' and 'recorded_in'"
            )
        out.append({"term": str(entry["term"]), "recorded_in": str(entry["recorded_in"])})
    return tuple(out)


def parse_trace(payload: dict, *, source_path: Path | None = None) -> GrillTrace:
    """Validate + build a :class:`GrillTrace` from an already-parsed JSON
    object. Raises :class:`GrillTraceError` on any structural violation —
    this is schema validation, never a quality judgment (see the module
    docstring and ``shared/grill-trace-format.md`` §3)."""
    if not isinstance(payload, dict):
        raise GrillTraceError("a grill-trace record must be a JSON object")

    requirement_key = _require_nonblank_str(payload, "requirement_key")
    if not _REQUIREMENT_KEY_RE.match(requirement_key):
        raise GrillTraceError(
            f"'requirement_key' must be lower-kebab-case (a-z, 0-9, single "
            f"hyphens between segments) — got {requirement_key!r}"
        )
    requirement_text = _require_nonblank_str(payload, "requirement_text")
    surface = _require_nonblank_str(payload, "surface")
    if surface not in SURFACES:
        raise GrillTraceError(f"'surface' must be one of {SURFACES}, got {surface!r}")
    evidence = _require_str_list(payload, "evidence", allow_empty=False)
    dimensions = _validate_dimensions(payload)
    fit_criterion = payload.get("fit_criterion")
    if fit_criterion is not None and (not isinstance(fit_criterion, str) or not fit_criterion.strip()):
        raise GrillTraceError("'fit_criterion' must be a non-blank string or null")
    glossary_delta = _validate_glossary_delta(payload)
    confirmed_by = _require_nonblank_str(payload, "confirmed_by")
    terms_used = _require_str_list(payload, "terms_used", allow_empty=True)

    return GrillTrace(
        requirement_key=requirement_key,
        requirement_text=requirement_text,
        surface=surface,
        evidence=evidence,
        dimensions=dimensions,
        fit_criterion=fit_criterion,
        glossary_delta=glossary_delta,
        confirmed_by=confirmed_by,
        terms_used=terms_used,
        source_path=source_path,
    )


def grill_traces_dir(planning_dir: Path) -> Path:
    return Path(planning_dir) / GRILL_TRACES_DIRNAME


def trace_path(planning_dir: Path, requirement_key: str) -> Path:
    return grill_traces_dir(planning_dir) / f"{requirement_key}.json"


def read_trace_dir(planning_dir: Path) -> list[GrillTrace]:
    """Every grill-trace record under ``{planning_dir}/grill-traces/*.json``,
    parsed and validated. Returns ``[]`` if the directory doesn't exist. A
    malformed file's :class:`GrillTraceError` is NOT swallowed — a broken
    trace must surface, never be silently skipped (it would otherwise look
    identical to "elicitation never ran")."""
    directory = grill_traces_dir(planning_dir)
    if not directory.is_dir():
        return []
    traces: list[GrillTrace] = []
    for path in sorted(directory.glob("*.json")):
        content = durable_read_bytes(path).decode("utf-8")
        payload = json.loads(content)
        traces.append(parse_trace(payload, source_path=path))
    return traces
