# Per-FR, evidence-driven Layers promotion — never a sweep

Campaign `req3-04c-ac-identity-wave2`, sub-iterate p3.5
("promote-layers-per-fr"), run
`iterate-2026-09-08-p3-5-promote-layers-per-fr`. Monorepo-only — the
WebUI's own counterpart is a separate, already-tracked card (`trg-8d6f4b90`),
same correction pattern already applied to P3.2/P3.4.

## Context

All 20 FRs in `.shipwright/planning/01-adopted/spec.md` carry
`required_layers_source=inferred_legacy`. P3.5's job: build the mechanism
that autonomously promotes one FR's binding to `explicit` wherever its own
test-coverage evidence justifies it — per requirement, one-way, never a
sweep — and hands back to an operator only for the three named undecidable
cases, reusing `diff_risk_recheck`'s process contract (exit 0/3/other) and
its two load-bearing properties (never self-ack; validated on content, not
presence), rather than inventing a new escalation channel.

## Decision

Three new library modules plus two CLIs:

1. `lib/layer_promotion.py` — pure evaluator (`evaluate_fr`), no I/O. Mirrors
   P3.3's own `"ok"` eligibility contract (`_layer_coverage_binding`) rather
   than importing it (different plugin/shared trees, ADR-045). FR-level only
   (D12) — an FR's coarse `coverage`/`tests` is the gate, not a per-AC audit.
2. `lib/layer_promotion_ledger.py` — the durable, append-only, per-FR
   decision record (`.shipwright/compliance/layer_promotion_ledger.json`,
   tracked, not a derived snapshot). Every entry carries an evidence
   fingerprint (sha256 over `coverage`+`tests`).
3. `lib/fr_layer_cell_writer.py` — surgical single-cell spec.md editor
   (idempotent, requires the canonical header, refuses an ambiguous target).
4. `tools/promote_required_layers.py` — the automated CLI. Reads the manifest
   + ledger, decides every active FR independently, writes only what a
   `promote` decision names. Exit `0`/`3`/other mirrors `diff_risk_recheck`.
5. `tools/record_layer_promotion_decision.py` — the HUMAN-ONLY CLI. Only
   writer allowed to record `demoted`, or to override a prior decision.
   Hardcodes `decided_by="operator"` — no flag exists to say otherwise.

Real run against this repo's own manifest: 5 of 20 FRs promoted
(FR-01.06/07/09/13/14 → explicit `unit`), 13 skipped (no evidence yet), 2
escalated (FR-01.01, FR-01.11 — see below). Verified idempotent (a clean
rerun writes nothing and reports the same two escalations) and correct on a
hand-reverted-cell rerun (re-escalates `contradicts_recorded_decision`
rather than silently re-promoting).

## Why FR-01.01 and FR-01.11 escalate (real evidence, not a fixture)

Both carry a `unit`-layer test link that shows `executed=pass` in this
repo's own `test-traceability.json` AND a second `unit`-layer link that
shows `executed=not_run` — a genuine "absent ≠ green" case at the SAME layer
that is already otherwise green. This is exactly the round-1 external
code-review fix (see below): the corrected predicate escalates on ANY
bound-but-unexecuted test, not only one that outranks the highest passing
layer. Before that fix, the first real run of this tool had silently
promoted both — a bug caught by the review, not by this unit's own design.

## External-Plan-Review-Findings (Step 3.5, GLM + OpenAI/codex, verdict
revise both)

| # | Source | Severity | Finding (short) | Disposition |
|---|---|---|---|---|
| 1 | GLM | high | Autonomy is a governance decision, not an implementation detail — get the SPEC's marking amended | rejected-with-reason — the sub-iterate spec itself (not this unit) already carries the amendment: its own "This runs autonomously" section states the SPEC's ⚠️ warns against a sweep, not against autonomy, and is the operator-authored mandate this unit executes against |
| 2 | GLM | high | Re-run after a partial promotion + ack can't distinguish a consistent existing promotion from a contradiction | accepted-and-fixed — every ledger entry carries an evidence fingerprint; `already_explicit` (re-derived from the LIVE spec.md, not the possibly-stale manifest) is the actual consistency check, and only a live/ledger mismatch escalates |
| 3 | GLM | high | Data model unspecified — where bindings live, who writes them, downstream consumer impact of `required_layers_source` flipping | accepted-and-fixed — `fr_layer_cell_writer.py` is the single writer; `layer_promotion_ledger.py` is the single record; consumer impact analysed below (P3.3's own gates) |
| 4 | GLM | medium | "Cannot silently demote" has no mechanism — whatever produced `inferred_legacy` could still rewrite the manifest | accepted-and-fixed — the manifest (`test-traceability.json`) is never written by this mechanism; `spec.md`'s cell is the actual binding, and once explicit this tool never revisits that FR again except to detect and escalate a hand-reverted cell |
| 5 | GLM | medium | CI evidence trust boundary unstated — could the run promote on self-attested green tests | accepted-with-tracking — this is a pre-existing property of the whole `test-traceability.json` contract every P3.3 layer-coverage gate already shares, not unique to this consumer; filed as `trg-fcd48a56` for a dedicated cross-cutting look rather than inventing a weaker or stronger trust model unilaterally inside one consumer |
| 6 | GLM | medium | Undefined gap between promote/escalate (binding without highest layer, a failed test, stale evidence) | accepted-and-fixed — a failed test is a decided `no_evidence_yet` skip (openai's high #2 below), and the per-FR report (`skipped`/`promoted`/`escalated`) names every outcome, none silent |
| 7 | GLM | low | "Most escalating" threshold undefined | accepted-and-fixed — fixed at >50%, reported as `sweep_signal_warning`, informational (exit code unchanged) |
| 8 | GLM | low | Ack fingerprint scope must be per-FR/per-stop, not per-run-global | accepted-and-fixed — the evidence fingerprint is per-FR (`coverage`+`tests` of that one node) |
| 9 | openai | high | Implementation approach too abstract — no canonical fields, evidence lookup, or write path named | accepted-and-fixed — see Decision above |
| 10 | openai | high | A failed (not absent) test is unaddressed | accepted-and-fixed — `test_a_failing_test_is_a_decided_non_promotion_not_an_escalation`: a `fail` is a decided non-promotion, never an escalation |
| 11 | openai | high | CI evidence not bound to commit/manifest revision | accepted-with-tracking — same as GLM #5, `trg-fcd48a56` |
| 12 | openai | medium | Partial-run + exit-3 rerun ambiguity | accepted-and-fixed — same as GLM #2 |
| 13 | openai | medium | No deterministic precedence rule for "highest observable layer" | accepted-and-fixed — `highest_ok_layer` mirrors P3.3's own pinned rank order exactly, tested against unrecognised-label inputs |
| 14 | openai | medium | No integrity control on promotion evidence itself | accepted-with-tracking — same as GLM #5, `trg-fcd48a56` |

## External-Code-Review-Findings, round 1 (Step 3.7 item 2, GLM + OpenAI/codex,
verdicts openai=reject, glm=revise — run over the pre-commit working diff,
zero commits existed yet on this branch)

| # | Source | Severity | Finding (short) | Disposition |
|---|---|---|---|---|
| 1 | openai | high | AC-scoped bindings ignored — a bare `@FR` tag can promote even with an unbound AC | rejected-with-reason — D12 and the sub-iterate spec's own line 5 ("FR level stays the coarse gate") explicitly settle this: FR-level coverage is the enforcement unit, AC-level is an ADDITIONAL index on top, never a precondition. Accepting this finding would re-litigate a decision the spec text forecloses |
| 2 | openai | high | Bound-but-absent test only escalates when ranked ABOVE the highest passing layer — a same/lower-rank absent binding is ignored | accepted-and-fixed — `evidence_ambiguous` is now unconditional (`bool(absent)`); the rank comparison was removed entirely. This is the fix that correctly turned FR-01.01 and FR-01.11 from silent (wrong) promotions into escalations, verified against this repo's real data |
| 3 | openai | high | Existing required layers never re-verified as `ok` before promoting (e.g. `unit` ok + `integration` MISSING still promotes both to explicit) | accepted-and-fixed — new `unverified_required` check; a new skip reason `existing_required_layer_not_verified` when an already-required layer lacks fresh `ok` coverage |
| 4 | openai | high | Ledger/human-CLI is a NEW escalation channel, not literal reuse of `diff_risk_recheck`'s ack file; no fingerprint re-validation | rejected-with-reason (partially accepted) — `diff_risk_recheck`'s ack is a single global, CI-supply-chain-specific file with no schema for a per-FR `required_layers` value, no permanent history, and no `promoted`/`demoted` distinction; the sub-iterate spec's own D5 ("permanent per-requirement decision") cannot be expressed in a run-scoped ack. The two LOAD-BEARING PROPERTIES are mirrored exactly (never self-ack; content-not-presence validation), which is what the spec asks to carry over — not the literal file. Partially accepted: `layer_promotion_ledger.fingerprint_drifted()` is now a real, tested, consumed check (`promote_required_layers.py` reports it for every FR with a prior ledger entry), closing the practical "recorded but unread" gap without abandoning the domain-appropriate design |
| 5 | openai | medium | `spec.md` written before the ledger entry — a ledger-write failure leaves an explicit cell with no durable record | accepted-and-fixed — reordered to ledger-first (`write_ledger` must succeed before `write_promotion_files` runs); a failure now strands a RECORDED-but-unwritten promotion, which the next run detects and escalates, never the reverse |
| 6 | openai | medium | Unrecognised layer name reporting `"ok"` is silently promotable | accepted-and-fixed — `_unrecognised_ok_layers` now escalates `layer_undeterminable` |
| 7 | glm | high | Collision escalation (`is_collision`) checked BEFORE the ledger — a recorded `demoted` never clears it; re-runs escalate forever | accepted-and-fixed — the `is_collision` branch now checks the ledger first; a recorded `demoted` clears it permanently, a recorded `promoted` (via the human CLI) clears it if the spec agrees |
| 8 | glm | medium | First-match FR-id resolution in `fr_layer_cell_writer.write_layers_cell` and `record_layer_promotion_decision._find_node` is ambiguous for a collision fan-out | accepted-and-fixed — both now refuse (raise / `SystemExit`) when more than one match exists; the human CLI's `--action demoted` (which never targets a specific node) remains the one way to clear a collision, `--action promoted` on an ambiguous id is rejected outright |
| 9 | glm | medium | `evidence_fingerprint` recorded but never consumed anywhere | accepted-and-fixed — same fix as openai #4 above (`fingerprint_drifted`) |
| 10 | glm | medium | Same ordering bug as openai #5, from the ledger-durability angle | accepted-and-fixed — same fix |
| 11 | glm | low | `test_decided_by_is_always_operator_never_configurable` greps source text, not behavior | accepted-and-fixed — replaced with `pytest.raises(SystemExit)` on an unrecognised `--decided-by` flag, plus a genuinely behavioral test (`promote_required_layers` against a `demoted`+green-evidence fixture: exit 3, nothing written) |
| 12 | glm | low | Unrecognised layer name with a bound `not_run` link silently degrades to a skip instead of escalating | accepted-and-fixed — `bound_but_absent_layers` counts every layer name, canonical or not; combined with fix #2's unconditional check, this now escalates correctly |
| 13 | glm | low (informational) | Sweep-signal downgrade from a 4th exit code to a report is a conscious, already-documented deviation | acknowledged, no action — GLM notes the comment already marks it as deliberate |

## External-Code-Review-Findings, round 2 (verdicts openai=reject, glm=revise
— run over the actual round-1 fixes)

| # | Source | Severity | Finding (short) | Disposition |
|---|---|---|---|---|
| 1 | openai | high | AC-scoped bindings ignored (repeat of round 1 #1) | rejected-with-reason — same D12/spec-line-5 citation, unchanged |
| 2 | openai | high | Ledger/CLI is a new escalation channel (repeat of round 1 #4) | rejected-with-reason (further strengthened) — see the narrowing fix (#3 below), which is a STRONGER content check than a hash fingerprint alone could give |
| 3 | openai | high | `already_explicit` alone treats a HAND-NARROWED explicit cell (e.g. `unit, integration` → `unit`) as a clean, consistent skip — a real silent-demotion path the ledger exists to catch | accepted-and-fixed — new `fr_layer_cell_writer.live_required_layers()` reads the actual current cell contents; `evaluate_fr`'s `promoted`-ledger branches now escalate `contradicts_recorded_decision` whenever the live set no longer covers what the ledger recorded, even while still nominally "explicit" |
| 4 | openai | spec | Fingerprint drift reported but not enforced — a stale/fabricated decision still clears the run | accepted-with-tracking (superseded by #3) — the narrowing check above is the concrete, TESTED enforcement both reviewers asked for; it is stronger than a hash comparison (a hand-typo that keeps the SAME set of layers would not move a fingerprint's underlying coverage/tests either, so a fingerprint check alone would not have caught #3's actual bug) |
| 5 | openai | medium | `record_layer_promotion_decision.py`'s operator path still wrote spec.md before the ledger (round-1's fix only touched the automated tool) | accepted-and-fixed — same ledger-first reorder applied to the operator CLI |
| 6 | glm | medium | Non-atomic `open(..., "w")` spec.md writes — a crash mid-write truncates the document | accepted-and-fixed — `fr_layer_cell_writer.atomic_write_text()` (tmp + `os.replace`, mirroring the ledger's own write), used by both the automated tool and the operator CLI |
| 7 | glm | medium | `new_required` unions EVERY currently-ok layer, not just the highest observable one — over-binds a layer the FR never asked for, which then HARD-gate-fails if that layer later regresses | accepted-and-fixed — promotion now widens by `required_before \| {highest_ok}` only, matching the spec's own singular framing ("the binding includes the highest observable layer") |
| 8 | glm | low | `bound_but_absent_layers` only recognises the literal `"not_run"` sentinel — a missing/`None`/unrecognised `executed` value is silently ignored | accepted-and-fixed — any enabled link whose `executed` is not exactly `"pass"` or `"fail"` now counts as absent |
| 9 | glm | low/test | No test forces a write-ordering failure or pins the union-vs-highest-only semantics | accepted-and-fixed — behavioral tests added for both (ledger-write-failure leaves spec.md untouched, on both CLIs; the 3-ok-layer widening test) |

## External-Code-Review-Findings, round 3 (verdicts glm=approve, openai=reject
— contradictory; resolved by disposition below, not by a further round)

| # | Source | Severity | Finding (short) | Disposition |
|---|---|---|---|---|
| 1 | openai | high | AC-scoped bindings ignored (3rd repeat) | rejected-with-reason — unchanged, D12 |
| 2 | openai | high | Ledger/CLI vs. `diff_risk_recheck` reuse (3rd repeat) | rejected-with-reason — unchanged; round 2's narrowing-detection fix is the concrete answer already given |
| 3 | openai | high | CI evidence provenance (3rd repeat) | accepted-with-tracking — unchanged, `trg-fcd48a56` |
| 4 | openai | medium | TOCTOU: `compute_promotion_writes` reads content once, `write_promotion_files` later overwrites with that STALE snapshot — a concurrent maintainer edit between the two is silently discarded | accepted-and-fixed — `compute_promotion_writes` now also returns each file's original content at plan time; `write_promotion_files` re-reads immediately before writing and raises `ConcurrentSpecEditError` (refuses, never clobbers) if the file moved on since |
| 5 | openai | medium/test | Fixtures assert promotion with no AC/CI-provenance data (repeat, tied to #1/#3) | no separate action — covered by #1/#3's dispositions |
| 6 | glm | medium | Deviation from literal ack-reuse not "substantiated in the diff" (the ADR file itself was excluded from the code-review diff) | acknowledged, no action — a deliberate scoping choice (documentation excluded from a CODE review diff); the real PR review sees this ADR alongside the code in the same commit |
| 7 | glm | low | Empty/missing `spec_path` node silently reaches a misattributed `IsADirectoryError` inside `compute_promotion_writes` | accepted-and-fixed — rejected immediately and by name inside `compute_promotion_writes` |
| 8 | glm | low | `live_required_layers`/`live_explicit` are keyed by DISPLAY id — a collision fan-out spanning different `spec_path`s could compare against "whichever file iterated last" | partially fixed, corrected Stage-4 code-review, P3.5 post-push round (this disposition previously overstated the fix) — the collision branch's `ledger_action == "promoted"` arm no longer consults the `live_required_layers` PARAMETER, closing that one comparison. `already_explicit` (`required_layers_source`, read from the SAME per-fr_id-keyed `plan_promotions.live_explicit` dict) is NOT fixed and has the identical display-id-keying hazard: a collision fan-out spanning two `spec_path`s still resolves `already_explicit` to whichever node's file `plan_promotions` iterated last. Left as-is (accepted, not fixed) for the same reason as before: documented unreachable in practice today (the operator CLI already refuses an ambiguous `--action promoted`, so a collision can only ever carry a `demoted` ledger entry, and the `promoted` arm this affects is therefore dead code on every real path) — a real fix needs `plan_promotions` to key BOTH values by the manifest's own unique key, not by display id, which is a wider change than this defect's live impact currently justifies |
| 9 | glm | low | Row re-render normalises hand-applied column padding on the edited row | rejected-with-reason — the row is rebuilt only from its own already-parsed cells; this repo's real spec.md already uses canonical single-space padding, confirmed by the real run's diff touching only the intended cell text, nothing else |
| 10 | glm | medium/test | No test for the empty-`spec_path` path or a partial spec-write failure | accepted-and-fixed — behavioral test added for the empty-`spec_path` operational failure; the concurrent-edit test above covers the partial-write-safety property directly |

**Not re-reviewed for a 4th round.** Round 3's remaining `reject` (openai)
rests entirely on the three repeated, considered rejections (#1–#3) this ADR
already stands behind with written reasoning, not on a new, unaddressed
defect — the same "disputed, not fixed" pattern P3.4's Tier-3 T5 finding
used. GLM's independent `approve` on the SAME diff, plus every genuinely new
bug either reviewer raised across all three rounds now fixed and tested
(narrowing detection, ledger-before-spec on both CLIs, atomic spec.md
writes, promote-by-highest-only, absent-detection robustness,
concurrent-edit refusal, empty-spec_path rejection), is the actual
convergence signal this campaign's review process is built to produce.

## Stage-1 spec-review finding — the `demoted` veto was not actually exitable

Campaign orchestrator's Stage-1 spec-reviewer (delegated cascade,
`campaign-mode.md` 3f-bis) REJECTED the diff after the F6 commit, citing spec
L25/L40 ("exitable — an operator ack clears the stop while the flag/evidence
stay reported, so a re-run doesn't hit the same wall forever"). The
`is_collision`-branch `demoted` case already honored this (round-1 finding
#7 above), but the plain non-collision `demoted` branch in
`evaluate_fr` did not: `if already_explicit or predicate_holds: escalate`
re-escalated on EVERY run for as long as the predicate kept holding against
the SAME evidence the operator had already looked at and vetoed — the only
way to clear it was to reverse the veto outright, which defeats the point of
recording one.

**Fix (accepted, one finding, targeted):** `fingerprint_drifted()`
(`layer_promotion_ledger.py`) — already computed for every FR with a prior
ledger entry, but wired as informational-only and explicitly documented as
"a demotion is deliberately evidence-independent, not expected to key off
this at all" — is now the actual gate for a demoted re-escalation. Unchanged
fingerprint since the veto → clean skip (`demoted_consistent`, no
escalation, no promotion). Fingerprint drifted since the veto (or the live
spec.md is explicit despite the veto, unchanged from before) → escalate
again, same `REASON_CONTRADICTS_DECISION` code as every other ledger/live
mismatch — a distinct reason code was considered and rejected: the
underlying claim ("the ledger and the current state disagree about whether
this FR should be explicit") is identical to what that code already means
for the `promoted` branch; splitting it would be a distinction without a
difference for any caller reading the report.

Both stale-vs-fixed states are now pinned as two separate tests, replacing
the single test that pinned the rejected always-re-escalate behavior:
`test_ledger_demoted_with_unchanged_evidence_since_the_veto_is_a_consistent_skip`
/ `test_ledger_demoted_but_evidence_drifted_since_the_veto_escalates_again`
(`shared/tests/test_layer_promotion.py`), and the CLI-level
`test_demoted_fr_with_unchanged_evidence_is_a_clean_skip_writes_nothing` /
`test_demoted_fr_with_drifted_evidence_escalates_and_writes_nothing`
(`shared/scripts/tools/tests/test_promote_required_layers.py`). The
now-dead `predicate_holds` local (superseded by the individual checks it was
built from, already used further down for the non-ledger path) was removed
rather than left unused. `layer_promotion_ledger.fingerprint_drifted`'s own
docstring is corrected to no longer claim a demotion is
"evidence-independent."

**Real-repo effect: none observed.** Neither FR-01.01 nor FR-01.11 (this
run's two live escalations) carries a `demoted` ledger entry, so this fix
changes no observed outcome against this repo's own manifest today — it
closes a latent gap the review caught before an operator ever exercised it.

## Stage-1 spec-review round 2 — the drift-gate needed a predicate, not just a fingerprint

Re-review REJECTED again: the round-1 fix resolved the forever-wall but
introduced a new gap plus a stale citation.

**Finding 1 (accepted, one gap, fixed):** `if already_explicit or
fingerprint_drifted(ledger_entry, node): escalate` re-escalated on ANY
fingerprint change, including drift TOWARD worse evidence. Concrete failure:
an operator vetoes FR-X while green; later a tagged test is deleted
(green → MISSING); the fingerprint differs, so the round-1 code wrongly
escalated even though nothing is promotable and none of the three named
undecidable cases applies — a 4th, unnamed undecidable case, against spec
L11/L21's "expected escalation volume is zero to a handful." **Fix:**
`predicate_holds` (already computed from `highest_ok`, `evidence_ambiguous`,
`unverified_required` for the non-ledger path) is reinstated and AND'd with
`fingerprint_drifted(...)`: only drift INTO a state the predicate would now
promote is the genuinely new situation the veto never saw. Drift toward
worse evidence stays the plain decided skip it would be with no ledger entry
at all. New sibling tests pin the regressed-evidence case without touching
the passing-direction tests: `test_ledger_demoted_but_evidence_drifted_toward_worse_stays_a_decided_skip`
(`shared/tests/test_layer_promotion.py`) and
`test_demoted_fr_with_evidence_drifted_toward_worse_is_a_clean_exit_zero_skip`
(`shared/scripts/tools/tests/test_promote_required_layers.py`).

**Finding 2 (accepted, citation fixed):** the F5c summary
(`.shipwright/agent_docs/iterates/iterate-2026-09-08-p3-5-promote-layers-per-fr.json`)
cited `test_demoted_fr_with_green_evidence_escalates_and_writes_nothing`,
deleted in the round-1 fix. Updated to cite the two tests that now jointly
cover "the tool never overrides an operator's recorded demotion":
`test_demoted_fr_with_unchanged_evidence_is_a_clean_skip_writes_nothing`
(unchanged evidence stays a skip) and
`test_demoted_fr_with_drifted_evidence_escalates_and_writes_nothing`
(evidence that newly looks green escalates rather than silently promoting).
Edited directly, not via a re-invocation of `append_iterate_entry.py`: per
`references/F5c.md`, only the paired `<run_id>.test-results.json` evidence
file is byte-immutable; the `<run_id>.json` summary is unconditionally
overwritten (`overwrite=True`) by the tool itself on every append, so a
direct correction changes nothing the tool wouldn't already have done. The
paired `.test-results.json` evidence file itself is left untouched — it is
a byte-immutable historical snapshot of what was true when F5 ran and is
expected to go stale as later fixes rename tests, not a live index.

**Non-blocking note (fixed):** `promote_required_layers.py`'s
`plan_promotions` comment still claimed "a demotion is deliberately
evidence-independent" — the one place round 1 left uncorrected outside
`fingerprint_drifted`'s own docstring. Reworded to describe the
now-consumed behavior.

**Real-repo effect: none observed.** Same as round 1 — neither live
escalation (FR-01.01, FR-01.11) carries a `demoted` ledger entry.

## Stage-2 code-review findings — ledger race, column-index guard, tmp-file race, fingerprint order

Verdict "Approve with changes" (no HIGH findings, non-blocking per protocol),
but two mediums genuinely undermined the "cannot silently demote" guarantee
this sub-iterate exists to deliver, so fixed before Stage 3:

**Medium 1 (accepted, fixed) — ledger race condition.** The load→append→write
sequence in both `promote_required_layers.main` and
`record_layer_promotion_decision.main` had no concurrency guard, while the
LESS load-bearing spec.md write already had one (round-3
`ConcurrentSpecEditError`). Concretely: an operator's `demoted` veto landing
between an automated run's own `load_ledger` and `write_ledger` was silently
overwritten — the automated write wins, the veto never happened, the FR
becomes auto-promotable again with no trace. **Fix:** `write_ledger` gained
an optional `expected_snapshot` (via new `read_ledger_snapshot`), re-reading
the file immediately before the replace and raising the new
`ConcurrentLedgerEditError` if it no longer matches what the caller's
`load_ledger` returned — the same symmetry `write_promotion_files` already
has for spec.md, applied to the ledger itself. Both CLIs now snapshot right
after their own `load_ledger` and pass it through. A sentinel
(`_UNCHECKED`) keeps the check strictly opt-in so every existing test that
does not care about concurrency needs no change.

**Medium 2 (accepted, fixed) — column-index guard weaker than its
docstring.** `_canonical_layers_index` validated the DOCUMENT has exactly
one canonical header, then returned a hardcoded column index — but never
checked the TARGET ROW is actually governed by that header. A canonical id
living only under a second, differently-shaped priority-bearing table
(recognised as a governing header by the general reader, which tolerates
re-ordered/renamed columns because it only ever reads) would get the wrong
cell index applied silently — exactly the "a WRITER that guessed wrong would
corrupt a cell silently" failure the module's own docstring refuses to
risk. **Fix:** `_canonical_layers_index` now also returns the header's own
line number; `write_layers_cell` asserts the target row is below it and that
its cell count matches the canonical header's column count, refusing
otherwise. The now-provably-unreachable "narrower than the Layers column"
branch (dead once cell count is asserted equal to the canonical width) was
removed rather than left as dead code. New test
`test_id_only_under_a_foreign_priority_bearing_table_refuses_to_guess`
(`shared/tests/test_fr_layer_cell_writer.py`), sibling to
`test_two_canonical_headers_refuses_to_guess`.

**Low 1 (accepted, fixed) — fixed tmp-file name race.** `atomic_write_text`
(`fr_layer_cell_writer.py`) and `write_ledger`'s own inline block both used a
FIXED sibling tmp name (`path.name + ".tmp"`): two concurrent writers to the
same target could collide on that path, and one's `finally:
tmp.unlink(missing_ok=True)` could delete the OTHER's in-flight tmp between
its write and its `os.replace`. **Fix:** both now delegate to the existing
shared `lib.atomic_write.durable_atomic_write` primitive (`tempfile.mkstemp`
with a per-call random suffix, plus `fsync`-before-rename durability this
codebase's other config/state writers already rely on) rather than adding a
THIRD hand-rolled copy of the same block — single-sourced, as asked, by
reusing infrastructure that already existed rather than writing a new one.

**Low 2 (accepted, fixed) — fingerprint doesn't canonicalize list order.**
`evidence_fingerprint` canonicalized dict key order (`sort_keys=True`) but
not the order of each layer's test-link list. A traceability re-collection
that emits links in a different order (set iteration, filesystem walk,
parallel collection) with no actual evidence change moved the fingerprint
anyway — and on a `demoted` entry whose predicate still holds, that is a
spurious re-escalation of an operator's veto for no real reason. **Fix:**
new `_canonical_tests` sorts each layer's link list by `(id, path, ac_id)`
before hashing. New test
`test_evidence_fingerprint_is_stable_under_link_list_reordering`
(`shared/tests/test_layer_promotion_ledger.py`).

**Also fixed while in the neighbourhood (cheap, not blocking):**
`fingerprint_drifted`'s docstring now names the `predicate_holds` qualifier
round 2 added, instead of implying ANY drift re-escalates; the
`promote_required_layers.py:199` (then-)error message no longer calls a
ledger-recorded-but-spec-unwritten failure something to "re-run to retry" —
a re-run actually escalates `contradicts_recorded_decision`, not a plain
retry; `record_layer_promotion_decision.py`'s manifest/ledger reads gained
the same `OSError`/`ValueError` → `SystemExit` handling
`promote_required_layers.py` already had for the identical reads. Skipped
(explicitly deferred, per reviewer's "your call"): the `already_explicit`
collision-branch inconsistency and the integration-test readability/
duplication items — neither is a correctness bug and both need more
context than "cheap" to resolve well.

**Real-repo effect: none observed.** The real run against this repo's own
manifest is unaffected: no concurrent writer exists in a single invocation,
no FR id collides across two tables in this repo's spec.md, and no test
link ever reordered between two runs in this session. Full canonical suite
re-run clean (18/18 GREEN, diff-coverage 91% PASS; the same pre-existing,
already-tracked flake `trg-f64d1c27` passed on retry) after the fix.

## Stage-3 doubt-review findings — union-not-narrow, demote wall, TOCTOU spans, own guard

Seven doubts (2 HIGH, 4 medium, 1 low), all genuinely new territory — none a
re-hash of Stage-1/Stage-2. All fixed; none rebutted.

**HIGH 1 (accepted, fixed) — a stale manifest could narrow a hand-declared
multi-layer cell.** `plan_promotions` derived `required_layers_source` from
the LIVE spec.md cell (Stage-2's own fix) but still took the `required_layers`
VALUE straight from the stale manifest. An inferred cell reading
`unit, e2e (inferred)` against a manifest still snapshotting `["unit"]`
(ordinary lag — this tool never regenerates the manifest) silently DROPPED
the hand-declared `e2e` the moment `unit`'s evidence alone justified a
promotion: `required_before` was `{"unit"}`, not `{"unit", "e2e"}`, so nothing
was left unverified and the promotion rewrote the cell to bare `unit`. **Fix:**
new `fr_layer_cell_writer.live_declared_layers` (mirrors
`_requirement_parse._parse_layers`'s tokenizer, ADR-045 independent copy —
`lib/` cannot import the compliance plugin) reads the cell's layers REGARDLESS
of the `(inferred)` marker; `plan_promotions` now unions it into
`required_before` before evaluation. A stale manifest can only under-report
what a live cell already declares, never over-report it, so the union only
ever WIDENS — the same "widen, never narrow" direction the evaluator already
commits to everywhere else. New test
`test_stale_manifest_never_narrows_a_hand_declared_multi_layer_cell`
(`shared/scripts/tools/tests/test_promote_required_layers.py`): the existing
pure `evaluate_fr`-level "never narrows" test
(`test_no_action_ever_removes_a_layer_or_reinstates_advisory_provenance`,
`shared/tests/test_layer_promotion.py`) cannot catch this class of bug —
`node` there is handed in already-built — so its docstring now says so and
points at the CLI-level pin.

**HIGH 2 (accepted, fixed) — `--action demoted` on an already-explicit FR
built a permanent, unfixable wall.** `evaluate_fr`'s demoted branch reads
`if already_explicit or (fingerprint_drifted(...) and predicate_holds):
escalate`. The `already_explicit` arm of that `or` carries no exitability
qualifier — unlike its sibling — and `--action demoted` never touched
spec.md at all, so an operator demoting an FR whose live cell was ALREADY
explicit left it explicit FOREVER: every future run of
`promote_required_layers.py` re-escalates `contradicts_recorded_decision`
for that FR, with no ledger entry able to clear it short of a further
`--action promoted` an operator has no reason to think of. **Fix (my call,
option (a) over refusing outright):** `record_layer_promotion_decision.py`'s
demoted branch now checks the live cell via `is_layers_cell_explicit_live`
and, when explicit, reverts it to `(inferred)` via
`render_layers(current_layers, inferred=True)` — restoring the invariant the
evaluator's exitable branch depends on, computed-then-applied-after-the-
ledger-write in the same order the `promoted` branch already uses. Skipped
for a collision fan-out (ambiguous match, `node is None`): that arm of
`evaluate_fr` never re-escalates a `demoted` entry on `already_explicit` in
the first place (no single per-node cell to attribute a rewrite to), so the
wall does not exist there. New test
`test_demoted_action_on_an_already_explicit_fr_reverts_the_cell_to_inferred`
(`shared/scripts/tools/tests/test_record_layer_promotion_decision.py`),
which also re-runs `evaluate_fr` against the reverted state to confirm the
wall is gone (a plain, exitable `demoted_consistent` skip).

**Medium 1 (accepted, fixed) — TOCTOU guard covered fold→write, not
decide→write.** Three separate reads existed across a promotion's lifetime
(`plan_promotions`'s own read, `compute_promotion_writes`'s independent
re-read, `write_promotion_files`'s pre-write re-read); the
`ConcurrentSpecEditError` guard only ever compared the LAST two. A
maintainer edit landing between the decision-time read and the fold's own
read slipped through undetected. **Fix:** `plan_promotions` now returns the
content it decided against (`dict[str, str]`, one entry per `spec_path`);
`compute_promotion_writes` accepts it as an optional `contents_by_path` fold
base, eliminating the middle read on the real call path entirely (`None`, the
default, keeps every existing direct-decision test's fresh-read behavior
unchanged — no test needed to change).

**Medium 2 (accepted, fixed) — ledger concurrency guard snapshotted from a
separate read than the one that produced the in-memory ledger.** `load_ledger`
and `read_ledger_snapshot` (Stage-2's own fix) were two independent
`read_bytes()` calls: a veto landing between them was invisible to the
returned ledger AND present in the snapshot, so `write_ledger`'s pre-replace
compare matched and the write erased the veto with no trace. **Fix:** new
`_parse_ledger` shared helper plus `load_ledger_with_snapshot`, doing exactly
ONE read. For the residual gap Stage-2's `expected_snapshot` compare alone
still leaves open (its re-read is not atomic WITH the replace — a narrowing,
not a close), the stronger of the reviewer's two offered fixes was taken:
new `ledger_lock_path` + `lib.file_lock.file_lock`, held across the WHOLE
load→decide→write span in BOTH CLIs (`promote_required_layers.py`'s new
`_plan_and_apply_locked`, `record_layer_promotion_decision.py`'s new
`_decide_and_write_locked`), not merely narrowed by a snapshot compare.

**Medium 3 (accepted, fixed) — column-index guard didn't check the row's OWN
governing header agrees with the canonical index.** Stage-2's guard checked
cell count and header position, but a second, SAME-WIDTH, differently-ORDERED
table (e.g. Layers at index 5, Basis at 6, instead of the canonical 6/—)
would still pass both and get the wrong cell silently overwritten. **Fix:**
`write_layers_cell` now also checks `target.layers_from_named_col` and
`cells[layers_idx] == target.layers_cell` — the row's own colmap-resolved
Layers value must agree with what the canonical hardcoded index reads.
Not a perfect solve (a coincidental content match at the wrong index could
still slip through), same best-effort tier as the rest of this guard family.
New test
`test_id_under_a_same_width_reordered_foreign_table_refuses_to_guess`
(`shared/tests/test_fr_layer_cell_writer.py`).

**Medium 4 (accepted, fixed) — the third instance of the concurrency guard,
applied asymmetrically.** `record_layer_promotion_decision.py`'s own spec.md
write (for `--action promoted`, and now for HIGH 2's demote-to-inferred
rewrite) had NO re-read-and-compare guard at all — reads once, writes the
ledger, writes spec.md with nothing checking the file did not change
underneath in between. **Fix:** re-reads immediately before writing and
raises `layer_promotion_apply.ConcurrentSpecEditError` on a mismatch,
mirroring `write_promotion_files` exactly (import reused, not a fourth
hand-rolled copy).

**Low (accepted, fixed) — ledger-first ordering's failure mode reds the
whole integration-test root, not just a local escalation.** Neither the ADR
nor the exit-2 message said what actually happens when
`write_promotion_files` fails after the ledger already recorded a promotion.
Traced concretely: `integration-tests/test_fr_table_shape_convergence.py`'s
`test_every_live_requirement_stays_on_legacy_provenance` asserts
`promoted <= explicit` (bidirectional — a ledger-promoted id with no matching
explicit cell fails with `"reverted: [...]"`) and
`test_every_live_layers_cell_carries_the_marker` asserts the marker and the
ledger agree per row; either hard-fails the moment this exact mismatch
exists on disk, not merely the one FR's own next `promote_required_layers.py`
invocation. **Fix:** both the exit-2 error message
(`_plan_and_apply_locked`) and this section now say so explicitly.

**Real-repo effect: none observed.** No live FR's manifest disagrees with
its own live cell's declared layers beyond ordinary lag already covered by
the union fix; no live FR carries a `demoted` ledger entry against an
explicit cell; no concurrent writer exists in a single invocation; no second,
reordered FR-table exists anywhere in this repo's specs. Full canonical
suite re-run clean after the fix (`shared/tests`, `shared/scripts/tools/tests`
roots; `integration-tests` unaffected — no new mismatch introduced).

## Stage-4 code-review dispositions — pinning the four headline Stage-3 fixes

Fresh code-review against pushed HEAD `71506676`: no HIGH, but a recurring
defect class across all four headline Stage-3 fixes above (Medium 1–4 in
that section) — each closed a real hazard but shipped with **zero** test
coverage of its own. Deleting the fix left the full suite green, the same
class this repo already hit and fixed once (`test_mint_ac_ids.py:198`).
Six required fixes (4 medium + 2 low), all accepted-and-fixed; plus
dispositions for nine "your call" items.

**Medium 1 (accepted, fixed) — `file_lock` in both CLIs had zero test
coverage.** Nothing exercised the `with file_lock(...):`/manual-enter
wrapper around either CLI's locked span; deleting it left every other test
green. **Fix:** ported `test_mint_ac_ids.py:198-229`'s shape into both CLI
test files —
`test_a_second_invocation_times_out_while_the_lock_is_held` (holds the lock
in a background thread, asserts the second invocation's own error shape:
`rc==2` for `promote_required_layers.py`, `SystemExit` for
`record_layer_promotion_decision.py`) and
`test_an_exception_inside_the_locked_span_still_releases_the_lock` (a body
exception the CLI does not itself catch still releases the lock for a
follow-up run). Surfaced, while writing these: the original single `with
file_lock(...):` wrapping BOTH the acquisition and the body caught body
`OSError`s an existing pinned test (`test_ledger_write_failure_leaves_
spec_md_untouched`) needed to propagate raw — fixed by manually driving
`file_lock`'s `__enter__`/`__exit__` so only ACQUISITION failures get the
CLI's error shape, confirmed safe by reading `file_lock.py`'s generator
cleanup (`_release` is unconditional, never branches on exception type).

**Medium 2 (accepted, fixed) — `load_ledger_with_snapshot` untested, and an
existing test still paired the two-call anti-pattern its own docstring warns
against.** **Fix:**
`test_load_ledger_with_snapshot_reads_exactly_once` (monkeypatches
`Path.read_bytes` with a call-counter, asserts exactly one call, and that
the returned snapshot round-trips through `write_ledger(expected_snapshot=
...)`) plus `test_load_ledger_with_snapshot_missing_file_returns_none_
snapshot`, both in `shared/tests/test_layer_promotion_ledger.py`. The
flagged two-call pair in `test_write_ledger_refuses_a_concurrent_edit`
(nothing happened between the two calls there — a genuine instance of the
anti-pattern, not the "simulating two points in time" case that would have
needed two reads by construction) migrated to
`loaded, snapshot = load_ledger_with_snapshot(path)`.

**Medium 3 (accepted, fixed) — `contents_by_path` (the decide→write
TOCTOU-span-widening fix) was unpinned.** Reverting
`promote_required_layers.py`'s 3-arg `compute_promotion_writes` call back to
2-arg left the whole suite green. **Fix:**
`test_a_concurrent_spec_edit_between_the_decision_read_and_the_fold_is_
refused` (`shared/scripts/tools/tests/test_promote_required_layers.py`)
wraps `plan_promotions` to mutate the spec.md on disk AFTER its own read but
BEFORE the fold, asserting `rc==2` and that the concurrent edit survives
untouched. **Verified this actually pins the fix**, not merely exercises the
code path: manually reverted the 3-arg call to 2-arg and re-ran — the new
test fails (`rc == 0`, the concurrent edit silently discarded), confirming
it would have caught deleting the fix; reverted back, full file green
again (17/17). This same test also incidentally covers "your call" item 3
below (the ledger-written/spec-unwritten exit-2 ordering) — it asserts the
ledger entry survives the refused write.

**Medium 4 (accepted, fixed) — `live_declared_layers`'s tokenizer mirror had
no drift-pinning test**, unlike this file's own sibling mirror
(`test_escape_cell_mirrors_markdown_table`) and `layer_promotion`'s own
mirror test. **Fix:**
`test_live_declared_layers_mirrors_requirement_parse_tokeniser`
(`shared/tests/test_fr_layer_cell_writer.py`), parametrized over the
separator matrix (comma, space, slash, pipe, the `(inferred)` marker, mixed
case, an unrecognised token), cross-importing
`_requirement_parse._parse_layers` directly (precedent: this file's own
`escape_cell` cross-import at line 13). The cross-import needed a namespace
package registered under a synthetic name (never `scripts`/`lib`) so it
cannot collide with what `shared/tests` already bound those names to this
session — the exact ADR-045/one-test-root-per-process hazard the repo-root
conftest documents; loading the REAL `collectors/__init__.py` (which does
its own `from .._audit_disclosure_render import ...`, a level this synthetic
single-level parent does not have) was tried first and failed for exactly
that reason, so the loader targets `_requirement_parse.py` directly as a
namespace-package submodule instead.

**Low 1 (accepted, fixed) — tokenizer asymmetry between
`live_required_layers` (comma-only) and `live_declared_layers`
(`_LAYER_TOKEN_RE`) produced a real false escalation.** A ledger recording
`["unit", "integration"]`, cosmetically reformatted on disk to
`unit integration` or `unit/integration` (both still canonical), reads via
`live_required_layers` as a single un-split token — `set(recorded) <=
set(live_required_layers)` then False, a false `contradicts_recorded_
decision` for a no-op edit. **Fix:** `layer_promotion._narrowed_since_
promotion` now canonicalizes BOTH sides (new `_canonical_layer_tokens`,
re-splitting each element on the shared `_LAYER_TOKEN_RE`, lowercased)
rather than comparing raw sets — `live_required_layers`'s own comma-only
contract is unchanged (its docstring now says why: it answers "is this
explicit", a narrower question than what separator it accepts). New
parametrized test
`test_ledger_promoted_and_a_cosmetic_reformat_is_not_a_false_narrowing`
(`shared/tests/test_layer_promotion.py`).

**Low 2 (accepted, fixed) — the ledger lock sidecar
(`.shipwright/compliance/layer_promotion_ledger.json.lock`) was covered only
by the root `.gitignore`'s un-managed `*.json.lock` rule**, not by
`shared/templates/shipwright-gitignore.template`'s managed block (which
re-includes `!/.shipwright/compliance/` wholesale) — an adopted project
running these tools gets a trackable lock sidecar. **Fix:** added
`/.shipwright/compliance/layer_promotion_ledger.json.lock` to the managed
block in both files, mirroring the existing
`/.shipwright/agent_docs/iterates/*.iterate_timings.jsonl.lock` precedent.
`test_gitignore_template_congruent.py` (`shared/tests/`) confirms the two
stay in sync.

**"Your call" items — dispositions:**

1. *Missing spec.md silently degrades to `no_evidence_yet`.* Accepted, not
   fixed. Traced: an FR whose spec.md is genuinely missing either has no
   `"ok"` coverage (correctly a plain skip — no evidence either way) or has
   coverage that WOULD promote, in which case `compute_promotion_writes` →
   `write_layers_cell` already raises `LayerCellWriteError` ("no ACTIVE FR
   row") loudly at the write step, surfaced as `_plan_and_apply_locked`'s
   named `"could not compute a promotion write"` exit-2 message — not a
   silent failure in the case that actually matters. A dedicated
   missing-spec.md error only for the no-evidence path would name a
   structural repo problem this tool has no other reason to detect.
2. *Collision branch's `already_explicit` still last-writer-wins keyed.*
   Accepted, not fixed — see the corrected round-3 #8 disposition above
   (External-Code-Review-Findings, round 3 table): that disposition
   previously overstated the fix, closing only the `live_required_layers`
   PARAMETER's use in the collision branch, not `already_explicit` itself
   (read from the same per-display-id-keyed `plan_promotions.live_explicit`
   dict). Left as-is: documented unreachable in practice (the operator CLI
   already refuses an ambiguous `--action promoted`), and a real fix needs
   `plan_promotions` re-keyed by the manifest's own unique key everywhere,
   a wider change than this defect's live impact justifies today.
3. *Ledger-written/spec-unwritten exit-2 ordering untested.* Fixed as a side
   effect of Medium 3's new test above — it asserts the ledger entry is
   durable even though the concurrent-edit refusal left spec.md untouched.
4. *`_decide_and_write_locked` was a 102-line 4-level-nested function.*
   Already fixed earlier in this same round, before this disposition was
   written: split into `_plan_decision` (everything ledger-independent —
   node targeting, `required_layers` parsing, spec.md content/new-content)
   and `_decide_and_write_locked` (the three ledger-facing steps only).
5. *The 10-second lock timeout was hardcoded/unnamed.* Already fixed earlier
   in this same round: `_LOCK_TIMEOUT_SECONDS` named module-level constant
   in both CLIs, monkeypatchable by tests — used by the Medium 1 tests above
   to keep the timeout test fast (`0.2`s, not the real `10.0`s).
6. *`file_lock`'s own `OSError` (non-contention) escaped as a raw
   traceback.* Already fixed earlier in this same round, as part of the
   Medium 1 fix: acquisition-time `LockTimeout`/`OSError` now gets the CLI's
   normal error shape via the manual `__enter__`/`__exit__` split; a body
   `OSError` the CLI does not already catch still propagates raw, by design
   (see Medium 1 above) and continues to be pinned by the pre-existing
   `test_ledger_write_failure_leaves_spec_md_untouched`.
7. *`_promoted_fr_ids()`-equivalent logic duplicated across two integration
   test files.* Accepted, not fixed — a readability/duplication cleanup with
   no correctness stake, and out of scope for a round already covering six
   required fixes; left for a future pass that touches those files for an
   unrelated reason.
8. *Six new modules carry ~65 review-provenance comments at roughly 13x the
   density of neighbouring files.* Partially addressed opportunistically
   this round and the prior one (attribution parentheticals trimmed from
   `promote_required_layers.py`'s `plan_promotions` docstring and several
   `record_layer_promotion_decision.py` docstrings, behavioral rationale
   kept) — not a full sweep. The remaining density is accepted: this ADR is
   already the auditable record of who-found-what, but the in-code
   attributions also serve as direct pointers from a reader mid-diff back to
   the specific finding without a context switch, which the ADR alone does
   not give a reader who has not already opened it.

**Real-repo effect: none observed.** No hazard this round's tests pin was
ever exercised against this repo's own real manifest/ledger — the layer-
promotion mechanism itself is unchanged behaviorally except Low 1's
false-escalation fix, and no live FR's ledger entry was ever cosmetically
reformatted on disk. Full canonical suite (`shared/tests`,
`shared/scripts/tools/tests` roots) re-run clean after every fix in this
section; `uvx ruff@0.15.15 check .` clean.

## Stage-5 code-review dispositions — real duplicate found, bloat baseline caught up

Fresh code-review against `ceda9f38`: verdict `approve_with_changes`, no HIGH.
All six of the Stage-4 fixes independently re-verified as genuine (reviewer
confirmed each new test actually fails when its fix is reverted, and
cross-checked the ADR's "your call" dispositions against the current code as
accurate). Two new mediums this round, plus 2 lows; all four
accepted-and-fixed. Plus dispositions for four "your call" items.

**Medium 1 (accepted, fixed) — the module docstring's drift-pinning claim for
`LAYER_RANK` was false, and the duplicate it waved off was real.**
`layer_promotion.py`'s docstring claimed `LAYER_RANK` was "pinned against
drift by `test_highest_ok_layer_matches_layer_coverage_binding_contract`" — a
repo-wide grep finds exactly one hit for that name: the docstring itself, no
such test exists. The stated ADR-045 justification for not importing directly
was also wrong: `tools/verifiers/_layer_coverage_binding.py` lives under the
SAME `shared/scripts` tree, and `promote_required_layers.py` already imports
`tools.verifiers._layer_coverage_core` in this diff — not a cross-plugin
boundary. Net effect: `LAYER_RANK` (derived from `requirement_model.LAYERS`)
and `_layer_coverage_binding._LAYER_RANK` (hardcoded
`{"unit":0,"integration":1,"e2e":2}`) was an actually-unpinned duplicate.
**Fix:** eliminated the duplicate rather than adding a test for it — found
existing `lib/phase_quality/` precedent (`_findings.py`, `_runners.py`,
`_staleness.py`) for `lib →` `tools.verifiers` imports, confirming this
direction is an accepted, existing pattern, not the boundary violation the
old docstring claimed. `layer_promotion.LAYER_RANK` is now a direct re-export
of `tools.verifiers._layer_coverage_binding._LAYER_RANK`, and
`highest_ok_layer()` delegates to `_highest_ok_layer` rather than
re-implementing it — a stronger guarantee than a drift test (which could
itself go stale) and a net line-count win over adding one. Docstring's tree
claim and ADR-045 justification corrected in the same edit; no false claim
was left standing.

**Medium 2 (accepted, fixed) — 7 new files crossed the 300-line bloat budget
with `shipwright_bloat_baseline.json` never touched.** `layer_promotion.py`
(323), `promote_required_layers.py` (310), `fr_layer_cell_writer.py` (304),
`record_layer_promotion_decision.py` (303), `test_layer_promotion.py` (467),
`test_promote_required_layers.py` (452), `test_record_layer_promotion_
decision.py` (302) — none registered, and test files ARE in scope
(`_SKIP_PATH_RE` only exempts `fixtures/`; `test_record_event.py` already
baselined as precedent). **Fix, in order:** (1) attribution-comment trimming
across all six source-tree files (round/reviewer parentheticals dropped,
behavioral rationale kept) brought `fr_layer_cell_writer.py` under budget
(298) with no baseline entry needed; (2) the Medium 1 fix above further
shrank `layer_promotion.py` net (removing the duplicate table plus its
`requirement_model.LAYERS` import outweighed the docstring rewrite); (3) the
remaining three source files (`layer_promotion.py` 331, `promote_required_
layers.py` 309, `record_layer_promotion_decision.py` 309 — final counts
after this round's Low-1/Low-2/"your call" fixes) and three test files
(`test_layer_promotion.py` 481, `test_promote_required_layers.py` 461,
`test_record_layer_promotion_decision.py` 345) registered in
`shipwright_bloat_baseline.json` as `state: "deferred-plan"` (no ADR number
assigned mid-iterate — that happens only at `/shipwright-changelog` release),
`plan_ref` pointing at this sub-iterate's spec, and a note naming why further
trimming was exhausted (source files) or would never close the gap
(test files, whose overage — 161–181 lines — dwarfs any plausible comment
trim). `uv run shared/scripts/hooks/anti_ratchet_check.py` clean against the
final staged tree.

**Low 1 (accepted, fixed) — the lock-release test in both CLI test files
didn't pin the mechanism it claimed to.** The docstring/ADR said the test
proved the manual `lock_cm.__exit__` in `main()`'s `finally` runs on the
exceptional path, but deleting that `finally` entirely still left the test
green: `file_lock` is a `@contextmanager` generator, and CPython's
refcount-driven `GeneratorExit` finalization released the lock anyway once
the exception info (and its traceback, holding `lock_cm`) went out of scope
— outcome-sensitive, not mechanism-sensitive. **Fix:** restructured both
`test_an_exception_inside_the_locked_span_still_releases_the_lock` tests
(`test_promote_required_layers.py`, `test_record_layer_promotion_decision.py`)
to capture the exception via `pytest.raises(...) as excinfo` and keep
`excinfo` referenced (via a trailing `assert excinfo.type is ...`) THROUGH
the follow-up lock-acquisition call — `excinfo`'s traceback chain keeps
`main()`'s own `lock_cm` local alive by refcount for the whole call, so
refcount-driven `GeneratorExit` cleanup cannot have run; only `main()`'s own
explicit `finally` can be what makes the follow-up succeed. **Verified this
actually pins the fix, both twins:** manually patched out each file's
`finally: lock_cm.__exit__(...)` block and re-ran the specific test —
confirmed a genuine failure both times (`test_record_layer_promotion_
decision.py`'s twin: real `LockTimeout` after the full 10s wait, converted to
`SystemExit`; `test_promote_required_layers.py`'s twin: `rc == 2` with the
same real `LockTimeout` in the CLI's JSON error shape, not the expected
`rc == 0`) — then restored both files and re-confirmed both full test files
green (17 + 16 passed).

**Low 2 (accepted, fixed) — `OSError` on the promoted-path spec.md read
wasn't caught in the operator CLI, unlike its sibling demoted branch.**
`record_layer_promotion_decision.py`'s `_plan_decision` promoted branch only
caught `LayerCellWriteError` — a deleted spec.md raised a raw
`FileNotFoundError`, an empty `spec_path` raised a raw `IsADirectoryError`.
Both branches also indexed `node["spec_path"]` directly with no guard for a
missing/empty value, where `layer_promotion_apply.compute_promotion_writes`
explicitly rejects that case by name. **Fix:** widened the promoted branch to
`except (OSError, LayerCellWriteError)` (matching the demoted branch), and
added a named `not node.get("spec_path")` guard raising `SystemExit` before
resolving the path on BOTH the promoted and demoted branches, mirroring
`compute_promotion_writes`'s own rejection. Two new tests in
`test_record_layer_promotion_decision.py`:
`test_promoted_action_with_missing_spec_path_is_rejected_by_name` and
`test_promoted_action_on_a_deleted_spec_md_fails_with_a_named_error`.

**"Your call" items — dispositions:**

1. *`promote_required_layers.py` parsed spec.md 3x per FR instead of 2x via a
   redundant explicit-check call.* Accepted, fixed. `is_layers_cell_
   explicit_live(content, fr_id)` is literally `live_required_layers(content,
   fr_id) is not None` (`fr_layer_cell_writer.py:223`) — `plan_promotions`
   called both separately on the same `(content, fr_id)` pair, parsing the
   table twice for the same fact. Now computes `live_required_layers` once
   and derives `live_explicit` from its result; the now-unused
   `is_layers_cell_explicit_live` import removed. Both CLI test files stay
   green (17 + 16 passed) after the change.
2. *`lock_cm.__exit__(*sys.exc_info())` could be the simpler `__exit__(None,
   None, None)`.* Accepted, fixed, in both CLIs — `file_lock`'s cleanup
   (`_release`) is exception-agnostic (established Stage-4), so forwarding
   the real `sys.exc_info()` was never load-bearing. A one-line comment at
   each call site now says why.
3. *`_canonical_layer_tokens` raised a raw `AttributeError` on a
   type-corrupted ledger element instead of the fail-closed `ValueError`
   `load_ledger`'s docstring promises.* Accepted, fixed — added an explicit
   `isinstance(value, str)` check raising `ValueError` with the offending
   element in the message. New test
   `test_ledger_promoted_with_a_corrupted_required_layers_element_fails_
   closed` (`shared/tests/test_layer_promotion.py`) asserts a `None` element
   in a ledger's `required_layers` raises `ValueError` rather than
   `AttributeError`.
4. *`json` imported inside the function body in two integration test files
   instead of module scope.* Not fixed — neither file was touched this
   round, and the item was explicitly scoped as "bundle only if touched
   again." Left as documented, deferred debt.

**Real-repo effect: none observed.** Both fixed defects (the unpinned
`LAYER_RANK` duplicate, the outcome- vs. mechanism-sensitive lock test) were
test/documentation-integrity issues, not behavioral bugs against this repo's
real manifest/ledger — `LAYER_RANK`'s two copies were never actually
divergent (both derived from the same three canonical layer names), and the
lock WAS always released correctly by the `finally` block; only the test's
ability to detect its own regression was fixed. Full canonical suite
(`shared/tests`, `shared/scripts/tests`, `shared/scripts/tools/tests`,
`integration-tests` — all 4 roots) re-run clean after every fix in this
section; `uvx ruff@0.15.15 check .` clean; `uv run shared/scripts/hooks/
anti_ratchet_check.py` clean.

## Stage-2 code-review round 2 dispositions — fail-open on ledger read closed

Fresh code-review against `512083a1`: `approve_with_changes`, explicitly
marked non-blocking. All four of the Stage-5 round's fixes independently
re-verified real (spot-checked against source, not labels), no regressions,
most "your call" items from that round correctly left as `not_findings`.
Three lows this round; two shared one fix site and were required, the third
was fixed opportunistically while already in the file.

**Low 1 + Low 2 (accepted, fixed) — fail-open on ledger read, contradicting
the "cannot silently demote" invariant.** `evaluate_fr` (`layer_promotion.py:191`)
branches only on the literal strings `"promoted"`/`"demoted"`; any other
value in a ledger entry's `action` field (a hand-typo like `"demote"`, or a
future third action) fell through to the no-ledger path — an FR that
already carries a decision could be silently auto-promoted again with a
second entry appended, directly contradicting `layer_promotion_ledger.py`'s
own module docstring ("once an FR has ANY entry, it's out of the automated
tool's authority forever"). `append_decision` validated the closed
`ACTIONS` vocabulary on write; nothing validated it on read. Second symptom
of the same gap: `latest_decision` (`layer_promotion_ledger.py:211`) assumed
`decisions[fr_id]` is a list of dicts — a corrupted value (a string, or a
list of non-dicts) raised a raw `AttributeError`/`KeyError` instead of the
CLI's normal JSON error shape, the same defect class `_canonical_layer_tokens`
closed the round before. **Fix, at the one site named in both findings:**
`_parse_ledger` (`layer_promotion_ledger.py:120`) now validates every
`decisions` value is a list and every element is a dict with `action` in
`ACTIONS`, raising `ValueError` naming the offending FR id — matching
`load_ledger`'s documented "fail closed rather than guess" contract. Both
CLIs already convert a `ValueError` from `load_ledger_with_snapshot` into
their own error shape (exit 2 / `SystemExit`), so this closes both symptoms
with no new plumbing; `layer_promotion.py:191` itself needed no code change
— once `_parse_ledger` rejects anything outside the closed vocabulary,
`ledger_action` can only ever be `None`, `"promoted"`, or `"demoted"`. Three
new tests in `shared/tests/test_layer_promotion_ledger.py`: an unrecognised
`action` string, a non-list decision history, and a list of non-dict
entries — all asserting `ValueError` naming the FR id.

**Low 3 (accepted, fixed opportunistically) — a test's own title claim
wasn't pinned.** `test_promoted_action_on_a_deleted_spec_md_fails_with_a_named_error`
(`test_record_layer_promotion_decision.py`) asserted a bare
`pytest.raises(SystemExit)` with no `match=`, unlike its `no spec_path`
sibling two lines up — it still caught the regression (a raw
`FileNotFoundError` is not a `SystemExit` at all) but didn't confirm the
CLI's error actually *names* the file, which is what the test's title
claims. Fixed cheaply while already touching this file for Low 1+2's
sibling tests: added `match="spec.md"` (a stable substring of the OS
`FileNotFoundError` message regardless of platform phrasing).

**Bloat baseline follow-up.** `layer_promotion_ledger.py` crossed the
300-line budget (323) after the validation fix; registered as
`deferred-plan` alongside the other layer-promotion modules already
deferred this campaign, same `plan_ref`. `test_record_layer_promotion_decision.py`'s
already-deferred entry bumped from 345 to 350 to reflect the Low-3 test
addition — no new crossing, an existing deferred entry moving within its
own file's growth.

**Real-repo effect: none observed.** This repo's own `layer_promotion_ledger.json`
has never contained a malformed `action` value — both fixed defects were a
missing input-validation guard against a hypothetical hand-edit or a future
bug, not an active hazard against this repo's own two live ledger entries
(FR-01.01/FR-01.11, both escalated, no ledger entry recorded for either).
Full canonical suite (`shared/tests`, `shared/scripts/tools/tests` roots)
re-run clean after the fix; `uvx ruff@0.15.15 check .` clean; `uv run
shared/scripts/hooks/anti_ratchet_check.py` clean.

## Stage-2 code-review round 3 dispositions — sibling fail-open closed, dead code removed

Fresh code-review against `7ceb082f`: `approve_with_changes`, only 2 lows
this round, and the reviewer explicitly re-derived and found clean
everything else across the full 6195-line diff — including disputing a
Stage-1 handoff note by confirming the integration tests' raw `json.loads`
is the CORRECT call there (importing `shared/scripts/lib` from
`integration-tests/` would hit the exact ADR-044/045 `sys.path` collision
hazard the repo-root `conftest.py` guards against), not a bypass.

**Low 1 (accepted, fixed) — sibling fail-open, same class and same fix site
as round 2's.** `_parse_ledger` (round 2's fix) validated `action` type and
vocabulary per entry, but not `required_layers` element types. A
hand-corrupted `promoted` entry like `"required_layers": [null, "unit"]`
passed `load_ledger_with_snapshot` unnoticed and only surfaced later as a
bare `ValueError` out of `layer_promotion._canonical_layer_tokens` via
`_narrowed_since_promotion` — `_plan_and_apply_locked`'s
`except (OSError, LayerCellWriteError)` clause around `plan_promotions`
does not catch a plain `ValueError` (`LayerCellWriteError` subclasses it,
but that is a different exception), so the corrupted entry escaped `main()`
as an uncaught traceback (exit 1) instead of the CLI's normal JSON error
shape. Fail-closed in outcome (no wrong promotion, lock still released) but
contradicting the exact contract round 2's fix cited (`load_ledger`'s "fail
closed rather than guess", and the operator-CLI rule "name the actual
problem, not an uncaught traceback"). Reachable only via a hand-edited
ledger, hence low. **Fix, at the reviewer's preferred site (matching round
2's own pattern):** extended `_parse_ledger`'s per-entry loop to also
reject a `required_layers` that isn't a list of strings, naming the FR id —
this makes `_canonical_layer_tokens`'s guard unreachable-by-construction,
and both CLIs get the normal error shape for free with no new plumbing.
Added one CLI-level test (`test_a_corrupted_ledger_required_layers_is_an_
operational_failure`, `test_promote_required_layers.py`: rc 2, an `error`
key naming the FR id) alongside the existing lib-level test that already
pins the underlying `_canonical_layer_tokens` behavior directly
(`test_layer_promotion.py`).

**Low 2 (accepted, fixed) — dead code.** `read_ledger_snapshot` had zero
production callers left — both CLIs use `load_ledger_with_snapshot`
exclusively since the Stage-3 concurrency fix superseded it; the only
remaining references were its own definition, two docstring
cross-references, `__all__`, and its own two tests. **Fix:** deleted the
function and its `__all__` entry, rewrote the two docstring
cross-references in `load_ledger_with_snapshot` and `write_ledger` to no
longer point at a function that no longer exists. Migrated
`test_write_ledger_with_matching_snapshot_succeeds`'s call site to
`load_ledger_with_snapshot(path)[1]`. `test_read_ledger_snapshot_is_none_
for_a_missing_file` was NOT migrated to a same-named `load_ledger_with_
snapshot` call as a literal 1:1 swap — its exact assertion (missing file →
`None` snapshot) was already independently pinned by the pre-existing
`test_load_ledger_with_snapshot_missing_file_returns_none_snapshot`, so
keeping both would have been the redundant-test smell this same fix is
otherwise closing; deleted outright instead. Two stale comment
cross-references to the deleted function rewritten to describe the
anti-pattern without naming it.

**Bloat baseline follow-up.** `layer_promotion_ledger.py`'s already-deferred
entry bumped 323 → 331 (the Low-1 validation net of the Low-2 deletion);
`test_promote_required_layers.py`'s already-deferred entry bumped
461 → 490 (the new CLI-level test). No new crossings — both are existing
`deferred-plan` entries moving within their own files' growth;
`anti_ratchet_check.py` exits 0.

**Real-repo effect: none observed.** Both fixed defects require a
hand-corrupted ledger to reach; this repo's own `layer_promotion_ledger.json`
has never contained a malformed `required_layers` value, and
`read_ledger_snapshot` was already fully unused in production code before
this round — its removal is a pure cleanup, not a behavior change. Full
canonical suite (`shared/tests`, `shared/scripts/tools/tests` roots) re-run
clean after the fix; `uvx ruff@0.15.15 check .` clean; `uv run
shared/scripts/hooks/anti_ratchet_check.py` clean.

## Stage-3 doubt-review findings, round 2 — cell-text narrowing, two fail-open
## reads, a coincidental fingerprint, and a demote-revert's error message

Doubt-reviewer ran again against pushed HEAD `0c672d6a`, found 4 new doubts
(1 Medium, 3 Low), none re-hashes of any prior round. Doubt is
advisory-must-address: every finding below is either fixed, with a test, or
would have needed a written rebuttal if left unfixed — none were.

**Medium — a promotion could silently delete non-canonical content from a
Layers cell, contradicting this mechanism's own "widen never narrow" claim.**
`fr_layer_cell_writer.live_declared_layers` + `layer_promotion_apply.
render_layers` regenerate the WHOLE cell from the canonical layer SET a
promotion computes — the "widen never narrow" invariant holds over that SET,
not over the cell's raw TEXT. A hand-maintained cell like `unit, db
(inferred)` or `unit (inferred) - integration deferred, see ADR-031` would
get silently rewritten to bare `unit` on promotion, permanently deleting the
non-canonical token or annotation with no warning and no escalation — the
same bug CLASS as the already-fixed HIGH (stale-manifest narrowing), on the
one axis that fix does not reach. Latent in this repo today (all 20 live
cells are pure-canonical); live for the first hand-annotated cell here, or
for any adopter. **Chose the FIX, not the rebuttal the finding itself
offered** ("the Layers cell is a machine-owned field whose free text is
expendable" — a real argument, since the compliance collector's own
`invalid_layers` channel already treats a non-canonical token as dropped
from the parsed model, only SURFACED as a hygiene finding elsewhere, never
blocking): the WRITER silently deleting text a human wrote, with zero trace
and zero escalation, is a materially different failure than the READER
flagging it — this mechanism escalates on every other undeterminable case
rather than guessing, and this is cheap to make consistent with that. Added
`fr_layer_cell_writer.live_cell_has_non_canonical_content(content, fr_id)`
(strips the `(inferred)` marker, re-tokenises on the same `_LAYER_TOKEN_RE`
mirror `live_declared_layers` already uses, and reports whether anything
survives outside the canonical `LAYERS` vocabulary); `promote_required_
layers.plan_promotions` computes it per FR from the same content read it
already has and threads it into `evaluate_fr` as a new keyword-only
`live_cell_has_non_canonical_content` parameter (default `False`, so every
existing caller/test is unaffected); `evaluate_fr` escalates
`REASON_LAYER_UNDETERMINABLE` when it is set, checked LAST — only on the
branch that would otherwise promote, so a not-yet-eligible FR's residual
text is never reported prematurely. Deliberately scoped to the AUTOMATED
tool only: the human-operated `record_layer_promotion_decision.py` keeps
overwriting unconditionally on `--action promoted`, because an operator
typing that command with an explicit `--reason` has already had the chance
to look at the cell they are about to replace — the automated tool is the
one acting with nobody looking. Three new tests: a lib-level parametrized
matrix (`test_fr_layer_cell_writer.py`) covering a pure-canonical cell
(false), a non-canonical token (true), a hand-added note (true), an empty
cell (false), and a missing row (false); an `evaluate_fr`-level pair
(`test_layer_promotion.py`) pinning the escalation and confirming the
default leaves every existing promote path unaffected; a CLI-level
end-to-end test (`test_promote_required_layers.py`) confirming an
otherwise-promotable FR with a non-canonical token in its live cell exits 3,
writes nothing, and leaves the annotation untouched on disk.

**Low — an `OSError` on the ledger read escaped both CLIs as a raw traceback
instead of the normal error shape.** `load_ledger_with_snapshot` calls
`path.read_bytes()` after `path.is_file()`; neither
`promote_required_layers.py`'s nor `record_layer_promotion_decision.py`'s
call site caught anything but `ValueError`, so a permissions error, or the
path becoming a directory between the two calls, escaped uncaught — the
identical defect CLASS already fixed at every OTHER read site in this
mechanism (the manifest read, both spec.md reads, `write_ledger`'s own
`OSError`), just not here. Fail-safe in outcome either way (nothing written,
the lock still releases via `finally`) — this fixes the error SHAPE only.
Fixed by widening both call sites to `except (OSError, ValueError)`. One new
test per CLI (an OSError-raising monkeypatch on `load_ledger_with_snapshot`,
pinning `rc == 2` with an `error` key for the automated tool and a named
`SystemExit` for the operator CLI).

**Low — `evidence_fingerprint`'s agreement between `evaluate_fr`'s demoted
branch and `plan_promotions`'/`record_ledger_entries`' own reporting is
coincidental, not enforced.** They agree today only because `plan_
promotions`'s `eval_node = dict(node)` is a SHALLOW copy — `coverage`/
`tests` stay the SAME nested objects on both `node` and `eval_node`, and
`evidence_fingerprint`'s payload today covers only those two keys. If that
payload is ever widened to include `required_layers` (a plausible future
extension per its own docstring — `eval_node`'s is the unioned value,
`node`'s is not), the two would silently diverge with no test to catch it —
a demoted veto's drift gate would start comparing against a unioned value
nothing ever recorded. Not a live bug — a latent trap. **Chose the test over
threading the raw node through explicitly**: an extra parameter on
`evaluate_fr` solely to carry a second, rarely-different node past the one
already accepted would be more surface for a mechanism already at its size
budget, for a risk that is purely about `evidence_fingerprint`'s own payload
staying stable — pinning THAT directly is the more precise fix. Added
`test_evidence_fingerprint_agrees_across_a_shallow_copy_that_only_touches_
required_layers` (`test_layer_promotion_ledger.py`), reproducing
`plan_promotions`'s exact mutation shape (copy, then reassign only
`required_layers_source`/`required_layers`) and asserting the fingerprints
still match despite the `required_layers` values now differing — so a
future payload widening fails LOUDLY here instead of silently in production.

**Low — the demote-revert's error message didn't tell the operator the
failure state is actually exitable.** The demote path is ledger-first (the
ledger write lands, then the spec.md revert-to-`(inferred)` runs behind a
re-read-and-compare guard). If that guarded write failed
(`ConcurrentSpecEditError` or the pre-write `OSError`), on-disk state became
ledger=demoted + cell-still-explicit — reds the same repo-wide
`explicit <= promoted` integration guard the automated tool's own
`already_explicit` escalation arm exists to prevent. Unlike the automated
tool's matching exit-2 message (which must warn an operator that a plain
re-run will NOT clear the gap — only this CLI can), this code path already
IS that CLI: re-running the exact same `--action demoted` command
recomputes the write fresh from the current on-disk state and retries it (a
second, redundant `demoted` ledger entry on retry is harmless —
`evaluate_fr`'s ledger-drift branches always read the LATEST entry, never
accumulate) — the opposite framing needed the opposite message, not a copy
of the automated tool's. Fixed by adding `_spec_write_failure_message(args,
node, detail)`, branching on `args.action` (the promoted branch keeps a
parallel, simpler "re-run the same --action promoted command" message —
symmetric, not previously named at all), and using it at both the
pre-write-read `OSError` site and the `ConcurrentSpecEditError` site. New
CLI-level test (`test_record_layer_promotion_decision.py`), mirroring
`test_promote_required_layers.py`'s existing TOCTOU-simulation idiom
(mutate the file from inside a wrapped `_plan_decision`, after its own
read, before the write) — only the promote-path ordering was pinned before;
this is the demote-path sibling, confirming the ledger entry lands, the
cell survives untouched, and the message names the retry.

Bloat-baseline follow-up: registered a NEW `deferred-plan` entry for
`fr_layer_cell_writer.py` (crossed 300 lines at 341 after the Medium fix)
and for `test_layer_promotion_ledger.py` (crossed 300 lines at 305 after the
fingerprint-coincidence test); bumped five already-deferred entries to their
new line counts (`layer_promotion.py` 331→349, `promote_required_layers.py`
309→331, `record_layer_promotion_decision.py` 309→346, `test_layer_
promotion.py` 481→505, `test_promote_required_layers.py` 490→537, `test_
record_layer_promotion_decision.py` 350→416); `layer_promotion_ledger.py`
was untouched this round (still 331, no bump needed) and `test_fr_layer_
cell_writer.py` grew but stayed under budget (281 lines — no new crossing).
`uv run shared/scripts/hooks/anti_ratchet_check.py` exits 0.

**Real-repo effect: none observed.** The Medium fix's escalation path is
latent (every live cell in this repo's own manifest is pure-canonical); the
two OSError fixes and the fingerprint-coincidence risk are all latent traps
requiring either a filesystem fault or a future payload change neither has
happened; the demote-revert message fix only changes what an operator sees
on an already-rare write failure. Full canonical suite re-run clean across
all four roots (`shared/tests`, `shared/scripts/tests`, `shared/scripts/
tools/tests`, `integration-tests`); repo-wide ruff clean; `verify_local.py`'s
3 mirrored gates green; the real promotion tool re-run against this repo's
own manifest unchanged (still 5 historically promoted, 2 escalated
FR-01.01/FR-01.11, no new writes).

## Stage-1 spec-review REJECT — the round-2 Medium fix escalated instead of skipping

Stage-1 spec-review REJECTed the round-2 Medium fix above (the non-canonical-
content guard), a hard gate, on the pushed HEAD carrying it. Not a re-hash of
the doubt finding itself — the fix's underlying data-protection goal (never
let an automated rewrite silently delete a hand-written cell annotation) was
accepted as correct; the objection is to the MECHANISM chosen to achieve it.
Two independent spec violations, both in `layer_promotion.py`'s `evaluate_fr`:

1. **AC-1/spec L15.** The branch fired only after `highest_ok is not None`,
   `not evidence_ambiguous`, `not unverified_required`, and no ledger
   contradiction had already been checked and passed — i.e. exactly the state
   in which the spec requires promotion to happen "without operator
   interaction." The spec's escalation vocabulary is closed to the three
   named undecidable cases (`REASON_LAYER_UNDETERMINABLE`, `REASON_
   BOUND_TEST_ABSENT`, `REASON_CONTRADICTS_DECISION`); halting on a case
   where the promotion predicate demonstrably HOLDS is not one of them.
2. **AC-4.** The branch reported `REASON_LAYER_UNDETERMINABLE`, whose
   spec-defined meaning is narrowly "the highest observable layer cannot be
   determined from the manifest" — but it WAS determined; that is exactly
   what passed just above. What was actually undeterminable was a different
   question read from the live document, not the manifest: whether the
   cell's hand-written text may be discarded. The reason code the next
   reader saw was untruthful about what happened, even though the free-text
   `detail` was accurate.

**The fix (reviewer's suggestion, smallest change, keeps the data-protection
goal intact):** changed the branch from `_escalate(..., REASON_LAYER_
UNDETERMINABLE, ...)` to a new named `_skip(fr_id, SKIP_LIVE_CELL_HAS_
RESIDUAL_TEXT)` — same practical effect (the promotion never overwrites the
hand-annotated cell; the CLI writes nothing and the ledger is untouched for
that FR), reported honestly as a plain "not promoted this run" rather than a
fabricated case-1 escalation. No change to `live_cell_has_non_canonical_
content` itself (`fr_layer_cell_writer.py`) or to how `plan_promotions`
computes and threads the flag — only `evaluate_fr`'s REACTION to a `True`
value changed. `evaluate_fr`'s and `plan_promotions`'s docstrings updated to
say "skips" rather than "escalates."

Retargeted both tests pinning the old behavior, renamed for what they now
assert:

- `test_layer_promotion.py::test_promotable_evidence_but_a_hand_annotated_
  live_cell_escalates_instead_of_overwriting` →
  `test_promotable_evidence_but_a_hand_annotated_live_cell_is_skipped_
  instead_of_overwriting`: now asserts the full skip-dict shape
  (`{"fr": ..., "action": "skip", "reason_code": SKIP_LIVE_CELL_HAS_
  RESIDUAL_TEXT}`), matching the file's established full-equality style for
  every other skip test, instead of `action == "escalate"` /
  `reason_code == REASON_LAYER_UNDETERMINABLE`.
- `test_promote_required_layers.py::test_a_hand_annotated_cell_escalates_
  instead_of_silently_losing_the_annotation` →
  `test_a_hand_annotated_cell_is_skipped_instead_of_silently_losing_the_
  annotation`: now asserts `rc == 0` (not 3), `out["escalated"] == []`, and
  `out["skipped"][0]["reason_code"] == "live_cell_has_residual_text"`. The
  annotation-survives-untouched and ledger-not-written assertions are
  unchanged — still true under the skip outcome.

The raw detector function's own tests (`test_fr_layer_cell_writer.py`) needed
no change — they pin `live_cell_has_non_canonical_content`'s return value
directly, not `evaluate_fr`'s reaction to it, and that function is untouched
by this round.

Full canonical suite (all four roots), repo-wide ruff, and `verify_local.py`
re-run clean after the retargeting. Once this lands, the full review cascade
(Stage-1 → Stage-2 → Stage-3) re-runs fresh against the corrected HEAD to
confirm.

## Stage-3 doubt-review findings, round 3 — a row-rewrite byte-preservation gap (rebutted) and a link sort-key total-order gap (fixed)

Doubt-reviewer ran a third time against pushed HEAD `ecc50a3e`, this round with
two focused adversarial questions checked and confirmed clean (does the
skip-vs-escalate REJECT fix open a new gap — no; do the four doubt-round-2
fixes interact badly — no) plus two new Low findings, both genuinely
latent/unreachable in this repo today with a bounded-safe blast radius. The
finding curve across 10 Stage-1, 7 Stage-2, and 3 Stage-3 rounds converges
here — this closes the cascade.

**Low — `write_layers_cell` rewrites the WHOLE row, so a promotion can
cosmetically re-escape a sibling cell (rebutted, tested, not fixed).**
`fr_layer_cell_writer.write_layers_cell` re-renders every cell of the target
row through `_escape_cell`, not only the Layers cell it changes — a
hand-written single backslash in a sibling cell (`C:\repo\spec`) becomes the
doubled, escaped `C:\\repo\\spec` on disk, and hand-added column-alignment
padding around a sibling cell collapses to a single space, purely as a side
effect of `split_cells`/`_escape_cell` being an exact round-trip pair over
the WHOLE row rather than the one edited cell. Value-preserving (a re-read of
the rewritten row yields the exact same content the hand-written cell meant)
but not byte-preserving — the same class of unrequested edit
`SKIP_LIVE_CELL_HAS_RESIDUAL_TEXT` exists to prevent, one cell over. **Chose
the rebuttal over the splice fix**, for reasons the finding itself
anticipated: latent (no live FR row in this repo's own `spec.md` contains a
backslash or non-canonical padding), convergent (idempotent from the second
write — a second promotion of a DIFFERENT FR in the same row-adjacent
neighbourhood, or a re-run, produces no further change), and semantically
lossless under this mechanism's own escaping contract (round-trip exact
inverse). A byte-preserving splice would require threading raw per-cell byte
spans through `_fr_table_cells.split_cells`/`fr_table_reader.read_fr_rows` —
shared readers this mechanism does not own and that are consumed well beyond
this one writer — a materially larger, riskier change than the narrow,
already-bounded gap it closes. Recorded the rebuttal directly in
`write_layers_cell`'s own docstring (not only here), and added two new tests
pinning the CURRENT, accepted behavior as an explicit tested contract rather
than an untested side effect: `test_normalizes_a_hand_written_backslash_in_
an_untouched_cell_when_the_row_is_rewritten` (byte change pinned, value
round-trip pinned) and `test_collapses_hand_added_column_alignment_padding_
in_an_untouched_cell_when_the_row_is_rewritten`. Registered a new
`deferred-plan` baseline entry for `test_fr_layer_cell_writer.py` (crossed
300 lines at 322 after the two new tests, same precedent as
`test_record_event.py`); no code-file crossing from this finding alone.

**Low — `_link_sort_key`'s `(id, path, ac_id)` was not a total order over
every link pair the test-link collector can produce (fixed).** A test
carrying both a `@pytest.mark` tag and a `# @covers` comment for the same FR
files two links with identical `id`/`path`/`ac_id`, differing only in
`tag_source` — `sorted`'s stability then let their relative order (and so
`evidence_fingerprint`'s digest) depend on collector emission order rather
than content, a completeness gap in the canonicalization the Stage-2
round-1 fix introduced (no nondeterministic reordering was ever
demonstrated — collector order is parse-order deterministic within a file
today — so this was latent, not a proven flake). Blast radius if it ever
fired: a spurious `fingerprint_drifted` on a demoted entry, which only
re-escalates when ANDed with `predicate_holds` — one extra exit-3 hand-back
to an operator, never a wrong write. **Chose the fix over the rebuttal**: a
genuine two-token change (`_link_sort_key` now also returns
`str(link.get("tag_source", ""))` as a fourth tuple element), cheap enough
that "would this be worth a line" was never a close call, closing the gap
outright rather than merely documenting today's incidental determinism as a
standing assumption. One new test,
`test_evidence_fingerprint_is_stable_under_reordering_of_links_sharing_id_
path_and_ac_id` (`test_layer_promotion_ledger.py`), constructing exactly the
two-links-one-differs-by-`tag_source` case and asserting the digest is
order-independent. Bumped two already-deferred bloat-baseline entries to
their new line counts (`layer_promotion_ledger.py` 331→343,
`test_layer_promotion_ledger.py` 305→320); no new crossings from this
finding alone; `anti_ratchet_check.py` exits 0.

Full canonical suite re-run clean across all four roots after both
dispositions (shared/tests net +3 from this round's three new tests;
shared/scripts/tests and shared/scripts/tools/tests unchanged;
integration-tests unchanged), repo-wide ruff clean, `verify_local.py`'s 3
mirrored gates green.

## Tier-3 PR-review CI gate BLOCK — a demoted collision could strand an explicit sibling row

**Provenance, named explicitly per the coordinator's instruction:** this
finding is NOT from our internal review cascade (Stage-1 spec-review /
Stage-2 code-review / Stage-3 doubt-review) — it is from PR #690's
automated Tier-3 PR-review CI gate, a separate required GitHub check that
runs post-push against the pushed diff. It posted a genuine BLOCK verdict
against HEAD `95656216`, examining an interaction none of the ~10
Stage-1 / 7 Stage-2 / 3 Stage-3 rounds above had specifically probed: the
collision × demoted interaction. (The same CI gate pass also re-examined
the CI-evidence-provenance concern from earlier rounds and downgraded it
to a non-blocking comment, explicitly accepting the existing `trg-fcd48a56`
tracking as reasonable for this PR's scope — no action needed there.)

**The gap:** `record_layer_promotion_decision.py`'s `--action demoted` path
for an ambiguous COLLISION id (more than one ACTIVE manifest node sharing a
display id, in different `spec_path`s) never touches spec.md at all — by
design, since a collision has no single resolvable `spec_path` to revert.
But it also never CHECKED whether any of the colliding rows was currently
explicit before recording the demotion. `layer_promotion.evaluate_fr`'s
own collision branch then returns `demoted_consistent` unconditionally for
that ledger action, with no live-state check at all (unlike the
non-collision `demoted` branch's `already_explicit` guard). Concretely: two
active nodes share a display id in different files; one already carries an
explicit Layers cell (hand-promoted, or promoted before the second node
existed and created the collision); an operator demotes the collision id;
the CLI records `demoted` and writes nothing to either spec.md file — the
already-explicit row is left standing with a ledger that now says
`demoted` for its own display id, not `promoted`, failing the repo-wide
`explicit <= promoted` provenance invariant the two integration tests
enforce. A human explicitly vetoing a collision could silently strand an
explicit row with no ledger entry backing it.

Distinct from the already-accepted Low finding about `already_explicit`'s
display-id keying on the PROMOTED-collision path (that one is theoretically
reachable but safe today, because `_find_node_for_promotion` already
refuses `--action promoted` for any collision id): this is the
DEMOTED-collision path specifically, which had NO equivalent refusal.

**The fix** (reviewer offered two shapes — refuse, or an atomic
all-matching-row revert; chose refuse): `record_layer_promotion_decision.
py`'s `_plan_decision` now, for a collision fan-out (`node is None`),
reads every colliding row's live spec.md content and refuses the whole
demotion with a named `SystemExit` if ANY of them is currently explicit —
before the ledger lock's load-decide-write span writes anything at all.
Chose refuse over an atomic multi-file revert: an all-matching-row revert
would need to span an unbounded number of DIFFERENT spec.md files
atomically (a collision fan-out is not bounded to two), multiplying the
concurrency-guard surface (`ConcurrentSpecEditError` today only ever
protects ONE file per call) for a case the mechanism's own module docstring
already treats as `operator`-resolved, not automated — refusing and naming
the conflicting spec_path(s) mirrors the EXACT pattern
`_find_node_for_promotion` already uses for the promoted-collision case
("resolve the underlying id collision first"), so the fix reuses an
established idiom rather than inventing a new one. `evaluate_fr`'s
collision branch is unchanged: with the CLI now refusing to ever create
the bad state, a `demoted` entry for a collision id is guaranteed to have
held the invariant at record time, so `demoted_consistent` trusting the
ledger unconditionally remains correct — the fix is a write-time
precondition, not a read-time re-derivation.

One new CLI-level regression test,
`test_demoted_action_on_a_collision_refuses_when_a_colliding_row_is_already_
explicit` (`test_record_layer_promotion_decision.py`), constructing two
colliding nodes in two different spec.md files (one inferred, one already
explicit) and asserting the demotion is refused, naming the conflict, with
NOTHING written — neither spec.md file changes and the ledger file is
never created. Both existing collision-demotion tests
(`test_demoted_action_on_a_collision_id_still_clears_it` and the promoted
sibling) remain green unmodified — they exercise the still-permitted
all-inferred collision case.

Bumped two already-deferred bloat-baseline entries to their new line counts
(`record_layer_promotion_decision.py` 346→389,
`test_record_layer_promotion_decision.py` 416→460); no new crossings;
`anti_ratchet_check.py` exits 0. Full canonical suite re-run clean across
all four roots, repo-wide ruff clean, `verify_local.py`'s 3 mirrored gates
green.

## The emit-half question (`trg-875104ac`) — still open, not covered here

`trg-875104ac` tracks whether P3.5 also covers the "emit half": producers
(`/shipwright-project`, `/shipwright-adopt`, `/shipwright-iterate`) writing
an INITIAL `required_layers` binding at requirement create/update time. It
does not. P3.5's mechanism only ever mechanically UPGRADES an EXISTING
`inferred_legacy`/`defaulted_legacy` binding based on accumulated CI
evidence, independent of any create/update event — it never touches any
producer's authoring code path. These are distinct lifecycle moments: one
writes a binding when a requirement is born or edited; the other promotes an
existing binding's provenance later, once evidence exists. `trg-875104ac`
stays OPEN — this run is not the follow-up it was waiting to see land.

## A pre-existing repo-wide guard assumed zero explicit FRs — updated, not weakened

Running the full canonical suite (`run_test_suite.py`) against this run's real,
committed promotion (not a fixture) surfaced 3 failures, all in
`integration-tests/`, none touched by this diff before this discovery:
`test_fr_table_shape_convergence.py::test_every_live_requirement_stays_on_legacy_provenance`
and `::test_every_live_layers_cell_carries_the_marker`, plus
`test_requirements_catalog_contract.py::test_every_layers_cell_keeps_the_inferred_marker`.
All three were written pre-P3.5 (S4/S5/S6 era) and hard-pinned "every live FR
stays legacy, ZERO explicit," reasoning that an unmarked cell would
hard-abort the layer-coverage gate against guaranteed gaps. That reasoning
was correct **before** a mechanism existed that only ever flips a cell when
coverage genuinely closes the gap — which is this sub-iterate's entire job.

Fixed, not skipped or loosened: all three now read
`.shipwright/compliance/layer_promotion_ledger.json` as the ONE legitimate
source of an `explicit` id. An id that is `explicit` with NO matching
`action:"promoted"` ledger entry still hard-fails every one of the three
tests, exactly as before — an unrecorded/accidental flip is exactly as
caught as it always was. A ledger-recorded promotion is now the one
exception, checked per-id, not by relaxing the assertion to "some are
allowed." Verified: `pytest integration-tests/` full root, 530 passed (was
527 passed + 3 failed before the fix), `uvx ruff@0.15.15 check` clean on both
edited files.

## Consequences

`required_layers` for the 5 promoted FRs is now the enforcement floor P3.3's
`evaluate_cross_layer`/`evaluate_binding_completeness` apply at HARD severity
instead of ADVISORY — verified safe today: each promoted FR's
`required_layers` was set to exactly its current `"ok"` coverage set, so no
existing test run newly fails the gate the moment this lands. `trg-8d6f4b90`
(WebUI counterpart) and `trg-fcd48a56` (CI-evidence provenance, cross-cutting)
remain open, tracked follow-ups, not silently resolved by this unit.

## Rejected alternatives

A single global sweep ("promote every FR whose evidence looks green in one
pass") was rejected outright — that is precisely what D5 and the sub-iterate
spec's own scope section forbid; per-FR evaluation with an independent ledger
entry per requirement is the only shape considered.
