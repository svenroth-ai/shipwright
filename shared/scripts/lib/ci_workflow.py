"""Convention lock for the GitHub Actions CI + Claude-Review workflows.

`/shipwright-adopt` scaffolds three different workflow files into adopted
target repos depending on profile:

1. `.github/workflows/ci.yml` — profile-specific (Vite-Hono, Supabase-Next.js,
   Python-Plugin-Monorepo). Chosen via `TEMPLATE_BY_PROFILE`.
2. `.github/workflows/claude-review.yml` — profile-agnostic Claude Code
   independent-reviewer workflow. Single template, no profile branching.

Both scaffolders read these constants directly. The drift test at
`shared/tests/test_ci_workflow_convention.py` pins every referenced
template path on disk and asserts each template carries the canonical
cross-platform matrix block + dormant-trigger contract.

Cross-platform matrix is the non-negotiable invariant. The webui v0.8.5
regression — four Windows-pathing tests silently failing on Linux runners
because adopt never landed a Windows job — drives this. Every CI template
must declare `os: [ubuntu-latest, windows-latest]` so test-portability
bugs surface at PR time, not at runtime in production-like deploy paths.

Profile-agnostic Claude-Review stays Linux-only by design: the
`claude-code-base-action` is platform-neutral and Linux runner minutes
are cheaper. Single-OS is correct for that workflow type.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Deployed-file paths in target repos
# ---------------------------------------------------------------------------

# Where the rendered CI workflow lives in a target repository.
WORKFLOW_PATH = ".github/workflows/ci.yml"

# Where the rendered Claude-Review workflow lives in a target repository.
CLAUDE_REVIEW_WORKFLOW_PATH = ".github/workflows/claude-review.yml"

# ---------------------------------------------------------------------------
# Template paths in the shipwright monorepo
# ---------------------------------------------------------------------------

# Profile-specific CI templates. Keys MUST match the profile names in
# `shared/profiles/*.json`. Values are repo-root-relative template paths.
#
# Adding a new profile: register here AND author the template file. The
# drift test asserts every value resolves to a file on disk; a stale entry
# fails the build before adopt can break on a missing template.
TEMPLATE_BY_PROFILE: dict[str, str] = {
    "supabase-nextjs": "shared/templates/github-actions/ci-supabase-nextjs.yml.template",
    "vite-hono": "shared/templates/github-actions/ci-vite-hono.yml.template",
    "python-plugin-monorepo": "shared/templates/github-actions/ci-python-plugin-monorepo.yml.template",
}

# Single profile-agnostic Claude-Review template.
CLAUDE_REVIEW_TEMPLATE_PATH = "shared/templates/github-actions/claude-review.yml.template"

# ---------------------------------------------------------------------------
# Convention-lock invariants
# ---------------------------------------------------------------------------

# Cross-platform matrix OS values. Every CI template's test/check job
# must declare exactly these (order matters for reproducibility — drift
# test compares as ordered list).
MATRIX_OS_VALUES: list[str] = ["ubuntu-latest", "windows-latest"]

# `fail-fast: false` is required: when the Windows runner discovers a
# portability bug after Ubuntu has already gone green, we want the
# Ubuntu result preserved so the diff between OSes is visible in the
# run summary. fail-fast would cancel the Ubuntu run too.
MATRIX_FAIL_FAST: bool = False


def template_path_for_profile(profile_name: str) -> str | None:
    """Return the repo-root-relative template path for a profile, or None.

    The scaffolder uses None to short-circuit with a graceful "no template
    for this profile" result instead of raising. New profile? Register in
    `TEMPLATE_BY_PROFILE` above.
    """
    return TEMPLATE_BY_PROFILE.get(profile_name)
