"""The registry of flip sites, pinned in both directions, plus the one message.

Split out of `test_triage_precondition_callers.py`, which crossed 300 lines.
These are the *source-level* pins for
iterate-2026-07-31-it1-s2-expected-status; the behavioural proofs that each arm
actually runs live in that sibling file, and the store mechanism in
`test_triage_expected_status.py`.

Both directions of drift protection are here (SKILL Step 6 registry rule):
FORWARD — every registered file passes the precondition at every flip, and
reports a kept item through the one shared shape; REVERSE — no unregistered
file flips status at all, so a tenth producer cannot quietly reintroduce the
race the whole run exists to close.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import triage  # noqa: E402

#: Producers that read UNLOCKED, filter statuses per call site, then flip.
#: Every `mark_status` call in these files MUST carry the resolved precondition.
AUTOMATIC_PRODUCERS = (
    "shared/scripts/github_triage/resolve.py",
    "shared/scripts/hooks/check_drift.py",
    "shared/scripts/lib/phase_quality/_triage_bundle.py",
    "shared/scripts/tools/accepted_risks_converge.py",
    "plugins/shipwright-compliance/scripts/audit/triage_bundle.py",
    "plugins/shipwright-compliance/scripts/lib/sbom_generator.py",
    "plugins/shipwright-compliance/scripts/lib/test_evidence.py",
)

#: The operator surface. Same requirement, different reason: its own pre-check
#: is a read-then-write with no lock spanning the two. It CONVERTS the refusal
#: to its own wording rather than reporting a kept item, so it is excluded from
#: the `kept_note` pin below.
OPERATOR_PRODUCERS = ("shared/scripts/tools/triage_promote.py", "shared/scripts/lib/triage_cli_commands.py")

_CALL_NAMES = {"mark_status", "mark_status_fn"}

#: Named status sets a flip site may pass instead of an inline literal.
#:
#: The pin used to demand a literal, because at the time every site hardcoded
#: `"triage"` and a bare name could have been anything — including the
#: documented unconditional `None`. iterate-2026-08-01-triage-defer-lifecycle
#: gave the producers ONE declared answer to "which statuses may I close?"
#: (`AUTO_RESOLVABLE_STATUSES`), which is the opposite of drift, so refusing
#: names outright would now push sites back to copied literals.
#:
#: A name is accepted only if it is on this list AND
#: :func:`_resolve_status_set` proves it is a non-empty set of real statuses
#: containing no `None`. That is strictly stronger than the old literal rule:
#: a literal was never checked against `triage.STATUSES` at all.
_VETTED_STATUS_NAMES = {
    "AUTO_RESOLVABLE_STATUSES",
    "DEFERRABLE_STATUSES",
    "UNPARKABLE_STATUSES",
    "_MIGRATION_STATUSES",
}


def _literal_statuses(node: ast.AST) -> tuple | None:
    """The statuses of a literal `expected_status`, or None if not a literal."""
    if isinstance(node, ast.Constant):
        return None if node.value is None else (node.value,)
    if isinstance(node, (ast.Tuple, ast.List)):
        if not all(isinstance(e, ast.Constant) for e in node.elts):
            return None
        return tuple(e.value for e in node.elts)
    return None


def _resolve_status_set(name: str) -> tuple:
    """The runtime value behind a vetted name.

    Resolved from `lib.triage_defer`, which is where all four live (the github
    migration's own constant is a copy of the same shape and is checked as a
    literal below). Executing rather than parsing is the point: a constant
    renamed to something meaningless would still parse.
    """
    if name == "_MIGRATION_STATUSES":
        # This is deliberately the producer's real value, not a duplicate.
        # Hard-coding ("triage",) here made the pin stay green if the producer
        # drifted — exactly the mutation this registry exists to catch.
        from github_triage import resolve  # noqa: PLC0415

        return tuple(resolve._MIGRATION_STATUSES)
    from lib import triage_defer  # noqa: PLC0415

    return tuple(getattr(triage_defer, name))


def test_a_partly_dynamic_literal_is_not_certified() -> None:
    value = ast.parse('(\"triage\", dynamic_status)', mode="eval").body
    assert _literal_statuses(value) is None


def _enclosing_function(tree: ast.AST, call: ast.Call) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and any(
            child is call for child in ast.walk(node)
        ):
            return node
    return None


def _called_name(node: ast.Call) -> str | None:
    """The flip function's name, whether called bare or through a module.

    BOTH forms must be recognised. `from triage import mark_status` gives an
    `ast.Name`; `import triage; triage.mark_status(...)` gives an
    `ast.Attribute` — and the second is idiomatic here (several existing
    modules use it). Matching only the first would mean the reverse test cannot
    see the next producer written the ordinary way, which is exactly the drift
    this pin exists to catch.
    """
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        # An unparseable file elsewhere in the repo is someone else's failure;
        # it must not turn THIS test red and hide a real registry drift.
        return None


def _flip_calls_in(tree: ast.AST | None) -> list[ast.Call]:
    """Flip calls from a tree the CALLER already parsed.

    Takes the tree rather than the path on purpose: `_statuses_behind` compares
    AST nodes by identity to find a call's enclosing function, and re-parsing
    the same file yields a second set of node objects for which every `is`
    comparison is false. That silently turned the parameter-following branch
    into "resolves nothing" — caught here because that branch then failed
    closed, which is the direction it was written to fail in.
    """
    if tree is None:
        return []
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _called_name(node) in _CALL_NAMES
    ]


def _flip_calls(path: Path) -> list[ast.Call]:
    return _flip_calls_in(_parse(path))


@pytest.mark.parametrize("rel", AUTOMATIC_PRODUCERS + OPERATOR_PRODUCERS)
def test_every_registered_flip_passes_a_real_expected_status(rel: str) -> None:
    """FORWARD drift protection — asserts about the source, executes nothing.

    Presence of the keyword is not enough: `expected_status=None` is the
    documented "flip unconditionally" value, so a site could carry the kwarg,
    pass this pin, and still have the original race. The value must be a real
    one — a literal status or a tuple of them.
    """
    path = _REPO_ROOT / rel
    tree = _parse(path)
    calls = _flip_calls_in(tree)
    assert calls, f"{rel} no longer flips status — update the registry"
    for call in calls:
        kwargs = {kw.arg: kw.value for kw in call.keywords}
        assert "expected_status" in kwargs, (
            f"{rel}:{call.lineno} flips status without expected_status"
        )
        value = kwargs["expected_status"]
        assert not (isinstance(value, ast.Constant) and value.value is None), (
            f"{rel}:{call.lineno} passes expected_status=None, which is the "
            f"unconditional flip — the race is still open there"
        )
        statuses = _statuses_behind(tree, rel, call, value)
        assert statuses, (
            f"{rel}:{call.lineno} passes an expected_status this pin cannot "
            f"resolve to a real status set; the race may still be open there"
        )
        unknown = [s for s in statuses if s not in triage.STATUSES]
        assert not unknown, (
            f"{rel}:{call.lineno} expects status(es) {unknown} that the store "
            f"does not define — the precondition can never hold"
        )


def _statuses_behind(
    tree: ast.AST, rel: str, call: ast.Call, value: ast.AST,
) -> tuple:
    """Resolve one `expected_status` argument to the statuses it really means.

    Three shapes, in order of how much work each needs:

    1. a literal — read straight off the AST, as this pin always did;
    2. a **vetted name** — resolved at runtime and checked, so `AUTO_RESOLVABLE_
       STATUSES` is accepted while an arbitrary variable still is not;
    3. a **parameter of the enclosing function** — the shape `triage_promote.
       _transition(allowed=…)` and `github_triage._dismiss_if_open(expected=…)`
       introduced when three transitions started sharing one body. The pin
       follows it out to every in-module caller and resolves what each passes,
       so a caller that supplied something unvetted still fails here.

    Returns the union of the statuses found, or `()` when nothing resolves —
    which the caller treats as a failure, so an unrecognised shape is refused
    rather than waved through.
    """
    literal = _literal_statuses(value)
    if literal:
        return literal
    if not isinstance(value, ast.Name):
        return ()
    if value.id in _VETTED_STATUS_NAMES:
        return _resolve_status_set(value.id)
    func = _enclosing_function(tree, call)
    if func is None or value.id not in {a.arg for a in func.args.args + func.args.kwonlyargs}:
        return ()
    # EVERY supplier must resolve, not merely one of them. A union that
    # accepted any single good caller let a sibling pass something unvetted and
    # still go green — found by mutating one call site and watching this pin
    # stay green, which is the only way that kind of hole ever shows up.
    found: list[str] = []
    for default in func.args.kw_defaults + func.args.defaults:
        if isinstance(default, ast.Name) and default.id in _VETTED_STATUS_NAMES:
            found.extend(_resolve_status_set(default.id))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _called_name(node) == func.name):
            continue
        for kw in node.keywords:
            if kw.arg != value.id:
                continue
            supplied = _literal_statuses(kw.value) or ()
            if isinstance(kw.value, ast.Name) and kw.value.id in _VETTED_STATUS_NAMES:
                supplied = _resolve_status_set(kw.value.id)
            if not supplied:
                return ()  # one unresolvable caller fails the whole site
            found.extend(supplied)
    return tuple(found)


@pytest.mark.parametrize("rel", AUTOMATIC_PRODUCERS)
def test_every_automatic_arm_reports_through_the_one_shape(rel: str) -> None:
    """FORWARD drift protection for the reporting contract.

    Nine call sites reporting a kept item in nine wordings is how three of them
    came to say less than the other four (Stage-1 review, finding 1). The shape
    lives on the exception as `kept_note`; every arm must use it, so a site
    cannot quietly report less — or leak an item's reason text.
    """
    src = (_REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "kept_note" in src, f"{rel} reports a kept item in its own wording"


def test_no_unregistered_module_flips_status() -> None:
    """REVERSE drift protection — a tenth producer must not appear unnoticed."""
    registered = set(AUTOMATIC_PRODUCERS) | set(OPERATOR_PRODUCERS)
    found = set()
    for base in ("shared/scripts", "plugins"):
        for path in (_REPO_ROOT / base).rglob("*.py"):
            # RELATIVE parts: filtering on absolute components would skip the
            # whole tree for anyone whose checkout happens to sit under a
            # directory named `tests`, and the test would then report every
            # registry entry as stale instead of failing honestly.
            parts = path.relative_to(_REPO_ROOT).parts
            if any(p in {".venv", "tests", "node_modules"} for p in parts):
                continue
            if _flip_calls(path):
                found.add(path.relative_to(_REPO_ROOT).as_posix())
    assert found == registered, (
        f"unregistered flip sites: {sorted(found - registered)}; "
        f"stale registry entries: {sorted(registered - found)}"
    )


# --------------------------------------------------------------------------
# The one message shape, and its Windows-console safety
# --------------------------------------------------------------------------

def test_kept_note_carries_id_actual_and_expected_only() -> None:
    """Executes `StatusPreconditionError.kept_note`.

    External finding #7: the diagnostic path must not widen what is logged.
    The "and nothing else" half is structural — the exception is never handed
    the item's reason or payload — so what is asserted here is the positive
    content plus the multi-expected phrasing and the `actual is None` case.
    """
    exc = triage.StatusPreconditionError("trg-abc", ("triage",), "dismissed")
    note = exc.kept_note
    assert "trg-abc" in note and "'dismissed'" in note and "'triage'" in note
    exc2 = triage.StatusPreconditionError("trg-abc", ("snoozed", "dismissed"), None)
    assert "'snoozed' or 'dismissed'" in exc2.kept_note
    assert "None" in exc2.kept_note


def test_store_supplied_values_cannot_reach_the_console_unescaped() -> None:
    """The real hazard is the INTERPOLATED value, not the format string.

    `item_id` and `actual` are read out of a git-tracked JSONL file that any
    producer may append to, and the reader only checks that the id is a `str`.
    So both are untrusted display input on six producers' stderr — which on
    Windows is a cp1252 console. `ascii()` closes both vectors at once: a
    control character cannot forge console output (the same class of bug as the
    title that once forged a row in the CLI listing), and a non-ASCII byte
    cannot raise `UnicodeEncodeError` inside a path that is only reporting a
    benign outcome.
    """
    # BOTH interpolations carry BOTH hazards - control chars AND non-ASCII.
    # With the non-ASCII only in `actual`, reverting `ascii(item_id)` to
    # `repr(item_id)` would leave every assertion below green: `repr`
    # escapes control characters too, and differs only on non-ASCII.
    exc = triage.StatusPreconditionError(
        "trg-\x1b[2Kevilß\r\n", ("triage",), "dismißed",
    )
    for text in (str(exc), exc.kept_note):
        text.encode("ascii")           # must not raise
        assert "\x1b" not in text      # no raw escape
        assert "\r" not in text and "\n" not in text
        assert "ß" not in text    # non-ASCII escaped, not passed through
