# Iterate ADR — D1: gitignored per-tree triage outbox + reroute + union reader

- Run-ID: `iterate-2026-06-08-outbox-delivery-d1`
- Branch: `iterate/outbox-delivery-d1-reroute`
- Complexity: medium · Risk flags: `touches_io_boundary`
- Campaign: `2026-06-08-triage-outbox-delivery`

## Decision

Introduce `.shipwright/triage.outbox.jsonl` — a per-tree, GITIGNORED transient
buffer. Idle-main background producers (plugin-sync Stop hook, compliance
audit, `triage_add`) route their appends/dismisses there instead of the tracked
`triage.jsonl`; the shared reader returns the tracked ∪ outbox UNION so Python
consumers still see background findings immediately. This kills main-tree drift
at its source (the tracked log stays byte-clean on idle main). The D2 sweep
folds the outbox into the iterate PR branch and GCs it.

Key invariants implemented:
- Outbox shares the ONE canonical lock (`triage.jsonl.lock`) — producer-append
  and the D2 sweep serialize (Codex Q4 data-loss invariant).
- Routing is BRANCH-based (`should_route_to_outbox` = `current_branch ==
  default_branch`), NOT `is_worktree` — the runner is on the main checkout on
  an `iterate/*` branch and must write the tracked log. Any git error → False
  (fail-safe = tracked).
- `to_outbox: bool = False` added to the 3 write APIs; default preserves all
  prior behavior. `read_all_items`/`_iter_raw_lines` always return the union.
- The outbox is ALREADY gitignored by the `/.shipwright/*` wildcard (no `!`
  re-include); a documentation-only comment was added OUTSIDE the managed
  congruence-checked block. D3 propagates intent to adopted repos.

## Affected Boundaries (ADR-024)

- Producer: the 3 rerouted producers + the existing 3 write APIs.
- Consumer: ALL `read_all_items` / `_iter_raw_lines` callers. Audited for
  read-vs-rewrite assumptions (external review #3). Found and fixed ONE
  rewrite-from-union hazard: `triage_gc` (`plan_gc`/`apply_gc`/`_validate_after`)
  read the union but rewrote the tracked path → would FOLD outbox into tracked.
  Now GC is tracked-only via `_iter_raw_lines_at(_triage_path)` + a
  tracked-only resolver. `reconcile_triage` + `churn_merge` operate on the
  literal tracked path (a git merge driver / drift folder) — unaffected.
  Read-only consumers (RTM, aggregate, promote/dismiss CLIs) correctly gain
  union visibility.
- Real round-trip probe run: producer→outbox file→union reader (all fields,
  CRLF, non-ASCII). See Confidence Calibration.

## External-Plan-Review-Findings

| # | Sev | Finding (source) | Disposition |
|---|-----|------------------|-------------|
| 1 | High | Assumes `.shipwright/*` ignored everywhere; could leave outbox tracked in repos without it (OpenAI) | accepted-and-fixed — added an explicit `git check-ignore` startup probe TEST (`test_triage_outbox_gitignored`); D3 owns adopted-repo propagation (out of D1 scope, noted). |
| 2 | High | Branch-name proxy weak: local work on main routes to outbox; detached/custom-default fall back to tracked (OpenAI) | accepted-with-tests — detached HEAD / non-git / custom-default already fail-safe to tracked (tested: `test_should_route_non_git_is_false`). "Local manual work on main → outbox" is the INTENDED behavior for D1 (idle-main background mitigation); the union reader keeps the item visible and D2 sweeps it. Documented as a deliberate trade-off. |
| 3 | Med | Union changes the shared-reader contract for every consumer (OpenAI) | accepted-and-fixed — full caller audit done (see Affected Boundaries); GC hazard fixed; kept the always-union contract (simpler than a mode flag for the 3-consumer surface) but GC/reconcile use tracked-only resolvers. |
| 4 | Med | Lock discipline must cover idempotent + status, not just append (OpenAI) | verified — all 3 mutations take the SAME canonical lock; dedup-scan + append are in one critical section; `test_idempotent_concurrency_under_lock` + cross-process tests cover it. |
| 5 | High | Cross-file last-status-wins by file order can let an older outbox state override a newer tracked state (OpenAI #5 + Gemini #1) | accepted-and-fixed — EMPIRICAL PROBE reproduced it (outbox-append clobbered tracked-dismiss back to `triage`). Fix: two-pass resolver (appends first, then statuses) + ts-primary ordering with file-order tiebreaker. Regression tests `test_tracked_status_wins_over_outbox_append`, `test_outbox_status_wins_over_tracked_append`, `test_cross_file_status_resolves_by_timestamp`. |
| 6 | Med | `mark_status` write-target rules for tracked-only / outbox-only / both unspecified (OpenAI) | accepted-and-fixed — write target is the explicit `to_outbox` arg; id-existence is union-aware; tested all three (`test_mark_status_finds_outbox_id_via_union`, cross-file precedence tests). |
| 7 | Med | Compliance dismiss moved to outbox may change downstream visibility pre-sweep (OpenAI) | accepted-with-rationale — union reader gives consumers the dismiss immediately (no sweep dependency for visibility); compliance suite (371 tests) green; on a branch the dismiss goes tracked (ships in PR). |
| 8 | Med | Out-of-scope producers (drift/phase-quality/etc.) can still drift on main (OpenAI) | accepted-as-scoped — D1 spec names exactly 3 producers; documented they can adopt `to_outbox` later. D1 is a partial-but-correct mitigation, not a claim of total drift elimination. |
| 9 | Low | Outbox missing-file / partial-line handling (OpenAI) | verified — readers treat missing outbox as `[]`; first append creates atomically; corrupt-line tolerance shared with the tracked reader. |
| 10 | Med | Malformed/truncated outbox line could break the union read (OpenAI) | verified — `_iter_raw_lines_at` skips JSONDecodeError lines with a warning (same tolerance as tracked); not a hard fail. |
| 11 | Low | Gitignored outbox = less review visibility / unbounded local accumulation (OpenAI) | accepted-as-scoped — D2 sweep+GC owns retention; documented as accepted interim state. |
| 12 | Low | "git error → tracked" is the wrong-direction fallback for a drift-mitigation change (OpenAI) | accepted-as-rationale — fail-safe MUST preserve today's behavior (a misroute to outbox on a real worktree would DROP a PR-bound finding). Tracked is the safe default; CI/reconcile remain authoritative for drift. |
| (G2) | Med | `triage_add` on main silently disappears manual work into the ignored outbox (Gemini) | accepted-with-rationale (mirrors #2) — intended for idle-main; visible via union; D2 sweeps. Operators who want a tracked manual card branch first (every `iterate/*` writes tracked). |
| (G3) | Med | D1-without-D2 = items live indefinitely in local ghost-state, lost on cleanup (Gemini) | accepted-as-campaign-sequencing — D2 immediately follows D1 in the stacked chain; documented. |

## External-Code-Review-Findings

External code-review leg run on the diff (OpenRouter). Internal reviewer
cascade (`spec-reviewer`→`code-reviewer`→`doubt-reviewer`) is
`delegated_to_orchestrator`.

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| C1 | High | `read_all_items` sorted status events by `str(ts)`; a malformed/null/int ts could outrank a later valid status (OpenAI) | accepted-and-fixed — `_ts_key` only honors a real `str` ts; malformed → `""` → sorts earliest (treated as oldest, never overrides a later valid status). Regression test `test_malformed_ts_status_does_not_override_valid_later`. |
| C2 | Med | `test_cross_file_status_resolves_by_timestamp` wrote a headerless tracked file — unrealistic shape (OpenAI) | accepted-and-fixed — test now creates the base item via `append_triage_item` (header present, asserted) before appending raw status lines. |
| C3 | Low | `test_union_is_tracked_then_outbox_order` asserted only `len==2`, not order (OpenAI) | accepted-and-fixed — now asserts `[ids] == [tracked_id, outbox_id]`. |
| C4 | — | Gemini's reasoning-out-loud trace self-corrected mid-sentence ("NO wait… runs entirely in Pass 1") and raised no concrete finding | no-action — confirms the two-pass logic is correct. |

## Self-Review (7-item)

1. **Spec Compliance** — PASS. AC1–AC4 implemented + tested; 3 named producers
   rerouted; union reader; outbox gitignored.
2. **Error Handling** — PASS. `should_route_to_outbox` try/except → fail-safe
   tracked; missing-outbox → `[]`; corrupt-line tolerated; `mark_status` raises
   on truly-unknown id across the union.
3. **Security Basics** — PASS. No new external input; JSONL written with the
   same atomic fsync+lock; no secrets; outbox is local + gitignored.
4. **Test Quality** — PASS. RED-first (import error → green); boundary probes
   (round-trip, CRLF, non-ASCII); cross-file precedence regression; GC
   outbox-fold guard; branch-routing tests.
5. **Performance Basics** — PASS. Reader does 2 file scans + 2 in-memory passes
   over the same lines; no N+1, no unbounded growth introduced by D1 (D2 GCs).
6. **Naming & Structure** — PASS. `OUTBOX_FILE`, `_outbox_path`,
   `_write_path`, `_append_line`, `should_route_to_outbox`,
   `_iter_raw_lines_at` — names state intent; no dead code.
7. **Affected Boundaries** — PASS. Producer/consumer identified (above); REAL
   round-trip + cross-file probes run; GC consumer hazard found + fixed.

## Confidence Calibration (touches_io_boundary — mandatory)

Boundary: `.shipwright/triage.{jsonl,outbox.jsonl}` serialized JSONL.

Probes run (real, non-mocked):
- Round-trip producer→outbox→union reader, all fields (`test_round_trip_outbox_all_fields`).
- CRLF-terminated outbox line tolerated (`test_outbox_crlf_lines_tolerated`).
- Non-ASCII title round-trip (round-trip test).
- Cross-file precedence probe A (outbox-append + tracked-dismiss) → FOUND BUG →
  two-pass fix → re-probe clean.
- Asymptote pass: probe B (outbox-dismiss early + tracked-promote late) → FOUND
  ordering bug → ts-primary fix → re-probe clean.
- Probe D (same-ts collision across files) → file-order tiebreaker correct, no
  finding. Probe E (tracked-only behaves as pre-D1) → no finding. Two
  consecutive clean probe rounds → **asymptote reached**.
- GC outbox-fold probe → FOUND consumer hazard → tracked-only GC fix → clean.

Edge cases NOT probed (acceptable):
- Concurrent producer-append + D2 sweep under the shared lock — D2's scope
  (the lock invariant is in place; D2V is the empirical concurrency gate).
- Adopted-repo gitignore propagation — D3's scope.

Asymptote reached: TRUE (3 distinct bugs found by probes, each fixed and
re-probed; final two probe rounds clean).

## Review Cascade Remediation (Stage-3 adversarial review, 2026-06-08)

A Stage-3 adversarial review of the D1 diff raised 2 HIGH + 2 LOW. All four
accepted-and-fixed in follow-up commit on `iterate/outbox-delivery-d1-reroute`
(`Run-ID: iterate-2026-06-08-outbox-delivery-d1`). This supersedes plan-review
finding #6 (which had `mark_status` write-target = the explicit `to_outbox`
arg): the arg is REMOVED; the write target is now RESIDENCE-DERIVED.

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| HIGH-1 | High | `mark_status` wrote the status to the caller's `to_outbox` file while id-existence was union-aware. A dismiss could land in the TRACKED log while the item's `append` lived only in the gitignored OUTBOX → (a) on a tree without that outbox the status silently dropped → a dismissed item RESURRECTED; (b) an orphan status in the tracked log on idle main → `validate_triage_text`/`_reconcile_triage` reject it → unhealable pull-block. Reachable via the compliance producer + the runner's main-checkout branch-switch. | **accepted-and-fixed** — `mark_status` is now RESIDENCE-DERIVED. Under the canonical lock it probes the item's `append` id in tracked (`_iter_raw_lines_at(_triage_path)`) ∪ outbox (`_iter_raw_lines_at(_outbox_path)`) via `_append_ids_at`; `to_outbox = (id in outbox_ids) and (id not in tracked_ids)` (TRACKED-PREFERRED in the post-sweep/pre-GC overlap so the flip ships in the PR and GC drops the outbox copy). The `to_outbox` PARAM is removed from the signature; the ONLY caller passing it (`triage_bundle.py` compliance dismiss) dropped the arg. This auto-routes EVERY producer's status writes (drift resolve, sbom, test-evidence, github resolve, f0.5) safely by residence with no per-producer edit. Regression: `test_mark_status_residence_outbox_no_tracked_orphan` (split/resurrection guard — status in outbox, no tracked orphan, union resolves dismissed), `test_mark_status_residence_tracked_preferred_on_overlap`, `test_mark_status_has_no_to_outbox_param`. |
| HIGH-2 (F3) | High | With status writes now residence-safe, NEW appends to the tracked log on idle main by SessionStart/Stop background producers still drove the campaign goal ("tracked clean on idle main") to fail. | **accepted-and-fixed** (bounded scope) — rerouted the two genuine idle-main APPENDERS: `check_drift.py` (SessionStart) and `_triage_bundle.py` (phase-quality Stop) now compute `to_outbox = should_route_to_outbox(project_root)` once and pass it to their `append_triage_item_idempotent` calls; their `mark_status` calls need NO change (residence-derived). **Intentionally NOT rerouted: `sbom_generator` / `test_evidence` / `github_triage` / `surface_verification` (f0.5)** — these run in iterate/compliance/CI contexts (not idle-main SessionStart/Stop); their appends correctly ship via the PR through the tracked log, and their STATUS writes are now residence-safe via FIX 1. `plugin_sync_reminder_on_stop` (the original D1 Stop-hook producer) keeps its hardcoded `to_outbox=True` (it is already the idle-main background path). |
| F2 | Low (de-risks D3) | `should_route_to_outbox` returned True on a fresh/no-`origin` repo on `main` (`default_branch` falls back to literal `"main"`), routing background appends to the gitignored outbox with NO PR/sweep delivery path → findings BURIED. | **accepted-and-fixed** — `should_route_to_outbox` now ALSO requires an `origin` remote: `has_origin = run_git(["remote","get-url","origin"], cwd=root, check=False).returncode == 0; return has_origin and current_branch(root) == default_branch(root)`. No `origin` → False → tracked (safe default; keeps no-origin temp test-repos writing tracked, so `check_drift`/`phase_quality` tests in non-git/no-origin temp repos route False → tracked → stay green). Tests updated: `test_should_route_idle_main_is_true` now adds a throwaway `origin`; new `test_should_route_no_origin_is_false`; `test_should_route_iterate_branch_is_false` adds an origin to prove the branch check still gates. |
| F4 | Low | `read_all_items` comment said `` `str(ts)` sorts ISO-8601-Z… `` but the impl uses `_ts_key` (no `str()` coercion). | **accepted-and-fixed** — comment now references `_ts_key` returning the ISO-8601-Z `ts` string (malformed → `""` → earliest). |

**Final `mark_status` residence logic:** under the lock, compute
`tracked_ids = _append_ids_at(_triage_path)` and
`outbox_ids = _append_ids_at(_outbox_path)`; `KeyError` if the id is in
neither; `to_outbox = id in outbox_ids and id not in tracked_ids`
(TRACKED-PREFERRED). The status event is written to the SAME store the item's
`append` lives in — status follows its append.

**Bloat:** `triage.py` kept at its ADR-100 baseline (718 ≤ 719 measured
newlines); the `mark_status` change is net-neutral after docstring trims; the
baseline `current` is NOT bumped.
