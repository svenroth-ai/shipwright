"""Centralized CI-discipline test helpers + static probe.

Replaces the inline `_ci_truthy`, `_import_or_fail_in_ci`, and
`_skip_or_fail_on_missing_binary` helpers that landed in PR #26
(ADR-044) duplicated across four test files. AC-6 of that iterate was
explicitly deferred pending the SKILL.md rule maturity check; ADR-045
(iterate-2026-05-11-test-hygiene-helper-and-self-review-wiring) takes
the deferral down.

Public API:

- ``is_ci()`` — canonical truthy check for the ``CI`` env variable.
- ``import_or_fail_in_ci(plugin_name, exc)`` — replaces inline helper in
  ``shared/tests/test_setup_writes_canonical.py``.
- ``skip_or_fail_on_missing_binary(binary, install_hint)`` — replaces
  inline helper in ``plugins/shipwright-security/tests/test_oss_backend_smoke.py``.
- ``Finding`` dataclass + ``scan_for_silent_skip_without_ci_guard(files)``
  — static probe powering the iterate Self-Review's Section 8 check
  (added in this iterate).

External-review-driven design notes (recorded for future maintainers):

* Suppression markers use the ``tokenize`` module, not ``ast``, because
  ``ast`` strips comments (Gemini-1).
* Guard topology is by *AST scope* (same ``FunctionDef`` body contains
  both the skip site and a ``pytest.fail`` call gated by ``is_ci()`` or
  equivalent), not by line proximity (OpenAI-1 + Gemini-2). The prior
  "±5 lines" heuristic admits both false positives (skip followed by an
  unrelated fail) and false negatives (formatter spreads fail+skip
  across many lines).
* ``@pytest.mark.skipif`` is ALWAYS flagged — decorators run at
  collection time and cannot structurally carry a CI-gated branch;
  the canonical fix is to convert to a body-level gate (ADR-044 § AC-3).
* ``pytest.importorskip`` is out of scope for the first probe release
  (ADR-045 § Out of Scope — different anti-pattern class).
"""

from __future__ import annotations

import ast
import io
import os
import shutil
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, NoReturn

# NOTE: pytest is imported LAZILY inside `import_or_fail_in_ci` and
# `skip_or_fail_on_missing_binary` so that the CLI entrypoint
# (`shared/scripts/tools/scan_test_hygiene.py`) does not require pytest
# on the importing interpreter — the static probe only needs ast +
# tokenize. Eager `import pytest` here would crash the Self-Review § 8
# invocation in any environment without pytest installed (caught
# empirically during the iterate's asymptote-heuristic probe — the
# "confident?" question is unfalsifiable, so the answer was: run more
# probes).

__all__ = [
    "Finding",
    "import_or_fail_in_ci",
    "is_ci",
    "scan_for_silent_skip_without_ci_guard",
    "skip_or_fail_on_missing_binary",
]


# ---------------------------------------------------------------------------
# Runtime helpers — used by test files at execution time
# ---------------------------------------------------------------------------


def is_ci() -> bool:
    """Canonical truthy check for the ``CI`` env variable.

    Returns True for ``CI=true``, ``CI=True``, ``CI=TRUE``, ``CI=1``;
    False for unset, empty, ``false``, ``0``, ``yes``, ``on``, or any
    other value. The exact spelling tolerated here is pinned by
    ``shared/tests/test_silent_skip_ci_discipline.py``.
    """
    return os.environ.get("CI", "").lower() in ("true", "1")


def import_or_fail_in_ci(plugin_name: str, exc: BaseException) -> NoReturn:
    """Convert a cross-plugin sys.path-pollution ImportError into either a
    local-skip or a CI hard-fail with an actionable plugin-session hint.

    Per-site failure hint names the owning plugin so the operator knows
    exactly which plugin's pytest session covers the import. The
    cross-plugin ``lib``/``tools`` namespace collision is structural —
    every plugin defines its own ``lib/`` package — and cannot be cleanly
    fixed at sys.path level. Approach (b) from ADR-044: loud-fail in
    CI rather than runtime module isolation.
    """
    import pytest  # local import — see module-top NOTE

    plugin_session_hint = f"cd plugins/{plugin_name} && uv run pytest tests/ -v"
    if is_ci():
        pytest.fail(
            f"cross-plugin sys.path pollution prevented importing "
            f"{plugin_name} module: {exc!r}. In CI, run the test under "
            f"its plugin's pytest session instead of from shared/tests/. "
            f"Recommended invocation: {plugin_session_hint}. "
            f"See ADR-044 / ADR-045."
        )
    pytest.skip(
        f"cross-plugin sys.path pollution: {exc!r} (run "
        f"{plugin_session_hint!r} locally to exercise this test)"
    )


def skip_or_fail_on_missing_binary(binary: str, install_hint: str) -> None:
    """AC-3 (ADR-044) CI-discipline: local-skip vs CI-fail for missing
    scanner / toolchain binaries.

    Returns silently if the binary is present on PATH; otherwise raises
    either ``pytest.skip.Exception`` (local) or ``pytest.fail.Exception``
    (CI=truthy). The install hint must point to a concrete remediation
    (``actions/setup-uv@v3``, ``pip install semgrep``, ``winget install``).
    """
    import pytest  # local import — see module-top NOTE

    if shutil.which(binary) is not None:
        return
    msg = f"{binary} not on PATH. {install_hint}"
    if is_ci():
        pytest.fail(msg, pytrace=False)
    pytest.skip(msg)


# ---------------------------------------------------------------------------
# Static probe — used by Self-Review and pre-commit-style scans
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """A single silent-skip finding.

    Attributes:
        file: Path of the offending source file.
        line: 1-indexed line of the offending call/decorator.
        pattern: Short identifier of the pattern (e.g. ``"pytest.skip"``,
            ``"pytest.mark.skipif"``, ``"syntax_error"``, ``"missing_file"``).
        reason: Human-readable one-line explanation for the operator.
    """

    file: Path
    line: int
    pattern: str
    reason: str


_ALLOW_MARKER = "test-hygiene: allow-silent-skip"


def _collect_suppression_lines(source: str) -> set[int]:
    """Return 1-indexed source-line numbers carrying the allow marker.

    Uses ``tokenize`` to preserve comments (which ``ast`` strips).
    A finding on line N is suppressed if N or any contiguous comment
    block immediately above N carries the marker — matching the spec
    in ``shared/tests/test_test_hygiene.py::test_scan_respects_allow_silent_skip_marker_*``
    plus the multi-line-rationale pattern surfaced during AC-2 refactor.
    """
    suppressed: set[int] = set()
    try:
        tokens = tokenize.tokenize(io.BytesIO(source.encode("utf-8")).readline)
        for tok in tokens:
            if tok.type == tokenize.COMMENT and _ALLOW_MARKER in tok.string:
                suppressed.add(tok.start[0])
    except (tokenize.TokenizeError, SyntaxError, UnicodeDecodeError):
        # Tokenizer errors are tolerable here — the AST pass will surface
        # the underlying issue as a syntax-error Finding.
        pass
    return suppressed


def _line_is_suppressed(
    line: int,
    suppression_lines: set[int],
    source_lines: list[str],
) -> bool:
    """A finding at line N is suppressed if N carries the marker OR a
    contiguous comment block immediately above N contains the marker.

    Walks upward from N-1 as long as each line is a pure comment
    (whitespace + ``#``). Stops at the first non-comment line. If any
    line in that block is in ``suppression_lines``, the finding is
    suppressed. This matches the natural Python pattern of writing a
    multi-line rationale comment block above the offending statement.
    """
    if line in suppression_lines:
        return True
    # Walk up from N-1
    n = line - 1
    while n >= 1:
        if n in suppression_lines:
            return True
        # Index into source_lines (0-indexed) — line N is source_lines[N-1].
        if n - 1 >= len(source_lines):
            break
        stripped = source_lines[n - 1].lstrip()
        if not stripped.startswith("#"):
            break
        n -= 1
    return False


def _is_pytest_skip_call(node: ast.AST) -> bool:
    """True if node is a `pytest.skip(...)` Call expression."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "skip"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "pytest"
    )


def _is_pytest_fail_call(node: ast.AST) -> bool:
    """True if node is a `pytest.fail(...)` Call expression."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "fail"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "pytest"
    )


def _is_skipif_decorator(node: ast.expr) -> bool:
    """True if node is a `@pytest.mark.skipif(...)` decorator expression."""
    if isinstance(node, ast.Call):
        node = node.func
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "skipif"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "pytest"
    )


def _is_ci_guard_test(node: ast.AST) -> bool:
    """True if node is a CI-truthy test expression: ``is_ci()`` or its
    inverse ``not is_ci()`` or the canonical env-var expression.

    Accepted canonical guards (external-review #O4 — narrow but
    explicit):
    - ``is_ci()`` / ``not is_ci()``
    - ``os.environ.get("CI", "").lower() in ("true", "1")``
      (allowed for backward-compat with inline-helper files mid-refactor)
    """
    # Strip outer `not` — inverted-branch form is semantically equivalent.
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        node = node.operand
    # Direct `is_ci()` call
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "is_ci"
        and not node.args
    ):
        return True
    # Or `lib.test_hygiene.is_ci()` qualified
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "is_ci"
        and not node.args
    ):
        return True
    # Backward-compat: the canonical `os.environ.get(...).lower() in (...)`
    # expression. Used by files mid-refactor before they swap to is_ci().
    if (
        isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.In)
        and isinstance(node.left, ast.Call)
    ):
        call = node.left
        if (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "lower"
            and isinstance(call.func.value, ast.Call)
        ):
            inner = call.func.value
            if (
                isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "get"
                and isinstance(inner.func.value, ast.Attribute)
                and inner.func.value.attr == "environ"
            ):
                return True
    return False


def _scope_contains_ci_gated_fail(scope: ast.AST) -> bool:
    """True if `scope` contains an `If` whose test is a CI-guard AND a
    ``pytest.fail(...)`` call co-located with it.

    Three accepted shapes (all require BOTH a CI-guard If AND a fail
    that is structurally co-located — bare scope-level fails without an
    accompanying CI-guard are NOT accepted, per code-review HIGH-1):

    1. ``if is_ci(): pytest.fail(...); ...; pytest.skip(...)``
       — fail in the If's body.
    2. ``if not is_ci(): pytest.skip(...); pytest.fail(...)``
       — fail as a sibling statement AFTER the If at the same scope.
       (Used by the inverted-branch pattern in canonical lib files.)
    3. ``if is_ci(): pytest.skip(...); else: pytest.fail(...)``
       — fail in the If's orelse.

    A scope with `pytest.skip` + `pytest.fail` but NO CI-guard If is
    correctly NOT accepted (no enforcement of CI semantics).
    """
    # Pass 1: find every CI-guard If in the scope, note whether its body
    # or orelse already contains a fail.
    has_any_ci_guard_if = False
    fail_inside_guard_branch = False
    for sub in ast.walk(scope):
        if not isinstance(sub, ast.If):
            continue
        if not _is_ci_guard_test(sub.test):
            continue
        has_any_ci_guard_if = True
        for stmt in sub.body:
            for n in ast.walk(stmt):
                if _is_pytest_fail_call(n):
                    fail_inside_guard_branch = True
        for stmt in sub.orelse:
            for n in ast.walk(stmt):
                if _is_pytest_fail_call(n):
                    fail_inside_guard_branch = True
    if fail_inside_guard_branch:
        return True
    # Pass 2: inverted-branch — only legitimate when a CI-guard If exists
    # at the same scope AND a sibling fail follows. Without the guard,
    # a scope-level fail is unaccompanied and must not whitewash a skip.
    if not has_any_ci_guard_if:
        return False
    for sub in ast.iter_child_nodes(scope):
        if isinstance(sub, ast.Expr) and _is_pytest_fail_call(sub.value):
            return True
    return False


def _find_enclosing_scope(
    tree: ast.AST, target: ast.AST
) -> ast.AST | None:
    """Return the nearest enclosing FunctionDef or Module for `target`."""
    # Walk all FunctionDefs / AsyncFunctionDefs and check if target is
    # in their subtree. If not, the module itself is the scope.
    nearest: ast.AST | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if sub is target:
                    nearest = node
                    break
    return nearest if nearest is not None else tree


def scan_for_silent_skip_without_ci_guard(
    test_files: Iterable[Path],
) -> list[Finding]:
    """Scan Python source files for silent-skip patterns without a
    CI-gated `pytest.fail` companion in the same scope.

    Returns a list of ``Finding`` objects (empty if all clear). Never
    raises on individual file errors — emits ``Finding(pattern="syntax_error",
    ...)`` or ``Finding(pattern="missing_file", ...)`` instead, so a
    single bad file doesn't break a CI-time scan.

    Suppression: an offending call/decorator is silenced when the
    ``# test-hygiene: allow-silent-skip`` comment appears on the same
    line or the line above.
    """
    findings: list[Finding] = []
    for path in test_files:
        if not path.exists():
            findings.append(
                Finding(
                    file=path,
                    line=0,
                    pattern="missing_file",
                    reason=f"file does not exist: {path}",
                )
            )
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(
                Finding(
                    file=path,
                    line=0,
                    pattern="read_error",
                    reason=f"could not read file: {exc!r}",
                )
            )
            continue

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            findings.append(
                Finding(
                    file=path,
                    line=exc.lineno or 0,
                    pattern="syntax_error",
                    reason=f"SyntaxError parsing {path.name}: {exc.msg}",
                )
            )
            continue

        suppression_lines = _collect_suppression_lines(source)
        source_lines = source.splitlines()

        # 1) @pytest.mark.skipif decorators — ALWAYS flagged.
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for deco in node.decorator_list:
                    if _is_skipif_decorator(deco):
                        line = getattr(deco, "lineno", node.lineno)
                        if _line_is_suppressed(line, suppression_lines, source_lines):
                            continue
                        findings.append(
                            Finding(
                                file=path,
                                line=line,
                                pattern="pytest.mark.skipif",
                                reason=(
                                    "@pytest.mark.skipif decorator — runs at "
                                    "collection time, cannot carry a CI-gated "
                                    "branch. Convert to body-level guard "
                                    "(ADR-044 § AC-3)."
                                ),
                            )
                        )

        # 2) pytest.skip(...) calls — flag unless the enclosing scope
        # contains a CI-gated pytest.fail.
        for node in ast.walk(tree):
            if not _is_pytest_skip_call(node):
                continue
            line = node.lineno
            if _line_is_suppressed(line, suppression_lines, source_lines):
                continue
            scope = _find_enclosing_scope(tree, node)
            if scope is not None and _scope_contains_ci_gated_fail(scope):
                continue
            findings.append(
                Finding(
                    file=path,
                    line=line,
                    pattern="pytest.skip",
                    reason=(
                        "pytest.skip() without an enclosing CI-gated "
                        "pytest.fail in the same function/module body. "
                        "Wrap with `if is_ci(): pytest.fail(...)` (ADR-044)."
                    ),
                )
            )

    return findings
