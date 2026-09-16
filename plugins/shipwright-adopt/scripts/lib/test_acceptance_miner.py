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
- No deduping across *files* — a different FR's ACs (from a different
  candidate file) are never merged or compared against this one's.
  WITHIN one file's own bullet list, an exact-duplicate line is deduped,
  first-seen order preserved (`_dedup_preserve_order`, below) — this
  applies uniformly, not only to bullets the hygiene strip reshaped: two
  literally-identical bullets add no information the reader doesn't
  already have, whether the collision came from prefix-stripping two
  differently-dirty describes to the same clean `it` text, or from the
  source file's own test descriptions genuinely repeating verbatim.

**Hygiene filtering (trg-ac2ef362).** A mined `describe`/`it`/`test_*` label
routinely carries a code symbol (a PascalCase component name in `describe`)
or an HTTP verb+path — exactly the implementation-detail shapes FR-01.02 #5
(`_project_gate_extras_rollout.criteria_free_of_implementation_detail`, via
`fr_hygiene_detectors.violations`) hard-blocks the next time
`/shipwright-project` Step 8 re-verifies a project's spec.md. There is no
rollout-transition grace for this: mining happens live, so a fresh
onboarding after the gate's own rollout instant has no historical snapshot
to grace against, and even a one-time grant would not stop the *next*
mining run from manufacturing a new violation. The fix is at the source:
every candidate bullet is checked against the identical shared detector the
gate uses (loaded via `shared_loader.load_shared_module`, never a naive
`from lib import ...` — both this plugin's own `lib/` and `shared/scripts/
lib/` are packages named `lib`, and Python's regular-package resolution
would shadow one with the other depending on import order, ADR-044/045) —
a dirty bullet is dropped, except a JS `"<describe>: <it>"` combination
whose bare `it` half is clean, which drops only the offending prefix rather
than the whole bullet (describe-names-the-component is the single largest
source of hits; discarding the whole bullet whenever a describe label
happens to be a component name would gut mining output for a typical
React/TS codebase).
"""

from __future__ import annotations

import re
from pathlib import Path

try:  # tool context: lib/ is on sys.path (setup_adopt/_load_lib)
    from shared_loader import load_shared_module
except ImportError:  # test / package context: scripts/ on sys.path, lib is a package
    from lib.shared_loader import load_shared_module

_HYGIENE = load_shared_module(
    "scripts/lib/fr_hygiene_detectors.py", "_shipwright_adopt_fr_hygiene_detectors"
)
# Called at MODULE import time (not lazily): this module now requires the
# `shared/` tree at every import, matching the same precedent already set by
# the plugin's other 8 shared_loader consumers (doubt review, low: `shared/`
# absent is not a supported /shipwright-adopt distribution shape — every
# plugin ships alongside `shared/`, dev repo and plugin cache alike).


def _is_clean(text: str) -> bool:
    return not _HYGIENE.violations(text)


def _dedup_preserve_order(bullets: list[str]) -> list[str]:
    """Prefix-stripping two distinct dirty bullets can collapse them to the
    same clean text (e.g. two components both testing "validates input") —
    the surviving list must not carry a literal duplicate line."""
    seen: set[str] = set()
    out: list[str] = []
    for b in bullets:
        if b not in seen:
            seen.add(b)
            out.append(b)
    return out

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


_DESCRIBE_FINDER = re.compile(r"""\bdescribe\s*\(\s*(['"])([^'"]+)\1""")
_IT_FINDER = re.compile(r"""\b(it|test)\s*\(\s*(['"])([^'"]+)\2""")


def _mine_js(test_file: Path) -> list[str]:
    """Walk a JS/TS test file and emit `<describe>: <it>` bullets, picking
    the *innermost still-open* describe for each it.

    Open/closed tracking uses a brace-balance heuristic: a describe is
    considered open at position P if the count of `{` between the
    describe's match-end and P exceeds the count of `}`. Imperfect when
    string literals or comments contain unbalanced braces, but robust
    enough for typical Jest / Vitest / Mocha files. The previous
    `last_describe` heuristic mis-attributed `it`s that came after a
    sibling describe had closed (the case-2-after-inner-closes scenario)."""
    try:
        body = test_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    describes = [(m.end(), m.group(2)) for m in _DESCRIBE_FINDER.finditer(body)]
    bullets: list[str] = []

    for it_match in _IT_FINDER.finditer(body):
        it_pos = it_match.start()
        it_label = it_match.group(3)
        # Innermost still-open describe at it_pos = last describe whose
        # opening `{...` has not yet closed by it_pos.
        innermost: str | None = None
        for d_end, d_label in describes:
            if d_end > it_pos:
                break
            chunk = body[d_end:it_pos]
            if chunk.count("{") > chunk.count("}"):
                innermost = d_label
        combined = f"{innermost}: {it_label}" if innermost else it_label
        # External code review, medium: `it('')`/`test('')` captures a
        # regex-non-empty-but-blank/whitespace-only label — `_is_clean`
        # trivially passes it (no violations on blank text), so guard the
        # same way `_mine_py` already does before ever appending.
        if not it_label.strip():
            continue
        if _is_clean(combined):
            bullets.append(combined)
        elif innermost and _is_clean(it_label):
            # The describe prefix (commonly a component/module name) is what
            # carries the violation — keep the bare `it` label rather than
            # discarding an otherwise-clean behavior description.
            bullets.append(it_label)
        # else: dirty on its own terms (no prefix to strip, or stripping
        # didn't help) — dropped.

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
            candidate = doc[0].strip()
        else:
            # Function name without docstring: humanize "test_foo_bar" -> "foo bar".
            candidate = fn.removeprefix("test_").replace("_", " ")
        # External code review, low: an all-underscore name (`test___`) or a
        # whitespace-only docstring line humanizes/strips to blank — guard
        # against emitting an empty or whitespace-only bullet, since
        # `violations("")`/`violations("  ")` are both trivially clean.
        if candidate.strip() and _is_clean(candidate):
            bullets.append(candidate)
        # else: dropped — no prefix to strip for a Python label.
    return bullets


def mine_acceptance_criteria(project_root: Path, source_file: str) -> list[str]:
    """Return up to _AC_CAP bullet-point ACs harvested from the FR's
    sibling test files. Empty list when no candidates are found.

    The first candidate that yields at least one *hygiene-clean* bullet
    wins. We don't union across files to avoid bloating spec.md when a
    single FR has many test files. A candidate whose every raw label is
    dirty (trg-ac2ef362) falls through to the next sibling exactly like a
    candidate with no `it`/`test_*` calls at all — both already meant "this
    file yielded nothing usable" before hygiene filtering existed; a fully
    dirty file is simply a second reason a file can yield nothing.
    """
    candidates = _candidate_test_files(project_root, source_file)
    if not candidates:
        return []
    for cand in candidates:
        if cand.suffix == ".py":
            bullets = _mine_py(cand)
        else:
            bullets = _mine_js(cand)
        bullets = _dedup_preserve_order(bullets)
        if bullets:
            return bullets[:_AC_CAP]
    return []
