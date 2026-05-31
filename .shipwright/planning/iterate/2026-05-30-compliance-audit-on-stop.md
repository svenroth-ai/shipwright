# Iterate Spec — Compliance detective-audit Stop-hook (triage emit/dismiss)

- **Run ID:** `iterate-2026-05-30-compliance-audit-on-stop`
- **Intent:** FEATURE (new shared Stop hook) + CHANGE (wire into 2 hooks.json Stop chains)
- **Complexity:** medium
- **Risk flags:** `touches_io_boundary` (`hooks.json` edits + the hook reads/writes `.shipwright/triage.jsonl` and a runtime marker)
- **Spec Impact:** ADD (new producer trigger; no existing artifact contract changes)

## Problem

`audit_detector.run_all(..., emit_to_triage=True)` is the ONLY path that runs
`mirror_findings_to_triage` (the auto-dismiss-when-finding-cleared logic in
`plugins/shipwright-compliance/scripts/audit/audit_detector.py`). That path is
invoked ONLY by the explicit `/shipwright-compliance` skill (via `run_audit.py`).
No Stop hook, SessionStart hook, `finalize_iterate`, or `update_compliance.py`
calls it. Consequence: any `source=compliance` triage item (F2/F4/F5/F6/F7,
B-group, etc.) stays in `status=triage` until someone manually runs
`/shipwright-compliance`, even after the underlying finding is fixed.

Every OTHER triage producer has a frequent automatic trigger
(`phaseQuality` → `audit_phase_quality_on_stop`; `github` → `import_github_findings`
SessionStart; `test-failure` + `sbom` → `update_compliance`). The compliance-audit
producer is the lone exception. (Not addressed by PR #78/#79 — those fixed the
E1-E5 compliance-MD *staleness* false-positives via single-producer +
snapshot-provenance, a different concern that this iterate does NOT touch.)

## Approach (Option A1 from the 2026-05-23 design discussion)

Add `shared/scripts/hooks/audit_compliance_on_stop.py`, modeled on
`audit_phase_quality_on_stop.py`, wired into the `shipwright-iterate` and
`shipwright-changelog` Stop chains AFTER finalize + phase_quality and BEFORE
`aggregate_triage_on_stop`.

### Stop contract (same as phase_quality)
- **Never blocks** — always exits 0, even on internal error. Observability, not a gate.
- **Idempotent per (HEAD-sha, session_id)** — re-running on the same commit in the
  same session is a no-op (marker under gitignored `.shipwright/agent_docs/runtime/`).
- **Greenfield-safe** — silent no-op when `project_root` isn't Shipwright-managed
  (reuses `pq.is_shipwright_project` + the monorepo auto-descent guard).
- **Opt-out** via `SHIPWRIGHT_COMPLIANCE_AUDIT_ON_STOP=0`.

### CRITICAL safety gate — full-coverage-before-dismiss
`mirror_findings_to_triage` auto-dismisses any currently-`triage` compliance item
whose `check_id` is absent from THIS run's failures. The dismiss is **groupless**:
if a group crashed/was skipped, its findings vanish from the run and its triage
items would be wrongly dismissed (running only group F would dismiss B7/B2/etc.).

Therefore the hook runs the **FULL audit (groups A-G)** with `emit_to_triage=False`,
verifies that `set(report.groups_run) == {A..G}` and there is no `import_gate_error`,
and ONLY THEN calls `mirror_findings_to_triage`. Any partial coverage → skip
mirroring entirely (never a false dismiss) + stderr diagnostic. This is strictly
safer than `run_audit.py`'s unconditional `emit_to_triage=True`.

Scoped per-group auto-dismiss (Option A2) and cross-worktree triage sync (Option C)
are explicitly OUT OF SCOPE (separate follow-ups). The #78 snapshot-provenance
E-staleness machinery is NOT touched.

### Why in-process (not shelling out to run_audit.py)
The audit chain is first-party + stdlib (empirically: probe ran all groups A-G with
zero third-party import errors in the shared-hook `uv` env). In-process avoids the
report-file churn that `run_audit.py --format both` would write on every Stop, and
lets us interpose the safety gate between detection and the triage mirror.

## Affected Boundaries
- `hooks.json` Stop chains (×2: iterate, changelog) — ordering contract.
- `.shipwright/triage.jsonl` — append (new compliance items) + status mutation
  (auto-dismiss resolved items). Gitignored + per-worktree.
- Runtime idempotency marker under `.shipwright/agent_docs/runtime/compliance_audit/`.
- Cross-layout path resolution (dev monorepo vs version-pinned cache) to locate
  `plugins/shipwright-compliance`.

## Acceptance Criteria
1. New hook exists, never blocks (exits 0) on every path incl. internal error.
2. Runs the full audit and, when all groups A-G ran, emits new compliance fails to
   triage and auto-dismisses resolved ones (parity with `/shipwright-compliance`).
3. When any group is missing/crashed or the import gate trips, it does NOT mirror
   (no false dismiss) and surfaces a diagnostic.
4. Idempotent: second invocation on the same (HEAD-sha, session) is a no-op.
5. Greenfield no-op; opt-out via `SHIPWRIGHT_COMPLIANCE_AUDIT_ON_STOP=0`.
6. Wired into iterate + changelog Stop chains in the mandated order.
7. `docs/hooks-and-pipeline.md` updated (hooks registry + Stop chain + producer matrix).

## Confidence Calibration
- **Boundaries touched:** hooks.json Stop chains (×2), `.shipwright/triage.jsonl`
  (append + status mutation), runtime idempotency marker, cross-layout plugin path
  resolution.
- **Empirical probes run:** (1) in-process `register_all()` + `run_all(emit_to_triage=False)`
  from the shared-hook env → `groups_run = A-G`, `groups_skipped = []`,
  `import_gate_error = None`, 6 real fails — confirms full coverage + faithfulness.
  (2) cache-layout check → `cache/shipwright/plugins/shipwright-compliance` exists,
  so `parents[3]/plugins/shipwright-compliance` resolves in both dev + cache.
- **Edge cases NOT probed + why acceptable:** end-user project `uv` env (audit is
  stdlib + first-party, so env-independent — verify_imports gate + per-group
  try/except make any drift fail safe to "skip mirror"); cross-worktree triage sync
  (explicitly out of scope, Option C).
- **Confidence-pattern check:** the asymptote risk here is "audit silently dismisses
  items it shouldn't" — defended by the full-coverage gate, which is itself tested
  (partial-groups → no mirror). One extra probe added: a unit test that injects a
  partial-coverage report and asserts `mirror` is NOT called.
