"""run_id-resolution guard for the iterate spec checks (S2/S3/S9/S10, W2).

Layer 2 of iterate-2026-05-31-phasequality-triage-bundle. When the resolved
run_id is a sentinel (``""`` / ``"unknown"`` — emitted by the phase-quality
Stop audit when no iterate run_id is resolvable) or has no exact
``iterate_history`` entry, AND no matching spec/mini-plan file is on disk,
S2/S3 SKIP — instead of tail-falling-back to the most-recent entry's
complexity and emitting an unsatisfiable FAIL. A matching file on disk
preserves the file-exists -> PASS signal.

S9/S10 take the same guard with ``candidates=[]`` (no run-specific file
exists for either, so there is no file-exists -> PASS signal to preserve).
They read the tail-fallback's ``type``/``category`` rather than its
``complexity``, so before the guard an unresolvable run_id let an *unrelated*
run's category decide their verdict — the sentinel-trigger sibling of the
corrupt-entry trigger ``resolve_iterate_entry`` closes below
(iterate-2026-08-06-s9-s10-sentinel-guard).

Which run_ids actually reach these checks matters, because it decides how much
the guard is worth. The sole production caller is the phase-quality Stop audit,
whose id comes from ``lib.phase_quality.resolve_run_id``.

**Since iterate-2026-08-06-resolve-run-id-seam that id is usually the real
one.** ``resolve_run_id`` gained priority 0 — the per-session run pointer
``setup_iterate_worktree.py`` writes at B1a — so an iterate audited from its own
worktree resolves its canonical ``iterate-YYYY-MM-DD-slug``, matches an
``iterate_history`` entry, and these checks actually evaluate. That is the seam
this module's guard was waiting on (formerly tracked as trg-0a80a7e7).

The guard still carries the cases the pointer cannot answer, and they are not
rare: an audit whose ``project_root`` is the MAIN root cannot see the run's own
ledger entry until the PR merges; a non-iterate session has no pointer at all;
and a campaign / autonomous-loop run falls through to
``SHIPWRIGHT_LOOP_ID``(+``_UNIT_ID``). **That last branch is the one that
mattered before the guard existed:** the read-time rollup filter
(``is_sentinel_run``) already dropped sentinel-run findings from every consumer,
but a loop id is not a sentinel, so there the inherited-category verdict really
did reach the triage backlog and the dashboard. None of those three is an
``iterate_history`` key, so all three still SKIP here.

Caveat worth knowing when triaging one of these SKIPs: ``has_exact_iterate_entry``
swallows any read error and returns ``False``, so an UNREADABLE iterate store is
reported identically to a foreign audit context.

Extracted into its own module (rather than inlined in ``spec_checks.py``) to
keep that already-grandfathered file under its bloat baseline.

``resolve_iterate_entry`` is the shared tail-fallback resolver for
``spec_checks._read_iterate_entry`` / ``iterate_compliance._latest_iterate_entry``
(both now thin wrappers over it, for the same bloat-baseline reason): it tells
a REQUESTED run whose own entry file is corrupt apart from one that is simply
not written yet, so only the latter may fall back to the most recent entry
(trg-e0a0f569).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.phase_quality import STATUS_SKIP, make_finding  # noqa: E402

_RUN_ID_SENTINELS = frozenset({"", "unknown"})


def has_exact_iterate_entry(project_root: Path, run_id: str) -> bool:
    """True when ``run_id`` matches an ``iterate_history`` entry EXACTLY.

    Unlike ``spec_checks._read_iterate_entry``, this does NOT tail-fall-back
    to the most-recent entry — a sentinel run_id must not inherit the latest
    iterate's complexity.
    """
    if not run_id or run_id.lower() in _RUN_ID_SENTINELS:
        return False
    from lib.iterate_entry import read_iterate_entries

    try:
        entries = read_iterate_entries(project_root)
    except Exception:  # noqa: BLE001 — fail-safe: treat as no exact match
        return False
    return any(
        isinstance(e, dict) and e.get("run_id") == run_id
        for e in (entries or [])
    )


def own_entry_file_is_corrupt(
    project_root: Path, run_id: str, entries: list[dict[str, Any]] | None = None,
) -> bool:
    """True when ``run_id``'s own entry is unreadable rather than genuinely absent.

    Two storage paths can hide a requested run's own entry from the merged
    ``read_iterate_entries`` result: its per-file ``iterates/<run_id>.json`` exists
    but failed to decode/parse, OR it lives only in the legacy
    ``iterate_history`` array and ``shipwright_run_config.json`` itself failed to
    parse (so the legacy array silently reads as empty — we cannot rule out the
    entry being in there). Either way, the requested run's own data is
    unreadable, NOT genuinely unwritten.

    Distinguishes that from the *genuinely unwritten* case (no per-file entry
    AND a readable — or absent — legacy config that simply does not mention
    ``run_id``), which is the one legitimate reason for
    ``resolve_iterate_entry`` to tail-fall-back to the most recent entry.
    Corruption of the REQUESTED run's own entry must never be papered over by
    substituting a different run's category/complexity.

    ``entries`` lets a caller that already has the merged result (e.g.
    ``resolve_iterate_entry``) pass it through instead of triggering a second
    full re-parse; omit it to fetch fresh. Safe against interleaving with a
    concurrent writer only because it never is: one iterate = one worktree =
    one physical directory (`references/artifact-ownership.md` B1a), F5c
    (the sole writer) always completes before F11 calls this in the SAME
    process, and no code path ever deletes a live run's own entry file
    (retention only evicts entries OLDER than the one being written). A
    caller reading a project_root that genuinely is being concurrently
    written from outside that model is out of scope for this guard.

    Fails CLOSED (returns ``True``) on any unexpected error — an error while
    determining corruption is itself the ambiguous case this guards against,
    so it must never resolve in favor of permitting a substitution.
    """
    if not run_id:
        return False
    from lib.iterate_entry import RUN_CONFIG_NAME, entry_file_for, read_iterate_entries

    try:
        target = entry_file_for(project_root, run_id)
        # is_symlink() also catches a DANGLING link (target missing), which
        # .exists() alone would follow and report False on — read_iterate_entries
        # excludes every symlink regardless of target validity (_is_entry_file),
        # so a dangling one must count as "present but unreadable", not "absent".
        own_file_exists = target.exists() or target.is_symlink()
        legacy_unreadable = False
        legacy_config = project_root / RUN_CONFIG_NAME
        if legacy_config.exists():
            try:
                json.loads(legacy_config.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                legacy_unreadable = True
        if not own_file_exists and not legacy_unreadable:
            return False
        if entries is None:
            entries = read_iterate_entries(project_root)
    except Exception:  # noqa: BLE001 — fail CLOSED: ambiguity favors "corrupt"
        return True
    return not any(
        isinstance(e, dict) and e.get("run_id") == run_id for e in (entries or [])
    )


def resolve_iterate_entry(project_root: Path, run_id: str) -> dict[str, Any] | None:
    """Merged-reader lookup for ``run_id`` with a corruption-aware tail fallback.

    Returns the exact entry when present. Returns ``None`` when there is no
    iterate history at all, or when ``run_id``'s own entry is unreadable
    (per-file or legacy-array corruption) — never substitutes a different
    run's category/complexity in that case (trg-e0a0f569). Otherwise falls
    back to the most recent entry, legitimate only when ``run_id`` genuinely
    has no entry yet (mid-flow finalize reaching a verifier before F5c writes
    it).
    """
    from lib.iterate_entry import read_iterate_entries

    entries = read_iterate_entries(project_root)
    if not entries:
        return None
    for entry in entries:
        if entry.get("run_id") == run_id:
            return entry
    if own_entry_file_is_corrupt(project_root, run_id, entries):
        return None
    return entries[-1]


def unresolvable_run_id_skip(
    project_root: Path,
    run_id: str,
    candidates: list[Any],
    check_id: str,
    name: str,
    provenance: str | None = None,
) -> dict[str, Any] | None:
    """Return a SKIP finding when ``run_id`` is unresolvable AND no file on disk.

    Returns ``None`` (caller proceeds with normal logic) when ``run_id`` has
    an exact ``iterate_history`` entry OR a matching spec/mini-plan file
    already exists (``candidates`` non-empty) — so the file-exists -> PASS
    signal is preserved.
    """
    if has_exact_iterate_entry(project_root, run_id) or candidates:
        return None
    kw: dict[str, Any] = {"name": name}
    if provenance:
        kw["provenance"] = provenance
    return make_finding(
        check_id, STATUS_SKIP,
        f"run_id={run_id} is not a resolvable iterate run "
        "(no exact iterate_history entry, no matching file) — "
        "spec check not applicable in this audit context",
        **kw,
    )
