"""Scaffold the GitHub Actions CI workflow into adopted target repos.

Adopted brownfield repositories typically arrive without a Shipwright-shaped
CI workflow — the webui repo's v0.8.5 cross-platform regression is the
canonical motivating example: a hand-written `ci.yml` that runs only on
ubuntu-latest, hiding Windows-pathing bugs from the test suite for days.

This scaffolder lands a profile-specific dormant CI template at the
canonical path (`.github/workflows/ci.yml`). The template carries the
cross-platform OS matrix (`ubuntu-latest` + `windows-latest`) as the
default so OS-coupled portability bugs surface at PR time.

External-review #O1: profile name is passed explicitly by the caller
(`generate_adoption_artifacts.py` reads `snapshot.profile.matched` and
forwards it). The scaffolder does not parse snapshot.json itself —
keeps the SSoT at the caller.

External-review #O12: distinct reason codes for "no template for this
profile" vs "profile name missing/malformed" so snapshot-parsing failures
upstream surface as their own diagnostic rather than masquerading as a
template gap.
"""

from __future__ import annotations

from pathlib import Path

try:  # tool context: lib/ is on sys.path (setup_adopt/_load_lib)
    from shared_loader import load_shared_module
except ImportError:  # test / package context: scripts/ on sys.path, lib is a package
    from lib.shared_loader import load_shared_module

# Resolve the shipwright monorepo root for the workflow template files.
# Layout (identical in dev repo and ~/.claude plugin cache):
#   <root>/plugins/shipwright-adopt/scripts/lib/<this-file>.py
#   <root>/shared/scripts/lib/ci_workflow.py
#   <root>/shared/scripts/lib/workflow_scaffold_helper.py
# parents[0]=lib, [1]=scripts, [2]=shipwright-adopt, [3]=plugins, [4]=<root>.
_REPO_ROOT = Path(__file__).resolve().parents[4]

_CI_WORKFLOW = load_shared_module(
    "scripts/lib/ci_workflow.py", "_shipwright_adopt_ci_workflow_constants"
)
_HELPER = load_shared_module(
    "scripts/lib/workflow_scaffold_helper.py", "_shipwright_adopt_ci_workflow_helper"
)

TEMPLATE_BY_PROFILE: dict[str, str] = _CI_WORKFLOW.TEMPLATE_BY_PROFILE
WORKFLOW_PATH: str = _CI_WORKFLOW.WORKFLOW_PATH
ScaffoldResult = _HELPER.ScaffoldResult  # re-export for typing


def scaffold_ci_workflow(
    project_root: Path, *, profile_name: str | None
) -> ScaffoldResult:
    """Write the profile-specific dormant CI workflow into ``project_root``.

    Args:
        project_root: Target adopted repository's root directory.
        profile_name: Profile name from snapshot.profile.matched. Caller
            (typically generate_adoption_artifacts.py) owns snapshot
            parsing and passes the result explicitly.

    Returns:
        ScaffoldResult with one of these reason codes:
        - ``scaffolded`` — wrote=True; template copied to target.
        - ``already_exists`` — wrote=False; pre-existing target preserved.
        - ``no_template_for_profile`` — wrote=False; profile recognized
          but no template registered for it.
        - ``profile_unresolved`` — wrote=False; profile_name is None,
          empty, or whitespace-only (distinct from "registered profile
          without template" so snapshot-parsing failures surface).
    """
    target = project_root / WORKFLOW_PATH

    # External-review #O12: profile_unresolved is distinct from
    # no_template_for_profile so callers can tell snapshot-parsing
    # failure from a deliberate "this profile has no CI template" miss.
    if profile_name is None or not profile_name.strip():
        return {
            "wrote": False,
            "path": str(target),
            "reason": "profile_unresolved",
        }

    template_rel = TEMPLATE_BY_PROFILE.get(profile_name.strip())
    if template_rel is None:
        return {
            "wrote": False,
            "path": str(target),
            "reason": "no_template_for_profile",
        }

    template = _REPO_ROOT / template_rel
    return _HELPER.copy_template_if_absent(
        template_path=template,
        target_path=target,
    )
