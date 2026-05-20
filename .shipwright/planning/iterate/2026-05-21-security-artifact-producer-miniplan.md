# Mini-Plan: security-artifact-producer (Iterate C)

- **Run ID:** iterate-2026-05-21-security-artifact-producer
- **Complexity:** medium
- **Risk flags:** touches_shared_infra, touches_io_boundary

## Approach

Single-producer extension. Treat the shipwright-security workflow
artifact as a **third parallel source** for the existing
`gh-security:{owner}/{repo}` action-unit, alongside Code Scanning
(`cs_alerts`) and Dependabot (`db_alerts`). Same action-unit, same
dedup key, same `launchPayload` contract — but the source of the
SAST data shifts when GHAS Code Scanning is unavailable.

**Revision after external LLM review (Iterate-C plan review):** the
original "fallback when cs AND db both fail" gate was incorrect because
Dependabot is free and commonly enabled on private repos without GHAS.
The artifact must fire whenever the SAST source (`cs_alerts`) is `None`,
independent of Dependabot status. The action-unit's `detail` then
renders three independent count lines — code-scanning / dependabot /
shipwright-security — each annotated `(unavailable)` when its fetch
returned `None`.

**Why this avoids double-counting.** When `cs_alerts` succeeds, the
SARIF upload from `shipwright-security.yml` succeeded (it requires
`security-events: write` which on private repos requires GHAS); GHAS
Code Scanning then contains the same data as the artifact would. By
skipping the artifact fetch in that case, we never double-count
semgrep/trivy findings.

**Fail-soft invariants preserved.**
- `None` on any failure (gh missing, run not found, run older than
  `SHIPWRIGHT_GITHUB_ARTIFACT_MAX_AGE_DAYS`, artifact expired /
  deleted, malformed JSON, non-list `findings`) — ADR-052 distinction
  between *failed* and *empty* fetch.
- Auto-resolve runs only when the artifact fetch SUCCEEDED with a
  fresh-enough clean scan — never when the fetch failed or the run is
  stale.
- The producer mutates no schema; the webui consumer needs no change.
- Severity counts are derived from iterating `findings[]`, never from
  trusting the aggregate `by_severity` / `total_findings` counters
  (defensive against producer/aggregate drift — external review
  finding #9).

## Files to change

| File | Change | LOC est. |
|---|---|---|
| `shared/scripts/github_api.py` | Add `latest_security_workflow_run()` + `download_security_findings(run_id)` helpers. Workflow identification via path-match against `shared/scripts/lib/security_workflow.py::WORKFLOW_PATH` (`.github/workflows/security.yml`). Branch auto-resolved via existing `default_branch()` helper — callers do NOT supply. Freshness gate via `SHIPWRIGHT_GITHUB_ARTIFACT_MAX_AGE_DAYS` env var (default 14). Robust file discovery via `Path(tmp).rglob('findings.json')`. | ~110 |
| `shared/scripts/github_triage.py` | Extend `security_action_unit` to accept `artifact` as a third parallel input (alongside `code_scanning`, `dependabot`). Detail line renders three independent count blocks, with `(unavailable)` for None sources. Counts derived from iterating `findings[]`, NOT from trusting `by_severity`. Length-cap detail at 1KB. Extend `import_findings` to fetch artifact when `cs_alerts is None`. Add `by_source["gh-security:artifact"]` telemetry key. Adjust auto-resolve gate to require at least one security source returning a fresh 0-finding state. | ~100 |
| `shared/tests/test_github_api_artifact.py` | NEW. Unit tests for `latest_security_workflow_run` + `download_security_findings`. Cover: happy path, no successful run, run too old (max-age gate), non-default-branch runs filtered out, artifact expired, malformed JSON (truncated, non-list `findings`, missing keys), `gh run download` non-zero exit, nested artifact layout discovered via rglob, subprocess argv hygiene (argv list never string concat). | ~200 |
| `shared/tests/test_github_triage_artifact_fallback.py` | NEW. Integration tests for the parallel-source branch. cs=None + artifact succeeds → emit with artifact data. cs succeeds → artifact NOT fetched. cs=None + db succeeds + artifact succeeds → both sources visible in detail. all sources None → no emission, no auto-resolve. artifact 0 findings (fresh) → auto-resolve fires. stale clean run → no auto-resolve. by_source telemetry. Source-switching transitions (4 cases per AC-6). | ~250 |
| `docs/guide.md` | §4.11.1: add a note on the two ingestion paths (API + artifact) and point to `security-ci-setup.md`. Remove the 2 dangling links to `triage-inbox.md`. | ~15 |
| `docs/security-ci-setup.md` | Complete rewrite — setup guide structure (parallel to `setup-guide-jelastic-infomaniak.md`). 3 sections: shipwright-security (default), GHAS alternative, Triage Inbox integration. Operational details (fork-PR, permissions, gate) retained. | ~250 |
| `docs/triage-inbox.md` | DELETE | -290 |

Net delta: ~430 LOC added, 290 LOC removed.

## Test strategy

1. **Tests first (RED).** Write `test_github_api_artifact.py` +
   `test_github_triage_artifact_fallback.py` with the AC matrix (AC-1
   through AC-5). All tests fail because the functions don't exist yet.
2. **Implement (GREEN).** Add the 2 helpers in `github_api.py`, then the
   fallback branch in `github_triage.py`. Run targeted tests until
   green.
3. **Boundary Probe.** Use the captured `findings_sample.json` (real
   35-finding artifact pulled from run 26192978904) as the round-trip
   fixture. Run all 8 probe categories from
   `references/boundary-probes.md` minus the 3 operator-input categories
   (justified inline — machine-only JSON).
4. **Drift protection.** The existing `test_github_triage.py` +
   `test_github_triage_action_units.py` must keep passing — the
   fallback is additive, no existing behavior change. The reverse
   drift test (every owned dedup-prefix has a mapper) stays green
   because the prefix is unchanged (`gh-security:`).
5. **Full suite at F0.** `uv run pytest shared/tests/ plugins/*/tests/`
   per the medium-complexity matrix.

## Alternative considered

**Alternative: read the PR-comment table instead of the artifact.**
Parse the `shipwright-security-report` PR comment posted by
`github-actions[bot]` and emit from there. **Rejected.**
- Brittle — depends on the markdown table format; a renderer change
  silently breaks the importer.
- Less data than the artifact (truncated past 15 findings in the
  current PR-comment shape; full structured findings only in
  `findings.json`).
- Couples to PR events; loses signal on `workflow_dispatch` /
  `schedule` runs that don't post a comment.
- The artifact is the producer's actual structured output; the PR
  comment is a rendered view. Always prefer reading the SSoT.

**Alternative: SARIF re-upload via Personal Access Token outside GHAS.**
Rejected — SARIF upload is gated by `security-events: write` which on
private repos requires GHAS. Working around the gate is fragile and
defeats the purpose of having a free path.

## Out-of-scope follow-ups

- Splitting `prompt_risks.json` into a separate `gh-prompt-injection:`
  action-unit (signal-to-noise will tell whether this matters).
- Per-finding navigation from the webui Triage tab (would need
  per-finding sub-items — bigger schema change).
- Auto-triggering the security workflow from inside the importer (the
  workflow stays DORMANT by user choice — the importer just reads what
  exists).
