"""Scaffold AUTOMERGE_SETUP.md into adopted target repos.

Lands a profile-aware branch-protection / auto-merge guide at the repo root.
The doc lists the Required-Check job names that the repo's ACTUALLY-scaffolded
workflows produce (derived by parsing the deployed `.github/workflows/*.yml`),
so it must run AFTER the ci / security / codeql / claude-review scaffolders.

Never overwrites a pre-existing `AUTOMERGE_SETUP.md` (a user may have edited it).

Render logic lives in `shared/scripts/lib/automerge_readiness.py` — loaded via
`spec_from_file_location` (ADR-045) so the shared `lib` package does not shadow
adopt's own `lib/`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

try:  # tool context: lib/ is on sys.path (setup_adopt/_load_lib)
    from shared_loader import load_shared_module
except ImportError:  # test / package context: scripts/ on sys.path, lib is a package
    from lib.shared_loader import load_shared_module

_AR = load_shared_module(
    "scripts/lib/automerge_readiness.py",
    "_shipwright_adopt_automerge_readiness",
)

AUTOMERGE_SETUP_OUTPUT_PATH: str = _AR.AUTOMERGE_SETUP_OUTPUT_PATH


class ScaffoldResult(TypedDict):
    wrote: bool
    path: str
    reason: str  # "scaffolded" | "already_exists"
    # Required-Check names the doc listed (empty when nothing was written).
    required_checks: list[str]


def scaffold_automerge_setup(
    project_root: Path, *, profile_name: str | None
) -> ScaffoldResult:
    """Render + write `AUTOMERGE_SETUP.md` into ``project_root`` if absent.

    Must be called after the workflow scaffolders so the doc reflects the real
    deployed workflow files. ``profile_name`` is a label only — the check names
    come from the deployed workflows, so the doc renders even for an unmapped
    profile (it just lists whatever workflows are present).
    """
    target = project_root / AUTOMERGE_SETUP_OUTPUT_PATH
    if target.exists():
        return {
            "wrote": False,
            "path": str(target),
            "reason": "already_exists",
            "required_checks": [],
        }

    content = _AR.render_automerge_setup(project_root, profile_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    return {
        "wrote": True,
        "path": str(target),
        "reason": "scaffolded",
        "required_checks": _AR.required_check_names(project_root),
    }
