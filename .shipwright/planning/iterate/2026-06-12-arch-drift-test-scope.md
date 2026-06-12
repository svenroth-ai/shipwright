# Iterate: Scope arch-drift checkers to tree-owned decision-drops

- **Run ID:** `iterate-2026-06-12-arch-drift-test-scope`
- **Intent:** CHANGE (modify scoping behavior of existing drift-protection infra)
- **Complexity:** medium
- **Risk flags:** `touches_shared_infra` (`shared/scripts/lib/`), `touches_io_boundary`
  (new `json.loads` consumer of `shipwright_events.jsonl`)
- **Spec Impact:** NONE (framework compliance/test-infra; no application FR or `spec.md`).
  `change_type: compliance`.

## Problem (empirically reproduced)

In an autonomous campaign, independent branches run sequentially and each writes
its gitignored decision-drop to the **shared, main-rooted** `decision-drops/` dir
(durable by design — `/shipwright-changelog` consumes them on `main`). Each
branch commits its own `architecture.md` / `conventions.md` entry **per-branch**
(it ships in that branch's PR, unmerged until the PR lands).

The two **whole-set** arch-drift checkers enumerate every drop in the shared dir
and require each `run_id` to appear in the current tree's docs:

- `shared/tests/test_architecture_md_reflects_arch_impact.py::test_every_arch_impact_drop_has_architecture_md_entry`
  (hard block at F0)
- the Group-F `_check_f5` detective (soft triage finding)

A later sibling branch sees an earlier sibling's drop in the shared dir, but that
sibling's doc entry lives only on the sibling's own unmerged branch → **false
fail**. It does NOT occur in CI: decision-drops are gitignored, so the dir is
absent on the runner → both checkers `skip`.

The F11 gate `check_architecture_documented(project_root, run_id)` is already
immune — it scopes to ONE `run_id` via `records_for_run`.

**Reproduced 2026-06-12** in local `main` (behind `origin/main`): 3 `convention`
drops from the running campaign (`agent-doc-entry-rules`, `triage-tooling-hardening`,
`utf8-churn-merge`) failed the test. All 3 have `adr_id` absent from this tree's
`shipwright_events.jsonl` and absent from both docs → pure unmerged-sibling bleed.

## Root cause

Ownership is not modeled. A drop in the shared main-rooted dir may belong to a
*different* (unmerged) branch. The per-tree, version-controlled
`shipwright_events.jsonl` IS the ledger of runs finalized on this tree's lineage
(an iterate's `work_completed` event carries its `run_id` in `adr_id`, ADR-059).

## Fix

Scope the two whole-set checkers to drops **owned by this tree's lineage**:
`run_id ∈ finalized_run_ids(this tree's events.jsonl)`.

- `events_log.finalized_run_ids(project_root) -> set[str] | None` — run_ids from
  this tree's events.jsonl (`adr_id` + `run_id` fields). Returns `None` when the
  event log is **absent** → ownership unknowable → caller **fails open** (whole-set,
  i.e. the pre-fix behavior; never weaker). Present-but-empty → empty set (strict).
- `architecture_doc.records_in_run_set(records, allowed) -> list[DropRecord]` —
  pure set-membership filter; the set-valued analogue of `records_for_run` (which
  the F11 gate uses for its single run_id).

Wiring (fail-open guard so hermetic `tmp_path` tests with no events.jsonl keep
their current behavior, and CI — where the drops dir is absent anyway — is
unaffected):

```python
owned = finalized_run_ids(project_root)
if owned is not None:
    records = records_in_run_set(records, owned)
```

Both checkers keep the shared `lib.architecture_doc.missing_entries` matching
oracle (the "cannot diverge" contract is on matching, not scoping). Built on top
of `origin/main`'s routing fix (checkers already reconcile both
`architecture.md` AND `conventions.md`).

### Why not "isolated worktrees" (the other proposed option)

Decision-drops resolve to the MAIN repo via `resolve_main_repo_root` **by design**
(durable staging consumed by `/shipwright-changelog` on `main`). Iterates already
run in per-slug worktrees, yet drops still land in the shared main dir — so
isolating worktrees does NOT stop the bleed. The bleed is via the main-rooted
resolver, not shared worktree state. Scoping the checker is the correct fix.

## Acceptance criteria

- AC1: `finalized_run_ids` returns the `adr_id`/`run_id` set from a tree's
  events.jsonl; `None` when the log is absent; skips corrupt lines.
- AC2: `records_in_run_set` keeps only records whose `run_id` is in the allowed set.
- AC3: An **unowned** undocumented arch-impact drop (events.jsonl present, run_id
  absent from it) is **excluded** — the drift test passes and F5 does not fail.
- AC4: An **owned** undocumented arch-impact drop (run_id in events.jsonl) is still
  caught — drift test fails and F5 fails (drift protection preserved).
- AC5: **Fail-open** — with NO events.jsonl, both checkers retain whole-set
  behavior (existing hermetic detective tests stay green; an undocumented drop
  still fails).

## Affected Boundaries

- Consumer of `shipwright_events.jsonl` (`json.loads`) → `touches_io_boundary`
  → Boundary Probe (round-trip a synthetic events.jsonl through `finalized_run_ids`).
- `shared/scripts/lib/` → `touches_shared_infra` → full suite at F0.

## Confidence Calibration

- **Boundaries touched:** events.jsonl reader (`finalized_run_ids`, `json.loads`);
  decision-drop record filter (`records_in_run_set`); Group-F F5 detective; drift
  test.
- **Empirical probes run:**
  - P1 — Reproduced the false-fail in local `main`: drift test `1 failed`, 3
    `convention` sibling drops flagged (agent-doc-entry-rules /
    triage-tooling-hardening / utf8-churn-merge).
  - P2 — Confirmed all 3 run_ids absent from local-main `events.jsonl` (`adr_id`
    count 0) AND from both docs → pure unmerged-sibling bleed (ownership signal
    correct).
  - P3 — Ran the NEW scoped logic against the live local-`main` tree: `owned`
    set = 128 run_ids (`is not None` → fail-open intact), arch-impact 25→21
    (4 bled siblings excluded), `missing == []` → the reported false-fail is
    resolved; all 3 named run_ids excluded.
  - P4 — Boundary Probe (round-trip): wrote a synthetic events.jsonl with
    `adr_id` + `run_id` + a non-run event + corrupt + blank lines; read back via
    `finalized_run_ids` → exact expected set (`test_finalized_run_ids_*`).
  - P5 — Regression: existing 35 group-C/F detective tests + events_log parity
    test green → fail-open introduces no regression.
- **Test Completeness Ledger:** every behavior `tested` (testable ⇒ tested; no
  untestable rows).

  | # | Behavior | Disposition (evidence) |
  |---|---|---|
  | 1 | `finalized_run_ids` absent log → `None` | tested — `test_finalized_run_ids_absent_log_returns_none` |
  | 2 | `finalized_run_ids` empty log → `set()` | tested — `test_finalized_run_ids_empty_log_returns_empty_set` |
  | 3 | `finalized_run_ids` collects `adr_id`+`run_id` (round-trip) | tested — `test_finalized_run_ids_collects_adr_id_and_run_id` |
  | 4 | `finalized_run_ids` skips corrupt/blank lines | tested — `test_finalized_run_ids_skips_corrupt_lines` |
  | 5 | `records_in_run_set` keeps allowed only | tested — `test_records_in_run_set_keeps_only_allowed` |
  | 6 | `records_in_run_set` empty allowed → `[]` | tested — `test_records_in_run_set_empty_allowed_keeps_nothing` |
  | 7 | drift test: unowned undocumented drop excluded (AC3) | tested — `test_unowned_undocumented_drop_is_excluded` + live P3 |
  | 8 | drift test: owned undocumented drop caught (AC4) | tested — `test_owned_undocumented_drop_is_caught` |
  | 9 | drift test green on live repo | tested — `test_every_arch_impact_drop_has_architecture_md_entry` |
  | 10 | F5 owned undocumented → fail | tested — `test_owned_undocumented_drop_fails` |
  | 11 | F5 unowned undocumented → excluded/pass (AC3) | tested — `test_unowned_undocumented_drop_excluded_passes` |
  | 12 | F5 owned documented → pass | tested — `test_owned_documented_drop_passes` |
  | 13 | F5 no event log → fail-open fail (AC5) | tested — `test_no_event_log_fails_open` |
  | 14 | F5 present-empty log → exclude all | tested — `test_present_empty_event_log_excludes_all` |
  | 15 | F5 pre-existing behaviors (corrupt/component/convention/data-flow/unknown/none) unchanged | tested — existing 35 group-C/F tests green |
- **Confidence-pattern check:** *asymptote (depth)* — traced the real mechanism
  (events.jsonl ownership; worktree-resolves-drops-to-MAIN vs
  events-to-self split; origin/main's prior doc-routing fix) and verified against
  live repo data, not just hermetic fixtures. *coverage (breadth)* — both
  whole-set consumers scoped identically; the already-scoped F11 gate left
  untouched; docstrings + `hooks-and-pipeline.md` updated; ruff + parity + LOC/
  bloat checked.
