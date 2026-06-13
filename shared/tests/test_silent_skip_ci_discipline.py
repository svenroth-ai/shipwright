"""Drift-protection for the centralized CI-discipline helpers.

Originally landed in PR #26 (ADR-044) to enforce that the inline
``_ci_truthy()`` copies agreed across the 4 affected test files. In
this iterate (ADR-045) the helpers moved to
``shared/scripts/test_hygiene.py``, so the assertions FLIP:

- **Forward (positive):** every affected file must
  `from test_hygiene import` the appropriate symbol(s).
- **Reverse (negative):** no affected file may carry the inline
  `def _ci_truthy(`, `def _import_or_fail_in_ci(`, or
  `def _skip_or_fail_on_missing_binary(` definition. The inline
  copies were the regression class; centralization makes their
  re-appearance the new regression.
- The pre-PR-#26 brittle-pattern rejection (``os.environ.get("CI") == "true"``)
  stays in place — still a regression class.

This test is the mechanical enforcement of ADR-045's "no double SSoT"
rule: once the lib lands, every consumer imports from it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Files that MUST import from `test_hygiene`. Keep this list in
# sync with AC-2 sites of iterate-2026-05-11-test-hygiene-helper-and-
# self-review-wiring.
AFFECTED_FILES: list[Path] = [
    REPO_ROOT / "shared" / "tests" / "test_setup_writes_canonical.py",
    REPO_ROOT / "shared" / "tests" / "test_path_helpers_template_vitest.py",
    REPO_ROOT / "shared" / "tests" / "test_hook_output_schema_compliance.py",
    # F40 (audit-3 WP11b): install-hook tests gate on bash via
    # test_hygiene.skip_or_fail_on_missing_binary (the old _has_bash() probe
    # crashed on a bash-less host instead of skipping, with no CI-fail branch).
    REPO_ROOT / "shared" / "tests" / "test_bloat_defense_artifacts.py",
    REPO_ROOT / "plugins" / "shipwright-security" / "tests" / "test_oss_backend_smoke.py",
]


# Canonical import: every affected file must have at least one
# `from test_hygiene import <symbol>` line. The module lives at
# `shared/scripts/test_hygiene.py` (top-level under shared/scripts/,
# NOT under shared/scripts/lib/) to avoid namespace collision with the
# plugin-local `lib/` packages — see ADR-045 § AC-2 / external-review
# code-reviewer finding (path-conflict in plugin pytest sessions).
_LIB_IMPORT_RE = re.compile(
    r"^from\s+test_hygiene\s+import\s+",
    flags=re.MULTILINE,
)

# REGRESSION shapes that MUST NOT appear in affected files anymore.
# Each pattern is the inline-helper-def that the lib supersedes.
_FORBIDDEN_DEFS: dict[str, re.Pattern[str]] = {
    "def _ci_truthy(": re.compile(r"^def\s+_ci_truthy\s*\(", re.MULTILINE),
    "def _import_or_fail_in_ci(": re.compile(
        r"^def\s+_import_or_fail_in_ci\s*\(", re.MULTILINE
    ),
    "def _skip_or_fail_on_missing_binary(": re.compile(
        r"^def\s+_skip_or_fail_on_missing_binary\s*\(", re.MULTILINE
    ),
}

# The pre-PR-#26 brittle exact-match check. Still a regression.
_BRITTLE_EXACT_MATCH_RE = re.compile(
    r'os\.environ\.get\(\s*["\']CI["\']\s*\)\s*==\s*["\']true["\']'
)


def _ci_truthy_reference(value: str | None) -> bool:
    """Reference implementation matching the lib's ``is_ci()``."""
    if value is None:
        return False
    return value.lower() in ("true", "1")


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("1", True),
        ("false", False),
        ("False", False),
        ("0", False),
        ("", False),
        ("yes", False),
        ("on", False),
        (None, False),
    ],
)
def test_ci_truthy_reference_branching(value: str | None, expected: bool) -> None:
    """Pin the canonical CI-truthy branching rule against an in-test reference
    implementation. ADR-044 + ADR-045: GitHub Actions exports CI=true, local
    utility scripts sometimes use CI=1 — both activate hard-fail. Everything
    else falls through to local-skip."""
    assert _ci_truthy_reference(value) is expected


@pytest.mark.parametrize("affected_file", AFFECTED_FILES)
def test_affected_file_imports_from_lib_test_hygiene(affected_file: Path) -> None:
    """Every affected file MUST `from test_hygiene import` at least one
    symbol. The inline-helper era ended with ADR-045 — centralization is
    enforced here.
    """
    if not affected_file.exists():
        pytest.fail(
            f"Expected CI-gated test file does not exist: {affected_file}. "
            f"ADR-045 AC-2 requires this file to import from "
            f"test_hygiene. If the file was intentionally removed, "
            f"update AFFECTED_FILES in this test."
        )

    text = affected_file.read_text(encoding="utf-8")
    assert _LIB_IMPORT_RE.search(text), (
        f"{affected_file} does not contain `from test_hygiene import ...`. "
        f"ADR-045 § AC-3 requires this canonical import form — the module "
        f"lives at `shared/scripts/test_hygiene.py` (top-level under "
        f"shared/scripts/, NOT under shared/scripts/lib/) to avoid the "
        f"plugin-local `lib/` namespace collision documented in the "
        f"code-review pass. If the file no longer needs the CI gate, "
        f"remove it from AFFECTED_FILES in this test."
    )


@pytest.mark.parametrize("affected_file", AFFECTED_FILES)
@pytest.mark.parametrize("forbidden_label", list(_FORBIDDEN_DEFS.keys()))
def test_affected_file_does_not_redefine_lib_helpers(
    affected_file: Path, forbidden_label: str
) -> None:
    """Affected files MUST NOT redefine `_ci_truthy`, `_import_or_fail_in_ci`,
    or `_skip_or_fail_on_missing_binary` locally. The lib version is
    canonical; an inline copy is the regression class.
    """
    if not affected_file.exists():
        # test-hygiene: allow-silent-skip — file-presence guard for parametrize;
        # not a CI-vs-local-binary condition.
        pytest.skip(f"file not present: {affected_file}")

    text = affected_file.read_text(encoding="utf-8")
    pattern = _FORBIDDEN_DEFS[forbidden_label]
    match = pattern.search(text)
    assert match is None, (
        f"{affected_file} re-defines `{forbidden_label}` inline. After "
        f"ADR-045 the lib (`shared/scripts/test_hygiene.py`) is the "
        f"single source of truth. Delete the inline def + import from the "
        f"lib instead. Match site: {match.group(0) if match else 'n/a'}"
    )


@pytest.mark.parametrize("affected_file", AFFECTED_FILES)
def test_affected_file_does_not_use_brittle_exact_match(affected_file: Path) -> None:
    """Reject the pre-PR-#26 brittle ``os.environ.get("CI") == "true"``
    exact-match pattern. ADR-044 external-review #O3 still applies — exact
    match rejects "True" and "1".
    """
    if not affected_file.exists():
        # test-hygiene: allow-silent-skip — file-presence guard for parametrize;
        # not a CI-vs-local-binary condition.
        pytest.skip(f"file not present: {affected_file}")

    text = affected_file.read_text(encoding="utf-8")
    match = _BRITTLE_EXACT_MATCH_RE.search(text)
    assert match is None, (
        f"{affected_file} uses the brittle exact-match CI check "
        f'(os.environ.get("CI") == "true") which rejects "True" and "1". '
        f"Use `is_ci()` from test_hygiene instead. "
        f"Match site: {match.group(0) if match else 'n/a'}"
    )


def test_ci_unset_means_local_skip_path() -> None:
    """When CI is unset entirely, the reference helper must return False
    (local-skip path). Belt-and-suspenders against env-clearing fixtures.
    """
    assert _ci_truthy_reference(os.environ.get("CI_UNSET_NEVER_DEFINED")) is False


def test_vitest_module_pattern_carries_both_ci_branches() -> None:
    """Pin the module-level pattern in test_path_helpers_template_vitest.py.

    Module-level `pytest.fail()` is undocumented but pytest converts it
    to a collection error (non-zero exit). Source-level pin: both
    branches must exist and use `is_ci()` for the guard.
    """
    vitest_test = REPO_ROOT / "shared" / "tests" / "test_path_helpers_template_vitest.py"
    text = vitest_test.read_text(encoding="utf-8")

    assert "pytest.fail(_msg" in text, (
        "Vitest module must contain a `pytest.fail(_msg...)` call at "
        "module level (the CI-mode hard-fail branch). ADR-044/045."
    )
    assert "pytest.skip(_msg" in text, (
        "Vitest module must contain a `pytest.skip(_msg...)` call at "
        "module level (the local-dev branch)."
    )
    assert "allow_module_level=True" in text, (
        "Module-level pytest.skip must use allow_module_level=True. "
        "Without it, the skip becomes a runtime error during collection."
    )
    # The guard must be `is_ci()` from the lib (not the brittle inline expr).
    assert "if is_ci():" in text, (
        "Vitest module must guard the CI fail branch with `is_ci()` from "
        "test_hygiene. Inline env-expression is the regression."
    )


def test_hook_schema_filenotfound_handler_is_ci_gated() -> None:
    """F41 (audit-3 WP11b): the per-hook-command FileNotFoundError handler in
    test_hook_output_schema_compliance.py must fail in CI, not silently skip.

    A misspelled interpreter in a registered hook command means Claude Code
    can't spawn it — the schema gate is silently absent. The function-scoped
    static probe whitewashes this site (the same function already carries the
    `uv` CI-gate), so pin it explicitly at the source level here.
    """
    hook_test = REPO_ROOT / "shared" / "tests" / "test_hook_output_schema_compliance.py"
    text = hook_test.read_text(encoding="utf-8")

    # Locate the FileNotFoundError handler and assert it is CI-gated before
    # the local-skip (the handler body spans a handful of lines).
    marker = "except FileNotFoundError as exc:"
    assert marker in text, (
        f"{hook_test.name} no longer has a `{marker}` handler — F41 guard is "
        f"looking at the wrong site; update this test."
    )
    handler = text.split(marker, 1)[1][:400]
    assert "if is_ci():" in handler and "pytest.fail(" in handler, (
        "The FileNotFoundError handler must hard-fail in CI (`if is_ci(): "
        "pytest.fail(...)`) before falling back to a local pytest.skip — a "
        "bare skip leaves a broken hook registration green in CI (ADR-044)."
    )
