"""AST scanner for production call sites of the plain `append_triage_item`.

FR-01.14 row #1's mechanisable half (`.shipwright/planning/campaigns/
2026-07-23-req3-ac-evidence-ledger-mono.md`): "the producer contract has no
gate, and a new producer calling the plain append writes duplicates freely."
The row itself named the oracle -- "a meta-test over the call sites" -- and
this module is that oracle's mechanism. Its registry and tests live in
`shared/tests/test_triage_append_producer_registry.py`.

**Repo-wide, not two trees.** External review (both plan-review and
code-review rounds, both providers, iterate-2026-09-16-e5) rejected an
earlier revision's `("shared/scripts", "plugins")` scope as "accidentally
true, not structurally guaranteed" -- a future producer in a new top-level
directory would have evaded it silently, which is exactly the "no gate"
failure mode this module exists to close. `SEARCH_BASES` is now the repo
root; `EXCLUDED_PARTS` keeps the scan off `.venv`, test trees, and every
directory that cannot hold a real producer. **Named, not implicit (round
10, GLM, low):** the directory-NAME exclusion (any path component equal to
`"tests"`, `"build"`, etc.) is structural, not individually verified --  a
producer placed under a path merely containing one of these names (contrary
to this repo's own documented convention) would evade the scan the same
silent way a package-qualified import does. Accepted for the same reason as
limit #1: checked empirically against the live tree, not assumed, and
building per-file content sniffing to second-guess a directory-name
convention this repo has never once violated is the over-engineering the
campaign's D7 abort condition warns against.

**Real lexical scope-chain resolution, not a four-round patch.** Rounds
5-8 external review found successive defects -- nesting without scoping,
scoping without a chain, a chain without real Python SHADOWING, shadowing
without ORDER-INDEPENDENT same-scope precedence, plus a comprehension-scope
miss -- in this module's name resolution. `triage_plain_append_scope.py`
(this file's sibling) is the result: full history in its own module
docstring.

**Three named limits, still not closed** (four more, narrower ones live in
`triage_plain_append_scope.py`'s own docstring: `global`/`nonlocal`, a
`def`'s decorators/defaults/annotations evaluated in the wrong scope, the
same-scope-reassignment order trade-off, and a walrus-in-comprehension
scope miss):

1. Accepted gap: a PACKAGE-QUALIFIED or relative import of the `triage`
   module itself, in any dotted or relative shape -- `from shared.scripts
   import triage` (used as `triage.append_triage_item(...)`), `import
   shared.scripts.triage`, `from . import triage`, or a dotted `FROM`
   straight to the function (`from shared.scripts.triage import
   append_triage_item`, round 9, GLM, medium: `node.module ==
   "shared.scripts.triage"` never equals the bare `"triage"` this scanner
   resolves) -- rather than the bare `import triage` this scanner
   resolves. Checked empirically, not assumed: a repo-wide grep of every
   `import triage`-shaped line in the live tree found EXACTLY ONE
   convention in use anywhere -- the same bare form
   `test_triage_precondition_registry.py`'s own sibling guard for
   `mark_status` already relies on, unchallenged. Building a package/
   relative import resolver to guard against a shape this codebase has
   never once used is the over-engineering the campaign's D7 abort
   condition warns against.
2. Accepted gap: a call reached through `getattr(triage,
   "append_triage_item")`, or a name stored and invoked indirectly (`fn =
   triage.append_triage_item; fn(...)`). Real Python, but no producer in
   this repo's history has ever reached the function this way.
3. Accepted imprecision, in the SAFE direction -- see
   `triage_plain_append_scope.py`'s own docstring: a `ClassDef` body's own
   import is treated as visible to that class's methods, though real
   Python does not extend class-body scope into methods.

**A file this scanner cannot read is a finding, not a silent pass.**
`_read_source` uses `tokenize.open()` so a PEP 263 encoding declaration
(`# -*- coding: ... -*-`) is honoured instead of assuming UTF-8 and
mis-decoding -- external review's point that a non-UTF-8-declared file was
previously invisible to the scan entirely. A file that still cannot be
parsed (a genuine `SyntaxError`, or one no declared/guessed encoding can
decode) is recorded by `find_unparseable_files` rather than dropped: the
registry test's job is to make an evasion loud, and a broken or
deliberately-mangled file inside the scanned tree is exactly the shape of
evasion `_calls_plain_append`'s previous silent `except: return None` would
have hidden.
"""

from __future__ import annotations

import ast
import tokenize
from pathlib import Path

from lib.triage_plain_append_scope import build_scope_bindings, resolve

#: Directories that can never hold a real producer. Wider than
#: test_triage_precondition_registry.py's own list (which only ever
#: searched two known trees) because this scanner now walks the whole repo.
#: `"tests"` excludes every plugin's `tests/` dir by CLAUDE.md's own
#: documented "Plugin Structure" convention (pytest tests, never shipped
#: code) -- round 3 external review (GLM, low) raised the general case of a
#: third-party vendored `tests/` dir shipping real code; this repo has none,
#: checked structurally, not assumed. `build`/`dist`/`.tox`/`.eggs`/`.nox`
#: added round 9 (GLM, low): a packaging step copying a real producer file
#: into one of these would otherwise trip the repo-wide registry test on a
#: build artifact, not a source file.
EXCLUDED_PARTS = frozenset({
    ".venv", "tests", "integration-tests", "node_modules", ".git",
    ".worktrees", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", ".cov-data", "build", "dist", ".tox", ".eggs", ".nox",
})

#: Repo-root scan -- see the module docstring's "Repo-wide, not two trees"
#: section for why the previous two-directory scope was rejected.
SEARCH_BASES = (".",)

#: The definition module itself. `def append_triage_item(...)` is a
#: FunctionDef, not a Call, so this exclusion is belt-and-braces, not
#: load-bearing -- kept explicit so a future helper added INSIDE triage.py
#: that delegates from the idempotent path to the plain one is not silently
#: exempted by an accident of the AST walk order.
DEFINITION_MODULE = "shared/scripts/triage.py"

TARGET_NAME = "append_triage_item"

#: The EXACT module `append_triage_item` lives in, in every real call site
#: this repo has ever used. Deliberately NOT `{"triage", None}` -- an
#: earlier revision accepted bare `None` (any relative import, at any
#: level) unconditionally, which is over-permissive in exactly the
#: direction this scoping exists to close (round 2 external review). A
#: package-qualified or relative form of the REAL module is a named,
#: accepted gap instead -- see the module docstring's limit #1.
_TRIAGE_MODULE_NAME = "triage"


def _read_source(path: Path) -> str | None:
    """The file's text, honouring a PEP 263 encoding declaration if present.

    `tokenize.open()` reads the declaration (or defaults to UTF-8, same as
    `ast.parse` would) instead of assuming UTF-8 unconditionally -- a file
    correctly declared in a different encoding no longer raises
    `UnicodeDecodeError` and vanish from the scan (external review finding).
    """
    try:
        with tokenize.open(path) as fh:
            return fh.read()
    except (OSError, SyntaxError, UnicodeDecodeError, tokenize.TokenError):
        # tokenize.open() itself can raise SyntaxError on a malformed
        # encoding declaration -- caught here so it becomes an unparseable
        # finding (see find_unparseable_files), not a crash.
        return None


def _parse(path: Path) -> ast.AST | None:
    source = _read_source(path)
    if source is None:
        return None
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        # Round 7 external review (GLM, low): `ast.parse` also raises
        # `ValueError` on an embedded NUL byte, and pathological nesting can
        # raise `RecursionError` -- both must become a `find_unparseable_
        # files` finding, per this module's own contract, not an unrelated
        # crash bypassing it entirely.
        return None


def _calls_plain_append(tree: ast.AST) -> bool:
    """Uses `triage_plain_append_scope.py`'s scope-chain engine, bound to
    THIS module's two targets: the plain `append_triage_item` name, and the
    `triage` module itself (see `TARGET_NAME` / `_TRIAGE_MODULE_NAME`).
    """
    parent, plain_names, triage_aliases, other_names, call_scope = build_scope_bindings(
        tree, target_name=TARGET_NAME, module_name=_TRIAGE_MODULE_NAME
    )
    for call, scope in call_scope.items():
        func = call.func
        if isinstance(func, ast.Name) and resolve(
            scope, func.id, plain_names, other_names, parent
        ):
            return True
        if (
            isinstance(func, ast.Attribute)
            and func.attr == TARGET_NAME
            and isinstance(func.value, ast.Name)
            and resolve(scope, func.value.id, triage_aliases, other_names, parent)
        ):
            return True
    return False


def _scan_paths(repo_root: Path, bases: tuple[str, ...]) -> list[Path]:
    """Every in-scope `.py` file under `bases`.

    `rglob` can follow a symlinked directory that escapes `repo_root`
    entirely, at which point `Path.relative_to` raises `ValueError` (round 4
    external review, GLM, low) -- caught and skipped rather than crashing
    the whole scan over one stray link. This repo carries no such symlink
    today (checked, not assumed), so this is defence-in-depth, not a
    response to a live defect.
    """
    paths: list[Path] = []
    for base in bases:
        base_dir = repo_root / base
        if not base_dir.is_dir():
            continue
        for path in base_dir.rglob("*.py"):
            try:
                rel_parts = path.relative_to(repo_root).parts
            except ValueError:
                continue
            rel = "/".join(rel_parts)
            if rel == DEFINITION_MODULE:
                continue
            if any(part in EXCLUDED_PARTS for part in rel_parts):
                continue
            paths.append(path)
    return paths


def find_plain_append_callers(
    repo_root: Path, bases: tuple[str, ...] = SEARCH_BASES,
) -> set[str]:
    """Every production `.py` file under `bases` calling the plain,
    non-deduplicating `append_triage_item` -- relative POSIX paths from
    `repo_root`. AST-based, not a text/regex scan, so a reformatted or
    multi-line call is still found and `append_triage_item_idempotent(...)`
    (a DIFFERENT call name) is never mistaken for it. A file that cannot be
    read/parsed is silently excluded HERE -- see `find_unparseable_files`,
    which the registry test checks separately so a broken file cannot both
    hide a violation AND stay invisible.
    """
    found: set[str] = set()
    for path in _scan_paths(repo_root, bases):
        tree = _parse(path)
        if tree is None:
            continue
        if _calls_plain_append(tree):
            found.add(path.relative_to(repo_root).as_posix())
    return found


def find_unparseable_files(
    repo_root: Path, bases: tuple[str, ...] = SEARCH_BASES,
) -> set[str]:
    """Every in-scope `.py` file `find_plain_append_callers` could not read
    or parse -- relative POSIX paths from `repo_root`. Not itself a
    violation, but a scan GAP: a producer hidden behind a syntax error or an
    undeclared/wrong encoding is invisible to the registry test above, which
    is precisely the silent-evasion shape external review flagged. Expected
    to be empty in a healthy tree; a non-empty result means a human must look
    at the named file(s) before the registry's "found == registered" claim
    can be trusted.
    """
    return {
        path.relative_to(repo_root).as_posix()
        for path in _scan_paths(repo_root, bases)
        if _parse(path) is None
    }
