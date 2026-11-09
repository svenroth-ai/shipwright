"""The ``## AC-Move-Map`` table: where a criterion went when its requirement was split (atomic-frs U2).

Splitting FR-01.11 moves some of its criteria into a new FR. The criterion keeps its number (``FR-01.11/AC21`` becomes
``FR-01.22/AC21``) but the FR part of its id changes, while old reports, decision notes and the append-only event log
keep naming the old id. This table is what keeps every old id resolvable, the way ``## FR-Fold-Map`` does for folded FRs::

    ## AC-Move-Map

    | Old id | New id |
    |---|---|
    | `FR-01.11/AC21` | `FR-01.22/AC21` |

Ids sit in backticks so a naive ``| FR-`` line filter (tests, scripts) never mistakes a row for a requirement row. Header cells must not start with ``ID`` (the FR-table readers treat a header whose first cell is ``ID`` as a
requirements table). Rows are append-only: a row is never edited or removed. Pure, stdlib only (ADR-045 loader safe).
"""

from __future__ import annotations

import re

__all__ = ["AC_ID", "MOVE_HEADING", "parse_move_map", "render_section", "resolve_ac"]

MOVE_HEADING = "## AC-Move-Map"
AC_ID = re.compile(r"^FR-\d{2}\.\d{2}/AC\d{2,}$")
_HEADER = ("Old id", "New id")


def parse_move_map(spec_text: str) -> dict[str, str]:
    """``{old id: new id}`` from the ``## AC-Move-Map`` section (``{}`` when there is none). Malformed rows are skipped."""
    out: dict[str, str] = {}
    inside = False
    for line in (spec_text or "").splitlines():
        if line.startswith("#"):
            inside = line.strip().lower() == MOVE_HEADING.lower()
            continue
        if not inside or not line.startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and AC_ID.match(cells[0]) and AC_ID.match(cells[1]):
            out[cells[0]] = cells[1]
    return out


def resolve_ac(ac_id: str, moves: dict[str, str]) -> str:
    """Follow ``ac_id`` through the move map to where it lives now (a cycle or a missing row returns the last id reached)."""
    seen = {ac_id}
    while ac_id in moves and moves[ac_id] not in seen:
        ac_id = moves[ac_id]
        seen.add(ac_id)
    return ac_id


def render_section(moves: dict[str, str]) -> str:
    """The full section text for ``moves`` (ends with a newline)."""
    rows = "\n".join(f"| `{o}` | `{n}` |" for o, n in moves.items())
    return f"{MOVE_HEADING}\n\n| {_HEADER[0]} | {_HEADER[1]} |\n|---|---|\n{rows}\n"
