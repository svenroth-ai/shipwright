# Iterate: atomic-frs U2b-prep - the gates and readers learn the AC-Move-Map before the real cut

Run: `iterate-2026-11-09-atomic-frs-u2b-prep` · Type: feature · Complexity: medium (shared gate code) · Branch: `iterate/atomic-frs-u2b-prep`
Campaign: `.shipwright/planning/campaigns/2026-11-08-atomic-frs-BRIEF.md`. Follows PR #1027 (U2, `fr_split`); precedes PR 2 (the real FR-01.11 cut, with the list of cuts for the operator to approve). Source of the work items: `.shipwright/planning/iterate/2026-11-08-atomic-frs-u2-fr-split.md`, "Review round 2" points 1-4.

## Goal
A criterion that `fr_split` moved (`## AC-Move-Map` in spec.md) must be read as the same criterion by every check that compares two catalogs, and `fr_split` must pick its new FR numbers against what `origin/main` already uses and tell the operator everything the cut copies.

## Measured first (probe tree: the real FR-01.11 cut of AC21-25 -> FR-01.22, committed on a detached checkout of origin/main)
| Check | Before | After |
|---|---|---|
| Keystone AC gate (`check_keystone_ac_gate.py`) | 5 added, 5 removed-with-bindings, 5 unbound; after a first fix attempt 5 "changed" (the criterion digest includes the id) | 0 added, 0 removed, 0 changed |
| Pre-build AC catalog diff (`ac_record.changed_catalog`, feeds Q1/Q2 and the "catalog AC edited or removed that no item names" warning) | 5 changed + 5 removed | none |
| Orphan AC binding gate | clean only when the traceability manifest is regenerated; with the committed (lagging) manifest it reports the 5 old ids as orphaned bindings | unchanged (correct): the gate judges the regenerated manifest, which CI produces; PR 2 must not judge it against a stale one |
| Binding-regression arm | no false positive (the moved id has no base links) | unchanged |

## Design
| Piece | Change |
|---|---|
| `lib/ac_move_map.py` | + `real_moves` (THE one rule the gates share: same AC number, source gone at head, target absent at base, target FR new, one source per target), `moved_catalog`, `aliases`, `split_sources` (pure helpers over the parsed map) |
| `verifiers/_keystone_criteria.py`, `_keystone_ac_digest.py` | `moved_origins` (= `real_moves`) + `moved_digests`; `AcChangeSet.moved` lets the binding check read base links under the old id: a moved criterion is compared under its pre-move id, so same wording = unchanged, changed wording = changed, never removed + added. Move maps are read from the head spec text |
| `lib/ac_record.py` `changed_catalog` | catalog texts of the base are re-keyed through `real_moves` (head's merged move maps) before comparing |
| `lib/spec_chain.py` `ac_history` | the runs under the old and the new id of a moved criterion are one history (either id asks the same question) |
| `lib/fr_change_history.py` + render + CLI | `FrHistory.split_from`: "some criteria of this requirement were moved here from FR-01.11; changes before the split are recorded there" (text and `--json`) |
| `lib/fr_split_report.py` (new) + `tools/fr_split.py` | new FR numbers also checked against `origin/main`'s copy of every spec; the report lists the chosen ids first, each new table row (shows the copied Priority/Basis/Layers) and the test files tagged with the bare source FR |

## Acceptance (framework tooling; no FR row changes - see Spec impact)
1. Keystone gate: a moved criterion with unchanged wording is not added, removed or changed; reworded it is changed; without a move map the same edit still reads as removed + added.
2. The pre-build catalog diff behaves the same (including a two-hop move).
3. `ac_history` of the old and the new id returns the same runs; other criteria are untouched.
4. `fr_history` of a requirement that received moved criteria says where they came from; one that did not says nothing.
5. `fr_split` never picks a FR number that `origin/main` (as last fetched, at the time of the run) already uses; the dry run names the ids, the rows and the FR-level test tags.

## Spec impact
NONE (tooling). Reason code: tooling-only. Catalog gap (how-only), nearest FR-01.10.

## Known limits / left for PR 2
- The manifest used by the orphan gate must be regenerated (CI does); never judge a cut against a committed manifest that lags.
- A moved criterion's *bindings* are not re-judged by the keystone gate (it is "unchanged") nor by `_ac_binding_regression`; `fr_split`'s own conservation check owns that, and it runs only when the operator runs `fr_split`. Tests dropped or untagged by hand AFTER the cut are caught in CI only by the AC coverage ratchet: a criterion left with 0 links, and only if it is not grandfathered in the baseline (the cut renames baseline entries, so a grandfathered criterion stays exempt); a partial drop (3 links to 1) is caught by nothing, exactly like an unmoved unchanged criterion. Decision (doubt review, medium): documented, not widened into this PR. PR 2 runbook: re-run the `fr_split` dry run after any rebase or hand edit of the cut.
- Item 5 holds against the last fetch at the moment of the run: a parallel iterate that mints the same FR number afterwards is not seen. PR 2 runbook: `git fetch origin main` and a fresh dry run right before the push.
- `aliases` / `split_sources` (history readers) trust every map row; a hand-written row can only mislead a history view. The GATES accept only rows `real_moves` accepts (what `fr_split` writes); a row it rejects reads as an ordinary removal + addition. Map rows are append-only once merged (the gates ignore a row once its target is on base; the history views keep using it).
- A one-commit reuse of a freed number as a move target (target existed at base) is not a move for the gates; `fr_split` mints fresh numbers so it never produces one.
- The strict rule is now ONE function; the history readers still use their own lenient helpers by design.
- A move whose target sits in another spec file than its source is resolved by id, not by file; both specs' maps are merged.

## Internal Plan Review
`opus-plan-reviewer` (opus, run late, after the build): no high finding. Medium: the gates' move check was looser than what `fr_split` writes (AC number and target FR not checked) and the rule was written twice. Both fixed in this PR (`real_moves`, one rule, parity test). Low, fixed: `__all__`, slash ids in `ac_history`, the report no longer claims an `origin/main` check when that ref is unreadable.

## Internal Architecture Review
`architecture-internal-reviewer` (opus, brief + spec only): build it; per-reader resolution through the shared helpers is the right size (an operator override per cut and rewriting history ids are worse). Medium, taken as PR 2 follow-ups, not built here: run `fr_split`'s conservation check in CI whenever a diff adds AC-Move-Map rows; confirm a merge-time check rejects a duplicate FR id across specs. Done here: the strict rule is one function, map rows are stated append-only.

## External code review (GPT + GLM, both `revise`, triaged against a closed list)
Fixed: `origin_numbers` lists every spec on `origin/main` itself; the FR-level test file list is no longer cut at eight; the moved-links lookup in the keystone binding check now has a test that fails without it (`evaluate_keystone`); the origin test asserts the exact ids line. Noted, not fixed: the report's table-row lookup depends on `plan()` inserting the spec first (low).
