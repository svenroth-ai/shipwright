# ADR spec-ref: FR-01.11 AC backfill (t1, req3-05-test-backfill-mono)

Long-form detail for the F3 decision-drop of run `iterate-2026-09-11-t1-iterate-surface`.
Full context, per-AC mapping, and external-review disposition tables live in
`.shipwright/planning/iterate/2026-09-11-t1-iterate-surface-miniplan.md`; this file exists
only because the decision-drop's `--decision`/`--consequences` fields are capped at 500
chars each.

## Decision (full)

Tagged 25 of the 27 unbound FR-01.11 ACs onto existing, already-passing tests in the two
roots t0's seam survey named (`plugins/shipwright-iterate/tests`, `shared/tests`) — **as of
this initial pass; the Addendum below corrects this to 24, since AC12 was later un-tagged
and recorded unbound with a reason instead.** Accepted
a third-root deviation for AC08/AC09 (their real implementation and only existing tests live
in `shared/scripts/tools/tests`, a third already-canonical ADR-044 root) — recorded as
"Exception 3" in `2026-09-11-req3-05-seam-survey.md`, following the exact convention that
survey's own Named Exceptions 1/2 established, and matching t0's own stated recommendation
("(a) accept the deviation... forced by where the behavior lives, not chosen") for the
identical fan-out shape it already flagged for FR-01.20/FR-01.14.

Widened `shipwright_compliance_config.json`'s `traceability.test_roots` to the full ADR-044
root list (it was missing `shared/scripts/tests` and `shared/scripts/tools/tests`) — this is
what let the `test_links` collector's manifest regen see the AC08/AC09 tags at all;
empirically verified via `check_ac_coverage_ratchet.py` before/after (259 → 234 after the
manifest regen alone with the OLD config, meaning AC08/AC09 stayed invisible; 234 → 232 only
after the config fix, exactly the remaining 2 of 27).

Wrote exactly 2 new test functions (not upgrades of existing ones), only where no existing
test drove the behavior at all: AC20's `ac_changed_ids` parameter of
`evaluate_cross_layer` (`test_layer_coverage_ac_only_change.py`), and AC22's
`ARM_SETTING_OFF` end-to-end path through `deliver_pr.py::deliver()`
(`test_deliver_pr.py::test_a_protected_base_with_auto_merge_off_is_reported_not_delivered`).

## Consequences (full)

`shipwright_ac_coverage_baseline.json`'s `unbound` count dropped from 259 to 232 — exactly
the 27 targeted FR-01.11 ACs, verified via `check_orphan_ac_binding.py` to introduce zero
orphaned bindings from the widened config scan.

Bumped `shared/tests/test_record_event.py`'s existing `ADR-092` bloat exception from 501 to
507 LOC (4 unavoidable `@pytest.mark.covers` decorator lines binding AC03/AC04, plus the
`import pytest` line) — same established pattern already used twice for this exact file
(`ADR-092`'s 791→810 bump, `ADR-096`-adjacent precedent elsewhere), noted rather than
silently laundered into a fresh crossing.

`shared/tests/test_surface_verification.py` was NOT bumped: it had no pre-existing ADR
exception (state `grandfathered`, `adr: null`), and the bloat-exception template's own
Ousterhout-Argument requirement ("if you cannot make this argument honestly, do not file the
ADR — split the file instead") could not be honestly satisfied for a flat, independent-test-
function file. Split its 2 newly-tagged tests (AC07) into a new sibling file,
`test_surface_verification_ac07.py`, instead — a mechanical move, not a re-implementation,
verified byte-for-byte behavior-identical before/after via a full green re-run of both files.

Added `shared/tests/test_traceability_config_roots_parity.py` (external code review, glm,
medium) so a future edit to `traceability.test_roots` that silently drops a real ADR-044
pytest root cannot reopen this same gap undetected — it discovers every real root via the
repo-root `conftest.py`'s own `discover_test_roots()` and asserts each resolves inside the
configured scan globs.

`.shipwright/compliance/sbom.md` and `dashboard.md` briefly disagreed on dependency-license
resolution counts after the first `update_compliance.py` regen in this worktree (5 of 12 dev
deps unresolved vs. dashboard claiming 0 unresolved) — root cause was a missing `uv sync
--extra dev` in this fresh worktree (a known, already-documented gap), not anything this
diff's content changed; fixed by syncing dev extras and re-regenerating, confirmed both
documents now agree (12/12 resolved).

## Rejected alternatives (full)

- **Skip AC08/AC09, leave them `unbound`.** Rejected: the campaign's own exit condition
  forbids leaving an AC unbound without a recorded reason, and a real, already-passing seam
  DOES exist for both — recording a "no seam" reason here would be dishonest.
- **Duplicate AC08/AC09's behavior into a new test inside `shared/tests`** (to stay within
  the stated 2-root budget). Rejected: this is exactly the "new harness where one fits"
  violation the binding-seam rule forbids — a duplicate test proves nothing an existing one
  doesn't already prove, and doubles future maintenance for no gain.
- **File a full Ousterhout-argument bloat-exception ADR for `test_surface_verification.py`
  instead of splitting it.** Rejected: the template itself says not to file the ADR when the
  deep-module argument cannot be made honestly, and a flat pytest file with independent test
  functions is not a deep module in Ousterhout's sense.
- **Leave `shipwright_compliance_config.json`'s `traceability.test_roots` unchanged and just
  record AC08/AC09 as "no seam" due to a tooling gap.** Rejected: the gap was a config
  omission (both missing roots are already-canonical ADR-044 pytest roots documented in
  `CLAUDE.md`), not a genuine absence of a seam — fixing the config is the honest resolution,
  not a workaround around it.

## Addendum (2026-09-11) — Stage-1 spec-review REJECT remediation

PR #730's Stage-1 spec-reviewer rejected this run at the campaign's 3f-bis gate on three
findings, all fixed on this same branch (full detail:
`.shipwright/planning/iterate/2026-09-11-t1-iterate-surface-miniplan.md`,
"Stage-1 Spec-Review REJECT" section):

1. **Authorization.** The original text above ("recorded as 'Exception 3'... matching t0's
   own stated recommendation") let t1 read as having self-authorized the 3rd-root deviation.
   t0's recommendation was scoped to t4/t5/t8/t9 only; it did not cover t1. The campaign owner
   (Sven) has since reviewed and accepted the deviation for t1 specifically (2026-09-11) — that
   owner ruling, not t1's own citation, is the actual authority. The AC08/AC09 binding itself
   is unchanged; only the authorization trail was corrected (seam-survey.md Exception 3,
   triage card `trg-ff6ea5f0`).
2. **Internal document consistency.** The seam-survey Exception-3 edit had updated only the
   root-count table, leaving the FR-01.11 row, the t1 Quick-decide note, and the "Flagged
   deviation" paragraph describing the pre-Exception-3 state. All three now agree with the
   table.
3. **FR-01.11/AC12 binding.** AC12 was tagged onto `test_model_tier_config.py` tests that
   prove only its model-configuration clause, not its internal-review-runs-first ordering
   clause (no seam exists for that clause today). The `covers` tags are removed; AC12 is
   recorded `unbound` with a reason (seam-survey.md Named Exception 4), following the
   FR-01.15/AC02 precedent for a conjunctive AC where only one clause is provable. **This
   changes the count in "Consequences" above: 26 of 27 targeted ACs are actually bound, not
   27; `unbound_count` moves 259 → 233, not 232.**
