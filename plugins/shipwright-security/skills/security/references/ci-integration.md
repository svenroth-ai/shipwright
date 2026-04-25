# CI Integration — `.github/workflows/security.yml`

The shipwright-security workflow runs the OSS scanner chain (Semgrep + Trivy +
Gitleaks) on GitHub Actions, posts a PR comment summarising findings, and
uploads SARIF to the GitHub Security tab. It ships **DORMANT**: only
`workflow_dispatch` (manual trigger) is active by default. You activate the
auto-triggers explicitly when you're ready.

## Current state — DORMANT

The `on:` block in `security.yml` looks like this:

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

The full pipeline (scan → SARIF translate → PR comment skip → critical gate →
artifact upload) runs on every dispatch. The PR-comment step is no-op outside
PR events; SARIF still uploads on `workflow_dispatch` and `schedule` events.

## Activation (Phase B / Go-Live)

When ready to go live, edit `security.yml` and uncomment the two auto-trigger
blocks:

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
- The GitHub Security tab shows findings under **category: shipwright-security**
  (separate from CodeQL's own category).

## Trigger semantics (once activated)

| Trigger | What runs | Where results land |
|---------|-----------|--------------------|
| `pull_request` against main | Full scan + SARIF translate + PR comment + critical gate | PR comment (replace), GitHub Security tab, `security-scan-results` artifact |
| `schedule` (weekly) | Full scan + SARIF translate + critical gate | GitHub Security tab, artifact |
| `workflow_dispatch` | Same as schedule (manual) | GitHub Security tab, artifact |

## SARIF upload — single-pass translator

Scanners run **once** and emit a normalised `findings.json`. A second `scan.py`
invocation reads that cache (`--input-from-cache`) and translates the in-memory
findings into per-source SARIF files (`--sarif-dir`). One `.sarif` per scanner
with a known capability is **always** written, even on clean scans, so
`upload-sarif` doesn't fail on an empty directory.

SARIF specifics:
- **`level` mapping** — `critical|high → error`, `medium → warning`,
  `low|info → note`, anything else → `none`.
- **Stable rule IDs** — `{source}/{rule}` (e.g. `semgrep/spawn-shell-true`).
- **Stable fingerprints** — `partialFingerprints["shipwright/v1"]` is a
  sha256 of `source|rule|file|line|cve_id`, so GitHub dedups the same finding
  across scans.
- **Severity score** — `severity_score` (0.0-10.0) is exposed as
  `properties.security-severity`, driving the GitHub badge.

## Permissions footgun — `actions: read`

The workflow declares an explicit `permissions:` block. Once you do that,
GitHub silently sets every *unlisted* permission to **none** for the run.
`upload-sarif@v3` needs `actions: read` to attach the SARIF to the workflow
run; without it the SARIF validates and parses fine but the final API push
fails with `Resource not accessible by integration`. The current block
includes:

```yaml
permissions:
  contents: read
  actions: read           # required by upload-sarif@v3
  pull-requests: write    # PR comment
  security-events: write  # SARIF upload
```

If you ever extend the workflow with another action that hits a new GitHub
API surface, double-check whether it needs an additional permission slot.

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
checkout of the PR head — explicitly out of scope for v0.3 because it
introduces a token-scope footgun for the maintainer.

## Critical-finding gate

A `jq`-based step counts findings with `severity == "critical"` across both
`findings.json` and `prompt_risks.json`. If the total is non-zero, the workflow
fails with `::error::` annotation, blocking merge. This behaviour is preserved
across iterates — it is the only hard gate the workflow enforces.

## Local parity

`run_scan_and_report.py` (the local interactive flow) produces the same
normalised findings with the same redaction rules. The differences are purely
in destination:

| Local | CI |
|-------|----|
| `securityreports/latest.{md,json}` (gitignored, 20 retained) | `findings.json` + `report.md` artifact (30-day retention) |
| Iterate-handoff dialog | PR comment |
| n/a | SARIF to GitHub Security tab |

A finding fingerprint is identical between the two paths, so once SARIF is
live, GitHub will dedup local-then-CI duplicate sightings of the same issue.

## Snapshot test

`tests/test_workflow_shape.py` asserts the dormant invariants on every
test run: triggers stay commented, `security-events: write` is set, fork
guards are present, SARIF category is `shipwright-security`. Any future edit
that accidentally activates triggers will break those tests until either the
trigger blocks are re-commented or the snapshot is intentionally updated.
