"""TS/JS silent-skip + focused-test hygiene probe (traceability G6, TT4).

A committed silent skip (``test.skip`` / ``it.skip`` / ``describe.skip`` /
``test.fixme`` / ``test.todo`` / ``xit`` / ``xfail`` …) in a Playwright/Vitest/
Jest spec must carry a structured quarantine annotation; a focused test
(``.only`` / ``fit`` / ``fdescribe``) is an *unconditional* failure — never
quarantineable. Chained modifiers (``test.only.each``, ``test.skip.each``,
``test.concurrent.only``) are matched too. Only the DECLARATION form is
flagged: Playwright's runtime conditional ``test.skip(cond, 'reason')`` (first
arg not a string literal) is exempt as a legitimate in-body guard.

Not naive regex (Spec §11 R4): ``_ts_lexer.lex`` blanks every comment / string
/ template / ``/regex/`` region before matching. Threat model = FORGOTTEN skips
+ common idiomatic forms, not adversarial obfuscation. Documented blind spots
(out of the limited-syntax scope — deeper matching is TT7/TT8): computed /
bracket-notation access (``test['skip']``), aliased bindings, ``.call``/
``.apply``, and a project with a fully custom ``testMatch``/``include``.

Quarantine syntax — a comment block immediately above the skip with an
``@quarantine`` marker plus ``reason`` + ``owner`` + ``ticket`` +
``expires: YYYY-MM-DD``. A missing field, a malformed ``expires``, an
``expires`` before today (UTC), or one more than ``_MAX_QUARANTINE_DAYS`` days
out → FAIL. Findings carry ``scope_lines`` (the call line + its quarantine
block) so a caller keeps only what a PR introduces or edits; deleting a
quarantine block re-trips its skip (``added_lines_from_diff``) but an unrelated
nearby deletion does not (AC3). See ``references/F0.5.md`` / ``§8``.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

from _ts_lexer import lex

__all__ = [
    "TsFinding",
    "added_lines_from_diff",
    "filter_to_changed",
    "is_ts_test_file",
    "scan_ts_source",
    "scan_ts_test_files",
]

# Root + optional chained ``.word`` segments + terminal method; ``\s*`` around
# dots allows valid spacing; global forms use ``(?<![\w.])`` so ``chart.fit()``
# / ``obj.xit()`` don't false-flag. The trailing ``(`` is checked separately.
_ROOT = r"(?:test|it|describe|context|suite)"
_CHAIN = r"(?:\s*\.\s*\w+)*"
_FOCUS_RE = re.compile(
    rf"\b{_ROOT}{_CHAIN}\s*\.\s*only\b|(?<![\w.])(?:fit|fdescribe)\b"
)
_SKIP_RE = re.compile(
    rf"\b{_ROOT}{_CHAIN}\s*\.\s*(?:skip|fixme|todo)\b"
    r"|(?<![\w.])(?:xit|xdescribe|xtest|xcontext|xfail)\b"
)
_QUARANTINE_FIELDS = ("reason", "owner", "ticket", "expires")
_MAX_QUARANTINE_DAYS = 180
_TS_EXT = r"(?:ts|tsx|js|jsx|mjs|cjs)"
_TS_NAME_RE = re.compile(rf"\.(?:e2e|spec|test)\.{_TS_EXT}$")
_TS_DIR_RE = re.compile(rf"(?:^|/)(?:e2e|tests?|__tests__)/.+\.{_TS_EXT}$")
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_QLINE_RE = re.compile(
    r"@quarantine|\b(?:reason|owner|ticket|expires)\s*:", re.IGNORECASE
)


@dataclass(frozen=True)
class TsFinding:
    """A single TS/JS hygiene finding. ``pattern`` ∈ js.only |
    js.skip.no_quarantine | js.skip.expired | js.skip.expiry_too_far |
    could_not_lex | read_error | missing_file. ``scope_lines`` are the lines
    whose edit brings the finding into a diff (empty for errors → always)."""

    file: Path
    line: int
    pattern: str
    reason: str
    scope_lines: frozenset[int]


def is_ts_test_file(path: Path) -> bool:
    """True for a Playwright/Vitest/Jest spec: a ``*.e2e.*``/``*.spec.*``/
    ``*.test.*`` name, OR any ts/js file under an ``e2e/``/``test(s)/``/
    ``__tests__/`` dir. A fully custom ``testMatch`` is unprotected (TT7/TT8)."""
    return bool(_TS_NAME_RE.search(path.name) or _TS_DIR_RE.search(path.as_posix()))


def _line_starts(source: str) -> list[int]:
    starts = [0]
    for idx, ch in enumerate(source):
        if ch == "\n":
            starts.append(idx + 1)
    return starts


def _skip_ws(source: str, i: int) -> int:
    n = len(source)
    while i < n and source[i] in " \t\r\n":
        i += 1
    return i


def _call_kind(source: str, end: int) -> str | None:
    # After a method name: "direct" (next is `(`), "chained" (next is `.`, e.g.
    # `.each(`), or None (not a call).
    i = _skip_ws(source, end)
    if i >= len(source):
        return None
    if source[i] == "(":
        return "direct"
    if source[i] == ".":
        return "chained"
    return None


def _first_arg_is_string(source: str, end: int) -> bool:
    """True if the direct call's first arg is a string literal (declaration)."""
    i = _skip_ws(source, end)
    if i >= len(source) or source[i] != "(":
        return False
    i = _skip_ws(source, i + 1)
    return i < len(source) and source[i] in "'\"`"


def _quarantine_block(
    line: int, code_lines: list[str], comments: dict[int, list[str]]
) -> tuple[str, frozenset[int]]:
    """Collect the contiguous pure-comment block immediately above ``line``
    (code-only content blank + comment text present). Returns the joined text
    (top-down) plus the line span, so editing the block counts as a touch."""
    block: list[str] = []
    span: set[int] = set()
    k = line - 1
    while k >= 1:
        idx = k - 1
        if idx >= len(code_lines) or code_lines[idx].strip() != "":
            break
        if k not in comments:
            break
        block.append(" ".join(comments[k]))
        span.add(k)
        k -= 1
    block.reverse()
    return "\n".join(block), frozenset(span)


def _parse_quarantine(block: str, today: date) -> tuple[str, str]:
    """Classify a quarantine block → ``(status, detail)``: ``valid``,
    ``expired``, ``too_far`` (>_MAX_QUARANTINE_DAYS out), or ``none`` (no
    marker / missing field / malformed date)."""
    if "@quarantine" not in block.lower():
        return "none", "no @quarantine annotation"
    fields: dict[str, str] = {}
    for key in _QUARANTINE_FIELDS:
        m = re.search(rf"(?im)^\s*\*?\s*{key}\s*:\s*(.+?)\s*$", block)
        if m and m.group(1).strip():
            fields[key] = m.group(1).strip()
    missing = [k for k in _QUARANTINE_FIELDS if k not in fields]
    if missing:
        return "none", f"quarantine missing field(s): {', '.join(missing)}"
    exp = fields["expires"]
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", exp)
    if not m:
        return "none", f"quarantine expires not YYYY-MM-DD: {exp!r}"
    try:
        exp_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return "none", f"quarantine expires is not a real date: {exp!r}"
    if exp_date < today:
        return "expired", (f"quarantine expired {exp} (owner {fields['owner']},"
                           f" ticket {fields['ticket']}) -- renew or retire")
    if (exp_date - today).days > _MAX_QUARANTINE_DAYS:
        return "too_far", (f"quarantine expires {exp} is >{_MAX_QUARANTINE_DAYS} "
                           "days out -- shorten it to force renewal")
    return "valid", ""


_FOCUS_REASON = (
    "focused test (.only / fit / fdescribe) silently narrows the suite -- "
    "remove it. Focused tests are never quarantineable."
)


def scan_ts_source(
    path: Path, source: str, today: date | None = None
) -> list[TsFinding]:
    """Scan one TS/JS spec source for focused/silent-skip hygiene findings."""
    today = today or datetime.now(timezone.utc).date()
    lexed = lex(source)
    code_only, comments = lexed.code_only, lexed.comments
    starts = _line_starts(source)
    code_lines = code_only.split("\n")
    findings: list[TsFinding] = []

    for ln, kind in lexed.unterminated:
        findings.append(TsFinding(
            path, ln, "could_not_lex",
            f"unterminated {kind} blanked the rest of the file -- a skip/only "
            "below it may be hidden; fix the syntax and re-run", frozenset()))

    for m in _FOCUS_RE.finditer(code_only):
        if _call_kind(source, m.end()) is None:
            continue
        ln = bisect_right(starts, m.start())
        findings.append(TsFinding(path, ln, "js.only", _FOCUS_REASON, frozenset({ln})))

    for m in _SKIP_RE.finditer(code_only):
        kind = _call_kind(source, m.end())
        if kind is None:
            continue
        # Conditional/imperative exemption applies only to the direct dotted
        # form (test.skip(cond)); chained (.skip.each) and global (xit) forms
        # are always declarations.
        if "." in m.group(0) and kind == "direct" and not _first_arg_is_string(
            source, m.end()
        ):
            continue
        ln = bisect_right(starts, m.start())
        block, span = _quarantine_block(ln, code_lines, comments)
        status, detail = _parse_quarantine(block, today)
        if status == "valid":
            continue
        if status == "expired":
            findings.append(TsFinding(
                path, ln, "js.skip.expired", detail, frozenset({ln}) | span))
        elif status == "too_far":
            findings.append(TsFinding(
                path, ln, "js.skip.expiry_too_far", detail, frozenset({ln}) | span))
        else:
            findings.append(TsFinding(
                path, ln, "js.skip.no_quarantine",
                "skipped test without a valid quarantine annotation "
                f"(reason+owner+ticket+expires) -- {detail}",
                frozenset({ln}) | span))

    return findings


def scan_ts_test_files(
    files: Iterable[Path], today: date | None = None
) -> list[TsFinding]:
    """Batch wrapper: read each file, tolerate per-file errors as findings."""
    findings: list[TsFinding] = []
    for path in files:
        if not path.exists():
            findings.append(TsFinding(
                path, 0, "missing_file", f"file does not exist: {path}", frozenset()))
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(TsFinding(
                path, 0, "read_error", f"could not read file: {exc!r}", frozenset()))
            continue
        findings.extend(scan_ts_source(path, source, today))
    return findings


def filter_to_changed(
    findings: Iterable[TsFinding], changed_by_file: dict[Path, set[int]]
) -> list[TsFinding]:
    """Keep only findings a diff introduces or edits (diff-scoped expiry).

    A finding with empty ``scope_lines`` (a file/lex error) always survives.
    """
    out: list[TsFinding] = []
    for f in findings:
        if not f.scope_lines:
            out.append(f)
            continue
        if f.scope_lines & changed_by_file.get(f.file, set()):
            out.append(f)
    return out


def added_lines_from_diff(diff_text: str) -> set[int]:
    """New-file line numbers touched in ``git diff -U0`` (``@@ -a,b +c,d @@`` →
    ``c..c+d-1``). A pure deletion (``d == 0``) contributes straddle lines ``c``
    and ``c+1`` ONLY when the deleted hunk body carried quarantine content (so
    deleting a quarantine re-trips its skip; an unrelated deletion does not)."""
    changed: set[int] = set()
    for chunk in re.split(r"(?m)^(?=@@ )", diff_text):
        m = _HUNK_RE.match(chunk)
        if not m:
            continue
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) is not None else 1
        if count > 0:
            changed.update(range(start, start + count))
            continue
        deleted = [ln[1:] for ln in chunk.splitlines()[1:] if ln.startswith("-")]
        if any(_QLINE_RE.search(d) for d in deleted):
            changed.update({start, start + 1})
    return changed
