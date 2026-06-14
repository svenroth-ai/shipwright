# Iterate Spec — Hook fan-out consolidation (once-per-event guard + session-state phase resolver)

**Run ID:** `iterate-2026-06-14-hook-fanout-dedup`
**Triage anchor:** `trg-721b1765` (rewritten by this iterate)
**Intent:** CHANGE (framework tooling) · **Complexity:** medium · **Spec impact:** none (Claude-Code hooks, no FR)
**Risk flags:** `cross_component` (real — hook fan-out), `touches_io_boundary` (real — hooks.json / events.jsonl / run_config reads). `touches_auth` is a classifier **prose false-positive** (no auth/middleware/supabase path touched) → recorded in `degraded[]`; the diff-driven F11 recompute drops it.

## Problem

Claude Code fires every *enabled* plugin's hooks with **no active-plugin filter**, so each shared cross-cutting hook does its real work N× per event (SessionStart/Stop/PostToolUse ×11–12). Re-measured live on the 12 `hooks.json` (2026-06-14):

- SessionStart: `capture_session_id` / `check_artifact_drift` / `session_start_using_shipwright` ×12
- Stop: `bloat_gate_on_stop` / `plugin_sync_reminder_on_stop` ×12; `audit_phase_quality_on_stop` / `generate_handoff_on_stop` ×11
- PostToolUse(Write|Edit): `check_file_size` / `mark_plugin_edit` ×12 per edit

`audit_phase_quality_on_stop` derives the audited phase from `CLAUDE_PLUGIN_ROOT`
(`phase_from_plugin_root`), so one Stop genuinely audits **11 phases — 10 of which
never ran** — then rewrites the non-engaged FAILs to SKIP. That is the
"audits phases that never ran" smell + 11× the heavy work (6 categories ×
phases + aggregate regen + backlog emit).

**Already handled (do NOT re-fix):** the SessionStart Phase-Quality injection
spam (`capture_session_id` already wraps the injection in `event_once.claim_once`),
and the per-hook self-dedups in `check_drift`, `audit_compliance_on_stop`,
`bloat_gate_on_stop`, `plugin_sync_reminder_on_stop`, and the audit's own
`already_audited`. **Already convergent by design (verified by reading):**
`mark_plugin_edit` (set-idempotent marker — concurrent firings short-circuit on
the set check) and `check_file_size` (upsert-by-`path` marker) — N× fan-out
produces **one** net marker entry, not N.

## Architecture decision (approved 2026-06-14)

**Symmetric, no single controlling plugin.** Keep every shared hook registered in
every plugin (preserves the `test_hook_registry_bloat` "register everywhere"
invariant + robustness across the greenfield **pipeline** AND **iterate** — if any
one plugin is disabled the hook still fires from another). Instead of moving
control into one plugin, wrap each genuinely-redundant hook's real work in a
**fail-open once-per-(event, session) guard** (reuse `event_once.claim_once`),
and make the phase-quality audit resolve "which phase(s) ran" from **session
state** (`shipwright_events.jsonl` + `run_config.current_step`) instead of
`CLAUDE_PLUGIN_ROOT`. Rejected alternatives: single-owner-in-iterate (couples a
framework concern to one phase plugin; brittle if iterate disabled), single-owner-
in-run / new shipwright-core (breaks register-everywhere; new ADR + back-compat).

## Scope

**Add a once-per-event guard (genuine redundant work):**

1. **`audit_phase_quality_on_stop.py`** — after the cheap guards, `claim_once`
   on a Stop+session-scoped path; the single winner resolves the set of
   **engaged** phases from session state and audits each (dedup via
   `already_audited`), then regenerates aggregates + emits the backlog **once**.
   Phase selection no longer uses the winner's `CLAUDE_PLUGIN_ROOT`. Keep the
   "unrecognized plugin root → no-op" gate (foreign-plugin contract) and the
   monorepo-descent guard. **Invariant: UNKNOWN engagement (cfg None) ⟹ audit
   ALL phases, never fewer.**
2. **`generate_handoff_on_stop.py`** — wrap the body in `claim_once`
   (first-wins): the handoff + dashboard regeneration is plugin-independent, so
   11× identical regen → once.
3. **`check_artifact_drift.py`** — `claim_once` the scan + `additionalContext`
   emission so the drift report + remediation message fire once per SessionStart,
   not 12×.

**New shared building blocks:**

4. `event_once.event_claim_path(project_root, event, session_id)` — standardise
   the claim-file location/naming under `.shipwright/.cache/` (DRY; mirrors
   `capture_session_id`'s `sessionstart-<sid>.claim`).
5. `phase_quality.resolve_engaged_phases(project_root)` — the unique canonical
   phases (`PLUGIN_TO_PHASE` values) filtered by the existing, well-tested
   `phase_is_engaged`; fail-open → cfg None returns ALL phases ("audit more").

**Leave unchanged (already convergent) but PIN in the integration test:**
`mark_plugin_edit`, `check_file_size` — assert N× fan-out → one net marker entry.

**Docs + item:** update `docs/hooks-and-pipeline.md` (Hooks Registry: the dedup
behavior + resolver); rewrite `trg-721b1765` to the corrected current state.

## Acceptance Criteria

- **AC-1 (exactly-once / Stop audit):** firing `audit_phase_quality_on_stop`
  across all 11 plugin roots in one session writes findings for the **engaged**
  phase(s) only, regenerates aggregates **once**, and never writes a finding for
  a phase that did not run. (integration + unit)
- **AC-2 (phase from session state, not plugin root):** in a clean fixture where
  only `build` is engaged, the audit targets `build` even when the *winning*
  invocation fires from a different plugin's `CLAUDE_PLUGIN_ROOT`. (unit)
- **AC-3 (fail-open):** `cfg is None` (no/ío-malformed run config) ⟹
  `resolve_engaged_phases` returns the full phase set (audit more, never zero).
  A `claim_once` guard error ⟹ the work RUNS (never silently dropped). (unit)
- **AC-4 (handoff / drift dedup):** firing `generate_handoff_on_stop` ×11 and
  `check_artifact_drift` ×12 in one session performs the write/emit **once**;
  a later (TTL-expired) event re-fires. (integration + unit)
- **AC-5 (robust when first-firing plugin "disabled"):** if the first plugin's
  invocation is skipped, a later plugin's invocation still does the work once
  (no single controlling plugin). (integration)
- **AC-6 (convergence pinned):** `mark_plugin_edit` ×12 and `check_file_size`
  ×12 for one edit yield exactly one marker entry for the path. (integration)
- **AC-7 (register-everywhere preserved):** `test_hook_registry_bloat` stays
  green; no hook is removed from any `hooks.json`. (existing test)

## Affected Boundaries (Step 7 item 7)

| Boundary | Direction | Round-trip |
|---|---|---|
| `.shipwright/.cache/<event>-<sid>.claim` | producer (claim file) | `claim_once` create ↔ TTL re-arm ↔ fail-open create-error → work runs |
| `shipwright_events.jsonl` | consumer (read) | `phase_is_engaged` reads `phase_completed`/`work_completed`/`source` |
| `shipwright_run_config.json` | consumer (read) | `current_step`/`completed_steps`/`status` → engagement; cfg None → fail-open all-phases |
| `hooks.json` ×12 | invariant (no edit) | register-everywhere preserved (AC-7) |

## Plan

- `event_once.py`: add `event_claim_path(project_root, event, session_id)`
  helper (pure path builder). `claim_once` unchanged.
- `phase_quality/_triage_bundle.py` (where `phase_is_engaged` lives): add
  `resolve_engaged_phases(project_root) -> list[str]` (fail-open all-phases on
  cfg None); export from `phase_quality/__init__.py`.
- `audit_phase_quality_on_stop.py`: refactor `main()` — keep enabled/greenfield/
  descent + "unrecognized plugin root → no-op" guards; `claim_once` Stop-scoped;
  winner loops `resolve_engaged_phases`, audits each un-audited phase, single
  `regenerate_all_aggregates` + `emit_phase_quality_backlog` + gc.
- `generate_handoff_on_stop.py`: `claim_once` gate at top of `main()` (after the
  greenfield guard) — losers exit 0.
- `check_artifact_drift.py`: `claim_once` gate around `hook_main(project_root)`.
- `integration-tests/test_hook_fanout_consolidation.py`: real temp git project;
  simulate fan-out per event type; AC-1/4/5/6.
- Unit: new `test_resolve_engaged_phases` cases; new guard tests for handoff +
  drift; **update** `test_audit_phase_quality.py` phase-selection tests to the
  session-state contract (Test-Update-Klausel — behavior intentionally changed).
- Docs: `docs/hooks-and-pipeline.md` Hooks Registry (dedup behavior + resolver).
- `trg-721b1765`: append corrected entry.

## External Plan Review — disposition (2026-06-14, OpenRouter: GPT + Gemini)

Both models rated the core strategy strong ("exceptionally strong, well-calibrated").
Actioned findings folded into the plan:

- **[HIGH] Guard-before-claim ordering** (gpt#2): ALL no-op guards — incl.
  "unrecognized plugin root" — run BEFORE `claim_once`, so a foreign first
  invocation cannot claim and block a later recognized one. → AC-2b + dedicated test.
- **[HIGH] Broaden fail-open** (gpt#5, gem#1): `resolve_engaged_phases` fails open
  to ALL phases not only on `cfg is None` but on ANY insufficient/unreadable
  engagement evidence (events.jsonl missing/corrupt/partial-flush, JSONDecodeError,
  OSError). "Never fewer" holds under stale end-of-session state. → AC-3 broadened + test.
- **[MED] Plugin-root independence of handoff/drift** (gpt#3, gem#2): audited —
  `generate_handoff_on_stop` resolves via `resolve_project_root()` + session_id
  (no `CLAUDE_PLUGIN_ROOT`); `check_artifact_drift` likewise. Claim placed AFTER
  the cheap local guards (greenfield / canon-skip), before the heavy work.
  Drift inputs are identical across all 12 invocations (input-deterministic), so
  claim-around-`hook_main` cannot drop work a sibling would have done.
- **[MED] Concurrency** (gpt#8, gem): integration test spawns the hook as N
  PARALLEL subprocesses and asserts exactly-one side effect (real fan-out atomicity).
- **[LOW] Path-safety** (gpt#9, gem#4): `event_claim_path` sanitises `event`/
  `session_id` to a safe filename charset; test asserts the path stays under
  `.shipwright/.cache/`.
- **[INFO] Call-site audit** (gpt#6): only `audit_phase_quality_on_stop:79` uses
  `phase_from_plugin_root` for phase TARGETING; `audit_compliance_on_stop:195`
  uses it only as an `is None` recognition gate → no mixed semantics post-change.
- **[INFO] Helper contract** (gpt#1): `event_claim_path` is documented as valid
  ONLY for session-unique events (SessionStart/Stop) — NOT PostToolUse (multi-fire)
  without an instance discriminator. PostToolUse hooks are intentionally untouched.
- **[INFO] gitignore + fresh project** (gpt#7/#11): `.shipwright/.cache/` is
  gitignored ✓; `claim_once` already `mkdir(parents=True, exist_ok=True)` →
  fresh-project test path added.
- **TTL** (gem#3): keep `claim_once` default 30 s — comfortably masks one event's
  ~12-hook burst; these events are logically once-per-session anyway.

## Confidence Calibration
- **Boundaries touched:** claim-file producer (`.shipwright/.cache/*.claim`);
  events.jsonl + run_config reads (engagement); no `hooks.json` edits.
- **Empirical probes run:**
  - *Fan-out re-measure* (live, this repo): parsed all 12 `hooks.json` → the N×
    table above (authoritative current state, not memory).
  - *Convergence read-probe*: `mark_plugin_edit.add_path` short-circuits on
    `rel in existing`; `check_file_size._write_marker_entry` filters existing
    entries for `norm_path` before append → both net-one. Confirmed by source.
  - *Engagement reuse*: `phase_is_engaged` already covers event/current_step/
    completed_steps/status + fail-open (cfg None) — pinned by
    `test_phase_quality_engagement.py` (22 cases). The resolver is a thin filter.
  - *Claim primitive*: `event_once.claim_once` first-wins + TTL re-arm +
    fail-open already proven in `capture_session_id` + `test_capture_session_id`.
- **Test Completeness Ledger:**

  | Behavior (this diff) | Disposition | Evidence |
  |---|---|---|
  | `event_claim_path` builds the canonical per-event claim path | tested | test_event_once::test_event_claim_path_shape |
  | `resolve_engaged_phases` returns engaged-only phases | tested | test_phase_quality_engagement::test_resolve_engaged_returns_engaged_only |
  | `resolve_engaged_phases` fail-open (cfg None) → all phases | tested | ::test_resolve_engaged_fail_open_all_phases |
  | audit: single winner audits engaged phase regardless of winning plugin root | tested | test_audit_phase_quality::test_audit_uses_session_state_not_plugin_root |
  | audit: non-engaged phase gets no finding | tested | ::test_audit_writes_no_finding_for_unengaged_phase |
  | audit: aggregates regenerate exactly once across fan-out | tested | integration::test_stop_audit_regenerates_once |
  | audit: unrecognized plugin root still no-ops | tested | ::test_hook_exits_zero_when_plugin_root_unrecognized (updated) |
  | handoff dedup: 11× fan-out → one regen; TTL re-arm | tested | test_generate_handoff_on_stop::test_claim_once_dedups + integration |
  | drift dedup: 12× fan-out → one scan/emit | tested | test_check_artifact_drift_dedup::test_claim_once_dedups + integration |
  | robust when first-firing plugin skipped | tested | integration::test_robust_when_first_plugin_disabled |
  | mark_plugin_edit / check_file_size convergence (one marker) | tested | integration::test_posttooluse_markers_converge |
  | register-everywhere preserved | tested | test_hook_registry_bloat (unchanged, green) |

  0 testable-but-untested. No `could-test-but-didn't`.
- **Confidence-pattern check:** *Depth (asymptote)* — the guard is ONE primitive
  (`claim_once`) reused at three call sites; correctness at one generalises.
  The resolver is a thin filter over the 22-case-tested `phase_is_engaged`.
  *Breadth (coverage)* — all three event types (SessionStart/Stop/PostToolUse),
  both the dedup path and the fail-open path, and the register-everywhere
  invariant. **Integration composition (cross_component):** the new
  `integration-tests/test_hook_fanout_consolidation.py` drives the actual hook
  scripts across a simulated multi-plugin fan-out in a real git project —
  proving the guard + resolver + register-everywhere compose (the non-dodgeable
  `category:"integration"` ledger row). No web surface (pure-Python hooks) →
  F0.5 `surface=none` with justification.
