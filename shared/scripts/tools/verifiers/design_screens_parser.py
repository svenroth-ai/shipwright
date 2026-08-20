"""Design-manifest ``## Screens``/``## Non-UI FRs`` parsing, plus the
FR-coverage summary built on top of them.

Extracted from ``design_checks.py`` (which is pinned at its current line
count in ``shipwright_bloat_baseline.json``) so the column-tolerant rewrite
and the Non-UI-FR exemption had room to land without ratcheting that file.

The Screens-table parser locates the "file" and "linked FRs" columns by
HEADER NAME rather than a fixed position, so an inserted column (e.g. a
"Split" column distinguishing frontend/backend screens) does not zero out
parsing the way a position-anchored 5-column regex did.
"""

from __future__ import annotations

import re

# Table separator line ("|---|---|" or "|:--|--:|"), ignored during parsing.
_TABLE_SEPARATOR_RE = re.compile(r"^\|[\s:|-]+\|$")

# Header-cell matchers: the path column is named "File"/"Files" (the
# "Screen" column beside it is a display NAME, not the path). The linked-FRs
# column is preferably "Linked FRs" (checked first); a bare "FR"/"FRs" is
# only a fallback, since an extra column mentioning "FR" (e.g. "FR Status")
# could otherwise be matched instead of the real one. Whole-word matches
# only, so neither pattern accidentally matches an unrelated header like
# "Frame".
_FILE_HEADER_RE = re.compile(r"\bfiles?\b", re.IGNORECASE)
_LINKED_FRS_HEADER_RE = re.compile(r"\blinked\s*frs?\b", re.IGNORECASE)
_FRS_HEADER_RE = re.compile(r"\bfrs?\b", re.IGNORECASE)

_NON_UI_FR_ROW_RE = re.compile(r"^-\s*(?P<fr>FR-[\d.]+)\b")
_ADR_REF_RE = re.compile(r"\bADR-\d+\b")


def _split_row(line: str) -> list[str]:
    """Split a markdown table row on ``|``, dropping the empty leading and
    trailing cells a well-formed ``| a | b |`` line produces."""
    cells = line.strip().split("|")
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [c.strip() for c in cells]


def _find_column(headers: list[str], pattern: re.Pattern[str]) -> int | None:
    for idx, header in enumerate(headers):
        if pattern.search(header):
            return idx
    return None


def _find_frs_column(headers: list[str]) -> int | None:
    """Locate the linked-FRs column, preferring a "Linked FRs" header over
    a bare "FR"/"FRs" one — an earlier unrelated column (e.g. "FR Status")
    must not shadow the real one. (Column 0 is falsy — must check for
    ``None`` explicitly, not fall through on it.)"""
    linked = _find_column(headers, _LINKED_FRS_HEADER_RE)
    return linked if linked is not None else _find_column(headers, _FRS_HEADER_RE)


def _extract_frs(fr_cell: str) -> list[str]:
    if not fr_cell or fr_cell.lower() in {"none", "-", "—", "tbd"}:
        return []
    return [
        f.strip()
        for f in re.split(r"[,\s]+", fr_cell)
        if re.match(r"^FR-[\d.]+$", f.strip())
    ]


def parse_screens_table(manifest_body: str) -> list[tuple[str, list[str]]]:
    """Return ``[(screen_file, [linked_frs])]`` for every row inside the
    ``## Screens`` section of a design manifest. Stops at the next ``## ``
    header so trailing ``## User Flows`` / ``## Uploads`` tables aren't
    merged in. Column count is read from the header row, not assumed."""
    m = re.search(r"##\s+Screens\s*\n(.*?)(?=\n##\s+|\Z)", manifest_body, re.DOTALL)
    if not m:
        return []
    lines = m.group(1).splitlines()

    header_idx = next(
        (i for i, ln in enumerate(lines) if ln.strip().startswith("|")),
        None,
    )
    if header_idx is None:
        return []
    headers = _split_row(lines[header_idx])
    file_col = _find_column(headers, _FILE_HEADER_RE)
    frs_col = _find_frs_column(headers)
    if file_col is None or frs_col is None:
        return []

    out: list[tuple[str, list[str]]] = []
    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if _TABLE_SEPARATOR_RE.match(stripped):
            continue
        if not stripped.startswith("|"):
            # A blank line or trailing prose ends the table — do not merge
            # a later, unrelated pipe-table (e.g. under a "### Archived"
            # subheading, which the section boundary above does not stop at).
            break
        cells = _split_row(stripped)
        if len(cells) <= max(file_col, frs_col):
            continue
        out.append((cells[file_col], _extract_frs(cells[frs_col])))
    return out


def parse_non_ui_frs(manifest_body: str) -> set[str]:
    """Return the FR ids listed under an optional ``## Non-UI FRs`` section
    of the design manifest — FRs a project has decided are legitimately
    backend-only and need no screen mapping. Each list line must be
    ``- FR-ID — ...ADR-NNN...``: an ``ADR-NNN`` reference is REQUIRED for a
    line to count, so a self-service waiver of an ERROR-severity compliance
    gate always requires a cited ADR id (the cited ADR's own validity is not
    checked here — see ``common.py``'s ADR-integrity helpers for that); a
    line with no ADR reference is ignored (not exempted)."""
    m = re.search(r"##\s+Non-UI FRs\s*\n(.*?)(?=\n##\s+|\Z)", manifest_body, re.DOTALL)
    if not m:
        return set()
    out: set[str] = set()
    for line in m.group(1).splitlines():
        stripped = line.strip()
        hit = _NON_UI_FR_ROW_RE.match(stripped)
        if hit and _ADR_REF_RE.search(stripped):
            out.add(hit.group("fr"))
    return out


def summarize_fr_coverage(
    declared: set[str], rows: list[tuple[str, list[str]]], non_ui: set[str]
) -> tuple[bool, str]:
    """Compare declared FR ids against Screens-table links plus Non-UI
    exemptions. Returns ``(ok, detail)`` for the caller to wrap in a
    ``CheckResult``."""
    linked: set[str] = set()
    for _, row_frs in rows:
        linked.update(row_frs)

    orphans = sorted(declared - linked - non_ui)
    exempt_count = len(declared & non_ui)
    stale_non_ui = sorted(non_ui - declared)
    stale_suffix = (
        f" ({len(stale_non_ui)} Non-UI FR entry(ies) match no declared "
        f"FR: {stale_non_ui[:3]})"
        if stale_non_ui else ""
    )

    if orphans:
        if not rows:
            # rows==[] means either the table is empty (no screens exist
            # yet) or the header/columns could not be identified at all —
            # this cannot tell the two apart without a richer parser
            # result, so the wording stays deliberately non-committal.
            return False, (
                "no Screens rows parsed (empty table, or unrecognized "
                "manifest format) — cannot verify coverage for "
                f"{len(orphans)} FR(s): {orphans[:5]}"
                + (" …" if len(orphans) > 5 else "") + stale_suffix
            )
        return False, (
            f"{len(orphans)} FR(s) with no screen mapping: {orphans[:5]}"
            + (" …" if len(orphans) > 5 else "") + stale_suffix
        )

    detail = f"{len(declared) - exempt_count} FR(s) linked across {len(rows)} screen(s)"
    if exempt_count:
        detail += f" ({exempt_count} exempt as Non-UI FRs)"
    if not rows and declared:
        # Coverage is satisfied entirely by Non-UI exemptions — but that can
        # also mean the Screens table failed to parse. Surface it either way
        # so a broken manifest is never invisible just because every
        # declared FR happens to be exempt.
        detail += " (no Screens rows parsed — empty table, or unrecognized manifest format)"
    detail += stale_suffix
    return True, detail
