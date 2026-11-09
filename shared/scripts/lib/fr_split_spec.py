"""The spec.md half of ``fr_split``: cut one FR into several, as pure text-to-text (atomic-frs U2).

``split_spec(text, grouping, taken)`` returns the new spec text and ``{old ac id: new ac id}``. It only MOVES criteria:
their wording is byte-for-byte what it was, their number is kept (``FR-01.11/AC21`` -> ``FR-01.22/AC21``), so a
criterion is never reworded or renumbered. A shape it cannot cut safely (an unmarked criterion, prose between criteria)
raises :class:`SplitError` instead of guessing. The conservation check lives in :mod:`lib.fr_split_check`.

Grouping (``dict``)::

    {"source": "FR-01.11",
     "remaining": {"title": "...", "description": "..."},          # optional: new wording for the FR that stays
     "parts": [{"title": "...", "description": "...", "acs": [21, 22, 23],
                "priority": "Must", "basis": "code", "layers": "unit (inferred)"}]}   # last three optional (default: the source's)
"""

from __future__ import annotations

import re

from lib._fr_table_cells import split_cells
from lib._fr_table_columns import header_map
from lib.ac_move_map import MOVE_HEADING, parse_move_map, render_section

__all__ = ["SplitError", "split_spec", "taken_fr_numbers"]

_AC_MARK = re.compile(r"^-\s+(?:\([A-Z]\)\s+)?\[AC(\d+)\]")
_ANY_BULLET = re.compile(r"^-\s")
_HEADING = re.compile(r"^(#{1,4})\s")
_FR_ID = re.compile(r"FR-(\d{2})\.(\d{2,})")
NL = "\n"


class SplitError(ValueError):
    """The grouping or the spec shape cannot be cut safely; nothing was changed."""


def taken_fr_numbers(text: str, major: str) -> set[int]:
    """Every FR number used in group ``major`` anywhere a requirement can be named (table rows incl. removed, headings, fold/move maps)."""
    used: set[int] = set()
    for line in text.splitlines():
        if line.startswith(("|", "#")):
            used.update(int(n) for m, n in _FR_ID.findall(line) if m == major)
    return used


def _cell(text: str) -> str:
    return " " + " ".join(str(text).replace("|", "\\|").split()) + " "


def _find_table(lines: list[str], fr: str) -> tuple[int, int, dict[str, int]]:
    """``(source row index, last FR row index, column map)`` of the requirements table holding ``fr``."""
    row = next((i for i, ln in enumerate(lines) if re.match(rf"^\|\s*{re.escape(fr)}\s*\|", ln)), -1)
    if row < 0:
        raise SplitError(f"{fr} has no row in a requirements table")
    top = row
    while top > 0 and lines[top - 1].startswith("|"):
        top -= 1
    hdr = next((i for i in range(top, row) if header_map(split_cells(lines[i]))), -1)
    cols = header_map(split_cells(lines[hdr])) if hdr >= 0 else None
    if not cols or not {"id", "name", "description"} <= set(cols):
        raise SplitError("the requirements table needs ID, Name and Description columns to cut it")
    if len(split_cells(lines[row])) != len(split_cells(lines[hdr])):
        raise SplitError(f"the row of {fr} does not have as many cells as its table header")
    last = row
    while last + 1 < len(lines) and lines[last + 1].startswith("|"):
        last += 1
    return row, last, cols


def _find_section(lines: list[str], fr: str) -> tuple[int, int, int]:
    """``(anchor/heading start, heading index, end)``: the block of ``fr``'s criteria; ``end`` is the next anchor or heading."""
    head = next((i for i, ln in enumerate(lines) if re.match(rf"^#{{2,4}}\s+{re.escape(fr)}\b", ln)), -1)
    if head < 0:
        raise SplitError(f"{fr} has no criteria section")
    start = head - 1 if head and lines[head - 1].startswith("<a id=") else head
    level = len(re.match(r"^#+", lines[head]).group(0))  # type: ignore[union-attr]
    end = len(lines)
    for i in range(head + 1, len(lines)):
        h = _HEADING.match(lines[i])
        if lines[i].startswith("<a id=") or (h and len(h.group(1)) <= level):
            end = i
            break
        if h:
            raise SplitError(f"{fr} has a sub-heading ({lines[i].strip()[:40]!r}); a cut cannot tell which part it belongs to")
    return start, head, end


def _bullets(lines: list[str], head: int, end: int) -> tuple[list[str], dict[int, list[str]]]:
    """``(lead, {ac number: bullet lines})`` of one section; refuses any shape it cannot move bullet-for-bullet."""
    lead: list[str] = []
    found: dict[int, list[str]] = {}
    cur = 0
    for ln in lines[head + 1:end]:
        m = _AC_MARK.match(ln)
        if m:
            cur = int(m.group(1))
            if cur in found:
                raise SplitError(f"criterion AC{cur:02d} appears twice in the section")
            found[cur] = [ln]
        elif _ANY_BULLET.match(ln):
            raise SplitError("the section has a criterion without an [ACnn] marker; mint ids first (lib.ac_identity)")
        elif cur and (ln.startswith(" ") or not ln.strip()):
            found[cur].append(ln)
        elif not cur:
            lead.append(ln)
        elif ln.strip():
            raise SplitError(f"unexpected text between or after the criteria: {ln.strip()[:60]!r}")
    for body in found.values():
        while body and not body[-1].strip():
            body.pop()
    return lead, found


def _validate(grouping: dict, have: set[int]) -> None:
    parts = grouping.get("parts") or []
    if not parts:
        raise SplitError("the grouping has no parts")
    rem = grouping.get("remaining")
    if rem is not None and (not str(rem.get("title", "")).strip() or not str(rem.get("description", "")).strip()):
        raise SplitError("'remaining' needs a title and a description")
    seen: set[int] = set()
    for p in parts:
        acs = [int(a) for a in p.get("acs", [])]
        if len(acs) < 3:
            raise SplitError(f"part {p.get('title')!r} has {len(acs)} criteria; a part needs at least three (stop rule, fr-authoring 3c)")
        if len(set(acs)) != len(acs) or seen & set(acs):
            raise SplitError(f"part {p.get('title')!r} lists a criterion twice or one another part already owns")
        if set(acs) - have:
            raise SplitError(f"part {p.get('title')!r} names criteria the source does not have: {sorted(set(acs) - have)}")
        if sum(1 for q in parts if " ".join(str(q.get("title", "")).split()) == " ".join(str(p.get("title", "")).split())) > 1:
            raise SplitError(f"two parts are both called {p.get('title')!r}")
        if not str(p.get("title", "")).strip() or not str(p.get("description", "")).strip():
            raise SplitError("every part needs a title and a description")
        seen |= set(acs)
    if len(have - seen) < 3:
        raise SplitError(f"the source would keep {len(have - seen)} criteria; it must keep at least three (or split into parts and retire it by hand)")


def split_spec(text: str, grouping: dict, taken: set[int] | None = None) -> tuple[str, dict[str, str], list[str]]:
    """``(new spec text, {old ac id: new ac id}, [new FR ids])`` for ``grouping``; raises :class:`SplitError` on anything unsafe."""
    crlf = "\r\n" in text
    lines = text.replace("\r\n", "\n").split("\n")
    src = grouping.get("source", "")
    m = _FR_ID.fullmatch(src)
    if not m:
        raise SplitError(f"source {src!r} is not an FR id")
    major = m.group(1)
    used = set(taken or ()) | taken_fr_numbers("\n".join(lines), major)
    row, last, cols = _find_table(lines, src)
    start, head, end = _find_section(lines, src)
    lead, found = _bullets(lines, head, end)
    _validate(grouping, set(found))
    if last >= start:
        raise SplitError("the requirements table must come before the criteria sections")

    new_ids, nxt = [], max(used, default=0)
    for _ in grouping["parts"]:
        nxt += 1
        if nxt > 99:
            raise SplitError("group %s has no free two-digit requirement number left" % major)
        new_ids.append(f"FR-{major}.{nxt:02d}")
    moves = {f"{src}/AC{int(a):02d}": f"{fr}/AC{int(a):02d}" for fr, p in zip(new_ids, grouping["parts"]) for a in p["acs"]}
    if set(moves.values()) & set(parse_move_map("\n".join(lines)).values()):
        raise SplitError("a target id is already in the AC-Move-Map")

    moved = {int(a) for p in grouping["parts"] for a in p["acs"]}
    sep = re.match(r"^#{2,4}\s+FR-\d{2}\.\d{2,}(\s*[—–:-]+\s*)", lines[head])
    level = re.match(r"^(#{2,4})", lines[head]).group(1)  # type: ignore[union-attr]
    dash = sep.group(1) if sep else " — "
    kept = [ln for a in found if a not in moved for ln in found[a]]  # document order, as written
    section = lines[start:head + 1] + lead + kept
    if (rem := grouping.get("remaining")):
        section[head - start] = f"{level} {src}{dash}" + " ".join(str(rem['title']).split())
    for fr, p in zip(new_ids, grouping["parts"]):
        own = {int(x) for x in p["acs"]}
        body = [ln for a in found if a in own for ln in found[a]]
        title = " ".join(str(p["title"]).split())
        section += ["", f'<a id="fr-{fr[3:].replace(".", "")}"></a>', f"{level} {fr}{dash}{title}", ""] + body
    out = lines[:start] + section + [""] + lines[end:]

    # the table: one row per part after the last FR row; the source row is reworded when asked
    base = [_cell(c) for c in split_cells(lines[row])]
    new_rows = []
    for fr, p in zip(new_ids, grouping["parts"]):
        cells = list(base)
        cells[cols["id"]] = _cell(fr)
        cells[cols["name"]] = _cell(p["title"])
        cells[cols["description"]] = _cell(p["description"])
        for key in ("priority", "basis", "layers"):
            if p.get(key) and key in cols:
                cells[cols[key]] = _cell(p[key])
        new_rows.append("|" + "|".join(cells) + "|")
    if rem:
        cells = list(base)
        cells[cols["name"]], cells[cols["description"]] = _cell(rem["title"]), _cell(rem["description"])
        out[row] = "|" + "|".join(cells) + "|"
    out[last + 1:last + 1] = new_rows
    joined = _with_move_map(NL.join(out), moves)
    return (joined.replace(NL, "\r\n") if crlf else joined), moves, new_ids


def _with_move_map(text: str, moves: dict[str, str]) -> str:
    """Append ``moves`` to the ``## AC-Move-Map`` section, creating it before ``## Provenance`` (or at the end) when absent."""
    lines = text.split("\n")
    idx = next((i for i, ln in enumerate(lines) if ln.strip().lower() == MOVE_HEADING.lower()), -1)
    rows = [f"| `{o}` | `{n}` |" for o, n in moves.items()]
    if idx < 0:
        block = render_section(moves).rstrip("\n").split("\n") + [""]
        at = next((i for i, ln in enumerate(lines) if ln.strip() == "## Provenance"), -1)
        if at < 0:
            return text.rstrip("\n") + "\n\n" + "\n".join(block)
        lines[at:at] = block
        return "\n".join(lines)
    stop = idx + 1
    while stop < len(lines) and not lines[stop].startswith("#"):
        stop += 1
    tbl = max((i for i in range(idx, stop) if lines[i].startswith("|")), default=-1)
    if tbl < 0:
        raise SplitError("the AC-Move-Map section has no table")
    lines[tbl + 1:tbl + 1] = rows
    return "\n".join(lines)
