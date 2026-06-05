# Sub-iterate C2 — triage merge-safety + leak-guard exemption ("like events")

- **Campaign:** 2026-06-05-track-triage-jsonl (sub-iterate C2 of A→E)
- **run_id:** `iterate-2026-06-05-triage-track-c2-churn`
- **Type:** change (framework infra) · **Complexity:** small/medium ·
  **Branch:** `iterate/triage-track-c2` · **Anchor:** `expands_triage: trg-2fb7d3bc`

## Scope (the de-scoped "mirror events" model — Codex-reviewed)

C1 made `triage.jsonl` trackable. C2 makes concurrent merges safe + the leak-guard
correct, **exactly** how `events.jsonl` is handled — including the leak-guard
**exemption** (`_MAIN_TREE_WRITE_EXEMPT`), which is what made the systemic per-tree
producer reroute (old "C3") unnecessary. Pipeline producers write the worktree
copy (shipped via F6); background Stop-hook / `triage_add` main-backlog writes are
exempt durable-log appends (not a branch leak).

## Changes

1. `churn_merge.py`: `TRIAGE_LOG` constant + `CHURN_ALLOWLIST`; `dedup_triage_lines`
   (exact-line, **no** id-collision warning — triage `append`+`status` share an id
   by design); `validate_triage_text` (header present + JSON-per-line).
2. `resolve_churn_conflicts.py`: `_reconcile_triage` (+ `_reconcile_logs` combining
   events+triage) routed unconditionally + in the `--ours` resolvable branch; new
   `triage_invalid` status (exit 4).
3. `.gitattributes`: `.shipwright/triage.jsonl merge=union` (DOGFOOD-only — never
   written to target projects; the resolver is the authority since union lacks dedup).
4. `worktree_isolation.py`: `_MAIN_TREE_WRITE_EXEMPT += (triage.jsonl, .lock)`.
5. `F6.md`: `git add {project_root}/.shipwright/triage.jsonl` + a note.
6. `docs/hooks-and-pipeline.md`: churn-reconciliation table row (SSoT for
   `CHURN_ALLOWLIST`, enforced both-directions by `test_churn_merge_doc_sync.py`).

Bloat hygiene: kept `resolve_churn_conflicts.py` < 300 (docstring trim); split the
pure-logic tests into a new `test_churn_merge.py` (mirrors the source module split),
keeping both test files < 300 — no bloat-exception needed.

## Acceptance criteria

- [x] **C2-AC1.** `.shipwright/triage.jsonl` ∈ `CHURN_ALLOWLIST`; documented in the
      hooks-and-pipeline churn table (both-directions doc-sync test green).
- [x] **C2-AC2.** `dedup_triage_lines` collapses byte-identical lines only and
      **never** warns on shared append/status ids.
- [x] **C2-AC3.** `validate_triage_text` flags missing header / non-JSON / empty.
- [x] **C2-AC4.** Resolver reconciles triage (dedup on no-conflict; **unions
      both sides** on a hard conflict so neither side's items are dropped —
      Codex BLOCKER; `triage_invalid` exit 4 on validation failure: dropped
      header, orphan `status` (append absent anywhere), or duplicate `append`).
      The validator is **order-independent** (two-pass — GPT-5.4 external-review:
      `merge=union` may interleave a status before its append while both are
      present, which must NOT false-fail).
- [x] **C2-AC5.** Leak-guard exempts a tracked main-tree `triage.jsonl` change
      (durable-log append), mirroring the events exemption.

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| `_reconcile_triage` rewrites the merged triage log | every triage reader, WebUI, RTM, audit detectors | `.shipwright/triage.jsonl` |
| `_MAIN_TREE_WRITE_EXEMPT` | the F0/F11 leak-guard | git porcelain paths |

## Confidence Calibration

- **Boundaries touched:** the churn-merge reconciliation of `.shipwright/triage.jsonl`
  + the leak-guard's main-tree exemption set. The triage event schema is unchanged.
- **Empirical probes run:**
  1. *Dedup probe* — `dedup_triage_lines` keeps both shared-id append/status lines,
     emits zero warnings (the events id-collision warning does NOT fire).
  2. *Validate probe* — header/non-JSON/empty all flagged; valid log passes.
  3. *Resolver probe* — git-repo merge: triage deduped on no-conflict; conflict
     auto-resolved (`--ours` + reconcile, not blocking); `triage_invalid` exit 4.
  4. *Leak-guard probe* — a committed-then-modified main-tree `triage.jsonl` is NOT
     flagged by `detect_leak` (exemption works), mirroring the events test.
  5. *Doc-sync probe* — `CHURN_ALLOWLIST` ↔ hooks-and-pipeline churn table congruent
     both directions.
  6. *Regression probe* — full shared suite 2781 passed (1 pre-existing local-only
     arch-md drift, CI-green; unrelated dev_server Windows-sim test).
- **Test Completeness Ledger:**

  | Behavior | Disposition | Evidence |
  |---|---|---|
  | TRIAGE_LOG in CHURN_ALLOWLIST | `tested` | `test_triage_in_churn_allowlist` |
  | dedup exact-line, no shared-id warning | `tested` | `test_triage_dedup_collapses_identical_lines_only`, `test_triage_dedup_does_NOT_warn_on_shared_append_status_id` |
  | validate header/non-JSON/empty | `tested` | `test_triage_validate_flags_missing_header/_non_json_line/_empty_log`, `_accepts_header_plus_json` |
  | resolver dedups triage on no-conflict | `tested` | `test_triage_deduped_and_validated_even_without_conflict` |
  | resolver routes triage conflict (--ours + reconcile) | `tested` | `test_triage_routed_in_churn_only_merge` |
  | triage_invalid status (exit 4) on dropped header | `tested` | `test_triage_invalid_when_header_dropped` |
  | leak-guard exempts tracked main triage write | `tested` | `test_detect_leak_ignores_tracked_triage_log` |
  | CHURN_ALLOWLIST ↔ doc table congruent | `tested` | `test_churn_merge_doc_sync` |
  | `.gitattributes merge=union` (dogfood-only optimization) | `untestable` | `covered-by-existing-test` — git's union is dogfood-only; the resolver (tested above) is the authority |

  0 testable-but-untested.
- **Confidence-pattern check:** *depth* — dedup/validate/reconcile/exemption each
  probed at the boundary (unit + git-integration); *breadth* — allowlist, dedup,
  validate, no-conflict, conflict, invalid, leak-exemption, doc-sync all covered.
