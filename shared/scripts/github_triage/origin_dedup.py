"""Dedup keys the default branch's tracked triage log already holds.

WHY (measured 2026-11-12, leadwright): ``triage.append_triage_item_idempotent`` decides
"already filed?" over THIS tree's tracked log + gitignored outbox. A checkout that stands
behind ``origin/<default>`` (normal whenever work lands by pull request from iterate
worktrees) lacks cards origin already carries, so a session-start sync filed four
duplicates of four open dependency pull requests.

This module is the "consult the default branch too" remedy: it reads origin's tracked
``.shipwright/triage.jsonl`` with ``git show`` (no checkout, working tree untouched) after a
bounded fail-soft ``git fetch``, and returns the dedup keys of items that would suppress a
re-import under the SAME rule the local scan applies (``match_commit=False``,
``window_seconds=None``): a durable operator decision, or an open / parked item.

ORIGIN ONLY FILLS GAPS: a key the local view already knows (any status) is left to the local
scan, which holds decisions origin has not seen yet (a machine close in the outbox, a dismiss
not merged). Origin's older copy must not outvote them, or a regressed finding stays hidden.

FAIL-SOFT, never fail-closed: no remote, no network, failed fetch, no such ref, unparsable
log -> an empty set and the local scan alone decides (today's behaviour). A missed sync is
worse than a duplicate card, so an unreachable or stale origin must never suppress filing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from shared_lib_loader import load_shared_lib
from triage import STATUSES, read_all_items

__all__ = ["origin_known_dedup_keys", "suppressing_keys_from_text"]

_TRIAGE_PATH = ".shipwright/triage.jsonl"
_GIT_TIMEOUT_SECONDS = 8


def _git(project_root: Path | str, *args: str) -> subprocess.CompletedProcess | None:
    # Never prompt: a credential dialog would hang a session-start sync past the timeout.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    try:
        return subprocess.run(
            ["git", "-c", "credential.interactive=false", *args], cwd=str(project_root), capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=_GIT_TIMEOUT_SECONDS, env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def suppressing_keys_from_text(text: str, *, source: str) -> set[str]:
    """Dedup keys of ``source`` items in a tracked-log ``text`` that suppress a re-import.

    Folds ``status`` events onto their ``append`` (later ``ts`` wins, file order breaks
    ties) - the same last-status-wins contract as ``triage.read_all_items``; ``amend``
    events change no field the suppression rule reads, so they are ignored.
    """
    defer = load_shared_lib("triage_defer")

    items: dict[str, dict] = {}
    statuses: list[tuple[str, int, dict]] = []
    for index, line in enumerate(text.splitlines()):
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            continue
        if record.get("event") == "append":
            items[record["id"]] = {
                "source": record.get("source"), "dedupKey": record.get("dedupKey"),
                "status": record["status"] if record.get("status") in STATUSES else "triage", "statusBy": None, "statusReason": None,
            }
        elif record.get("event") == "status" and record.get("newStatus") in STATUSES:
            ts = record.get("ts")
            statuses.append((ts if isinstance(ts, str) else "", index, record))
    for _ts, _index, record in sorted(statuses, key=lambda t: (t[0], t[1])):
        item = items.get(record["id"])
        if item is not None:
            item.update(status=record["newStatus"], statusBy=record.get("by"), statusReason=record.get("reason"))
    return {
        item["dedupKey"] for item in items.values()
        if item["source"] == source and isinstance(item["dedupKey"], str) and item["dedupKey"]
        and (defer.is_durable_decision(item) or defer.is_auto_resolvable(item["status"]))
    }


def origin_known_dedup_keys(project_root: Path | str, default_branch: str, *, source: str) -> set[str]:
    """Suppressing dedup keys held by ``origin/<default_branch>``'s tracked log; ``set()`` on any failure."""
    fetched = _git(project_root, "fetch", "--quiet", "origin", default_branch)
    if fetched is None or fetched.returncode != 0:
        sys.stderr.write("[github-triage] origin fetch failed; deduping against the local log only\n")
        return set()
    shown = _git(project_root, "show", f"origin/{default_branch}:{_TRIAGE_PATH}")
    if shown is None or shown.returncode != 0:
        return set()
    try:
        local = {i.get("dedupKey") for i in read_all_items(project_root) if i.get("source") == source}
        return suppressing_keys_from_text(shown.stdout, source=source) - local
    except Exception as exc:  # noqa: BLE001 - fail-soft: the local scan still decides
        sys.stderr.write(f"[github-triage] origin triage log unreadable: {type(exc).__name__}: {exc}\n")
        return set()
