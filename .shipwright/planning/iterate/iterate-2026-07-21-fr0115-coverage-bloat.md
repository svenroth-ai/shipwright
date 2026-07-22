# Iterate — Reconcile D1/D3 (FR-01.15 coverage) + H2 (bloat ratchet)

- **Run ID:** `iterate-2026-07-21-fr0115-coverage-bloat`
- **Intent:** change
- **Complexity:** medium (history-calibrated; `prior_source: history`, n=20)
- **Risk flags:** none
- **Spec Impact:** **MODIFY** — fold one new acceptance criterion into
  `FR-01.10` (/shipwright-compliance). No new FR is minted: the capability
  (the cross-check audit) already exists; this states one more case it must
  get right. Per `shared/fr-authoring.md` this is a FOLD, not a MINT.
- **Affected FRs:** `FR-01.10` (audit behaviour changed), `FR-01.15` (its
  delivery record corrected and verified by this run).

## Problem

Three open compliance findings. Two of them (D1, D3) are the *same* defect
seen from two angles; the third (H2) is unrelated and mechanical.

### D1 + D3 — the audit cannot see a newly-created requirement

`FR-01.15` ("cross-repo output contract") is reported as never covered (D1)
and never delivered (D3). **Both reports are wrong.** The requirement was
built, tested and merged on 2026-07-14 as PR #368.

Root cause is a mismatch between the component that *writes* the change log
and the component that *reads* it:

| Side | Behaviour | Evidence |
|---|---|---|
| Writer | accepts a change that names a requirement under `new_frs` **alone** as complete linkage | `shared/scripts/lib/fr_gates.py:211` |
| Reader (D1) | counts a requirement covered only via `affected_frs`, and only from an event with `tests.total > 0` | `group_d.py:134`, `:131` |
| Reader (D3) | counts a requirement delivered only via `affected_frs` | `group_d.py:229` |

So a change that *creates* a requirement — the one change that most
certainly delivers it — is invisible to both checks. `FR-01.15` is the only
requirement ever minted this way in 505 events, which is why the defect
surfaced only now.

`evt-edcf1064` carries a second, independent omission: **no `tests` block at
all**, though that run recorded a full green suite. That is missing evidence,
not a misclassification.

The D3 source already blesses the "introduce + deliver in one change" case
(`group_d.py:240-245`), but only honours it when the author *redundantly*
duplicates the ID into `affected_frs` — something the writer never required.
This change completes that intent rather than inventing a new rule.

### H2 — bloat baseline is looser than reality

Five entries record a line count higher than the file's actual size. The
ratchet is therefore slack: each file could grow silently back up to its
recorded number. Tightening is the intended maintenance direction.

## Approach

Each defect is fixed at its own source. Nothing is suppressed, and no
historical record is rewritten in place.

1. **Reader (`group_d.py`)** — D1 counts `new_frs` as coverage evidence
   alongside `affected_frs` (the `tests.total > 0` requirement is
   **retained**, so the TT2 hardening is not weakened). D3 treats the
   minting event itself as the delivery.
2. **Evidence (`evt-edcf1064`)** — append an `event_amended` overlay
   supplying **only** the missing `tests` block. The overlay is append-only,
   keeps the original timestamp, and is itself auditable. `new_frs` is left
   untouched: that classification was correct per the writer's contract.
   Numbers are taken verbatim from that run's own committed
   `shipwright_test_results.json` at `9def6390` — unit 4705/4705 and
   integration 184/184 — never invented.
3. **Baseline** — set the five stale entries to their true line counts
   (plus `group_d.py`'s own new count, since this change edits it).

### Alternative considered and rejected

*Write a fresh `work_completed` event today re-affirming FR-01.15.* Rejected:
it would date May/July work to today and forge the audit trail. The
2026-07-19 iterate rejected the same move for the same reason
(`2026-07-19-traceability-derived-view-miniplan.md`, "Deliberately not done").
The overlay differs — it corrects evidence *at the original timestamp*
rather than fabricating a new delivery.

*Silence D1/D3 via `audit_config.disabled_checks`.* Rejected: it would switch
off two real checks to hide one false alarm, so genuine future gaps would go
unreported too.

## Acceptance Criteria

- **AC1** — A requirement introduced by a tested change is reported as
  covered by that change; D1 no longer flags `FR-01.15`.
- **AC2** — A requirement introduced by a change **that recorded test totals**
  (`tests.total > 0`) is reported as delivered by that same change; D3 no
  longer flags `FR-01.15`. The tested qualifier is part of the rule, not an
  implementation detail — it is stated identically in AC3, in the FR-01.10
  acceptance criterion, and in the D3 finding text.
- **AC3** — The `tests.total > 0` requirement still applies: a change that
  introduces a requirement but ran no tests does **not** mark it covered.
- **AC4** — `evt-edcf1064` folds to carry the real test totals, keeps its
  original timestamp, and keeps `new_frs` unchanged.
- **AC5** — The five stale baseline entries record their true line counts.
- **AC6** — `FR-01.10` gains one acceptance criterion stating the new rule.

## Review (internal code-reviewer + external GPT-5.4 / Gemini 3.1 Pro)

Both external legs returned substantive, non-degenerate feedback. The dispositions
that changed code:

| # | Finding | Disposition |
|---|---|---|
| Internal 1 (M) | The `tested` guard does **not** prove the *minted* requirement was tested — `tests` is the run's whole-suite total. So "keeps D3 non-vacuous / honest" overclaims; what actually survives is a *recording-omission* check. | **accepted.** The strongest finding in the review. Rejected the offered alternative of routing D3 through the manifest link proof — that would duplicate D1's job and contradict D3's reason for being a log-only check. Instead the claim was corrected everywhere it appeared (module docstring, inline comment, test docstring) to state plainly what the guard does and does not buy. The check keeps its worth: a recording omission is exactly what caused this incident. |
| Internal 2 (M) | The fail text still said "never delivered" — a missing-*evidence* state described as missing *work*, sending a reader down the wrong investigation. | **accepted-and-fixed.** Detail and evidence strings now name the real condition ("minted with no test totals recorded and never named in affected_frs since"). This is the same misdirection that cost this iterate its investigation budget. |
| Internal 3 (L) | New crash surface: `tests.get("total")` raises `AttributeError` when `tests` is truthy-but-not-a-dict; `run()`'s blanket except turns it into a synthetic HIGH finding. D4 already guards correctly. | **accepted-and-fixed** in both D1 and D3, pinned by `test_non_dict_tests_does_not_crash_the_checks`. A real latent bug, not hypothetical — union-merged logs are a known shape here. |
| Internal 6 (L) | Test gap: all four new tests omit the manifest, so `refine_d1_covered` returns early and the TT2 link proof — the guard that actually does per-FR work — was never exercised on the new path. | **accepted-and-fixed.** Added `test_d1_still_drops_an_explicit_fr_without_a_passing_link`. It **failed twice** before passing honestly (schema v1, then `collector_version` as int): `load_manifest` is fail-closed, so a near-miss fixture silently disables the proof and the test would have passed for the wrong reason. |
| GPT 2 (M) | Asymmetry: D3's `affected_frs` path has no test gate, so an untested mint that *also* lists `affected_frs` is delivered while an identical one without redundant linkage fails. | **accepted as documented behaviour.** The `affected_frs` path is pre-existing and untouched — the new path is stricter, never looser — so this was not introduced here. Pinned by `test_affected_frs_path_has_no_test_gate` so it is a recorded decision rather than a latent surprise. |
| GPT 3 (M) | `new_frs` might be counted on ineligible (planning / aborted) event types. | **already-addressed, now pinned.** Both checks filter `type == "work_completed"` first. `test_an_ineligible_event_type_never_covers_or_delivers` proves it — and needed a second genuine event, because with no eligible event D1 returns SKIP and the assertion would have passed vacuously. |
| GPT 4 (M) | Nothing asserts the amendment patches only `tests` and preserves `ts` / `new_frs` / target. | **accepted-and-fixed.** `test_a_tests_only_amendment_preserves_classification_and_timestamp` pins exactly that, including `set(target) - set(original) == {"tests"}`. |
| GPT 5 (M) / Internal 9 (L) | The amendment carries no provenance in the durable log — the only record of where 4889 came from lived in this document, beside an overlay that flips an audit from fail to pass. | **accepted-and-fixed.** `record_event.py` drops `--description` for `event_amended`, so the row was written without it. Added an inert top-level `note` naming commit `9def6390` and the arithmetic. `apply_amendments` reads only `type`/`amends`/`fields`, so the key cannot affect folding. |
| Internal 4 / 5 (L) | Stale docstrings that no longer describe behaviour: `test_audit_groups_a_d.py`'s D1/D3 summary, and two `fr_change_history` comments citing "what D1/D3 flag for FR-01.15 today". | **accepted-and-fixed** in all three places. The `fr_change_history` distinction now stands on its own merit rather than on a finding that no longer fires. |
| Internal 7 (L) | `test_links.py` tightened to 277 < limit 300 is no longer a crossing, but kept `state: "grandfathered"`. | **accepted-and-fixed** → `state: "ok"`, matching the existing precedent for a sub-limit entry (`classify_complexity.py`). |
| Gemini 1 (M) / GPT 7 (L) | Revert the extraction — refactoring solely to evade a line ceiling obscures the functional diff; instead raise the baseline to the new actuals. | **rejected-with-reason.** The suggested remedy is forbidden here: raising `current` on an over-limit entry *is* the ratchet the gate exists to block (`anti_ratchet.py`), and both files sit far above the 300 cap under ADR-096. Extraction into a cohesive sub-300 module is this repo's documented pattern for exactly this situation — `_group_d_link_proof.py` was split from `_group_d_traceability` for the same reason and says so. Net effect is a *tightening*: `group_d.py` 449 → 408. Both reviewers were reasoning from general practice without the local rule. |
| Internal 8 (L) | `_check_d3` is now a pass-through, and its docstring claimed "every existing import path keeps working" — but no such caller exists. | **partially accepted.** The false claim is removed. The wrapper is kept for `_check_d1.._check_d5` symmetry in the plan table, which the reviewer explicitly allowed; with 41 lines of headroom regained, the ~8 lines are not scarce. |
| Gemini 2 (L) | Per-event rather than per-FR granularity: an event minting an untested FR while affecting a tested one delivers both. | **accepted as documented behaviour**, pinned by `test_guard_is_per_event_not_per_fr`. Same root as Internal 1. Mints run ~1-in-505 events, so the exposure is small — but it is now stated rather than discovered later. |
| Gemini 3 (L) | Ensure defensive access to `new_frs` on legacy events. | **already-addressed** — both paths use `ev.get(key, []) or []`. |
| GPT 6 (L) | Baseline scope ambiguous: five entries, or six including `group_d.py`? | **accepted-and-clarified** — five entries, `group_d.py` among them; the exact old→new pairs are listed under "Empirical probes run". |

Not accepted as findings: splitting the pure move from the rule change into
separate commits (the F11 verifier checks one atomic commit, so splitting would
fight the project's own contract), and the duplicated test helpers (the
established convention across seven sibling compliance test modules).

## Confidence Calibration

- **Boundaries touched:** the detective-audit reader (`group_d.py` D1/D3), the
  change log (`shipwright_events.jsonl` — one append-only overlay), the
  requirements catalog (`spec.md`, one AC folded into FR-01.10), and the bloat
  baseline. No hook, no phase validator, no merge/churn resolver — so
  `cross_component` does not apply, and the classifier reported no risk flags.

- **Empirical probes run:**
  1. *Is FR-01.15 genuinely undelivered?* Scanned all 505 events — it appears
     exactly once (`evt-edcf1064`, `new_frs`, no `affected_frs`, no `tests`).
     PR #368 shipped it with real contract gates. **The findings were false.**
  2. *Is the convention "mint also lists affected_frs" established?* Counted
     every FR-introducing event: **1 of 1** non-conforming. There was no
     convention to violate — `fr_gates.py:211` accepts `new_frs` alone.
  3. *Is the link-proof the binding constraint?* No — 10 of 15 FRs carry no test
     link, yet only FR-01.15 was flagged. `refine_d1_covered` exempts
     `inferred_legacy` (confirmed in `LEGACY_SOURCES`), so the sole cause was
     the missing `affected_frs`/`tests`.
  4. *Does the audit even fold overlays?* Yes — `group_d.py:435` applies
     `apply_amendments` before the checks. Had it not, the overlay would have
     been inert.
  5. *Does it work on the real repo?* Ran the real reader against the real log:
     **D1 pass, D2 pass, D3 pass, D5 pass.**
  6. *Is the ratchet satisfied?* `anti_ratchet_check.py --worktree` →
     `{"status": "ok", "ratchets": [], "stale": [], "new_crossings": []}`.
  7. *Did my own edits breach a ceiling?* Yes — caught mid-flight:
     `group_d.py` 449→468 and the test module 789→838. Fixed by extraction, not
     by loosening the baseline. Final: 408 and 782, both **below** the recorded
     numbers.

- **Test Completeness Ledger:**

| # | Behavior | Disposition | Evidence |
|---|---|---|---|
| 1 | D1 counts a tested mint as coverage | `tested` | `test_d1_counts_a_tested_mint_as_coverage` — pass |
| 2 | D1 still refuses an **untested** mint (TT2 intact) | `tested` | `test_d1_does_not_count_an_untested_mint_as_coverage` — pass |
| 3 | D3 counts a tested mint as delivery | `tested` | `test_d3_counts_a_tested_mint_as_delivery` — pass |
| 4 | D3 still flags an untested mint (non-vacuous) | `tested` | `test_d3_does_not_count_an_untested_mint_as_delivery` + `test_d3_still_flags_new_fr_with_no_covering_affected` — pass |
| 5 | D3 pass message states the new rule | `tested` | asserts `"tested mint" in d3.detail` — pass |
| 6 | D3 extraction to `_group_d_promise` is behavior-preserving | `untestable` → `covered-by-existing-test` | the 13-test D1/D3 set + full 1299-test plugin suite pass unchanged across the move; reviewer also diffed it line-by-line against `main` |
| 7 | Overlay makes `evt-edcf1064` carry real test totals | `tested` | probe 5 — real reader on real log, D1+D3 flip fail→pass |
| 8 | FR-01.10 gains one AC | `untestable` → `covered-by-existing-test` | requirements-corpus + FR-table-shape integration tests (417) pass on the edited catalog |
| 9 | Five baseline entries tightened | `tested` | probe 6 — `stale: []`, and the recomputation refuses to loosen |
| 10 | The manifest link proof still drops an explicit-provenance minted FR with no passing link | `tested` | `test_d1_still_drops_an_explicit_fr_without_a_passing_link` — pass (added on review; failed twice first) |
| 11 | An ineligible event type covers/delivers nothing | `tested` | `test_an_ineligible_event_type_never_covers_or_delivers` — pass |
| 12 | Asymmetry: `affected_frs` path has no test gate | `tested` | `test_affected_frs_path_has_no_test_gate` — pass |
| 13 | Asymmetry: guard is per-event, not per-FR | `tested` | `test_guard_is_per_event_not_per_fr` — pass |
| 14 | Non-dict `tests` does not crash D1/D3 | `tested` | `test_non_dict_tests_does_not_crash_the_checks` — pass |
| 15 | Overlay patches only `tests`; `ts`/`new_frs`/identity intact | `tested` | `test_a_tests_only_amendment_preserves_classification_and_timestamp` — pass |

0 testable-but-untested. No "could-test-but-didn't". Rows 10–15 were added in
response to review; row 10 in particular closed a gap where the guard that does
the real per-FR work was never exercised.

- **Confidence-pattern check:**
  - *Asymptote (depth):* the two findings were traced to one shared cause
    (reader/writer disagreement) and each defect fixed at its own source — the
    reader in code, the missing evidence by overlay. Probe 4 was the stop
    condition: it proved the overlay is actually read rather than assumed to be.
  - *Coverage (breadth):* both directions of the new rule are pinned (tested
    mint passes, untested mint still fails), so the relaxation cannot become a
    loophole. Full suites run: compliance 1299, shared 4730, integration 417,
    ruff clean — **6446 passing**.
  - *Integration composition:* not required — no `cross_component` machinery is
    touched (no hooks, validators, resolvers, or campaign drain).
  - *Known limit, stated plainly:* D3 can now only fail for an **untested**
    mint. That is deliberate — with `work_completed` meaning the work is done,
    a tested mint is a delivery — but it does narrow D3's reach, and probe 2
    showed this repo mints FRs about once a year, so the check will rarely
    speak. D1 remains the broader guard.
