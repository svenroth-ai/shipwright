#!/usr/bin/env python3
"""PostToolUse hook: nudge + write marker when an edit crosses the size limit.

Per Campaign A.foundation (bloat cleanup): per-filetype limits (300 source/
tests, 400 runtime-prompt — SKILL.md / CLAUDE.md / agents / prompts via
``bloat_baseline.classify_md``; docs skipped). On every crossing / anti-ratchet
event it writes a per-session marker
``<cwd>/.shipwright/locks/bloat_pending.<session_id>.json``; the Stop hook
``bloat_gate_on_stop.py`` reads it (TTL + path-normalise) and blocks on
anti-ratchet entries or new crossings outside the baseline. PostToolUse stays
advisory (always exits 0); only the Stop-Gate blocks.

Crossing detection is stateless: ``Edit`` without ``replace_all`` uses the line
delta; otherwise ``before`` is the line count at ``git HEAD`` (unknown -> nudge).
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import bloat_baseline as _bb  # noqa: E402

DEFAULT_MAX_LINES = _bb.LIMIT_SOURCE  # 300; runtime-prompts override to 400.


def _read_payload() -> dict:
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _md_classification(file_path: str) -> str | None:
    """Thin wrapper around :func:`bloat_baseline.classify_md`."""
    return _bb.classify_md(file_path)


def _limit_for(file_path: str, cwd: Path) -> int | None:
    """Limit applicable to ``file_path``; honours the source-limit override.

    Runtime-prompt limit (400) is fixed by the campaign and is NOT
    user-overridable. The legacy ``shipwright_build_config.json::
    enforcement.max_file_lines`` override applies to source files only.
    """
    classification = _md_classification(file_path)
    if classification == "runtime-prompt":
        return _bb.LIMIT_RUNTIME_PROMPT
    if classification == "doc":
        return None
    base = _bb.limit_for(file_path)
    if base is None:
        return None
    config = cwd / "shipwright_build_config.json"
    if not config.is_file():
        return base
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
        return int(data.get("enforcement", {}).get("max_file_lines", base))
    except (json.JSONDecodeError, OSError, AttributeError, TypeError, ValueError):
        return base


def _should_skip(file_path: str) -> bool:
    return _bb.should_skip(file_path)


def _file_newlines(path: Path) -> int:
    try:
        with path.open("rb") as fh:
            return fh.read().count(b"\n")
    except OSError:
        return 0


def _git_head_newlines(path: Path) -> int | None:
    try:
        top = subprocess.run(
            ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if top.returncode != 0:
            return None
        repo_root = Path(top.stdout.strip())
        try:
            rel = path.resolve().relative_to(repo_root.resolve())
        except ValueError:
            return None
        blob = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"HEAD:{rel.as_posix()}"],
            capture_output=True, timeout=5,
        )
        if blob.returncode != 0:
            return 0
        return blob.stdout.count(b"\n")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _before_newlines(tool_name: str, tool_input: dict, now: int, path: Path) -> int | None:
    if tool_name == "Edit" and not tool_input.get("replace_all"):
        old = tool_input.get("old_string")
        new = tool_input.get("new_string")
        if isinstance(old, str) and isinstance(new, str):
            return now - (new.count("\n") - old.count("\n"))
    return _git_head_newlines(path)


def _emit_nudge(file_path: str, now: int, limit: int) -> None:
    message = (
        f"NOTE - {file_path} just crossed the {limit}-line size guideline "
        f"(now {now} lines). Large source files are harder for AI agents to "
        f"edit reliably -- more context consumed, weaker edit localisation. "
        f"Mention this to the user and offer to split the file into smaller "
        f"modules. This is a non-blocking suggestion -- do not treat it as a "
        f"gate and do not block on it."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        }
    }))


# ----------------------------------------------------------------------
# Per-session marker writer
# ----------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _session_id(payload: object = None) -> str:
    """Marker key from the stdin payload ``session_id`` (env var is unset in this
    process), then ``SHIPWRIGHT_SESSION_ID``, then ``"unknown"`` — env-only keying
    pooled sessions into one bucket and blocked the wrong Stop (fixed 2026-05-29)."""
    if isinstance(payload, dict):
        sid = payload.get("session_id")
        if isinstance(sid, str) and sid.strip():
            return sid.strip()
    return (os.environ.get("SHIPWRIGHT_SESSION_ID") or "").strip() or "unknown"


def _marker_path(cwd: Path, sid: str) -> Path:
    return cwd / ".shipwright" / "locks" / f"bloat_pending.{sid}.json"


def _load_existing_marker(marker: Path) -> dict:
    if not marker.is_file():
        return {"version": 1, "entries": []}
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "entries": []}
    if not isinstance(data, dict):
        return {"version": 1, "entries": []}
    entries = data.get("entries")
    if not isinstance(entries, list):
        data["entries"] = []
    return data


def _atomic_write_marker(marker: Path, doc: dict) -> None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(doc, indent=2, sort_keys=False) + "\n"
    fd, tmp = tempfile.mkstemp(
        prefix=f".{marker.name}.tmp.", suffix=f".{uuid.uuid4().hex[:8]}",
        dir=str(marker.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
        os.replace(tmp, marker)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _baseline_paths(cwd: Path) -> set[str]:
    doc = _bb.load(cwd)
    if not doc:
        return set()
    return {e["path"] for e in doc.get("entries", []) if isinstance(e, dict)}


def _classification_label(file_path: str) -> str:
    md = _md_classification(file_path)
    return md if md == "runtime-prompt" else "source"


def _rel_path(cwd: Path, abs_path: Path) -> str:
    try:
        return _bb.normalize_path(str(abs_path.resolve().relative_to(cwd.resolve())))
    except ValueError:
        return _bb.normalize_path(str(abs_path))


def _write_marker_entry(
    cwd: Path, file_path: str, now: int, limit: int, before: int | None,
    payload: dict,
) -> None:
    """Upsert one entry into the per-session marker file (read-modify-write)."""
    sid = _session_id(payload)
    marker = _marker_path(cwd, sid)
    norm_path = _rel_path(cwd, Path(file_path))
    in_allowlist = norm_path in _baseline_paths(cwd)
    delta = "anti-ratchet" if in_allowlist else "crossing"
    entry = {
        "path": norm_path,
        "now": now,
        "limit": limit,
        "classification": _classification_label(file_path),
        "was_in_allowlist": in_allowlist,
        "delta": delta,
        "ts": _now_iso(),
    }
    doc = _load_existing_marker(marker)
    entries = [e for e in doc.get("entries", []) if e.get("path") != norm_path]
    entries.append(entry)
    doc["entries"] = entries
    _atomic_write_marker(marker, doc)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main() -> int:
    payload = _read_payload()
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return 0
    path = Path(file_path)
    if not path.is_file():
        return 0
    if _should_skip(file_path):
        return 0
    cwd = Path.cwd()
    # Only govern files within THIS project: a sibling repo (its own bloat
    # baseline) must not leak into this project's marker (advisory -> skip).
    try:
        path.resolve().relative_to(cwd.resolve())
    except ValueError:
        return 0
    limit = _limit_for(file_path, cwd)
    if limit is None:
        return 0
    now = _file_newlines(path)
    if now <= limit:
        return 0
    before = _before_newlines(
        str(payload.get("tool_name") or ""), tool_input, now, path,
    )
    # Determine whether this edit "newly" crossed the limit or grew an
    # already-oversize file. The marker is written either way — the
    # Stop-Gate decides what to do with it (anti-ratchet always blocks).
    is_crossing = before is None or before <= limit
    try:
        _write_marker_entry(cwd, file_path, now, limit, before, payload)
    except OSError:
        # Marker write must never break the tool flow.
        pass
    if is_crossing:
        _emit_nudge(file_path, now, limit)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 -- advisory hook: never break the tool flow
        sys.exit(0)
