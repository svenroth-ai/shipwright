"""Triage Inbox storage API.

Append-only JSONL store under `.shipwright/triage.jsonl` for findings
from hooks, scans, and audits. Triage is the pre-backlog intake; the
backlog (ExternalTask in shipwright-webui) is a separate store reached
via the explicit `promote` action.

On-disk format (JSONL, camelCase wire keys to match webui ExternalTask)
is authoritatively codified at ``shared/schemas/triage_item.schema.json``
(iterate-2026-05-21-triage-producer-contract / ADR-054). Four event kinds
share the file: a one-time header (line 1), ``append`` (one per new item),
``status`` (one per Promote/Dismiss/Park/Un-park), and ``amend`` (one per
in-place title/detail/severity/kind correction — see `lib.triage_amend`,
iterate-2026-08-08-triage-amend-event). See the schema for the full field
list including optional `dedupKey`, `launchPayload`, `frId`, `suiteId`, `eventId`.

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

def _load_triage_defer():
    """Lazy `lib.triage_defer` (park lifecycle) — same ADR-045 constraint."""
    return load_shared_lib("triage_defer")

def _load_triage_fields():
    """Lazy `lib.triage_fields` (severity/kind derivation) — ADR-045 constraint."""
    return load_shared_lib("triage_fields")

def _load_triage_amend():
    """Lazy `lib.triage_amend` (amend vocab/validation/overlay) — ADR-045 constraint."""
    return load_shared_lib("triage_amend")

#: Re-exported from `lib.triage_fields` via `__getattr__` below.
_FIELDS_NAMES = frozenset(("SEVERITIES", "KINDS", "SEVERITY_RANK", "PRIORITY_FROM_SEVERITY", "DEFAULT_DOMAIN", "DOMAIN_FROM_SOURCE", "DETAIL_MAX_LEN", "suggest_priority_from_severity", "suggest_domain_from_source", "check_optional_str", "check_detail_length"))

def __getattr__(name):  # PEP 562 — lazy `triage._FileLock`, no eager lib import
    if name == "_FileLock":
        return _load_file_lock_cls()
    if name == "AUTO_RESOLVABLE_STATUSES":
        # Re-exported so the seven auto-resolving producers read the one
        # declared answer out of the module they already import.
        return _load_triage_defer().AUTO_RESOLVABLE_STATUSES
    if name in _FIELDS_NAMES:
        return getattr(_load_triage_fields(), name)
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
#: SEVERITIES/KINDS/etc. moved to `lib.triage_fields` (bloat-budget room) — re-exported via `__getattr__` above.
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

    Concatenated records on one physical line all survive, including after a damaged
    prefix — which needs this store's record predicate so recovery cannot fabricate a
    nested object as a record. Corruption goes to stderr via ``lib.triage_integrity``,
    NOT ``warnings.warn`` (any global filter silences it — audit finding 22), and
    stays retrievable as data. Contract: ``lib/jsonl_records.py``.
    """
    integrity = load_shared_lib("triage_integrity")
    result = _load_jsonl_records().read_jsonl_records(path, is_record=integrity.is_triage_record)
    integrity.report_corruption(result.corrupt)
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
    any event kind it does not recognize anyway), just ensure the directory
    exists.
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
    _flds = _load_triage_fields()
    if severity not in _flds.SEVERITIES:
        raise ValueError(
            f"unknown severity {severity!r}; expected one of {_flds.SEVERITIES}"
        )
    if kind not in _flds.KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {_flds.KINDS}")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a non-empty string")
    _flds.check_detail_length(detail, _flds.DETAIL_MAX_LEN)
    for name, value in (("fr_id", fr_id), ("suite_id", suite_id), ("event_id", event_id)):
        _flds.check_optional_str(name, value)

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
        "suggestedPriority": _flds.suggest_priority_from_severity(severity),
        "suggestedDomain": _flds.suggest_domain_from_source(source),
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
    """Append a triage item only if no matching item already represents it.

    `to_outbox` (D1): write the gitignored outbox buffer instead of the tracked
    store (idle-main background producers). The dedup scan runs against the
    UNION (`read_all_items`), so an open match in EITHER file suppresses the
    append regardless of where the new line lands.

    Match = same `source` + `dedup_key` + (optionally) `commit`. Open and
    parked entries suppress by the configured recency policy; dismissed and
    promoted entries always suppress so an operator decision is durable.

    `window_seconds` controls the recency horizon:

    - ``int``  — only open/parked items appended within that many seconds count
      as duplicates. Re-firing after the window appends a new item.
      Phase-Quality producer uses 24h to deliberately re-flag stale
      issues daily.
    - ``None`` — no window check; any matching open or parked item suppresses
      regardless of age. Compliance
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

    _flds = _load_triage_fields()
    if severity not in _flds.SEVERITIES:
        raise ValueError(
            f"unknown severity {severity!r}; expected one of {_flds.SEVERITIES}"
        )
    if kind not in _flds.KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {_flds.KINDS}")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a non-empty string")

    _flds.check_detail_length(detail, _flds.DETAIL_MAX_LEN)
    for name, value in (("fr_id", fr_id), ("suite_id", suite_id), ("event_id", event_id)):
        _flds.check_optional_str(name, value)

    new_id = _generate_id()
    with _load_file_lock_cls()(_lock_path(project_root)):
        # One lock-bound instant governs expiry, the recency cutoff, and the
        # event timestamp. Capturing any of them before lock acquisition lets
        # contention across midnight make one append use two different days.
        defer_policy = _load_triage_defer()
        stamp = defer_policy.now_utc()
        cutoff = (
            None if window_seconds is None
            else stamp.timestamp() - window_seconds
        )
        for existing in read_all_items(
            project_root, now=stamp,
        ):
            matches = (
                existing.get("source") == source
                and existing.get("dedupKey") == dedup_key
                and (not match_commit or existing.get("commit") == commit)
            )
            if matches and (
                existing.get("status") in ("dismissed", "promoted")
                or defer_policy.suppresses_reimport(
                    existing, source=source, dedup_key=dedup_key, commit=commit,
                    match_commit=match_commit, cutoff=cutoff,
                )
            ):
                return None

        ts = stamp.isoformat().replace("+00:00", "Z")
        new_event = {
            "event": "append", "id": new_id, "ts": ts, "originalTs": ts,
            "source": source, "severity": severity, "kind": kind,
            "title": title, "detail": detail, "evidencePath": evidence_path,
            "runId": run_id, "commit": commit, "dedupKey": dedup_key,
            "launchPayload": launch_payload, "frId": fr_id,
            "suiteId": suite_id, "eventId": event_id, "status": "triage",
            "suggestedPriority": _flds.suggest_priority_from_severity(severity),
            "suggestedDomain": _flds.suggest_domain_from_source(source),
        }
        new_line = json.dumps(
            new_event, ensure_ascii=False, separators=(",", ":"),
        ) + "\n"
        _append_line(project_root, new_line, to_outbox=to_outbox)

    return new_id

# ---------------------------------------------------------------------------
# Public API: mark status
# ---------------------------------------------------------------------------

class StatusPreconditionError(ValueError):
    """A conditional status transition did not hold at write time — NOTHING was written.

    Subclasses ``ValueError`` deliberately: the background producers already
    catch broad exceptions, and ``triage_promote``'s CLI already maps
    ``ValueError`` to exit 2, so neither contract moves.

    ``expected`` is the NORMALIZED status tuple and ``actual`` is the status the
    store resolved to (``None`` when the item carries no resolvable status).
    It also reports a matching-condition block. Callers
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
    expected_by: str | None = None,
    block_matching_terminal: tuple[str, str] | None = None,
    revisit_at: str | None = None,
    require_future_revisit: bool = False,
    return_item: bool = False,
) -> str | None | tuple[str | None, dict]:
    """Append a status event for an existing item (never mutates prior lines).

    Returns the status this event REPLACED — ``None`` when the item carries no
    resolvable status. It returned nothing before
    iterate-2026-07-31-it1-s2-expected-status, which left a caller unable to
    tell a real transition from a re-flip of an already-decided item.

    ``expected_status`` / ``expected_by`` make the flip conditional: the item's currently
    resolved status/provenance are compared inside the lock this function
    already holds for the write, and a mismatch raises
    :class:`StatusPreconditionError` having written nothing. Omitted, the flip
    is unconditional exactly as before. `block_matching_terminal` atomically blocks a
    reopen when another matching card is active or terminally decided by another actor.

    **The guarantee covers writers that cooperate with this lock.** The Command
    Center uses ``proper-lockfile``, which does NOT compose with the Python
    byte lock, so a WebUI write can still interleave with this critical
    section. The precondition closes the Python producer/operator race — not
    every race. ``return_item`` also reads the fully resolved post-write card
    under this same lock, without reopening the race window.
    **Write target is DERIVED (never a caller flag):** idle main with a delivery
    path (`should_route_to_outbox` — origin + HEAD==default) → outbox, symmetric
    with `append_triage_item` (2026-06-12); else a tracked-item flip on idle main is
    undelivered drift (sweep delivers only the outbox; `reconcile_main_triage` is
    manual-CLI-only post-D2) → blocks a hand pull, never reaches origin; loss-proof
    via union-read + sweep + GC. Otherwise residence-derived: outbox-only → outbox
    (no orphan/resurrect); tracked/both → tracked (TRACKED-PREFERRED: a worktree flip ships in the PR).

    That first probe spawns three git subprocesses and reads nothing the lock
    protects, so it runs BEFORE acquiring it (IT-1 audit finding 12; the lock is
    shared with the D2 sweep). Always advisory — the lock never covered git refs —
    but now staler by the lock wait plus the in-lock reads, and a REFUSED flip pays
    a probe it skipped. Both accepted; moving it back in is what 12 forbids. RESIDENCE stays inside the lock.

    ``revisit_at`` (``YYYY-MM-DD``) is the day a parked entry returns to the
    open list by itself; rules in :mod:`lib.triage_defer`. Accepted ONLY on a
    ``snoozed`` flip and only as a real calendar date, so a malformed event
    cannot acquire park semantics. OPTIONAL here although the CLI requires it —
    the Command Center writes a date-less park and every pre-existing park has
    none; those resolve parked-but-not-due. Unlike ``reason`` the key is OMITTED
    when unset, so status lines carrying no park stay byte-identical.
    ``require_future_revisit`` is an opt-in Command Center guard: a supplied
    revisit day must still be after the UTC day observed inside this lock.

    Raises:
        FileNotFoundError: if NEITHER the tracked store NOR the outbox exists.
        KeyError: if `item_id` is not an `append` id in (tracked ∪ outbox).
        ValueError: if `new_status` or `expected_status` is not a known status,
            or `revisit_at` is malformed or given for a non-`snoozed` flip.
        StatusPreconditionError: if a conditional status/provenance/condition
            precondition did not hold (nothing written).
    """
    if new_status not in STATUSES:
        raise ValueError(
            f"unknown status {new_status!r}; expected one of {STATUSES}"
        )
    if revisit_at is not None:
        if new_status != "snoozed":
            raise ValueError(
                f"revisit_at is park semantics and is accepted only on a "
                f"'snoozed' flip, got {new_status!r}"
            )
        if _load_triage_defer().parse_revisit_date(revisit_at) is None:
            raise ValueError(
                f"revisit_at must be an exact YYYY-MM-DD calendar date, "
                f"got {revisit_at!r}"
            )
    if require_future_revisit and new_status != "snoozed":
        raise ValueError("require_future_revisit is accepted only for a 'snoozed' flip")
    expected = None if expected_status is None else _normalize_expected(expected_status)
    if expected is None and (expected_by is not None or block_matching_terminal is not None):
        raise ValueError("expected_status is required for extended preconditions")
    if expected_by is not None and not isinstance(expected_by, str):
        raise ValueError("expected_by must be a string when provided")
    if block_matching_terminal is not None and (
        not isinstance(block_matching_terminal, tuple) or len(block_matching_terminal) != 2
        or not all(isinstance(part, str) and part for part in block_matching_terminal)
    ):
        raise ValueError("block_matching_terminal must be a (source, dedup_key) pair")

    if not _triage_path(project_root).exists() and not _outbox_path(project_root).exists():
        raise FileNotFoundError(
            f"triage store not initialized at {_triage_path(project_root)} "
            f"(nor outbox at {_outbox_path(project_root)}); "
            f"run /shipwright-adopt or append an item first"
        )

    idle_main_routes_to_outbox = should_route_to_outbox(project_root)

    with _load_file_lock_cls()(_lock_path(project_root)):
        tracked_ids = _append_ids_at(_triage_path(project_root))
        outbox_ids = _append_ids_at(_outbox_path(project_root))
        if item_id not in tracked_ids and item_id not in outbox_ids:
            raise KeyError(item_id)
        now = _load_triage_defer().now_utc()
        if require_future_revisit and revisit_at is not None:
            revisit = _load_triage_defer().parse_revisit_date(revisit_at)
            if revisit is None or revisit <= _load_triage_defer().utc_date(now):
                raise ValueError("revisit_at must be a future UTC calendar date")
        items = read_all_items(project_root, now=now)
        previous_item = next((it for it in items if it.get("id") == item_id), {})
        raw_previous = previous_item.get("status")
        matching_terminal = block_matching_terminal and any(
            it.get("id") != item_id
            and it.get("source") == block_matching_terminal[0]
            and it.get("dedupKey") == block_matching_terminal[1]
            and (
                it.get("status") in _load_triage_defer().AUTO_RESOLVABLE_STATUSES
                or (it.get("status") in ("dismissed", "promoted") and it.get("statusBy") != by)
            )
            for it in items
        )
        previous = raw_previous if isinstance(raw_previous, str) else None
        if (expected is not None and previous not in expected) or (
            expected_by is not None and previous_item.get("statusBy") != expected_by
        ) or matching_terminal:
            raise StatusPreconditionError(item_id, expected, previous)
        # Idle main → outbox (like append); else residence-derived. See docstring.
        to_outbox = idle_main_routes_to_outbox or (item_id in outbox_ids and item_id not in tracked_ids)

        event = {
            "event": "status",
            "id": item_id,
            "ts": _now_z(),
            "newStatus": new_status,
            "by": by,
            "reason": reason,
            "promotedTaskId": promoted_task_id,
        }
        if revisit_at is not None:
            event["revisitAt"] = revisit_at
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        _append_line(project_root, line, to_outbox=to_outbox)
        resulting_item = next((it for it in read_all_items(project_root) if it.get("id") == item_id), {}) if return_item else None

    return (previous, resulting_item) if return_item else previous

# ---------------------------------------------------------------------------
# Public API: amend
# ---------------------------------------------------------------------------

def amend_triage_item(
    project_root: Path | str,
    item_id: str,
    *,
    by: str = "cli",
    title: str | None = None,
    detail: str | None = None,
    severity: str | None = None,
    kind: str | None = None,
    expected_status: str | tuple[str, ...] | list[str] | None = None,
    return_item: bool = False,
) -> bool | tuple[bool, dict]:
    """Append an `amend` event (never mutates prior lines; only title/detail/
    severity/kind amendable); returns True iff it landed in the gitignored
    outbox, not tracked (AC15 defers delivery-visibility parity — doubt #1).
    Raises `ValueError` on a contentless call or an unknown severity/kind.
    ``expected_status`` is an optional in-lock CAS guard; ``return_item`` adds
    the fully resolved post-write card to the return pair before releasing the
    lock.  Both keep the prior default API unchanged.
    Mirrors `mark_status`'s existence/residence/locking contract — see that
    docstring; validation/event-building delegate to `lib.triage_amend`.
    """
    _flds, _amend = _load_triage_fields(), _load_triage_amend()
    _amend.check_amend_fields(title=title, detail=detail, severity=severity, kind=kind, severities=_flds.SEVERITIES, kinds=_flds.KINDS, detail_max_len=_flds.DETAIL_MAX_LEN)
    expected = None if expected_status is None else _normalize_expected(expected_status)
    if not _triage_path(project_root).exists() and not _outbox_path(project_root).exists():
        raise FileNotFoundError(f"triage store not initialized at {_triage_path(project_root)} (nor outbox at {_outbox_path(project_root)}); run /shipwright-adopt or append an item first")
    idle_main_routes_to_outbox = should_route_to_outbox(project_root)  # git-only, OUTSIDE the lock (mirrors mark_status)
    with _load_file_lock_cls()(_lock_path(project_root)):
        to_outbox = _amend.resolve_amend_residence(item_id, tracked_ids=_append_ids_at(_triage_path(project_root)), outbox_ids=_append_ids_at(_outbox_path(project_root)), idle_main_routes_to_outbox=idle_main_routes_to_outbox)
        if expected is not None:
            item = next((it for it in read_all_items(project_root) if it.get("id") == item_id), {})
            actual = item.get("status") if isinstance(item.get("status"), str) else None
            if actual not in expected:
                raise StatusPreconditionError(item_id, expected, actual)
        event = _amend.build_amend_event(item_id, _now_z(), by, title=title, detail=detail, severity=severity, kind=kind)
        _append_line(project_root, json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n", to_outbox=to_outbox)
        resulting_item = next((it for it in read_all_items(project_root) if it.get("id") == item_id), {}) if return_item else None
    return (to_outbox, resulting_item) if return_item else to_outbox

# ---------------------------------------------------------------------------
# Public API: read (with status resolution)
# ---------------------------------------------------------------------------

def read_all_items(
    project_root: Path | str, *, now: datetime | None = None,
) -> list[dict]:
    """Return the resolved view: one dict per item, last-status-wins by file
    order. `status` flips overlay `status`/`ts`/`reason`/`promotedTaskId`/`by`
    /`revisitAt`. `amend` events overlay `title`/`detail`/`severity`/`kind`
    from the most recent VALID amend carrying each field (never `item["ts"]`,
    which stays "time of the last status decision"); an amend with any
    invalid PRESENT field is skipped WHOLE (mirrors `status`), an absent
    field is simply not applied.

    **Expired parks resolve as open (iterate-2026-08-01-triage-defer-lifecycle).**
    A `snoozed` item whose `revisitAt` day has arrived reads `triage` here and
    nothing is written to do it. Reading stays pure — the stored last event is
    still `snoozed`. Rules and rationale: :mod:`lib.triage_defer`.

    ``now`` is the aware instant every expiry question in THIS read is decided
    by, normalized to UTC once. Callers holding the lock pass their own so
    their read, suppression decision and precondition all agree.

    Returns `[]` when the file is missing or contains only the header.

    **Two-pass union resolution (D1):** tracked ∪ outbox lines. Pass 1 applies
    ALL `append` events (base records); Pass 2 applies ALL `status` AND
    `amend` events TOGETHER, ordered by ``(ts, file-order)`` — timestamp
    primary (a later event in EITHER file wins regardless of kind), file
    order a stable tiebreaker for equal ts. Load-bearing: (1) append-first
    stops an OUTBOX `append` (status:triage) clobbering a TRACKED status
    flip; (2) ts-primary ordering preserves the single-file "later line
    wins" contract across files (external review, OpenAI #5 / Gemini #1).
    """
    _defer, _amend, _flds = _load_triage_defer(), _load_triage_amend(), _load_triage_fields()
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
        # Revisit semantics belong only to a valid snoozed status event. The
        # tolerant reader must not let a hand-edited append acquire them.
        item[_defer.REVISIT_FIELD] = None
        item[_amend.AMENDED_BY_FIELD], item[_amend.AMENDED_AT_FIELD] = None, None
        resolved[item_id] = item

    # Pass 2 — overlay status flips AND amends together, by (ts, file-order):
    # timestamp is primary so a chronologically-later event in EITHER file
    # wins; file order is a STABLE tiebreaker for equal ts (clock-resolution
    # collisions), preserving the single-file "later valid line wins" contract
    # (external review, OpenAI #5 / Gemini #1). ``_ts_key`` sorts the
    # ISO-8601-Z ``ts`` string lexicographically == chronologically
    # (malformed ts → "" → earliest).
    def _ts_key(raw: dict) -> str:
        # Only a real ISO-8601-Z string participates in chronological ordering;
        # a malformed/missing ts (non-str, null, int) coerces to "" so it sorts
        # EARLIEST — i.e. is treated as "oldest / unknown time" and can never
        # outrank a later valid status (external code review, OpenAI High). The
        # file-order index then keeps malformed events stable among themselves.
        ts = raw.get("ts")
        return ts if isinstance(ts, str) else ""

    status_and_amend_events = [
        (idx, raw) for idx, raw in enumerate(raw_lines)
        if raw.get("event") in ("status", "amend")
    ]
    status_and_amend_events.sort(key=lambda t: (_ts_key(t[1]), t[0]))
    for _idx, raw in status_and_amend_events:
        item_id = raw.get("id")
        if not isinstance(item_id, str) or item_id not in resolved:
            # status/amend for unknown id (corrupt or out-of-order) — skip
            continue
        item = resolved[item_id]

        if raw.get("event") == "amend":
            _amend.try_apply_amend(item, raw, severities=_flds.SEVERITIES, kinds=_flds.KINDS, priority_from_severity=_flds.suggest_priority_from_severity)
            continue

        new_status = raw.get("newStatus")
        if new_status not in STATUSES:
            # Tolerant means skip a damaged event, not apply half of it. An
            # unknown status carrying revisitAt must not rewrite a valid park.
            continue
        item["status"] = new_status
        item["ts"] = raw.get("ts", item.get("ts"))
        item["statusBy"] = raw.get("by")
        item["statusReason"] = raw.get("reason")
        # A valid later event replaces the date: a park takes its supplied
        # value; un-park/dismiss/promote clear it even if a hand-edited event
        # illegally carries park semantics.
        item[_defer.REVISIT_FIELD] = (
            raw.get(_defer.REVISIT_FIELD) if new_status == "snoozed" else None
        )
        if raw.get("promotedTaskId") is not None:
            item["promotedTaskId"] = raw["promotedTaskId"]

    stamp = now if now is not None else _defer.now_utc()
    return _defer.apply_revisit_expiry(
        list(resolved.values()), today=_defer.utc_date(stamp),
    )
