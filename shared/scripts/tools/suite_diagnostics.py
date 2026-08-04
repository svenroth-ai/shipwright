"""Bounded, redacted, run-scoped evidence for failed F0 attempts."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.lib.atomic_write import durable_atomic_write  # noqa: E402
from scripts.lib.main_health_diagnosis import redact  # noqa: E402
from scripts.lib.repo_root import resolve_main_repo_root  # noqa: E402

DEFAULT_MAX_TAIL_BYTES = 64 * 1024


def _key(value: object, length: int) -> str:
    """Return a compact opaque key; display names live inside the JSON payload.

    F0 itself is frequently exercised from pytest projects already nested deeply
    below the Windows temp root. Human-readable path slugs consumed enough of
    MAX_PATH that the atomic writer could not create its temporary sibling. Fixed
    hash widths keep the producer path bounded independently of untrusted ids.
    """
    raw = str(value or "unknown")
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:length]


def _display(value: object, cap: int = 200) -> str:
    return " ".join(redact(str(value or "unknown")).split())[:cap]


def _io_path(path: Path) -> Path:
    """Use the Windows extended path only at the filesystem boundary."""
    resolved = path.resolve()
    if os.name != "nt":
        return resolved
    text = str(resolved)
    if text.startswith("\\\\?\\"):
        return resolved
    if text.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + text[2:])
    return Path("\\\\?\\" + text)


def _cap_utf8(text: str, cap: int) -> tuple[str, bool]:
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= cap:
        return text, False
    return raw[-max(1, cap):].decode("utf-8", errors="ignore"), True


def write_attempt_evidence(
    project_root: Path, *, run_id: str, unit_id: str, phase: str, rc: int,
    seconds: float, tail: str, truncated: bool, pytest_ran: bool,
    max_tail_bytes: int = DEFAULT_MAX_TAIL_BYTES,
) -> Path:
    """Publish under the stable main-repo run store and return its relative path."""
    safe_tail, capped = _cap_utf8(redact(tail), max(1, max_tail_bytes))
    durable_root = resolve_main_repo_root(project_root) or Path(project_root)
    attempt = uuid4().hex
    relative = (Path(".shipwright") / "runs" / f"f0-{_key(run_id, 12)}" /
                "f0-diagnostics" / _key(unit_id, 12) /
                f"{_key(phase, 8)}-{attempt}.json")
    payload = {
        "schema_version": 1,
        "untrusted": True,
        "run_id": _display(run_id),
        "unit_id": _display(unit_id),
        "phase": _display(phase),
        "rc": int(rc),
        "seconds": round(float(seconds), 3),
        "pytest_ran": bool(pytest_ran),
        "truncated": bool(truncated or capped),
        "tail": safe_tail,
    }
    durable_atomic_write(_io_path(durable_root / relative),
                         json.dumps(payload, indent=2, ensure_ascii=True) + "\n")
    return relative
