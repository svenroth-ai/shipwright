"""Scaffold the gitleaks allowlist config into adopted target repos.

The Shipwright security workflow (``.github/workflows/security.yml``,
scaffolded by ``security_workflow_scaffolder``) runs
``gitleaks detect --no-git`` with **no** ``--config`` flag, so gitleaks
auto-loads a ``.gitleaks.toml`` from the repository root when one exists.
Without it, gitleaks' built-in ``sidekiq-secret`` rule false-matches the
magic-hex documentation placeholder ``cafebabe:deadbeef`` and the hardened
critical-gate (correctly blocking on ANY gitleaks result) turns every
freshly-adopted repo's first Security Scan red — a misleading "secret leak"
that is no leak at all (empirically proven on leadwright 2026-06-07: run
27086046885 red -> 27086178138 green after this file was added).

This scaffolder lands the allowlist at the repo root so the auto-load makes
the very first scan green. Two non-negotiable invariants (mirror
``security_workflow_scaffolder``):

* **Auto-write on absence.** Adopt is the entry point for brownfield repos,
  so a missing ``.gitleaks.toml`` is the default case. The scaffolder writes
  silently.
* **Never overwrite.** A pre-existing ``.gitleaks.toml`` — whether a prior
  adopt run or a hand-rolled allowlist — is preserved bit-for-bit. The
  scaffolder reports ``wrote=False, reason="already_exists"`` so the adopt
  handoff can surface the skip.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import TypedDict

# Resolve the shipwright monorepo root and load the convention-lock constants
# by file path. Layout (identical in dev repo and ~/.claude plugin cache):
#   <root>/plugins/shipwright-adopt/scripts/lib/<this-file>.py
#   <root>/shared/scripts/lib/security_workflow.py
# parents[0]=lib, parents[1]=scripts, parents[2]=shipwright-adopt,
# parents[3]=plugins, parents[4]=<root>.
#
# We deliberately do NOT add shared/scripts to sys.path: both adopt and shared
# expose a package called `lib`, and Python's regular-package resolution would
# shadow one with the other depending on import order. Loading the constants
# module by absolute file path under a unique private name avoids the
# collision entirely (same technique as security_workflow_scaffolder).
_REPO_ROOT = Path(__file__).resolve().parents[4]
_CONSTANTS_FILE = _REPO_ROOT / "shared" / "scripts" / "lib" / "security_workflow.py"


def _load_constants() -> object:
    spec = importlib.util.spec_from_file_location(
        "_shipwright_adopt_security_constants", _CONSTANTS_FILE
    )
    if spec is None or spec.loader is None:
        raise FileNotFoundError(
            f"could not load security-workflow constants from {_CONSTANTS_FILE}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CONSTANTS = _load_constants()
TEMPLATE_PATH: str = _CONSTANTS.GITLEAKS_CONFIG_TEMPLATE_PATH  # type: ignore[attr-defined]
CONFIG_PATH: str = _CONSTANTS.GITLEAKS_CONFIG_PATH  # type: ignore[attr-defined]


class ScaffoldResult(TypedDict):
    wrote: bool
    path: str
    reason: str  # "scaffolded" | "already_exists"


def scaffold_gitleaks_config(project_root: Path) -> ScaffoldResult:
    """Write the gitleaks allowlist into ``project_root``.

    Returns a structured result so the adopt handoff banner can render the
    "installed" vs "preserved" line without re-checking the filesystem.
    """
    target = project_root / CONFIG_PATH
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
            f"gitleaks config template missing at {template}. "
            f"shared/scripts/lib/security_workflow.py declares "
            f"GITLEAKS_CONFIG_TEMPLATE_PATH={TEMPLATE_PATH!r} "
            f"but no such file exists in the shipwright tree."
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, target)

    return {
        "wrote": True,
        "path": str(target),
        "reason": "scaffolded",
    }
