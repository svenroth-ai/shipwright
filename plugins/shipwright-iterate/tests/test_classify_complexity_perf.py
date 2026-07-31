"""Tests for the touches_build risk-flag (Iterate I3 / T3 hook).

Verifies that performance-relevant changes — dependencies, build configs —
trigger the touches_build flag, while ordinary source changes don't.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "scripts" / "lib"),
)

from classify_complexity import (  # noqa: E402
    RISK_TAXONOMY,
    TOUCHES_BUILD_BASENAME_GLOBS,
    TOUCHES_BUILD_FILE_PATTERNS,
    detect_risk_flags,
    touches_build_files,
)


# ── Taxonomy registration ───────────────────────────────────────────────────

def test_touches_build_in_taxonomy():
    assert "touches_build" in RISK_TAXONOMY
    flag = RISK_TAXONOMY["touches_build"]
    assert flag["min_complexity"] == "small"
    assert "performance_test_layer" in flag["enforces"]


# ── Prompt-keyword detection ────────────────────────────────────────────────

def test_keyword_package_json_fires_flag():
    flags = detect_risk_flags("Update dependencies in package.json")
    flag_names = [f["flag"] for f in flags]
    assert "touches_build" in flag_names


def test_keyword_next_config_fires_flag():
    flags = detect_risk_flags("Tweak next.config.ts to enable standalone output")
    assert "touches_build" in [f["flag"] for f in flags]


def test_keyword_vite_config_fires_flag():
    flags = detect_risk_flags("Add proxy config to vite.config.ts")
    assert "touches_build" in [f["flag"] for f in flags]


def test_keyword_pnpm_lockfile_fires_flag():
    flags = detect_risk_flags("Refresh pnpm-lock.yaml after security update")
    assert "touches_build" in [f["flag"] for f in flags]


def test_keyword_unrelated_does_not_fire_flag():
    flags = detect_risk_flags("Rename a button label in src/components/Header.tsx")
    assert "touches_build" not in [f["flag"] for f in flags]


# ── Diff-driven file-glob detection ─────────────────────────────────────────

def test_touches_build_files_detects_package_json():
    assert touches_build_files(["src/foo.tsx", "package.json"]) is True


def test_touches_build_files_detects_lockfile_with_path_prefix():
    assert touches_build_files(["webui/client/package-lock.json"]) is True


def test_touches_build_files_detects_next_config_variants():
    for variant in ["next.config.js", "next.config.ts",
                    "next.config.mjs", "next.config.cjs"]:
        assert touches_build_files([variant]) is True, f"failed for {variant}"


def test_touches_build_files_detects_tsconfig():
    assert touches_build_files(["packages/shared/tsconfig.json"]) is True


def test_touches_build_files_returns_false_on_src_only():
    assert touches_build_files([
        "src/components/Header.tsx",
        "src/lib/util.ts",
        "tests/unit/util.test.ts",
    ]) is False


def test_touches_build_files_returns_false_on_empty():
    assert touches_build_files([]) is False


def test_touches_build_files_handles_windows_separators():
    assert touches_build_files(["webui\\client\\package.json"]) is True


def test_touches_build_files_does_not_match_partial_basename():
    """`my-package.json` should NOT trigger — exact basename match required."""
    assert touches_build_files(["my-package.json"]) is False


# ── Coverage of all documented file patterns ────────────────────────────────

def test_all_documented_patterns_are_detected():
    """Every entry in TOUCHES_BUILD_FILE_PATTERNS should fire from a synthetic diff."""
    for pat in TOUCHES_BUILD_FILE_PATTERNS:
        assert touches_build_files([f"some/path/{pat}"]) is True, (
            f"pattern {pat} declared but not detected"
        )


def test_all_documented_globs_are_detected():
    """Every entry in TOUCHES_BUILD_BASENAME_GLOBS fires from a synthetic diff.

    The glob tuple is matched with fnmatch, so a literal instance is built by
    substituting the wildcard — `requirements*.txt` → `requirements-dev.txt`.
    """
    for glob in TOUCHES_BUILD_BASENAME_GLOBS:
        instance = glob.replace("*", "-dev")
        # Reject EVERY fnmatch metacharacter, not just `*`: a future glob using
        # `?` or `[seq]` would survive a `*`-only guard, then be probed as a
        # literal path still containing the wildcard — and fnmatch would match
        # it against itself, passing without ever proving the glob fires on a
        # real filename.
        assert not set(instance) & set("*?["), (
            f"glob {glob} has no single-* shape this test can instantiate"
        )
        assert touches_build_files([f"some/path/{instance}"]) is True, (
            f"glob {glob} declared but {instance} not detected"
        )


# ── Python build inputs (trg-496e63a7) ──────────────────────────────────────
#
# The detector listed JS build inputs only, so in this Python monorepo a
# dependency change raised no risk flag at all. Both surfaces are covered:
# the diff-driven detector here, the message-keyword surface below.

PYTHON_BUILD_INPUTS = (
    "uv.lock", "poetry.lock", "Pipfile", "Pipfile.lock",
    "pyproject.toml", "setup.py", "setup.cfg",
)


@pytest.mark.parametrize("name", PYTHON_BUILD_INPUTS)
def test_touches_build_files_detects_python_build_inputs(name):
    assert touches_build_files([name]) is True


@pytest.mark.parametrize("name", PYTHON_BUILD_INPUTS)
def test_python_build_inputs_detected_at_any_path_depth(name):
    assert touches_build_files([f"plugins/shipwright-plan/{name}"]) is True
    assert touches_build_files([f"plugins\\shipwright-plan\\{name}"]) is True


@pytest.mark.parametrize("name", [
    "requirements.txt", "requirements-dev.txt", "requirements_prod.txt",
])
def test_touches_build_files_detects_requirements_family(name):
    assert touches_build_files([f"deploy/{name}"]) is True
    # The glob branch needs the same path-shape coverage as the literal half,
    # else a regression moving the glob check above the separator
    # normalization would go unnoticed.
    assert touches_build_files(["deploy\\pinned\\" + name]) is True


@pytest.mark.parametrize("name", ["uv.lock", "requirements-dev.txt"])
def test_git_quoted_non_ascii_path_still_fires(name):
    """git core.quotePath wraps non-ASCII paths; the quote must not survive
    into the basename, or the detector silently stays down.

    The octal escapes here are LITERAL backslash-digit text — that is exactly
    what `git diff --name-only` prints for a non-ASCII path, so the raw string
    is load-bearing: writing it unraw would embed the decoded character and
    test a path git never emits.
    """
    quoted = r'"tools/tempf\303\266rderung/' + name + '"'
    assert "\\303" in quoted, "the escape must stay literal, not be decoded"
    assert touches_build_files([quoted]) is True


@pytest.mark.parametrize("name", [
    # The glob anchors the WHOLE basename, so a prefixed or suffixed name is
    # not a build input — same contract as `my-package.json` above.
    "my-requirements.txt", "requirements.txt.bak", "requirements.md",
    "requirements/base.txt",
])
def test_requirements_glob_does_not_over_match(name):
    assert touches_build_files([name]) is False


@pytest.mark.parametrize("name", [
    "REQUIREMENTS.TXT", "Requirements.txt", "UV.LOCK", "PyProject.toml",
])
def test_build_input_matching_is_case_sensitive_on_every_platform(name):
    """The glob half uses fnmatchCASE, so the verdict cannot depend on the OS.

    Plain `fnmatch` calls `os.path.normcase`, which lowercases on Windows and
    is a no-op on POSIX — so `REQUIREMENTS.TXT` would raise touches_build on a
    Windows dev machine and not in CI (which has no Windows job at all, see
    trg-80e3b3cd). A risk gate whose verdict depends on the developer's
    operating system is a defect; the exact-basename half is case-sensitive
    already, and this pins the glob half to the same rule.
    """
    assert touches_build_files([f"some/path/{name}"]) is False


def test_python_source_alone_does_not_touch_build():
    assert touches_build_files([
        "plugins/shipwright-iterate/scripts/lib/risk_detectors.py",
        "shared/scripts/tools/triage_gc.py",
    ]) is False


# ── Message-keyword surface (what actually fires at SKILL.md Step E) ─────────
#
# detect_risk_flags matches RISK_TAXONOMY patterns against the MESSAGE, not the
# diff. Widening only the file patterns would leave this surface blind.

@pytest.mark.parametrize("message", [
    "bump the pinned version in uv.lock",
    "regenerate poetry.lock after the dependency bump",
    "update Pipfile.lock for the new runtime",
    "add a dependency to pyproject.toml",
    "move the package metadata out of setup.py",
    "drop the stale section from setup.cfg",
    "pin the transitive dep in requirements.txt",
    "split requirements-dev.txt from the runtime deps",
    "regenerate requirements_prod.txt after the pin",
])
def test_python_build_inputs_fire_touches_build_from_message(message):
    flags = [f["flag"] for f in detect_risk_flags(message)]
    assert "touches_build" in flags


@pytest.mark.parametrize("message", [
    # A longer token that merely CONTAINS a build-input name is not one. The
    # message surface must match a whole filename, exactly as the diff surface
    # does — `my-requirements.txt` is False there (see
    # test_requirements_glob_does_not_over_match), so it must be False here.
    # External review 2026-07-31 (openai, `revise`): a bare `\b` guard let all
    # of these through, because `.` is a non-word char and satisfies `\b`.
    "rewrite the setup.python bootstrap helper",
    "document the uv.lockfiles layout in the guide",
    "restore my-requirements.txt from the backup",
    "delete requirements.txt.bak",
    "restore uv.lock.bak after the failed sync",
    "remove setup.py.bak and pyproject.toml.orig",
    "drop the stale vendor-poetry.lock copy",
])
def test_a_longer_token_containing_a_build_input_does_not_fire(message):
    flags = [f["flag"] for f in detect_risk_flags(message)]
    assert "touches_build" not in flags


@pytest.mark.parametrize("message", [
    # FALSE-POSITIVE GUARD — this is an IREB requirements-engineering
    # framework. A bare `requirements` pattern would fire touches_build on
    # ordinary prose about requirement catalogues, so the pattern demands a
    # `.txt` filename.
    "update the requirements catalog for FR-01.02",
    "the requirements are decomposed into planning splits",
    "add acceptance criteria to the elicited requirements",
    "rewrite the page header text",
])
def test_requirements_prose_does_not_fire_touches_build(message):
    flags = [f["flag"] for f in detect_risk_flags(message)]
    assert "touches_build" not in flags
