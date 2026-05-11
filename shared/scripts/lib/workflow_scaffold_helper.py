"""Shared idempotent workflow-file copy helper.

Adopted from the `security_workflow_scaffolder.py` pattern but extracted
so the new CI + Claude-Review scaffolders share the path-creation +
idempotency + structured-result logic (external-review #O11). The
security scaffolder is intentionally NOT migrated to this helper in the
same iterate — separate diff to keep this iterate's blast radius
focused.

Invariants:

* **Auto-write on absence.** Adopt is the entry point for brownfield
  repos; missing workflows are the default case. The helper writes
  silently.
* **Never overwrite.** Pre-existing files at the target path — whether
  a prior shipwright workflow, a hand-rolled GitHub Actions YAML, or
  anything else — are preserved bit-for-bit. The helper returns
  ``wrote=False, reason="already_exists"`` so the adopt handoff can
  surface the skip.
* **Auto-create parent dirs.** Brownfield repos may not have
  ``.github/`` yet; the helper creates intermediate dirs with
  ``parents=True, exist_ok=True``.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TypedDict


class ScaffoldResult(TypedDict):
    wrote: bool
    path: str
    # See callers for the full reason vocabulary; this module emits
    # "scaffolded" | "already_exists" | "template_missing".
    reason: str


def copy_template_if_absent(
    *,
    template_path: Path,
    target_path: Path,
) -> ScaffoldResult:
    """Copy ``template_path`` to ``target_path`` if the target is absent.

    Args:
        template_path: Absolute path to the source template file.
        target_path: Absolute path to where the rendered workflow should land.

    Returns:
        ScaffoldResult with the operation outcome.

    Raises:
        FileNotFoundError: If the source template doesn't exist. This
            indicates a development-time bug (constants module declares a
            template path that doesn't resolve) — loud failure is correct.
    """
    if target_path.exists():
        return {
            "wrote": False,
            "path": str(target_path),
            "reason": "already_exists",
        }

    if not template_path.exists():
        # Convention lock declares a path that doesn't resolve — this is a
        # development-time bug, not a target-project condition. Caller
        # should surface this loudly.
        raise FileNotFoundError(
            f"workflow template missing at {template_path}. "
            f"This indicates a constants-module mismatch in shared/scripts/lib/."
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template_path, target_path)

    return {
        "wrote": True,
        "path": str(target_path),
        "reason": "scaffolded",
    }
