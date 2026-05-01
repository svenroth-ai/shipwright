# Security CI Setup — `.github/workflows/security.yml`

The Shipwright security workflow runs an OSS scanner chain (Semgrep + Trivy +
Gitleaks) on GitHub Actions, posts a PR comment summarising findings, and
uploads SARIF to the GitHub Security tab. It ships **DORMANT**: only
`workflow_dispatch` (manual trigger) is active by default. You activate the
auto-triggers explicitly when you're ready.

This document is the operational truth for two surfaces:

- **Adopted projects.** `/shipwright-adopt` Step E.13 scaffolds the workflow
  into `<project>/.github/workflows/security.yml` from the template at
  `shared/templates/github-actions/security.yml.template`.
- **The shipwright monorepo itself.** The workflow at
  `.github/workflows/security.yml` exercises the same scanner chain on every
  shipwright commit.

Both files share the same **DORMANT** invariants and Phase-B activation
procedure described below.

## Current state — DORMANT

The `on:` block looks like this:

```yaml
on:
  # pull_request:
  #   branches: [main]
  # schedule:
  #   - cron: '0 6 * * 1'  # Monday 06:00 UTC — weekly full scan
  workflow_dispatch:
```

You can manually fire the scan today via:

```bash
gh workflow run security.yml
```

The full pipeline (scan → SARIF upload → PR-comment skip → critical gate →
artifact upload) runs on every dispatch. The PR-comment step is no-op outside
PR events; SARIF still uploads on `workflow_dispatch` and `schedule` events.

## Activation (Phase B / Go-Live)

Pre-flight checklist before turning auto-triggers on — adopted repositories
will not have these by default:

1. **Enable Code Scanning** in repo *Settings → Code security and analysis*.
   Without it, SARIF uploads succeed but findings are not displayed in the
   Security tab.
2. **Confirm fork-PR semantics** — see "Fork-PR degradation" below. If your
   project receives external contributions, decide whether you accept the
   read-only-token degradation (no SARIF upload, no PR comment) or want to
   adopt `pull_request_target` (out of scope for the dormant template).
3. **Run one manual dispatch** (`gh workflow run security.yml`) and confirm
   the workflow completes green and SARIF lands in the Security tab.
4. **Review the PR comment shape** — fire one workflow_dispatch from a
   feature branch, then look at the rendered comment to confirm the
   formatting matches your team's expectations.

Then edit `security.yml` and uncomment the two auto-trigger blocks:

```yaml
on:
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 6 * * 1'
  workflow_dispatch:
```

No other code changes are needed. After the merge:

- Every PR against `main` triggers a scan with a comment summary.
- Every Monday 06:00 UTC, a full scan runs and uploads fresh SARIF.
- The GitHub Security tab shows findings under **category:
  shipwright-security** (separate from CodeQL's own category).

## Trigger semantics (once activated)

| Trigger | What runs | Where results land |
|---------|-----------|--------------------|
| `pull_request` against main | Full scan + SARIF upload + PR comment + critical gate | PR comment (replace), GitHub Security tab, `security-scan-results` artifact |
| `schedule` (weekly) | Full scan + SARIF upload + critical gate | GitHub Security tab, artifact |
| `workflow_dispatch` | Same as schedule (manual) | GitHub Security tab, artifact |

## Permissions footgun — `actions: read`

The workflow declares an explicit `permissions:` block. Once you do that,
GitHub silently sets every *unlisted* permission to **none** for the run.
`upload-sarif@v3` needs `actions: read` to attach the SARIF to the workflow
run; without it the SARIF validates and parses fine but the final API push
fails with `Resource not accessible by integration`. The current block
includes:

```yaml
permissions:
  contents: read           # actions/checkout
  actions: read            # required by upload-sarif@v3 to attach SARIF
  pull-requests: write     # PR-comment posting
  security-events: write   # SARIF upload to Code Scanning
```

The convention lock at `shared/scripts/lib/security_workflow.py` declares
`security-events: write`, `contents: read`, and `actions: read` as the
minimum-required floor — those three together are what the SARIF upload
flow needs. `pull-requests: write` is optional and only present when the
PR-comment step is wired in. `/shipwright-compliance` Group A5 audits
against this convention; missing required permissions are HIGH findings,
missing optional permissions are INFO ("PR-comment feature inactive").

If you ever extend the workflow with another action that hits a new GitHub
API surface, double-check whether it needs an additional permission slot —
the existing keys do not extend by default.

## Fork-PR degradation

PRs from forks run with a read-only `GITHUB_TOKEN`: neither
`security-events: write` nor `pull-requests: write` is granted by GitHub. The
workflow handles this transparently:

- The scan still runs against the PR branch (artifacts are uploaded).
- The SARIF upload step **is skipped** (`if:` guard checks
  `github.event.pull_request.head.repo.full_name == github.repository`).
- The PR comment step **is skipped** for the same reason.
- The critical-finding gate still fires — fork PRs introducing critical
  findings still fail the workflow.

If you need full SARIF/PR-comment coverage on fork PRs, the canonical
GitHub-recommended pattern is the `pull_request_target` event with manual
checkout of the PR head. That is explicitly out of scope for the dormant
template because it introduces a token-scope footgun for the maintainer.

## Critical-finding gate

A `jq`-based step counts findings with `severity == "critical"` (or, in the
adopted-template variant, SARIF `properties.security-severity >= 9.0`)
across the produced reports. If the total is non-zero, the workflow fails
with `::error::` annotation, blocking merge. This step carries the canonical
id `shipwright-critical-gate` so `/shipwright-compliance` Group A5 can
verify the gate is wired without parsing free-form step names.

## Local parity

`run_scan_and_report.py` (the local interactive flow) produces the same
normalised findings with the same redaction rules. The differences are purely
in destination:

| Local | CI |
|-------|----|
| `.shipwright/securityreports/latest.{md,json}` (gitignored, 20 retained) | `findings.json` + `report.md` artifact (30-day retention) |
| Iterate-handoff dialog | PR comment |
| n/a | SARIF to GitHub Security tab |

A finding fingerprint is identical between the two paths, so once SARIF is
live, GitHub will dedup local-then-CI duplicate sightings of the same issue.

## Convention lock

The deployed workflow path, the critical-gate step id, the minimum-required
permissions, and the SARIF category are pinned by
`shared/scripts/lib/security_workflow.py`. Both `/shipwright-adopt` (writes
the template) and `/shipwright-compliance` Group A5 (audits the deployed
file) read these constants — neither side hard-codes them.

The drift test at `shared/tests/test_security_workflow_convention.py` parses
the template via PyYAML and asserts every constant is present. A template
edit that removes or renames a pinned element fails the test, so convention
and template stay in sync without manual review.

## Snapshot test (monorepo workflow)

`plugins/shipwright-security/tests/test_workflow_shape.py` asserts the
dormant invariants on the **monorepo's own** `.github/workflows/security.yml`
on every test run: triggers stay commented, `security-events: write` and
`actions: read` are set, fork guards are present, SARIF category is
`shipwright-security`. Any future edit that accidentally activates triggers
will break those tests until either the trigger blocks are re-commented or
the snapshot is intentionally updated.

The drift test (template) and the snapshot test (monorepo workflow) are
deliberately separate because the two files are allowed to diverge: the
monorepo workflow runs against the shipwright codebase and uses
plugin-internal scripts (`scripts/tools/scan.py`), while the template ships
with native scanner CLI invocations so it works in any adopted repo.
