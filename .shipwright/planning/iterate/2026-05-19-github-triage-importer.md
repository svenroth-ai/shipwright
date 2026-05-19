# Iterate Spec: github-triage-importer

- **Run ID:** iterate-2026-05-19-github-triage-importer
- **Type:** feature
- **Complexity:** medium
- **Status:** draft

## Goal

Add a GitHub-findings triage producer so that security alerts (code scanning,
Dependabot, secret scanning) and failed CI workflow runs reported by GitHub's
automated runs land in the local `.shipwright/triage.jsonl` automatically. Today the GitHub Actions
security run uploads SARIF to the cloud Security tab but writes nothing local —
the local triage stays empty of security findings. This un-defers the CI
producer deferred in ADR-047, using a pull-based `gh api` design (no webhook).

## Acceptance Criteria

- [ ] AC1 — Given `gh` is installed and authenticated, when the importer runs,
  then each open result of `gh api repos/{owner}/{repo}/code-scanning/alerts`
  is appended to `.shipwright/triage.jsonl` with `source="github"`,
  `dedup_key="github:code-scanning:{alert.number}"`, and severity mapped from
  `rule.security_severity_level` (fallback `rule.severity`).
- [ ] AC2 — Given open Dependabot alerts, when the importer runs, then each is
  appended with `dedup_key="github:dependabot:{alert.number}"` and severity
  from `security_advisory.severity`.
- [ ] AC3 — Given a failed workflow run on the default branch, when the importer
  runs, then it is appended with `dedup_key="github-ci:{workflow}:{head_sha}"`
  and severity `high`; failed runs on non-default branches are ignored.
- [ ] AC4 — Given the same alert is imported a second time, when the importer
  runs again, then `append_triage_item_idempotent` returns `None` for it and no
  duplicate line is written (idempotent, `match_commit=False, window=None`).
- [ ] AC5 — Given a triage item exists for a GitHub alert whose state is now
  `fixed`/`dismissed` (or a CI failure whose latest run on the same
  workflow+branch now succeeds), when the importer runs, then the still-open
  triage item is marked `dismissed` with reason `githubResolved`, scoped to the
  `github:`/`github-ci:` dedup-key shapes only — items from other producers are
  untouched (ADR-052 key-shape-scoped resolve pattern).
- [ ] AC6 — Given the last import was less than the throttle interval ago, when
  the SessionStart hook fires, then it exits 0 with no `gh api` call; given it
  was longer ago, the import runs and `.shipwright/github_import_state.json`
  records a fresh ISO-8601 timestamp.
- [ ] AC7 — Given `gh` is absent or unauthenticated, when the SessionStart hook
  fires, then it exits 0 (fail-soft), writes one stderr notice, and does not
  block session start.
- [ ] AC8 — Given open secret scanning alerts, when the importer runs, then each
  is appended with `source="github"`,
  `dedup_key="github:secret-scanning:{alert.number}"`, and severity `critical`;
  the raw `secret` value from the API is NEVER written to
  `.shipwright/triage.jsonl` — only `secret_type_display_name` and the alert
  location / HTML URL.

## Spec Impact

- **Classification:** modify
- **ADD:** none
- **MODIFY:** FR-01.14 (Triage Inbox) — description gains the GitHub producer;
  the `(E)` acceptance line "The CI producer is explicitly deferred" is replaced,
  and a new `(E)` line is appended for the GitHub findings producer.
- **REMOVE:** none
- **NONE justification:** n/a

## Out of Scope

- WebUI Triage-tab changes — shipped separately (Iterate 3).
- leadwright ExternalTask extension (Iterate 1b).
- Auto-promote — imported findings land as `status: triage`; the operator
  promotes/dismisses. No automatic backlog write.
- CI failures on non-default branches / PR branches — expected-red mid-work,
  would flood triage.
- An always-on webhook receiver — pull-based `gh api` only.
- De-duplication between `source="github"` and a local `source="security"`
  scan. Keys are namespaced so they never collide in storage; true cross-source
  de-dup is a separate concern (this repo does not run local scans).
- Backfilling historical already-resolved alerts.

## Design Notes

No UI surface. Producer + SessionStart hook only.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `gh api` (GitHub REST) | `github_triage.py` alert/run parsers | JSON (stdout) |
| `github_triage.py` (writes state) | `import_github_findings.py` throttle check | JSON — `.shipwright/github_import_state.json` |
| `github_triage.py` → `append_triage_item_idempotent` | `triage.py` storage + `aggregate_triage.py` | JSONL — `.shipwright/triage.jsonl` |

The `gh api` JSON shape and the throttle state file are both new serialized
boundaries → Boundary Probe sub-step is mandatory in Build (Step 6a).

## Confidence Calibration

Empirical probes — all in `shared/tests/test_github_triage.py` (32 tests):

- **Boundaries touched:** (1) `gh api` JSON → the 4 parsers; (2) the
  throttle state file `.shipwright/github_import_state.json` (write→read);
  (3) `github_triage` → `append_triage_item_idempotent` → `triage.jsonl`.
- **Empirical probes run:**
  - State-file round-trip — `write_last_import` → real file on disk →
    `read_last_import` returns the identical datetime. PASS.
  - Malformed state file — corrupt JSON → `read_last_import` None →
    `is_due` conservatively True. PASS (probe added after Self-Review).
  - gh-api shape parse — realistic code-scanning / Dependabot /
    secret-scanning / workflow-run fixtures through every parser; fields,
    severities, dedup keys asserted. PASS.
  - Producer→file→consumer — `import_findings` → `triage.jsonl` →
    re-read; dedup keys + `source` asserted. PASS.
  - Idempotency — double import, second run appends 0. PASS.
  - None-vs-`[]` distinction (correctness-critical) — a failed fetch
    (`None`) must NOT auto-resolve that prefix's items; a successful-empty
    fetch (`[]`) MUST. Both directions asserted. PASS.
  - Secret hygiene — full import of a secret-scanning alert; the raw
    sentinel value is absent from the `triage.jsonl` bytes. PASS.
- **Edge cases NOT probed + why acceptable:** operator-input categories
  (POSIX `export`, inline `#` comments, quoted `#`) — N/A: both the state
  file and `gh api` output are machine-written/-read JSON, never
  hand-edited (justified skip per `references/boundary-probes.md`). Two
  GitHub workflows sharing one display name would collide on the
  `github-ci:<name>:<sha>` key — pathological, accepted.
- **Confidence-pattern check:** no "are you confident?" yes-then-bug
  pattern fired. The Self-Review surfaced one gap (malformed-state file
  untested); one more probe was run (the malformed-state test) before F0.
  Most recent probe returned no finding → exhausted.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run --with pytest --with pytest-mock pytest shared/tests/test_github_triage.py -q --color=no`
- **Evidence path:** `.shipwright/runs/iterate-2026-05-19-github-triage-importer/surface_verification.json`
