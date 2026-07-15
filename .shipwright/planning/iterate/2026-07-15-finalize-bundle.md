---
run_id: iterate-2026-07-15-finalize-bundle
intent: change
complexity: medium
spec_impact: none
status: draft
campaign: iterate-duration (part 2 of 3)
---

# Iterate Spec — finalize_bundle.py (collapse the finalization LLM round-trips)

## Problem

The `finalize` node measures ~4.1 min in `phase_timings` telemetry. It is slow
from **sequential LLM round-trips**, not slow scripts (the compliance regen
inside `finalize_iterate` is hard-capped at 30s; every other finalize tool is
sub-second). In a typical run the LLM invokes ~6 finalize tools one at a time —
F1 (`artifact_sync`), F3 (`write_decision_drop`), F4 (`write_changelog_drop`),
F5c (`append_iterate_entry`), F5b (`finalize_iterate`), plus the manual F5
test-results write — each a think→build-command→read-output→next turn (~30s of
turn-taking each). That turn-taking is the reducible cost.

Part 1 of this campaign (F0 parallel runner, #371) already cut the F0 gate. This
is part 2.

## Decision considered (Think-Before-Coding)

- **Chosen:** a `shared/scripts/tools/finalize_bundle.py` that takes ONE JSON
  payload (via `--payload-file`) and invokes the existing finalization tools
  **unchanged, as subprocesses, in dependency order** — F1 → F3 → F4(×N) → F5c
  → F5b — reporting per-step and aborting with the NAME of the failed step. The
  LLM authors all content once (into the payload) and takes ~1 turn to run the
  bundle instead of ~5 separate turns.
- **Alternative rejected:** also fold the F5 test-results write and the F2/F3a
  agent-doc bullets into the bundle (full ~6→1 collapse). Rejected for this
  iterate — it gives the bundle a NEW write surface (`shipwright_test_results.json`
  merge + always-loaded-doc appends) on the highest-blast-radius machinery in the
  framework, for the marginal saving of ~1 turn (~30s). The orchestrator-only
  scope captures the bulk of the win (~6→2 turns) at zero new write surface.
  (User decision, 2026-07-15.) The W4 coverage-drop footgun that a safe F5 merge
  would kill is logged as a possible follow-up, not entangled here.

## Scope (orchestrator-only)

`finalize_bundle.py` runs, in order, each step whose section is present in the
payload; it **writes no artifact itself** — every file is produced by the same
unchanged tool as today:

| Step | Tool (subprocess) | Payload section |
|---|---|---|
| F1  | `shared/scripts/artifact_sync.py`            | `artifact_sync` (optional; default ref `HEAD~1..HEAD`) |
| F3  | `shared/scripts/tools/write_decision_drop.py`| `decision` (required) |
| F4  | `shared/scripts/tools/write_changelog_drop.py`| `changelog` (required list; one subprocess per bullet) |
| F5c | `shared/scripts/tools/append_iterate_entry.py`| `iterate_entry` (required) |
| F5b | `shared/scripts/tools/finalize_iterate.py`   | `finalize` (required: `reason` + `event_extras`) |

**Stays a manual Claude step (NOT in the bundle):** F5 (test-results JSON write —
done BEFORE the bundle so F5b's compliance regen reads it), F2 (architecture.md
bullet, conditional), F3a (conventions.md `## Learnings`, conditional), F6 (the
atomic commit + explicit per-path `git add`).

**Two focused tool fixes (user decision, 2026-07-15 — retry safety).** Both
`write_decision_drop.py` (F3) and `write_changelog_drop.py` (F4) are currently
NON-idempotent per run_id (they claim the smallest *unused* `<run_id>_NNN`
counter, so a re-run duplicates the entry). This breaks whole-bundle retry after
a partial failure. Fix: before claiming a new counter, each tool scans existing
`<run_id>_*` drops and returns the existing path if one already holds THIS EXACT
content (dedup) — first-run output is byte-identical, only re-runs change (dedup
instead of duplicate). This also fixes a latent duplicate-entry bug independent
of the bundle (any double-invocation dups today).

## External Review Integration (GPT-5.4 + Gemini 3.1 Pro, 2/2 succeeded)

Approach endorsed as "sound / pragmatic / well-calibrated". Findings integrated:

1. **stdout capture (HIGH):** all subprocesses run `capture_output=True,
   text=True, shell=False`; the bundle emits EXACTLY ONE JSON document; each
   step's captured stdout/stderr is truncated to a bound in the result. A noisy-
   child unit test guards it.
2. **F1 non-bypassable (HIGH):** F1 ALWAYS runs (default ref `HEAD~1..HEAD`);
   the only bypass is an explicit `artifact_sync.skip: true`, documented as
   bypassing the drift gate.
3. **Whole-bundle retry idempotency (HIGH):** addressed by the two tool fixes
   above (NOT by bundle-side cleanup — reviewers explicitly rejected that). The
   integration test forces a failure and re-runs the whole bundle, asserting no
   duplicate artifacts.
4. **artifact_sync exit-code semantics (MED):** drift is detected by PARSING
   `artifact_sync` stdout `drift_detected`, not the raw exit code (a crash also
   exits 1). Unparseable stdout ⇒ F1 tool-error, not drift.
5. **Strict payload schema (MED):** non-empty `run_id`; `project_root` from CLI
   `--project-root` ONLY (payload carries none — no precedence ambiguity);
   unknown top-level keys rejected (typo guard); `changelog` non-empty list;
   `decision`/`finalize` required subfields; `steps.F4` is an aggregate with a
   per-bullet `drops[]` array.
6. **Absolute sub-tool paths (MED):** resolved via `Path(__file__).parent`,
   cwd-independent.
7. **Integration baseline (MED):** both paths start from byte-identical fixture
   repos + the same payload; compare a defined artifact manifest; normalize only
   the parsed non-deterministic fields (event-id, timestamps).
8. **LLM sequencing (LOW):** the doc states the 2-step workflow — write the
   payload file, then run the bundle.
9. **Secrets in event_extras (LOW):** shell=False/argv-list (no shell exposure);
   captured failure output is truncated; doc contract: no secrets in event_extras.

## Design invariants (the landmines)

1. **Do not change what any tool WRITES** — the bundle only changes how many LLM
   turns invoke them. Each tool is called with the SAME argv the SKILL uses
   today. Verified by the artifact-equivalence integration test (AC5).
2. **Order matters for F6 staging** and for F5b: F1 first (abort on drift before
   any write); F5b last (it reads `shipwright_test_results.json` for compliance
   regen + records the `work_completed` event).
3. **Abort-on-first-failure**: a failed step STOPs the bundle before later steps
   run — a clean abort the LLM can fix and retry beats a half-finalized run.
   After the two tool fixes, ALL sub-tools are idempotent per `run_id`, so
   re-invoking the WHOLE bundle after a fix is safe (proven by the retry scenario
   in the integration test — AC-idem).
4. **artifact_sync exit code 1 == drift, not a crash** — the bundle interprets
   exit 1 as "drift detected" (STOP, F1 named) and any other non-zero as a tool
   error.
5. **`--payload-file`, not inline JSON** — robust against Windows/PowerShell
   quoting of a large multi-field payload.
6. **Subprocess via `sys.executable`** (not in-process import) — avoids the
   ADR-045 `sys.modules['lib']` collision + argparse/`sys.exit` global-state
   hazards; mirrors how `finalize_iterate.py` already shells out to
   `update_compliance.py`.

## cross_component / integration coverage (honest note)

The memory plan predicted this would trip the `cross_component` risk flag. It
will **not**: `_CROSS_COMPONENT_PATTERNS` (the SSoT the F11
`check_integration_coverage` gate recomputes from the diff) is filename-driven
and covers merge/churn/event-log resolvers, hooks, phase validators, and campaign
machinery — **not** finalization orchestration; `finalize_bundle.py` matches no
pattern, so the gate returns PASS. We still author a `category:"integration"`
behavior + integration test **voluntarily** (AC5) — the change IS multi-tool
composition and proving artifact-equivalence is the whole point (spirit over
letter). We do NOT expand the pattern SSoT (out of scope; a policy change not
requested).

## Acceptance Criteria (assertion-shaped)

- **AC1-agent:** `finalize_bundle.py --payload-file p.json --project-root R` with
  all five sections present runs the five tools in dependency order and exits 0
  with stdout JSON where `success == true` and every `steps.<F>.status == "ok"`.
- **AC2-agent:** With a payload whose F3 field overflows the 500-char budget (so
  `write_decision_drop` exits 1), the bundle STOPs at F3, does NOT invoke
  F4/F5c/F5b, exits non-zero, and stdout JSON has `failed_step == "F3"` carrying
  the tool's stderr.
- **AC3-agent:** When `artifact_sync` exits 1 (drift), the bundle STOPs at F1
  with `failed_step == "F1"`, `reason` mentioning drift, exits non-zero, and runs
  no F3/F4/F5c/F5b subprocess.
- **AC4-agent:** A payload missing a required section (e.g. no `finalize`) exits
  non-zero with a validation error naming the missing key, BEFORE any subprocess
  runs.
- **AC5-agent (INTEGRATION):** On a real fixture project, the artifacts produced
  by the bundle (decision-drop file, changelog-drop file(s), iterate-entry file,
  `work_completed` event, regenerated compliance MDs) are equivalent — modulo
  non-deterministic event-id/timestamp — to those produced by invoking the five
  tools manually in sequence. `category:"integration"`.
- **AC6-agent:** Each tool's argv is constructed correctly from the payload
  (F3 fields→flags, F4 bullet→`--category`/`--bullet`, F5c→`--entry-json`,
  F5b→`--event-extras-json`+`--reason`), verified via an injected runner that
  captures argv without spawning a process.
- **AC7-agent:** A `changelog` list of N bullets produces exactly N
  `write_changelog_drop` invocations, each with its own category/bullet.
- **AC-idem-tools:** `write_decision_drop` and `write_changelog_drop` return the
  EXISTING drop path (no new file) when re-invoked with the same
  `(run_id, content)` — first-run output byte-identical; a re-run with *different*
  content still gets a fresh counter (multi-ADR / multi-bullet preserved).
- **AC-idem-bundle:** Re-invoking the WHOLE bundle with the same `run_id` after a
  simulated partial failure produces NO duplicate artifacts (decision-drop,
  changelog-drop(s), iterate-entry, event) — asserted in the integration test.
- **AC8-agent:** SKILL.md F-phase references + `docs/hooks-and-pipeline.md`
  document the bundle so future runs use it; the doc drift/consistency tests stay
  green.
- **AC1-user (optional UAT):** the next real iterate's finalize phase visibly runs
  as one bundle call instead of five separate tool turns.

## Verification (medium+)

- **Surface:** `cli` — `finalize_bundle.py` is a CLI tool; no UI/API/DB surface.
- **Runner:** `CI=true uv run --extra dev pytest shared/tests/test_finalize_bundle.py
  shared/tests/test_finalize_bundle_integration.py -q` (unit + the real-tool
  integration test), plus a scripted CLI invocation of `finalize_bundle.py` on a
  fixture payload asserting exit 0 / JSON shape.
- **Evidence path:** `.shipwright/runs/iterate-2026-07-15-finalize-bundle/surface_verification.log`

## Code Review Cascade Dispositions (spec + code + doubt reviewers, opus)

- **AC5 equivalence (spec REJECT) — FIXED:** added `test_bundle_output_equals_the_manual_sequence` — two byte-identical fixtures, bundle vs manual-sequence, manifest compared (decision-drop, changelog bytes, iterate-entry modulo date, event modulo id/ts/session/commit).
- **UnicodeDecodeError in runner (code MED) — FIXED:** `encoding="utf-8", errors="replace"`.
- **Uncaught exception → non-JSON stdout (code MED + doubt LOW) — FIXED:** `main()` catch-all → `{error:"internal"}` exit 3 + `sys.stdout.reconfigure(utf-8)`. Test `test_internal_error_emits_structured_json_exit_3`.
- **F5b signal buried (doubt MED) — FIXED + REBUTTED:** `_lift_finalize_steps` surfaces finalize_iterate's per-step status; rebuttal: not a regression (manual sequence swallows compliance identically; F11 re-checks). Test `test_finalize_steps_surfaced_from_f5b_stdout`.
- **AC-idem-bundle partial-failure (spec + doubt LOW) — FIXED:** `test_partial_failure_then_whole_bundle_retry_recovers_without_dups` (F5b FR-gate reject → F3/F4 wrote → retry dedups) + iterate-entry count assertion.
- **Bloat (code MED) — FIXED:** extracted the pure layer to `finalize_bundle_lib.py`; both < 300 LOC, no coverage loss (tested via `run()`).
- **Unknown sub-object keys + iterate_entry forbidden keys (code LOW) — FIXED:** `_reject_unknown` on decision/artifact_sync; `run_id`/`date` pre-rejected in iterate_entry; docstring softened.
- **Edit-then-retry / event-not-updated / F5c byte-drift (code+doubt LOW) — DOCUMENTED** in F-finalize-bundle.md retry caveats.
- **Changelog dedup run_id-blindness (doubt LOW) — REBUTTED:** F4 drop_dir is worktree-local; one iterate = one worktree = one run_id, so two distinct run_ids never coexist in a worktree's `CHANGELOG-unreleased.d` → collision unreachable.

## Confidence Calibration
- **Boundaries touched:** the bundle's own boundary is the payload JSON file
  (parse) + the subprocess argv/exit-code process boundary. It writes NO artifact;
  `*_config.json`/`*_state.json` are READ only by the sub-tools it invokes.
- **Empirical probes run:** (1) payload→argv round-trip via injected runner
  (argv captured, not spawned) — PASS; (2) drift-abort (stdout `drift_detected`)
  + crash-not-drift — PASS; (3) fail-abort at each of F3/F4/F5c/F5b names the step
  — PASS; (4) real 5-tool composition on disk — PASS; (5) **bundle ≡ manual
  sequence** artifact-equivalence — PASS; (6) whole-bundle retry + partial-failure
  recovery no-dup — PASS; (7) internal-error → one JSON doc, exit 3 — PASS.
- **Test Completeness Ledger:** 42 bundle tests + 6 new idempotency/drop tests;
  every enumerated behavior `tested`; 0 untested-testable. The composition proof
  carries `category:"integration"` (see F5 ledger block).
- **Confidence-pattern check:** depth (each step ok/fail/skip/drift + ordering +
  argv) + breadth (validation, idempotency, retry, encoding, exit codes) +
  **integration composition** (bundle ≡ manual sequence, on real tools).
