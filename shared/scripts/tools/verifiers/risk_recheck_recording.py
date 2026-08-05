"""Recording-integrity gate for the campaign sub-iterate-runner's Step 3.4
diff-driven risk re-check (`diff_risk_recheck.py` / `risk_recheck_record.py`).

Step 3.4 computes ``effective_complexity`` from the real diff and the runner
contract says F5c MUST record that value — but until this gate existed nothing
checked that it did. A runner could silently write Step 2's stale, message-only
estimate into the F5c entry instead, and no gate caught it: `check_integration_coverage`
(``integration_coverage.py``) reads the F5c complexity for its diagnostic
``_floor_note`` but, since iterate-2026-08-01-coverage-gate-recompute-order,
never uses it for control flow — so it was never going to catch this either.

This matters beyond any one gate: the F5c-recorded ``complexity`` is a durable,
cross-run input — `classify_complexity`'s history-prior fallback
(``prior_source: history``) reads the median of exactly these values for every
OTHER no-keyword iterate in the project. An unenforced under-record doesn't
just make one run's own audit trail wrong; it quietly corrupts the classifier
every future run falls back on.

**This is a TRANSCRIPTION-integrity check, not independent re-verification.**
It proves the F5c-recorded complexity honors what Step 3.4's persisted
artifact says it computed — it does not re-derive `effective_complexity` from
the diff itself. A runner could still edit `risk_recheck.json` to a lower
value before F6 and this gate would not catch that: closing that residual
would need an independently reproducible fingerprint or a re-run of the
diff-driven detectors at F11, which is out of scope here (matches this
codebase's existing acknowledgement that every runner-contract step is
contract-enforced, not independently gated — this is not a new category of
that gap).

**Campaign-only, by absence.** Step 3.4 never runs for a standalone iterate,
so the artifact this gate reads is only ever produced by a campaign
sub-iterate-runner. Its absence is a SKIP, not a failure — every standalone
iterate and every pre-existing campaign run from before this contract must be
unaffected.

**A write failure can no longer reach this SKIP through a normal run**
(Stage-3 doubt review, then closed by external code review 2026-08-05):
`diff_risk_recheck.main()` now turns a `write_recheck_record` failure into a
non-zero exit on EVERY path — 2 on continue, 3 (unchanged) on CI escalation —
so the runner contract's own "any other non-zero: STOP, never continue on a
stale estimate" instruction means Finalization (and therefore F5c) is never
reached for a run whose artifact write failed. The SKIP message still does
not claim a specific cause, though: that guarantee holds only as long as the
runner FOLLOWS its own contract, which (like every other runner-contract step
in this codebase) is contract-enforced, not code-enforced — so "standalone or
pre-contract" remains an inference, never a certainty this gate can verify.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.iterate_entry import find_entry_by_run_id  # noqa: E402
from lib.review_record_schema import is_safe_run_id  # noqa: E402

from .common import CheckResult, Severity  # noqa: E402

#: Self-contained, drift-pinned copy of
#: ``plugins/shipwright-iterate/scripts/lib/complexity_vocabulary.COMPLEXITY_ORDER``.
#: This load-bearing verifier never cross-plugin-imports the iterate-plugin lib
#: (ADR-044). ``test_complexity_order_sync`` pins this == the SSoT.
_COMPLEXITY_ORDER = ("trivial", "small", "medium", "large")

#: Must match ``risk_recheck_record.RECHECK_SCHEMA_VERSION`` — a plugin-lib
#: constant this shared verifier cannot import (ADR-044), so the two are kept
#: in lock-step by ``test_recheck_schema_version_sync``.
RECHECK_SCHEMA_VERSION = 1


def _rank(level: object) -> int | None:
    """Index in the canonical order, or ``None`` for anything unrecognized.

    Never raise on a bad value: an artifact this gate reads is a self-report,
    and a malformed one must fail the check, not crash the whole F11 run.
    """
    if not isinstance(level, str):
        return None
    try:
        return _COMPLEXITY_ORDER.index(level)
    except ValueError:
        return None


def recheck_record_relpath(run_id: str) -> str:
    return f".shipwright/planning/iterate/{run_id}/risk_recheck.json"


def _read_recheck_record(project_root: Path, run_id: str) -> tuple[dict | None, str | None]:
    """Return ``(block, error)``.

    ``(None, None)`` means genuine absence — the SKIP path (standalone iterate,
    or a run that predates this contract). Any other outcome with ``error`` set
    means the artifact exists but is unusable — the FAIL path. Reads the
    WORKING TREE, mirroring `integration_coverage._read_entry`'s read of the F5c
    entry: this is a same-run self-report comparison, not a diff computation,
    so (unlike `ci_supplychain_ack`'s content-fingerprint concern, which
    guards against re-editing a CI file after acknowledging it) there is no
    analogous "content changed after the fact" property to defend here — see
    the module docstring's transcription-integrity boundary.

    An unsafe `run_id` and a `<run_id>` directory that resolves OUTSIDE the
    planning tree (a symlinked path component) both FAIL rather than SKIP —
    a stale or foreign artifact must not silently license this run (external
    code review, 2026-08-05). A dangling or non-regular-file symlink at the
    artifact path is malformed, never genuine absence: `path.exists()` alone
    follows the link and reports `False` for a dangling one, which would
    otherwise misreport a planted-but-broken symlink as "nothing to see here".
    """
    if not is_safe_run_id(run_id):
        return None, (f"run id {str(run_id)[:60]!r} is not a single safe path "
                      "component — the risk-recheck artifact cannot be located")
    rel = recheck_record_relpath(run_id)
    path = project_root / rel
    root = (Path(project_root) / ".shipwright" / "planning" / "iterate").resolve()
    try:
        path.parent.resolve().relative_to(root)
    except ValueError:
        return None, (f"{rel} resolves outside {root} — refusing to read through "
                      "what a symlinked run directory would make an escape")
    if path.is_symlink():
        return None, f"{rel} is a symlink, not a regular file"
    if not path.exists():
        return None, None
    if not path.is_file():
        return None, f"{rel} exists but is not a regular file"
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"{rel} is unreadable ({exc})"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"{rel} is unreadable/corrupt ({exc})"
    if not isinstance(data, dict):
        return None, f"{rel} is not a JSON object"
    version = data.get("schema_version")
    if version != RECHECK_SCHEMA_VERSION:
        return None, (f"{rel} is schema_version {version!r}, which this verifier "
                      f"cannot read (expected {RECHECK_SCHEMA_VERSION})")
    envelope_run_id = data.get("run_id")
    if envelope_run_id != run_id:
        return None, (f"{rel} belongs to another run "
                      f"({envelope_run_id!r} != {run_id!r}) — a stale artifact "
                      "cannot license this run")
    block = data.get("risk_recheck")
    if not isinstance(block, dict):
        return None, f"{rel} carries no `risk_recheck` object"
    return block, None


def _read_f5c_complexity(project_root: Path, run_id: str) -> tuple[str | None, str | None]:
    """The F5c-recorded complexity for this run, or an error naming why not.

    `.shipwright/agent_docs/iterates/<run_id>.json` is a one-file-per-run_id
    store with a single writer (`append_iterate_entry.py`, F5c) — there is no
    "which entry is the real F5c record" ambiguity the way there might be in
    an append-only log.
    """
    try:
        entry = find_entry_by_run_id(project_root, run_id)
    except (ValueError, OSError):
        return None, "the F5c entry could not be read (corrupt or unreadable)"
    if not isinstance(entry, dict):
        return None, f"no F5c entry found for {run_id}"
    complexity = entry.get("complexity")
    if not isinstance(complexity, str):
        return None, "the F5c entry has no valid `complexity` field"
    return complexity, None


def check_risk_recheck_recorded(project_root: Path, run_id: str) -> CheckResult:
    """Recording-integrity gate — see module docstring for the full rationale.

    FAILs when the F5c-recorded complexity is outranked by Step 3.4's recorded
    `effective_complexity`. SKIPs when no Step 3.4 artifact exists for this run.
    """
    name = "risk re-check recording integrity"
    block, err = _read_recheck_record(project_root, run_id)
    if block is None and err is None:
        # Absence is reported WITHOUT claiming why: the likeliest cause is a
        # standalone iterate (Step 3.4 never runs there) or a pre-contract
        # campaign run, but a campaign run whose write_recheck_record() call
        # itself failed (surfaced as `recheck_record_error` in that run's
        # result.json, not read by anything today — a stated residual, see
        # module docstring) looks IDENTICAL from here. Naming only the
        # standalone/pre-contract causes would misattribute that third case
        # (Stage-3 doubt review).
        return CheckResult(
            name, True,
            "skipped (no Step 3.4 risk re-check artifact found for this run)",
            severity=Severity.SKIPPED.value,
        )
    if err:
        return CheckResult(name, False, err)

    effective = block.get("effective_complexity")
    eff_rank = _rank(effective)
    if eff_rank is None:
        if "effective_complexity" not in block:
            return CheckResult(
                name, False,
                "the recorded risk re-check lacks an `effective_complexity` field",
            )
        return CheckResult(
            name, False,
            f"the recorded risk re-check has an unrecognized effective_complexity "
            f"({effective!r}) — expected one of {_COMPLEXITY_ORDER}",
        )

    complexity, f5c_err = _read_f5c_complexity(project_root, run_id)
    if f5c_err:
        return CheckResult(
            name, False,
            f"Step 3.4 recorded effective_complexity={effective!r} but {f5c_err} — "
            "an under-recording run must not escape this gate by omitting F5c",
        )
    rec_rank = _rank(complexity)
    if rec_rank is None:
        return CheckResult(
            name, False,
            f"the F5c entry recorded an unrecognized complexity ({complexity!r}) — "
            f"expected one of {_COMPLEXITY_ORDER}",
        )
    if rec_rank < eff_rank:
        return CheckResult(
            name, False,
            f"Step 3.4 computed effective_complexity={effective!r} but F5c recorded "
            f"complexity={complexity!r} — the recorded tier is outranked by what the "
            "diff-driven re-check found. Re-run F5c with the correct complexity, or "
            "record why the re-check's floor over-fired.",
        )
    return CheckResult(
        name, True,
        f"F5c complexity={complexity!r} honors Step 3.4's effective_complexity={effective!r}",
    )
