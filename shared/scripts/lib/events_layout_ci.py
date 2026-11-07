"""Consumer CI check: no legacy event-log writes once the drops layout is on (issue 978, S7).

Judged at the MERGE-BASE, not at the head: a PR that was opened before the flip (base still ``legacy`` or
without the key) keeps appending to ``shipwright_events.jsonl`` and is NOT failed, even when its head already
carries ``events_layout: drops``; once the merge-base declares ``drops`` a PR that touches the legacy log is
the old-writer case the layout exists to stop, and fails. A merge-base or head declaration this plugin
generation does not understand fails closed too. A head that declares ``legacy`` with no drop file left
(the emergency-fold rollback shape) passes. Needs the merge-base: check out with ``fetch-depth: 0``. ``allow_full_fold`` accepts the operator's full-fold
rollback commit, which writes into the legacy log by design.

A head that declares ``drops`` (a PR that took main in) is judged per commit: a commit that touches the legacy log
counts only when its first parent is already on ``drops`` (S8). Any other head is judged by the plain merge-base diff.

No-op (no violations) while the merge-base is ``legacy`` / absent. Blobs are read with ``git cat-file``
(``events_fold_io.blob``), never ``git show``. Never prints.
"""

from __future__ import annotations

import json
from pathlib import Path

from .events_fold_io import GitError, blob, git, parse_bytes, same_bytes, tree_names  # noqa: F401 -- GitError re-exported for the CLI
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


def _legacy_written_on_drops(root: Path, base_ref: str, head_ref: str) -> bool:
    """True when a commit of the PR itself (not a merge) touches the legacy log on top of a tree that is already ``drops``.

    A PR open at the flip appended the legacy log while the layout was still legacy; once it merges main in, the merge-base
    moves past the flip and a plain base..head diff would blame those older appends (S8 rehearsal). Judged per commit
    instead: the layout at the commit's FIRST PARENT decides. A PR rebased onto the flipped main has every commit on
    drops, so its legacy appends are (rightly) flagged: those events must be re-recorded as drops.
    Only the PR's own non-merge commits are judged (a merge commit's own content is a known gap, see the flip note).
    """
    if _layout_at(root, head_ref) != "drops":   # a head that does not declare drops is no in-flight PR: the plain diff judges it
        return bool(git(root, "diff", "--name-only", "--no-renames", base_ref + "..." + head_ref, "--", EVENT_FILE).stdout.strip())
    base = git(root, "merge-base", base_ref, head_ref).stdout.decode().strip()
    rows = git(root, "log", "--full-history", "--no-merges", "--format=%H %P", f"{base_ref}..{head_ref}", "--", EVENT_FILE).stdout
    own = set(git(root, "log", "--first-parent", "--format=%H", f"{base_ref}..{head_ref}").stdout.decode().split())
    for row in rows.decode("utf-8", "replace").splitlines():
        parts = row.split()
        # only the PR's OWN line (first parents) can have been written before the flip; a commit that came in through a merge's
        # second parent (a side branch from a pre-flip commit) is judged like any other and fails closed
        if len(parts) < 2 or parts[0] not in own or _layout_at(root, parts[1]) == "drops":   # no parent to judge against: fail closed
            return True
        # written before the flip = its parent is not on drops AND it does not descend from the (drops) merge-base;
        # a PR's own earlier commits flipping the key to legacy and back (drops -> legacy -> append -> drops) cannot excuse it
        if git(root, "merge-base", "--is-ancestor", base, parts[0], check=False).returncode == 0:
            return True
    return False


def _only_unfoldable_leftovers(root: Path, base: str, head_ref: str, names: list[str]) -> bool:
    """True when every drop left at the head is one an emergency fold CANNOT move: it was not ok at the merge-base and is unchanged.

    That is the shape the fold itself leaves behind (``plan_fold`` skips corrupt and empty files); the layout sentinel honours
    the explicit ``legacy`` declaration there, so a rollback that finishes the job by writing the legacy log is not an old writer.
    A readable drop at the head, or one this change added, is not that shape.
    """
    for n in names:
        was, now = blob(root, base, f"{DROPS_DIR}/{n}"), blob(root, head_ref, f"{DROPS_DIR}/{n}")
        if was is None or now is None or not same_bytes(was, now) or parse_bytes(was).status == "ok":
            return False
    return True


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
        stuck = [n for n in left if n.endswith(".jsonl")]
        if not stuck or _only_unfoldable_leftovers(root, base, head_ref, stuck):
            return out
    if _legacy_written_on_drops(root, base_ref, head_ref):
        out.append(Violation("legacy_write_after_flip", EVENT_FILE,
                             "the merge-base uses events_layout drops, but this change modifies the legacy log; "
                             "write events through the Shipwright tools (shipwright_events.d/) or update the plugins"))
    return out
