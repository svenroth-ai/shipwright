"""Did this diff make the test suite prove less?

The AC-6 hard rule of the `main` self-heal (FR-01.19), in code rather than in
prose: a branch that repairs itself must never do it by adjusting the test until
it is green.

**AST, not diff text.** The comparison is between the *parsed* before and after
of each changed test file. Text diffing cannot distinguish a moved assertion
from a deleted one, and reading `==` → `>=` out of a unified diff is a tar pit
(external plan review, round 1).

**What is blocked** is unambiguous loss: fewer assertions in a test that still
exists, a test/class/file that no longer exists, `skip`/`skipif`/`xfail` newly
applied at module, class or function level, an *after* revision that will not
parse, and a changed test file in a language this detector cannot read.

**What is only reported** is a changed assertion *expression*. Updating a count
another pull request legitimately changed is the commonest honest repair; a rule
that blocked it would block the mechanism this exists to serve. The reviewer
sees it and the pull request must say why the new value is the truth.

**Stated limit, not implied completeness.** A relaxation that keeps the shape
(`== 5` → `== 4`) lands in the reported bucket, not the blocked one. This is a
conservative floor on mechanical coverage loss — the governing norm stays a rule
the agent is held to, and this file does not pretend otherwise.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

#: Names that switch a test off wherever they are applied.
_SKIP_MARKS = frozenset({"skip", "skipif", "xfail"})
#: Callables whose invocation inside a body switches the test off from within.
_SKIP_CALLS = frozenset({"skip", "xfail"})
#: `unittest`-style assertions, counted alongside bare `assert`.
_ASSERT_METHOD_PREFIX = "assert"
#: Context managers that assert a raise/warn happened.
_ASSERTING_CONTEXTS = frozenset({"raises", "warns", "deprecated_call"})


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
    marks: frozenset[str]


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
        tests[qualname] = _Test(
            qualname=qualname,
            assertions=tuple(_assertions(node)),
            marks=marks | frozenset(_decorator_marks(node.decorator_list))
            | frozenset(_body_marks(node)),
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
    if change.old_path and is_test_file(change.old_path) and not is_test_file(path):
        return [
            Finding(
                "test_removed_by_rename", True, f"{change.old_path} -> {path}",
                "renamed out of test collection — the assertions survive, "
                "but nothing runs them any more",
            )
        ]

    if not is_test_file(path):
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

    after_tree = _parse(change.after)
    if after_tree is None:
        return [
            Finding("unparseable", True, path,
                    "the post-change revision does not parse — fails closed")
        ]

    before_tree = _parse(change.before)
    if before_tree is None:
        # A base that never parsed is not this change's doing; blocking on it
        # would wedge every repair touching that file.
        return []

    before, after = _collect(before_tree), _collect(after_tree)
    findings: list[Finding] = []
    for qualname, was in before.items():
        now = after.get(qualname)
        if now is None:
            findings.append(
                Finding("test_removed", True, f"{path}::{qualname}",
                        "a test that existed before is gone")
            )
            continue
        new_marks = now.marks - was.marks
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
