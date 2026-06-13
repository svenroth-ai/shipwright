"""Drift test pinning the CodeQL workflow template to its convention lock.

The convention lock at ``shared/scripts/lib/codeql_workflow.py`` is consumed by:

- ``codeql_workflow_scaffolder.py`` — renders the language matrix per profile
  and writes the template into target repos at ``CODEQL_WORKFLOW_PATH``.
- ``automerge_readiness.py`` — derives the ``Analyze (<lang>)`` Required-Check
  names for the AUTOMERGE_SETUP.md doc.

Without this test the constants module is a lie: the template could lose its
dormant-trigger contract, drop the `continue-on-error` private-repo guard, lose
the `security-events: write` permission, or rename the placeholder the
scaffolder substitutes — and nobody would notice until an adopted repo hit the
gap in production CI (or, worse, a Required Check that never reports silently
blocked every PR).

Failure modes deliberately covered:

1. Template path declared but file missing on disk.
2. Runtime triggers (`pull_request`, `push`, `schedule`) ACTIVE — must be absent
   from parsed YAML so adopted repos don't auto-fire before Phase-B activation.
   (PyYAML cannot distinguish "commented" from "absent" — we require absent.)
3. Explicit `permissions:` floor missing.
4. `continue-on-error` dropped from the analyze step (the private-repo / no-GHAS
   green-job guard).
5. The `${SHIPWRIGHT_CODEQL_LANGUAGES}` placeholder renamed / removed (would
   silently break the scaffolder's substitution).
6. A profile registered for CodeQL languages that is NOT a real CI profile.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")  # PyYAML — root + adopt + compliance deps

from lib.ci_workflow import TEMPLATE_BY_PROFILE  # noqa: E402
from lib.codeql_workflow import (  # noqa: E402
    ANALYZE_JOB_NAME,
    CODEQL_LANGUAGES_BY_PROFILE,
    CODEQL_TEMPLATE_PATH,
    CODEQL_WORKFLOW_PATH,
    LANGUAGES_PLACEHOLDER,
    REQUIRED_PERMISSIONS,
    languages_for_profile,
    render_languages_yaml,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _raw() -> str:
    return (REPO_ROOT / CODEQL_TEMPLATE_PATH).read_text(encoding="utf-8")


def _parsed() -> dict:
    return yaml.safe_load(_raw())


# ---------------------------------------------------------------------------
# Path-constant sanity + template resolves
# ---------------------------------------------------------------------------


def test_workflow_path_under_dot_github() -> None:
    assert CODEQL_WORKFLOW_PATH.startswith(".github/workflows/")
    assert CODEQL_WORKFLOW_PATH.endswith(".yml")


def test_template_exists() -> None:
    template = REPO_ROOT / CODEQL_TEMPLATE_PATH
    assert template.exists(), (
        f"CodeQL template at {template} declared in CODEQL_TEMPLATE_PATH but "
        f"does not exist on disk."
    )


# ---------------------------------------------------------------------------
# Dormant-trigger contract
# ---------------------------------------------------------------------------


def test_workflow_dispatch_active() -> None:
    parsed = _parsed()
    # PyYAML quirk: bare `on:` parses as Python literal True (YAML 1.1 truthy).
    triggers = parsed.get("on") or parsed.get(True) or {}
    assert isinstance(triggers, dict), (
        f"`on:` block is not a mapping (got {type(triggers).__name__})."
    )
    assert "workflow_dispatch" in triggers, (
        "workflow_dispatch trigger missing — operator has no manual handle to "
        "fire the workflow before activating auto-triggers."
    )


@pytest.mark.parametrize("trigger", ["pull_request", "push", "schedule"])
def test_no_active_auto_trigger(trigger: str) -> None:
    triggers = _parsed().get("on") or _parsed().get(True) or {}
    if isinstance(triggers, dict):
        assert trigger not in triggers, (
            f"CodeQL template: {trigger} trigger is ACTIVE — adopted repos "
            f"would auto-fire before Phase-B activation. It must be absent from "
            f"parsed YAML (header comments are fine — uncomment after review)."
        )


# ---------------------------------------------------------------------------
# Permissions floor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key,value", list(REQUIRED_PERMISSIONS.items()))
def test_explicit_permissions_floor(key: str, value: str) -> None:
    permissions = _parsed().get("permissions")
    assert isinstance(permissions, dict), (
        "CodeQL template: top-level `permissions:` block missing or not a "
        "mapping — implicit token permissions are org-policy-dependent."
    )
    assert permissions.get(key) == value, (
        f"CodeQL template: permissions.{key} != {value!r} "
        f"(got {permissions.get(key)!r}). Required by codeql-action."
    )


# ---------------------------------------------------------------------------
# Analyze job shape: name, matrix placeholder, continue-on-error
# ---------------------------------------------------------------------------


def test_analyze_job_name() -> None:
    job = (_parsed().get("jobs") or {}).get("analyze") or {}
    assert job.get("name") == ANALYZE_JOB_NAME, (
        f"analyze job name={job.get('name')!r}, expected {ANALYZE_JOB_NAME!r} — "
        f"the check name `Analyze (<lang>)` is what the AUTOMERGE_SETUP doc and "
        f"branch protection match on."
    )


def test_matrix_language_is_placeholder() -> None:
    job = (_parsed().get("jobs") or {}).get("analyze") or {}
    matrix = (job.get("strategy") or {}).get("matrix") or {}
    assert matrix.get("language") == LANGUAGES_PLACEHOLDER, (
        f"analyze matrix.language={matrix.get('language')!r}, expected the "
        f"placeholder {LANGUAGES_PLACEHOLDER!r} that the scaffolder substitutes."
    )


def test_matrix_fail_fast_off() -> None:
    job = (_parsed().get("jobs") or {}).get("analyze") or {}
    strategy = job.get("strategy") or {}
    assert strategy.get("fail-fast") is False, (
        "analyze strategy.fail-fast must be false so one language's failure "
        "does not cancel the others' results."
    )


def test_analyze_step_continue_on_error() -> None:
    """The analyze step must carry continue-on-error so the job stays green on
    a private repo without GHAS (the SARIF upload fails there)."""
    job = (_parsed().get("jobs") or {}).get("analyze") or {}
    steps = job.get("steps") or []
    analyze_steps = [
        s for s in steps
        if isinstance(s, dict)
        and isinstance(s.get("uses"), str)
        and s["uses"].startswith("github/codeql-action/analyze")
    ]
    assert analyze_steps, "no github/codeql-action/analyze step found in template."
    for s in analyze_steps:
        assert s.get("continue-on-error") is True, (
            "github/codeql-action/analyze step must set continue-on-error: true "
            "so a private repo without GitHub Advanced Security keeps a green "
            "`Analyze (<lang>)` Required Check."
        )


def test_raw_template_carries_placeholder_literal() -> None:
    # Guards against a YAML round-trip that quotes/mangles the token.
    assert LANGUAGES_PLACEHOLDER in _raw()


# ---------------------------------------------------------------------------
# Language SSoT
# ---------------------------------------------------------------------------


def test_codeql_profiles_are_real_ci_profiles() -> None:
    """Every profile we render CodeQL for must be a real CI profile, else the
    automerge-readiness doc would list a profile adopt never scaffolds CI for."""
    unknown = set(CODEQL_LANGUAGES_BY_PROFILE) - set(TEMPLATE_BY_PROFILE)
    assert not unknown, (
        f"CODEQL_LANGUAGES_BY_PROFILE has profiles absent from "
        f"ci_workflow.TEMPLATE_BY_PROFILE: {sorted(unknown)!r}"
    )


@pytest.mark.parametrize(
    "profile,expected",
    list(CODEQL_LANGUAGES_BY_PROFILE.items()),
)
def test_languages_for_profile(profile: str, expected: list[str]) -> None:
    assert languages_for_profile(profile) == expected
    assert languages_for_profile(f"  {profile}  ") == expected  # whitespace-tolerant


def test_languages_for_profile_unmapped() -> None:
    assert languages_for_profile(None) is None
    assert languages_for_profile("totally-unknown-profile") is None


def test_render_languages_yaml() -> None:
    assert render_languages_yaml(["python"]) == "[python]"
    assert (
        render_languages_yaml(["python", "javascript-typescript"])
        == "[python, javascript-typescript]"
    )
    with pytest.raises(ValueError):
        render_languages_yaml([])


@pytest.mark.parametrize("profile", list(CODEQL_LANGUAGES_BY_PROFILE))
def test_rendered_template_is_valid_yaml(profile: str) -> None:
    """Substituting the placeholder for a profile's languages must yield a
    parseable matrix.language list — the scaffolder's exact operation."""
    langs = CODEQL_LANGUAGES_BY_PROFILE[profile]
    rendered = _raw().replace(LANGUAGES_PLACEHOLDER, render_languages_yaml(langs))
    parsed = yaml.safe_load(rendered)
    matrix = parsed["jobs"]["analyze"]["strategy"]["matrix"]
    assert matrix["language"] == langs
