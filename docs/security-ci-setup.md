# Security Scanning Setup

Shipwright surfaces security findings from your CI into the Triage Inbox
(visible in the [shipwright-webui](https://github.com/svenroth-ai/shipwright-webui)
Triage tab) regardless of GitHub's pricing tier. There are two equivalent
paths to populate that surface:

| Path | Scanners | Cost on private repos | Where findings land |
|---|---|---|---|
| **A. shipwright-security workflow (default)** | Semgrep + Trivy + Gitleaks + Shipwright Prompt-Injection Scanner | Free | `findings.json` CI artifact → Triage Inbox → WebUI Triage tab |
| **B. GitHub Advanced Security (GHAS) alternative** | CodeQL + Dependabot + Secret Scanning + (optional) SARIF re-upload from path A | **Paid** for private repos (free for public) | GitHub Security tab → Triage Inbox → WebUI Triage tab |

Pick one. The Triage Inbox importer auto-detects which path is active.
**Use both only if you specifically need GHAS's native Security-tab UX** —
see "Running both" below.

> **TL;DR for greenfield Shipwright projects on a private repo:** keep the
> default (Path A). It's free, scans more (Prompt Injection is unique to
> Shipwright), and lands in the same Triage Inbox surface.

---

## Path A — `shipwright-security` workflow (default)

The Shipwright Security workflow runs an OSS scanner chain on GitHub
Actions, posts a PR comment summarising findings, uploads SARIF
best-effort, **and** uploads a `findings.json` artifact that the
Triage Inbox imports automatically.

It ships **DORMANT**: only `workflow_dispatch` (manual trigger) is active
by default. Activate the auto-triggers explicitly when you're ready.

### What it scans

| Scanner | What it finds |
|---|---|
| **Semgrep** | SAST (taint analysis, security patterns, OWASP rules) |
| **Trivy** | Dependency CVEs, container vulnerabilities |
| **Gitleaks** | Hard-coded secrets in source + history |
| **Shipwright Prompt-Injection Scanner** | LLM prompt-injection risks (unique to Shipwright) |

The combined output lands in three places:

- **PR comment** — collapsed table per scanner, posted by `github-actions[bot]`
  (only fires on `pull_request` triggers).
- **CI artifact** `security-scan-results` (30-day retention) — contains
  `findings.json`, `prompt_risks.json`, `report.md`, and SARIF.
- **GitHub Security tab** — best-effort SARIF upload via
  `github/codeql-action/upload-sarif@v4`. On private repos without GHAS
  this step fails silently (`continue-on-error: true`) — the other
  outputs still land. See "Running both" if you want GHAS to consume
  this SARIF.

### Two surfaces share the same template

- **Adopted projects.** `/shipwright-adopt` Step E.13 scaffolds the
  workflow into `<project>/.github/workflows/security.yml` from the
  template at `shared/templates/github-actions/security.yml.template`.
- **The shipwright monorepo itself.** `.github/workflows/security.yml`
  exercises the same scanner chain on every shipwright commit.

Both files share the same DORMANT invariants and activation procedure.

### Current state — DORMANT

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

The full pipeline (scan → SARIF upload → PR-comment skip → critical
gate → artifact upload) runs on every dispatch. The PR-comment step is
no-op outside PR events; SARIF still uploads on `workflow_dispatch` and
`schedule` events.

> **Critical gate fails closed.** The "Check for critical findings" step
> aborts the run if `findings.json` is **absent or unparseable** (a
> scanner crash), instead of reading it as "0 criticals" and passing
> green. It also aborts on a **degraded scan** — when `findings.json`
> carries `"degraded": true` because a scanner leg (Gitleaks / Semgrep /
> Trivy) fataled or produced a truncated report. Such a leg yields `[]`
> findings, so the critical count would otherwise read 0 and pass green
> (same failure class as the `--report-path -` secret-scanner regression,
> iterate-2026-06-05-gitleaks-report-path); the `scan_errors` array names
> the failed scanner + reason. `prompt_risks.json` is a softer signal: its
> absence warns loudly but does not block. This invariant is enforced
> going forward by the CI-gate guard
> (`shared/scripts/tools/check_ci_gate_coverage.py`, check (c)).

### Activation — turn on auto-triggers

Pre-flight checklist before flipping the auto-triggers on:

1. **Run one manual dispatch first** (`gh workflow run security.yml`)
   and confirm the workflow completes green.
2. **Check the PR-comment shape** — fire one workflow_dispatch from a
   feature branch, then look at the rendered comment to confirm
   formatting matches your team's expectations.
3. **Confirm fork-PR semantics** — see "Fork-PR degradation" below.
   If your project receives external contributions, decide whether you
   accept the read-only-token degradation (no SARIF upload, no PR
   comment) or want to adopt `pull_request_target` (out of scope for
   the dormant template).
4. **Optional — enable Code Scanning** in repo *Settings → Code
   security and analysis* if you want SARIF findings to additionally
   appear in the GitHub Security tab. This is Path B's gate; Path A
   works fine without it.

Then edit `.github/workflows/security.yml` and uncomment the two
auto-trigger blocks:

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
- Every Monday 06:00 UTC, a full scan runs.
- New findings appear in the Triage Inbox (and the WebUI Triage tab)
  within ~6 hours on the SessionStart side (throttled — see "Triage
  Inbox integration" below).

### Deactivation — turn off auto-triggers

Either re-comment the two trigger blocks (keeping `workflow_dispatch`
for manual dispatches), or delete the file entirely. The Triage Inbox
gracefully degrades: when no successful run exists, the importer
returns `None` and no `gh-security:` action-unit is emitted. Previously
open items remain (they are NOT mass-resolved — a failed fetch never
auto-resolves per ADR-052).

### Trigger semantics (once activated)

| Trigger | What runs | Where results land |
|---------|-----------|--------------------|
| `pull_request` against main | Full scan + SARIF upload + PR comment + critical gate | PR comment (replace), GitHub Security tab (if GHAS), `security-scan-results` artifact, Triage Inbox |
| `schedule` (weekly) | Full scan + SARIF upload + critical gate | GitHub Security tab (if GHAS), artifact, Triage Inbox |
| `workflow_dispatch` | Same as schedule (manual) | GitHub Security tab (if GHAS), artifact, Triage Inbox |

### Operational details

#### Permissions footgun — `actions: read`

The workflow declares an explicit `permissions:` block. Once you do
that, GitHub silently sets every *unlisted* permission to **none** for
the run. `upload-sarif@v3` needs `actions: read` to attach the SARIF to
the workflow run; without it the SARIF validates and parses fine but
the final API push fails with `Resource not accessible by integration`.
The current block includes:

```yaml
permissions:
  contents: read           # actions/checkout
  actions: read            # required by upload-sarif@v3 to attach SARIF
  pull-requests: write     # PR-comment posting
  security-events: write   # SARIF upload to Code Scanning
```

The convention lock at `shared/scripts/lib/security_workflow.py`
declares `security-events: write`, `contents: read`, and `actions: read`
as the minimum-required floor. `pull-requests: write` is optional and
only needed for the PR-comment step. `/shipwright-compliance` Group A5
audits against this convention.

If you extend the workflow with another action that hits a new GitHub
API surface, double-check whether it needs an additional permission slot.

#### Fork-PR degradation

PRs from forks run with a read-only `GITHUB_TOKEN`: neither
`security-events: write` nor `pull-requests: write` is granted by
GitHub. The workflow handles this transparently:

- The scan still runs against the PR branch (artifacts upload).
- The SARIF upload step **is skipped**
  (`if:` guard checks `github.event.pull_request.head.repo.full_name ==
  github.repository`).
- The PR comment step **is skipped** for the same reason.
- The critical-finding gate still fires — fork PRs introducing
  critical findings still fail the workflow.

If you need full SARIF / PR-comment coverage on fork PRs, the canonical
GitHub-recommended pattern is the `pull_request_target` event with
manual checkout of the PR head. That is explicitly out of scope for the
dormant template because it introduces a token-scope footgun for the
maintainer.

#### Critical-finding gate

A `jq`-based step counts findings with `severity == "critical"` (or, in
the adopted-template variant, SARIF `properties.security-severity >= 9.0`)
across the produced reports. If the total is non-zero, the workflow
fails with `::error::` annotation, blocking merge. This step carries the
canonical id `shipwright-critical-gate` so `/shipwright-compliance`
Group A5 can verify the gate is wired without parsing free-form step
names.

#### Accepted-risk rule tailoring (Semgrep)

Two Semgrep rules fire on this repo every scan but map to **accepted-risk /
by-design** postures, not actionable findings. Rather than dismiss them in
Triage every week (they re-surface from each fresh scan), they are suppressed
at the **producer** — filtered in the Semgrep normalizer, keyed off two opt-in
env vars set in the scan step of `.github/workflows/security.yml`. Both default
**off** in the plugin, so adopted repos are unaffected and decide their own
posture.

| Rule (`check_id`) | Count | Why accepted | Channel |
|---|---|---|---|
| `…dependabot-missing-cooldown…` | 14 low | `.github/dependabot.yml` is DORMANT (`open-pull-requests-limit: 0` on every ecosystem) — a cooldown on a config that opens zero PRs is meaningless. | `SHIPWRIGHT_SEMGREP_EXCLUDE_RULES` (exact `check_id`, wholesale drop) |
| `…github-actions-mutable-action-tag…` | 12 medium | GitHub-owned actions (`actions/*`, `github/*`) are deliberately not SHA-pinned (decision 2026-06-30 — Scorecard weights pinned-deps 8:2 and pinning GitHub-owned actions needs Dependabot to avoid tag-rot). | `SHIPWRIGHT_SEMGREP_ACCEPT_GH_OWNED_ACTION_TAGS` (owner-scoped) |

**The mutable-tag channel is owner-scoped, not wholesale.** It suppresses the
finding *only* when the matched `uses:` line points at a GitHub-owned owner
(`actions`, `github`). An unpinned **third-party** action still gets flagged —
that is the supply-chain guard the rule exists for. When the owner can't be
parsed from the matched line, the finding is kept (fail toward the signal).

Suppression happens in the normalizer (`normalizers/semgrep.py::normalize`),
not via a `semgrep --exclude-rule` flag, so it is robust across semgrep
versions and mirrors the SARIF-suppression parser. SCA acceptances live in the
parallel Trivy register at repo-root `.trivyignore.yaml`.

#### The accepted-risk register (scanner-agnostic record)

The channels above are where a suppression is *applied*; repo-root
**`shipwright_accepted_risks.yaml`** is where it is *recorded*. Every acceptance
carries a `target`, the scanner-native `rule`, an `expires` re-review date, a
`rationale_ref` naming a recorded decision (`ADR-NNN`, an `iterate-…` run id,
`#NNN`, `DO-NOT #NNN`), and a `statement`.

Before it existed, the only accepted-risk due date in the framework was
`expired_at` inside `.trivyignore.yaml` — a *Trivy SCA ignore file*. A Semgrep or
CI-posture acceptance had nowhere to record an expiry, so one ended up registered
inside a Trivy ignore file purely to obtain a due date.

The register does not replace the scanner wiring; a both-directions gate keeps
the two honest:

```bash
uv run shared/scripts/tools/accepted_risks_cli.py check  --project-root .
uv run shared/scripts/tools/accepted_risks_cli.py expire --project-root .
```

`check` fails when a suppression has no register entry (an **unrecorded**
acceptance — nobody can tell why it is there or when to re-review it) *and* when
a register entry matches no real suppression (a **stale** record). `expire` fails
once an acceptance is past its re-review date. Both run in CI via
`shared/tests/test_accepted_risks_register.py`, so the discipline is mechanical
rather than conventional — an expiry nobody enforces is a comment.

The compliance dashboard renders the register with expiry status and the
authority each acceptance rests on. A suppression with **no** register entry is
rendered as drift, not as an accepted risk: being suppressed is not the same as
being accepted.

**Not covered offline:** a `github-dismissal` acceptance. Its counterpart is live
GitHub alert state rather than a file, so `check` reports it as *unchecked* (it
never treats "not checkable here" as "checked and fine"). Converging that surface
so one acceptance quiets both triage and code scanning is tracked separately.

**Where the GH-owned drop applies (two paths).** The owner-scoped predicate lives
in the shared leaf module `shared/scripts/gh_action_tag_owner.py` so both
application points stay in lockstep:

- **Plugin scan** (`semgrep_tailoring.py::normalize_tailored`) — the monorepo's
  own `security.yml` runs the shipwright-security scanner, so its `findings.json`
  is already tailored at scan time.
- **Artifact ingest** (`shared/scripts/security_findings.py::_findings_from_sarif`)
  — every `/shipwright-adopt` repo's `security.yml` runs **raw** `semgrep scan
  --sarif` and uploads un-tailored SARIF (no `findings.json`). So the GH-owned
  mutable-tags used to reach the `gh-security` Triage producer *and* the
  Control-Grade Security dimension even after the repo formally accepted them —
  a recurring false "N low" alarm. With the env var set they are now dropped at
  ingest too (owner read from the checked-out workflow file at the finding's
  line, via the repo root the producer passes as `workflow_base`; unresolvable →
  kept). Third-party tags stay counted on both paths. inSource `# nosemgrep`
  suppressions were already honoured at ingest.

**Verify / revert.** Unset either env var in `security.yml` to see the rule
resurface. The pure `normalize()` (no kwargs) and the two resolver helpers are
covered by `tests/test_semgrep_rule_tailoring.py` (plugin scan) and
`shared/tests/test_security_findings_gh_tag_drop.py` (artifact ingest), both
including the third-party still-flagged guard.

#### Local parity

`run_scan_and_report.py` (the local interactive flow) produces the same
normalised findings with the same redaction rules. The differences are
purely in destination:

| Local | CI |
|-------|----|
| `.shipwright/securityreports/latest.{md,json}` (gitignored, 20 retained) | `findings.json` + `report.md` artifact (30-day retention) |
| Iterate-handoff dialog | PR comment |
| n/a | SARIF to GitHub Security tab (best-effort on private no-GHAS) |
| n/a | Triage Inbox via the artifact importer |

A finding fingerprint is identical between the two paths, so once
SARIF is live, GitHub dedups local-then-CI duplicate sightings of the
same issue.

#### Convention lock

The deployed workflow path, the critical-gate step id, the
minimum-required permissions, and the SARIF category are pinned by
`shared/scripts/lib/security_workflow.py`. Both `/shipwright-adopt`
(writes the template) and `/shipwright-compliance` Group A5 (audits
the deployed file) read these constants — neither side hard-codes them.

The drift test at
`shared/tests/test_security_workflow_convention.py` parses the template
via PyYAML and asserts every constant is present. A template edit that
removes or renames a pinned element fails the test, so convention and
template stay in sync.

#### Snapshot test (monorepo workflow)

`plugins/shipwright-security/tests/test_workflow_shape.py` asserts the
dormant invariants on the **monorepo's own**
`.github/workflows/security.yml` on every test run: triggers stay
commented, `security-events: write` and `actions: read` are set, fork
guards are present, SARIF category is `shipwright-security`. Any future
edit that accidentally activates triggers will break those tests until
either the trigger blocks are re-commented or the snapshot is
intentionally updated.

The drift test (template) and the snapshot test (monorepo workflow)
are deliberately separate because the two files are allowed to
diverge: the monorepo workflow runs against the shipwright codebase
and uses plugin-internal scripts (`scripts/tools/scan.py`), while the
template ships with native scanner CLI invocations so it works in any
adopted repo.

---

## Path B — GitHub Advanced Security (GHAS) alternative

If you already pay for GHAS (or work on a public repo where GHAS is
free), you can use GitHub's native scanners as the Triage Inbox source
and turn off Path A.

### When this makes sense

- You want the GitHub-native Security tab UX (per-finding triage,
  dismissal at SARIF level, GitHub's own dedup).
- You're already on a GHAS plan (Enterprise / paid private repos /
  public repos).
- You prefer CodeQL's SAST coverage over Semgrep's (Path A's SAST
  scanner).

### Setup

1. Enable Code Scanning in repo *Settings → Code security and analysis*.
2. Enable Dependabot alerts and Secret Scanning in the same panel.
3. Enable CodeQL. `/shipwright-adopt` already scaffolds a **dormant**
   `.github/workflows/codeql.yml` (Step E.14b) with a profile-aware
   `language:` matrix (`python` and/or `javascript-typescript`) — activate it
   by uncommenting the `pull_request:` / `push:` / `schedule:` triggers, or
   use GitHub's CodeQL default setup instead. The scaffolded workflow keeps
   `continue-on-error` on the analyze step, so on a **private** repo without
   GitHub Advanced Security the `Analyze (<language>)` job stays green (the QL
   analysis runs; only the SARIF upload to the Security tab fails). On a
   public repo CodeQL is free and results appear in the Security tab.
4. Disable Path A — either re-comment the `pull_request` / `schedule`
   triggers in `.github/workflows/security.yml`, or delete the file.

> **Automerge.** If you require a CodeQL `Analyze (<language>)` check (or any
> dormant workflow's check) in branch protection, activate its `pull_request:`
> trigger first — a check that never reports blocks every PR. The
> `AUTOMERGE_SETUP.md` that adopt writes at the repo root lists the exact
> Required-Check job names this repo produces and the branch-protection steps.

### Triage Inbox integration

The Triage Inbox importer calls three GitHub APIs (`code-scanning/alerts`,
`dependabot/alerts`, `secret-scanning/alerts`) and emits the same
`gh-security:{owner}/{repo}` action-unit. No additional config needed —
the importer auto-detects which path returned data.

### Auth requirement

`gh auth status` must show the `repo` and `read:org` scopes. The
Dependabot API also requires `admin:repo_hook`; if absent, the
importer gracefully degrades — no Dependabot findings, but
code-scanning / secret-scanning still flow.

---

## Running both (not recommended)

You can run Path A and Path B in parallel — the SARIF upload step in
`.github/workflows/security.yml` will push Semgrep + Trivy findings
into Code Scanning when GHAS is active. The Triage Inbox importer
then preferentially uses the GHAS API path; the artifact path is
**skipped** to avoid double-counting (`cs_alerts is None` is the gate).

Trade-offs:

- **Pro:** Findings appear in the GitHub Security tab AND the Triage
  Inbox, so reviewers who prefer the native UX get it.
- **Con:** Pay for GHAS without gaining new scanner coverage (Path A's
  scanners SARIF-upload into the same Code Scanning surface; you're
  paying for the surface, not the scans).
- **Con:** Duplicate effort if you want to suppress a finding —
  dismissing in the GitHub Security tab does NOT auto-dismiss the
  Triage item (intentional: the Triage item is a launch-surface, not
  a finding-mirror; see § 4.11.1 of the main guide).

If you decide to disable Path A while keeping GHAS, remove or
re-comment the auto-triggers in `.github/workflows/security.yml`. The
critical-gate step also drops; CodeQL's gate (if configured) takes over.

---

## Triage Inbox integration

Either path produces a `gh-security:{owner}/{repo}` action-unit in
`.shipwright/triage.jsonl` — one item per repo, regardless of finding
count. The item carries a `launchPayload` field with a ready-to-paste
`/shipwright-security` invocation plus the relevant URL (GitHub
Security tab for Path B, workflow run URL for Path A).

### What appears in the Triage tab

- One **GitHub security** action-unit per repo (Path A or Path B
  source) — severity = max across scanner findings.
- One **GitHub secret-scanning** action-unit per repo (Path B only —
  not produced by Path A; secret-scanning belongs to GHAS).
- One **failed CI** action-unit per failing default-branch workflow
  (orthogonal to Path A vs B — produced by the workflow-runs importer).

### Operator flow

Three verbs on every action-unit (matching the launch-surface model
from iterate-2026-05-20):

- **Fix now** — copy the `launchPayload` fence into a new Claude session.
  The matching slash command auto-fires and resolves the item via the
  existing lifecycle hooks.
- **Promote** — `triage_cli.py promote <id> --task-ref EXT:<ref>`
  creates a backlog ExternalTask for deferred work.
- **Dismiss** — `triage_cli.py dismiss <id> --reason <reason>` for
  false-positives / won't-fix. (Per-finding false-positives are
  dismissed on GitHub at SARIF level, not in the triage inbox.)

### Freshness window (Path A only)

The artifact importer treats workflow runs older than
`SHIPWRIGHT_GITHUB_ARTIFACT_MAX_AGE_DAYS` days (default 14) as stale and
skips them. If your security workflow runs less frequently than that,
either:

- Set a wider window:
  `export SHIPWRIGHT_GITHUB_ARTIFACT_MAX_AGE_DAYS=60`
- Configure a `schedule:` trigger (see "Activation" above) so a fresh
  artifact lands at least once per cutoff window.

A stale window does NOT auto-resolve open Triage items — a stale clean
run never dismisses real findings.

### Throttle

The Triage Inbox SessionStart hook
(`shared/scripts/hooks/import_github_findings.py`) runs at most once per
`SHIPWRIGHT_GITHUB_IMPORT_THROTTLE_HOURS` hours (default 6). This
applies to both paths and prevents one Claude session per minute from
hammering the GitHub API.

---

## Prerequisites

Both paths require:

- **GitHub CLI (`gh`) installed and authenticated** — `gh auth status`
  must show the active account.
- A `git remote get-url origin` that resolves to a recognised GitHub
  URL (`github.com` or a `github.*` enterprise host).

Path A additionally requires:

- The shipwright-security GitHub Action to have run at least once
  recently (within `SHIPWRIGHT_GITHUB_ARTIFACT_MAX_AGE_DAYS`) and
  produced a `security-scan-results` artifact.

Path B additionally requires:

- GHAS enabled on the repo (paid for private, free for public).
- The `gh` token's scopes must include `repo` and `read:org`; the
  Dependabot API additionally needs `admin:repo_hook`.
