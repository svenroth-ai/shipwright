"""Tests for shared/scripts/tools/grill_trace_fr_coverage.py — the
FR-row <-> grill-trace ``requirement_key`` join (external plan review,
P4.2), which closes the "partially recorded interview" gap the plain
``grill_trace_coverage`` guard cannot see.
"""

from __future__ import annotations

from tools.grill_trace_fr_coverage import check_fr_trace_coverage, extract_fr_names, slugify
from tools.verifiers.common import Severity


def test_slugify_lower_kebab_cases_a_capability_name():
    assert slugify("User Login") == "user-login"
    assert slugify("  Login Rate Limiting!  ") == "login-rate-limiting"
    assert slugify("Multi--Word___Name") == "multi-word-name"


_SPEC_MD = """# Authentication

## 2. Functional Requirements

| ID | Area | Name | Priority | Description | Basis | Layers |
|---|---|---|---|---|---|---|
| FR-01.01 | Authentication | User login | Must | The system SHALL authenticate users. | interview | unit |
| FR-01.02 | Authentication | Password reset | Must | The system SHALL support password reset. | interview | unit |

### Removed Requirements

| ID | Requirement | Priority | Removed by | status |
|----|-------------|----------|------------|--------|
| FR-01.00 | Old capability | Should | iterate-x | status: deprecated |
"""


def test_extract_fr_names_reads_live_rows_only():
    names = extract_fr_names(_SPEC_MD)
    assert names == {"FR-01.01": "User login", "FR-01.02": "Password reset"}


def test_extract_fr_names_excludes_removed_requirements_rows():
    names = extract_fr_names(_SPEC_MD)
    assert "FR-01.00" not in names


def test_check_fr_trace_coverage_skips_when_no_spec_md_exists():
    result = check_fr_trace_coverage([], trace_keys=set())
    assert result.is_skipped


def test_check_fr_trace_coverage_skips_when_specs_have_no_fr_rows(tmp_path):
    spec = tmp_path / "01-x" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# Empty\n\nNo table here.\n", encoding="utf-8")

    result = check_fr_trace_coverage([spec], trace_keys=set())

    assert result.is_skipped


def test_check_fr_trace_coverage_fails_when_an_fr_has_no_matching_trace(tmp_path):
    spec = tmp_path / "01-auth" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(_SPEC_MD, encoding="utf-8")

    result = check_fr_trace_coverage([spec], trace_keys={"user-login"})

    assert result.ok is False
    assert "FR-01.02" in result.detail


def test_check_fr_trace_coverage_failure_is_warning_not_error(tmp_path):
    """PR #705 Tier-3 review finding: the Name-cell-slug <-> requirement_key
    join has no stable identity contract (a rename, a punctuation/Unicode
    difference, or two Names colliding on one slug all produce a false
    'missing' here) — so a mismatch must surface as a non-blocking WARNING,
    not the CheckResult default ERROR, which would hard-block Step 8 for a
    project that did the elicitation work correctly. This is the one
    deliberate exception among the grill-trace structural guards; the four
    closed-vocabulary STOPs and grill_trace_coverage stay ERROR."""
    spec = tmp_path / "01-auth" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(_SPEC_MD, encoding="utf-8")

    result = check_fr_trace_coverage([spec], trace_keys={"user-login"})

    assert result.ok is False
    assert result.severity == Severity.WARNING.value
    # `is_failure` alone doesn't gate blocking (it's true for both ERROR and
    # WARNING failures — see CheckResult.is_failure); every ERROR-only gate
    # boundary in this codebase additionally checks `severity == ERROR`
    # (verify_grill_trace_completeness.main, phase_validators._run_canon_checks),
    # so WARNING severity is what actually keeps this from hard-blocking.
    assert result.is_failure is True


def test_check_fr_trace_coverage_passes_when_every_fr_has_a_matching_trace(tmp_path):
    spec = tmp_path / "01-auth" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(_SPEC_MD, encoding="utf-8")

    result = check_fr_trace_coverage([spec], trace_keys={"user-login", "password-reset"})

    assert result.ok is True


def test_check_fr_trace_coverage_joins_across_multiple_spec_files(tmp_path):
    spec_a = tmp_path / "01-auth" / "spec.md"
    spec_a.parent.mkdir(parents=True)
    spec_a.write_text(_SPEC_MD, encoding="utf-8")
    spec_b = tmp_path / "02-billing" / "spec.md"
    spec_b.parent.mkdir(parents=True)
    spec_b.write_text(
        "## 2. Functional Requirements\n\n"
        "| ID | Area | Name | Priority | Description | Basis | Layers |\n"
        "|---|---|---|---|---|---|---|\n"
        "| FR-02.01 | Billing | Invoice export | Must | The system SHALL export invoices. | interview | unit |\n",
        encoding="utf-8",
    )

    result = check_fr_trace_coverage(
        [spec_a, spec_b],
        trace_keys={"user-login", "password-reset"},
    )

    assert result.ok is False
    assert "FR-02.01" in result.detail
    assert "FR-01.01" not in result.detail
    assert "FR-01.02" not in result.detail
