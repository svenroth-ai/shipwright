"""Triage Inbox storage API.

Append-only JSONL store under `.shipwright/triage.jsonl` for findings
from hooks, scans, and audits. Triage is the pre-backlog intake; the
backlog (ExternalTask in shipwright-webui) is a separate store reached
via the explicit `promote` action.

On-disk format (JSONL, camelCase wire keys to match webui ExternalTask)
is authoritatively codified at ``shared/schemas/triage_item.schema.json``
(iterate-2026-05-21-triage-producer-contract / ADR-054). Three event
kinds share the file: a one-time header (line 1), ``append`` events
(one per new triage item), and ``status`` events (one per
Promote / Dismiss / Snooze). See the schema for the full field list
including optional `dedupKey`, `launchPayload`, `frId`, `suiteId`,
`eventId`.

Status resolution is by **file order** (later valid line wins). The reader
is tolerant: a line holding several concatenated records (an unterminated
predecessor let the next writer append onto it) yields ALL of them; only
undecodable text is skipped, with a warning. Record boundaries + the
writer's newline guard live in `shared/scripts/lib/jsonl_records.py`.

The module lives at `shared/scripts/triage.py` (outside `lib/`) per
ADR-045 so it can be imported from `shared/tests/` AND
`plugins/*/tests|scripts/` without colliding on `sys.modules['lib']`.

Cross-process file locking uses the shared `FileLock` class from
`shared/scripts/lib/file_lock.py`, imported LAZILY and exposed as the
historical private `_FileLock` name via module `__getattr__` — ADR-045:
no eager `lib` import at module top (iterate-2026-06-13-shc-file-lock).
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from shared_lib_loader import load_shared_lib

# Cross-platform append-log mutex + the record-boundary / header leaves live under
# lib/, but triage.py deliberately lives OUTSIDE lib/ per ADR-045 so it stays
# importable from plugins/*/{tests,scripts} (which each carry their own `lib`
# package). `shared_lib_loader.load_shared_lib` owns that import — including the
# path-based fallback for the case where a plugin's `lib` is already cached. The
# PEP 562 `__getattr__` below keeps `triage._FileLock` resolving for external
# consumers (sweep_outbox, triage_gc, reconcile_triage).
def _load_file_lock_cls():
    return load_shared_lib("file_lock").FileLock


def _load_jsonl_records():
    """Lazy `lib.jsonl_records` (record-boundary SSoT) — ADR-045 constraint above."""
    return load_shared_lib("jsonl_records")


def _load_triage_header():
    """Lazy `lib.triage_header` — same ADR-045 constraint as above."""
    return load_shared_lib("triage_header")


def __getattr__(name):  # PEP 562 — lazy `triage._FileLock`, no eager lib import
    if name == "_FileLock":
        return _load_file_lock_cls()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# ---------------------------------------------------------------------------
# Constants (Single Source of Truth — tests assert against these)
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1
TRIAGE_FILE = "triage.jsonl"
# Per-tree, GITIGNORED transient buffer for background main-tree producers
# (campaign 2026-06-08-triage-outbox-delivery / D1). Idle-main producers route
# here instead of the tracked TRIAGE_FILE so the tracked log stays clean (no
# main drift); the sweep (D2) folds it into the PR branch and GCs it. The
# outbox carries NO schema header — it is a buffer, not a store — and shares
# the canonical TRIAGE_FILE lock so producer-append and sweep serialize.
OUTBOX_FILE = "triage.outbox.jsonl"
_SHIPWRIGHT_DIR = ".shipwright"

STATUSES = ("triage", "promoted", "dismissed", "snoozed")
SEVERITIES = ("critical", "high", "medium", "low", "info")
KINDS = ("bug", "feature", "improvement", "compliance", "maintenance")
KNOWN_SOURCES = (
    "phaseQuality",
    "compliance",
    "security",
    "performance",
    "ci",
    "iterate",
    "manual",
    # legacy: the F0.5 fail-closed triage producer was removed
    # (iterate-2026-06-13-triage-not-current-work) — the gate STOPs via its exit
    # code instead. Retained so historical f0.5 items still render/launch.
    "f0.5",
    "drift",
    "github",
    # Test-phase producers — the non-blocking layers that used to leave nothing
    # behind once the session ended (iterate-2026-07-27-test-phase-record-honesty).
    "test-warning",
    "journey-coverage",
)

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

PRIORITY_FROM_SEVERITY = {
    "critical": "P0",
    "high": "P1",
    "medium": "P2",
    "low": "P3",
    "info": "P3",
}

DEFAULT_DOMAIN = "engineering"
DOMAIN_FROM_SOURCE = {"compliance": "compliance"}


# ---------------------------------------------------------------------------
# Pure mapping helpers
# ---------------------------------------------------------------------------

def _check_optional_str(name: str, value: object) -> None:
    """Reject non-string, non-None values for camelCase optional fields.

    Iterate B0 (2026-05-21) — caught by external review (H1): producers
    that pass `fr_id=42` (or any non-string) silently wrote an integer to
    disk, breaking the JSON schema at validation time. This guard turns
    that into a producer-side ValueError so misuse fails fast.
    """
    if value is None or isinstance(value, str):
        return
    raise ValueError(
        f"{name!r} must be str or None, got {type(value).__name__}"
    )


def suggest_priority_from_severity(severity: str) -> str:
    """Pure: severity → P0..P3.

    Raises ValueError on unknown severity (forces producers to pick from
    the canonical SEVERITIES enum).
    """
    try:
        return PRIORITY_FROM_SEVERITY[severity]
    except KeyError as exc:
        raise ValueError(
            f"unknown severity {severity!r}; expected one of {SEVERITIES}"
        ) from exc


def suggest_domain_from_source(source: str) -> str:
    """Pure: source → domain. Falls back to DEFAULT_DOMAIN for any
    source not in DOMAIN_FROM_SOURCE.
    """
    return DOMAIN_FROM_SOURCE.get(source, DEFAULT_DOMAIN)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _triage_path(project_root: Path | str) -> Path:
    return Path(project_root) / _SHIPWRIGHT_DIR / TRIAGE_FILE


def _outbox_path(project_root: Path | str) -> Path:
    return Path(project_root) / _SHIPWRIGHT_DIR / OUTBOX_FILE


def _lock_path(project_root: Path | str) -> Path:
    # The outbox shares this ONE canonical lock so producer-append and the D2
    # sweep (which holds it across read->commit) serialize — do NOT add a
    # separate outbox lock (Codex Q4 data-loss invariant).
    return Path(project_root) / _SHIPWRIGHT_DIR / (TRIAGE_FILE + ".lock")


def should_route_to_outbox(project_root: Path | str) -> bool:
    """True iff a real delivery path exists AND HEAD is the default branch.

    BOTH required (D1 review cascade, F2): (1) an ``origin`` remote — the outbox
    is only delivered via the D2 sweep → PR → ``origin`` path, and
    ``default_branch`` falls back to literal ``"main"`` with no ``origin/HEAD``,
    so a no-origin repo on ``main`` would route spuriously and BURY the finding;
    (2) ``current_branch == default_branch`` (idle main, not an ``iterate/*``
    branch whose writes ship in the PR — branch-based, NOT ``is_worktree``).
    Every no-origin repo, non-default branch, and git error fail safe to tracked.
    (3) NEVER under CI: a runner meets both conditions, and the gitignored outbox
    dies with it (``trg-6af8dc72``; rationale in :mod:`lib.ci_env`).
    """
    try:
        scripts_dir = str(Path(__file__).resolve().parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from lib.ci_env import ci_active  # noqa: PLC0415
        from lib.worktree_isolation import (  # noqa: PLC0415
            current_branch,
            default_branch,
            run_git,
        )

        if ci_active():
            return False
        root = Path(project_root)
        has_origin = (
            run_git(["remote", "get-url", "origin"], cwd=root, check=False).returncode
            == 0
        )
        return has_origin and current_branch(root) == default_branch(root)
    except Exception:  # noqa: BLE001
        return False


def _now_z() -> str:
    """ISO-8601 UTC timestamp with `Z` suffix (matches wire format)."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _generate_id() -> str:
    """Generate a unique triage item ID: `trg-` + 8 hex chars from UUID4."""
    return f"trg-{uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Header bootstrap
# ---------------------------------------------------------------------------

def _has_header(path: Path) -> bool:
    return _load_triage_header().has_header(path)


def _ensure_header(project_root: Path | str) -> None:
    """Create `.shipwright/triage.jsonl` with the schema header if missing.

    Idempotent — never overwrites an existing header. Caller must hold the file lock.
    """
    _load_triage_header().ensure_header(
        _triage_path(project_root), schema_version=SCHEMA_VERSION, now=_now_z()
    )


# ---------------------------------------------------------------------------
# Low-level read
# ---------------------------------------------------------------------------

def _iter_raw_lines_at(path: Path) -> list[dict]:
    """Tolerant reader for ONE file — recover concatenated records, keep order.

    A line holding several concatenated records (a writer left no trailing newline,
    so the next writer appended onto its line) yields ALL of them rather than none:
    this reader used to skip such a line whole, silently discarding every record on
    it. Undecodable text still warns, but its valid neighbours survive and
    the leaf's ``RecordRead.corrupt`` exposes it as data. Contract + rationale:
    ``lib/jsonl_records.py`` (iterate-2026-07-18-outbox-newline-corruption).
    """
    result = _load_jsonl_records().read_jsonl_records(path)
    for frag in result.corrupt:
        # ASCII-only: surfaces on Windows cp1252 consoles.
        warnings.warn(
            f"Corrupt triage record at {path.name}:{frag.line_no} "
            f"({len(frag.text)} bytes unrecoverable). Run triage_repair.py to "
            f"quarantine it; the rest of the line was recovered.",
            stacklevel=2,
        )
    return result.records


def _append_ids_at(path: Path) -> set[str]:
    """Set of `append`-event ids in ONE file (residence probe for mark_status)."""
    return {
        ln["id"] for ln in _iter_raw_lines_at(path)
        if isinstance(ln, dict) and ln.get("event") == "append"
    }


def _iter_raw_lines(project_root: Path | str) -> list[dict]:
    """Tolerant union reader — tracked lines THEN outbox lines, file order.

    The union (campaign 2026-06-08-triage-outbox-delivery / D1) makes
    background producer appends + status-flips that land in the outbox visible
    to every Python consumer immediately, without a sweep. Resolution is by id
    in :func:`read_all_items`, so a line present in both (post-sweep, pre-GC)
    collapses to one item.
    """
    out: list[dict] = []
    for path in (_triage_path(project_root), _outbox_path(project_root)):
        out.extend(_iter_raw_lines_at(path))
    return out


# ---------------------------------------------------------------------------
# Low-level write (caller holds the lock)
# ---------------------------------------------------------------------------

def _append_line(project_root: Path | str, line: str, *, to_outbox: bool) -> None:
    """Append one JSONL line under the held lock.

    Tracked target → ensure the schema header first. Outbox target → no
    header (it is a transient buffer; :func:`read_all_items` ignores
    non-append/status events anyway), just ensure the directory exists.
    """
    if to_outbox:
        path = _outbox_path(project_root)
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        _ensure_header(project_root)
        path = _triage_path(project_root)
    # Termination guard (iterate-2026-07-18-outbox-newline-corruption): never assume
    # the PREVIOUS writer left a trailing newline, or two records land on one physical
    # line. Runs inside the caller's canonical lock (every call site holds it).
    needs_separator = _load_jsonl_records().ends_without_newline(path)
    # newline="": LF on all platforms, for BOTH stores (FIX A/D2 + this run's AC-2).
    with open(path, "a", encoding="utf-8", newline="") as fp:
        if needs_separator:
            fp.write("\n")
        fp.write(line)
        fp.flush()
        os.fsync(fp.fileno())


# ---------------------------------------------------------------------------
# Public API: append
# ---------------------------------------------------------------------------

def append_triage_item(
    project_root: Path | str,
    *,
    source: str,
    severity: str,
    kind: str,
    title: str,
    detail: str,
    evidence_path: str | None = None,
    run_id: str | None = None,
    commit: str | None = None,
    dedup_key: str | None = None,
    launch_payload: str | None = None,
    fr_id: str | None = None,
    suite_id: str | None = None,
    event_id: str | None = None,
    to_outbox: bool = False,
) -> str:
    """Append a new triage item. Returns the new `trg-<8hex>` id.

    `to_outbox` (D1): True writes the per-tree GITIGNORED outbox buffer
    instead of the tracked store (idle-main background producers → no main
    drift). Default False preserves prior behavior; the write still serializes
    on the canonical lock and is visible immediately via the union reader.

    Auto-creates `.shipwright/triage.jsonl` with the schema header on
    first call (so producers are robust against adopt-not-yet-run repos
    — HIGH-3 from external review).

    Validates `severity` and `kind` against the SSoT enums; raises
    ValueError on unknown values. `source` is free-form (open vocab —
    new producers don't need code changes here), but
    `suggest_domain_from_source` only special-cases `compliance`.

    `dedup_key` is an optional producer-supplied stable identifier
    (e.g. Phase-Quality check id `C1`, compliance finding code
    `RLS-MISSING-X`). It does NOT enforce uniqueness on the wire — see
    `append_triage_item_idempotent` for the deduplicated path. The
    field is preserved so the aggregator and downstream tooling can
    correlate items across runs.

    `launch_payload` (iterate-2026-05-20-triage-launch-surface) is an optional
    ready-to-paste block (slash command + context) the operator copies into a
    new session. Stored verbatim under `launchPayload`, ALWAYS persisted (null
    when omitted), frozen at first append (AC-8).

    `fr_id` / `suite_id` / `event_id` (iterate-2026-05-21-triage-producer-contract):
    optional cross-artifact refs the RTM generator uses to render
    `FAIL → [trg-XXX](...)` links. Persisted under camelCase `frId` / `suiteId`
    / `eventId`; null is the wire default. Schema:
    `shared/schemas/triage_item.schema.json`.
    """
    if severity not in SEVERITIES:
        raise ValueError(
            f"unknown severity {severity!r}; expected one of {SEVERITIES}"
        )
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {KINDS}")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a non-empty string")
    _check_optional_str("fr_id", fr_id)
    _check_optional_str("suite_id", suite_id)
    _check_optional_str("event_id", event_id)

    item_id = _generate_id()
    ts = _now_z()
    event = {
        "event": "append",
        "id": item_id,
        "ts": ts,
        "originalTs": ts,
        "source": source,
        "severity": severity,
        "kind": kind,
        "title": title,
        "detail": detail,
        "evidencePath": evidence_path,
        "runId": run_id,
        "commit": commit,
        "dedupKey": dedup_key,
        "launchPayload": launch_payload,
        "frId": fr_id,
        "suiteId": suite_id,
        "eventId": event_id,
        "status": "triage",
        "suggestedPriority": suggest_priority_from_severity(severity),
        "suggestedDomain": suggest_domain_from_source(source),
    }
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"

    with _load_file_lock_cls()(_lock_path(project_root)):
        _append_line(project_root, line, to_outbox=to_outbox)

    return item_id


def append_triage_item_idempotent(
    project_root: Path | str,
    *,
    source: str,
    severity: str,
    kind: str,
    title: str,
    detail: str,
    dedup_key: str,
    evidence_path: str | None = None,
    run_id: str | None = None,
    commit: str | None = None,
    match_commit: bool = True,
    window_seconds: int | None = 24 * 3600,
    launch_payload: str | None = None,
    fr_id: str | None = None,
    suite_id: str | None = None,
    event_id: str | None = None,
    to_outbox: bool = False,
) -> str | None:
    """Append a triage item only if no matching item is currently open.

    `to_outbox` (D1): write the gitignored outbox buffer instead of the tracked
    store (idle-main background producers). The dedup scan runs against the
    UNION (`read_all_items`), so an open match in EITHER file suppresses the
    append regardless of where the new line lands.

    Match = same `source` + `dedup_key` + (optionally) `commit` AND
    status is `triage` (items already promoted / dismissed / snoozed
    are not re-evaluated — operators get them back if the underlying
    issue re-fires under a new id).

    `window_seconds` controls the recency horizon:

    - ``int``  — only items appended within that many seconds count as
      duplicates. Re-firing after the window appends a new item.
      Phase-Quality producer uses 24h to deliberately re-flag stale
      issues daily.
    - ``None`` — no window check; any open `triage` item with the same
      key suppresses the append, regardless of age. Compliance
      producer uses this because the same finding code is the same
      issue indefinitely until the operator resolves it.

    Returns the new item id, or `None` if a duplicate was found and
    the append was skipped.

    **Atomicity:** the dedup scan and append happen inside the same
    file-lock critical section. Two concurrent producers with the same
    `(source, dedup_key, commit)` cannot both pass the dedup check and
    both append (HIGH-1 from external code review).
    """
    if not dedup_key:
        raise ValueError("dedup_key is required for idempotent append")

    cutoff: float | None
    if window_seconds is None:
        cutoff = None
    else:
        cutoff = datetime.now(timezone.utc).timestamp() - window_seconds

    # Build the new event payload up front so the critical section is
    # tight — only the read + decision + write happen under lock.
    if severity not in SEVERITIES:
        raise ValueError(
            f"unknown severity {severity!r}; expected one of {SEVERITIES}"
        )
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {KINDS}")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a non-empty string")

    _check_optional_str("fr_id", fr_id)
    _check_optional_str("suite_id", suite_id)
    _check_optional_str("event_id", event_id)

    new_id = _generate_id()
    ts = _now_z()
    new_event = {
        "event": "append",
        "id": new_id,
        "ts": ts,
        "originalTs": ts,
        "source": source,
        "severity": severity,
        "kind": kind,
        "title": title,
        "detail": detail,
        "evidencePath": evidence_path,
        "runId": run_id,
        "commit": commit,
        "dedupKey": dedup_key,
        "launchPayload": launch_payload,
        "frId": fr_id,
        "suiteId": suite_id,
        "eventId": event_id,
        "status": "triage",
        "suggestedPriority": suggest_priority_from_severity(severity),
        "suggestedDomain": suggest_domain_from_source(source),
    }
    new_line = json.dumps(new_event, ensure_ascii=False, separators=(",", ":")) + "\n"

    with _load_file_lock_cls()(_lock_path(project_root)):
        # Dedup-scan under the same lock — readers see the merged (union) view.
        for existing in read_all_items(project_root):
            if existing.get("status") != "triage":
                continue
            if existing.get("source") != source:
                continue
            if existing.get("dedupKey") != dedup_key:
                continue
            if match_commit and existing.get("commit") != commit:
                continue
            if cutoff is None:
                # Window-less dedup — any open match suppresses.
                return None
            original_ts = existing.get("originalTs") or existing.get("ts") or ""
            try:
                existing_dt = datetime.fromisoformat(
                    original_ts.replace("Z", "+00:00")
                )
                if existing_dt.timestamp() >= cutoff:
                    return None
            except ValueError:
                # Malformed ts → conservative: treat as recent, skip.
                return None

        # No duplicate — append.
        _append_line(project_root, new_line, to_outbox=to_outbox)

    return new_id


# ---------------------------------------------------------------------------
# Public API: mark status
# ---------------------------------------------------------------------------

class StatusPreconditionError(ValueError):
    """``expected_status`` did not hold at write time — NOTHING was written.

    Subclasses ``ValueError`` deliberately: the background producers already
    catch broad exceptions, and ``triage_promote``'s CLI already maps
    ``ValueError`` to exit 2, so neither contract moves.

    ``expected`` is the NORMALIZED tuple and ``actual`` is the status the store
    resolved to (``None`` when the item carries no resolvable status). Callers
    report the skip from these attributes rather than re-reading the store,
    which would simply race a second time.
    """

    def __init__(
        self, item_id: str, expected: tuple[str, ...], actual: str | None
    ) -> None:
        self.item_id = item_id
        self.expected = expected
        self.actual = actual
        # ASCII-only, and `ascii()` not `repr()` on the store-supplied values.
        # This text reaches producer stderr, which on Windows is a cp1252
        # console, so a non-ASCII byte here would raise INSIDE a diagnostic
        # path. `item_id` is read straight out of a git-tracked JSONL file that
        # any producer may append to, and the reader only checks it is a `str`
        # — so it is untrusted display input, exactly like the title that once
        # forged a row in the CLI listing (see `triage_promote`'s sanitizer).
        # `ascii()` escapes control characters AND non-ASCII in one step.
        super().__init__(
            f"item {ascii(item_id)} has status={ascii(actual)}; expected "
            f"{self._expected_phrase()}; no status event written"
        )

    def _expected_phrase(self) -> str:
        # `expected` is validated against STATUSES, so it is already safe —
        # `ascii()` anyway keeps one rule for the whole message.
        return " or ".join(ascii(s) for s in self.expected)

    @property
    def kept_note(self) -> str:
        """The ONE line every producer prints when it keeps an item.

        Defined here, once, so the nine call sites cannot drift into nine
        wordings — and so the three that only need `except ... as exc` cannot
        quietly report less than the others. Carries id, actual and expected
        and NOTHING else: never the item's reason text, never its payload
        (external plan review, finding #7).
        """
        return (
            f"kept {ascii(self.item_id)}: status is {ascii(self.actual)}, "
            f"expected {self._expected_phrase()}"
        )


def _normalize_expected(expected_status: object) -> tuple[str, ...]:
    """One status or several → a validated tuple.

    A bare ``str`` is iterable, so testing ``previous not in expected_status``
    against the raw argument would be a SUBSTRING test — both external plan
    reviewers raised this independently. Normalizing here is what makes the
    comparison set membership. Empty and unknown members are rejected, so a
    typo cannot silently become a precondition nothing can satisfy.
    """
    if isinstance(expected_status, str):
        expected = (expected_status,)
    else:
        try:
            expected = tuple(expected_status)  # type: ignore[call-overload]
        except TypeError as exc:
            raise ValueError(
                "expected_status must be a status or an iterable of statuses, "
                f"got {type(expected_status).__name__}"
            ) from exc
    if not expected:
        raise ValueError("expected_status must name at least one status")
    for status in expected:
        # The isinstance check is not redundant with the membership test.
        # `STATUSES` is a TUPLE today, so `["triage"] not in STATUSES` compares
        # by equality and already raises the documented ValueError — external
        # code review reported a TypeError here and it did not reproduce. But
        # the guarantee is a property of `STATUSES` being a sequence, not of
        # this function; making `STATUSES` a set later would turn an unhashable
        # member into a TypeError from a validator whose contract is ValueError.
        if not isinstance(status, str) or status not in STATUSES:
            raise ValueError(
                f"unknown expected_status {status!r}; expected one of {STATUSES}"
            )
    return expected


def mark_status(
    project_root: Path | str,
    item_id: str,
    *,
    new_status: str,
    by: str,
    reason: str | None = None,
    promoted_task_id: str | None = None,
    expected_status: str | tuple[str, ...] | list[str] | None = None,
) -> str | None:
    """Append a status event for an existing item (never mutates prior lines).

    Returns the status this event REPLACED — ``None`` when the item carries no
    resolvable status. It returned nothing before
    iterate-2026-07-31-it1-s2-expected-status, which left a caller unable to
    tell a real transition from a re-flip of an already-decided item.

    ``expected_status`` makes the flip conditional: the item's currently
    resolved status is compared against it INSIDE the lock this function
    already holds for the write, and a mismatch raises
    :class:`StatusPreconditionError` having written nothing. Omitted, the flip
    is unconditional exactly as before. This is what stops a background
    producer — which reads the store unlocked, filters ``status == "triage"``,
    then flips each hit under a separate lock acquisition — from overwriting a
    decision a person recorded in between (``trg-93ceb2b0``).

    **The guarantee covers writers that cooperate with this lock.** The Command
    Center uses ``proper-lockfile``, which does NOT compose with the Python
    byte lock, so a WebUI write can still interleave with this critical
    section. The precondition closes the Python producer/operator race — not
    every race.

    **Write target is DERIVED (never a caller flag), under the lock:** idle main
    with a delivery path (`should_route_to_outbox` — origin + HEAD==default) →
    outbox, symmetric with `append_triage_item` (2026-06-12). Else a tracked-item
    flip on idle main is undelivered drift (sweep delivers only the outbox;
    `reconcile_main_triage` is manual-CLI-only post-D2) → blocks a hand pull,
    never reaches origin; loss-proof via union-read + sweep + GC. Otherwise
    residence-derived: outbox-only → outbox (no orphan/resurrect); tracked/both →
    tracked (TRACKED-PREFERRED: a worktree flip ships in the PR).

    Raises:
        FileNotFoundError: if NEITHER the tracked store NOR the outbox exists.
        KeyError: if `item_id` is not an `append` id in (tracked ∪ outbox).
        ValueError: if `new_status` or `expected_status` is not a known status.
        StatusPreconditionError: if `expected_status` did not hold (nothing written).
    """
    if new_status not in STATUSES:
        raise ValueError(
            f"unknown status {new_status!r}; expected one of {STATUSES}"
        )
    # Argument validation before any I/O, so a bad precondition fails the same
    # way whether or not the store happens to exist.
    expected = None if expected_status is None else _normalize_expected(expected_status)

    if not _triage_path(project_root).exists() and not _outbox_path(project_root).exists():
        raise FileNotFoundError(
            f"triage store not initialized at {_triage_path(project_root)} "
            f"(nor outbox at {_outbox_path(project_root)}); "
            f"run /shipwright-adopt or append an item first"
        )

    # Derive residence + write the status to the SAME store, under the lock.
    with _load_file_lock_cls()(_lock_path(project_root)):
        tracked_ids = _append_ids_at(_triage_path(project_root))
        outbox_ids = _append_ids_at(_outbox_path(project_root))
        if item_id not in tracked_ids and item_id not in outbox_ids:
            raise KeyError(item_id)
        # PREREQUISITE: `read_all_items` must stay LOCK-FREE. `FileLock` is not
        # reentrant — a read side that acquired it would not raise here, it
        # would HANG (msvcrt spin on Windows, blocking flock on POSIX). The
        # test `test_mark_status_acquires_the_canonical_lock_exactly_once` is
        # what turns that hang into a red test. Same in-lock read the dedup
        # scan in `append_triage_item_idempotent` already does.
        raw_previous = next(
            (
                it.get("status") for it in read_all_items(project_root)
                if it.get("id") == item_id
            ),
            None,
        )
        # A legacy or hand-written append line can carry a non-str `status`
        # (Pass 1 copies it verbatim). Collapsing that to None keeps the
        # documented `str | None` return TRUE, and makes such an item refuse
        # under ANY expected_status rather than be compared as some other type.
        previous = raw_previous if isinstance(raw_previous, str) else None
        if expected is not None and previous not in expected:
            raise StatusPreconditionError(item_id, expected, previous)
        # Idle main → outbox (like append); else residence-derived. See docstring.
        to_outbox = should_route_to_outbox(project_root) or (item_id in outbox_ids and item_id not in tracked_ids)

        event = {
            "event": "status",
            "id": item_id,
            "ts": _now_z(),
            "newStatus": new_status,
            "by": by,
            "reason": reason,
            "promotedTaskId": promoted_task_id,
        }
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        _append_line(project_root, line, to_outbox=to_outbox)

    return previous


# ---------------------------------------------------------------------------
# Public API: read (with status resolution)
# ---------------------------------------------------------------------------

def read_all_items(project_root: Path | str) -> list[dict]:
    """Return the resolved view: one dict per item, last-status-wins by
    file order. Items with status `triage` retain their original append
    fields; status flips overlay `status`, `ts`, plus optional
    `reason`/`promotedTaskId`/`by` from the most recent status event.

    Returns `[]` when the file is missing or contains only the header
    (so consumers don't need a separate existence check).

    **Two-pass union resolution (D1):** sources tracked ∪ outbox lines. Pass 1
    applies ALL `append` events (base records); Pass 2 applies ALL `status`
    events ordered by ``(ts, file-order)``. Load-bearing across the split: (1)
    the append-first split stops an OUTBOX `append` (status:triage) from
    clobbering a TRACKED `status` flip back to `triage`; (2) ``ts``-primary
    ordering makes the chronologically-later flip win regardless of source file
    (file order is only a STABLE tiebreaker for equal ts), preserving the
    single-file "later valid line wins by file order" contract. Both bugs were
    flagged by external review (OpenAI #5 / Gemini #1) and reproduced by probes.
    """
    raw_lines = [r for r in _iter_raw_lines(project_root) if isinstance(r, dict)]

    # Pass 1 — every append establishes a base record (union of both files).
    resolved: dict[str, dict] = {}
    for raw in raw_lines:
        if raw.get("event") != "append":
            continue
        item_id = raw.get("id")
        if not isinstance(item_id, str):
            continue
        # Initial record — strip "event" key (internal). A duplicate append for
        # the same id (post-sweep, pre-GC window) collapses to one record; the
        # later line's fields win, which is harmless (identical content).
        item = {k: v for k, v in raw.items() if k != "event"}
        item["statusBy"] = None
        item["statusReason"] = None
        item["promotedTaskId"] = None
        resolved[item_id] = item

    # Pass 2 — overlay status flips. Order by (ts, file-order): timestamp is
    # primary so a chronologically-later status in EITHER file wins; file order
    # is a STABLE tiebreaker for equal ts (clock-resolution collisions) so the
    # single-file contract "later valid line wins by file order" is preserved
    # exactly (within one file, appends are written in ascending ts; ties keep
    # file order). This resolves the cross-file status-vs-status ambiguity the
    # external plan review (OpenAI #5 / Gemini #1) flagged without breaking
    # same-ts determinism. ``enumerate`` index is the file-order tiebreaker;
    # ``_ts_key`` returns the ISO-8601-Z ``ts`` string, which sorts
    # lexicographically == chronologically (malformed ts → "" → earliest).
    def _ts_key(raw: dict) -> str:
        # Only a real ISO-8601-Z string participates in chronological ordering;
        # a malformed/missing ts (non-str, null, int) coerces to "" so it sorts
        # EARLIEST — i.e. is treated as "oldest / unknown time" and can never
        # outrank a later valid status (external code review, OpenAI High). The
        # file-order index then keeps malformed events stable among themselves.
        ts = raw.get("ts")
        return ts if isinstance(ts, str) else ""

    status_events = [
        (idx, raw) for idx, raw in enumerate(raw_lines)
        if raw.get("event") == "status"
    ]
    status_events.sort(key=lambda t: (_ts_key(t[1]), t[0]))
    for _idx, raw in status_events:
        item_id = raw.get("id")
        if not isinstance(item_id, str) or item_id not in resolved:
            # status for unknown id (corrupt or out-of-order) — skip
            continue
        item = resolved[item_id]
        new_status = raw.get("newStatus")
        if new_status in STATUSES:
            item["status"] = new_status
        item["ts"] = raw.get("ts", item.get("ts"))
        item["statusBy"] = raw.get("by")
        item["statusReason"] = raw.get("reason")
        if raw.get("promotedTaskId") is not None:
            item["promotedTaskId"] = raw["promotedTaskId"]

    return list(resolved.values())
