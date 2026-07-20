"""`risk_detectors.is_ci_supplychain_change` — the diff-driven CI trust-boundary
predicate (iterate-2026-07-18-ci-supplychain-risk-flag, triage trg-9509c2e8).

Path semantics are pinned explicitly because the external review flagged them:
`.y(a)ml` is not glob alternation, `**` differs between fnmatch/pathlib, and a
DELETED workflow is the largest CI-boundary change there is.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "shipwright-iterate" / "scripts" / "lib"))

import risk_detectors as rd  # noqa: E402

TRIGGERS = [
    ".github/workflows/ci.yml",
    ".github/workflows/security.yaml",
    ".github/workflows/nested/deep.yml",
    ".github/dependabot.yml",
    ".github/dependabot.yaml",
    ".github/actions/diff-coverage-gate/action.yml",
    # Windows-style separators must normalize.
    ".github\\workflows\\ci.yml",
    # Shipped CI templates are the ADOPTERS' trust boundary: an edit here rewrites
    # every future adopted repo's CI, so it must trip the ack gate too (trg-6e8121e7).
    # The whole directory counts, across extensions (.yml.template, .toml.template).
    "shared/templates/github-actions/security.yml.template",
    "shared/templates/github-actions/codeql.yml.template",
    "shared/templates/github-actions/gitleaks.toml.template",
    "shared\\templates\\github-actions\\ci-vite-hono.yml.template",
]

NEAR_MISSES = [
    "docs/.github/workflows/x.yml",   # nested under another dir, not repo .github
    ".github/workflow/x.yml",          # singular dir - not the real one
    ".github/dependabot.json",         # wrong extension
    ".github/CODEOWNERS",              # .github but not the CI trust boundary
    "docs/shared/templates/github-actions/x.yml.template",  # not the repo-root shared dir
    "shared/templates/rules/migrations.md.template",         # shared/templates, not github-actions
    "src/app/page.tsx",
]


@pytest.mark.parametrize("path", TRIGGERS)
def test_ci_supplychain_paths_trigger(path):
    assert rd.is_ci_supplychain_change([path]) is True, path


@pytest.mark.parametrize("path", NEAR_MISSES)
def test_near_misses_do_not_trigger(path):
    assert rd.is_ci_supplychain_change([path]) is False, path


def test_empty_and_none_are_false():
    assert rd.is_ci_supplychain_change([]) is False
    assert rd.is_ci_supplychain_change(None) is False


def test_one_trigger_among_many_is_enough():
    assert rd.is_ci_supplychain_change(
        ["README.md", "src/x.py", ".github/workflows/ci.yml"]
    ) is True


def test_deleted_and_renamed_workflows_trigger():
    """A deleted security workflow is the biggest CI-boundary change there is.

    `git diff --name-only` lists deletions and both sides of a rename as plain
    paths, so the predicate must not depend on the file existing on disk.
    """
    assert rd.is_ci_supplychain_change([".github/workflows/deleted-security.yml"]) is True
    assert rd.is_ci_supplychain_change(
        [".github/workflows/old-name.yml", ".github/workflows/new-name.yml"]
    ) is True
