#!/usr/bin/env python3
"""Stop hook: block when bloat markers indicate anti-ratchet or new crossing.

Reads the current session's marker (.shipwright/locks/bloat_pending.<sid>.json),
re-measures each entry's file, consults shipwright_bloat_baseline.json, and
emits top-level ``{"decision": "block", "reason": "..."}`` for anti-ratchet
entries or crossings outside the baseline. Stop schema (Claude Code current,
refreshed 2026-05-25) permits NO ``hookSpecificOutput`` wrapper — pass-path
emits empty stdout, block-path emits top-level decision/reason only.
Diagnostics route to stderr.

Iron-Law / Red-Flags / Rationalization-Prevention block-body adapted from
``obra/superpowers`` verification-before-completion (MIT, © Jesse Vincent).
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import bloat_baseline as _bb  # noqa: E402
from lib.repo_root import main_repo_root_or  # noqa: E402


def _session_id(payload: object = None) -> str:
    """Per-session marker key. Prefer the hook stdin payload's ``session_id``
    (the canonical id, same across PostToolUse + Stop of one session); fall back
    to the ``SHIPWRIGHT_SESSION_ID`` env var, then ``"unknown"``. The env var is
    NOT set in this Stop process, so env-only keying pooled every session into a
    shared ``bloat_pending.unknown.json`` — one session's oversize file then
    blocked another's Stop (fixed 2026-05-29)."""
    if isinstance(payload, dict):
        sid = payload.get("session_id")
        if isinstance(sid, str) and sid.strip():
            return sid.strip()
    sid = (os.environ.get("SHIPWRIGHT_SESSION_ID") or "").strip()
    return sid or "unknown"


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


def _marker_path(cwd: Path, sid: str) -> Path:
    return cwd / ".shipwright" / "locks" / f"bloat_pending.{sid}.json"


def _load_marker(marker: Path) -> list[dict]:
    """Read the marker entry list; ``[]`` on any error (fail-open)."""
    if not marker.is_file():
        return []
    try:
        doc = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"bloat_gate: marker unreadable ({exc!r}) — fail-open", file=sys.stderr)
        return []
    if not isinstance(doc, dict):
        return []
    entries = doc.get("entries")
    return entries if isinstance(entries, list) else []


def _parse_ts(ts: object) -> datetime.datetime | None:
    if not isinstance(ts, str):
        return None
    try:
        s = ts.rstrip("Z")
        if s.endswith("+00:00"):
            return datetime.datetime.fromisoformat(s)
        return datetime.datetime.fromisoformat(s).replace(
            tzinfo=datetime.timezone.utc,
        )
    except (ValueError, TypeError):
        return None


def _within_ttl(entry: dict, now: datetime.datetime) -> bool:
    ts = _parse_ts(entry.get("ts"))
    if ts is None:
        return False
    return (now - ts).total_seconds() <= _bb.MARKER_TTL_SECONDS


def _file_newlines(path: Path) -> int:
    try:
        with path.open("rb") as fh:
            return fh.read().count(b"\n")
    except OSError:
        return -1  # missing or unreadable — caller drops the entry


def _re_measure_oversize(cwd: Path, entry: dict) -> int | None:
    """Return current file size if still over limit; ``None`` if cleared."""
    rel = _bb.normalize_path(str(entry.get("path", "")))
    if not rel:
        return None
    p = cwd / rel
    if not p.is_file():
        return None
    n = _file_newlines(p)
    limit = entry.get("limit")
    if not isinstance(limit, int):
        return None
    if n <= limit or n < 0:
        return None
    return n


def _baseline_map(cwd: Path) -> dict[str, object] | None:
    """``{normalized_path: current}`` for baseline entries, or ``None`` if the
    baseline is missing/malformed.

    ``None`` triggers AC-7 pass-silently behavior in the caller. The ``current``
    value is the grandfathered line ceiling: an anti-ratchet entry only blocks
    when the live size grew PAST it (canonical definition — constitution +
    ``anti_ratchet.py``). ``_bb.load`` normalises entry paths, so keys line up
    with the marker's ``_bb.normalize_path`` form.
    """
    doc = _bb.load(cwd)
    if doc is None:
        return None
    return {e["path"]: e.get("current")
            for e in doc.get("entries", []) if isinstance(e, dict) and "path" in e}


# Iron-Law block message — adapted from obra/superpowers (MIT,
# © Jesse Vincent). The "spirit over letter" rule is preserved.

_BLOCK_HEADER = """\
================================================================
  SHIPWRIGHT BLOAT GATE — Stop blocked
================================================================

The IRON LAW

    NO COMPLETION WHILE FILES ARE GROWING UNCHECKED

If a file just crossed its size limit (300 LOC source, 400 LOC
runtime-prompt) or an already-oversize file got LARGER, that is
not a completion candidate — that is technical debt being
ratcheted in. Split the file, or document the exception via ADR
and update shipwright_bloat_baseline.json. Do not commit through.

Offenders (this session):"""

_BLOCK_FOOTER = """\

Red Flags — STOP
  - "Just one more line"              — RATCHET
  - "I will split it later"           — there is no later
  - "It is mostly comments"           — count the lines
  - "The limit is arbitrary"          — the limit is policy
  - "Splitting now would be churn"    — churn-deferral IS the trap

Rationalization Prevention
  | Excuse                          | Reality                          |
  | ------------------------------- | -------------------------------- |
  | "It is just a few lines over"   | The line is the line             |
  | "I will refactor in the next PR"| Next PR has its own scope        |
  | "The test is already big"       | Test files count too (campaign)  |
  | "ADR feels heavy"               | Heavy is the point of an ADR     |

How to clear this block
  1. Split the offending file into smaller modules, OR
  2. Add an ADR to .shipwright/planning/adr/ that promotes the file
     to state=exception and update shipwright_bloat_baseline.json.

Attribution: Iron-Law / Red-Flags / Rationalization-Prevention
language adapted from the Superpowers project's
verification-before-completion skill (MIT, © Jesse Vincent —
https://github.com/obra/superpowers). Adapted for the bloat
domain. Spirit over letter.
================================================================"""


def _build_block_reason(offenders: list[dict]) -> str:
    """Compose the Stop-block ``reason`` body."""
    offender_lines = [
        f"  - {o.get('path','?')}  "
        f"({o.get('now','?')} lines, limit {o.get('limit','?')}, "
        f"{o.get('delta','?')})"
        for o in offenders
    ]
    lines = [_BLOCK_HEADER, *offender_lines, _BLOCK_FOOTER]
    return "\n".join(lines)


def _emit_block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}))


def _emit_pass() -> None:
    # Empty stdout is the only schema-valid pass shape for Stop —
    # any JSON object on stdout (even just hookSpecificOutput) trips
    # Claude Code's validator with "Invalid input".
    return


def _worktree_root(main_root: Path, marker_path: str) -> Path | None:
    """Worktree root owning ``marker_path``'s ceiling (trg-28e83840), or ``None``
    for a main-tree path (reconstructed from the ``.worktrees/<slug>/`` prefix)."""
    norm = _bb.normalize_path(marker_path)
    stripped = _bb.strip_worktree_prefix(norm)
    if stripped == norm:
        return None
    prefix = norm[: len(norm) - len(stripped)]  # ".worktrees/<slug>/"
    return main_root / prefix.rstrip("/")


def main() -> int:
    # Canonical MAIN repo root (fail-soft), never Path.cwd() — must match the
    # writer (check_file_size) so marker/baseline/re-measure key off ONE root.
    # A Stop firing with cwd != repo-root otherwise reads the wrong location.
    root = main_repo_root_or(Path.cwd())
    sid = _session_id(_read_payload())
    entries = _load_marker(_marker_path(root, sid))
    if not entries:
        _emit_pass()
        return 0
    now = datetime.datetime.now(datetime.timezone.utc)
    main_baseline = _baseline_map(root)
    if main_baseline is None:
        # AC-7: no/malformed baseline → pass silently (fresh / pre-adopt / corrupted).
        _emit_pass()
        return 0
    # trg-28e83840: resolve each entry's ceiling from the tree it's MEASURED in — a
    # worktree iterate's ADR baseline bump lives in the worktree baseline, not main.
    baseline_by_root: dict[Path, dict[str, object]] = {root: main_baseline}

    def _baseline_for(marker_path: str) -> dict[str, object]:
        wt = _worktree_root(root, marker_path)
        if wt is None:
            return main_baseline
        if wt not in baseline_by_root:
            # worktree baseline if present, else MAIN (never empty → false crossing).
            baseline_by_root[wt] = _baseline_map(wt) or main_baseline
        return baseline_by_root[wt]

    offenders: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if not _within_ttl(entry, now):
            continue
        current = _re_measure_oversize(root, entry)
        if current is None:
            continue
        path = _bb.normalize_path(str(entry.get("path", "")))
        # trg-305e2aab: a worktree-iterate marker stores `.worktrees/<slug>/...`
        # (relative to the MAIN root); resolve it to the repo-relative baseline
        # key so an already-baselined file finds its ceiling / isn't treated as a
        # new crossing. `path` itself stays prefixed (re-measured above as-is).
        baseline_key = _bb.strip_worktree_prefix(path)
        baseline = _baseline_for(path)  # worktree baseline for a worktree-path entry
        in_baseline = baseline_key in baseline
        delta = entry.get("delta")
        # Anti-ratchet blocks only when the file grew PAST its baseline ceiling.
        # A grandfathered file trimmed back to <= `current` (even if still over
        # the raw 300 limit) is NOT a ratchet — clearing it here fixes the
        # transient-over-then-trimmed false-positive. New crossing blocks unless
        # the path is already grandfathered in the baseline.
        if delta == "anti-ratchet":
            ceiling = baseline.get(baseline_key)
            if isinstance(ceiling, int) and current <= ceiling:
                continue
            offenders.append({**entry, "path": path, "now": current})
        elif delta == "crossing" and not in_baseline:
            offenders.append({**entry, "path": path, "now": current})
    if not offenders:
        _emit_pass()
        return 0
    _emit_block(_build_block_reason(offenders))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        # Fail-open: never brick the agent on an unexpected error.
        print(f"bloat_gate: unexpected error ({exc!r}) — fail-open", file=sys.stderr)
        _emit_pass()
        sys.exit(0)
