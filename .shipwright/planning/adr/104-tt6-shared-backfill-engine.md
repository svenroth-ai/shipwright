# ADR 104 — TT6 shared `backfill_test_links` engine

- Run-ID: `iterate-2026-07-15-shared-backfill-engine`
- Campaign: `2026-07-15-test-traceability-layers` (sub-iterate TT6, serial #6 of 8)
- Spec: `.shipwright/planning/iterate/campaigns/2026-07-15-test-traceability-layers/sub-iterates/TT6-shared-backfill-engine.md`
  (+ `Spec/test-traceability-across-layers.md` §7, §8, §11 — gitignored)

## Decision

Add a shared, standalone `shared/scripts/tools/backfill_test_links.py` (+ `_lib`
modules `backfill_scan`, `backfill_signals`, `backfill_write`, `backfill_llm`)
that maps existing tests to the FRs they cover — deterministic-first,
LLM-assisted-second — and emits (i) high-confidence `@FR` tag edits into files,
(ii) a `backfill-report.{json,md}` of low-confidence proposals with confidences,
(iii) orphan candidates in three categories. Reuses the frozen shared contracts
(`fr_tag_grammar`, `requirement_model`, the `events_log` resolver); the written
tags feed the TT1 `test_links` collector, which regenerates the manifest. Used by
adopt (TT7) and the retrofit step (TT8).

## Confidence policy (§11-R1, fixed + documented)

Auto-write requires a **deterministic** signal naming exactly ONE live FR:
`path_fr_token` (0.98), `unique_split` (0.95), or `unique_commit` (0.90) — each
≥ the 0.90 auto-write floor. Title-similarity (cap 0.70) and the LLM leg (cap
0.60) may **never auto-write alone**. Tie-break: higher confidence → more
corroborating signals → lexicographically smaller FR id. Two deterministic
signals naming different FRs = a `conflict` (surfaced, never written).

## Orphan categories (§11-R4)

`confirmed_orphan` (explicit tag → removed/absent FR — one record per dead tag),
`possible_orphan` (untagged, strongest signal is a removed/absent FR),
`unmapped` (no signal — never a stale-feature accusation). Orphans are surfaced,
NEVER auto-deleted.

## LLM data controls (§11-R4)

Offline-deterministic by default; opt-in `--use-llm` adjudicates only the
residue. Payload carries only path + title + candidate FR ids (never test
bodies), bounded + validated; output is untrusted (an out-of-set FR is dropped);
CI injects P1's stubbed record/replay adapter (no live call); production uses
explicit GPT+Gemini OpenRouter models.

## External-Plan-Review-Findings (GPT-5.4 + Gemini 3.1 Pro, OpenRouter — succeeded)

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| P1 | High | Multi-FR truncation (auto-write only ONE FR) | accepted-with-reason: each deterministic-unique FR writes independently; two *different* deterministic FRs = a surfaced `conflict` (conservative, never a guess). |
| P2 | High | Brittle source modification | accepted-and-already-done: line-number insertion above the parsed decl, LF/CRLF preserved, covers-comment/decorator idiom. |
| P3 | Med | Destructive edits on a dirty tree | accepted-as-doc: callers run on a dedicated branch (`--dry-run` for preview); noted in the CLI docstring. |
| P4 | Med | Git perf + shell safety | accepted-and-already-done: per-FILE (deduped) `git log`, array-form subprocess (no shell), best-effort + offline-optional. |
| P5 | Low | Jaccard NLP deps | accepted-and-already-done: pure-stdlib token Jaccard, no new deps. |
| P6 | High | removed-FR discovery (removed vs absent vs malformed) | accepted-and-already-done: `parse_frs` reads active + removed; reason distinguishes `fr_removed`/`fr_absent`. |
| P7 | High | "already-tagged skipped" vs orphan detection | accepted-and-already-done: tagged tests are classified (dead tags → confirmed orphan) even though not re-written. |
| P8 | Med | report/manifest stability | accepted-and-fixed: report lists canonically sorted; a re-run is byte-stable (test pins it). |
| P9 | Med | path/split over-mapping | accepted-with-reason: canonical `FR-XX.YY` boundary + `unique_split` requires a single-FR split; RTM `NN-` semantics. |
| P10 | Med | interaction fixtures (conflict, live+dead, …) | accepted-and-fixed: added conflict + mixed live/dead + multi-dead tests. |

## External-Code-Review-Findings (GPT-5.4 + Gemini 3.1 Pro, OpenRouter — succeeded)

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| O1 | High | Python match not tagged unless `import pytest` present | accepted-and-fixed: a deterministic pytest match now inserts a real `import pytest` (after docstring/`__future__`) so it is always tagged (AC1). |
| O2 | High | `"import pytest" in text` substring false-positive → NameError | accepted-and-fixed: AST-based `pytest_bound()` (a comment/docstring mention no longer satisfies it). |
| O3 | Med | LLM gets FR ids, not FR text | rejected-with-reason: the frozen P1 record/replay adapter contract (`_ALLOWED_PAYLOAD_KEYS`, canonical-FR-only) forbids FR text in the payload; the leg is advisory-only. |
| O4 | Med | only `dead[0]` reported for multi-dead tags | accepted-and-fixed: one confirmed-orphan record per dead tag (`Resolution.orphans` list). |
| O5 | Med | removed-only path/commit signal → `unmapped` not orphan | accepted-and-fixed: a signal resolving only to a removed/absent FR now yields `possible_orphan`. |
| O6 | Med | relative `--spec-file`/`--test-root` resolved vs CWD | accepted-and-fixed: resolved against `--project-root`. |
| O7 | Med | single-line-only TS/JS enumeration | rejected-with-reason: consistent with the frozen TT1 `fr_tag_grammar` `_TEST_DECL_RE`; multiline is a grammar-level enhancement, out of TT6 scope. |
| O8 | Med | commit-signal test only injects `commit_frs` | accepted-and-fixed: added a real git-init + events-log integration test exercising `introducing_commit_map`. |

## Coordinator Code-Review Cascade (spec + code + doubt) — round 2

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| C1 | Blocker (CI-red) | CRLF preservation was dead code — `read_text`/`write_text` normalise via universal-newlines + `os.linesep`, so the CRLF test passed on Windows only (green-local/red-Linux). | accepted-and-fixed: `apply_writes` now reads RAW bytes, detects the ending from raw content, and rewrites with `write_bytes` (no `os.linesep`) → byte-identical on Windows + Linux (probed both endings). |
| C1b | Med | Non-UTF-8 source → `UnicodeDecodeError` mid-loop → partial write, no report. | accepted-and-fixed: `apply_writes` is best-effort per file (a non-UTF-8/read-error file is skipped untouched + recorded in `write_failures`); the report is always emitted. New test. |
| C2 | High (false-write) | `unique_split` auto-wrote on a bare `NN-` prefix with zero corroboration — but `NN-` is the Playwright/Cypress execution-ORDER convention on brownfield repos → false coverage. | accepted-and-fixed: gated behind `--repo-follows-split-convention` (default FALSE for the shared engine / adopt); OFF → advisory proposal, ON → auto-write. New tests pin both. |
| C3 | Med | §11-R4 "redact secrets" was unimplemented (verbatim title → OpenRouter). | accepted-and-fixed: `backfill_llm.redact_secrets` scrubs token shapes (GitHub/OpenAI/AWS/Slack/JWT/Bearer/long-hex) from path+title before send; applied in `_run_llm`. New test. |
| C4 | Med | `_TEST_DECL_RE` was a hard-copy with a false "imported lazily" comment (enumerator↔grammar drift risk). | accepted-and-fixed: imported from `fr_tag_grammar` (single source); comment corrected. |
| C5 | Med | `introducing_commit_map` spawned one `git log` per file (O(N) subprocesses). | accepted-and-fixed: ONE `git log --diff-filter=A --name-only --reverse` walk builds the file→introducing-commit map in a single pass. |
| C6 | Low | Multi-FR docstring / possible_orphan tie-break / unused `tag_sources` + dead `n!="priority"` guard / `honoured` not in report / lib placement. | accepted-and-fixed: docstring corrected (distinct deterministic FRs → conflict); tie-break now highest-confidence-then-smallest-FR-id; `tag_sources` + dead guard dropped; `already_tagged` (honoured) + `write_failures` now in the report for the TT7/TT8 feed. The 4 `_lib` modules live in `shared/scripts/lib/` intentionally — the frozen contracts they consume (`fr_tag_grammar`, `requirement_model`, `events_log`) live there. |

## Self-Review (7-item checklist)

1. **Spec Compliance** — pass: implements §7 cascade (a–e), §11-R1 confidence
   gating, §11-R4 orphan categories + LLM data controls, idempotency, never-delete.
2. **Error Handling** — pass: git/subprocess + JSON decode + LLM calls guarded;
   payload validation raises on R4 breach; missing inputs → empty (greenfield-safe).
3. **Security Basics** — pass: R4-bounded payload (no bodies), untrusted output
   allowlist-validated, array-form git (no shell injection), no secrets logged.
4. **Test Quality** — pass: 21 tests incl. all 3 orphan categories, idempotency
   byte-stable, confidence gating, conflict, mixed/multi-dead, CRLF, real git+events,
   and a real cross-component composition with the TT1 collector.
5. **Performance Basics** — pass: O(files) scan; per-file (not per-test) git;
   title Jaccard bounded; LLM touches only the residue.
6. **Naming & Structure** — pass: 5 cohesive modules ≤300 LOC, ruff-clean, no
   dead code, reuses shared frozen contracts.
7. **Affected Boundaries (ADR-024)** — pass: the `@FR` tag boundary (producer =
   engine, consumer = TT1 grammar/collector) has a real round-trip probe (write →
   `build_manifest` → coverage link); events.jsonl read via the `events_log` SSoT
   resolver; report.json is a deterministically-ordered producer for TT7/TT8.

## Confidence Calibration (empirical probes)

- **Probes run:** (1) round-trip write→TT1-`build_manifest`→coverage-link (real
  subprocess); (2) idempotency byte-stability across a re-run; (3) CRLF-preserved
  tag insertion; (4) real git-init + events-log introducing-commit; (5) untrusted
  out-of-set LLM FR dropped.
- **Findings → fixes:** the external code review (a probe of the write boundary)
  found the pytest-import + multi-dead + removed-signal gaps → fixed → the re-run
  suite (a further probe) found no new defects → boundary calibrated (asymptote
  reached).
- **Edge cases not probed (acceptable):** multi-line/`.each` TS test decls
  (consistent with the frozen TT1 grammar — a grammar-level change), non-UTF-8
  source files (read fails loud, not silently miswritten), duplicate test titles
  within one file (documented limitation of the shared `path::name` identity).
