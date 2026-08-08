#!/usr/bin/env python3
"""Render and refresh ``.shipwright/agent_docs/decision_log_index.md``.

Same treatment as the ADR spec folder's ``INDEX.md`` (``lib/adr_index.py``,
ADR-116): a pure ``render_decision_log_index`` + a writing
``rebuild_decision_log_index``, so a byte-equality drift guard is possible.
Two producers refresh it — the direct-append path (``write_decision_log.py``,
used by plan/build/deploy) and the release-time fold
(``aggregate_decisions.py``) — because either one can be the last thing to
change ``decision_log.md`` before a commit lands.

Unlike the ADR index, there is no per-file title lookup: ``decision_log.md``
is ONE file and each entry's title sits on its own ``### ADR-NNN`` (or
shipwright-design's ``### DR-NNN``, a second, independently-numbered entry
class in the same file) heading line, so parsing is a single regex pass.

``current-status`` is derived from a ``(supersedes ADR-NNN)`` marker in a
later entry's title — never from the ``**Status**`` field, which exists on
only 16 of this repo's 328 entries (measured 2026-08-07) and so cannot carry
the signal for the other 95%. Only one such marker exists in this log today
(ADR-307 supersedes ADR-042); the parser handles however many more accrue.
"""

from __future__ import annotations

import re
from pathlib import Path

from .atomic_write import durable_atomic_write
from .file_lock import LockTimeout, file_lock

DECISION_LOG_PATH = ".shipwright/agent_docs/decision_log.md"
DECISION_LOG_FILENAME = "decision_log.md"
DECISION_LOG_INDEX_FILENAME = "decision_log_index.md"

#: Regen tool path, relative to the SHARED ROOT — see ``adr_index.REGEN_COMMAND``
#: for why ``{shared_root}`` stays unresolved in the rendered header.
REGEN_TOOL_RELPATH = "scripts/tools/rebuild_decision_log_index.py"
REGEN_COMMAND = f"uv run {{shared_root}}/{REGEN_TOOL_RELPATH} --project-root ."


def regen_command_resolved() -> str:
    """:data:`REGEN_COMMAND` with ``{shared_root}`` filled in from this file."""
    shared_root = Path(__file__).resolve().parents[2]
    return REGEN_COMMAND.replace("{shared_root}", shared_root.as_posix())


# ADR headings are write_decision_log.py's own; DR headings are shipwright-design's
# (`plugins/shipwright-design/.../review-loop.md` `### DR-{NNN}: {Title}` format) —
# both land in the SAME decision_log.md, so an index calling itself complete must
# read both. Unlike get_next_adr_number's unanchored, non-fence-aware `### ADR-`
# findall (used only for numbering, a narrower job), this is anchored + fence-aware
# and now also DR-aware — the two intentionally are not the same regex.
_ENTRY_RE = re.compile(r"^ {0,3}### (?P<kind>ADR|DR)-(?P<num>\d+):?\s*(?P<title>.*?)\s*$")
_FENCE_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})")
_SUPERSEDES_RE = re.compile(
    r"\(supersedes\s+(?P<targets>ADR-\d+(?:\s*(?:,|and)\s*ADR-\d+)*)[^)]*\)",
    re.IGNORECASE,
)
_SUPERSEDES_TARGET_RE = re.compile(r"ADR-(?P<num>\d+)", re.IGNORECASE)
_SLUG_STRIP_RE = re.compile(r"[^\w\- ]+", re.UNICODE)


def _slugify_heading(text: str) -> str:
    """Approximate GitHub's markdown heading-anchor algorithm.

    Best-effort: lowercase, drop everything but word chars/hyphens/spaces,
    spaces to hyphens. A wrong slug degrades the row to "doesn't jump to the
    exact heading" — the visible label is unaffected, so this never renders
    wrong data, only a possibly-imprecise link target.
    """
    s = text.strip().lower()
    s = _SLUG_STRIP_RE.sub("", s)
    return s.replace(" ", "-")


def _escape_link_text(text: str) -> str:
    """Keep a title's brackets from terminating the markdown link label."""
    return text.replace("\\", "\\\\").replace("[", r"\[").replace("]", r"\]")


def _entries(text: str) -> list[tuple[str, str, str]]:
    """``(kind, num, title)`` for every ``### {ADR|DR}-NNN[: Title]`` heading
    in ``text``, outside fenced code blocks, in file order.

    ``num`` keeps the source's own digit string (never reformatted to a fixed
    width) so a rendered link can never disagree with the heading it points at.
    """
    entries: list[tuple[str, str, str]] = []
    fence: str | None = None
    for line in text.splitlines():
        opened = _FENCE_RE.match(line)
        if fence is not None:
            run = opened.group("fence") if opened else ""
            if run and run[0] == fence[0] and len(run) >= len(fence):
                fence = None
            continue
        if opened:
            fence = opened.group("fence")
            continue
        match = _ENTRY_RE.match(line)
        if match:
            entries.append((match.group("kind"), match.group("num"), match.group("title")))
    return entries


def _supersession_map(entries: list[tuple[str, str, str]]) -> dict[tuple[str, int], str]:
    """``{(kind, superseded_num): superseding_ref}`` parsed from ``(supersedes
    ADR-NNN [and ADR-MMM...])`` parentheticals — the only link vocabulary this
    log uses today, and it only ever names ``ADR-`` targets. Keyed by
    ``(kind, int(num))``, not a bare number, so an ``ADR-042`` and a ``DR-042``
    (independent numbering sequences sharing the same digits) can never
    collide. The ``int()`` normalization means a hand-written unpadded
    reference (``ADR-42``) still matches the zero-padded heading it targets
    (``ADR-042``) — a bare digit-string key would silently miss that, the most
    likely real-world typo since the marker is authored by hand, not generated.

    A marker only counts when its target's own heading appears EARLIER in the
    file than the entry carrying the marker — the documented rule is "a marker
    in a LATER entry's title", not merely any entry with the phrase. Without
    this, a mis-numbered or out-of-order entry (``ADR-001: ... (supersedes
    ADR-002)`` written before ADR-002 exists) would mark the *later* ADR-002
    as superseded by the *earlier* ADR-001 — backwards. A target that is not
    among ``entries`` at all (e.g. one of the fenced historical duplicates) is
    accepted as-is, since its true position is unknown, not provably wrong.
    A duplicate ADR number in the log (a known historical artifact — see
    ``lib/adr_index.py``) keeps only its LAST position here; out of scope.
    """
    position = {("ADR", int(num)): i for i, (kind, num, _title) in enumerate(entries) if kind == "ADR"}
    obsoleted_by: dict[tuple[str, int], str] = {}
    for i, (kind, num, title) in enumerate(entries):
        marker = _SUPERSEDES_RE.search(title)
        if not marker:
            continue
        for target in _SUPERSEDES_TARGET_RE.finditer(marker.group("targets")):
            key = ("ADR", int(target.group("num")))
            target_pos = position.get(key)
            if target_pos is not None and target_pos >= i:
                continue
            obsoleted_by[key] = f"{kind}-{num}"
    return obsoleted_by


def render_decision_log_index(text: str) -> str:
    """Render the index for ``decision_log.md``'s ``text``. Pure — LF-only."""
    lines = [
        "# Decision Log — INDEX",
        "",
        "_Auto-generated — do not edit by hand. Each row's title comes from",
        "that decision's own `### ADR-NNN` (or design's `### DR-NNN`) heading",
        "in `decision_log.md`, so change the heading, not this file.",
        "`superseded by ADR-NNN` is derived from a `(supersedes ADR-NNN)`",
        "marker in a LATER entry's title, never from the `**Status**` field",
        "(present on a minority of entries)._",
        "",
        f"_Regenerate:_ `{REGEN_COMMAND}`",
        "",
    ]
    entries = _entries(text)
    if not entries:
        lines += [
            "_No decisions yet. Add one via `write_decision_log.py` and regenerate._",
            "",
        ]
        return "\n".join(lines)
    obsoleted_by = _supersession_map(entries)
    for kind, num, title in entries:
        ref = f"{kind}-{num}"
        heading = f"{ref}: {title}" if title else ref
        href = f"{DECISION_LOG_FILENAME}#{_slugify_heading(heading)}"
        label = f"{ref} — {_escape_link_text(title)}" if title else ref
        row = f"- [{label}]({href})"
        if kind == "ADR" and ("ADR", int(num)) in obsoleted_by:
            row += f" — **superseded by {obsoleted_by[('ADR', int(num))]}**"
        lines.append(row)
    lines.append("")
    return "\n".join(lines)


def rebuild_decision_log_index(project_root: Path | str) -> Path | None:
    """Refresh the decision-log INDEX for ``project_root``. Returns the path
    written, or ``None`` when ``decision_log.md`` does not exist.

    A missing ``decision_log.md`` is a strict no-op — never minted for a repo
    that has not recorded a decision yet. Lock + :func:`durable_atomic_write`
    mirror ``lib.adr_index.rebuild_adr_index`` exactly: two producers
    (``write_decision_log.py``, ``aggregate_decisions.py``) can race, and the
    LF-exact write matters the same way on a CRLF Windows working tree.

    Raises :class:`LockTimeout` (a ``RuntimeError``, not an ``OSError``) if the
    index lock cannot be taken — callers treating a refresh as best-effort
    must catch both.
    """
    project_root = Path(project_root)
    log_path = project_root / DECISION_LOG_PATH
    if not log_path.is_file():
        return None
    index_path = log_path.parent / DECISION_LOG_INDEX_FILENAME
    lock_path = project_root / ".shipwright" / "locks" / "decision_log_index.lock"
    with file_lock(str(lock_path), timeout_seconds=10.0):
        durable_atomic_write(index_path, render_decision_log_index(
            log_path.read_text(encoding="utf-8")
        ))
    return index_path


def refresh_best_effort(project_root: Path | str) -> str | None:
    """Refresh the index, returning a warning message instead of raising.

    Mirrors ``lib.adr_index.refresh_best_effort``'s fail-soft contract: a
    stale index must never undo work the caller already committed to, but the
    failure must be loud, not silent.
    """
    try:
        rebuild_decision_log_index(project_root)
    except (OSError, LockTimeout, UnicodeDecodeError) as exc:
        return (
            f"refreshing .shipwright/agent_docs/{DECISION_LOG_INDEX_FILENAME} "
            f"failed: {exc}\n         The index is now stale and the drift "
            f"guard will fail. Regenerate it with:\n         "
            f"{regen_command_resolved()}"
        )
    return None
