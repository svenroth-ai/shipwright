"""Pure evaluator for the removal → orphan F11 gate (Spec §11 R2/R3).

Split from ``_layer_coverage_core`` (ADR-099 300-LOC cap) once git rename-correlation
landed. Operates only on the two *already-regenerated* base/head manifests (R3): an FR that
was ``active`` at base but is no longer active at head (moved into ``## Removed
Requirements`` or deleted) must have every base-linked test deleted or retargeted to a live
FR. A bare ``@FR`` tag removal (the test escapes into ``untagged_tests``), a still-standing
tag → dead FR, or a rename+tag-strip are HARD findings — the exact rot (a removed feature's
E2E spec still green) the campaign exists to catch. Collision (un-namespaced fan-out) ids
route to ADVISORY (a HARD block on a legitimately-covered collision FR would be a false-red).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ._layer_coverage_core import _active_nodes, collision_display_ids


@dataclass
class HeadIndex:
    """Fast lookups over the head manifest for the removal gate's per-test classify."""

    untagged: set[str]
    orphan_tests: set[str]
    orphan_frs: dict[str, set[str]]        # test id → display ids it is STILL tagged to but dead
    link_display: dict[str, set[str]]      # test id → display ids of ACTIVE reqs linking it
    active_display_ids: set[str]


def build_head_index(head: dict) -> HeadIndex:
    untagged = {str(t) for t in (head.get("untagged_tests") or [])}
    orphan_tests: set[str] = set()
    orphan_frs: dict[str, set[str]] = {}
    for o in (head.get("orphans") or []):
        if not isinstance(o, dict) or not o.get("test"):
            continue
        tid = str(o["test"])
        orphan_tests.add(tid)
        if o.get("tagged_fr"):
            orphan_frs.setdefault(tid, set()).add(str(o["tagged_fr"]))
    link_display: dict[str, set[str]] = {}
    active_display: set[str] = set()
    for node in _active_nodes(head).values():
        disp = node.get("id")
        active_display.add(disp)
        for links in (node.get("tests") or {}).values():
            for link in links or []:
                tid = link.get("path") or link.get("id")
                if tid:
                    link_display.setdefault(str(tid), set()).add(disp)
    return HeadIndex(untagged, orphan_tests, orphan_frs, link_display, active_display)


@dataclass
class RemovalVerdict:
    removed_frs: list[str] = field(default_factory=list)          # namespaced keys
    hard: list[tuple[str, str, str]] = field(default_factory=list)      # (display, test, reason)
    advisory: list[tuple[str, str, str]] = field(default_factory=list)
    retired: list[tuple[str, str, str]] = field(default_factory=list)   # deleted/retargeted OK

    @property
    def any_fail(self) -> bool:
        return bool(self.hard)


def _classify_at_head(tid: str, removed_disp: str, hx: HeadIndex) -> tuple[str, str] | None:
    """Head state of a single test id, or None when the id is ABSENT at head.

    Order is load-bearing: STILL carrying the removed FR's dead ``@FR`` tag is HARD first,
    even if the test ALSO gained a valid active tag — a clean retarget REPLACES the tag, it
    must not merely supplement it (else the removed feature's stale spec keeps running).
    """
    if removed_disp in hx.orphan_frs.get(tid, set()):
        return "hard", "still tagged to the removed FR (dead tag not removed — not a clean retarget)"
    disps = hx.link_display.get(tid)
    if disps:
        if disps - {removed_disp}:
            return "retired", "retargeted to a live FR"          # gained a valid replacement tag
        return "advisory", "still tagged to a collision id (active in another namespace)"
    if tid in hx.untagged:
        return "hard", "bare @FR tag removed — test escaped into untagged_tests"
    if tid in hx.orphan_tests:
        return "hard", "still tagged to a removed/absent FR (orphan spec still stands)"
    return None


def _all_test_ids(manifest: dict) -> set[str]:
    """Every test id present at a revision: tagged links + untagged + orphans."""
    ids = {str(t) for t in (manifest.get("untagged_tests") or [])}
    ids |= {str(o.get("test")) for o in (manifest.get("orphans") or []) if isinstance(o, dict)}
    for node in (manifest.get("requirements") or {}).values():
        for links in (node.get("tests") or {}).values() if isinstance(node, dict) else []:
            for link in links or []:
                tid = link.get("path") or link.get("id")
                if tid:
                    ids.add(str(tid))
    return ids


def _classify_removed_test(
    test_id: str, removed_disp: str, hx: HeadIndex,
    rename_map: dict[str, str], base_ids: set[str],
) -> tuple[str, str]:
    """(bucket, reason) for one base-linked test of a removed FR at head.

    Checks the test under BOTH its original id AND — if git renamed the file — its new id.
    A rename+tag-strip must NOT read as ``deleted`` (external-review escape). Before crediting
    a deletion, a final heuristic guards the FUNCTION-rename-within-a-surviving-file case that
    git rename detection (file-level only) cannot see: if a candidate file gained a
    BRAND-NEW untagged test (present at head, absent at base) it may be the same test renamed
    and stripped, so surface ADVISORY rather than silently credit deletion (WARN, not a HARD
    false-red on a genuine delete-plus-unrelated-new-test).
    """
    path, _, name = test_id.partition("::")
    candidate_files = {path}
    candidates = [test_id]
    if path in rename_map and name:
        new_path = rename_map[path]
        candidate_files.add(new_path)
        candidates.append(f"{new_path}::{name}")
    for tid in candidates:
        verdict = _classify_at_head(tid, removed_disp, hx)
        if verdict is not None:
            return verdict
    # Fail-CLOSED escape check (external-review MUST-FIX): a brand-new untagged test (present
    # at head, absent at base) is a likely move/identifier-change + tag-strip of THIS test
    # when EITHER it sits in a candidate file (same file, or a git-detected rename target) OR
    # it keeps the SAME function/test name — the latter catches a move whose edits fell below
    # git's -M similarity threshold (rename_map empty) but which preserved the test name. A
    # HARD finding (a rare false-red on a genuine delete-plus-new-untagged-test is "merely
    # noisy"; a false-green defeats the gate). Only a move that ALSO renames the function AND
    # evades git detection escapes — a documented quadruple-adversarial residual.
    new_untagged = [
        u for u in hx.untagged
        if u not in base_ids and (
            u.rsplit("::", 1)[0] in candidate_files
            or (name and u.rsplit("::", 1)[-1] == name)
        )
    ]
    if new_untagged:
        return "hard", (
            f"base-linked test id absent but a new untagged test ({new_untagged[0]}) "
            "appeared — likely move/identifier-change + tag-strip escape")
    return "retired", "deleted at head"


def _base_linked_tests(node: dict) -> list[str]:
    out: list[str] = []
    for links in (node.get("tests") or {}).values():
        for link in links or []:
            tid = link.get("path") or link.get("id")
            if tid and tid not in out:
                out.append(str(tid))
    return out


def _removed_keys(head: dict) -> set[str]:
    """Keys whose head node is explicitly ``status: removed`` (a ``## Removed Requirements``
    row) — one of the two removal triggers (the other is a wholesale row deletion that still
    leaves a test standing, see :func:`_deleted_row_keys`)."""
    return {
        key for key, node in (head.get("requirements") or {}).items()
        if isinstance(node, dict) and node.get("status") == "removed"
    }


def _has_surviving_test(bnode: dict, disp: str, hx: HeadIndex, rename_map: dict[str, str]) -> bool:
    """True when head still carries a test for ``disp`` — an orphan STILL tagged to it, or a
    base-linked test that survives (untagged / orphaned / linked, or moved via rename_map)."""
    if any(disp in frs for frs in hx.orphan_frs.values()):
        return True
    for tid in _base_linked_tests(bnode):
        if tid in hx.untagged or tid in hx.orphan_tests or tid in hx.link_display:
            return True
        path, _, name = tid.partition("::")
        moved = f"{rename_map[path]}::{name}" if path in rename_map and name else None
        if moved and (moved in hx.untagged or moved in hx.orphan_tests or moved in hx.link_display):
            return True
    return False


def _deleted_row_keys(
    base_active: dict, head: dict, hx: HeadIndex, rename_map: dict[str, str],
) -> set[str]:
    """Base-active FRs whose row was DELETED OUTRIGHT (no head node at all) yet a test still
    stands for them (MUST-FIX 3) — a false-green the ``status: removed`` trigger alone misses.

    Fires only when the FR is truly gone: NOT active under any head namespace (guards against
    a relocation/collision to another split) AND its spec file was NOT renamed (guards against
    a spec-file move — ``rename_map``). Together these keep a genuine relocation from a
    false-red while catching a deleted feature whose test keeps running."""
    removed = _removed_keys(head)
    head_active = set(_active_nodes(head))
    out: set[str] = set()
    for key, bnode in base_active.items():
        if key in removed or key in head_active:
            continue
        disp = bnode.get("id")
        if disp in hx.active_display_ids:                       # still active elsewhere → relocation
            continue
        if (bnode.get("spec_path") or "") in rename_map:        # spec file moved → relocation
            continue
        if _has_surviving_test(bnode, disp, hx, rename_map):
            out.add(key)
    return out


def evaluate_removal(
    base: dict, head: dict, rename_map: dict[str, str] | None = None,
) -> RemovalVerdict:
    """A base-active FR that was removed (moved into ``## Removed Requirements`` OR its row
    deleted outright while a test still stands) must retire its base-linked tests.

    Two triggers: :func:`_removed_keys` (explicit ``status: removed``) and
    :func:`_deleted_row_keys` (a wholesale deletion with a surviving test, guarded against a
    relocation/collision false-red). ``rename_map`` (old→new path, from ``git diff -M``) plus
    the new-untagged escape check + the git-diff-independent orphan sweep close the
    rename/identifier + tag-strip escapes. A collision display id demotes an otherwise-HARD
    verdict to ADVISORY (the tag may cover a still-active same-id FR in another namespace).
    """
    rename_map = rename_map or {}
    verdict = RemovalVerdict()
    base_active = _active_nodes(base)
    hx = build_head_index(head)
    collisions = collision_display_ids(head)
    base_ids = _all_test_ids(base)
    # Two triggers: an explicit `status: removed` row AND a wholesale row deletion that still
    # leaves a test standing (MUST-FIX 3) — both must retire their base-linked tests.
    candidate_keys = _removed_keys(head) | _deleted_row_keys(base_active, head, hx, rename_map)
    for key, bnode in base_active.items():
        if key not in candidate_keys:
            continue
        verdict.removed_frs.append(key)
        disp = bnode.get("id")
        seen: set[str] = set()
        for test_id in _base_linked_tests(bnode):
            bucket, reason = _classify_removed_test(test_id, disp, hx, rename_map, base_ids)
            if bucket == "hard" and disp in collisions:
                bucket = "advisory"
                reason = f"{reason} (collision id — deferred, not a hard block)"
            getattr(verdict, bucket).append((disp, test_id, reason))
            seen.add(test_id)
        # Git-diff-INDEPENDENT sweep (external-review MUST-FIX): ANY test at head still tagged
        # to the removed display id is a dead-tag test still standing — a moved/renamed test
        # that KEPT its tag surfaces here even when git's -M rename detection misses it (the
        # regenerated head manifest sees the tag regardless of path). A collision id fans into
        # its still-active namespace (a link, never an orphan), so this branch is always HARD.
        if disp not in collisions:
            for test, frs in hx.orphan_frs.items():
                if disp in frs and test not in seen:
                    verdict.hard.append((disp, test,
                        "test still tagged to the removed FR (dead tag standing after a move)"))
                    seen.add(test)
    return verdict


__all__ = [
    "HeadIndex",
    "build_head_index",
    "RemovalVerdict",
    "evaluate_removal",
]
