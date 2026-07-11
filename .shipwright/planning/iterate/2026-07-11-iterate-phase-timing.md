# Iterate: per-phase durations for the WebUI Iterate-Rail (M-Pre-1 iterate half)

- **Run ID:** iterate-2026-07-11-iterate-phase-timing
- **Type:** feature (framework tooling) · **Complexity:** medium
- **Campaign follow-up:** monorepo-wow-usability-2026-07-10 sub-iterate B1 (triage `trg-8efeb3d7`)
- **Spec Impact:** NONE (framework tooling; no app FR) · change_type=tooling
- **Status:** implemented — AC1–AC4, AC6, AC7 met (see Test Completeness Ledger); AC5 deliberately dropped/reconciled (see below).

## Think Before Coding (Karpathy)

**Problem.** B1 gave the *pipeline* rail real per-phase durations (paired
`phase_started`/`phase_completed`). The *iterate* flow was deferred: it writes
exactly ONE timestamped event (`work_completed` at F5b), and its ~20 phases are
LLM-executed SKILL steps, not program-orchestrated boundaries — so there is no
cheap deterministic per-phase timestamp. The WebUI Iterate-Rail (concept §5a/§K3)
is a 5-node display grouping (`scope → build → review → test → finalize`) and
wants real time-per-node.

**Alternatives considered.**
1. *Full per-F-phase emission (~20 paired events).* Rejected — ~40 LLM-emitted,
   imprecise events per iterate; pollutes the tracked log; violates Simplicity-First.
2. *Structure-only mapping layer in webui.* Rejected by the user — leaves iterate
   durations permanently blank.
3. *5 group-boundary marks → one `phase_timings` block on `work_completed`.*
   **Chosen (user-approved).** Matches the 5-node rail exactly, additive, cheap.

**Decision.** The iterate emits a lightweight timing *mark* as it crosses each of
the 5 rail-group boundaries into a gitignored per-run sidecar
(`<run_id>.phase_timings.jsonl`, sibling of the existing `<run_id>.plan.json`).
`finalize_iterate.py` (F5b) reads the sidecar, computes per-group
`{phase, started, duration_ms}`, and folds it — additively — into the single
`work_completed` event. The WebUI reads `work_completed.phase_timings` if present
(partial history degrades gracefully). Group ids reuse the existing SSoT
(`session_plan._PHASE_CATALOG`) so the Plan-Card groups and the durations join.

**Why:** framework produces timing, WebUI renders — same model as pipeline B1.
Aggregation is deterministic (in finalize), so the only agent-driven part is 5
one-line marks; missing marks simply omit that group's bar.

## Acceptance Criteria

- **AC1** — A shared SSoT (`shared/scripts/lib/iterate_phase_groups.py`) defines
  the ordered 5 rail groups (`scope, build, review, test, finalize`), pinned by a
  test to `session_plan._PHASE_CATALOG` so the two never drift.
- **AC2** — A `iterate_phase_timing.py` CLI records a mark
  (`mark <group> --run-id --project-root`) to the gitignored sidecar; first-wins
  per group; rejects unknown group ids and non-canonical run_ids.
- **AC3** — `compute_phase_timings(marks, end_ts)` yields chronological
  `{phase, started, duration_ms}` (last group's end = `end_ts`); non-negative
  `duration_ms`; empty marks → empty list.
- **AC4** — `finalize_iterate.run()` auto-reads the sidecar and folds a non-empty
  `phase_timings` into the `work_completed` event; absent/empty sidecar leaves the
  event unchanged (additive, backward-compatible).
- **AC5** — ~~`record_event.py` accepts `--phase-timings-json`~~ **DROPPED mid-build
  (deviation logged, ADR F3).** Rationale: the manual `record_event` path is only
  the legacy/out-of-band F7 recorder, which the normal worktree flow **skips** —
  `finalize_iterate`'s auto-fold is the *sole* iterate producer, so the manual arg
  has no consumer (YAGNI / Simplicity-First). Adding it would also ratchet the
  785-line grandfathered `record_event.py`. The shared validator
  `normalize_phase_timings` still guards every write (called inside
  `fold_into_event`). External review (GPT-5.4) flagged the spec/impl drift; this
  reconciles the spec to the final decision rather than re-adding dead surface.
- **AC6** — SKILL.md documents the 5 marks + anchors; `.gitignore` ignores the
  sidecar; `docs/hooks-and-pipeline.md` records the new event field + sidecar.
- **AC7** — Framework suite stays green; bloat baseline not ratcheted;
  update-marketplace + cache-sync run at finalize.

## Affected Boundaries (touches_io_boundary)

- NEW producer/consumer: `<run_id>.phase_timings.jsonl` (write: mark CLI; read:
  finalize). → round-trip test required.
- Extended event schema: `work_completed.phase_timings[]` (write: finalize /
  record_event; read: WebUI). → normalizer round-trip test.

## Confidence Calibration

- **Boundaries touched:** `<run_id>.phase_timings.jsonl` sidecar (io_boundary);
  `work_completed.phase_timings[]` event field.
- **Empirical probes run:**
  1. End-to-end CLI (real subprocess, not import): `mark scope/build/finalize`
     with 1s sleeps → sidecar written; `summarize` returned
     `scope≈1113ms build≈1106ms finalize≈111ms` — real wall-clock durations
     matching the sleeps. Bad run_id → exit 2. **Finding:** the exact command the
     SKILL invokes works and produces true durations.
  2. `git check-ignore -v` → the sidecar matches `.gitignore:198`
     (`*.phase_timings.jsonl`) and the durable `<run_id>.json` is NOT ignored
     (tracked). **Finding:** transient/durable split is correct.

- **Test Completeness Ledger** (testable ⇒ tested; 0 untested-testable):

| Behavior | Disposition | Evidence |
|---|---|---|
| SSoT = 5 rail groups | tested | `test_groups_are_the_five_rail_nodes` |
| SSoT pins to `session_plan._PHASE_CATALOG` (drift guard) | tested | `test_groups_pin_to_session_plan_catalog` |
| mark writes sidecar | tested | `test_append_mark_writes_sidecar` + probe 1 |
| mark first-wins per group | tested | `test_append_mark_is_first_wins_per_group` |
| mark rejects unknown group | tested | `test_append_mark_rejects_unknown_group` |
| read skips malformed lines | tested | `test_read_marks_skips_malformed_lines` |
| sidecar path containment (crafted run_id) | tested | `test_sidecar_path_contains_crafted_run_id` |
| compute chronological durations (last→end_ts) | tested | `test_compute_durations_chronological_with_end_ts` |
| compute empty → [] | tested | `test_compute_empty_marks_is_empty` |
| compute non-negative int (clock skew clamp) | tested | `test_compute_durations_non_negative_and_int` |
| normalize accepts valid | tested | `test_normalize_accepts_valid_block` |
| normalize rejects malformed (6 classes) | tested | `test_normalize_rejects_malformed` |
| CLI mark + summarize | tested | `test_cli_mark_and_summarize` + probe 1 |
| CLI rejects non-canonical run_id | tested | `test_cli_mark_rejects_noncanonical_run_id` + probe 1 |
| finalize folds phase_timings into event | tested | `test_finalize_folds_phase_timings` |
| finalize w/o sidecar omits field (backward-compat) | tested | `test_finalize_without_sidecar_omits_phase_timings` |
| fold additive + pre-existing wins + best-effort | tested | `test_fold_into_event_is_additive_and_validated` |
| sidecar gitignored, durable json tracked | tested | probe 2 (`git check-ignore`) |
| SKILL ≤300 LOC + reference linked | tested | `test_kern_skill_md_under_300_loc`, `test_skill_references_link` |
| WebUI renders the durations | untestable | `covered-by-existing-test` — WebUI is a separate repo (this iterate is producer-only; render is a follow-up webui iterate) |

- **Confidence-pattern check:**
  - *Asymptote (depth):* the fold logic is exercised at unit (compute), lib
    (fold_into_event), and integration (finalize→event) levels + a real-subprocess
    probe — the same behavior verified at 4 depths, findings stable.
  - *Coverage (breadth):* every producer/consumer boundary is tested — mark write,
    read, compute, normalize, CLI, finalize fold, gitignore, drift-pin. The one
    `untestable` row (WebUI render) is genuinely out-of-repo, not skipped.
  - *Integration composition:* not `cross_component` (no merge/hook/phase-validator
    machinery touched); no integration-coverage flag required.

## Files (footprint)

- NEW `shared/scripts/lib/iterate_phase_groups.py`
- NEW `shared/scripts/tools/iterate_phase_timing.py`
- NEW `shared/tests/test_iterate_phase_timing.py`
- EDIT `shared/scripts/tools/finalize_iterate.py`
- EDIT `shared/scripts/tools/record_event.py`
- EDIT `plugins/shipwright-iterate/skills/iterate/SKILL.md` (+ `references/F5b.md`)
- EDIT `.gitignore`, `docs/hooks-and-pipeline.md`
