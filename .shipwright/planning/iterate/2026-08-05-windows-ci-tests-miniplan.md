# Mini-Plan: windows-ci-tests

- **Run ID:** iterate-2026-08-05-windows-ci-tests

## Approach

Add one new workflow file, `.github/workflows/windows-tests.yml`, with a
single job `shared-tests-windows` on `runs-on: windows-latest`. Steps:
checkout → install `uv` (same pinned SHA `astral-sh/setup-uv` action `ci.yml`
already uses) → `uv python install 3.11` → `uv sync` → a `shell: bash` step
that loops over `shared/tests`, `shared/scripts/tests`,
`shared/scripts/tools/tests` running
`uv run --with pytest --with pytest-mock pytest "$dir" -v -m "not slow and not cross_plugin"`
per directory (the exact per-dir pattern `ci.yml`'s "Run shared tests" step
already uses on Linux, chosen specifically because it is already proven
collision-safe in this repo). No coverage flags, no lint, no security-scanner
installs — none of the three target directories need them, and pulling in
Semgrep/Trivy/Gitleaks on Windows is real added complexity, unlike Linux
where `ci.yml` already had to solve it for `plugins/shipwright-security`.

Triggers mirror `ci.yml` exactly: `pull_request` → `main`, `push` → `main`,
`workflow_dispatch`. Same `permissions: contents: read` (checkout + test
only, no writes) and the same per-ref/per-commit `concurrency` group shape.

## Alternative Considered

**Run the full monorepo suite (all plugins + shared + integration) on
`windows-latest`, mirroring `ci.yml` end-to-end**, on the reasoning that the
anchor's own illustrative defect (97392eea) lived in a *plugin*
(`shipwright-changelog`), not in `shared/`, so a shared-only Windows job
would not literally have caught that specific historical commit.

**Rejected.** Three reasons:
1. `plugins/shipwright-security/tests` hard-fails in CI (by design, ADR-044
   "Silent-skip CI-discipline") when Semgrep/Trivy/Gitleaks binaries are
   absent. `ci.yml` solves this with Linux-specific install steps (apt for
   Trivy, a SHA-verified tarball for Gitleaks); replicating that for Windows
   is a materially bigger, separately-riskable unit of work (different
   binary, different archive format, a fresh SHA to verify) that doesn't
   serve this unit's stated purpose.
2. The 97392eea bug itself is **already fixed** at its source
   (`plugins/shipwright-changelog/scripts/lib/git_utils.py` already pins
   `encoding="utf-8"` on every `subprocess.run` call, confirmed by reading
   the current file) — it is cited in the anchor as *motivation* for why
   Windows CI matters, not as a live defect this unit must re-catch.
3. This repo's own prior iterate
   (`.shipwright/planning/iterate/2026-05-31-ci-shared-tests.md`) already
   scoped and flagged exactly this follow-up — "a `windows-latest` CI job …
   so the `os.name`-fake Windows-simulation tests also run" — against the
   `shared/` dirs specifically, because that is where every currently-skipped
   Windows-gated test actually lives. Matching that scope is the smaller,
   already-vetted fix, not a guess.

Full-suite Windows coverage remains a reasonable future escalation (noted in
the iterate spec's Out of Scope) but is not this unit's job.
