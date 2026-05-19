# Mini-Plan: github-triage-importer

- **Run ID:** iterate-2026-05-19-github-triage-importer
- **Spec:** `2026-05-19-github-triage-importer.md`

## Approach

A pull-based GitHub→Triage producer, run by a throttled SessionStart hook.
Mirrors the existing `check_drift.py` SessionStart pattern and the
`_emit_*_to_triage` producer pattern (ADR-046/047). No webhook, no always-on
process — `gh api` is invoked on demand, at most once per throttle interval.

### Files

**New:**

| File | Role | ~LOC |
|---|---|---|
| `shared/scripts/github_triage.py` | Importer module: 4 `gh api` fetchers (code-scanning, dependabot, secret-scanning, ci-runs), severity mapping, dedup-key builders, key-shape-scoped auto-resolve pass, `import_github_findings()` orchestrator. Top-level under `shared/scripts/` (NOT `lib/`) per ADR-045. If it crosses 300 LOC, factor the thin gh-client into `shared/scripts/github_api.py`. | ~290 |
| `shared/scripts/hooks/import_github_findings.py` | Thin SessionStart hook: read throttle state → if stale call the module → write state → fail-soft on any error. Emits a short `additionalContext` line only when new items were imported. | ~110 |
| `shared/tests/test_github_triage.py` | Tests per AC + Boundary Probe (gh-api fixture parsing, state-file round-trip). | ~300 |

**Modified:**

| File | Change |
|---|---|
| `plugins/shipwright-iterate/hooks/hooks.json` | Register the new SessionStart hook — **one plugin only** (avoids the known "runs 13×" multi-registration noise). |
| `docs/triage-inbox.md` | Remove the "CI failure producer — deferred indefinitely" bullet; add `github` producer row(s) to the Producers table + a "GitHub Findings Producer" section. |
| `docs/hooks-and-pipeline.md` | Add the new SessionStart hook to the hooks registry + context-loading matrix (mandated by CLAUDE.md). |
| `.shipwright/planning/01-adopted/spec.md` | MODIFY FR-01.14 — description + `(E)` lines (Spec Impact). |
| `shipwright_sync_config.json` | Map the new files → FR-01.14. |
| `.gitignore` | Ensure `.shipwright/github_import_state.json` is ignored (verify against the `.shipwright/` whitelist). |

### Key design decisions

- **`gh api` placeholders.** `gh api repos/{owner}/{repo}/...` auto-fills owner/repo
  from the cwd git remote — no config of the repo slug needed.
- **Dedup model.** Stable GitHub alert IDs → `match_commit=False, window_seconds=None`
  (indefinite, one item per alert — mirrors the compliance/drift producers).
  CI failures: `github-ci:{workflow}:{head_sha}` — per-commit.
- **Auto-resolve.** Per ADR-052: scope the resolve pass by the dedup-key shape
  this producer owns (`github:`, `github-ci:` prefixes) — never by `source`
  alone. Reason string `githubResolved`.
- **Throttle.** Interval default 6h; resolution order: `shipwright_run_config.json`
  → `triage.github_import_throttle_hours` (optional), else env
  `SHIPWRIGHT_GITHUB_IMPORT_THROTTLE_HOURS`, else 6. State file
  `.shipwright/github_import_state.json` holds `last_import` (ISO-8601 UTC).
- **Severity mapping.** GitHub `critical/high/medium/low/warning/note/error` →
  triage `critical/high/medium/low/info`; CI run failure → fixed `high`;
  secret scanning alert → fixed `critical`.
- **Secret hygiene.** Secret-scanning alert objects carry the leaked `secret`
  value — it is NEVER read into the triage `title`/`detail`. Only
  `secret_type_display_name` + location / HTML URL are persisted.
- **Fail-soft.** `gh` missing / unauthenticated / offline / non-zero → hook
  exits 0 with one stderr line. A SessionStart hook must never block a session.

### Work breakdown (TDD)

1. RED — `test_github_triage.py`: gh-api fixture JSON (captured shapes for the
   4 endpoints), parse → triage-item assertions, severity mapping, dedup keys,
   idempotent re-import, key-shape-scoped auto-resolve, throttle no-op vs run,
   `gh`-absent fail-soft, state-file round-trip.
2. GREEN — `github_triage.py`, then `import_github_findings.py`.
3. Boundary Probe (Step 6a) — `gh api` JSON → parser; state-file write→read
   round-trip; the 8 edge-case categories (machine-only JSON — operator-input
   categories justified-skipped).
4. Register hook; update the 3 docs + spec + sync_config + .gitignore.
5. Full `shared/tests/` suite at F0 (baseline 1817 pass).

### Test strategy

- Unit: full `shared/tests/` suite (medium → full suite).
- Boundary Probe: producer→file→consumer round-trip for the state file; gh-api
  fixture → parser.
- E2E (F0.5): cli surface — `pytest shared/tests/test_github_triage.py --color=no`.
- `gh` is mocked in all tests (subprocess patched) — no live network in CI.

## Alternatives considered

- **Webhook receiver** — rejected: needs an always-on process; out of scope per
  ADR-047. Pull-based `gh api` gives the same data with no infrastructure.
- **Manual CLI only** — rejected: operator explicitly flagged "I'll forget it".
- **Unthrottled SessionStart import** — rejected: a `gh api` round-trip on every
  session start; the throttle keeps it to ~4 calls/day.
- **New `shipwright_triage_config.json`** — rejected for v1: one optional key in
  the existing `shipwright_run_config.json` + an env override is enough; a new
  config file would pull in schema + adopt-scaffolder scope.
