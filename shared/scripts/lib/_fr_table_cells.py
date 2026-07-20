"""Markdown row mechanics for the FR-table reader: cells in, escapes out.

Split out of ``fr_table_reader`` when the single-pass tokenizer pushed that
module past the 300-line cap. The seam mirrors the one already used for the
fold map (``fr_fold_map`` semantics / ``_fr_fold_map_parse`` mechanics): this
module knows only how a markdown table ROW becomes cells and how an escape
sequence becomes a character. It knows nothing about requirements, headers,
priorities or removal sections — those are the reader's.

Keeping the seam here is what let the escaping contract be stated, probed and
fixed as one thing. Its counterpart producer is
``shared/scripts/markdown_table.escape_cell``; the two are exact inverses, and
a round-trip probe over both is what found the doubled-backslash defect this
module now handles.
"""

from __future__ import annotations


def split_cells(line: str) -> list[str]:
    """Split one markdown table row into stripped, unescaped cells.

    Splitting and unescaping happen in ONE left-to-right pass, which is what
    makes this the exact inverse of ``markdown_table.escape_cell`` — the
    producer for every machine-written cell in this repo. Two bugs come free
    with the single pass, both found by a round-trip probe against the real
    producer rather than against hand-written escapes:

    * A regex lookbehind for "a pipe not preceded by a backslash" mis-reads
      ``a\\\\|`` — an ESCAPED backslash followed by a REAL separator. It sees the
      backslash, calls the pipe escaped, and silently merges two columns.
      Consuming escape pairs as it goes cannot make that mistake.
    * ``escape_cell`` emits ``\\`` → ``\\\\`` before it emits ``|`` → ``\\|``, so
      undoing only the pipe leaves every backslash in the value doubled. Any
      cell containing a path or a regex came back wrong.

    A backslash that does not begin an escape pair is content and is preserved,
    so a hand-written ``C:\\repo\\spec`` survives intact. The declared cost of
    being the producer's exact inverse: a hand-written literal ``\\\\`` reads as
    one backslash, because that is what the producer means by it.

    One leading and one trailing pipe are dropped; a row whose closing pipe is
    missing still yields its cells (rule 6).
    """
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]

    cells: list[str] = []
    buf: list[str] = []
    ended_on_separator = False
    i, n = 0, len(inner)
    while i < n:
        char = inner[i]
        if char == "\\" and i + 1 < n and inner[i + 1] in "\\|":
            buf.append(inner[i + 1])
            i += 2
            ended_on_separator = False
        elif char == "|":
            cells.append("".join(buf).strip())
            buf = []
            i += 1
            ended_on_separator = True
        else:
            buf.append(char)
            i += 1
            ended_on_separator = False

    tail = "".join(buf).strip()
    if tail or not ended_on_separator:
        cells.append(tail)
    return cells
