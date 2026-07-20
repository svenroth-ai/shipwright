"""No display literal may look like a missing comma (campaign S7).

One structural rule, enforced by AST over every file this campaign step added:
**no list, tuple, set or dict display may contain implicitly concatenated string
literals.**

CodeQL raised seven "implicit string concatenation — maybe missing a comma?"
warnings on hand-wrapped operator output. Every one was intentional. That is the
problem: intentional and accidental are byte-identical in that shape, and the
accident silently merges two lines of output — the defect class this whole
change exists to remove. The fix was to delete the shape; body text is written
as one logical string and wrapped at runtime by ``_para`` / ``_fold``.

Detection counts string TOKENS, not line spans. The first version measured
``end_lineno > lineno`` and was wrong in both directions: it missed
``["a" "b", "c"]`` — the single-line form, and the *more* likely accident, since
nobody hand-breaks a forty-character string — while it would have false-flagged
a triple-quoted string, which is one literal. ``fr_history_render`` contains a
live single-line display (``["", "  + introduced …"]``) that the old detector
could not have protected.

Dict displays are covered too: the ``--json`` payload is a dict literal, where a
dropped comma merges two fields of a machine contract rather than two lines of
prose.
"""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]

#: Where this campaign step put code, and the filename rule that identifies it.
#: Membership is DERIVED, never hand-listed: two hand-maintained copies of "the
#: S7 files" had already drifted apart after a single round, each missing a
#: module the other had. A glob cannot drift.
_ROOTS = (
    "shared/scripts/lib",
    "shared/scripts/tools",
    "shared/scripts/tests",
    "integration-tests",
)
_NAME_MARKERS = ("fr_history", "fr_change_history")


def s7_sources() -> list[Path]:
    """Every Python file this campaign step added or rewrote."""
    found: list[Path] = []
    for root in _ROOTS:
        for path in sorted((_REPO / root).glob("*.py")):
            if any(marker in path.name for marker in _NAME_MARKERS):
                found.append(path)
    return found


def _string_token_count(source: str, node: ast.AST) -> int:
    """How many string literals the element's own source spans.

    Wrapped in parentheses before tokenizing so an indented element lifted out
    of a display is still a valid standalone expression.
    """
    segment = ast.get_source_segment(source, node)
    if segment is None:
        return 1
    count = 0
    try:
        for tok in tokenize.generate_tokens(io.StringIO(f"({segment})").readline):
            if tok.type == tokenize.STRING:
                count += 1
            elif tok.type == getattr(tokenize, "FSTRING_START", -1):
                # 3.12+ tokenizes f-strings as START/MIDDLE/END — one START per
                # literal, so f"a" f"b" counts as two, exactly like "a" "b".
                count += 1
    except tokenize.TokenError:  # pragma: no cover - defensive
        return 1
    return max(count, 1)


def _is_explicitly_grouped(lines: list[str], node: ast.AST) -> bool:
    """True when the literal is wrapped in its own parentheses.

    This is the distinction that matters, and it is not "does it span lines".
    The hazard is a concatenation whose neighbours are **comma-separated
    siblings**: in ``["a" "b", "c"]`` a dropped comma silently merges two
    elements. A parenthesised group has no sibling to merge with — adding a
    comma inside it produces a tuple, which fails loudly at the point of use.

    So ``("a" "b")`` as a dict value is an explicit statement of intent and
    stays permitted, exactly as the review described. Flagging it would have
    forced a rewrite of readable, unambiguous code to satisfy a rule aimed at a
    different shape.

    Scans ACROSS lines, because the opening parenthesis of a wrapped value sits
    on the line above the first literal::

        "reason": (
            "first part "
            "second part"
        ),

    A same-line-only check misses that and reports the readable, unambiguous
    form as a defect — which the first version of this function did.
    """
    starts = _line_start_offsets(lines)
    begin = starts[node.lineno - 1] + node.col_offset
    end = starts[node.end_lineno - 1] + node.end_col_offset
    text = "\n".join(lines)

    i = begin - 1
    while i >= 0 and text[i].isspace():
        i -= 1
    j = end
    while j < len(text) and text[j].isspace():
        j += 1
    return i >= 0 and text[i] == "(" and j < len(text) and text[j] == ")"


def _line_start_offsets(lines: list[str]) -> list[int]:
    """Absolute offset of each line within ``"\\n".join(lines)``."""
    offsets = [0]
    for line in lines[:-1]:
        offsets.append(offsets[-1] + len(line) + 1)
    return offsets


def implicit_concatenations(source: str) -> list[int]:
    """Line numbers of ambiguously concatenated literals inside any display."""
    lines = source.splitlines()
    found: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            elements: list = list(node.elts)
        elif isinstance(node, ast.Dict):
            elements = [x for x in (*node.keys, *node.values) if x is not None]
        else:
            continue
        for elt in elements:
            if not isinstance(elt, (ast.Constant, ast.JoinedStr)):
                continue
            if _string_token_count(source, elt) <= 1:
                continue
            if _is_explicitly_grouped(lines, elt):
                continue
            found.append(elt.lineno)
    return sorted(found)


@pytest.mark.parametrize(
    "path", s7_sources(), ids=lambda p: p.name,
)
def test_no_display_contains_implicitly_concatenated_literals(path):
    lines = implicit_concatenations(path.read_text(encoding="utf-8"))
    assert not lines, (
        f"{path.name} has adjacent string literals inside a collection display "
        f"at line(s) {lines}. That is indistinguishable from a missing comma, "
        f"and on output lines a missing comma silently merges two of them. "
        f"Write the text as one string and let _para/_fold wrap it."
    )


def test_the_file_set_is_discovered_and_covers_the_known_modules():
    """A glob that silently matched nothing would make the guard vacuous."""
    names = {p.name for p in s7_sources()}
    assert len(names) >= 15, f"only {len(names)} S7 files discovered: {sorted(names)}"
    for anchor in (
        "fr_history_render.py",
        "fr_change_history.py",
        "_fr_history_events.py",
        "fr_history.py",
        "test_fr_history_display_lists.py",
    ):
        assert anchor in names, f"{anchor} is not covered by the discovery rule"


@pytest.mark.parametrize("snippet,expected", [
    # The single-line form the previous detector missed entirely.
    ('x = ["a" "b", "c"]\n', [1]),
    # The multi-line form it did catch.
    ('x = [\n    "first half "\n    "second half",\n    "next",\n]\n', [2]),
    # f-strings concatenate implicitly too.
    ('x = [f"a{v}" f"b", "c"]\n', [1]),
    # Dict values — the --json payload shape.
    ('x = {"k": "a" "b"}\n', [1]),
    # Dict keys.
    ('x = {"a" "b": 1}\n', [1]),
])
def test_the_detector_fires_on_every_concatenated_form(snippet, expected):
    assert implicit_concatenations(snippet) == expected


@pytest.mark.parametrize("snippet", [
    'x = ["ab", "c"]\n',
    'x = [f"a{v}", "c"]\n',
    # One literal, not two — the previous line-span detector false-flagged this.
    'x = ["""a\nb""", "c"]\n',
    'x = {"k": "ab"}\n',
    # Explicit concatenation states its intent and is not the ambiguous shape.
    'x = ["a" + "b", "c"]\n',
    # Parenthesised groups have no sibling to merge with; a stray comma inside
    # one makes a tuple, which fails loudly rather than silently.
    'x = [("a" "b"), "c"]\n',
    'x = {"k": ("a" "b")}\n',
    # The wrapped form the data module uses: the "(" sits a line above.
    'x = {\n    "k": (\n        "first "\n        "second"\n    ),\n}\n',
])
def test_the_detector_does_not_fire_on_unambiguous_forms(snippet):
    assert implicit_concatenations(snippet) == []
