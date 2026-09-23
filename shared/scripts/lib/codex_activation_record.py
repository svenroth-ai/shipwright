"""Codex activation-record library (R2 — AC1a).

Exclusive-create mint-once / exclusive-consume-once state for gating a
Codex-driven iterate session's first gated tool call. Minted by the
``UserPromptSubmit`` hook (Step 5) after a successful
``codex_envelope_grammar.parse()``, consumed by the ``PreToolUse`` hook
(Step 6) on its first locally-gated tool call.

**Fail-open is a hard, pre-decided contract (R0's ADR), not a choice made
here.** Absent, corrupt, schema-mismatched, cwd-mismatched, or expired
records are all unconditionally "no record" to ``read()``/``consume()`` —
never an exception, never a denial by default. The only thing enforced
strictly is exclusivity: ``mint()`` never overwrites an existing record,
``consume()`` never lets a second caller claim one already consumed.

**Storage:** ``<project_root>/.shipwright/runtime/codex-activation/
<session>.json`` plus a same-named ``.consumed`` sidecar — both gitignored.
One file per ``session_id`` (the storage key); ``turn_id``/``cwd``/
``generation`` are recorded FIELDS. Only ``cwd`` (via ``normalize_cwd()``)
is re-validated today, alongside ``schema_version`` and expiry —
``turn_id``/``generation`` are write-only, for a future consumer (R2b).

**Exclusive-create** mirrors ``lib.event_once._create``'s
``os.O_CREAT | os.O_EXCL`` (atomic on POSIX and Windows) rather than
``durable_atomic_write``, an unconditional tmp+replace that would silently
violate the never-overwrite contract. ``generation`` is a random opaque
token stamped at mint time, not a counter — so a test can show a
``consume()`` validates the SAME minted instance, not a recreated one.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import secrets
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

try:  # loaded as ``lib.codex_activation_record``
    from . import git_base
    from .atomic_write import durable_read_text
except ImportError:  # loaded as top-level ``codex_activation_record`` (lib/ on sys.path)
    import git_base
    from atomic_write import durable_read_text

_SCHEMA_VERSION = 1
_RUNTIME_SUBDIR = ("runtime", "codex-activation")
#: Same sanitization spirit as ``lib.event_once``'s claim-file tokens: an
#: unexpected session_id (separators, ``..``) can never escape the runtime
#: dir. A theoretical same-token collision across two distinct raw
#: session_ids is unguarded — real session_ids are UUID-shaped, already
#: inside this charset.
_SAFE_TOKEN_RE = re.compile(r"[^A-Za-z0-9._-]")
#: Generous by default: expiry here is an anti-staleness safety net, not a
#: security boundary (read()/consume() fail open on expiry regardless), so
#: erring toward "still armed" is the safer of the two wrong defaults.
_DEFAULT_TTL_SECONDS = 1800.0


@dataclass(frozen=True)
class ActivationRecord:
    schema_version: int
    session_id: str
    turn_id: str
    cwd: str
    generation: str
    armed: bool
    skill_id: str | None
    args: dict | None
    minted_at: float
    expiry: float


def _safe_token(value: str) -> str:
    return _SAFE_TOKEN_RE.sub("_", value or "") or "unknown"


def normalize_cwd(cwd: str) -> str:
    """Resolve ``cwd`` to its git-identity path (the MAIN repo root, never a
    linked worktree) so a worktree-invoked hook and a main-checkout-invoked
    one agree on "same repo" instead of comparing path spelling literally
    (mini-plan Step 4). Falls back to ``cwd`` UNCHANGED on any git failure —
    must never raise, matching the module's fail-open contract. Public
    (code review, MEDIUM): three call sites previously duplicated this body."""
    try:
        return str(git_base.main_repo_root(Path(cwd)))
    except (git_base.GitError, OSError, subprocess.SubprocessError):
        return cwd


def _record_dir(project_root: str | os.PathLike[str]) -> Path:
    return Path(project_root).joinpath(".shipwright", *_RUNTIME_SUBDIR)


def _record_path(project_root: str | os.PathLike[str], session_id: str) -> Path:
    return _record_dir(project_root) / f"{_safe_token(session_id)}.json"


def _consumed_path(project_root: str | os.PathLike[str], session_id: str) -> Path:
    return _record_dir(project_root) / f"{_safe_token(session_id)}.consumed"


def _has_valid_field_types(record: ActivationRecord) -> bool:
    """A syntactically valid JSON object can carry wrong field types
    (``"expiry": null``) and still construct via ``ActivationRecord(**payload)`` —
    the ``TypeError`` fires later, at ``ts >= record.expiry`` (external review,
    openai medium). ``bool`` is an ``int`` subclass, so numeric fields reject it."""
    str_fields = (record.session_id, record.turn_id, record.cwd, record.generation)
    numbers = (record.minted_at, record.expiry)
    return (
        all(isinstance(v, str) for v in str_fields)
        and isinstance(record.armed, bool)
        and (record.skill_id is None or isinstance(record.skill_id, str))
        and (record.args is None or isinstance(record.args, dict))
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in numbers)
        and all(math.isfinite(v) for v in numbers)
    )


def _exists_fail_open(path: Path) -> bool:
    """``path.exists()`` treating a stray OSError as "not found" (fail-open, code review medium)."""
    try:
        return path.exists()
    except OSError:
        return False


def _purge_expired_records(directory: Path, *, now: float) -> None:
    """Best-effort reap of expired record/sidecar pairs (doubt-review,
    medium: mirrors ``lib.event_once._purge_expired_claims`` — this module
    had no GC, so every pair persisted forever, invisible to the bloat gate
    since it's gitignored). Runs once per NEW session, on ``mint()``'s
    exclusive-create path only. Fail-open."""
    try:
        candidates = tuple(directory.glob("*.json"))
    except OSError:
        return
    for candidate in candidates:
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            expiry = float(payload["expiry"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if now < expiry:
            continue
        # `.consumed` first (code review, low): an interruption between the
        # two unlinks must never leave an orphaned `.consumed` with no
        # `.json` -- that would wrongly deny a future consume() for a
        # reused session_id. Leaving `.json` behind instead just means the
        # expired record persists a bit longer, already a normal state here.
        with contextlib.suppress(OSError):
            candidate.with_suffix(".consumed").unlink()
        with contextlib.suppress(OSError):
            candidate.unlink()


def _exclusive_create(path: Path, data: str) -> bool | None:
    """Atomic exclusive create. True=created (winner), False=exists, None=I/O
    error (both treated as "did not win" by callers — fail-open, never a crash)."""
    try:
        # 0o600 (owner-only): single-user local runtime state, not shared.
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    except OSError:
        # Covers both mkdir and open() (external review, glm low: mkdir
        # previously sat outside this guard, so a read-only project root
        # raised past the module's own "never an exception" contract).
        return None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        with contextlib.suppress(OSError):
            path.unlink()
        return None
    return True


def mint(
    project_root: str | os.PathLike[str],
    *,
    session_id: str,
    turn_id: str,
    cwd: str,
    armed: bool,
    skill_id: str | None = None,
    args: dict | None = None,
    ttl_seconds: float = _DEFAULT_TTL_SECONDS,
    now: float | None = None,
) -> ActivationRecord | None:
    """Exclusive-create-only mint. Returns the minted record on success, or
    ``None`` if a record already exists for this ``session_id`` (a second
    ``UserPromptSubmit`` never overwrites the first) or on any I/O failure —
    the caller distinguishes neither case.

    ``armed=False`` mints an explicit unarmed marker (no grammar match) —
    still one-shot, so a later prompt cannot retroactively arm a session.

    **Early exists() short-circuit (doubt-review, medium):** fires on EVERY
    ``UserPromptSubmit``, not just the first, but only the first can ever
    win the create below — without this, every later turn paid a
    ``normalize_cwd()`` subprocess + record build just to lose it. Race-safe:
    a stale check falls through to the exclusive-create attempt itself."""
    if not session_id or not session_id.strip():
        return None
    path = _record_path(project_root, session_id)
    ts = time.time() if now is None else now
    if _exists_fail_open(path):
        return None
    _purge_expired_records(path.parent, now=ts)
    record = ActivationRecord(
        schema_version=_SCHEMA_VERSION,
        session_id=session_id,
        turn_id=turn_id,
        cwd=normalize_cwd(cwd),
        generation=secrets.token_hex(8),
        armed=armed,
        skill_id=skill_id if armed else None,
        args=((args if args is not None else {}) if armed else None),
        minted_at=ts,
        expiry=ts + ttl_seconds,
    )
    created = _exclusive_create(path, json.dumps(asdict(record)) + "\n")
    return record if created else None


def read(
    project_root: str | os.PathLike[str],
    session_id: str,
    *,
    cwd: str,
    now: float | None = None,
) -> ActivationRecord | None:
    """Return the session's activation record, or ``None`` if absent,
    unreadable/corrupt, schema-mismatched, cwd-mismatched, or expired — all
    fail-open, never raised. ``session_id`` is unvalidated here, unlike
    ``mint()`` — a bad value is just another "no record found" miss."""
    path = _record_path(project_root, session_id)
    try:
        raw = durable_read_text(path)
    except (OSError, ValueError):
        # ValueError covers UnicodeDecodeError: durable_read_text decodes
        # strict UTF-8, and a byte-corrupted record file is exactly the kind
        # of corruption this function's fail-open contract must absorb.
        return None
    try:
        payload = json.loads(raw)
        record = ActivationRecord(**payload)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not _has_valid_field_types(record):
        return None
    if record.schema_version != _SCHEMA_VERSION:
        return None
    if record.cwd != normalize_cwd(cwd):
        return None
    ts = time.time() if now is None else now
    if ts >= record.expiry:
        return None
    return record


def consume(
    project_root: str | os.PathLike[str],
    session_id: str,
    *,
    cwd: str,
    now: float | None = None,
) -> ActivationRecord | None:
    """One-time claim of the session's activation record via exclusive
    create of a ``.consumed`` sidecar. Returns the record on the FIRST
    successful consume; ``None`` otherwise — absent/corrupt/cwd-mismatched/
    expired (fail-open, same as ``read()``), or already consumed (exclusive,
    not idempotent — decided once, permanently).

    **Early exists() short-circuit (doubt-review, medium):** fires on every
    ``PreToolUse`` call after the first, but only the first can ever win the
    create below — without this, ``read()``'s ``normalize_cwd()`` subprocess
    ran again on every later call just to re-derive "already settled"."""
    consumed_path = _consumed_path(project_root, session_id)
    if _exists_fail_open(consumed_path):
        return None
    record = read(project_root, session_id, cwd=cwd, now=now)
    if record is None:
        return None
    ts = time.time() if now is None else now
    claimed = _exclusive_create(
        consumed_path,
        json.dumps({"consumed_at": ts, "generation": record.generation}) + "\n",
    )
    return record if claimed else None
