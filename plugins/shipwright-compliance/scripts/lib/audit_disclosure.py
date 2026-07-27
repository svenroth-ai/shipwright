"""When did the cross-check last run? — the durable record behind the answer.

The detective audit (``run_audit.py``, invoked only by ``/shipwright-compliance``)
is the check that reports where the evidence disagrees with reality. It is wired
to no trigger — no schedule, no workflow, no hook — and that is deliberate: a
check nobody asked for produces warnings nobody wants. The cost of that choice is
that in a project where nobody thinks of it for three months, divergence
accumulates while the evidence documents look unchanged and trustworthy the whole
time. So the documents disclose *when the check last happened*, turning
possibly-never-checked into visibly-not-checked-since.

This module owns the fact; :mod:`scripts.lib._audit_disclosure_render` renders it.

**Where it lives.** ``shipwright_compliance_config.json``, which is *tracked* —
the point of the exercise. The audit's own outputs (``audit-report.md`` /
``.json``) are gitignored transients, so a disclosure sourced from them would be
absent on a fresh clone and would make a tracked document say different things on
different machines. The config is already a mixed settings+state file (``status``,
``phases_covered``, ``last_full_generation``, ``seeded_by_adopt`` are all
machine-written) and every consumer reads it loosely, so additive keys are safe.
Writes are read-modify-write, atomic (temp + replace), and refuse to clobber a
config they cannot parse.

**Reaching a fresh clone requires a commit.** Recording makes the working tree
dirty; nothing here commits it. The iterate/finalize flow stages the config with
the rest of the compliance write-set, so a disclosure only travels once that
commit lands. A bare ``run_audit.py`` invocation leaves it uncommitted.

**Two records, because a partial run is not a full one.** ``last_audit`` is the
latest run of any scope; ``last_full_audit`` is the latest whole-project run.
Keeping only the former would let a Friday ``--only A`` erase the evidence of
Thursday's full audit and leave the documents reading "partial" indefinitely —
losing exactly the answer a reader wants ("when was the *whole* thing checked?").

**Absent is not the same as unreadable.** A damaged or hand-edited record must
never render as "never run": that asserts something the project cannot know. The
loader reports ``absent`` / ``valid`` / ``invalid`` and the renderer says which.
Values are validated before they reach markdown (a committed hostile ``scope``
must not inject layout into a compliance document).

Stdlib-only, so ``collect_all`` and ``run_audit`` can both import it without
pulling in the audit machinery.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, NamedTuple

CONFIG_FILE = "shipwright_compliance_config.json"
LAST_AUDIT_KEY = "last_audit"
LAST_FULL_AUDIT_KEY = "last_full_audit"
SCOPE_FULL = "full"

#: Loader outcomes. ``absent`` = no audit was ever recorded; ``invalid`` = a
#: record exists but cannot be trusted (the honest answer is "unknown", never
#: "never run"); ``valid`` = usable.
ABSENT = "absent"
VALID = "valid"
INVALID = "invalid"

_COUNTED_STATUSES = ("pass", "fail", "skip")
_VERDICTS = ("pass", "fail")
# Group letters / check ids only — anything else in a tracked, hand-editable
# file is refused rather than interpolated into a compliance document.
_SCOPE_ALLOWED = re.compile(r"[^A-Za-z0-9,_-]")
_SCOPE_MAX = 40


@dataclass(frozen=True)
class AuditRecord:
    """One completed audit run, validated and safe to render."""

    ran_at: str
    verdict: str
    scope: str
    checks: dict

    @property
    def is_full(self) -> bool:
        return self.scope == SCOPE_FULL


class AuditFreshness(NamedTuple):
    """What the project can honestly say about its last cross-check.

    ``latest`` is the most recent run of any scope; ``latest_full`` the most
    recent whole-project one. Both are ``None`` unless ``status`` is ``valid``.
    """

    status: str
    latest: AuditRecord | None = None
    latest_full: AuditRecord | None = None


def _sanitize_scope(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return _SCOPE_ALLOWED.sub("", value)[:_SCOPE_MAX]


def _valid_timestamp(value: object) -> str:
    """Return ``value`` when it is a parseable ISO-8601 instant, else ``""``."""
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return ""
    return value


def _clean_checks(value: object) -> dict:
    """Keep only non-negative integer counts.

    These land verbatim in a markdown document, and the config is tracked and
    hand-editable — a string count would inject layout into compliance evidence.
    """
    if not isinstance(value, dict):
        return {}
    clean: dict = {}
    for key in ("total", *_COUNTED_STATUSES):
        count = value.get(key)
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            clean[key] = count
    return clean


def _parse_record(block: object) -> AuditRecord | None:
    """Validate one stored block. ``None`` means "present but not trustworthy"."""
    if not isinstance(block, dict):
        return None
    ran_at = _valid_timestamp(block.get("ran_at"))
    verdict = block.get("verdict")
    if not ran_at or verdict not in _VERDICTS:
        return None
    # A record with no scope reads as full — the writer always sets it, and the
    # audit's own default scope is full, so absence means legacy/hand-edited.
    scope = _sanitize_scope(block.get("scope")) or SCOPE_FULL
    return AuditRecord(
        ran_at=ran_at,
        verdict=verdict,
        scope=scope,
        checks=_clean_checks(block.get("checks")),
    )


def _read_config(project_root: Path) -> tuple[str, dict]:
    """``(status, config)`` — ``status`` is ABSENT / VALID / INVALID."""
    path = Path(project_root) / CONFIG_FILE
    if not path.is_file():
        return ABSENT, {}
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return INVALID, {}
    if not isinstance(config, dict):
        return INVALID, {}
    return VALID, config


def load_audit_freshness(project_root: Path) -> AuditFreshness:
    """What this project can truthfully say about its last cross-check."""
    status, config = _read_config(project_root)
    if status != VALID:
        # An unreadable config is not evidence that no audit ever ran.
        return AuditFreshness(status)

    raw_latest = config.get(LAST_AUDIT_KEY)
    raw_full = config.get(LAST_FULL_AUDIT_KEY)
    if raw_latest is None and raw_full is None:
        return AuditFreshness(ABSENT)

    latest = _parse_record(raw_latest)
    if latest is None:
        return AuditFreshness(INVALID)

    latest_full = _parse_record(raw_full)
    if latest.is_full and (
        latest_full is None or latest_full.ran_at <= latest.ran_at
    ):
        latest_full = latest
    return AuditFreshness(VALID, latest, latest_full)


def read_last_audit(project_root: Path) -> dict | None:
    """The latest stored block as written, or ``None`` when unusable."""
    freshness = load_audit_freshness(project_root)
    if freshness.status != VALID:
        return None
    _, config = _read_config(project_root)
    block = config.get(LAST_AUDIT_KEY)
    return block if isinstance(block, dict) else None


def _atomic_write(path: Path, text: str) -> None:
    """Replace ``path`` in one step so a crash cannot truncate the config."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)  # never leave a stray half-config behind
        raise


def record_audit_run(
    project_root: Path,
    *,
    statuses: Iterable[str],
    any_fail: bool,
    scope: str = SCOPE_FULL,
    ran_at: str | None = None,
) -> dict:
    """Record that the audit ran, into tracked state.

    ``statuses`` is the audit's per-finding status stream (``pass`` / ``fail`` /
    ``skip``); ``scope`` is ``"full"`` or the comma-joined group letters of a
    ``--only`` run. A full run also refreshes ``last_full_audit``; a partial run
    leaves it alone, so it can never erase the answer to "when was the whole
    project last checked?".

    Only *completed* runs reach this — the CLI returns before recording when the
    audit aborts — so a stored record always means "this audit finished".

    Best-effort by contract: the caller is an audit whose exit code means "is the
    project consistent?", and bookkeeping must never change that answer. Returns
    ``{"recorded": True, "last_audit": {...}}`` or ``{"recorded": False,
    "reason": ...}``; a config that cannot be parsed is reported and left
    byte-for-byte alone rather than replaced.
    """
    project_root = Path(project_root)
    path = project_root / CONFIG_FILE

    status, config = _read_config(project_root)
    if status == INVALID:
        return {"recorded": False, "reason": "config_unreadable_or_not_an_object"}

    statuses = list(statuses)
    scope = _sanitize_scope(scope) or SCOPE_FULL
    block = {
        "ran_at": ran_at or datetime.now(timezone.utc).isoformat(),
        "verdict": "fail" if any_fail else "pass",
        "scope": scope,
        "checks": {
            "total": len(statuses),
            **{s: statuses.count(s) for s in _COUNTED_STATUSES},
        },
    }
    previous = config.get(LAST_AUDIT_KEY)
    config[LAST_AUDIT_KEY] = block
    if scope == SCOPE_FULL:
        config[LAST_FULL_AUDIT_KEY] = block
    elif _parse_record(config.get(LAST_FULL_AUDIT_KEY)) is None:
        # Upgrade path: a config written before ``last_full_audit`` existed holds
        # its full run only under ``last_audit``. Promote it before this partial
        # run overwrites that slot, or the first ``--only`` invocation after the
        # upgrade would silently downgrade the project to "never fully run".
        prior = _parse_record(previous)
        if prior is not None and prior.is_full:
            config[LAST_FULL_AUDIT_KEY] = previous

    try:
        _atomic_write(
            path, json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        )
    except OSError as exc:
        return {"recorded": False, "reason": f"write_error: {exc}"}
    return {"recorded": True, LAST_AUDIT_KEY: block}


__all__ = [
    "ABSENT",
    "CONFIG_FILE",
    "INVALID",
    "LAST_AUDIT_KEY",
    "LAST_FULL_AUDIT_KEY",
    "SCOPE_FULL",
    "VALID",
    "AuditFreshness",
    "AuditRecord",
    "load_audit_freshness",
    "read_last_audit",
    "record_audit_run",
]
