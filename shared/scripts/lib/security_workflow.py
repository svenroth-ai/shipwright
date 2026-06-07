"""Convention lock for the GitHub Actions security workflow.

Both /shipwright-adopt (writes the template into target repos) and
/shipwright-compliance Group A5 (audits the deployed file) consume these
constants. They are the single source of truth — neither side hard-codes
step ids, permission keys, or paths.

The drift test at shared/tests/test_security_workflow_convention.py pins
the template at TEMPLATE_PATH against these constants, so this module
cannot lie about what the template actually contains.
"""

from __future__ import annotations

# Identifier on the critical-findings gate step in the workflow. Adopt
# writes a step with this id into the rendered workflow; A5 audit greps
# for it to confirm the merge gate is wired.
CRITICAL_GATE_STEP_ID = "shipwright-critical-gate"

# Minimum permissions required for the SARIF-uploading scanner workflow
# to function correctly. GitHub Actions semantics: once any explicit
# `permissions:` key is set, every UNLISTED permission silently falls
# back to `none` — so this dict is also the floor below which the
# workflow stops working.
#
# - security-events: write — github/codeql-action/upload-sarif@v3 to
#   attach SARIF results to the GitHub Code Scanning surface.
# - contents: read — actions/checkout@v4 to fetch the repo.
# - actions: read — upload-sarif@v3 to attach the SARIF blob to the
#   workflow run. Without it the SARIF parses but the API push fails
#   with "Resource not accessible by integration". Empirically verified
#   on https://github.com/svenroth-ai/shipwright/actions/runs/24942627768.
REQUIRED_PERMISSIONS: dict[str, str] = {
    "security-events": "write",
    "contents": "read",
    "actions": "read",
}

# Optional permission — only present when the workflow includes the
# PR-comment step. A5 audit treats absence as INFO ("PR-comment feature
# inactive"), not HIGH — minimal SARIF-only workflows are valid.
OPTIONAL_PERMISSIONS: dict[str, str] = {
    "pull-requests": "write",
}

# Where the rendered workflow lives in a target repository. Adopt
# scaffolds it; compliance Group A5 audits it.
WORKFLOW_PATH = ".github/workflows/security.yml"

# Where the source template lives in the shipwright monorepo. Adopt
# reads from this path; the drift test verifies the template's shape
# against the constants in this module.
TEMPLATE_PATH = "shared/templates/github-actions/security.yml.template"

# Companion gitleaks allowlist. The deployed security.yml runs
# `gitleaks detect --no-git` with NO `--config`, so gitleaks auto-loads a
# `.gitleaks.toml` from the repo root when present. Adopt scaffolds this
# file alongside the workflow so a brownfield repo's first scan does not go
# red on the universal `cafebabe:deadbeef` sidekiq-secret false positive
# (proven on leadwright 2026-06-07). GITLEAKS_CONFIG_PATH MUST be the
# root-level name gitleaks auto-loads; the drift test at
# shared/tests/test_gitleaks_config_convention.py pins the template's shape.
GITLEAKS_CONFIG_PATH = ".gitleaks.toml"
GITLEAKS_CONFIG_TEMPLATE_PATH = "shared/templates/github-actions/gitleaks.toml.template"

# SARIF results land under this category in the GitHub Security tab —
# separate from CodeQL's own category. Both adopt template and any
# audit must use this exact value.
SARIF_CATEGORY = "shipwright-security"

# Action prefix used to identify the SARIF-uploading step in a workflow.
# The published action is versioned as `github/codeql-action/upload-sarif@v3`
# (or `@v4`, future versions). A5 audit matches steps whose `uses:` value
# starts with this prefix so it picks up legitimate version pins without
# coupling to a specific tag. The template uses `@v3` today — bumping the
# template's version pin must NOT require an audit code change.
SARIF_UPLOAD_USES_PREFIX = "github/codeql-action/upload-sarif"
