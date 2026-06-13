"""Integration + render tests for the AUTOMERGE_SETUP.md renderer
(shared/scripts/lib/automerge_readiness.py).

The card's defensive constraint: "wrong job names → branch protection silently
never matches". For each of the 3 stack profiles, build a sample adopted repo
from the REAL workflow templates (CI/security/claude copied; CodeQL rendered for
the profile's languages), then assert ``required_check_names`` returns exactly
the UNCONDITIONAL names those deployed workflows declare, that `if:`-gated deploy
jobs are split out as conditional (never requireable), and that the rendered doc
substitutes every placeholder. Pure check-name-derivation unit tests live in
``test_automerge_check_names.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from lib import automerge_readiness as ar  # noqa: E402
from lib.ci_workflow import (  # noqa: E402
    CLAUDE_REVIEW_TEMPLATE_PATH,
    CLAUDE_REVIEW_WORKFLOW_PATH,
    TEMPLATE_BY_PROFILE,
    WORKFLOW_PATH as CI_WORKFLOW_PATH,
)
from lib.codeql_workflow import (  # noqa: E402
    CODEQL_LANGUAGES_BY_PROFILE,
    CODEQL_TEMPLATE_PATH,
    CODEQL_WORKFLOW_PATH,
    LANGUAGES_PLACEHOLDER,
    render_languages_yaml,
)
from lib.security_workflow import (  # noqa: E402
    TEMPLATE_PATH as SECURITY_TEMPLATE_PATH,
    WORKFLOW_PATH as SECURITY_WORKFLOW_PATH,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# KNOWN_WORKFLOWS drift pin
# ---------------------------------------------------------------------------


def test_known_workflows_match_convention_modules() -> None:
    """KNOWN_WORKFLOWS basenames must match the per-workflow convention modules'
    deployed paths, else the doc would inspect the wrong files."""
    expected = {
        Path(CI_WORKFLOW_PATH).name,
        Path(SECURITY_WORKFLOW_PATH).name,
        Path(CODEQL_WORKFLOW_PATH).name,
        Path(CLAUDE_REVIEW_WORKFLOW_PATH).name,
    }
    assert set(ar.KNOWN_WORKFLOWS) == expected


# ---------------------------------------------------------------------------
# Defensive integration: per-profile sample repo
# ---------------------------------------------------------------------------


def _build_sample_repo(root: Path, profile: str) -> None:
    """Materialise the workflows /shipwright-adopt would scaffold for a profile.

    CI/security/claude-review are pure copies; CodeQL is rendered for the
    profile's language list (the scaffolder's exact substitution)."""
    wf_dir = root / ".github" / "workflows"
    wf_dir.mkdir(parents=True)

    def _copy(template_rel: str, out_rel: str) -> None:
        src = (REPO_ROOT / template_rel).read_text(encoding="utf-8")
        (root / out_rel).write_text(src, encoding="utf-8")

    _copy(TEMPLATE_BY_PROFILE[profile], CI_WORKFLOW_PATH)
    _copy(SECURITY_TEMPLATE_PATH, SECURITY_WORKFLOW_PATH)
    _copy(CLAUDE_REVIEW_TEMPLATE_PATH, CLAUDE_REVIEW_WORKFLOW_PATH)

    codeql_src = (REPO_ROOT / CODEQL_TEMPLATE_PATH).read_text(encoding="utf-8")
    langs = CODEQL_LANGUAGES_BY_PROFILE[profile]
    codeql_rendered = codeql_src.replace(
        LANGUAGES_PLACEHOLDER, render_languages_yaml(langs)
    )
    (root / CODEQL_WORKFLOW_PATH).write_text(codeql_rendered, encoding="utf-8")


def _expected_requireable_names(root: Path) -> list[str]:
    """The UNCONDITIONAL check names the deployed workflows declare, in
    KNOWN_WORKFLOWS order — independently reconstructed (skip `if:`-gated jobs,
    expand the rest) so this is a genuine cross-check of required_check_names."""
    names: list[str] = []
    for wf in ar.KNOWN_WORKFLOWS:
        path = root / ".github" / "workflows" / wf
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_id, job in (parsed.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            cond = job.get("if")
            if isinstance(cond, str) and cond.strip():
                continue  # conditional job — not a requireable check
            names.extend(ar._job_check_names(str(job_id), job))
    return names


@pytest.mark.parametrize("profile", sorted(CODEQL_LANGUAGES_BY_PROFILE))
def test_required_check_names_match_deployed_workflows(
    tmp_path: Path, profile: str
) -> None:
    _build_sample_repo(tmp_path, profile)

    derived = ar.required_check_names(tmp_path)
    expected = _expected_requireable_names(tmp_path)

    assert derived == expected, (
        f"profile {profile!r}: doc would list {derived!r} but the deployed "
        f"workflows declare {expected!r} — a mismatch means branch protection "
        f"silently never matches."
    )
    # The codeql + security + advisory checks must concretely appear.
    for lang in CODEQL_LANGUAGES_BY_PROFILE[profile]:
        assert f"Analyze ({lang})" in derived
    assert "Shipwright Security Scan" in derived
    assert "claude-review" in derived
    # CI is matrix-expanded over both OSes.
    assert any("ubuntu-latest" in n for n in derived)
    assert any("windows-latest" in n for n in derived)


def test_required_checks_exclude_if_gated_deploy_jobs(tmp_path: Path) -> None:
    """H1 regression: the supabase-nextjs CI template carries `if:`-gated
    deploy-dev / deploy-prod jobs that are SKIPPED on feature-branch PRs (they
    never report). They MUST NOT appear as requireable checks (requiring one
    blocks every PR), but they MUST be surfaced as conditional in the report."""
    _build_sample_repo(tmp_path, "supabase-nextjs")

    derived = ar.required_check_names(tmp_path)
    assert "deploy-dev" not in derived
    assert "deploy-prod" not in derived

    ci_report = next(
        r for r in ar.gather_required_checks(tmp_path) if r["workflow"] == "ci.yml"
    )
    conditional_names = {name for name, _cond in ci_report["conditional"]}
    assert {"deploy-dev", "deploy-prod"} <= conditional_names
    # `Tests (...)` jobs are unconditional → requireable.
    assert any(n.startswith("Tests (") for n in ci_report["checks"])


@pytest.mark.parametrize("profile", sorted(CODEQL_LANGUAGES_BY_PROFILE))
def test_render_automerge_setup_substitutes_everything(
    tmp_path: Path, profile: str
) -> None:
    _build_sample_repo(tmp_path, profile)

    doc = ar.render_automerge_setup(tmp_path, profile)

    # No placeholders left.
    assert ar.PROFILE_PLACEHOLDER not in doc
    assert ar.TABLE_PLACEHOLDER not in doc
    # Profile name + every derived check name appear in the rendered doc.
    assert profile in doc
    for name in ar.required_check_names(tmp_path):
        assert name in doc
    # The dormant trap + signing-omission guidance are present.
    assert "dormant" in doc.lower()
    assert "pull_request" in doc
    assert "signed commits" in doc.lower() or "required_signatures" in doc
    # CodeQL/CI/security are dormant; claude-review is active.
    assert "| dormant |" in doc
    assert "| active |" in doc


def test_render_warns_about_conditional_deploy_jobs(tmp_path: Path) -> None:
    """H1 render-level: the supabase-nextjs doc must surface deploy-dev/prod in
    the 'conditional — do NOT require' warning, NOT as requireable table rows."""
    _build_sample_repo(tmp_path, "supabase-nextjs")
    doc = ar.render_automerge_setup(tmp_path, "supabase-nextjs")

    assert "Conditional jobs" in doc
    assert "deploy-prod" in doc
    assert "deploy-dev" in doc
    # And the requireable table row for ci.yml must NOT advertise deploy-* as a
    # Required-Check candidate (they only live in the warning block).
    table_part = doc.split("Conditional jobs")[0]
    assert "deploy-prod" not in table_part


def test_render_handles_repo_with_no_workflows(tmp_path: Path) -> None:
    doc = ar.render_automerge_setup(tmp_path, "python-plugin-monorepo")
    assert ar.TABLE_PLACEHOLDER not in doc
    assert "no Shipwright workflows found" in doc
