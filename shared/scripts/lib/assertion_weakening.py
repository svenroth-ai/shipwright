"""Did this diff make the test suite prove less?

The AC-6 hard rule of the `main` self-heal (FR-01.19), in code rather than in
prose: a branch that repairs itself must never do it by adjusting the test until
it is green.

**AST, not diff text.** The comparison is between the *parsed* before and after
of each changed test file. Text diffing cannot distinguish a moved assertion
from a deleted one, and reading `==` → `>=` out of a unified diff is a tar pit
(external plan review, round 1).

**What is blocked** is unambiguous loss: fewer assertions in a test that still
exists, a test/class/file that no longer exists, `skip`/`skipif`/`xfail`
(Python) or `.skip`/`.todo`/`xit`/`xtest`/`xdescribe` (JS/TS) newly applied, an
*after* revision that will not parse (or, for JS/TS, whose brackets do not
balance), and a changed test file in a language neither reader covers. A
newly-applied JS/TS `.only` counts too, on every OTHER test in the file — not
on the `.only`'d one, which is the one that still runs. `.only` is real Jest/
Vitest's best-known footgun: it makes every sibling test/describe in that
file skip at runtime with no mark on the sibling itself, so treating it as
inert (an earlier revision of this scanner did) let a repair silence a
failing neighbor without ever touching its body — the AC-6 failure mode this
file exists to catch, reached sideways (doubt review).

**Two readers, one contract.** Python is read with `ast` — a real parser.
JS/TS (`.test.`/`.spec.` name segments on `.ts`/`.tsx`/`.js`/`.jsx`/`.mts`/
`.mjs`/`.cts`/`.cjs`) is read with a bracket-balancing scanner instead: one
pass over the source (skipping string and comment contents) matches every
`(`/`{`/`[`, then `describe`/`it`/`test` call heads and the `expect`/`assert`
calls nested inside them are located through that bracket map. That is enough
to count assertions, catch a newly-applied skip, resolve `.each(table)(...)`
or `` .each`table`(...) `` (Jest/Vitest's `@pytest.mark.parametrize`
equivalent, in either of its two argument forms) to the call that actually
carries the test body, and see a `describe.skip` swallow its children — but
it is a scanner, not a parser. A single resolver (`_js_resolve_test_call`,
fed by `_js_scan_chain`) decides what counts as a call the scanner
understands; a chain outside the small set it implements (`.skip`, `.only`,
`.todo`, `.each`, and `.skip.each`/`.only.each`/`.todo.each`), a chain
reachable only through a computed-access segment (`test['skip'](...)`), or
a chain inside that set that still doesn't resolve to an actual call, is
`unparseable`, same as an unparseable Python revision — not silently waved
through. Chain-scanning tolerates whitespace, newlines and comments between
segments (`test\n  .each(...)`, `test/* eslint */.skip(...)`), and a name
occurrence inside a string or comment is not mistaken for a real call
either. (Three rounds of external spec review found daylight here: a second,
independently-written "is this supported" regex that could drift from the
resolver; that resolver requiring `.each`'s table to be parenthesized when
Jest/Vitest also allows a tagged template; and the chain regex requiring
strict adjacency, so a line-broken or computed-access chain collapsed to
"nothing chained" instead of failing closed. There is now exactly one place
each of those decisions gets made.)

**What is only reported** is a changed assertion *expression*. Updating a count
another pull request legitimately changed is the commonest honest repair; a rule
that blocked it would block the mechanism this exists to serve. The reviewer
sees it and the pull request must say why the new value is the truth.

**Stated limit, not implied completeness.** A relaxation that keeps the shape
(`== 5` → `== 4`) lands in the reported bucket, not the blocked one. This is a
conservative floor on mechanical coverage loss — the governing norm stays a rule
the agent is held to, and this file does not pretend otherwise.

Two further JS/TS limits, named rather than left implicit: a dynamic test
name (`it(caseName, fn)`, not a string literal) has no recoverable identity
across a diff without a real parser, and two statically-named tests can
legitimately share one literal title (the same `it('returns 200', ...)`
reused under different `describe` blocks) — both are keyed the same way,
pooled into one aggregate entry per identity instead of being individually
ordinal-keyed. An ordinal key ("the Nth test with this identity") was tried
first and rejected (doubt review, rounds 2 and 4): a decoy test inserted
earlier in the same diff can reoccupy a shifted test's ordinal and launder
its real assertion loss into a comparison against unrelated content — round 2
found this for dynamic names, round 4 found the identical exposure still
open for duplicate literal names. Pooling is order-independent, so a decoy
inserted elsewhere can no longer hide a real loss the way an ordinal key did.
**Named limit, not closed:** pooling can still soften a blocking
`assertions_removed` into a merely-reported `assertion_changed` by padding
the aggregate count back up, and if a decoy's own assertion signature is
textually IDENTICAL to the one actually removed (realistic for table-driven
tests sharing boilerplate assertions like `expect(status).toBe(200)`), the
pooled before/after sets can come out equal and the loss is fully invisible —
content-only identity cannot tell "this assertion moved" from "this assertion
was deleted and an unrelated one happens to read the same" (doubt review,
round 3). This is a stated residual, not a claim that pooling makes a silent
`clear` impossible. A pooled identity also tracks how many source `it`/`test`
calls fed it (`_Test.instance_count`); a DECREASE is reported (not blocked —
a harmless duplicate-test merge is one legitimate cause) because it is
exactly how a mark or an assertion can move onto a surviving pooled instance
without changing any aggregate count the other checks can see — e.g. removing
an empty-bodied `.skip` stub in the same edit that newly `.skip`'s an
assertion-bearing sibling of the same title moves the "skip" mark within the
pool (flat count) while contributing zero assertion delta (doubt review,
round 6). This closes the mechanism the round-3 residual above does not
cover (that one is about a decoy ADDED with colliding content; this one is
about an instance REMOVED while carrying a mark) but not a third: a pool
whose SURVIVING instances swap which one carries a mark, with instance count,
aggregate mark count and aggregate assertion count all unchanged (doubt
review, round 7 — e.g. two same-titled tests trading which one is `.skip`'d,
their assertion bodies otherwise untouched). `_Test.instances` closes this
one too, WITHOUT the false-positive risk a similarity-based pairing would
carry: each entry keeps its exact `(assertions, marks)` snapshot instead of
being flattened away, and `_relocated_mark_findings` recovers exact identity
per CONTENT KEY — a key that occurs exactly once on both sides is matched
and its marks compared directly; a key that is duplicated on either side, or
whose content changed, is simply skipped for THIS check (left to the
existing aggregate checks) rather than guessed at. A legitimate one-test-
split-into-two refactor necessarily changes at least one instance's exact
content, so its key is skipped instead of misfiring (doubt review, round 8),
unlike an ordinal key (rounds 2/4) or a similarity-based pairing, both
rejected for being gameable or over-eager respectively.

Matching a key in isolation is not the same as trusting it in isolation,
though, and two more rounds sharpened that gap. Checking each unambiguous
key independently and blocking on any that gained a mark (a first attempt at
this) let an unrelated duplicate decoy, or an ordinary unrelated edit to a
completely different same-titled sibling, blind detection of an otherwise
cleanly-matchable swap elsewhere in the pool (doubt review, round 9) — but
blocking on every isolated unambiguous key regardless of the REST of the
pool cuts the other way just as badly: if some OTHER key in the pool is
ALSO ambiguous or changed, an unrelated edit that happens to land on
coincidentally-identical text can be misread as "this exact instance
persisted and gained a mark," which is a false BLOCK of a diff that
introduced no weakening at all (doubt review, round 10) — the one failure
mode this file's stated design (`What is blocked is unambiguous loss`)
explicitly rules out, and strictly worse than the false negative it would
have replaced, given that a wrongly-blocked repair is this file's entire
reason for existing. The resolution: a relocated mark BLOCKS only when the
WHOLE pool's content is CONSERVED (before/after occurrence counts are
identical, key for key — nothing added, nothing removed, anywhere in the
pool) and is merely REPORTED (`pooled_mark_possibly_relocated`) whenever
something was genuinely added or removed elsewhere in the same pool, since a
coincidental collision with THAT can no longer be ruled out. A duplicate that
is merely present at the same count on both sides is not itself a source of
new or vanished text, so it does not, on its own, demote an otherwise-
unambiguous swap (doubt review, round 11 — an earlier version of this gate
required every count to be exactly 1, which was safe but stricter than
necessary). What survives as the honest floor is exactly: the SPECIFIC two
instances trading a mark must themselves have IDENTICAL assertion content
for the swap to be invisible (no exact key exists to hang the comparison on)
— the same content-collision residual round 3 already named, now scoped to
the swapping pair itself rather than the whole pool. And the bracket scanner
has no notion of a
JS regex literal (`` /\\(/ ``), so one containing a lone bracket character with no
in-literal match can desync the scanner — traced to fail in the safe
direction (a spurious `unparseable` on an untouched file), consistent with
this file's conservative-floor default, not to a silent miss (doubt review;
unproven in the unsafe direction, not ruled out either).
"""

from __future__ import annotations

import ast
import bisect
import re
from collections import Counter
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

#: Names that switch a test off wherever they are applied.
_SKIP_MARKS = frozenset({"skip", "skipif", "xfail"})
#: Callables whose invocation inside a body switches the test off from within.
_SKIP_CALLS = frozenset({"skip", "xfail"})
#: `unittest`-style assertions, counted alongside bare `assert`.
_ASSERT_METHOD_PREFIX = "assert"
#: Context managers that assert a raise/warn happened.
_ASSERTING_CONTEXTS = frozenset({"raises", "warns", "deprecated_call"})

#: Extensions the JS/TS bracket scanner will attempt (see `is_js_test_file`).
_JS_TEST_EXTENSIONS = (
    ".ts", ".tsx", ".js", ".jsx", ".mts", ".mjs", ".cts", ".cjs",
)


@dataclass(frozen=True)
class FileChange:
    """One file's before/after content, as `git diff --name-status` saw it."""

    status: str  # A | M | D | R
    path: str
    old_path: str | None = None
    before: str | None = None
    after: str | None = None


@dataclass(frozen=True)
class Finding:
    kind: str
    blocking: bool
    subject: str
    detail: str


@dataclass(frozen=True)
class _Test:
    qualname: str
    assertions: tuple[str, ...]
    #: A MULTISET (sorted, repeats kept), not a set. A single Python test or
    #: unpooled JS test carries at most one occurrence of a given mark, so
    #: this behaves exactly like a set there — but a pooled JS entry (see
    #: `_js_collect`) can carry the SAME mark from several distinct pooled
    #: instances, and only a multiset lets `_diff_tests` tell "a mark that
    #: was already present somewhere in the pool" from "a mark that just
    #: appeared on one MORE pooled instance than before" (doubt review,
    #: round 5).
    marks: tuple[str, ...]
    #: How many source `it`/`test` calls fed this entry — always 1 for a
    #: Python test or an unpooled JS test (one call, one entry), but for a
    #: pooled JS identity (see `_js_collect`) it can be more than one. A
    #: DECREASE here between before/after means a same-identity test
    #: instance disappeared from the pool — mark- and assertion-count
    #: comparisons alone cannot rule out that its mark was reassigned to a
    #: SURVIVING instance (e.g. an empty-bodied `.skip` stub removed while an
    #: assertion-bearing sibling of the same title is newly `.skip`'d in the
    #: same edit): the stub's zero assertions vanish without moving the
    #: assertion count, and the skip MARK's count stays flat because it
    #: simply relocated within the pool instead of accumulating — a fully
    #: silent `clear` with no code-side signal otherwise (doubt review,
    #: round 6). Tracking this count turns that into a reported finding.
    instance_count: int
    #: One `(assertions, marks)` snapshot per source `it`/`test` call that
    #: fed this entry, kept alongside the flattened aggregates above instead
    #: of being discarded at merge time. This is what lets `_diff_tests`
    #: (`_relocated_mark_findings`) recover EXACT per-instance identity, PER
    #: CONTENT KEY: any assertion tuple that occurs exactly once on both the
    #: before and after side is an unambiguous 1:1 match on its own — no
    #: split, no merge, no edit to what THAT instance asserts — so a mark
    #: that moved between two otherwise-identical instances is no longer
    #: invisible just because the pool's aggregates stayed flat (doubt
    #: review, round 8, closing round 7 — a legitimate test split necessarily
    #: changes at least one instance's exact content, so its key is simply
    #: skipped rather than misfiring). But a matched key is trustworthy only
    #: when the WHOLE POOL is a clean bijection: checking each unambiguous
    #: key in isolation once let an unrelated decoy or sibling edit blind a
    #: real swap elsewhere (round 9), and then let a coincidental text
    #: collision with an unrelated edit be misread as the same instance
    #: persisting — a false BLOCK, worse than the silence it replaced given
    #: this file's stated rule that only unambiguous loss blocks (doubt
    #: review, round 10). So a relocated mark blocks only when the pool's
    #: content is fully CONSERVED (before/after occurrence counts identical,
    #: key for key — nothing added or removed anywhere), and is merely
    #: reported when something genuinely added or removed elsewhere makes a
    #: coincidental collision possible. A duplicate present at the same count
    #: on both sides doesn't itself demote an otherwise-unambiguous swap —
    #: requiring every count to be exactly 1 (an earlier version) was safe
    #: but needlessly stricter (doubt review, round 11). The one case still
    #: irreducible either way: the SPECIFIC two instances trading a mark are
    #: themselves content-identical, so no unique key exists to hang the
    #: comparison on at all — the same residual round 3 named.
    instances: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]


def is_test_file(path: str) -> bool:
    """Only files pytest would collect as tests are examined.

    A production `assert` is not a test assertion; counting it would block
    ordinary refactors that happen to drop one.
    """
    name = (path or "").replace("\\", "/").rsplit("/", 1)[-1]
    return name.startswith("test_") or name.endswith("_test.py") or (
        name.endswith(".py") and name.startswith("test")
    )


def _looks_like_a_test_path(path: str) -> bool:
    """A test by location, in any language — used to refuse what we cannot read."""
    p = (path or "").replace("\\", "/")
    name = p.rsplit("/", 1)[-1]
    return (
        "/tests/" in p
        or p.startswith("tests/")
        or name.startswith("test_")
        or ".spec." in name
        or ".test." in name
    )


def is_js_test_file(path: str) -> bool:
    """A JS/TS test file the bracket scanner will attempt to read.

    Deliberately narrower than `_looks_like_a_test_path`: a `.rb`/`.go`/other
    file at a test-shaped path still falls through to `unsupported_test_file`.
    """
    p = (path or "").replace("\\", "/")
    return p.endswith(_JS_TEST_EXTENSIONS) and _looks_like_a_test_path(p)


def _is_recognized_test_file(path: str) -> bool:
    """Any test file either reader can attempt — Python or JS/TS."""
    return is_test_file(path) or is_js_test_file(path)


#: Backtick is deliberately excluded — a template literal isn't a simple
#: quoted run, it can contain `${...}` interpolations of real code (see
#: `_js_scan_template`), so it needs its own handling, not this branch's.
_JS_QUOTE_STARTS = frozenset("'\"")
_JS_BRACKET_PAIRS = {"(": ")", "{": "}", "[": "]"}
_JS_BRACKET_CLOSERS = {v: k for k, v in _JS_BRACKET_PAIRS.items()}

#: Keywords after which a bare `/` is a regex literal, not division, even
#: though the preceding token is word-shaped (`return /foo/.test(x)`,
#: `typeof /x/`). Division never follows these; an expression always does.
_JS_REGEX_CONTEXT_KEYWORDS = frozenset({
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
    "do", "else", "yield", "case", "throw", "await",
})

#: Keywords whose `(...)` is a control-flow CONDITION, not a value-producing
#: grouping expression — `if (enabled) /\[/.test(value);` is valid JS with a
#: regex literal right after the `)`, indistinguishable by character alone
#: from `(a + b) / c` (division). `_js_bracket_match` records which specific
#: closing parens follow one of these (external Tier-3 review, PR #685,
#: seventh round: `_js_slash_starts_regex` treated every `)` as division
#: unconditionally, so this exact valid-JS shape produced a false blocking
#: `unparseable`, the very failure mode this fix exists to remove).
_JS_CONTROL_PAREN_KEYWORDS = frozenset({"if", "while", "for"})


def _js_word_before(
    source: str, idx: int, comment_spans: Sequence[tuple[int, int]] = (),
) -> str:
    """The word-shaped token immediately before `idx`, skipping whitespace
    AND any of `comment_spans` that ends exactly where the skip currently
    stands — so `if /* c */ (enabled) /\\[/.test(v);` still finds `if`
    (external Tier-3 review, PR #685, tenth round: whitespace-only skip
    left a comment between the keyword and its `(` invisible, so this exact
    valid-JS shape produced a false blocking `unparseable` the same way
    round seven's fix did for the no-comment case). `comment_spans` only
    ever holds `//`/`/* */` comments — a preceding STRING/regex span must
    NOT be skipped the same way, since that span IS a real value token, not
    filler between a keyword and its parenthesis.
    """
    j = idx - 1
    while True:
        while j >= 0 and source[j] in " \t\r\n":
            j -= 1
        moved = False
        for start, end in comment_spans:
            if end - 1 == j:
                j = start - 1
                moved = True
                break
        if not moved:
            break
    k = j
    while k >= 0 and (source[k].isalnum() or source[k] in "_$"):
        k -= 1
    return source[k + 1:j + 1]


def _js_quote_glued_to_word(source: str, i: int) -> str | None:
    """The identifier/keyword-shaped word immediately (zero-gap, no
    whitespace at all) before the quote at `source[i]`, or `None` if the
    quote isn't glued to one -- i.e. there is whitespace, punctuation, or
    start-of-source right before it instead.
    """
    if i == 0:
        return None
    j = i - 1
    if not (source[j].isalnum() or source[j] in "_$"):
        return None
    k = j
    while k >= 0 and (source[k].isalnum() or source[k] in "_$"):
        k -= 1
    return source[k + 1:j + 1]


def _js_slash_starts_regex(
    source: str, i: int, control_closes: AbstractSet[int] = frozenset(),
) -> bool:
    """Whether the `/` at `source[i]` opens a regex literal rather than
    being a division operator — the standard heuristic every hand-rolled JS
    tokenizer uses: division follows a VALUE (an identifier, a number, a
    closing `)`/`]`/`}`, or the end of a string/template); everywhere else
    is a position where an expression is expected, and a `/` there can only
    open a regex (external Tier-3 review, PR #685, third round: the
    bracket scanner treated brackets inside a regex literal like `/\\(/` as
    structural code, so a valid test using one — the file's own
    `test_js_a_regex_literal_with_a_lone_bracket_fails_closed_not_silently`
    demonstrates exactly this — read as unparseable and blocked every
    repair touching it, not just the ambiguous case that test documents).

    `control_closes` names the index of every `)` (in `_JS_CONTROL_PAREN_KEYWORDS`'s
    closing position) so far — see that constant's docstring — carving out the
    one shape where a `)` does NOT mean "division follows".
    """
    j = i - 1
    while j >= 0 and source[j] in " \t\r\n":
        j -= 1
    if j < 0:
        return True
    prev = source[j]
    if prev == ")" and j in control_closes:
        return True
    if prev in ")]}" or prev in "'\"`":
        return False
    if prev.isalnum() or prev in "_$":
        k = j
        while k >= 0 and (source[k].isalnum() or source[k] in "_$"):
            k -= 1
        word = source[k + 1:j + 1]
        if word[0].isdigit():
            return False  # a number literal ends here — division
        return word in _JS_REGEX_CONTEXT_KEYWORDS
    return True


def _js_regex_literal_end(source: str, i: int) -> int | None:
    """End index (exclusive) of the regex literal starting at `source[i]`
    (a `/` already confirmed by `_js_slash_starts_regex`), or `None` if it
    never closes before a newline — that reads as "not actually a regex"
    (a stray division, or malformed source), and the caller falls back to
    treating `/` as an ordinary character rather than committing to a span
    it cannot confirm."""
    n = len(source)
    j = i + 1
    in_class = False
    while j < n:
        c = source[j]
        if c == "\n":
            return None
        if c == "\\":
            j += 2
            continue
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            j += 1
            while j < n and source[j].isalpha():
                j += 1
            return j
        j += 1
    return None


#: What one `_js_scan_code` call returns on success: the index just past
#: what it scanned, plus everything it collected along the way.
_JsScanResult = tuple[int, dict[int, int], list[tuple[int, int]], list[tuple[int, int]], set[int]]


def _js_scan_template(source: str, start: int, n: int) -> _JsScanResult | None:
    """Scan the template literal opening at the backtick `start`. Returns
    `(end, match, non_code, comment_spans, control_closes)` for everything
    up to and including the matching closing backtick, or `None` if the
    template never closes, or a `${...}` interpolation's own brackets do
    not balance — both fail closed the same way an unterminated string
    already does (external Tier-3 review, PR #685, eleventh round: a
    malformed interpolation was previously invisible, since the whole
    template was skipped as one opaque span from backtick to backtick
    regardless of what was inside it — inconsistent with every other
    "cannot confirm this is valid" path in this file, which all fail
    closed).

    Everything between backticks that is NOT inside a `${...}` is raw text
    (recorded as one non-code span per run); everything INSIDE a `${...}`
    is scanned as ordinary code by `_js_scan_code` — including nested
    strings, comments, regex literals, and nested template literals — so a
    real `expect(...)`/`it(...)` occurrence inside an interpolation is now
    visible to the name/assertion scanners afterward too (closing, as a
    side effect, the fourth round's separately-named non-blocking comment
    about executable interpolations being invisible).
    """
    non_code: list[tuple[int, int]] = []
    match: dict[int, int] = {}
    comment_spans: list[tuple[int, int]] = []
    control_closes: set[int] = set()
    i = start + 1
    text_start = start
    while i < n:
        c = source[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            non_code.append((text_start, i + 1))
            return i + 1, match, non_code, comment_spans, control_closes
        if c == "$" and source[i:i + 2] == "${":
            non_code.append((text_start, i))
            brace_idx = i + 1
            sub = _js_scan_code(source, brace_idx, n, stop_at=brace_idx)
            if sub is None:
                return None
            end, s_match, s_non_code, s_comments, s_control = sub
            match.update(s_match)
            non_code.extend(s_non_code)
            comment_spans.extend(s_comments)
            control_closes.update(s_control)
            i = end
            text_start = i
            continue
        i += 1
    return None  # unterminated template -- fail closed


def _js_scan_code(source: str, i: int, n: int, stop_at: int | None) -> _JsScanResult | None:
    """Scan ordinary JS/TS code from `i`. With `stop_at` given — the index
    of an already-encountered `{` that opens a template interpolation —
    scanning stops the instant THAT `{` closes, bounding the interpolation
    to its own expression without a second, duplicate implementation of
    every rule below (a call from `_js_scan_template`, one level of
    mutual recursion for a nested template inside an interpolation).
    Without it, scans to end of `source`, and anything left open on the
    stack at that point fails closed exactly like a plain unbalanced file
    always has. `_js_bracket_match` is the public, single-call entry point
    (`stop_at=None`, `i=0`).
    """
    stack: list[tuple[str, int, bool]] = []
    match: dict[int, int] = {}
    non_code: list[tuple[int, int]] = []
    comment_spans: list[tuple[int, int]] = []
    control_closes: set[int] = set()
    while i < n:
        c = source[i]
        if c in _JS_QUOTE_STARTS:
            glued = _js_quote_glued_to_word(source, i)
            if glued is not None and glued not in _JS_REGEX_CONTEXT_KEYWORDS:
                # A straight quote glued directly onto a preceding word with
                # NO separator at all -- "it's", "don't", `5'6"` -- is not
                # something any two adjacent, valid JS tokens can produce: a
                # real string only ever opens at the start of an expression
                # (after punctuation/whitespace) or immediately after one of
                # the few keywords that can precede a bare value with no gap
                # (`return"x"`, already carved out via
                # `_JS_REGEX_CONTEXT_KEYWORDS`). This shape is JSX text --
                # `.tsx`/`.jsx` are in `_JS_EXTENSIONS` -- so treat the quote
                # as ordinary prose, not the start of a string (external
                # Tier-3 review, PR #685, fifteenth round: unconditionally
                # opening a string here turned every contraction in a valid
                # JSX/TSX test file's rendered text into either an
                # unterminated-string false `unparseable`, or a real string
                # elsewhere in the file being misread as this one's content).
                i += 1
                continue
            start = i
            quote = c
            i += 1
            while i < n and source[i] != quote:
                if source[i] == "\\":
                    # A backslash escapes whatever follows, including a raw
                    # line terminator (a legal line-continuation) -- `\r\n`
                    # is one such terminator, so it must be consumed as a
                    # pair, not just its `\r` half (leaving a bare `\n` that
                    # would otherwise trip the check below).
                    i += 3 if source[i:i + 3] == "\\\r\n" else 2
                    continue
                if source[i] in "\r\n":
                    # A single/double-quoted string cannot legally contain
                    # an unescaped line terminator -- unlike a template
                    # literal (`_js_scan_template`), which can. Treating one
                    # as ordinary string content let this scanner run past
                    # the line where the string was actually supposed to
                    # end, silently swallowing whatever real code followed
                    # as "string" (external Tier-3 review, PR #685,
                    # thirteenth round). Fail closed, same as any other
                    # syntactically invalid after revision.
                    return None
                i += 1
            if i >= n:
                # No closing delimiter before end-of-file: the file is not
                # valid JS/TS. Fail closed rather than silently treating
                # everything after the open quote as string content
                # (external Tier-3 review, PR #685, fourth round: this
                # previously let an otherwise-balanced-looking after
                # revision with a genuinely unterminated string pass
                # analysis instead of reporting `unparseable`).
                return None
            i += 1
            non_code.append((start, i))
            continue
        if c == "`":
            tmpl = _js_scan_template(source, i, n)
            if tmpl is None:
                return None
            end, t_match, t_non_code, t_comments, t_control = tmpl
            match.update(t_match)
            non_code.extend(t_non_code)
            comment_spans.extend(t_comments)
            control_closes.update(t_control)
            i = end
            continue
        if c == "/" and source[i:i + 2] == "//":
            start = i
            j = source.find("\n", i)
            i = n if j == -1 else j
            non_code.append((start, i))
            comment_spans.append((start, i))
            continue
        if c == "/" and source[i:i + 2] == "/*":
            start = i
            j = source.find("*/", i + 2)
            if j == -1:
                return None  # unterminated block comment -- fail closed, same reasoning as above
            i = j + 2
            non_code.append((start, i))
            comment_spans.append((start, i))
            continue
        if c == "/" and _js_slash_starts_regex(source, i, control_closes):
            end = _js_regex_literal_end(source, i)
            if end is not None:
                non_code.append((i, end))
                i = end
                continue
            # Doesn't actually close before a newline — not a regex after
            # all; fall through and treat `/` as an ordinary, non-bracket
            # character (matches nothing below either way).
        if c in _JS_BRACKET_PAIRS:
            is_control = (
                c == "(" and _js_word_before(source, i, comment_spans) in _JS_CONTROL_PAREN_KEYWORDS
            )
            stack.append((c, i, is_control))
        elif c in _JS_BRACKET_CLOSERS:
            if not stack or stack[-1][0] != _JS_BRACKET_CLOSERS[c]:
                return None
            _, open_idx, is_control = stack.pop()
            match[open_idx] = i
            if is_control:
                control_closes.add(i)
            if stop_at is not None and open_idx == stop_at:
                return i + 1, match, non_code, comment_spans, control_closes
        i += 1
    if stop_at is not None:
        return None  # the interpolation's own `{` never closed -- fail closed
    return None if stack else (i, match, non_code, comment_spans, control_closes)


def _js_bracket_match(
    source: str,
) -> tuple[dict[int, int], list[tuple[int, int]]] | None:
    """Map every code `(`/`{`/`[` index to its matching close, and separately
    record the `[start, end)` span of every string literal, comment, and
    template-literal raw-text run skipped along the way. `None` means the
    brackets did not balance (including inside a template's `${...}`
    interpolation) — the caller fails closed rather than trusting a partial
    map.

    The spans exist so a name-like regex run afterwards (`_JS_NAME`,
    `_JS_ASSERT_HEAD`) can tell a real `it`/`expect`/... occurrence from one
    that only appears inside a comment or a string — this scanner already
    has to walk past those to match brackets correctly; recording where they
    were is nearly free, and skipping it left an earlier revision of this
    file treating "`it.skip(...)`" inside a `//` comment as a real call.
    """
    result = _js_scan_code(source, 0, len(source), stop_at=None)
    if result is None:
        return None
    _end, match, non_code, _comment_spans, _control_closes = result
    return match, non_code


def _js_in_non_code(non_code: list[tuple[int, int]], pos: int) -> bool:
    i = bisect.bisect_right(non_code, (pos, pos)) - 1
    return i >= 0 and non_code[i][0] <= pos < non_code[i][1]


#: A word immediately before a matched name that means the name is a
#: declaration site, not a call (`function test(name, fn) { ... }` — a
#: parameter list is textually indistinguishable from a call's argument
#: list). Deliberately small: this is the one keyword the grammar actually
#: allows there in a test file's normal vocabulary.
_JS_DECLARATION_KEYWORDS = frozenset({"function"})


def _js_name_is_standalone_call(source: str, start: int) -> bool:
    """False when the `_JS_NAME` match at `start` is reached via member
    access (`fixture.test(...)`, `namespace.it(...)`) or is a `function
    test(...)`-shaped declaration head — neither is a describe/it/test call
    (external Tier-3 review, PR #685: an ordinary helper method or function
    named `test`/`it` produced a blocking `assertions_removed` finding for
    an unrelated change, because the scanner never inspected what preceded
    the matched name).

    Only the immediately preceding non-whitespace token is inspected —
    `.`/`?.` both end in `.`, so checking that one character catches both
    forms of member access without needing to special-case `?.` — which
    keeps this a narrow, targeted guard rather than a second parser.
    """
    i = start - 1
    while i >= 0 and source[i] in " \t\r\n":
        i -= 1
    if i < 0:
        return True
    if source[i] == ".":
        return False
    j = i
    while j >= 0 and (source[j].isalnum() or source[j] in "_$"):
        j -= 1
    return source[j + 1:i + 1] not in _JS_DECLARATION_KEYWORDS


#: `describe`/`it`/`test` and their `x`-disabled siblings, plus Jasmine/Jest's
#: `f`-focused siblings (`fit`, `fdescribe` — the direct opposite of `x`:
#: Jest/Jasmine's own alias for `.only`, not chain-based, so it was silently
#: invisible here entirely before external Tier-3 review, PR #685, sixth
#: round, caught assertion weakening inside one passing the gate with no
#: finding at all — a genuine false negative, not just an accepted one).
#: Chain-scanning (whitespace/comment-tolerant, computed-access-aware) is
#: `_js_scan_chain`'s job, not this regex's; folding it into the regex is
#: what let a line-broken `test\n  .skip(...)` or a `test['skip'](...)`
#: collapse to an empty chain unnoticed in an earlier revision of this file.
_JS_NAME = re.compile(r"\b(?:describe|xdescribe|fdescribe|it|xit|fit|test|xtest)\b")
#: Every chain `_js_resolve_test_call` actually knows how to follow. A single
#: authoritative set: unlike an earlier revision of this file, there is no
#: second regex re-deciding "supported" on its own that could quietly drift
#: out of sync with the resolver (the gap external spec review caught here,
#: across three rounds: `.each`, `.each` as a tagged template, then a chain
#: reachable only through whitespace/comments/computed access). `.fixme` was
#: advertised (this module's own test-completeness ledger claimed it) but
#: never actually added here, so every invoked `test.fixme(...)`/
#: `it.fixme(...)` fell through to the unrecognized-and-invoked path and
#: blocked the repair outright (external Tier-3 review, PR #685, ninth
#: round: a documentation/implementation mismatch, not a new gap).
_JS_ALLOWED_CHAINS = frozenset({
    "", ".skip", ".only", ".todo", ".fixme", ".each",
    ".skip.each", ".only.each", ".todo.each", ".fixme.each",
})
#: `assert.<method>(` (Node's built-in `assert` module, and Chai's `assert`
#: interface — `assert.strictEqual(a, b)`, `assert.ok(x)`) is at least as
#: common as bare `assert(x)` and was invisible without this, an undocumented
#: silent gap unlike every other named limit in this file (code review).
#: Deliberately NOT extended to `expect.<method>(` the same way: Jest/Vitest
#: matcher FACTORIES (`expect.stringContaining(...)`, `expect.any(Number)`)
#: are arguments passed INTO a real `expect(...)` call, not independent
#: assertions of their own — matching them here would count one real
#: assertion as two and inflate the count against itself.
#: `(?<![\w.$])` anchors both alternatives so neither can match after `.`/`?.`
#: or as a continuation of another identifier (external Tier-3 review, PR
#: #685: `fixture.assert.ok(...)` and `helper.expect(...)` — ordinary helper
#: methods that merely happen to share these names — were counted as real
#: assertions, so removing one produced a blocking `assertions_removed`
#: finding for a change that touched no real test). Named cost, accepted the
#: same way as every other narrowing in this file: a namespaced
#: `chai.expect(x)` (rather than the far more common destructured
#: `const { expect } = require('chai')`) is no longer counted either — an
#: undercount (false negative), not a false block.
_JS_ASSERT_HEAD = re.compile(
    r"(?<![\w.$])assert\.\w+\s*\(|(?<![\w.$])(?P<name>expect|assert)\s*\("
)
#: The pooled-dynamic-tests qualname (see `_js_collect`). Embeds a raw,
#: unescaped instance of ALL THREE quote delimiters (`'`, `"`, `` ` ``), which
#: makes it a string no JS/TS source can ever produce as a test name: each of
#: `_JS_STRING_LIT`'s three alternatives excludes only its OWN delimiter from
#: its content class, so whichever one is matching would stop at its own
#: embedded copy and could never capture the rest of this text too -- no
#: single literal, of any quote type, can ever equal this exact string.
#: Deliberately NOT keyed on an embedded raw newline instead (an earlier
#: revision's approach): true for single/double-quoted strings (which cannot
#: contain a raw line terminator at all -- see the quote-scanning fail-closed
#: check above), but never true for a template literal, which is explicitly
#: allowed to span real newlines. A template-literal test name built to
#: contain that same text-plus-newline would have collided with a pooled
#: dynamic-name entry, silently merging its assertions/marks into the pool
#: and hiding a real change to either side (external Tier-3 review, PR #685,
#: fourteenth round).
_DYNAMIC_POOL_KEY = "<dynamically-named tests: unreachable ' \" ` marker>"
#: Three explicit alternatives, not one pattern with a `\1` backreference to
#: the opening quote (CodeQL, high severity: the backreference form's body
#: was `(?:\\.|(?!\1).)*` — a backslash can be consumed either as the start
#: of `\\.` or as the plain char matched by `(?!\1).` (it is never the quote
#: itself), so a run of N backslashes has an exponential number of ways to
#: split between the two alternatives, and an unterminated string forces the
#: engine to try all of them before failing. Each alternative here excludes
#: ONLY its own delimiter (plus backslash) from the plain-char class, so a
#: quote character of a DIFFERENT kind still passes through as ordinary
#: content (`"it's a test"` stays intact) while every character is
#: classified by exactly one alternative — no ambiguity, no backtracking
#: blowup. `_js_test_name` reads whichever of the three groups matched.
_JS_STRING_LIT = re.compile(
    r"""'((?:\\.|[^'\\])*)'"""
    r'''|"((?:\\.|[^"\\])*)"'''
    r"""|`((?:\\.|[^`\\])*)`"""
)
_JS_CHAIN = re.compile(r"\s*\.(\w+)")
_JS_WORD = re.compile(r"\w+")


def _js_skip_gap(source: str, i: int) -> int:
    """Whitespace and comments between chain segments — the same two things
    `_js_bracket_match` already treats as not-code, so `test\n  .skip(...)`
    and `test/* eslint */.skip(...)` chain the same as `test.skip(...)`.
    """
    n = len(source)
    while i < n:
        c = source[i]
        if c in " \t\r\n":
            i += 1
        elif c == "/" and source[i:i + 2] == "//":
            j = source.find("\n", i)
            i = n if j == -1 else j
        elif c == "/" and source[i:i + 2] == "/*":
            j = source.find("*/", i + 2)
            i = n if j == -1 else j + 2
        else:
            break
    return i


def _js_scan_chain(
    source: str, match: dict[int, int], pos: int,
) -> tuple[str, int]:
    """Everything chained onto a name occurrence, from `pos` (just after the
    name). Tolerant of whitespace/comments between segments. A computed-
    access segment (`test['skip'](...)`) is recorded as the literal sentinel
    `.[computed]`, and an optional-chaining link (`test?.skip(...)`,
    `test?.(...)`) as `.[optional]` (property) or `.[optional-call]` (the
    invocation itself) — none of these three sentinels is ever in
    `_JS_ALLOWED_CHAINS`, which routes them through the exact same
    fail-closed-if-actually-invoked path as any other unrecognized named
    segment (see `_js_collect`), rather than silently ending the chain one
    segment early or dropping an invoked-but-unusual test declaration as if
    it were an ordinary uncalled reference (external Tier-3 review, PR #685,
    eighth round: `test?.('case', fn)`/`test?.skip('case', fn)` were
    invisible here entirely, so weakening inside one produced no finding).
    """
    chain = ""
    n = len(source)
    while True:
        gap_end = _js_skip_gap(source, pos)
        if gap_end < n and source[gap_end:gap_end + 2] == "?.":
            after_opt = _js_skip_gap(source, gap_end + 2)
            if after_opt < n and source[after_opt] == "(":
                chain += ".[optional-call]"
                pos = after_opt  # leave the `(` itself for the resolver to find
                break
            w = _JS_WORD.match(source, after_opt)
            if not w:
                break
            chain += ".[optional]." + w.group(0)
            pos = w.end()
            continue
        if gap_end < n and source[gap_end] == ".":
            after_dot = _js_skip_gap(source, gap_end + 1)
            w = _JS_WORD.match(source, after_dot)
            if not w:
                break
            chain += "." + w.group(0)
            pos = w.end()
            continue
        if gap_end < n and source[gap_end] == "[" and gap_end in match:
            chain += ".[computed]"
            pos = match[gap_end] + 1
            continue
        break
    return chain, pos


def _js_skip_template(source: str, backtick_idx: int) -> int | None:
    """`backtick_idx` is an opening backtick. Returns the index just past the
    matching close, or `None` if there isn't one.

    Delegates to `_js_scan_template` (the recursive scanner `_js_bracket_
    match` itself uses) rather than a lighter-weight backtick-to-backtick
    search, so `.each`'s tagged-template table form gets the exact same
    handling of `${...}` interpolations everything else does -- including a
    NESTED template literal inside one. An earlier, simpler version of this
    function predated that scanner and stopped at the first literal
    backtick regardless of what it was nested inside, so a table containing
    one ended the "skip" early; the mismatched position that produced then
    made `_js_resolve_test_call` fail to find the real call afterward,
    reporting a valid after revision `unparseable` (external Tier-3 review,
    PR #685, seventeenth round).
    """
    result = _js_scan_template(source, backtick_idx, len(source))
    return None if result is None else result[0]


def _js_resolve_test_call(
    source: str, match: dict[int, int], end_of_chain: int, has_each: bool,
) -> tuple[int, int] | None:
    """From just past a name+chain (`test`, `test.skip`, `test.each`, ...),
    find the `(open_idx, close_idx)` of the call that actually carries the
    test's name and body.

    Not `.each`: that is the very next `(...)`. `.each`: Jest/Vitest's
    parametrize table comes first, as either `(table)` or a tagged template
    (`` .each`a|b\n${1}|${2}` ``) — either way, the real call is the `(...)`
    immediately after it. `None` means this shape is not one this resolver
    implements (or, for a chain of `""`, simply that this identifier was not
    invoked here at all — see the call site's distinct handling of the two).
    """
    i = _js_skip_gap(source, end_of_chain)
    n = len(source)
    if has_each:
        if i < n and source[i] == "(" and i in match:
            i = match[i] + 1
        elif i < n and source[i] == "`":
            skipped = _js_skip_template(source, i)
            if skipped is None:
                return None
            i = skipped
        else:
            return None
        i = _js_skip_gap(source, i)
    if i < n and source[i] == "(" and i in match:
        return i, match[i]
    return None


def _js_test_name(source: str, open_idx: int, close_idx: int) -> str | None:
    """The test's name — its first string-literal argument, if there is one.

    `_js_skip_gap` first, so a call whose name argument is on its own line
    (`it(\n  'name', fn)`, a common formatter style for long callbacks) is
    read the same as the single-line form — code review caught an earlier
    revision anchoring right after `(` with no gap tolerance, which silently
    dropped every multi-line-formatted test from collection entirely.

    A genuinely dynamic name (a bare variable, `it(caseName, fn)`) is not a
    string literal at all, so `_JS_STRING_LIT` never matches here and the
    caller pools the test into the dynamic-name aggregate instead of
    collecting it under its own identity (stated limit, not a parse failure).
    A template literal WITH an interpolation (`` it(`case ${x}`, fn) ``) is
    different: `_JS_STRING_LIT` has no special case for backticks and matches
    it like any other quoted literal, so it comes back as a literal (garbled,
    interpolation-and-all) name rather than being routed to the dynamic pool
    — harmless in isolation, but it means two such templates that happen to
    share identical raw text collide under the same duplicate-literal-name
    pooling as any other repeated title (see the module docstring).
    """
    start = _js_skip_gap(source, open_idx + 1)
    m = _JS_STRING_LIT.match(source, start)
    if not m or m.end() > close_idx:
        return None
    return m.group(1) if m.group(1) is not None else (
        m.group(2) if m.group(2) is not None else m.group(3)
    )


def _js_assertion_signatures(
    source: str, match: dict[int, int], non_code: list[tuple[int, int]],
    span_start: int, span_end: int,
) -> list[str]:
    """One normalised string per `expect(...)`/`assert(...)` call in the span,
    including any directly-chained matchers (`.not.toBe(x)`), so a changed
    matcher argument is comparable the same way a changed `ast.dump` is.
    """
    sigs = []
    for m in _JS_ASSERT_HEAD.finditer(source):
        if _js_in_non_code(non_code, m.start()):
            continue  # e.g. a comment that merely mentions `expect(...)`
        open_idx = m.end() - 1
        close_idx = match.get(open_idx)
        if close_idx is None or not (span_start < open_idx < span_end):
            continue
        head_start = m.start()
        end = close_idx + 1
        while True:
            cm = _JS_CHAIN.match(source, end)
            if not cm:
                break
            end = cm.end()
            if end < len(source) and source[end] == "(":
                chained_close = match.get(end)
                if chained_close is None:
                    break
                end = chained_close + 1
        sigs.append(re.sub(r"\s+", " ", source[head_start:end]).strip())
    return sigs


def _js_collect(source: str) -> dict[str, "_Test"] | None:
    """Every `it`/`test` in the file, addressed by (de-duplicated) name.

    `None` propagates a bracket-scan failure, an unrecognized modifier chain
    (including a computed-access one — see `_js_scan_chain`) that IS actually
    invoked, or a recognized chain (anything but `""`) that never resolved to
    an actual call — all three are the signal to fail closed exactly like an
    unparseable Python revision. A chain — recognized or not — that is never
    invoked here at all (`const helper = it.customModifier;`, chain `""`, no
    following `(`) is treated as "not a declaration" rather than "unreadable",
    since that is ordinary code (assigning `it`/a property of it to a
    variable, passing it around) with nothing to weaken.
    """
    scanned = _js_bracket_match(source)
    if scanned is None:
        return None
    match, non_code = scanned

    calls = []
    for m in _JS_NAME.finditer(source):
        if _js_in_non_code(non_code, m.start()):
            continue  # e.g. a comment that merely mentions `it.skip(...)`
        if not _js_name_is_standalone_call(source, m.start()):
            continue  # `fixture.test(...)` / `function test(...)` — not a describe/it/test call
        chain, chain_end = _js_scan_chain(source, match, m.end())
        recognized = chain in _JS_ALLOWED_CHAINS
        resolved = _js_resolve_test_call(source, match, chain_end, chain.endswith(".each"))
        if resolved is None:
            #: A chain that is never actually invoked here is ordinary code
            #: (`const helper = it.customModifier;`, `test['skip']` passed
            #: around without a call) — nothing to weaken, whether or not
            #: the chain shape itself is one this scanner recognizes.
            #: A RECOGNIZED chain left unresolved (`test.each;` with no
            #: table/body) is different: it looks like an incomplete/broken
            #: declaration rather than a plain reference, so it keeps
            #: failing closed exactly as before (external Tier-3 review, PR
            #: #685, fifth round: an unrecognized chain used to fail closed
            #: purely for existing, regardless of whether it was invoked at
            #: all, blocking ordinary non-test property references).
            if chain and recognized:
                return None
            continue
        if not recognized:
            return None
        if chain and chain != ".each":
            # A written-out modifier chain (`.skip`, `.only.each`, ...) —
            # its own first segment names the mark.
            mod = chain[1:].split(".", 1)[0]
        elif m.group(0) in ("fit", "fdescribe"):
            #: `fit`/`fdescribe` ARE `.only` — Jest/Jasmine's own alias, not
            #: a chained modifier — so BOTH the bare form (`fit(...)`,
            #: chain == "") AND the `.each` form (`fit.each(...)`, chain ==
            #: ".each") land in this branch and get exactly the same "only"
            #: treatment a written-out `.only` chain would, below. This is
            #: an explicit branch of its own, not a `mod is None` fallback
            #: check after the fact, specifically so `fit.each`/
            #: `fdescribe.each` composing with `.only` semantics is visible
            #: by inspection, not implied (external Tier-3 review, PR #685,
            #: eighteenth round re-raised the twelfth round's already-
            #: refuted claim that this composition silently fails; this
            #: shape removes the ambiguity a `mod is None` side-channel
            #: check invited, without changing behavior at all — see the
            #: fit/fdescribe.each regression tests already covering both
            #: the call-parens and tagged-template forms).
            mod = "only"
        else:
            mod = None
        calls.append((m.group(0), mod, m.start(), *resolved))

    describes = [c for c in calls if c[0] in ("describe", "xdescribe", "fdescribe")]
    #: A `.only` anywhere in the file — on a test OR a describe — makes Jest/
    #: Vitest run *only* that block and skip every sibling in the file at
    #: runtime, with no mark on the siblings themselves. An earlier revision
    #: of this scanner recognized `.only` as a chain but never gave it any
    #: effect, so this exact "leave a `.only` in" footgun produced zero
    #: findings — the AC-6 failure mode this whole reader exists to catch,
    #: reached without touching a single skipped test's own body or marks
    #: (doubt review). `only_protected(open, close)` below decides whether a
    #: test escapes the shadow: itself `.only`, or nested inside a describe
    #: that is.
    any_only = any(mod == "only" for _, mod, *_rest in calls)

    def _only_protected(open_idx: int, close_idx: int, mod: str | None) -> bool:
        if mod == "only":
            return True
        return any(
            d_mod == "only" and d_open < open_idx and close_idx < d_close
            for _, d_mod, _dh, d_open, d_close in describes
        )

    tests: dict[str, _Test] = {}
    #: A dynamic name (a variable, `cases.forEach(c => it(c.name, ...))`) is
    #: not extractable as text, but the call itself resolved fine — dropping
    #: it outright made it invisible to diffing on both sides. An ordinal key
    #: ("the Nth dynamic test") fixed that but introduced a worse failure: an
    #: unrelated dynamic test inserted earlier in the SAME diff reoccupies a
    #: lower ordinal, so a real assertion loss in the shifted test compared
    #: against the decoy's unrelated content, laundering a blocking loss into
    #: a merely-reported (or fully invisible) one (doubt review, round 2).
    #: Two statically-named tests sharing one literal title — ordinary,
    #: legitimate Jest/Vitest style, e.g. the same `it('returns 200', ...)`
    #: reused under different `describe` blocks — have exactly the same
    #: ordinal-reordering exposure and were keyed the same broken way until
    #: doubt review, round 4. Both cases now resolve to the SAME pooling
    #: below, keyed by whatever identity the test resolved to (its literal
    #: name, or the dynamic-pool sentinel for a name that never resolved to
    #: text at all): order-independent, so a decoy inserted elsewhere no
    #: longer hides a real loss the way an ordinal key did — normally it can
    #: only soften a blocking `assertions_removed` into a reported
    #: `assertion_changed`, the honest "ambiguous, so reported not blocked"
    #: treatment this file already gives any assertion-content change it
    #: cannot fully disambiguate. **Named limit, not closed:** if a decoy's
    #: own assertion signature is textually IDENTICAL to the one actually
    #: removed (realistic for table-driven tests sharing boilerplate
    #: assertions like `expect(status).toBe(200)`), the pooled before/after
    #: sets can come out equal and the loss is fully invisible — content-only
    #: identity cannot tell "this assertion moved" from "this assertion was
    #: deleted and an unrelated one happens to read the same" (doubt review,
    #: round 3). Marks are pooled as a MULTISET, one entry per pooled test
    #: instance that carries it, not a plain set: a plain union made a
    #: genuinely new `.skip`/`.only`-shadow on ONE pooled instance invisible
    #: whenever another pooled instance already carried that same mark
    #: before the change (doubt review, round 5) — `_diff_tests` below
    #: compares occurrence COUNTS, the same "quantity, not presence" floor
    #: already given to assertions, so one more occurrence after than before
    #: still fires even though the mark type itself is not new.
    for name, mod, _head_start, open_idx, close_idx in calls:
        if name not in ("it", "xit", "test", "xtest", "fit"):
            continue
        test_name = _js_test_name(source, open_idx, close_idx)
        marks: set[str] = set()
        if name in ("xit", "xtest") or mod in ("skip", "todo", "fixme"):
            marks.add("skip")
        for d_name, d_mod, _d_head, d_open, d_close in describes:
            if d_open < open_idx and close_idx < d_close and (
                d_name == "xdescribe" or d_mod in ("skip", "todo", "fixme")
            ):
                marks.add("skip")
        if any_only and not _only_protected(open_idx, close_idx, mod):
            marks.add("skip")
        assertions = _js_assertion_signatures(source, match, non_code, open_idx, close_idx)
        key = test_name if test_name is not None else _DYNAMIC_POOL_KEY
        prior = tests.get(key)
        inst_assertions = tuple(sorted(assertions))
        inst_marks = tuple(sorted(marks))
        tests[key] = _Test(
            qualname=key,
            assertions=tuple(sorted((*prior.assertions, *assertions) if prior else assertions)),
            marks=tuple(sorted((*prior.marks, *sorted(marks)) if prior else sorted(marks))),
            instance_count=(prior.instance_count if prior else 0) + 1,
            instances=(*(prior.instances if prior else ()), (inst_assertions, inst_marks)),
        )
    return tests


def _decorator_marks(decorators: list[ast.expr]) -> set[str]:
    marks: set[str] = set()
    for dec in decorators:
        node = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(node, ast.Attribute) and node.attr in _SKIP_MARKS:
            marks.add(node.attr)
        elif isinstance(node, ast.Name) and node.id in _SKIP_MARKS:
            marks.add(node.id)
    return marks


def _module_marks(tree: ast.Module) -> set[str]:
    """Marks from a module-level ``pytestmark`` assignment."""
    marks: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
        ):
            continue
        values = (
            node.value.elts
            if isinstance(node.value, (ast.List, ast.Tuple))
            else [node.value]
        )
        marks |= _decorator_marks(values)
    return marks


def _body_marks(fn: ast.AST) -> set[str]:
    """A ``pytest.skip(...)`` / ``pytest.xfail(...)`` call inside the body."""
    marks: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in _SKIP_CALLS:
                marks.add(f.attr)
    return marks


def _assertions(fn: ast.AST) -> list[str]:
    """Every assertion in a function body, as a normalised expression string.

    Normalised (``ast.dump``) rather than source, so reformatting is not a
    change and a genuinely different expectation is.
    """
    found: list[str] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assert):
            found.append("assert:" + ast.dump(node.test))
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute):
                if f.attr.startswith(_ASSERT_METHOD_PREFIX) and isinstance(
                    f.value, ast.Name
                ):
                    found.append("call:" + f.attr)
                elif f.attr in _ASSERTING_CONTEXTS:
                    found.append("ctx:" + f.attr)
    return sorted(found)


def _collect(tree: ast.Module) -> dict[str, _Test]:
    """Every test in the module, addressed by qualified name."""
    inherited = frozenset(_module_marks(tree))
    tests: dict[str, _Test] = {}

    def _add(node, qualname: str, marks: frozenset[str]) -> None:
        assertions = tuple(_assertions(node))
        all_marks = tuple(sorted(
            marks | frozenset(_decorator_marks(node.decorator_list))
            | frozenset(_body_marks(node))
        ))
        tests[qualname] = _Test(
            qualname=qualname,
            assertions=assertions,
            marks=all_marks,
            instance_count=1,
            instances=((assertions, all_marks),),
        )

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test"):
                _add(node, node.name, inherited)
        elif isinstance(node, ast.ClassDef):
            class_marks = inherited | frozenset(_decorator_marks(node.decorator_list))
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                    sub.name.startswith("test")
                ):
                    _add(sub, f"{node.name}::{sub.name}", class_marks)
    return tests


def _parse(source: str | None) -> ast.Module | None:
    if source is None:
        return None
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def _relocated_mark_findings(path: str, qualname: str, was: _Test, now: _Test) -> list[Finding]:
    """A mark that moved between two EXACT-content-identical instances in a
    pool, invisible to `instance_count` (unchanged) and the aggregate mark
    count (also unchanged — it just relocated). Recoverable without the
    false-positive risk a similarity-based pairing would carry: a legitimate
    test split necessarily changes at least one instance's exact assertion
    content, so a content key that changed simply isn't matched, rather than
    being guessed at (doubt review, round 8, closing the round-7 gap).

    A content key that occurs EXACTLY ONCE on both the before and after side
    is an unambiguous 1:1 match *for that key* — but "unambiguous for that
    key" is not the same as "unambiguous for the pool". A first attempt at
    per-key matching (checked each such key independently, blocking on any
    that gained a skip/xfail mark) closed a real gap — an unrelated duplicate
    decoy, or an ordinary unrelated edit to a different same-titled sibling,
    used to blind detection of a real swap elsewhere in the pool (doubt
    review, round 9) — but opened a worse one: when some OTHER key in the
    same pool is ALSO ambiguous or changed, an unrelated edit that happens to
    land on a coincidentally-identical text can be misread as "this exact
    instance persisted and gained a mark," producing a BLOCKING finding for a
    diff that introduced no weakening at all (doubt review, round 10) — a
    false block, which this file's own stated design (`What is blocked is
    unambiguous loss`) explicitly rules out, and a strictly worse failure
    mode than the false negative it replaced given this file's whole reason
    for existing (a wrongly-blocked repair is the exact motivating bug).

    The resolution: blocking requires the WHOLE POOL's content to be
    CONSERVED between before and after — occurrence counts identical, key for
    key (`Counter` equality) — not merely the ONE key under consideration.
    That is exactly the round-7/8 case (a clean, total swap with no other
    pool members, or with only untouched duplicates alongside it) and is
    genuinely unambiguous: nothing anywhere in the pool was added or removed,
    so nothing could have produced the matched key coincidentally. A
    duplicate present at the SAME count on both sides is conserved and does
    not, on its own, break this — requiring every count to be exactly 1 (an
    earlier version) was safe but needlessly stricter (doubt review, round
    11). Whenever the pool is NOT conserved (something genuinely added or
    removed elsewhere), a still-unambiguous single-key match is reported
    instead of blocked — real, but not provably free of the round-10
    coincidence risk. Two instances sharing IDENTICAL content still defeat
    the match for THAT
    key regardless — the same irreducible residual round 3 already named.
    """
    if was.instance_count != now.instance_count or was.instance_count <= 1:
        # A pool of exactly one instance has nothing to relocate a mark
        # BETWEEN — the aggregate mark-count check just below already covers
        # it completely, so skipping here avoids emitting a second, redundant
        # `skip_added` Finding for the ordinary single-test case (doubt
        # review, round 11).
        return []
    before_counts = Counter(assertions for assertions, _marks in was.instances)
    after_counts = Counter(assertions for assertions, _marks in now.instances)
    # dict() collapses a duplicate content key to its LAST occurrence — safe
    # only because every lookup below is gated on `count == 1` (content
    # unique on both sides), so a collapsed duplicate is never the key
    # actually indexed (code review).
    before_marks_by_content = dict(was.instances)
    after_marks_by_content = dict(now.instances)
    # Counter EQUALITY, not "every count is 1": a duplicate pair that is
    # PRESENT WITH THE SAME COUNT on both sides, untouched, contributes no
    # new text and erases no existing text, so it cannot supply the
    # coincidental-collision material round 10 found — it never changes
    # count and is never itself matched. Requiring every count to be exactly
    # 1 was safe but stricter than necessary: it downgraded an isolated,
    # genuinely unambiguous swap to merely-reported whenever an unrelated,
    # perfectly conserved duplicate happened to exist elsewhere in the same
    # pool (doubt review, round 11). Only an ADDED or REMOVED key — which
    # Counter equality still catches — can supply that material.
    full_bijection = before_counts == after_counts
    findings: list[Finding] = []
    for content, count in before_counts.items():
        if count != 1 or after_counts.get(content, 0) != 1:
            continue
        gained = {
            m for m, c in Counter(after_marks_by_content[content]).items()
            if c > Counter(before_marks_by_content[content]).get(m, 0)
        }
        if not (gained & (_SKIP_MARKS | _SKIP_CALLS)):
            continue
        if full_bijection:
            findings.append(
                Finding(
                    "skip_added", True, f"{path}::{qualname}",
                    "newly " + "/".join(sorted(gained)) + "-ed — recovered by "
                    "matching an exact-content instance within an otherwise-"
                    "unambiguous pool, not by the pool's aggregate mark count "
                    "(which stayed flat)",
                )
            )
        else:
            findings.append(
                Finding(
                    "pooled_mark_possibly_relocated", False, f"{path}::{qualname}",
                    "an exact-content match within the pool appears to have "
                    "gained " + "/".join(sorted(gained)) + " — but another "
                    "part of the same pool changed too, so this could be a "
                    "coincidental content match rather than the same "
                    "instance persisting; a human read is needed",
                )
            )
    # The loop above's own docstring names the residual it deliberately does
    # NOT close: two instances sharing IDENTICAL content defeat the
    # per-key exact match, since neither is individually addressable. A mark
    # that PURELY permutes between two such instances, with nothing else in
    # the pool changing, is genuinely unrecoverable — as a multiset of
    # (content, marks) pairs, the after state is indistinguishable from the
    # before one, full stop, not merely hard to pin down.
    #
    # But a narrower, DETECTABLE case was still falling through uncaught: a
    # mark moving INTO or OUT OF a duplicate-content group from elsewhere in
    # the same pool. That changes the group's own aggregate mark composition
    # while leaving both that content's occurrence count (still shared,
    # unique-content matching above never looks at it) and the WHOLE pool's
    # aggregate (the move's other end cancels it out) exactly flat — invisible
    # to every check above and to the plain aggregate check below alike: a
    # silent clear of a genuine execution-state change, not merely an
    # unreported one (external Tier-3 review, PR #685, sixteenth round).
    # Reported, not blocked — still ambiguous, since more than one instance
    # shares this content and nothing here says which one specifically
    # gained or lost the mark.
    for content, count in before_counts.items():
        if count <= 1 or after_counts.get(content, 0) != count:
            continue
        before_group_marks = Counter()
        for assertions, marks in was.instances:
            if assertions == content:
                before_group_marks.update(marks)
        after_group_marks = Counter()
        for assertions, marks in now.instances:
            if assertions == content:
                after_group_marks.update(marks)
        if before_group_marks != after_group_marks:
            findings.append(
                Finding(
                    "pooled_mark_possibly_relocated", False, f"{path}::{qualname}",
                    f"{count} instances share identical assertion content, "
                    "and the marks attached to them as a group changed even "
                    "though neither that content's occurrence count nor the "
                    "whole pool's aggregate mark count did — a mark may have "
                    "moved between this group and elsewhere in the pool; a "
                    "human read is needed",
                )
            )
    return findings


def _diff_tests(
    path: str, before: dict[str, _Test], after: dict[str, _Test],
) -> list[Finding]:
    """The before/after comparison, shared by the Python and JS/TS readers —
    once each has reduced its file to `{qualname: _Test}`, loss looks the
    same regardless of which parser found it.
    """
    findings: list[Finding] = []
    for qualname, was in before.items():
        now = after.get(qualname)
        if now is None:
            findings.append(
                Finding("test_removed", True, f"{path}::{qualname}",
                        "a test that existed before is gone")
            )
            continue
        if now.instance_count < was.instance_count:
            # A same-identity pooled instance vanished (see `_Test.instance_
            # count`). Ambiguous, not unambiguous, so reported rather than
            # blocked: it could be a harmless intentional merge of two
            # duplicate-named tests — but it could also be exactly how a
            # mark or an assertion gets reassigned onto a SURVIVING pooled
            # instance without moving any aggregate count the checks below
            # can see (doubt review, round 6). Naming it here is what turns
            # that into a `review` verdict instead of a silent `clear`.
            findings.append(
                Finding(
                    "pooled_test_instance_lost", False, f"{path}::{qualname}",
                    f"{was.instance_count} same-identity test(s) pooled here "
                    f"before, {now.instance_count} after — assertion/mark "
                    "counts alone cannot rule out one instance's coverage "
                    "or skip state moving onto another",
                )
            )
        findings.extend(_relocated_mark_findings(path, qualname, was, now))
        # A COUNT comparison, not a set difference: `now.marks`/`was.marks`
        # are multisets (see `_Test.marks`), so a pooled JS entry can carry
        # more than one occurrence of the same mark. Comparing sets would
        # only ever see "skip present" vs. "skip present" and miss a mark
        # that appeared on one MORE pooled test than before (doubt review,
        # round 5) — a plain Python test never has more than one occurrence
        # of a given mark, so this is exactly the old set-difference result
        # there.
        was_counts = Counter(was.marks)
        now_counts = Counter(now.marks)
        new_marks = {m for m, count in now_counts.items() if count > was_counts.get(m, 0)}
        if new_marks & (_SKIP_MARKS | _SKIP_CALLS):
            findings.append(
                Finding("skip_added", True, f"{path}::{qualname}",
                        "newly " + "/".join(sorted(new_marks)) + "-ed")
            )
        if len(now.assertions) < len(was.assertions):
            findings.append(
                Finding("assertions_removed", True, f"{path}::{qualname}",
                        f"{len(was.assertions)} assertion(s) before, "
                        f"{len(now.assertions)} after")
            )
        elif set(was.assertions) - set(now.assertions):
            # Keyed on what DISAPPEARED, not on inequality: adding an assertion
            # makes the sets differ too, and reporting that would train the
            # reader to ignore the field.
            findings.append(
                Finding("assertion_changed", False, f"{path}::{qualname}",
                        "an assertion's expectation changed — say why the new "
                        "value is the truth")
            )
    return findings


def analyze_file(change: FileChange) -> list[Finding]:
    """Findings for one changed file. Order of the guards is the contract."""
    path = change.path
    status = (change.status or "M").upper()[:1]

    if status == "A":  # nothing existed to weaken
        return []

    # A rename OUT of test-collection removes tests just as surely as `rm` does,
    # and it is the quieter way to do it: `tests/test_x.py` -> `lib/helpers.py`
    # leaves the assertions in the tree, where nothing runs them. Judging only
    # the destination waves that through (external code review, round 2).
    if (
        change.old_path
        and _is_recognized_test_file(change.old_path)
        and not _is_recognized_test_file(path)
    ):
        return [
            Finding(
                "test_removed_by_rename", True, f"{change.old_path} -> {path}",
                "renamed out of test collection — the assertions survive, "
                "but nothing runs them any more",
            )
        ]

    is_python = is_test_file(path)
    is_js = (not is_python) and is_js_test_file(path)
    if not is_python and not is_js:
        # `.py` is exempt even here: a file under a `tests/`-shaped path that
        # `ast` can read but that isn't pytest-collected (`conftest.py`, a
        # fixture module, `tests/__init__.py`) is a language this detector
        # DOES cover — it just has no tests to lose, so it produces zero
        # findings, not a refusal. Without this exemption every ordinary
        # conftest/fixture edit in this very repo would wrongly BLOCK (code
        # review) — dropped by mistake when JS/TS support was added.
        if _looks_like_a_test_path(path) and not path.endswith(".py"):
            return [
                Finding(
                    "unsupported_test_file", True, path,
                    "a test file this detector cannot parse changed — refusing "
                    "rather than waving it through",
                )
            ]
        return []

    if status == "D" or change.after is None:
        return [Finding("file_removed", True, path, "the whole test file was deleted")]

    if is_python:
        after_tree = _parse(change.after)
        if after_tree is None:
            return [
                Finding("unparseable", True, path,
                        "the post-change revision does not parse — fails closed")
            ]
        before_tree = _parse(change.before)
        if before_tree is None:
            # A base that never parsed is not this change's doing; blocking on
            # it would wedge every repair touching that file.
            return []
        before, after = _collect(before_tree), _collect(after_tree)
    else:
        after_tests = _js_collect(change.after)
        if after_tests is None:
            return [
                Finding("unparseable", True, path,
                        "the post-change revision's brackets do not balance — "
                        "fails closed")
            ]
        before_tests = None if change.before is None else _js_collect(change.before)
        if before_tests is None:
            # Same reasoning as the Python branch: a base we cannot scan is
            # not this change's doing.
            return []
        before, after = before_tests, after_tests

    return _diff_tests(path, before, after)


def detect_weakening(changes: list[FileChange]) -> list[Finding]:
    """Every finding across a change set, blocking ones first."""
    findings: list[Finding] = []
    for change in changes or []:
        findings.extend(analyze_file(change))
    return sorted(findings, key=lambda f: (not f.blocking, f.subject, f.kind))


def verdict(findings: list[Finding]) -> str:
    """``blocked`` | ``review`` | ``clear``."""
    if any(f.blocking for f in findings):
        return "blocked"
    return "review" if findings else "clear"
