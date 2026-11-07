"""Consumer CI check: no legacy event-log writes once the drops layout is on (issue 978, S7).

Judged at the MERGE-BASE, not at the head: a PR that was opened before the flip (base still ``legacy`` or
without the key) keeps appending to ``shipwright_events.jsonl`` and is NOT failed, even when its head already
carries ``events_layout: drops``; once the merge-base declares ``drops`` a PR that touches the legacy log is
the old-writer case the layout exists to stop, and fails. A merge-base or head declaration this plugin
generation does not understand fails closed too. A head that declares ``legacy`` with no drop file left
(the emergency-fold rollback shape) passes. Needs the merge-base: check out with ``fetch-depth: 0``. ``allow_full_fold`` accepts the operator's full-fold
rollback commit, which writes into the legacy log by design.

No-op (no violations) while the merge-base is ``legacy`` / absent. Blobs are read with ``git cat-file``
(``events_fold_io.blob``), never ``git show``. Never prints.
"""

from __future__ import annotations

import json
from pathlib import Path

from .events_fold_io import GitError, blob, git, tree_names  # noqa: F401 -- GitError re-exported for the CLI
from .events_integrity import Violation
from .events_log import DROPS_DIR, EVENT_FILE
from .events_sentinel import SUPPORTED_LAYOUTS, SYNC_CONFIG


def _layout_at(root: Path, rev: str) -> object:
    """The raw ``events_layout`` at ``rev`` (``None`` = absent / unreadable file)."""
    data = blob(root, rev, SYNC_CONFIG)
    if data is None:
        return None
    try:
        cfg = json.loads(data.decode("utf-8-sig"))
    except ValueError:
        return None
    return cfg.get("events_layout") if isinstance(cfg, dict) else None


def check_layout_ci(project_root: Path | str, base_ref: str, head_ref: str = "HEAD",
                    allow_full_fold: bool = False) -> list[Violation]:
    root = Path(project_root)
    parents = git(root, "rev-list", "--parents", "-n", "1", head_ref).stdout.decode().split()
    if len(parents) == 3 and parents[1] == git(root, "rev-parse", "--verify", base_ref + "^{commit}").stdout.decode().strip():
        head_ref = parents[2]  # GitHub's synthetic pull_request merge (HEAD^1 is the base tip): judge the PR's own tip
    base = git(root, "merge-base", base_ref, head_ref).stdout.decode().strip()
    out: list[Violation] = []
    for label, rev in (("merge-base", base), ("head", head_ref)):
        value = _layout_at(root, rev)
        if value is not None and value not in SUPPORTED_LAYOUTS:
            out.append(Violation("unsupported_layout", SYNC_CONFIG,
                                 f"events_layout {value!r} at the {label} is not a layout this plugin supports"))
    if _layout_at(root, base) is not None and _layout_at(root, head_ref) is None:
        out.append(Violation("layout_key_removed", SYNC_CONFIG,
                             "events_layout is present at the merge-base but missing at the head; the key is never removed"))
    if _layout_at(root, base) != "drops" or allow_full_fold:
        return out
    if _layout_at(root, head_ref) == "legacy":  # the emergency-fold rollback: declared legacy AND no drop file left at the head
        left = tree_names(root, head_ref, DROPS_DIR)
        if left is None:
            raise GitError(f"cannot list {DROPS_DIR}/ at {head_ref}")
        if not any(n.endswith(".jsonl") for n in left):
            return out
    changed = git(root, "diff", "--name-only", "--no-renames", base, head_ref, "--", EVENT_FILE).stdout
    if changed.decode("utf-8", "replace").strip():
        out.append(Violation("legacy_write_after_flip", EVENT_FILE,
                             "the merge-base uses events_layout drops, but this change modifies the legacy log; "
                             "write events through the Shipwright tools (shipwright_events.d/) or update the plugins"))
    return out
