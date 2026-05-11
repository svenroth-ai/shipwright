"""Unit-level verifier for the CI-gate convention.

Pins the ``_ci_truthy()`` helper signature + branching rules used at all
sites that convert a silent skip to a hard CI failure (AC-2 + AC-3 of
iterate-2026-05-11-test-hygiene-and-skill-rules).

The helper is duplicated inline at each affected test file (AC-6
deferred). This test asserts the duplicate copies agree on which env
values activate the CI branch — drift-protection without a shared lib.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Files that MUST carry the `_ci_truthy()` helper. Keep this list in
# sync with the build sites of AC-2 + AC-3. When AC-6 lands and the
# helper moves to shared/scripts/lib/, this test is the first thing
# to update.
AFFECTED_FILES: list[Path] = [
    REPO_ROOT / "shared" / "tests" / "test_setup_writes_canonical.py",
    REPO_ROOT / "shared" / "tests" / "test_path_helpers_template_vitest.py",
    REPO_ROOT / "shared" / "tests" / "test_hook_output_schema_compliance.py",
    REPO_ROOT / "plugins" / "shipwright-security" / "tests" / "test_oss_backend_smoke.py",
]


# The canonical body of `_ci_truthy()` — accepts "true", "1", "True",
# "TRUE", "1" but rejects "false", "0", "", None. Each file must
# define a function with this exact body (whitespace-tolerant).
_CANONICAL_TRUTHY_RE = re.compile(
    r'os\.environ\.get\(\s*["\']CI["\']\s*,\s*["\']["\']\s*\)\.lower\(\)\s*'
    r'in\s*\(\s*["\']true["\']\s*,\s*["\']1["\']\s*\)',
)

# Also require a `def _ci_truthy(` definition somewhere in the file — the
# regex above matches the expression alone, but a regression that inlines
# the expression at every call site (no helper function) would still
# pass the expression check. Anchor on the helper name so the AC-6
# migration (centralize helper) is mechanically driven by this test.
_HELPER_DEF_RE = re.compile(r"^def\s+_ci_truthy\s*\(", flags=re.MULTILINE)


def _ci_truthy_reference(value: str | None) -> bool:
    """Reference implementation matching the canonical helper."""
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
    """Pin the canonical CI-truthy branching rule.

    Standardized across all sites per external-review #O3 + #G4.
    GitHub Actions exports CI=true; local utility scripts sometimes use
    CI=1. Both must activate the hard-fail branch; everything else falls
    through to local-skip behavior.
    """
    assert _ci_truthy_reference(value) is expected


@pytest.mark.parametrize("affected_file", AFFECTED_FILES)
def test_affected_file_carries_canonical_ci_check(affected_file: Path) -> None:
    """Every CI-gated test file uses the canonical ``CI`` env-check pattern.

    Drift-protection: if a file regresses to the brittle
    ``os.environ.get("CI") == "true"`` form (exact match), this test
    fails and surfaces the divergence. The regex matches the
    normalized form: ``.get("CI", "").lower() in ("true", "1")``.
    """
    if not affected_file.exists():
        pytest.fail(
            f"Expected CI-gated test file does not exist: {affected_file}. "
            f"AC-2/AC-3 of iterate-2026-05-11-test-hygiene-and-skill-rules "
            f"requires this file to carry the CI gate. If the file was "
            f"intentionally removed, also update AFFECTED_FILES in this test."
        )

    text = affected_file.read_text(encoding="utf-8")
    assert _CANONICAL_TRUTHY_RE.search(text), (
        f"{affected_file} does not contain the canonical CI-truthy check "
        f"pattern. Expected to find a match for "
        f'os.environ.get("CI", "").lower() in ("true", "1"). '
        f"Update the file or, when AC-6 lands and the helper centralizes, "
        f"update this drift test."
    )
    assert _HELPER_DEF_RE.search(text), (
        f"{affected_file} contains the canonical CI-truthy EXPRESSION but "
        f"no `def _ci_truthy(` definition. Inlining the expression at "
        f"every call site is a regression — keep the helper function so "
        f"the AC-6 migration can mechanically rewrite to a shared import."
    )


@pytest.mark.parametrize("affected_file", AFFECTED_FILES)
def test_affected_file_does_not_use_brittle_exact_match(affected_file: Path) -> None:
    """Reject the pre-iterate ``os.environ.get("CI") == "true"`` pattern.

    External-review #O3: exact-match is brittle (rejects "True", "1").
    All sites must use the case-normalized form.
    """
    if not affected_file.exists():
        pytest.skip(f"file not present (will fail in completeness test): {affected_file}")

    text = affected_file.read_text(encoding="utf-8")
    # The exact-equal form is forbidden. Use a precise pattern so we
    # don't false-match the canonical form's substring.
    brittle = re.compile(
        r'os\.environ\.get\(\s*["\']CI["\']\s*\)\s*==\s*["\']true["\']'
    )
    match = brittle.search(text)
    assert match is None, (
        f"{affected_file} uses the brittle exact-match CI check "
        f'(os.environ.get("CI") == "true") which rejects "True" and "1". '
        f"Switch to the normalized form: "
        f'os.environ.get("CI", "").lower() in ("true", "1"). '
        f"Match site: {match.group(0) if match else 'n/a'}"
    )


def test_ci_unset_means_local_skip_path() -> None:
    """When CI is unset entirely, the helper must return False (local-skip).

    Belt-and-suspenders: even if the env var was cleared by a fixture
    or wrapper script, the CI-gate must default to permissive.
    """
    assert _ci_truthy_reference(os.environ.get("CI_UNSET_NEVER_DEFINED")) is False


def test_vitest_module_pattern_carries_both_ci_branches() -> None:
    """Pin the module-level pattern in test_path_helpers_template_vitest.py.

    Module-level `pytest.fail()` is undocumented but pytest converts it
    to a collection error (non-zero exit). The risk is that a future
    pytest major changes this behavior. We can't easily exercise the
    CI=true branch live without a subprocess + monkeypatched PATH, but
    we can pin the SOURCE — both branches must be present and the
    canonical CI-truthy expression must guard them.

    External-review finding (code-review pass): the contract that
    'module-level fail produces non-zero exit' isn't pinned by any
    runtime test, so pin it at the source level instead.
    """
    vitest_test = REPO_ROOT / "shared" / "tests" / "test_path_helpers_template_vitest.py"
    text = vitest_test.read_text(encoding="utf-8")

    # The module must contain both a pytest.fail and a pytest.skip path,
    # guarded by _ci_truthy(). Substring checks are sufficient here:
    # the canonical-truthy regex already covers the expression shape.
    assert "pytest.fail(_msg" in text, (
        f"Vitest module must contain a `pytest.fail(_msg...)` call at "
        f"module level (the CI-mode hard-fail branch). "
        f"AC-3 of iterate-2026-05-11-test-hygiene-and-skill-rules."
    )
    assert "pytest.skip(_msg" in text, (
        f"Vitest module must contain a `pytest.skip(_msg...)` call at "
        f"module level (the local-dev branch)."
    )
    assert "allow_module_level=True" in text, (
        f"Module-level pytest.skip must use allow_module_level=True. "
        f"Without it, the skip becomes a runtime error during collection."
    )
