"""routing — authoritative-vs-heuristic contract (defined in G1, wired in G4).

A target with a real, healthy ``.shipwright/`` event log / RTM is an
**authoritative** source (the grade could be read from Shipwright's own
records). Everything else is a **heuristic** synthetic projection from git
history, stamped as such.

The contract — and its behaviour for the partial / stale / malformed / mixed
cases — is defined and tested NOW (GPT #5/#17). G1 always *grades* via the
heuristic projector (``effective_mode == "heuristic"``); the ``detected_mode``
records whether an authoritative source is present so the report can honestly
say "authoritative source available — ingestion lands in G4" without claiming a
grade it did not compute.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Recognised states of a target's `.shipwright/` directory.
STATE_ABSENT = "absent"
STATE_VALID = "valid"
STATE_PARTIAL = "partial"
STATE_STALE = "stale"
STATE_MALFORMED = "malformed"
STATE_MIXED = "mixed"

_MODE_AUTHORITATIVE = "authoritative"
_MODE_HEURISTIC = "heuristic"


@dataclass(frozen=True)
class RoutingDecision:
    """The routing verdict for a target."""

    detected_mode: str    # what the target *could* support
    effective_mode: str   # what the grader actually used (heuristic in G1)
    state: str            # one of the STATE_* constants
    reason: str

    @property
    def is_authoritative_source(self) -> bool:
        return self.detected_mode == _MODE_AUTHORITATIVE


def _read(path: Path, limit: int = 65536) -> str:
    """Bounded read of the FILE HEAD (first ``limit`` bytes)."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def _read_tail(path: Path, limit: int = 65536) -> str:
    """Bounded read of the FILE TAIL (last ``limit`` bytes).

    The event log is append-only, so the newest events live at the end. A 253 KB
    log read head-first would show only the OLDEST events — exactly the ones that
    carry legacy commit SHAs — which mis-fires the staleness check. The tail read
    stays bounded (hostile-repo safe) while seeing the current records; a leading
    partial line (from seeking mid-line) simply fails to parse and is skipped.
    """
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > limit:
                fh.seek(size - limit)
            raw = fh.read()
        return raw.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _sha_match(a: str, b: str) -> bool:
    """True when ``a`` and ``b`` share a ≥7-char SHA prefix (either abbreviated)."""
    a, b = a.lower(), b.lower()
    n = min(len(a), len(b))
    return n >= 7 and a[:n] == b[:n]


def _newest_work_commit(events_text: str) -> tuple[bool, str]:
    """Return ``(saw_work_event, commit)`` for the NEWEST ``work_completed`` event.

    Keying staleness on the newest work event only (not the whole history) is
    what keeps the check false-positive-free: a repo that migrated from the old
    commit-attached model to the modern commit-less worktree model has ancient
    recorded commits that never match HEAD, but its newest event carries
    ``commit == ""`` — so we (correctly) decline to judge it stale.
    """
    for line in reversed(events_text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict) and obj.get("type") == "work_completed":
            commit = obj.get("commit")
            return True, commit.strip() if isinstance(commit, str) else ""
    return False, ""


def _staleness_reason(events_text: str, head_sha: str | None) -> str:
    """Return a stale reason when the log is provably behind HEAD, else ``""``.

    Conservative and *positive*: it fires only when the newest ``work_completed``
    event explicitly records a commit SHA that is NOT the working-tree HEAD. A
    commit-less (worktree-model) log — where staleness is unknowable — is never
    false-flagged.

    Note the dependence on the legacy ``commit`` field: modern Shipwright logs
    record ``commit == ""`` (F6.5 is skipped), so a *current* Shipwright repo never
    trips this check and grades authoritatively. Staleness is thus reachable only
    for the older commit-attached model — deliberately narrow, because a false
    "stale" only costs a (still-correct) heuristic grade, whereas a false
    "authoritative" would misrepresent stale records as current.
    """
    if not head_sha or not head_sha.strip():
        return ""
    saw_work, commit = _newest_work_commit(events_text)
    if not saw_work or not commit:
        return ""
    if _sha_match(head_sha, commit):
        return ""
    return (
        "event log is behind HEAD — the newest recorded work commit is not the "
        "working-tree HEAD (records may be stale)"
    )


def _within_root(path: Path, root: Path) -> bool:
    """True when ``path`` resolves INSIDE ``root`` (rejects symlink escapes).

    A hostile clone can ship ``.shipwright/events.jsonl`` (or the RTM) as a symlink
    to an out-of-tree file; without this guard routing would follow it and feed
    off-tree content into the grade. Mirrors ``repo_context.read_text``'s guard so
    every repo-derived read is escape-checked.
    """
    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError):  # pragma: no cover - defensive
        return False


def _events_path(root: Path) -> Path | None:
    """The target's event log, at its REAL location (within-root), or ``None``.

    The canonical Shipwright log is the **root-level** ``shipwright_events.jsonl``
    (the per-tree, version-controlled artifact the compliance collector reads —
    ``collectors.change_history._resolve_events_path``). A ``.shipwright/events.jsonl``
    is accepted as a fallback so routing and the authoritative ingestion agree on
    what "has an event log" means. A symlink escaping the root is ignored.
    """
    for cand in (root / "shipwright_events.jsonl", root / ".shipwright" / "events.jsonl"):
        if cand.is_file() and _within_root(cand, root):
            return cand
    return None


def _has_rtm(sw_dir: Path) -> bool:
    """True when the target carries a Requirements Traceability Matrix.

    The canonical artifact is ``.shipwright/compliance/traceability-matrix.md``
    (hyphenated — what ``rtm_generator`` writes); the legacy names are kept as
    fallbacks. These reference the GRADED TARGET repo's ``.shipwright/``, not this
    project's canonical compliance dir — the canon lint can't tell them apart. A
    symlink escaping the repo root is ignored (untrusted-clone guard).
    """
    root = sw_dir.parent
    candidates = [
        sw_dir / "compliance" / "traceability-matrix.md",  # artifact-path-canon: legacy
        sw_dir / "compliance" / "rtm.md",  # artifact-path-canon: legacy
        sw_dir / "compliance" / "traceability_matrix.md",  # artifact-path-canon: legacy
    ]
    return any(p.is_file() and _within_root(p, root) for p in candidates)


def _classify_shipwright(root: Path, head_sha: str | None = None) -> tuple[str, str]:
    """Return (state, reason) for a target's Shipwright records."""
    sw_dir = root / ".shipwright"
    if not sw_dir.is_dir():
        return STATE_ABSENT, "no .shipwright/ directory"

    events = _events_path(root)
    head_text = _read(events) if events else ""
    has_rtm = _has_rtm(sw_dir)
    has_events = bool(head_text.strip())

    if not has_events and not has_rtm:
        return STATE_PARTIAL, ".shipwright/ present but no event log or RTM"

    if has_events:
        # Malformed if the first non-empty line is not JSON-object-shaped.
        first = next((ln for ln in head_text.splitlines() if ln.strip()), "")
        stripped = first.strip()
        if stripped and not (stripped.startswith("{") and stripped.endswith("}")):
            return STATE_MALFORMED, "events.jsonl is not JSON-lines shaped"

    if has_events and not has_rtm:
        return STATE_MIXED, "event log present but no RTM"
    if has_rtm and not has_events:
        return STATE_MIXED, "RTM present but no event log"
    # Staleness reads the log TAIL (newest events) — see _read_tail.
    stale = _staleness_reason(_read_tail(events) if events else "", head_sha)
    if stale:
        return STATE_STALE, stale
    return STATE_VALID, "healthy .shipwright/ event log + RTM"


# States that would (in G4) support an authoritative read.
_AUTHORITATIVE_STATES = frozenset({STATE_VALID})


def decide_routing(root: Path, head_sha: str | None = None) -> RoutingDecision:
    """Decide authoritative-vs-heuristic routing for a target root.

    Only ``detected_mode`` reflects an authoritative-capable source; the caller
    (:func:`grade_context`) performs the ingestion and sets ``effective_mode``
    to ``authoritative`` when it succeeds. Any degraded state (partial / stale /
    malformed / mixed / absent) falls back to heuristic, labelled. ``head_sha``
    (the working-tree HEAD) enables the staleness check — omit it and a valid
    log is never flagged stale.
    """
    state, reason = _classify_shipwright(root, head_sha)
    detected = _MODE_AUTHORITATIVE if state in _AUTHORITATIVE_STATES else _MODE_HEURISTIC
    if detected == _MODE_AUTHORITATIVE:
        reason = "authoritative .shipwright/ event log + RTM detected"
    return RoutingDecision(
        detected_mode=detected,
        effective_mode=_MODE_HEURISTIC,
        state=state,
        reason=reason,
    )
