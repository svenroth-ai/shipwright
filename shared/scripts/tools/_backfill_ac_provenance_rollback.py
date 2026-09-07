"""The snapshot/rollback wrapper around ``apply_upgrades`` for
``backfill_ac_provenance.py``'s ``--write`` path. Split out at the 300-LOC
bloat-baseline threshold (same precedent as ``_backfill_ac_provenance_apply.py``
itself) so ``main()`` stays a thin CLI shell.

Snapshots every candidate file BEFORE writing so any of three failure modes
-- an uncaught I/O exception mid-batch, a post-write orphan tag, or a
SILENTLY-reported write failure for a sibling candidate -- restores every
file this run touched, never leaving a half-applied tree behind a non-zero
exit (external plan review, P3.4, glm low / openai medium; Tier-3 CI-gate
re-review, P3.4 high, across several re-review rounds).

Every snapshot read and every restore write is guarded by
``backfill_write.is_contained`` (Tier-3 CI-gate re-review, P3.4 high): a
candidate whose path resolves outside the project root (a committed symlink)
must never be read through on snapshot, nor written through on restore --
``write_bytes`` FOLLOWS a symlink, so an unrelated sibling's rollback could
otherwise rewrite a file outside the repository.
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from backfill_write import is_contained  # noqa: E402


def apply_with_rollback(project_root: Path, report: dict, spec_path: Path,
                         apply_upgrades, validate_applied) -> tuple[dict, int]:
    """Returns ``(apply_out, rc)`` -- ``apply_out`` is what the caller assigns
    to ``out["apply"]``; ``rc`` is 0 on success, 1 if a rollback fired."""
    originals: dict[Path, bytes] = {}
    for cand in report["candidates"]:
        if cand.get("status") != "candidate":
            continue
        for rel in cand.get("test_files", []):
            abs_path = project_root / rel
            if abs_path.is_file() and is_contained(project_root, abs_path):
                originals[abs_path] = abs_path.read_bytes()

    def _restore() -> None:
        for abs_path, content in originals.items():
            if is_contained(project_root, abs_path):
                abs_path.write_bytes(content)

    try:
        apply_result = apply_upgrades(project_root, report)
    except OSError as exc:
        # An I/O failure partway through apply_upgrades's per-file writes
        # previously propagated straight out of main(), leaving every file
        # written before the failure modified with no rollback.
        _restore()
        return {"write_error": str(exc), "rolled_back": True}, 1

    orphans = validate_applied(project_root, apply_result, spec_path)
    # A write attempted for one candidate can fail after a SIBLING candidate's
    # upgrade already landed on disk in the same batch -- that must roll back
    # too, not just report an unqualified success.
    if orphans or apply_result.get("write_failures_occurred"):
        _restore()
        if orphans:
            apply_result["orphan_tags_written"] = orphans
        apply_result["rolled_back"] = True
        return apply_result, 1
    return apply_result, 0


__all__ = ["apply_with_rollback"]
