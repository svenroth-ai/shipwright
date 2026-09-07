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

    def _restore() -> list[str]:
        # Best-effort (Tier-3 CI-gate re-review, P3.4 high): a write failure
        # on ONE file during restore must not abort the loop and leave every
        # LATER file un-restored -- every file gets its own restore attempt,
        # and a failure is reported rather than silently swallowed or crashed.
        failures: list[str] = []
        for abs_path, content in originals.items():
            if not is_contained(project_root, abs_path):
                continue
            try:
                abs_path.write_bytes(content)
            except OSError:
                failures.append(str(abs_path))
        return failures

    def _rolled_back_result(result: dict, restore_failures: list[str]) -> dict:
        result["rolled_back"] = not restore_failures
        if restore_failures:
            result["restore_failures"] = restore_failures
        return result

    try:
        apply_result = apply_upgrades(project_root, report)
    except OSError as exc:
        # An I/O failure partway through apply_upgrades's per-file writes
        # previously propagated straight out of main(), leaving every file
        # written before the failure modified with no rollback.
        return _rolled_back_result({"write_error": str(exc)}, _restore()), 1

    try:
        orphans = validate_applied(project_root, apply_result, spec_path)
    except (OSError, UnicodeDecodeError) as exc:
        # validate_applied reads spec.md AFTER writes already landed -- a
        # transient failure there must not leave those writes un-rolled-back
        # (Tier-3 CI-gate re-review, P3.4 high; this used to run outside any
        # try/except at all). UnicodeDecodeError (malformed UTF-8) is a
        # ValueError, not an OSError -- `except OSError` alone does not
        # catch it (Tier-3 CI-gate re-review, P3.4 high, round 9).
        apply_result["validate_error"] = str(exc)
        return _rolled_back_result(apply_result, _restore()), 1

    # A write attempted for one candidate can fail after a SIBLING candidate's
    # upgrade already landed on disk in the same batch -- that must roll back
    # too, not just report an unqualified success.
    if orphans or apply_result.get("write_failures_occurred"):
        if orphans:
            apply_result["orphan_tags_written"] = orphans
        return _rolled_back_result(apply_result, _restore()), 1
    return apply_result, 0


__all__ = ["apply_with_rollback"]
