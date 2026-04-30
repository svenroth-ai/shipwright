"""Mine sibling test files for Acceptance Criteria.

Tests are the most honest spec a brownfield repo carries — every passing
test is a behavioral guarantee. /shipwright-adopt's old pipeline ignored
them entirely. The miner walks an FR's `source_file` to the conventional
sibling test files and harvests `describe(...)` / `it(...)` / `test(...)`
strings (Jest / Vitest / Mocha) and `def test_*` functions with docstrings
(pytest).

Used only when the enrichment-supplied `acceptance_draft` is empty / "TBD"
— enrichment is the richest source when it exists.

Non-goals (per the iterate spec):
- No AST-level test parsing. Regex catches every common case; the
  accuracy delta is not worth a Jest/Babel dep.
- No semantic interpretation. The mined string is the spec.
- No deduping across describe-blocks — the user gets to see redundancy.
"""

from __future__ import annotations

import re
from pathlib import Path

# Sibling-resolution candidates. For `src/foo.ts` we try, in order:
#   src/foo.test.ts, src/foo.spec.ts, src/foo.test.tsx, ... (same dir)
#   src/__tests__/foo.test.ts, src/__tests__/foo.spec.ts ...
#   tests/foo.test.ts, tests/foo.test.py, tests/test_foo.py
# All silent on absence. Iteration stops when at least one match yields ACs
# (we don't union across multiple test files for the same FR — the closest
# sibling wins — to keep the spec clean).
_JS_TEST_SUFFIXES = (".test.ts", ".test.tsx", ".test.js", ".test.jsx",
                     ".test.mjs", ".test.cjs",
                     ".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx")
_PY_PREFIX = "test_"
_AC_CAP = 10  # max bullets per FR; beyond this we're flooding spec.md


def _candidate_test_files(project_root: Path, source_file: str) -> list[Path]:
    """Return existing sibling test paths to consult for an FR."""
    if not source_file or source_file == "—":
        return []
    src_path = (project_root / source_file).resolve()
    if not src_path.exists() or src_path.is_dir():
        # The path may not exist (e.g. fixture-only test fixtures), but
        # we can still derive candidates from string manipulation.
        src_path = (project_root / source_file).resolve()
    parent = src_path.parent
    stem = src_path.stem
    suffix = src_path.suffix.lower()

    candidates: list[Path] = []
    if suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        # Same directory siblings
        for s in _JS_TEST_SUFFIXES:
            candidates.append(parent / f"{stem}{s}")
        # __tests__ subdirectory
        for s in _JS_TEST_SUFFIXES:
            candidates.append(parent / "__tests__" / f"{stem}{s}")
        # Top-level tests/ mirror
        try:
            rel = src_path.relative_to(project_root)
            top_tests = project_root / "tests" / Path(*rel.parts[1:]).with_suffix("")
            for s in _JS_TEST_SUFFIXES:
                candidates.append(top_tests.parent / f"{top_tests.name}{s}")
            # Also tests/<basename>.<test-suffix>
            for s in _JS_TEST_SUFFIXES:
                candidates.append(project_root / "tests" / f"{stem}{s}")
        except ValueError:
            pass
    elif suffix == ".py":
        # Same directory: test_<stem>.py
        candidates.append(parent / f"{_PY_PREFIX}{stem}.py")
        # Top-level tests/test_<stem>.py
        candidates.append(project_root / "tests" / f"{_PY_PREFIX}{stem}.py")
        # __tests__ rarely used in python but cheap to check
        candidates.append(parent / "__tests__" / f"{_PY_PREFIX}{stem}.py")

    # Filter to those that actually exist, preserving order.
    return [p for p in candidates if p.is_file()]


# `describe('label', ...)` and `it('case', ...)` and `test('case', ...)`.
# Single OR double quote. Capture group 2 is the label.
_DESCRIBE_RE = re.compile(
    r"""\bdescribe\s*\(\s*(['"])([^'"]+)\1""",
)
_IT_RE = re.compile(
    r"""\b(it|test)\s*\(\s*(['"])([^'"]+)\2""",
)


def _mine_js(test_file: Path) -> list[str]:
    """Walk a JS/TS test file. Output: '<describe>: <it>' bullets when a
    describe was the most-recent ancestor; bare '<it>' otherwise."""
    try:
        body = test_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    bullets: list[str] = []
    last_describe: str | None = None
    # Walk in source order so the right describe wraps each it/test.
    iter_pos = 0
    pattern = re.compile(
        r"""\bdescribe\s*\(\s*(['"])([^'"]+)\1|\b(it|test)\s*\(\s*(['"])([^'"]+)\4"""
    )
    for m in pattern.finditer(body):
        if m.group(2) is not None:  # describe match
            last_describe = m.group(2)
        else:  # it / test match
            label = m.group(5)
            bullet = f"{last_describe}: {label}" if last_describe else label
            bullets.append(bullet)
        iter_pos += 1
    return bullets


# `def test_<name>(...)` plus optional docstring on the next line(s).
_PY_TEST_FN_RE = re.compile(
    r"""^\s*def\s+(test_[A-Za-z0-9_]+)\s*\([^)]*\)\s*:\s*\n"""
    r"""(?:\s*\"\"\"([^\"]+?)\"\"\"|\s*'''([^']+?)''')?""",
    re.MULTILINE,
)


def _mine_py(test_file: Path) -> list[str]:
    try:
        body = test_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    bullets: list[str] = []
    for m in _PY_TEST_FN_RE.finditer(body):
        fn = m.group(1)
        doc = (m.group(2) or m.group(3) or "").strip().splitlines()
        if doc:
            bullets.append(doc[0].strip())
        else:
            # Function name without docstring: humanize "test_foo_bar" -> "foo bar".
            humanized = fn.removeprefix("test_").replace("_", " ")
            bullets.append(humanized)
    return bullets


def mine_acceptance_criteria(project_root: Path, source_file: str) -> list[str]:
    """Return up to _AC_CAP bullet-point ACs harvested from the FR's
    sibling test files. Empty list when no candidates are found.

    The first existing candidate wins. We don't union across files to
    avoid bloating spec.md when a single FR has many test files.
    """
    candidates = _candidate_test_files(project_root, source_file)
    if not candidates:
        return []
    for cand in candidates:
        if cand.suffix == ".py":
            bullets = _mine_py(cand)
        else:
            bullets = _mine_js(cand)
        if bullets:
            return bullets[:_AC_CAP]
    return []
