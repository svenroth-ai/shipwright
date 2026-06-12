# Iterate ADR — iterate-2026-06-12-triage-tooling-hardening

Campaign: `2026-06-10-audit-1-auto` · Sub-iterate: `a1-6` · WP9 of the
2026-06-10 deep audit (F30, F19, F31, F29).

## Decision

Four scoped, pairwise-coherent fixes to the triage tooling:

- **F30** — added `phaseQualityRefreshed` to `triage_gc.MACHINE_REASONS` so the
  phase-quality rollup's per-run dismissal churn is GC-able (identical
  decoupled-SSoT miss to the already-fixed `complianceRefreshed`). Added a
  registry-driven forward+reverse-drift meta-test enumerating the producer
  recurring auto-resolve tokens, asserting `MACHINE_REASONS` equals that set in
  both directions.
- **F19** — `apply_gc` now recomputes the droppable set UNDER the lock and
  intersects it with the caller's planned ids. A status flip appended between
  plan and apply (operator/WebUI re-open) makes the item no-longer-churn under
  the fresh plan, so it survives. Intersect (not union) keeps the operator
  consent surface: apply never drops MORE than the dry-run report announced.
  Validation now runs against the effective (actually-dropped) set, under the
  lock.
- **F31 (SECURITY)** — wired `_strip_control_chars` into `title`/`detail`/
  `evidence` (`aggregate_triage._render_item`) and `title`
  (`triage_cli._format_item`), before `_escape_md`. Also tightened BOTH
  `_strip_control_chars` copies to strip C1 controls (0x80-0x9F) in addition to
  C0/DEL (external review, see below). Non-control Unicode (>= 0xA0) preserved.
- **F29** — relaxed the `triage_promote.promote`/`dismiss` existence pre-check to
  tracked-OR-outbox (mirrors `triage.mark_status`). FileNotFoundError still
  raised when NEITHER store exists; the mutation itself still delegates to
  `mark_status`, so no new precedence is introduced.

## External-Plan-Review-Findings (Step 3.5, OpenRouter — openai + gemini)

| # | Provider | Sev | Finding | Disposition |
|---|---|---|---|---|
| G1 | gemini | HIGH | `>= 0x80` preserve leaves C1 (0x80-0x9F) terminal control codes (e.g. 0x9B CSI) executable in a TTY | **accepted-and-fixed** — both `_strip_control_chars` strip C0+C1; cutoff raised to `>= 0xA0`; C1 regression test added |
| O1 | openai | MED | F19 intersect changes behavior subtly; make explicit | accepted-and-fixed — documented in `apply_gc` docstring; added consent-surface test (`test_apply_does_not_drop_item_churned_after_the_consented_plan`) |
| O2 | openai | HIGH | plan/apply contract may drift for callers expecting exact equality | accepted-and-fixed — docstring states the intersect contract; the only callers are `main()` (report is an upper bound) + tests; report wording unchanged (dry-run is the consent surface, apply is same-or-fewer) |
| O3 | openai | MED | meta-test needs a stable token registry, not ad-hoc enumeration | rejected-with-reason — no shared registry exists today; extracting one is a cross-producer refactor beyond WP9. The meta-test enumerates the canonical recurring tokens with provenance comments and guards BOTH drift directions, which closes the F30 gap without scope creep |
| O4 | openai | MED | historical `triage.jsonl` may carry legacy token casings | rejected-with-reason — tokens are emitted by code (exact literals), not free text; no migration of stored data in scope; GC is exact-equality by design (human reasons must survive) |
| O5/G-mid | both | MED | centralize the sanitizer at one display boundary | rejected-with-reason — the two `_strip_control_chars` copies pre-date this iterate (documented mirror). Both are now updated in lockstep + cross-referenced in docstrings; a shared-module extraction is a separate refactor (Surgical-Changes) |
| O6 | openai | MED | test detail/evidence ANSI + multiline | accepted-and-fixed — aggregator test covers title+detail control chars and C1; evidence is now stripped via the same path |
| O7 | openai | LOW | bidi/invisible Unicode still passes | rejected-with-reason — threat model is ASCII/C1 escape injection into a TTY (the audit's exact scenario). Bidi spoofing is out of scope and documented here |
| O8/G-f29 | both | MED/LOW | F29 dual-presence precedence + atomicity | accepted-and-fixed — added dual-presence test; precedence/atomicity are owned by `mark_status` (residence-derived, single-lock append), which promote/dismiss delegate to; pre-check only gates existence |
| O9 | openai | LOW | lookup matrix: tracked-only / outbox-only / both / neither | accepted-and-fixed — tests cover outbox-only, tracked-only-with-outbox-present, dual-presence, and neither-exists for both lib + CLI |
| O10 | openai | LOW | reconcile with PR #182 `triage_cli.py` structure | accepted-and-fixed — branched from current main (carries #182's UTF-8 stdout pin); the title strip folds into the existing `_format_item`, untouched the `_ensure_utf8_stdout` path |
| O11 | openai | MED | planned-vs-effective mismatch should not hard-fail | accepted-and-fixed — `_validate_after` runs against the EFFECTIVE set, so a re-opened (surviving) item is never flagged "dropped id still present"; no benign concurrency turns into a failure |
| O12 | openai | LOW | output sanitization vs stored-data normalization boundary | rejected-with-reason — output-only sanitization is intentional (the raw JSONL is the audit log; normalizing at ingestion would mutate stored history). All human-facing readers (md + CLI) use the sanitizer; documented |
| G2 | gemini | MED | newline/tab strip could break detail/evidence readability | accepted-as-handled — `_strip_control_chars` explicitly allow-lists `\n`/`\t`; markdown `_escape_md` collapses them for single-line bullets afterward (existing behavior, preserved) |
| G3 | gemini | MED | recompute-under-lock expands the critical section (large file contention) | rejected-with-reason — `triage.jsonl` is a compaction target (this very tool keeps it small); GC is a manual maintenance CLI run rarely, not a hot path; the lock is the SAME one all appends already take briefly. Tail-only-parse optimization is premature (Simplicity-First) |
| G4 | gemini | LOW | PR #182 rebase missing from explicit steps | accepted-as-handled — branched from current main; verified #182's pin is present |

## Self-Review (Step 3.6 — 7-item)

1. **Spec Compliance** — PASS. All 4 findings (F30/F19/F31/F29) fixed; all 5
   spec ACs met (GC-token meta-test, concurrent re-open survives, control-char
   title sanitized in both surfaces, outbox-only promotable/dismissable, suite
   green / no new bloat crossing).
2. **Error Handling** — PASS. F29 keeps FileNotFoundError (neither store) /
   KeyError (unknown id) / ValueError (bad state) contract intact; F19
   validation runs against the effective set so it never false-fails on a
   concurrent re-open.
3. **Security Basics** — PASS. F31 strips C0+C1+DEL control chars from every
   attacker-influenceable rendered field (title/detail/evidence + launchPayload)
   in BOTH output surfaces; C1 hole found by external review and closed; threat
   model (TTY escape injection) documented, bidi explicitly out of scope.
4. **Test Quality** — PASS. TDD (all new tests confirmed red first); tests use
   `tmp_path` fixtures, never the live `.shipwright/triage.jsonl`; cover both
   library and subprocess CLI paths; the meta-test guards both drift directions.
5. **Performance Basics** — PASS. F19 recompute under the lock parses a file
   this tool itself keeps compact; GC is a rare manual CLI, not a hot path.
6. **Naming & Structure** — PASS. `effective_drop_ids` / `fresh_drop_ids` are
   descriptive; the two sanitizers stay mirrored + cross-referenced; no dead
   code, no premature abstraction.
7. **Affected Boundaries** (ADR-024) — PASS. Producer = background producers
   writing `triage.jsonl` (`phase_quality/_triage_bundle`, `triage_bundle`,
   `append_triage_item` outbox path); consumers = `triage_gc`, `aggregate_triage`
   (→ `triage_inbox.md`), `triage_cli`, `triage_promote`. Round-trip probes run
   (see Confidence Calibration).

## Confidence Calibration (Step 3.8 — empirical probes)

Boundary: `.shipwright/triage.jsonl` (+ gitignored outbox) ↔ rendered surfaces.

Probes run:
- **F31 producer→render round-trip:** appended a title with a real ANSI escape
  (`\x1b[2J`), BEL (`\x07`), OSC (`\x1b]2;...\x07`) → asserted rendered
  `triage_inbox.md` AND `triage_cli list` stdout contain NO raw escape. Finding:
  initial fix passed C0 but a follow-up C1 probe (`\x9b` CSI, `\x84` IND) still
  leaked → fixed (cutoff `>= 0xA0`) → re-probed C1 → clean. Two consecutive
  clean probes (C0+C1, then non-ASCII-preservation) → asymptote reached.
- **F31 non-ASCII preservation probe:** umlaut/CJK/em-dash title → asserted
  survives both surfaces (no over-stripping). Clean.
- **F19 concurrent re-open probe:** status flip appended between `plan_gc` and
  `apply_gc` → asserted the re-open survives with `status==triage`; complement
  probe (item churned after the consented plan) → asserted it is NOT silently
  dropped. Both clean → asymptote reached.
- **F30 phaseQualityRefreshed round-trip:** dismissed via the producer token →
  `plan_gc` lists it as droppable; human-reason variant kept. Clean.
- **F29 lookup-matrix probe:** outbox-only / tracked-only-with-outbox-present /
  dual-presence / neither-exists → all behave (promote/dismiss succeed where an
  item resolves; FileNotFoundError only when neither store exists). Clean.

Edge cases not probed (acceptable):
- Bidi / zero-width Unicode spoofing — out of the F31 threat model (TTY control
  escape), documented (review O7).
- Stored-data normalization — intentional output-only boundary (review O12).
- Lock contention under a multi-MB `triage.jsonl` — GC keeps the file compact;
  not a realistic state for this maintenance CLI (review G3).

Asymptote: reached — the only probe that found a bug (C1) was fixed and
re-probed clean, then a further independent probe (non-ASCII) also found
nothing.

## Code Review Cascade (Step 3.7)

- Internal reviewer cascade: `delegated_to_orchestrator` (runner has no Agent
  tool; the campaign orchestrator spawns spec-reviewer → code-reviewer →
  doubt-reviewer after Build).
- External LLM code review: see `External-Code-Review-Findings` below.

## External-Code-Review-Findings (Step 3.7 external, OpenRouter)

Diff fed was source-only (217 LOC); tests reviewed separately (171 passing).

| # | Provider | Sev | Finding | Disposition |
|---|---|---|---|---|
| C-O1 | openai | MED | no tests in the diff → ACs unimplemented | **rejected-with-reason** — false positive: the diff was source-only by design; the tests (meta-test, F19 reopen, F31 sanitize, F29 outbox) exist and pass (171 green). |
| C-O2 | openai | MED | sanitizing `evidencePath` is scope overreach beyond title/detail | **accepted-as-intentional** — `evidencePath` renders into a TTY-visible code span in `triage_inbox.md` (same injection surface), and the Step-3.5 plan review (O6) explicitly endorsed sanitizing evidence. Stripping control bytes never removes legitimate path chars (printable ASCII / Unicode survive). Kept + documented here. |
| C-O3 | openai | LOW | `_triage_path`/`_outbox_path` are underscored internals → tight coupling | **rejected-with-reason** — these are the established intra-package convention in `shared/scripts/tools` (`triage_cli.py` already imports `_triage_path`/`_outbox_path`/`_append_ids_at`; `mark_status` itself uses them). Mirroring `mark_status` exactly is the spec's instruction. Regression tests cover both code paths. |
| C-G1 | gemini | — | truncated/unstructured output (model reasoned out loud, no findings) | no-action — no actionable structured finding emitted. |
