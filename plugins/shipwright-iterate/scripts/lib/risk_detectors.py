#!/usr/bin/env python3
"""Diff-driven risk detectors for the Shipwright iterate classifier.

Extracted from ``classify_complexity.py``
(iterate-2026-06-13-risk-detector-extract) so the classifier module stays
under the bloat limit. These are the *path-match* detectors a caller runs
over ``git diff --name-only`` output — distinct from the *message-keyword*
risk taxonomy (``RISK_TAXONOMY`` + ``detect_risk_flags``) which stays in
``classify_complexity``.

``classify_complexity`` re-exports every name below (so existing importers —
the ``shared.contracts.iterate`` cross-plugin contract, the test plugin's
boundary-coverage report, and the detector tests — keep resolving them from
their original home). New consumers may import from here directly.

Stable surface
--------------
* :func:`touches_build_files` / :data:`TOUCHES_BUILD_FILE_PATTERNS`
* :func:`is_io_boundary_change` / :data:`IO_BOUNDARY_FILE_PATTERNS`
* :func:`is_cross_component_change` / :data:`CROSS_COMPONENT_FILE_PATTERNS`
* :func:`is_ci_supplychain_change` / :data:`CI_SUPPLYCHAIN_FILE_PATTERNS`
"""

from __future__ import annotations

import re

# File-glob patterns for diff-driven touches_build detection (basename match).
TOUCHES_BUILD_FILE_PATTERNS = (
    "package.json", "package-lock.json", "yarn.lock",
    "pnpm-lock.yaml", "bun.lockb", "npm-shrinkwrap.json",
    "next.config.js", "next.config.ts", "next.config.mjs", "next.config.cjs",
    "vite.config.js", "vite.config.ts", "vite.config.mjs",
    "tailwind.config.js", "tailwind.config.ts",
    "webpack.config.js", "webpack.config.ts",
    "rollup.config.js", "rollup.config.ts", "rollup.config.mjs",
    "tsconfig.json",
)


def touches_build_files(changed_files: list[str]) -> bool:
    """Return True if any changed file matches a build-touching pattern.

    Diff-driven detection — caller passes `git diff --name-only` output.
    Match is by basename only (path-agnostic).
    """
    if not changed_files:
        return False
    for path in changed_files:
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        if name in TOUCHES_BUILD_FILE_PATTERNS:
            return True
    return False


# Regex patterns (anchored on basename) for diff-driven
# touches_io_boundary detection. Used by is_io_boundary_change() —
# producer/consumer round-trip bugs typically surface in these file
# shapes:
#   - .env / .env.local / .env.* — env-iterate motivating example
#   - hooks.json / settings.json — hook chain config
#   - <name>_config.json — shipwright_*_config.json family
#   - <name>_state.json — loop_state.json, external_review_state.json, ...
# The path-match path covers the producer/consumer-in-same-diff case for
# all known real-world examples. AST-pair detection (producer + consumer
# living in different .py files in the same diff) is explicitly deferred
# per Sub-Iterate A spec — file paths cover 90%+ of cases empirically.
IO_BOUNDARY_FILE_PATTERNS = (
    r"(^|/)\.env(\..+)?$",
    r"(^|/)hooks\.json$",
    r"(^|/)settings\.json$",
    r"(^|/)[^/]*_config\.json$",
    r"(^|/)[^/]*_state\.json$",
)


def is_io_boundary_change(changed_files: list[str] | None) -> bool:
    """Return True if any changed file matches an IO boundary pattern.

    Diff-driven detection — caller passes `git diff --name-only` output.
    Path normalization handles Windows backslashes.

    # DEFERRED — AST-pair detection (writer + reader living in different
    # .py files within the same diff) is intentionally NOT implemented.
    # See `.shipwright/planning/iterate/campaigns/iterate-skill-hardening/
    # sub-iterates/A-boundary-tests-foundation.md` Acceptance Criteria
    # line 53-60: the original AC text read this as required, but the
    # Implementation Plan allowed deferral. Per E spec HIGH-1, A's spec
    # was relabeled `(deferred)` with this rationale: path-match catches
    # every known real-world boundary bug (the env-iterate BOM + inline-
    # comment bugs both touched `.env` files in the diff), so the
    # additional complexity of AST-pair scanning is not justified
    # empirically. Reactivate when a real-world bug emerges that needs it.
    """
    if not changed_files:
        return False
    for path in changed_files:
        normalized = path.replace("\\", "/")
        for pattern in IO_BOUNDARY_FILE_PATTERNS:
            if re.search(pattern, normalized):
                return True
    return False


# Diff-driven cross_component detection (on normalized paths): the FRAMEWORK
# cross-component contracts whose behavior only emerges when the pieces interact
# (merge/churn/event-log resolver, hooks + hook fan-out, pipeline validators,
# campaign drain). SSoT; the F11 verifier keeps a drift-pinned copy (no
# cross-plugin import). Deliberately EXCLUDES the gate's own meta-tooling
# (classify_complexity / iterate_checks) — gating itself would be circular.
CROSS_COMPONENT_FILE_PATTERNS = (
    r"(^|/)(integrate_main|ensure_current|resolve_churn_conflicts)\.py$",
    r"(^|/)(churn_merge|gitattributes_union|gitattributes_selfheal)\.py$",
    r"(^|/)(autonomous_loop|events_log)\.py$",
    r"(^|/)campaign_[^/]*\.py$",
    r"(^|/)campaign-mode\.md$",
    r"(^|/)hooks\.json$",
    r"(^|/)hooks/.+\.py$",  # any hook script under a hooks/ dir (incl. scripts/hooks/ + nested)
    r"(^|/)(verify_phase|get_phase_context)\.py$",
)


def is_cross_component_change(changed_files: list[str] | None) -> bool:
    """Return True if any changed file is FRAMEWORK cross-component machinery
    (merge/churn/event-log resolver, hooks + hook fan-out, pipeline validators,
    campaign drain). Diff-driven — caller passes `git diff --name-only` output;
    path normalization handles Windows backslashes. Mirrors is_io_boundary_change."""
    if not changed_files:
        return False
    for path in changed_files:
        normalized = path.replace("\\", "/")
        for pattern in CROSS_COMPONENT_FILE_PATTERNS:
            if re.search(pattern, normalized):
                return True
    return False


# The CI trust boundary: the files that decide WHICH third-party code runs with
# repository credentials. Changing them fired zero risk flags before
# iterate-2026-07-18-ci-supplychain-risk-flag — proven twice live (webui #285 ran
# a full medium iterate with `risk_flags: []`, and its revert reproduced it).
# SSoT; the F11 verifier keeps a drift-pinned copy (no cross-plugin import, ADR-044).
#
# Anchored at `^` on purpose: paths come from `git diff --name-only` and are
# repo-relative, so `docs/.github/workflows/x.yml` is NOT this repo's CI boundary.
# INCLUDES shared/templates/github-actions/* — the shipped CI templates are the
# ADOPTERS' trust boundary, so an edit that rewrites what runs in every future
# adopted repo must be reasoned about too (trg-6e8121e7 closes the gap the hard
# test in iterate-2026-07-19-adopter-pinning-posture-rule deliberately left open).
CI_SUPPLYCHAIN_FILE_PATTERNS = (
    r"^\.github/workflows/.+\.ya?ml$",
    r"^\.github/dependabot\.ya?ml$",
    r"^\.github/actions/.+$",
    # Any hosted dependency-updater config, not just Dependabot: reintroducing the
    # posture under a different filename must not escape the gate.
    r"^\.github/renovate\.json5?$",
    r"^renovate\.json5?$",
    r"^\.renovaterc(\.json)?$",
    # Shipped CI templates — the adopters' trust boundary (not this repo's own
    # .github). Any file under the dir, across extensions (.yml.template,
    # .toml.template): editing one changes every future adopted repo's CI.
    r"^shared/templates/github-actions/.+$",
)


def _normalize_ci_path(path: str) -> str:
    """Repo-relative POSIX path. `git` quotes non-ASCII paths by default
    (core.quotePath), and a leading quote would defeat the `^` anchor."""
    norm = path.replace("\\", "/").strip()
    if len(norm) >= 2 and norm.startswith('"') and norm.endswith('"'):
        norm = norm[1:-1]
    return norm


def is_ci_supplychain_change(changed_files: list[str] | None) -> bool:
    """Return True if any changed file is part of the CI supply-chain trust
    boundary (workflows, the dependency-updater config, composite actions).

    Diff-driven — caller passes `git diff --name-only` output. Deletions and both
    sides of a rename appear there as plain paths, so this never touches the
    filesystem: a DELETED security workflow must trigger just like an edited one.
    Mirrors is_cross_component_change."""
    if not changed_files:
        return False
    for path in changed_files:
        normalized = _normalize_ci_path(path)
        for pattern in CI_SUPPLYCHAIN_FILE_PATTERNS:
            if re.search(pattern, normalized):
                return True
    return False
