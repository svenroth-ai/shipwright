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

#: Producers that read the store UNLOCKED, filter `status == "triage"`, then
#: flip. Every `mark_status` call in these files MUST carry the precondition.
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
OPERATOR_PRODUCERS = ("shared/scripts/tools/triage_promote.py",)

_CALL_NAMES = {"mark_status", "mark_status_fn"}


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


def _flip_calls(path: Path) -> list[ast.Call]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        # An unparseable file elsewhere in the repo is someone else's failure;
        # it must not turn THIS test red and hide a real registry drift.
        return []
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _called_name(node) in _CALL_NAMES
    ]


@pytest.mark.parametrize("rel", AUTOMATIC_PRODUCERS + OPERATOR_PRODUCERS)
def test_every_registered_flip_passes_a_real_expected_status(rel: str) -> None:
    """FORWARD drift protection — asserts about the source, executes nothing.

    Presence of the keyword is not enough: `expected_status=None` is the
    documented "flip unconditionally" value, so a site could carry the kwarg,
    pass this pin, and still have the original race. The value must be a real
    one — a literal status or a tuple of them.
    """
    calls = _flip_calls(_REPO_ROOT / rel)
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
        assert isinstance(value, (ast.Constant, ast.Tuple, ast.List)), (
            f"{rel}:{call.lineno} passes a non-literal expected_status; this "
            f"pin can no longer tell whether the race is closed"
        )


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
