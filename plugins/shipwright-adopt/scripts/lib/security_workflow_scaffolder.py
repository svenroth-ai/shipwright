"""Scaffold the GitHub Actions security workflow into adopted target repos.

Adopted brownfield repositories typically arrive without any Shipwright CI
plumbing — the WebUI repo, for example, ships a hand-written ``ci.yml`` but
no security workflow at all. /shipwright-adopt's job (Step E.13) is to land
the dormant scanner-chain workflow at the canonical path so the target repo
has a working Phase-B activation point without any further manual work.

Two non-negotiable invariants:

* **Auto-write on absence.** Adopt is the entry point for brownfield repos,
  so a missing workflow is the default case. The scaffolder writes silently.
* **Never overwrite.** A pre-existing file at the target path — whether a
  prior shipwright workflow, a hand-rolled CodeQL configuration, or
  anything else — is preserved bit-for-bit. The scaffolder reports
  ``wrote=False, reason="already_exists"`` so the adopt handoff can
  surface the skip.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TypedDict

try:  # tool context: lib/ is on sys.path (setup_adopt/_load_lib)
    from shared_loader import load_shared_module
except ImportError:  # test / package context: scripts/ on sys.path, lib is a package
    from lib.shared_loader import load_shared_module

# Resolve the shipwright monorepo root and load the convention-lock
# constants by file path. Layout (identical in dev repo and ~/.claude
# plugin cache):
#   <root>/plugins/shipwright-adopt/scripts/lib/<this-file>.py
#   <root>/shared/scripts/lib/security_workflow.py
# parents[0]=lib, parents[1]=scripts, parents[2]=shipwright-adopt,
# parents[3]=plugins, parents[4]=<root>.
#
# We deliberately do NOT add shared/scripts to sys.path: both adopt and
# shared expose a package called `lib`, and Python's regular-package
# resolution would shadow one with the other depending on import order.
# Loading the constants module by absolute file path under a unique
# private name avoids the collision entirely.
_REPO_ROOT = Path(__file__).resolve().parents[4]

_CONSTANTS = load_shared_module(
    "scripts/lib/security_workflow.py", "_shipwright_adopt_security_constants"
)
TEMPLATE_PATH: str = _CONSTANTS.TEMPLATE_PATH  # type: ignore[attr-defined]
WORKFLOW_PATH: str = _CONSTANTS.WORKFLOW_PATH  # type: ignore[attr-defined]


class ScaffoldResult(TypedDict):
    wrote: bool
    path: str
    reason: str  # "scaffolded" | "already_exists"


def scaffold_security_workflow(project_root: Path) -> ScaffoldResult:
    """Write the dormant security workflow into ``project_root``.

    Returns a structured result so the adopt handoff banner can render the
    "installed" vs "preserved" line without re-checking the filesystem.
    """
    target = project_root / WORKFLOW_PATH
    if target.exists():
        return {
            "wrote": False,
            "path": str(target),
            "reason": "already_exists",
        }

    template = _REPO_ROOT / TEMPLATE_PATH
    if not template.exists():
        # Convention lock declares a path that doesn't resolve — this is a
        # development-time bug, not a target-project condition. Loud failure
        # is correct.
        raise FileNotFoundError(
            f"security-workflow template missing at {template}. "
            f"shared/scripts/lib/security_workflow.py declares TEMPLATE_PATH={TEMPLATE_PATH!r} "
            f"but no such file exists in the shipwright tree."
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, target)

    return {
        "wrote": True,
        "path": str(target),
        "reason": "scaffolded",
    }
