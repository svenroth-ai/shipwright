"""synthetic_projection — the git history IS the event log.

Each commit becomes a synthetic :class:`WorkEvent`: author-date, author,
Conventional-Commit type, a PR/issue reference token (if any), and the two
derived provenance flags the projector maps onto ``GradeInputs``:

- ``is_traced``   — Conventional-Commit-typed **or** carrying a PR/issue
  reference. Feeds requirement-traceability *change classification* (tag-rate).
- ``has_provenance`` — carries a PR/issue reference token (a ``#N`` or a
  ``pull``/``issues`` URL). "Strict" here means a bare commit SHA does **not**
  count — a reference to a tracked PR/issue does. It is a *reference*, not a
  gh-API-*verified* link (that verification is a G2 enrichment); feeds
  change-traceability.

``files_changed`` is left ``None`` in G1 (a per-commit numstat pass is wasteful
here and unbounded on hostile bodies); it is populated as a G2 enrichment.

The parser (:func:`parse_git_log`) is a **pure** function over ``git log`` text
so it is unit-tested without a repo; :func:`collect_events` is the thin
hardened-``git`` collector.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from git_exec import run_git

# ASCII separators keep the format robust against newlines in commit bodies.
_US = "\x1f"  # unit separator (between fields)
_RS = "\x1e"  # record separator (between commits)
_LOG_FORMAT = f"%H{_US}%aI{_US}%an{_US}%s{_US}%b{_RS}"

_CONVENTIONAL_TYPES = frozenset({
    "feat", "fix", "chore", "docs", "style", "refactor",
    "perf", "test", "build", "ci", "revert",
})
_CONV_RE = re.compile(r"^([a-zA-Z]+)(?:\([^)]*\))?!?:\s")
_PR_URL_RE = re.compile(r"/(pull|merge_requests)/(\d+)")
_ISSUE_URL_RE = re.compile(r"/issues/(\d+)")
_MERGE_PR_RE = re.compile(r"\bpull request #(\d+)", re.IGNORECASE)
_HASH_REF_RE = re.compile(r"(?<![\w/])#(\d+)\b")


@dataclass(frozen=True)
class WorkEvent:
    """One commit projected as a synthetic work event."""

    sha: str
    author_date: str
    author: str
    subject: str
    conventional_type: str | None
    ref: str | None        # e.g. "#123" or "pull/123"
    ref_kind: str | None   # "pr" | "issue" | "ref"
    files_changed: int | None  # None in G1 (per-commit numstat is a G2 enrichment)
    is_traced: bool
    has_provenance: bool


def _conventional_type(subject: str) -> str | None:
    m = _CONV_RE.match(subject.strip())
    if not m:
        return None
    kind = m.group(1).lower()
    return kind if kind in _CONVENTIONAL_TYPES else None


def _find_ref(subject: str, body: str) -> tuple[str | None, str | None]:
    """Return (ref, kind) — the first PR/issue reference, or (None, None)."""
    text = f"{subject}\n{body}"
    m = _PR_URL_RE.search(text)
    if m:
        return f"pull/{m.group(2)}", "pr"
    m = _MERGE_PR_RE.search(text)
    if m:
        return f"#{m.group(1)}", "pr"
    m = _ISSUE_URL_RE.search(text)
    if m:
        return f"issues/{m.group(1)}", "issue"
    m = _HASH_REF_RE.search(text)
    if m:
        return f"#{m.group(1)}", "ref"
    return None, None


def _event_from(sha: str, date: str, author: str, subject: str, body: str) -> WorkEvent:
    conv = _conventional_type(subject)
    ref, kind = _find_ref(subject, body)
    is_traced = conv is not None or ref is not None
    has_provenance = ref is not None
    return WorkEvent(
        sha=sha, author_date=date, author=author, subject=subject,
        conventional_type=conv, ref=ref, ref_kind=kind, files_changed=None,
        is_traced=is_traced, has_provenance=has_provenance,
    )


def parse_git_log(raw: str) -> list[WorkEvent]:
    """Parse ``git log`` output in ``_LOG_FORMAT`` into events (pure)."""
    events: list[WorkEvent] = []
    for record in raw.split(_RS):
        record = record.strip("\n")
        if not record.strip():
            continue
        fields = record.split(_US)
        if len(fields) < 4 or not fields[0].strip():
            continue
        sha, date, author, subject = fields[0], fields[1], fields[2], fields[3]
        body = fields[4] if len(fields) > 4 else ""
        events.append(_event_from(sha.strip(), date.strip(), author, subject, body))
    return events


# Bound the log stdout so a hostile repo with multi-MB commit bodies cannot
# buffer GBs into memory (subject+body of the newest N commits fits comfortably).
_MAX_LOG_BYTES = 4_000_000


def collect_events(path: Path, *, max_commits: int) -> list[WorkEvent]:
    """Collect up to ``max_commits`` newest synthetic events (hardened git).

    Deterministic: ``git log`` yields newest-first; the cap truncates the tail,
    not a random sample. Output is byte-bounded (``_MAX_LOG_BYTES``); a truncated
    final record is dropped by :func:`parse_git_log`.
    """
    cap = str(int(max_commits))
    _, meta = run_git(
        ["log", "--no-merges", f"--max-count={cap}", f"--format={_LOG_FORMAT}"],
        path, max_bytes=_MAX_LOG_BYTES,
    )
    return parse_git_log(meta)
