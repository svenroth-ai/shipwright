# Iterate Spec — phase-quality triage bundling (action-units, not finding-mirrors)

- **run_id:** `iterate-2026-05-31-phasequality-triage-bundle`
- **Type:** change (modifies existing producer emission behavior)
- **Complexity:** medium (override; keyword-classifier under-counted — 3 behavioral
  layers, changes a triage-emission contract consumed by the WebUI inbox + RTM +
  audit detectors, touches a Stop hook that fans out across all 13 plugins,
  reads/writes JSON state boundaries → `touches_io_boundary`)
- **Spec Impact:** MODIFY (producer behavior; no new FR)
- **Triggering principle:** memory `project_triage_launch_surface_redesign` —
  *"Triage producers MUST emit action-units, not finding-mirrors"*; mirrors the
  AC structure of `proposed-sbom-triage-cluster-collapse.md`.

## Problem (empirically observed 2026-05-31)

A single Stop event fans out across all 13 plugin Stop hooks; each invocation
resolves its own phase from `CLAUDE_PLUGIN_ROOT` and audits only that phase.
The producer `_emit_tier1_fails_to_triage` then mirrors **one triage row per
Tier-1 FAIL code** (`dedup_key={phase}:{code}`). Result today: **9 separate
`phaseQuality` items** (design:C1/D1, build:C4, compliance:C1, security:C1/Sec1,
deploy:C1, adopt:C1, iterate:S2), all `runId=unknown`, all `severity=high`.

Two compounding causes:

1. **No phase-applicability notion.** This monorepo was *adopted* (brownfield)
   and only ever runs `/shipwright-iterate`. `shipwright_events.jsonl` carries
   exactly one `phase_completed` event (`changelog`); `phase_history` outcomes
   are `"adopted"` bootstrap markers. The audit nonetheless runs the C/D/Sec/S
   checks for design/build/deploy/adopt/security/compliance — phases this repo
   never actively executed — so each FAILs its "phase_completed event / artifact"
   check. False-positive-**by-context**.
2. **`run_id=unknown` + tail-fallback.** `resolve_run_id` falls through to
   `"unknown"` (no `run_config.run_id`, no `run_started` event, no loop env,
   empty `SHIPWRIGHT_SESSION_ID`). `spec_checks._read_iterate_entry` then
   *tail-falls-back* to the most-recent iterate entry (complexity=medium), so
   S2 demands a spec file whose name contains `run_id=unknown` — which can never
   exist → guaranteed FAIL.

Plus `match_commit=True` + 24h window → the whole set **re-fires on every new
HEAD commit**. The operator sees N inbox rows for what is one situation.

## Goal

Turn the phase-quality producer from a finding-mirror into an **action-unit**:
one rolling inbox row that represents "this project has open phase-quality
Tier-1 FAILs — go fix them", auto-dismissed when the set clears. And stop
emitting rows for phases the project never engaged or for run-id-less spec
checks that can't pass.

## Acceptance Criteria

### Layer 1 — phase-applicability gate (root cause)

- [ ] **AC-1 (engagement predicate).** A new helper
      `phase_is_engaged(project_root, phase, cfg, events) -> bool` returns True
      iff ANY of:
      (a) phase has a `phase_completed` event OR a `work_completed` event with
      `source==phase` in `shipwright_events.jsonl`; OR
      (b) `cfg.status.lower() == "complete"` AND `phase == "iterate"` (iterate is
      the always-on maintenance phase of a finished project); OR
      (c) `cfg.status.lower() != "complete"` AND (`phase ∈ cfg.completed_steps`
      OR `phase == cfg.current_step`).
      Otherwise False.
- [ ] **AC-1b (FAIL-OPEN on unreadable state).** If `shipwright_run_config.json`
      is missing/malformed OR `shipwright_events.jsonl` is unreadable, the
      predicate returns **True** (engaged) — the gate only ever SUPPRESSES when
      it has positively read the state and found no engagement signal. Never
      swallow a genuine alert on a read error. `status` casing is normalized.
      (external-review O#4 / G#4)
- [ ] **AC-2 (stale-cursor safety).** `current_step` and `completed_steps` grant
      engagement ONLY when `status != "complete"` — a stale `current_step`
      (here: `"design"` on a `status=complete` repo) must NOT re-admit a phase.
- [ ] **AC-3 (shape not scope).** The predicate keys on *active-engagement
      evidence*, never on "is the framework repo". A consumer app mid-pipeline
      (status=in_progress, current_step=build) gets build audited; a real
      completed pipeline keeps every phase that emitted a `phase_completed`
      event (orchestrated phases always do). Adopted-brownfield phases with no
      completion event are the only ones suppressed.
- [ ] **AC-4 (producer honors the gate).** The producer emits NO triage signal
      for FAILs whose phase is not engaged, and the bundle body (AC-7) excludes
      them.

### Layer 2 — run_id-less spec-check guard

- [ ] **AC-5 (S2 SKIP on unresolved run_id).** `check_s2_iterate_spec` returns
      `STATUS_SKIP` (reason: run_id not a resolvable iterate run) when `run_id`
      is a sentinel (`""`, `"unknown"`, `None`) OR has no **exact**
      `iterate_history` entry — **AND** no spec file on disk matches the run_id
      — instead of inheriting the tail-fallback entry's complexity and emitting
      an unsatisfiable FAIL. If a matching spec file IS on disk, normal logic
      runs (→ PASS). Same guard for `check_s3_iterate_miniplan` (S3).
      (external-review O#6 — preserve the file-exists→PASS signal)
- [ ] **AC-6 (mid-flow finalize preserved).** A real iterate run with an exact
      `iterate_history` entry (or a spec file already on disk matching the
      run_id) still PASS/FAILs normally — the guard only fires for the
      sentinel / no-exact-entry-and-no-file case. The existing tail-fallback
      stays for any other caller of `_read_iterate_entry`.

### Layer 3 — action-unit bundling

- [ ] **AC-7 (single rolling backlog item).** When ≥1 in-scope open Tier-1 FAIL
      exists across all phases (read structurally via `load_findings` → latest
      finding per phase → Tier-1 FAILs → filtered by Layer 1 + Layer 2), the
      producer emits **exactly one** triage item, `source="phaseQuality"`,
      `dedup_key="phaseQuality:backlog:<sig>"` where `<sig>` is a stable
      sha256[:12] of the sorted `phase:code` set. Body summarizes the FAILs
      (count, phases, the `phase:code` list) and carries a `launch_payload` that
      opens the skill-compliance dashboard.
- [ ] **AC-8 (idempotent within + across sweeps).** Every per-plugin Stop
      invocation in one sweep reads the same persisted finding JSONs → same
      `<sig>` → after the first appends, the rest no-op. Across sweeps with an
      unchanged FAIL set, no new item (open same-sig item suppresses;
      `match_commit=False`, `window_seconds=None`).
- [ ] **AC-9 (refresh on changed set).** When the in-scope FAIL set changes,
      open `phaseQuality:backlog:*` items whose `<sig>` ≠ current are dismissed
      (`reason="phaseQualityRefreshed"`) and one fresh item is appended — so the
      body always reflects the current set and there is never more than one open
      backlog item.
- [ ] **AC-10 (auto-dismiss on resolve).** When the in-scope FAIL set is empty,
      every open `phaseQuality:backlog:*` item is dismissed
      (`reason="phaseQualityResolved"`). No new item.
- [ ] **AC-11 (legacy back-compat).** Pre-existing `{phase}:{code}` items
      (status=triage/promoted/dismissed) are NOT migrated or mass-dismissed by
      this producer. Only the new `phaseQuality:backlog:*` shape is emitted
      going forward. (The 9 current ones were already operator-dismissed.)

### Cross-cutting

- [ ] **AC-12 (LOC budget).** New logic lands in a new module
      `shared/scripts/lib/phase_quality/_triage_bundle.py` (≤300 LOC); the hook
      `audit_phase_quality_on_stop.py` (currently 310 LOC, over budget) shrinks
      by delegating — net de-ratchet, never a ratchet.
- [ ] **AC-13 (never blocks).** All new code is best-effort; the Stop hook still
      always exits 0. Errors → stderr + no triage mutation.
- [ ] **AC-14 (docs).** `docs/hooks-and-pipeline.md` artifact-write matrix /
      triage-producer section updated to describe the backlog action-unit shape.
- [ ] **AC-15 (concurrent-sweep convergence).** Two sequential producer
      invocations with the same in-scope FAIL set leave exactly one open
      `phaseQuality:backlog:*` item (no thrash). Relies on atomic finding
      writes (no partial reads), deterministic checks (stable `<sig>`), and the
      triage `_FileLock` + idempotent append/dismiss. No leader election added —
      the change reduces triage write volume vs the prior per-FAIL emit.
      (external-review G#1/#2, O#2)
- [ ] **AC-16 (body is sig-derivable).** The backlog body + launch_payload are a
      pure function of the in-scope `phase:code` set plus static per-code
      remediation text — so the `<sig>` fully determines the rendered body and
      it can never go stale behind the dedup. `launch_payload` carries only
      normalized phase/code identifiers + the dashboard path (no free-form
      finding text). (external-review O#8, O#10)
- [ ] **AC-17 (consumer compatibility).** `source` stays `"phaseQuality"`,
      `severity="high"`, `kind="bug"` (unchanged); only dedup-key shape + item
      count change. Audit WebUI inbox / RTM / audit-detectors / triage schema /
      fixtures for any assumption of the `{phase}:{code}` dedup-key shape; none
      may break. (external-review O#3/#9/#11, G#5)

## Known limitation (documented, not a regression)

The phase-applicability gate (Layer 1) is **producer-side only** — the
skill-compliance *dashboard* aggregate still renders out-of-scope-phase FAILs
as red (it reads raw finding JSONs, not the engagement filter). The user's
stated problem is the **inbox flood**, which this fixes. Making the runners
emit `SKIP (not applicable)` for non-engaged phases (consistent dashboard) is
the operator-approved **follow-up iterate**, not in scope here — it widens
blast radius to `test_audit_phase_quality` + `_runners`.

**Exception (external-review G#3):** Layer 2 *does* touch a verifier
(`spec_checks.py`), so S2/S3 render as SKIP (not FAIL) on the dashboard too.
That is intentional — Layer 2 patches a genuine tail-fallback bug at the
source, not pure producer-side suppression. `test_audit_phase_quality` /
`test_spec_checks` are updated to expect the SKIP.

## Out of scope

- Wiring the compliance producer (`mirror_findings_to_triage`) to the same
  bundle shape. It already has an auto-dismiss path; a shared helper + its
  adoption is a fast-follow.
- The stale `current_step="design"` on a `status=complete` run_config (latent
  data bug) — AC-2 makes the gate robust to it; cleaning the field itself is
  separate.
- Changing the Stop-hook per-plugin fan-out architecture.

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| `emit_phase_quality_backlog` (new) writes one backlog action-unit | WebUI Triage-Inbox + RTM + audit detectors | `.shipwright/triage.jsonl` lines |
| `phase_is_engaged` reads run_config + events | producer + bundle builder | in-memory |
| `check_s2/s3` SKIP-on-sentinel | dashboard + bundle | finding JSON |

## Confidence Calibration

- **Boundaries touched:** `.shipwright/triage.jsonl` (append/status events via
  `append_triage_item_idempotent` + `mark_status`); `shipwright_run_config.json`
  + `shipwright_events.jsonl` (read-only, for engagement); per-run finding JSONs
  (read via `load_findings`).
- **Empirical probes run:**
  - *Reproduction probe* — built a temp project with the exact 2026-05-31
    conditions (status=complete, only `phase_completed[changelog]`, the 9
    flooding FAILs across design/build/compliance/security/deploy/adopt +
    iterate:S2-as-SKIP). Result: `collect_in_scope_fails → 0`, `emit → 0
    items` (was **9**). Flood eliminated.
  - *No-over-suppression probe* — an actively-engaged iterate
    (`work_completed[source=iterate]`) with a real `W2` FAIL still surfaces
    (`iterate:W2`). Confirms AC-3 (gate keys on engagement, not repo identity).
  - *LOC* — `_triage_bundle.py` = 300, hook 310→238 (de-ratchet, AC-12).
- **Test Completeness Ledger:**
  | Behavior | Status | Evidence |
  |---|---|---|
  | `phase_is_engaged` all branches (AC-1/1b/2/3) | tested | test_phase_quality_engagement (11 cases) |
  | `load_engagement_inputs` fail-open | tested | test_load_inputs_* |
  | `collect_in_scope_fails` (multi-code, filter, tier2, pass/skip, latest-per-phase, fail-open) | tested | test_phase_quality_engagement (6 cases) |
  | backlog emit: single/body/launch/idempotent/refresh/auto-dismiss/no-fails/unengaged/legacy/re-fire (AC-7..11,15,16) | tested | test_phase_quality_triage_emit (11 cases) |
  | S2/S3 run_id guard (AC-5/6) | tested | test_spec_checks_run_id_guard (7 cases) |
  | existing S2/S3 PASS/FAIL/WARN preserved | tested | test_spec_checks (40 cases, green) |
  | hook delegates to emit; old fn removed | tested | import smoke + test_audit_phase_quality + test_hook_output_schema_compliance |
  | end-to-end flood elimination | tested | reproduction probe above |
  | docs (hooks-and-pipeline.md) | untestable (`covered-by-existing-test` — doc text, no behavior) | manual edit, AC-14 |
  - **0 untested-testable behaviors.**
- **Confidence-pattern check:** asymptote (depth) — exercised the
  concurrency-convergence path (idempotent re-emit + refresh-on-change),
  fail-open on unreadable config, and the file-on-disk S2 override, not just
  happy paths. Coverage (breadth) — both layers' filters + the producer
  contract + the verifier guard + the real-repo reproduction. Residual risk:
  dashboard still shows unengaged-phase FAILs (documented; iterate 2 follow-up).
