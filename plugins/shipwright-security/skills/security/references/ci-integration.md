# CI Integration — `.github/workflows/security.yml`

This page used to carry the operational details. The full content has moved
to a top-level user-facing doc:

> **See [docs/security-ci-setup.md](../../../../../docs/security-ci-setup.md)**

It covers: dormant-trigger semantics, Phase-B activation pre-flight, the
`actions: read` permissions footgun, fork-PR degradation, the critical-gate
step, local-vs-CI parity, the convention lock, and both the drift test and
the monorepo snapshot test.

The workflow itself lives at `.github/workflows/security.yml` (monorepo) or
is scaffolded by `/shipwright-adopt` Step E.13 into adopted target repos
from `shared/templates/github-actions/security.yml.template`. The convention
lock at `shared/scripts/lib/security_workflow.py` keeps both paths consistent
with what `/shipwright-compliance` Group A5 audits.
