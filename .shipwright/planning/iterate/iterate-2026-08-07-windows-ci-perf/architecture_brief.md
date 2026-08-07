# Architecture Brief: windows-ci-perf

## The problem

The existing `windows-tests.yml` CI job (added 2026-08-05) takes 24-28
minutes on a 2x-billed Windows runner, mostly because its largest test
directory runs with no parallelism and the pytest environment is
provisioned three times instead of once. Separately, two tests in that job
are permanently skipped because a security-hardening ownership check in
shared test-infrastructure code rejects a legitimate ownership shape that
GitHub's own Windows runner account produces.

## What would newly, permanently exist

Nothing. This changes machinery that already exists: the shell invocation
inside one existing CI workflow step, and the trusted-owner set inside one
existing Windows ACL-checking function in shared test infrastructure.
