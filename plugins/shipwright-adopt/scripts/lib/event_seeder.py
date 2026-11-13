"""Seed shipwright_events.jsonl with the adopted event + optional backfill.

One `adopted` event is mandatory. Optional backfill: N `work_completed`
events derived from major_refactor_commits, tagged with
`source="adopted-backfill"` and `confidence="low"` so they don't
contaminate serious RTM metrics.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ends_without_newline(path: Path) -> bool:
    """True iff ``path`` exists, is non-empty, and its final byte is not ``\\n``.

    DELIBERATE DUPLICATION of ``shared/scripts/lib/jsonl_records.ends_without_newline``,
    which is the SSOT for this contract. This plugin CANNOT import it: it ships its
    own ``scripts/lib/`` package, so ``from lib import jsonl_records`` resolves to
    THIS package and raises ImportError — the ``sys.modules['lib']`` collision that
    ADR-045 describes. Verified empirically, not assumed.

    Keep in lock step with the shared leaf; the contract is small and stable
    (missing / zero-byte -> False, since seeking -1 from an empty file raises).
    """
    try:
        if path.stat().st_size == 0:
            return False
        with path.open("rb") as fh:
            fh.seek(-1, 2)  # 2 == os.SEEK_END
            return fh.read(1) != b"\n"
    except (OSError, ValueError):
        return False


# DROPS LAYOUT (issue 978, S4). DELIBERATE DUPLICATION of ``shared/scripts/lib/events_layout`` +
# ``events_write`` (same ADR-045 reason as the terminator guard above): layout resolution, the
# ``<key>--<wt8>--<nonce8>.jsonl`` name, the ``run`` stamp and the atomic first write. One drop file per
# process (this writer takes no lock). ``test_events_writers_drops`` pins wt8 / name parity with the SSOT.
_DROPS_DIR = ".shipwright/events/drops"
_BAD_KEY = re.compile(r"[^A-Za-z0-9._-]")
_drop_targets: dict[str, Path] = {}


def _drops_layout(root: Path) -> bool:
    if os.environ.get("SHIPWRIGHT_EVENTS_LAYOUT" + "_TEST") == "1":  # READ only (name split: plugins never set the flag)
        forced = os.environ.get("SHIPWRIGHT_EVENTS_LAYOUT", "").strip().lower()
        if forced in ("legacy", "drops"):
            return forced == "drops"
    try:
        cfg = json.loads((root / "shipwright_sync_config.json").read_text(encoding="utf-8-sig"))
        return isinstance(cfg, dict) and cfg.get("events_layout") == "drops"
    except (OSError, ValueError):
        return False


def _wt8(root: Path) -> str:
    try:
        git_dir = subprocess.run(["git", "-C", str(root), "rev-parse", "--absolute-git-dir"], capture_output=True,
                                 text=True, timeout=15, check=True).stdout.strip()
        git_dir = os.path.realpath(git_dir)
    except (OSError, subprocess.SubprocessError):
        git_dir = os.path.realpath(root)
    return hashlib.sha256(os.path.normcase(git_dir).encode("utf-8")).hexdigest()[:8]


def _drop_key() -> str:
    raw = os.environ.get("SHIPWRIGHT_RUN_ID", "").strip() or "_adopt"
    return (_BAD_KEY.sub("-", raw).lstrip(".") or "_run")[:80]


def events_target(events_path: Path) -> Path:
    """The file/folder a seeded event ends up in: the drop file under the drops layout, else ``events_path``."""
    root = events_path.parent
    return _drop_targets.get(str(root.resolve()), events_path) if _drops_layout(root) else events_path


def _is_closed(root: Path, target: Path) -> bool:
    """True when ``target`` is in the index (staged or committed)."""
    rel = f"{_DROPS_DIR}/{target.name}"
    try:
        listed = subprocess.run(["git", "-C", str(root), "ls-files", "--", rel], capture_output=True, text=True, timeout=15)
        return listed.returncode == 0 and bool(listed.stdout.strip())  # not a repo: nothing can be committed
    except (OSError, subprocess.SubprocessError):
        return True


def _append_drop(root: Path, event: dict[str, Any]) -> None:
    key = str(root.resolve())
    event = {**event, "id": f"evt-{uuid4().hex[:16]}", "run": _drop_key()}
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"  # compact: the stamp stays the last member
    target = _drop_targets.get(key)
    if target is not None and _is_closed(root, target):
        target = None  # staged / committed since: a closed file is never edited
    if target is None or not target.exists():
        (root / _DROPS_DIR).mkdir(parents=True, exist_ok=True)
        target = root / _DROPS_DIR / f"{_drop_key()}--{_wt8(root)}--{uuid4().hex[:8]}.jsonl"
        tmp = target.with_name("." + target.name + ".tmp")  # invisible to readers until the rename
        tmp.write_text(line, encoding="utf-8", newline="\n")
        os.replace(tmp, target)
        _drop_targets[key] = target
        return
    with target.open("a", encoding="utf-8", newline="\n") as f:  # LF on every platform, like every other writer
        f.write(line)


def _append_jsonl(path: Path, event: dict[str, Any]) -> None:
    if path.name == "shipwright_events.jsonl" and _drops_layout(path.parent):
        _append_drop(path.parent, event)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    # Termination guard (iterate-2026-07-18-events-jsonl-record-boundary): this
    # writer takes NO lock and appends repeatedly (the adopted event, then N
    # backfill events), so it must not assume the previous line was terminated —
    # otherwise two records land on one physical line and a reader without
    # record-boundary recovery discards BOTH.
    needs_separator = _ends_without_newline(path)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        if needs_separator:
            f.write("\n")
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def seed_adopted_event(
    events_path: Path,
    *,
    profile: str,
    scope: str,
    features_inferred: int,
    nested_excluded: list[str],
    plugin_version: str,
    commit_sha: str | None,
) -> dict[str, Any]:
    event = {
        "type": "adopted",
        "timestamp": _utc_now_iso(),
        "profile": profile,
        "scope": scope,
        "features_inferred": features_inferred,
        "nested_excluded": nested_excluded,
        "plugin_version": plugin_version,
        "commit_at_adoption": commit_sha or "HEAD",
    }
    _append_jsonl(events_path, event)
    return event


def seed_backfill_events(
    events_path: Path,
    refactor_commits: list[dict[str, Any]],
    *,
    max_count: int = 10,
) -> int:
    """Write backfill `work_completed` events from major refactor commits.

    Returns the number of events written.
    """
    written = 0
    for commit in refactor_commits[:max_count]:
        event = {
            "type": "work_completed",
            "timestamp": commit.get("date") or _utc_now_iso(),
            "source": "adopted-backfill",
            "confidence": "low",
            "commit_sha": commit.get("sha", ""),
            "subject": commit.get("subject", ""),
            "author": commit.get("author", ""),
            "files_changed": commit.get("files_changed", 0),
        }
        _append_jsonl(events_path, event)
        written += 1
    return written
