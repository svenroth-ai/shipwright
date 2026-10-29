"""FR-row <-> grill-trace coverage join — split out of
``verify_grill_trace_completeness.py`` the moment that file crossed the
300-LOC bloat-baseline threshold (same precedent as
``_write_context_term_cli.py`` / ``context_md_format.py`` in P4.1).

Closes a gap external plan review found in the ``grill_trace_coverage``
guard alone (P4.2): "an interview ran, zero traces exist" catches a
SKIPPED interview, but not a PARTIALLY recorded one where some elicited
requirements never got a trace. FR ids don't exist until spec generation
(Step 6), so this join can only run at gate-time (Step 8), via the same
``Name``-column slug convention ``shared/grill-trace-format.md`` §1
documents — the slug an interviewer is asked to choose from the
requirement's short capability name, matched against the FR row's own
``Name`` cell once spec generation has written it.

Not one of the four closed-vocabulary STOP conditions
(``verify_grill_trace_completeness.py``'s module docstring) — kept in its
own, differently-named module and result (``fr_trace_coverage``) so it is
never confused with them.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.verifiers.common import CheckResult, Severity

# One FR row per line of a spec.md's Functional Requirements table, in the
# converged column order `spec-generation.md` documents:
# `| ID | Area | Name | Priority | Description | Basis | Layers |`.
# Anchored on a literal "FR-" in the first cell, which naturally excludes
# the header row and the `|---|` separator row. A narrow, LOCAL parser —
# deliberately not `drift_parsers.parse_fr_table`, which owns `id`/`text`/
# `priority` but never exposes `Name` (the only cell this coverage check
# needs); forking a general FR-table reader for one column would cost more
# than it saves.
_FR_ROW_RE = re.compile(r"^\|\s*(FR-[\w.]+)\s*\|([^|]*)\|([^|]*)\|", re.MULTILINE)
_REMOVED_REQUIREMENTS_RE = re.compile(r"^#{2,3}\s+Removed Requirements\s*$", re.MULTILINE)
_SLUG_COLLAPSE_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Lower-kebab-case, matching ``shared/grill-trace-format.md``'s
    ``requirement_key`` convention."""
    return _SLUG_COLLAPSE_RE.sub("-", name.strip().lower()).strip("-")


def extract_fr_rows(spec_content: str) -> dict[str, tuple[str, str]]:
    """``{FR id: (Name, Basis)}`` for every LIVE row — rows inside a ``## Removed
    Requirements`` / ``### Removed Requirements`` subsection are excluded, mirroring
    ``drift_parsers.parse_fr_table``'s own exclusion (a retired FR is not something a live
    interview trace should have to cover). Name and Basis columns come from the table's header
    row (column orders are not stable); a table without a ``Basis`` column reads as
    ``interview`` (strict)."""
    body = _REMOVED_REQUIREMENTS_RE.split(spec_content, maxsplit=1)[0]
    rows: dict[str, tuple[str, str]] = {}
    name_idx, basis_idx = 2, None  # the converged `| ID | Area | Name | ...` layout until a header says otherwise
    for line in body.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0].lower() == "id":
            lowered = [c.lower() for c in cells]
            name_idx = lowered.index("name") if "name" in lowered else 2
            basis_idx = lowered.index("basis") if "basis" in lowered else None
            continue
        if cells and re.fullmatch(r"FR-[\w.]+", cells[0]) and len(cells) > name_idx and cells[name_idx]:
            basis = cells[basis_idx].lower() if basis_idx is not None and len(cells) > basis_idx else "interview"
            rows[cells[0]] = (cells[name_idx], basis or "interview")
    return rows


def extract_fr_names(spec_content: str) -> dict[str, str]:
    """``{FR id: Name cell text}`` for every live row (see :func:`extract_fr_rows`)."""
    return {fr_id: name for fr_id, (name, _basis) in extract_fr_rows(spec_content).items()}


def check_fr_trace_coverage(
    spec_paths: list[Path], trace_keys: set[str], *, inherited_ok: bool = False,
) -> CheckResult:
    """SKIPPED entirely before any spec.md exists (nothing to join against
    yet — the normal state during the interview itself, before Step 6)."""
    name = "fr_trace_coverage"
    if not spec_paths:
        return CheckResult(
            name, None, "no spec.md found yet — nothing to check", severity=Severity.SKIPPED.value,
        )
    fr_rows: dict[str, tuple[str, str]] = {}
    for path in spec_paths:
        fr_rows.update(extract_fr_rows(path.read_text(encoding="utf-8", errors="ignore")))
    fr_names = {fr_id: name_ for fr_id, (name_, _basis) in fr_rows.items()}
    if not fr_names:
        return CheckResult(
            name, None, "no FR rows found in any spec.md yet", severity=Severity.SKIPPED.value,
        )
    missing_ids = [fr_id for fr_id, name_ in fr_names.items() if slugify(name_) not in trace_keys]
    missing = sorted(f"{fr_id} (Name={fr_names[fr_id]!r} -> slug {slugify(fr_names[fr_id])!r})" for fr_id in missing_ids)
    if missing:
        # ERROR: "each requirement gets a trace" is the contract for every entry channel (it was a
        # WARNING after PR #705: the Name-slug join has no stable identity contract, so fix a false
        # positive by aligning the FR Name / requirement_key, not by letting a gap through).
        # Extension scope: only rows whose Basis is NOT `interview` (inherited, adopted, code-derived)
        # never went through this run's interview, so only those stay visible-but-non-blocking.
        blocking = [i for i in missing_ids if not inherited_ok or fr_rows[i][1].startswith("interview")]
        return CheckResult(
            name, False,
            f"FR row(s) with no matching grill-trace requirement_key: {missing}",
            severity=Severity.ERROR.value if blocking else Severity.WARNING.value,
        )
    return CheckResult(name, True, f"{len(fr_names)} FR row(s), every one has a matching grill-trace")
