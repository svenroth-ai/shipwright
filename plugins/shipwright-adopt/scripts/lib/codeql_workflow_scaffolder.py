"""Scaffold the GitHub Actions CodeQL workflow into adopted target repos.

Adopted brownfield repos arrive without a CodeQL workflow. /shipwright-adopt
lands a dormant `codeql.yml` whose `language:` matrix is rendered from the
detected stack profile, so the repo can offer the `Analyze (<language>)`
Required-Check job names that B4.5-style automerge branch protection needs
(alongside `ci.yml`, `security.yml`, `claude-review.yml`). Activation +
branch-protection wiring is documented in the scaffolded `AUTOMERGE_SETUP.md`.

Unlike the pure-copy CI / security / Claude-Review scaffolders, this one
RENDERS: it substitutes the `${SHIPWRIGHT_CODEQL_LANGUAGES}` placeholder in the
template for the profile's YAML language list before writing. The convention
lock (`shared/scripts/lib/codeql_workflow.py`) owns the placeholder, the
path, and the profile→languages SSoT — this module does not hard-code them.

Module-load uses `spec_from_file_location` (ADR-045): both adopt and shared
expose a package named `lib`, and a plain `from lib import ...` would shadow
one with the other depending on import order.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TypedDict

# parents[0]=lib, [1]=scripts, [2]=shipwright-adopt, [3]=plugins, [4]=<root>.
_REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_module(path: Path, alias: str):
    spec = importlib.util.spec_from_file_location(alias, path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CODEQL = _load_module(
    _REPO_ROOT / "shared" / "scripts" / "lib" / "codeql_workflow.py",
    "_shipwright_adopt_codeql_workflow_constants",
)

CODEQL_WORKFLOW_PATH: str = _CODEQL.CODEQL_WORKFLOW_PATH
CODEQL_TEMPLATE_PATH: str = _CODEQL.CODEQL_TEMPLATE_PATH
LANGUAGES_PLACEHOLDER: str = _CODEQL.LANGUAGES_PLACEHOLDER


class ScaffoldResult(TypedDict):
    wrote: bool
    path: str
    reason: str
    # languages rendered into the matrix (empty when nothing was written).
    languages: list[str]


def scaffold_codeql_workflow(
    project_root: Path, *, profile_name: str | None
) -> ScaffoldResult:
    """Render + write the dormant CodeQL workflow into ``project_root``.

    Args:
        project_root: Target adopted repository's root directory.
        profile_name: Profile name from snapshot.profile.matched. Caller
            (generate_adoption_artifacts.py) owns snapshot parsing.

    Returns:
        ScaffoldResult with one of these reason codes:
        - ``scaffolded`` — wrote=True; rendered template written.
        - ``already_exists`` — wrote=False; pre-existing target preserved.
        - ``no_codeql_for_profile`` — wrote=False; profile recognized but no
          CodeQL language mapping registered for it.
        - ``profile_unresolved`` — wrote=False; profile_name is None / empty
          (distinct from "registered profile without languages" so
          snapshot-parsing failures surface as their own diagnostic).
    """
    target = project_root / CODEQL_WORKFLOW_PATH

    if profile_name is None or not profile_name.strip():
        return {
            "wrote": False,
            "path": str(target),
            "reason": "profile_unresolved",
            "languages": [],
        }

    languages = _CODEQL.languages_for_profile(profile_name)
    if not languages:
        return {
            "wrote": False,
            "path": str(target),
            "reason": "no_codeql_for_profile",
            "languages": [],
        }

    # Never overwrite a pre-existing workflow (hand-rolled CodeQL config, a
    # prior shipwright scaffold, anything). Checked AFTER profile resolution so
    # an unresolved profile surfaces its own diagnostic regardless of target
    # state — mirrors ci_workflow_scaffolder's ordering.
    if target.exists():
        return {
            "wrote": False,
            "path": str(target),
            "reason": "already_exists",
            "languages": [],
        }

    template = _REPO_ROOT / CODEQL_TEMPLATE_PATH
    if not template.exists():
        # Convention lock declares a path that doesn't resolve — dev-time bug.
        raise FileNotFoundError(
            f"CodeQL workflow template missing at {template}. "
            f"shared/scripts/lib/codeql_workflow.py declares "
            f"CODEQL_TEMPLATE_PATH={CODEQL_TEMPLATE_PATH!r} but no such file exists."
        )

    rendered = template.read_text(encoding="utf-8").replace(
        LANGUAGES_PLACEHOLDER, _CODEQL.render_languages_yaml(languages)
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")

    return {
        "wrote": True,
        "path": str(target),
        "reason": "scaffolded",
        "languages": list(languages),
    }
