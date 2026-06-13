"""Convention lock for the GitHub Actions CodeQL workflow.

`/shipwright-adopt` scaffolds `.github/workflows/codeql.yml` into adopted
target repos so a brownfield repo can offer the `Analyze (<language>)`
Required-Check job names that B4.5-style automerge branch-protection needs
(alongside `ci.yml`, `security.yml`, `claude-review.yml`).

Unlike the profile-specific CI templates, CodeQL needs ONE template whose
`language:` matrix is parametrized at scaffold time from the detected stack
profile (Python repo → `[python]`, a JS/TS repo → `[javascript-typescript]`,
a mixed repo → both). The template carries a `${SHIPWRIGHT_CODEQL_LANGUAGES}`
placeholder on the matrix line that `codeql_workflow_scaffolder.py` replaces
with the rendered YAML list; the placeholder keeps the template a parseable
YAML scalar so the drift test can pin its shape.

The drift test at `shared/tests/test_codeql_workflow_convention.py` pins the
template against these constants — neither the scaffolder nor the
automerge-readiness doc renderer hard-codes paths, the placeholder, or the
job-name shape.

Two non-negotiable invariants mirror the other workflow templates:

* **Dormant by default.** Only `workflow_dispatch:` is active; `pull_request:`
  / `push:` / `schedule:` must be absent from the parsed YAML (header comments
  are fine). Phase-B activation — flipping the auto-triggers — is a deliberate
  operator step, because a Required Check that never reports (dormant) would
  block every PR in branch protection.
* **`continue-on-error` on the analyze step.** A private repo without GitHub
  Advanced Security fails the SARIF upload ("Advanced Security must be enabled
  for this repository"); the analysis still runs, and the job stays GREEN so it
  can serve as a Required Check. Mirrors the guard `security.yml` carries on its
  upload-sarif step.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Deployed-file path in target repos + template path in the monorepo
# ---------------------------------------------------------------------------

# Where the rendered CodeQL workflow lives in a target repository.
CODEQL_WORKFLOW_PATH = ".github/workflows/codeql.yml"

# Where the source template lives in the shipwright monorepo.
CODEQL_TEMPLATE_PATH = "shared/templates/github-actions/codeql.yml.template"

# ---------------------------------------------------------------------------
# Language parametrization (the SSoT the scaffolder + doc renderer read)
# ---------------------------------------------------------------------------

# Placeholder token on the template's `matrix.language:` line. The scaffolder
# replaces this exact literal with a rendered YAML list (e.g. `[python]`).
# Chosen as a `${...}` form so PyYAML parses the template line as a plain
# string scalar — the drift test asserts the placeholder is present, and a
# render test asserts the rendered output parses back to the expected list.
LANGUAGES_PLACEHOLDER = "${SHIPWRIGHT_CODEQL_LANGUAGES}"

# Profile → CodeQL languages. Keys MUST match profile names in
# `shared/profiles/*.json` (and `ci_workflow.TEMPLATE_BY_PROFILE`).
# CodeQL language ids: `python`, `javascript-typescript`.
CODEQL_LANGUAGES_BY_PROFILE: dict[str, list[str]] = {
    "python-plugin-monorepo": ["python"],
    "supabase-nextjs": ["javascript-typescript"],
    "vite-hono": ["javascript-typescript"],
}

# The analyze job's `name:` in the template — interpolates the matrix language
# so the GitHub check name becomes `Analyze (<language>)` per matrix entry.
#
# ANALYZE_JOB_NAME + REQUIRED_PERMISSIONS below are currently consumed only by
# the drift test (they pin the template's shape, like the constants in
# security_workflow.py). They are deliberately public so a future A5-style
# CodeQL audit can verify the deployed workflow against the same SSoT the
# template is pinned to — do not mistake them for unwired dead code.
ANALYZE_JOB_NAME = "Analyze (${{ matrix.language }})"

# Minimum permissions the SARIF-uploading CodeQL workflow needs. Same floor
# semantics as `security_workflow.REQUIRED_PERMISSIONS`: once any explicit
# `permissions:` key is set, every unlisted permission falls back to `none`.
REQUIRED_PERMISSIONS: dict[str, str] = {
    "security-events": "write",  # codeql-action/analyze SARIF upload
    "contents": "read",          # actions/checkout
    "actions": "read",           # SARIF attach to the workflow run
}


def languages_for_profile(profile_name: str | None) -> list[str] | None:
    """Return the CodeQL language list for a profile, or None if unmapped.

    None lets the scaffolder short-circuit with a graceful
    `no_codeql_for_profile` result instead of writing a broken matrix.
    """
    if profile_name is None:
        return None
    return CODEQL_LANGUAGES_BY_PROFILE.get(profile_name.strip())


def render_languages_yaml(languages: list[str]) -> str:
    """Render a CodeQL language list as a YAML flow sequence, e.g. `[python]`.

    The scaffolder substitutes this for ``LANGUAGES_PLACEHOLDER`` in the
    template. Empty list is a caller bug (a profile with no languages should
    return None from ``languages_for_profile`` and skip scaffolding).
    """
    if not languages:
        raise ValueError("render_languages_yaml: empty language list")
    return "[" + ", ".join(languages) + "]"
