"""``@FR`` tag grammar — the reference parser (traceability Spec §4 / R4).

Frozen P1 contract. One concept — the canonical machine token ``@FR-XX.YY`` — with
an idiom per runner. This module is the **reference** parser that proves the
grammar: each accepted form binds to a test; each malformed form becomes an
``invalid_tags`` entry. It is deliberately a *limited, documented* syntax
(structured, **not** a naive repo-wide regex) — the production ``test_links``
collector (campaign TT1) generalises the JS side with a real JS matcher; here we
pin the grammar so the answer key is unambiguous.

Accepted forms (see `references/traceability-tag-grammar.md`):

* **pytest** — ``@pytest.mark.covers("FR-01.03", "FR-01.04")`` — read from the
  Python AST, bound to the decorated function. ``tag_source="pytest_marker"``.
* **TS/JS ``@covers`` comment** — ``// @covers FR-01.03`` on the line *preceding* a
  test, bound to that test. ``tag_source="covers_comment"``.
* **Playwright native tag** — ``test('…', { tag: ['@FR-01.03'] }, …)`` on the test
  declaration line. ``tag_source="native_tag"``.
* **Vitest title suffix** — ``it('does X @FR-01.03', …)``. ``tag_source="title_suffix"``.

A malformed token (``@FR-1.3`` — not two-digit.two-digit; ``@FR01.03`` — no dash)
is recorded in :class:`InvalidTag`, never bound as coverage (R4).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

try:  # Package context — `from lib.fr_tag_grammar import …` (shared/tests).
    from .requirement_model import CANONICAL_FR_RE
except ImportError:  # Loaded by file path (a future plugin collector): no parent package.
    from requirement_model import CANONICAL_FR_RE  # type: ignore

# Closed vocabulary of where a tag was found (mirrors the manifest tag_source enum).
TAG_SOURCES: tuple[str, ...] = (
    "pytest_marker",
    "covers_comment",
    "native_tag",
    "title_suffix",
)

# A *valid* tag token: two-digit.two-digit, dash-delimited (D1). The negative
# lookahead ``(?![\w.-])`` guards the tail so a trailing continuation is rejected
# — ``@FR-01.033``, ``@FR-01.03x`` and ``@FR-01.03.4`` do NOT expose a valid
# ``@FR-01.03`` prefix to a consumer using this exported regex (a plain ``\b``
# would, since ``3`` → ``.`` is a word boundary).
TAG_TOKEN_RE = re.compile(r"@FR-\d{2}\.\d{2}(?![\w.-])")

# A *candidate* (valid OR malformed) tag token, so malformed forms are reported
# instead of silently dropped. Captures the WHOLE token run (``[\w.-]`` includes
# any trailing junk like ``@FR-01.03x`` / ``@FR-01.03.4``) so the canonical check
# rejects it — never accepts a valid-looking prefix and drops the tail.
_TAG_CANDIDATE_RE = re.compile(r"@FR[\w.-]*")
# Bare-id candidate after ``@covers`` (no ``@`` prefix); same whole-token capture.
_COVERS_CANDIDATE_RE = re.compile(r"\bFR[\w.-]*")

# TS/JS surface matchers (limited, documented reference forms).
_COVERS_COMMENT_RE = re.compile(r"//\s*@covers\s+(?P<ids>[^\n]+)")
# ``it(``/``test(`` (and modifiers like .skip/.only/.each) — but NOT ``test.describe(``,
# which is a suite, not a binding target for the reference (describe is out of scope).
_TEST_DECL_RE = re.compile(r"\b(?:it|test)(?:\.(?!describe\b)\w+)?\s*\(\s*(['\"`])(?P<title>.*?)\1")
# The documented "title suffix": one or more @FR tokens at the END of the title.
_TITLE_SUFFIX_RE = re.compile(r"(?P<tags>(?:@FR[\w.-]*\s*)+)$")
_TAG_ARRAY_RE = re.compile(r"tag\s*:\s*\[(?P<body>[^\]]*)\]")


@dataclass(frozen=True)
class TagHit:
    """A tag successfully bound to a test."""

    fr_id: str            # canonical "FR-01.03"
    test: str             # binding: "path::name"
    tag_source: str       # one of TAG_SOURCES
    raw: str              # the raw matched text


@dataclass(frozen=True)
class InvalidTag:
    """A malformed tag that cannot satisfy coverage (R4)."""

    raw: str
    test: str = ""
    reason: str = "non_canonical_fr_id"


@dataclass(frozen=True)
class ParseResult:
    hits: tuple[TagHit, ...] = ()
    invalid: tuple[InvalidTag, ...] = ()


def canonical_fr_id(raw: str) -> str | None:
    """Return the canonical ``FR-XX.YY`` id if ``raw`` (with or without a leading
    ``@``) is canonical, else ``None``."""
    token = raw[1:] if raw.startswith("@") else raw
    return token if CANONICAL_FR_RE.match(token) else None


# ---------------------------------------------------------------------------
# Python (pytest) — AST, robust binding
# ---------------------------------------------------------------------------

def _is_covers_marker(dec: ast.expr) -> bool:
    """True for a ``@pytest.mark.covers(...)`` decorator call."""
    if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
        return False
    func = dec.func
    if func.attr != "covers" or not isinstance(func.value, ast.Attribute):
        return False
    mark = func.value
    return mark.attr == "mark" and isinstance(mark.value, ast.Name) and mark.value.id == "pytest"


def parse_python(source: str, path: str = "") -> ParseResult:
    """Parse ``@pytest.mark.covers`` markers from Python source via the AST."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ParseResult()

    hits: list[TagHit] = []
    invalid: list[InvalidTag] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        test = f"{path}::{node.name}"
        for dec in node.decorator_list:
            if not _is_covers_marker(dec):
                continue
            for arg in dec.args:
                if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                    invalid.append(InvalidTag(raw=ast.dump(arg), test=test, reason="non_string_arg"))
                    continue
                canon = canonical_fr_id(arg.value)
                if canon:
                    hits.append(TagHit(canon, test, "pytest_marker", arg.value))
                else:
                    invalid.append(InvalidTag(raw=arg.value, test=test))
    return ParseResult(tuple(hits), tuple(invalid))


# ---------------------------------------------------------------------------
# TS/JS — limited, documented line matcher
# ---------------------------------------------------------------------------

def _classify_bare_ids(chunk: str, test: str, source: str) -> tuple[list[TagHit], list[InvalidTag]]:
    """Classify comma/space-separated bare FR ids after ``@covers``."""
    hits: list[TagHit] = []
    invalid: list[InvalidTag] = []
    for raw in _COVERS_CANDIDATE_RE.findall(chunk):
        canon = canonical_fr_id(raw)
        if canon:
            hits.append(TagHit(canon, test, source, raw))
        else:
            invalid.append(InvalidTag(raw=raw, test=test))
    return hits, invalid


def _classify_at_tokens(chunk: str, test: str, source: str) -> tuple[list[TagHit], list[InvalidTag]]:
    """Classify ``@FR-…`` candidate tokens inside ``chunk``."""
    hits: list[TagHit] = []
    invalid: list[InvalidTag] = []
    for raw in _TAG_CANDIDATE_RE.findall(chunk):
        canon = canonical_fr_id(raw)
        if canon:
            hits.append(TagHit(canon, test, source, raw))
        else:
            invalid.append(InvalidTag(raw=raw, test=test))
    return hits, invalid


def _title_suffix_tags(title: str, test: str) -> tuple[list[TagHit], list[InvalidTag]]:
    """Classify @FR tokens that occur as a **suffix** of the test title only.

    A token in the middle/prefix of a title is ambiguous and left informational
    (not bound) — matching the documented "title suffix" form.
    """
    m = _TITLE_SUFFIX_RE.search(title.rstrip())
    if not m:
        return [], []
    return _classify_at_tokens(m.group("tags"), test, "title_suffix")


def parse_ts_js(source: str, path: str = "") -> ParseResult:
    """Parse the three TS/JS reference forms, binding each tag to a test.

    Limited by design (structured, not a general JS parser):

    * A ``// @covers`` comment binds to the ``it(``/``test(`` on the **same line**
      (a trailing comment) or on the **immediately following** line (a leading
      comment). A leading comment that is not immediately adjacent to a test does
      **not** bind — its valid ids are informational (dropped), but its *malformed*
      ids are still recorded in ``invalid_tags`` (AC2: malformed forms are always
      surfaced, bound or not).
    * Native ``tag:`` arrays and title *suffixes* bind to the test on their own
      declaration line.
    * Binding targets are ``it(``/``test(`` only — ``describe``/suite-level tag
      propagation is a production-collector feature, out of scope for the reference.
    """
    hits: list[TagHit] = []
    invalid: list[InvalidTag] = []
    covers_prev: str | None = None  # leading @covers ids from the immediately preceding line

    def flush_unbound(ids: str | None) -> None:
        # A leading @covers that never bound: valid ids are informational (dropped),
        # malformed ids are still recorded as invalid_tags (unbound, test="").
        if ids is not None:
            _, iv = _classify_bare_ids(ids, "", "covers_comment")
            invalid.extend(iv)

    for line in source.splitlines():
        comment = _COVERS_COMMENT_RE.search(line)
        same_line_covers = comment.group("ids") if comment else None
        decl = _TEST_DECL_RE.search(line)

        if decl:
            title = decl.group("title")
            test = f"{path}::{title}"
            for chunk in (covers_prev, same_line_covers):  # leading (prev line) + trailing (this line)
                if chunk is not None:
                    h, iv = _classify_bare_ids(chunk, test, "covers_comment")
                    hits += h
                    invalid += iv
            covers_prev = None

            array = _TAG_ARRAY_RE.search(line)
            if array:
                h, iv = _classify_at_tokens(array.group("body"), test, "native_tag")
                hits += h
                invalid += iv

            h, iv = _title_suffix_tags(title, test)
            hits += h
            invalid += iv
        elif same_line_covers is not None:
            flush_unbound(covers_prev)          # an older pending comment is superseded
            covers_prev = same_line_covers      # hold this leading comment for the next line
        else:
            flush_unbound(covers_prev)          # a non-comment, non-decl line breaks the pending comment
            covers_prev = None

    flush_unbound(covers_prev)                  # a trailing pending comment at EOF
    return ParseResult(tuple(hits), tuple(invalid))


_PY_SUFFIXES = (".py",)
_TS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts")


def parse_source(path: str, source: str) -> ParseResult:
    """Dispatch to the pytest or TS/JS parser by file suffix."""
    lower = path.lower()
    if lower.endswith(_PY_SUFFIXES):
        return parse_python(source, path)
    if lower.endswith(_TS_SUFFIXES):
        return parse_ts_js(source, path)
    return ParseResult()


__all__ = [
    "TAG_SOURCES",
    "TAG_TOKEN_RE",
    "TagHit",
    "InvalidTag",
    "ParseResult",
    "canonical_fr_id",
    "parse_python",
    "parse_ts_js",
    "parse_source",
]
