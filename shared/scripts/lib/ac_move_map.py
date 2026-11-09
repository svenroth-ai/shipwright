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

__all__ = ["AC_ID", "MOVE_HEADING", "aliases", "moved_catalog", "parse_move_map", "real_moves", "render_section", "resolve_ac", "split_sources"]

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


def real_moves(base: set[tuple[str, str]], head: set[tuple[str, str]], moves: dict[str, str]) -> dict[tuple[str, str], tuple[str, str]]:
    """``{(fr, ac) at head: (fr, ac) at base}`` for the map rows that look like what ``fr_split`` writes - THE one rule the gates share.

    A row counts only when the criterion keeps its AC number, the source is gone at head, the target did not exist at base,
    the target FR is new (absent at base) and no other source already claimed the target. Anything else (a hand-written row
    onto a living id, a renumbering, a merge into an existing FR) reads as an ordinary removal + addition, so a row cannot hide one."""
    base_frs = {fr for fr, _ in base}
    out: dict[tuple[str, str], tuple[str, str]] = {}
    for fr, ac in sorted(base):
        target = resolve_ac(f"{fr}/{ac}", moves).split("/", 1)
        new = (target[0], target[1]) if len(target) == 2 else (fr, ac)
        if new != (fr, ac) and new[1] == ac and new in head and (fr, ac) not in head and new not in base and new[0] not in base_frs and new not in out:
            out[new] = (fr, ac)
    return out


def moved_catalog(texts: dict[str, str], moves: dict[str, str]) -> dict[str, str]:
    """``texts`` (catalog keys ``FR-01.11.AC21``) re-keyed to where each criterion lives now, per ``moves`` (ids ``FR-01.11/AC21``)."""
    out = {}
    for key, text in texts.items():
        fr, _, ac = key.rpartition(".")
        out[resolve_ac(f"{fr}/{ac}", moves).replace("/", ".")] = text
    return out


def aliases(ac_key: str, moves: dict[str, str]) -> set[str]:
    """Every id the criterion ``ac_key`` (dotted, ``FR-01.11.AC21``) has ever carried or carries now, dotted, itself included."""
    fr, _, ac = ac_key.rpartition(".")
    final = resolve_ac(f"{fr}/{ac}", moves)
    ids = {a for a in {*moves, *moves.values()} if resolve_ac(a, moves) == final}
    return {a.replace("/", ".") for a in ids} | {ac_key}


def split_sources(fr_id: str, moves: dict[str, str]) -> tuple[str, ...]:
    """The requirements whose criteria an ``fr_split`` moved INTO ``fr_id`` (so their history is part of its story)."""
    return tuple(sorted({o.split("/")[0] for o, n in moves.items() if n.split("/")[0] == fr_id and o.split("/")[0] != fr_id}))


def render_section(moves: dict[str, str]) -> str:
    """The full section text for ``moves`` (ends with a newline)."""
    rows = "\n".join(f"| `{o}` | `{n}` |" for o, n in moves.items())
    return f"{MOVE_HEADING}\n\n| {_HEADER[0]} | {_HEADER[1]} |\n|---|---|\n{rows}\n"
