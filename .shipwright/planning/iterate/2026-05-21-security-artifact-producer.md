# Iterate Spec: security-artifact-producer

- **Run ID:** iterate-2026-05-21-security-artifact-producer
- **Type:** feature
- **Complexity:** medium
- **Status:** draft

## Goal

Close the Triage Inbox ingestion gap on repos without GitHub Advanced
Security (GHAS): parse the `shipwright-security` workflow's
`findings.json` artifact and emit it as the existing
`gh-security:{owner}/{repo}` action-unit. This makes the
shipwright-security workflow — the default scanner stack — fully visible
in the Triage Inbox and the shipwright-webui Triage tab, instead of only
in PR-comment emails.

## Acceptance Criteria

- [ ] **AC-1** Given a repo whose GitHub code-scanning API fails (403,
  no GHAS), and a recent successful run of the
  `.github/workflows/security.yml` workflow on the default branch
  exists with a downloadable `security-scan-results` artifact whose
  `findings.json` lists ≥1 finding, when `import_findings` runs, then a
  `gh-security:{owner}/{repo}` action-unit is appended to
  `.shipwright/triage.jsonl` with severity = max severity across the
  artifact's `findings` array (derived from the list, NOT trusted from
  the `by_severity` aggregate), `detail` showing per-source counts
  (code-scanning / dependabot / shipwright-security each rendered
  independently, with `(unavailable)` for `None` sources), and
  `launchPayload` starting with `/shipwright-security` + the workflow
  run's `html_url`.
- [ ] **AC-2** Given the artifact path emitted an action-unit in a
  previous run, when a subsequent successful run yields 0 findings (clean
  scan) AND the clean run is fresher than
  `SHIPWRIGHT_GITHUB_ARTIFACT_MAX_AGE_DAYS` (default 14), then the
  previously-open `gh-security:{owner}/{repo}` item is auto-dismissed
  with `reason="githubResolved"` — same semantics as the GHAS API path.
- [ ] **AC-3** Given GHAS Code Scanning is active (cs_alerts fetch
  succeeds), when `import_findings` runs, then the artifact path is NOT
  taken — the existing API-based action-unit emission is unchanged.
  No double-counting between GHAS-uploaded SARIF and the artifact
  source. (Dependabot's availability does NOT gate the artifact path —
  Dependabot is free and orthogonal to the SAST source.)
- [ ] **AC-4** Given any failure mode in the artifact path (workflow
  never ran, latest successful run older than the max-age cutoff,
  artifact expired / deleted, malformed `findings.json` —
  non-list `findings`, missing keys, truncated JSON, `gh run download`
  not installed, network error), when `import_findings` runs, then the
  artifact helpers return `None`, the importer skips emission on the
  artifact path, and the auto-resolve pass does NOT mass-resolve
  previously-open items (the failed-fetch-vs-empty distinction from
  ADR-052 — `None` ≠ `[]`).
- [ ] **AC-5** Given the importer ran via the artifact path, when
  inspecting `import_findings`'s return dict, then `by_source` records
  the ingestion path distinctly — `gh-security:artifact` for an
  artifact-sourced action-unit — so telemetry / future audit can
  distinguish API vs artifact emission.
- [ ] **AC-6** Given a source-switching transition (artifact → GHAS,
  GHAS → artifact, or any clean ↔ findings cycle), when subsequent
  imports run, then the same `gh-security:{owner}/{repo}` dedup key
  preserves idempotency: no duplicate items appear, the persisted
  `launchPayload` stays frozen at first append (existing contract from
  iterate-2026-05-20), and `detail`'s live-best-effort counts may
  refresh on the next emission but never re-create the item.
- [ ] **AC-7** Given the shipwright-webui Triage tab is open and the
  importer has emitted an artifact-sourced action-unit, when the user
  views the tab, then the item renders identically to an API-sourced
  one — same severity badge, same `launchPayload` block, same
  Promote/Dismiss buttons. (No webui code change expected.)
- [ ] **AC-8** Documentation: `docs/guide.md` §4.11.1 reflects the two
  ingestion paths; `docs/security-ci-setup.md` is rewritten as a user
  setup guide (shipwright-security default vs GHAS alternative);
  `docs/triage-inbox.md` is deleted and every repo-wide reference is
  rewritten or removed.

## Spec Impact

- **Classification:** MODIFY
- **ADD** (new FR appended): none
- **MODIFY** (existing FR changed): FR-01.14 — Triage Inbox. Append new
  `- (E) Given … when … then …` acceptance-criteria lines under FR-01.14
  covering AC-1 / AC-3 / AC-4 / AC-5 above (the artifact ingestion path,
  fallback semantics, fail-soft contract, by_source telemetry). The FR
  table-row description stays as-is — the change is additive within the
  GitHub triage producer's already-listed responsibilities (`findings from
  local hooks/scans/audits AND from GitHub's automated runs`).
- **REMOVE** (FR retired): none
- **NONE justification:** n/a

## Out of Scope

- Modifying the shipwright-security workflow (`.github/workflows/security.yml`).
  The producer is artifact-consumer-only.
- Activating the security workflow's auto-triggers (`pull_request` /
  `schedule`). The workflow stays DORMANT by default; activation is
  documented in the rewritten `security-ci-setup.md` but unchanged in
  this iterate.
- Webui code changes. The action-unit schema is unchanged; the existing
  TriageItemCard / LaunchPayloadBlock / PromoteModal components in
  `shipwright-webui` will render artifact-sourced items unmodified.
- Schema migrations for `.shipwright/triage.jsonl`. The `gh-security:`
  dedup key, JSONL shape, and history-event format stay identical.
- Per-finding rendering. The artifact has rich per-finding data; the
  action-unit collapses it into one item per repo, mirroring the GHAS
  API path. Per-finding navigation lives in the workflow run page (URL
  embedded in `launchPayload`).
- Reading `prompt_risks.json` as a separate action-unit. The prompt-
  injection scanner findings are merged into the same `gh-security`
  action-unit (one unit per repo) — same as the PR comment's combined
  table. A separate `gh-prompt-injection:` action-unit is a possible
  future split if signal-to-noise warrants.

## Design Notes

n/a — no UI (Python-only producer change). The webui already renders
the action-unit; verification is read-only.

## Affected Boundaries

The artifact path adds a new serialized-format consumer. Producer side
lives in the shipwright-security workflow's `scan.py` →
`generate_security_report.py` chain and is unchanged by this iterate.

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `plugins/shipwright-security/scripts/tools/generate_security_report.py` writes `findings.json` (rendered in CI via `actions/upload-artifact@v4` as `security-scan-results`) | `shared/scripts/github_api.py::download_security_findings` (new) → `shared/scripts/github_triage.py::import_findings` (extended) | JSON object `{ "by_severity": {...}, "findings": [...], "total_findings": int, ... }` |
| `gh run list --workflow=<path> --status=success --json ...` (gh CLI) | `shared/scripts/github_api.py::latest_security_workflow_run` (new) | JSON array of run records |

The `findings.json` schema is **machine-only** (no operator-handediting),
so the operator-input categories of `references/boundary-probes.md` (POSIX
`export` prefix, inline `# comment`, quoted `#`) are N/A; round-trip +
malformed-input probes are required.

## Confidence Calibration

- **Boundaries touched:** see "Affected Boundaries" above —
  `findings.json` (artifact) + `gh run list` JSON (CLI output).
- **Empirical probes run** (all returned green after first GREEN cycle —
  no follow-up probe needed per the asymptote stopping rule):
  1. **Real-artifact round-trip** — `findings_sample.json` (35 real
     findings, mixed semgrep/trivy/gitleaks, from run 26192978904)
     piped through `download_security_findings` → returns list of 35
     dicts → `security_action_unit_from_artifact` produces a coherent
     action-unit. See
     `test_real_findings_sample_parses`.
  2. **Empty findings** — `{"findings": []}` returns `[]` (NOT None)
     from `download_security_findings`; `security_action_unit_from_artifact`
     returns None for empty list; orchestrator routes to auto-resolve
     gate when prior open item exists. See
     `test_download_security_findings_accepts_empty_findings_list`,
     `test_artifact_empty_list_with_no_prior_state_is_noop`,
     `test_artifact_clean_scan_auto_resolves_open_item`.
  3. **Missing/wrong-typed keys** — `{}`, `{"findings": null}`,
     `{"findings": "not-a-list"}`, `{"findings": 42}`,
     `{"findings": {"keyed": "by-id"}}` all return `None`. See
     `test_download_security_findings_returns_none_when_findings_not_a_list`.
  4. **Truncated JSON** — `'{"findings": [trunc'` returns `None`. See
     `test_download_security_findings_returns_none_on_invalid_json`.
  5. **Workflow never ran** — `_gh_api` returns empty `workflow_runs`
     list → `latest_security_workflow_run` returns `None` → artifact
     fetch skipped → no emission. See
     `test_latest_security_workflow_run_returns_none_on_empty_list`,
     `test_artifact_skipped_when_no_run_available`.
  6. **Run too old + artifact expired** — Two cases. (a) Freshness gate:
     stale run filtered at `latest_security_workflow_run` step. (b)
     `gh run download` exits non-zero (artifact retention window
     elapsed): `download_security_findings` returns `None`. See
     `test_latest_security_workflow_run_freshness_gate_default_14d`,
     `test_latest_security_workflow_run_freshness_gate_env_override`,
     `test_download_security_findings_returns_none_on_subprocess_failure`,
     `test_artifact_skipped_when_download_fails`.
  7. **Tempdir cleanup** — `subprocess.run` mock tracks the `--dir`
     argument; tempdir asserted nonexistent after helper returns. See
     `test_download_security_findings_cleans_up_tempdir`.
  8. **Severity mapping** — Severity derived by iterating
     `findings[]`, NOT by trusting the `by_severity` aggregate.
     Unknown severities fall back to `medium` (existing
     `triage_severity` helper). See
     `test_artifact_severity_derived_from_findings_list`,
     `test_artifact_unknown_severity_falls_back_to_medium`.
  9. **Subprocess argv hygiene** (added per external LLM review
     openai-10 / gemini-4) — `subprocess.run` always passed an argv
     list with `shell=False`; assertion enforced inside the stub
     helper used by all download tests. See
     `test_download_security_findings_uses_argv_list`.
  10. **Untrusted artifact content** (added per external LLM review
      openai-11) — sentinel `ATTACKER_CONTROLLED_*` strings in
      `rule` / `description` / `affected_file` MUST NOT appear in the
      action-unit's persisted `detail` or `launchPayload`. See
      `test_artifact_detail_does_not_leak_raw_finding_strings`.
  11. **Source-switching transitions** (AC-6, openai-2) —
      artifact→GHAS, GHAS→artifact, GHAS-clean→artifact-with-findings.
      Each preserves dedup-key idempotency and frozen `launchPayload`.
      See `test_transition_artifact_to_ghas_preserves_idempotency`,
      `test_transition_ghas_to_artifact_preserves_idempotency`,
      `test_transition_ghas_clean_then_artifact_findings`.
- **Edge cases NOT probed + why acceptable:** Operator-input categories
  (POSIX `export`, inline `# comment`, quoted `#`) — N/A for
  machine-only JSON artifact (the JSON parser handles its own
  whitespace/comment semantics). Cross-platform line-endings — the
  Python JSON parser is CRLF-tolerant.
- **Confidence-pattern check:** No "are you confident?"-style question
  was asked or answered in this run. The external LLM review caught
  the two HIGH findings (gate logic + freshness) BEFORE coding (in the
  plan-review phase), so they shaped the implementation rather than
  surfacing as test regressions. Asymptote stopping rule satisfied:
  the marginal empirical probe (round-trip with 500 synthetic
  findings — `test_artifact_detail_respects_length_cap`) returned
  green with no new finding.

## Verification (medium+)

- **Surface:** cli — `pytest` against the new unit + integration tests
  is the empirical surface. No UI surface; no API surface change.
- **Runner command:**
  ```bash
  uv run pytest shared/tests/test_github_api_artifact.py \
                shared/tests/test_github_triage_artifact_fallback.py \
                shared/tests/test_github_api.py \
                shared/tests/test_github_triage.py \
                shared/tests/test_github_triage_action_units.py \
                --color=no -v
  ```
- **Evidence path:**
  `.shipwright/runs/iterate-2026-05-21-security-artifact-producer/surface_verification.json`
  (the F0.5 orchestrator writes this).
- **Justification (only if surface=none):** n/a — the cli surface is
  applicable.
