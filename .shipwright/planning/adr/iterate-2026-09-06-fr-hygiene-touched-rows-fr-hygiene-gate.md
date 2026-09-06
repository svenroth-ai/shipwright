# ADR: Diff-scoped FR-hygiene gate for touched rows, plus I7/I8

## Context

`shared/fr-authoring.md`'s substantive Group I checks — I1 (name hygiene), I2
(description hygiene), I6 (criteria presence) — are deliberately advisory-only
(`_ADVISORY_CHECKS` in `group_i.py`), by explicit, tested design: an adopted
repo's pre-existing spec must be able to clean up gradually without reddening
CI. An observed adopted repo (~50 iterates since onboarding) carried extensive
implementation-prose FR descriptions and "acceptance criteria" that were
actually test-status-report prose, and every compliance gate reported clean.
Separately, nothing checked that a criterion was in the prescribed
`(E) Given ... when ... then ...` shape (only that criteria existed and were
not bare placeholders), and a `/shipwright-adopt` `TBD` acceptance-criteria
placeholder never escalated with age.

## Decision

1. Added `shared/scripts/tools/verifiers/fr_hygiene.py` —
   `check_fr_hygiene_on_touched_rows`, a non-dodgeable F11 finalization gate.
   It recomputes, from the run's own diff (merge-base..HEAD), which FR ids had
   their Name/Description cells changed OR their acceptance-criteria digest
   changed (covering the FOLD-edit pattern §3 recommends), then runs
   I1/I2/I7-equivalent checks against exactly those rows' HEAD content. A hit
   STOPs finalization, at every complexity — modelled on
   `check_integration_coverage`'s non-complexity-gated posture, not
   `check_cross_layer_coverage`'s deliberate medium+ cost floor. Reuses
   existing per-FR digest primitives (`fr_table_reader.read_fr_rows`,
   `_layer_coverage_ac.criteria_digests`/`spec_text_at`) rather than diffing
   raw text hunks, since `/shipwright-adopt`'s spec renderer regenerates the
   whole document from one f-string.
2. Added `fr-authoring.md` §3b, prescribing the `Given/when/then` shape a
   criterion must have — the rule existed only in `glossary.md` and
   `requirement-elicitation.md` before this change, never in the document
   Group I actually enforces. Added I7 (`fr_criterion_shape.py` +
   `group_i_criteria.py` wiring) as a new advisory Group I check for the
   whole-catalogue view, and as one of the checks the new touched-row gate
   enforces for real.
3. Added I8 (`group_i_tbd_age.py`): reads how long a TBD placeholder has
   survived from git history (`git blame` on the marker's own line) rather
   than stamping new state — a second non-bullet line between an FR heading
   and its bullets would disqualify `fr_criteria`'s leading-bullet run
   entirely, zeroing out real criteria for a row carrying both. Advisory,
   MEDIUM severity, reports past 90 days; never blocks, since it targets
   exactly the legacy content a run did not touch.
4. Moved the I1/I2/I3 detector vocabulary from
   `plugins/shipwright-compliance/scripts/audit/group_i_detectors.py` to
   `shared/scripts/lib/fr_hygiene_detectors.py`, with the plugin module now a
   thin delegator (`load_shared_lib`) — mirroring `group_i_criteria.py`'s
   existing delegation to `lib.fr_criteria`. Necessary because the new F11
   verifier lives under `shared/scripts/tools/verifiers/`, which must never
   cross-plugin-import a plugin's own `scripts/audit` package (the same rule
   `integration_coverage.py`/`ci_supplychain.py` already document for their
   own SSoTs).

## Consequences

- A run that adds or edits an FR row violating I1/I2/I7 now fails
  finalization instead of shipping silently; untouched legacy rows are
  unaffected — Group I's advisory reporting there is unchanged.
- The compliance dashboard gains I7 and I8 columns/findings.
- Three existing Group I test fixtures that hardcoded the check-id set
  (`{"I1".."I6"}`) needed updating to include I7/I8 — a mechanical, expected
  consequence of adding checks to a group whose id set some tests assert
  exhaustively.
- `fr_table_reader`/`fr_criteria`/`_layer_coverage_ac` gained a second
  consumer of their pure parsing primitives, reinforcing them as the shared
  reading layer for FR-table content rather than growing a third independent
  walk.

## Rationale

An independent Opus-model validation pass, run before this iterate started,
reviewed the operator's own initial two suggestions and rejected both:
(a) blanket-promoting I1/I2/I6 to blocking everywhere contradicts
`fr-authoring.md` §7's explicit, tested rationale and would instantly redden
every adopted brownfield repo's dashboard for content nobody in the current
run touched; (b) a project-vs-adopt conditional advisory split is not
implementable at the Group I layer, which reads a spec file, not its
producer. The same pass also corrected an initial TBD-aging design (a second
stamped marker line) that would have silently broken existing criteria
detection for any FR carrying both a TBD marker and real bullets — fixed by
reading git history instead.

## External-Code-Review-Findings

Two providers (GLM via OpenRouter, GPT via Codex CLI) reviewed the diff, both
returning `SHIPWRIGHT_VERDICT: revise`. Every claim was verified empirically
(a probe repo, not trust) before disposition — two of the four substantive
claims did not survive that check:

| Provider | Finding | Disposition |
|---|---|---|
| openai | A newly added `spec.md` (absent at the merge-base) makes `spec_text_at(...base...)` return `None`, false-blocking a clean new spec | **rejected-with-reason** — empirically disproven: `spec_text_at` correctly returns `""` (not `None`) for a path absent at a valid, resolvable base commit; verified with a real two-commit probe repo. `None` is reserved for a base commit that itself does not resolve. |
| openai | I8 fires on a stale TBD even when the FR also carries real criteria, contradicting "never fires on a row with real criteria" | **accepted-with-clarification** — the Ledger claim was narrower than stated; softened to "never fires on a row with NO TBD marker at all". A TBD line left behind alongside real criteria elsewhere in the same row is dead placeholder litter, and reporting it is the correct, intended signal, not a bug. |
| openai | `_blame_epoch` does not catch `subprocess.TimeoutExpired`, risking an audit-wide crash | **accepted-and-fixed** — added to the except tuple. |
| glm | `git blame` with no revision blames the working tree; an uncommitted TBD line's `committer-time` reads as `0`, making a brand-new placeholder read as ~20,000 days stale | **rejected-with-reason** — empirically disproven: porcelain `committer-time` for an uncommitted line is the current wall-clock time, not `0` (verified against the installed git). Age reads as 0 (fresh), the safe direction. |
| glm | No test pins the "brand-new spec.md, absent at base" case | **accepted-and-fixed** — added `test_passes_when_a_brand_new_spec_file_is_added`. |
| glm | If `FrTableRow.text` is the whole physical row line, a Priority/Basis-only edit would mark a row touched and expose it to blocking | **rejected-with-reason** — empirically disproven: `text` is populated from `_fr_table_columns.title_cell`, which is the Description-preferred cell only, never the whole row. |

An internal Opus plan-review pass (recorded separately, see the iterate spec's
`## Internal Plan Review`) found the more serious, CONFIRMED defect this
external round's false positives were adjacent to: `_row_findings` judged a
touched row's WHOLE HEAD content rather than the delta, which the fold pattern
this document recommends would have made worse, not better. See the iterate
spec for that disposition table; it is the change that actually mattered.

A subsequent internal `code-reviewer` re-review of the fix for that defect
found two further CONFIRMED regressions in the fix itself (`base_row is None`
still zeroing `base_criteria` for a reinstated FR; `base_sha == commit`
silently reporting "clean" with zero rows judged) plus a bloat-baseline
anti-ratchet violation in `iterate_checks.py` — all three fixed in the same
diff, each with a new regression test.

### External LLM review, iterate-mode leg (over the spec + mini-plan)

| Provider | Finding | Disposition |
|---|---|---|
| openai | A diff-based path selector could exclude an untracked new `spec.md`, letting a dirty new spec bypass the gate as "no spec touched" | **rejected-with-reason** — empirically disproven: a newly ADDED path is an ordinary member of `git diff --name-only base..commit`'s output once committed (nothing special-cases it), and F11 only ever judges committed content by design, same as every other F11 gate. Added `test_fails_on_a_dirty_row_in_a_brand_new_spec_file` to pin it. |
| openai | I8's age may be derived from git's user-controlled AUTHOR time rather than committer time, since the tests set `GIT_AUTHOR_DATE` | **rejected-with-reason** — empirically disproven by reading the code: `_blame_epoch` parses the porcelain `"committer-time "` line only, never author-time. The tests set both env vars together (indistinguishable from the test alone), but the source is unambiguous. |
| glm | `git blame` reattributes a TBD line to whichever commit last touched it, not the one that introduced its content — an unrelated edit or reflow resets the age clock | **accepted-with-clarification** — a real, already-partially-documented limitation (the "Known imprecision" paragraph already covered reworded-and-retyped text); extended that paragraph to name line-movement/reflow explicitly rather than leave it a silent gap next to the one that was already written down. No behavior change: understating age is the accepted safe direction. |
| glm | Row-identity matching between base and head (by FR id) is implicit, not stated | **accepted-and-fixed** — added a paragraph to `fr_hygiene.py`'s module docstring naming FR id as the sole join key and stating what happens to an id that changes (judged in full, the safe direction). |
| glm | Squashed/rebased trunk history could make the "unreadable base spec text" fail-closed branch a steady state rather than a rare path | **rejected-with-reason** (deferred) — a general exposure of merge-base-based F11 gates, not specific to this one; out of scope for this iterate. |
| glm | The rejected I1/I2 allowlist follow-up should be prioritized near-term, not backlog, given the gate is non-dodgeable | **acknowledged** — a prioritization opinion on an already-filed follow-up, not a new finding; no code change. |
| glm | I8's one-`git-blame`-per-FR cost was already flagged; ensure the deferral is actually tracked | **acknowledged** — already filed as a follow-up in the Internal Plan Review disposition table above. |

Verdicts: `glm=approve`, `openai=revise` (not a contradiction requiring
resolution — one step apart). Both actionable claims in the `revise` were
disproven on inspection; the accepted findings are documentation
clarifications with no behavior change.

### Stage-3 doubt review (triggered by the cross-plugin import into
`fr_hygiene_detectors`/`fr_criteria`/`fr_criterion_shape`/`fr_table_reader`)

Fresh-context, biased-to-disprove pass after Stage-2's code-reviewer had
already re-reviewed the fix twice. Two HIGH, four MEDIUM, one LOW — five
addressed with code + a new regression test each, two rejected with recorded
reasoning:

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | HIGH | `_iterate_changed_paths`'s silent single-commit fallback (when the merge-base can't be resolved) could report "no spec.md touched" narrowly true of one commit, before the gate's own merge-base fail-closed check ever ran — a spec.md edit landing in an EARLIER commit than HEAD would never be seen | **accepted-and-fixed** — the gate no longer calls `_iterate_changed_paths` at all; it resolves `_branch_base_commit` once, fails closed on it immediately, and only then computes the branch-range diff directly. The merge-base check now runs unconditionally before any "was spec.md touched" question. New test: `test_a_dirty_row_added_in_an_earlier_commit_is_still_caught_at_a_later_head`. |
| 2 | HIGH | `_branch_base_commit`'s local `main`/`master` candidates can resolve to `commit` itself for an unpushed commit made directly on the local trunk, corroborated by a real (behind) `origin/main` — the same shape the code already excludes `@{u}` for — falsely reporting "already on the trunk, no range to judge" | **rejected-with-reason** — this is `_branch_base_commit`'s own pre-existing, already-doubt-reviewed behavior (its docstring explicitly reasons through the local-`main` case and calls the on-the-trunk answer correct when HEAD genuinely is local `main`), inherited unchanged by three OTHER F11 gates (`derived_snapshot_gate`, `ci_supplychain`, `decision_log_gate` via `_iterate_changed_paths`) before this iterate ever used it. Not a new defect this gate introduces; a systemic resolver behavior out of this iterate's scope. |
| 3 | MED | `_row_map` never passed a `rejects` accumulator to `read_fr_rows` — a row this run adds with a non-canonical id (e.g. hand-typed `FR-1.02` for the canonical `FR-01.02`) never becomes a `FrTableRow` at all, so it is invisible to `_touched_ids`/`_row_findings` and a dirty row escapes purely via an id typo | **accepted-and-fixed** — `_row_map` now accepts `rejects`; a new `_new_reject_findings` compares the reader's own reject accumulator at base vs head and flags any reject that is NEW at head. New test: `test_a_non_canonical_id_this_run_added_is_still_flagged`. |
| 4 | MED | `_touched_ids` decided "did this row's criteria change" via `_layer_coverage_ac.criteria_digests` (restricted to a recognised `## Acceptance Criteria` REGION when its anchor id-set matches the whole document's), while `_row_findings` decided "what are the new criteria" via `fr_criteria.criteria_for` (whole-document) — the region guard only compares which IDS are found, not which BLOCKS, so a stray extra anchor for an id already found inside the region passes the guard unnoticed while sitting outside the slice it returns | **accepted-and-fixed** — added `_whole_doc_criteria_digests`, reimplementing the same pooling at whole-document scope with `fr_criteria`'s own primitives, so both halves of the judgment share one scope; `_layer_coverage_ac.criteria_digests` is no longer imported by this gate. New test: `test_a_criterion_anchored_outside_the_recognised_ac_region_is_still_touched`. |
| 5 | MED | The TBD-marker parity test only pinned the CONSTANT, not the contract — `spec_document.py`'s marker emission was conditional on `has_any_ac`, and a wholly-TBD adoption (the common freshly-adopted shape) rendered undifferentiated prose with no per-FR heading at all, so I8 could never fire on exactly the specs most likely to carry a stale TBD | **accepted-and-fixed** — `spec_document.py`'s Acceptance Criteria block now always renders a per-FR `### FR-xx.yy` heading (with `TBD_MARKER` where there is no AC), regardless of `has_any_ac`; the old branch's E2E-baseline note is kept as a lead-in when no feature has an AC. New behavioral test: `test_an_all_tbd_adoption_still_renders_the_marker_under_an_fr_heading` (integration-tests), rendering through the real `_render_spec_md` rather than a hand-typed fixture. |
| 6 | MED | `fr_hygiene_detectors._PASCAL_RE`'s allowlist (`_NOT_SYMBOLS`) has no general escape hatch, so an unlisted two-capital-segment brand/product noun in a touched row's Name/Description would false-block finalization, with no warm-up period under the operator's "block immediately" rollout decision | **rejected-with-reason** — pre-existing detector logic, unchanged by this iterate (moved verbatim from `group_i_detectors.py`, already reviewed and running for Group I's advisory I1/I2 checks). The blast radius is one row, immediately diagnosable (the finding names the row and category) and immediately actionable (reword, or a one-line `_NOT_SYMBOLS` addition) — not a systemic block on unrelated work. A shared-vocabulary allowlist-escape-hatch mechanism is a larger, cross-cutting change out of this iterate's scope; filed as a follow-up if false positives are observed in practice. |
| 7 | LOW | `spec_text_at`'s underlying git calls carry no `timeout`; `_branch_base_commit` used to be resolved twice per invocation (once for "was spec.md touched", once for reading either side) | **accepted-and-fixed** (the second half) — as a consequence of fix #1's refactor, `_branch_base_commit` is now resolved exactly once. `spec_text_at`'s own timeout gap is `_layer_coverage_ac`'s pre-existing surface, not introduced here; left as a separate, smaller follow-up rather than touching a shared module for a LOW finding on this iterate's critical path. |

### Second doubt-review pass (round 2, after round 1's five fixes landed)

A second, fresh-context doubt-review pass run after round 1's fixes were
already in place. Four more genuine gaps found — all in the cross-row/
cross-file identity handling round 1's fixes had not touched — all
accepted-and-fixed with a new regression test each
(`shared/tests/test_check_fr_hygiene_doubt3.py`):

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | HIGH | Row identity was scoped to one `spec.md` file's own base/head text; a legacy dirty row RELOCATED to a different split's `spec.md` (`fr-authoring.md` §4's own prescribed remedy for "filed in the wrong split") had no base-side history at its new path, so it was judged in full instead of on the delta — the exact false-positive the delta-scoping fix was built to prevent, now reachable via a move instead of an edit | **accepted-and-fixed** — `fr_hygiene.py` now builds a `global_base_rows` map pooling every touched spec's base-side rows, and falls back to it when a row's own file has no base-side entry for that id. New tests: `test_a_row_moved_between_spec_files_is_not_reflagged_when_unchanged` (exempts a byte-identical move), `test_a_row_moved_between_spec_files_is_flagged_for_a_violation_added_during_the_move` (still catches a violation smuggled in during the move). |
| 2 | MED | A criterion anchored under a non-canonical heading id (e.g. `FR-1.02` missing zero-pad) never joined its intended row's criteria pool on either side of the id comparison — invisible to every FR-catalogue check, including this gate, unless the mismatch itself is surfaced | **accepted-and-fixed** — new `_new_orphan_anchor_findings` flags a NEW (not present at base) anchored block whose id is non-canonical and carries a real criterion. New test: `test_orphan_criterion_anchor_with_non_canonical_id_is_flagged`. |
| 3 | HIGH | `_row_map`'s dict-based lookup keeps whichever occurrence of a duplicate id is LAST in document order — a dirty new row added ABOVE an existing clean legacy row sharing its id is silently shadowed by the clean one, so neither `_touched_ids` nor `_row_findings` ever sees the dirty occurrence | **accepted-and-fixed** — new `_new_duplicate_id_findings` reports any id with more than one active row at HEAD that was not already duplicated at base, unconditionally blocking (the gate cannot honestly tell which occurrence is which). New test: `test_a_new_duplicate_id_at_head_is_flagged`. |
| 4 | LOW | `_new_reject_findings`'s base-vs-head comparison used SET membership, collapsing two rejects sharing the same `(id, reason)` pair into one — a run duplicating or re-typing an already-malformed legacy row under the same id/reason was invisible, since the legacy occurrence masked the run's own new one | **accepted-and-fixed** — the comparison now uses `Counter` multiplicity; only the surplus beyond how many were already present at base is reported as new. New test: `test_a_second_row_with_the_same_malformed_id_and_reason_is_flagged`. |

### Architecture review (Step 3.5, Branch A second call — "should this be
built at all")

Brief: `.shipwright/planning/iterate/iterate-2026-09-06-fr-hygiene-touched-rows/architecture_brief.md`
(no rejection rationale included, per the pass's own rule). Verdicts:
`glm=approve`, `openai=revise` — one step apart, no `reject`, so integrated
rather than stopped-and-asked.

| # | Sev | Reviewer | Finding | Disposition |
|---|---|---|---|---|
| 1 | MED | openai | I8's `git blame`-based TBD age computation and 90-day threshold is "policy machinery for a recoverable, already-visible documentation debt" — drop it as a standing mechanism not worth its upkeep | **rejected-with-reason** — I8's threshold and inclusion were an explicit, binding operator decision made before this spec was written ("TBD-aging threshold is 90 calendar days"), not scope this pass discovered; dropping it post-hoc on a proportionality judgment would silently reverse an operator decision. It is also the cheaper of the two mechanisms under review — advisory-only, no gate, no persisted state, reads git history rather than storing it — a property glm's independent `approve` credits explicitly ("the difference between a mechanism and a liability"). |
| 2 | MED | glm | Blocking on heuristic prose detectors (`_PASCAL_RE`) with no allowlist makes a false positive on a touched row an unclearable F11 stop; the allowlist follow-up should be treated as a real obligation, not optional | **acknowledged, already tracked** — the identical gap was raised independently by the Stage-3 doubt review (finding #6 above) and rejected-with-reason there for the same scope boundary; the follow-up glm names is the same one already filed in the Internal Plan Review and doubt-review tables, not a new item. |

Both reviewers converged on Option A (the diff-scoped F11 gate, as proposed)
being the right shape; B (global blocking promotion) and C (advisory-only,
detective-audit-only) were both independently rejected by the reviewers on
the same grounds already reasoned through in the pre-build validation pass
below.

### Supplementary Stage-3 doubt review (second pass, fresh context)

The Stage-3 doubt review above was found unrecorded in `reviews.json` when
this run resumed (a lost write between the subagent returning and the record
being made — the exact window `iteration-reviews.md`'s immediate-write
mandate names as a known gap). Rather than reconstruct that record from ADR
prose, a genuinely fresh doubt-reviewer pass was run against the diff as it
stood after all of the above fixes; `reviews.json`'s own `doubt` row was
found already durably recorded (salvaged) once this session looked, so this
second pass is documentation of ADDITIONAL diligence, not the row-owning
pass. Six doubts, two HIGH, three MEDIUM, one LOW:

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | HIGH | Row identity was actually `(FR id, spec.md PATH)`, not the FR id alone the module docstring claimed: a row this run only RELOCATES between two touched `spec.md` files — `fr-authoring.md` §4's own prescribed remedy for "filed in the wrong split" — had no base-side counterpart at its NEW path and was judged in full on content it never touched | **accepted-and-fixed** — `fr_hygiene.py` now builds `global_base_rows`, pooling every touched path's base rows into one id-keyed map before judging any row, and `_row_findings` pools criteria from ALL touched paths' base text (`base_texts`), not just the row's own HEAD path. New tests: `test_a_row_moved_between_spec_files_is_not_reflagged_when_unchanged`, `test_a_row_moved_between_spec_files_is_flagged_for_a_violation_added_during_the_move` (the second pins that a genuine edit made DURING the move is still caught — the fix only exempts a byte-identical relocation). |
| 2 | HIGH | The recorded rejection of the original doubt round's finding #5/#6 (no escape hatch for the `_PASCAL_RE`/code-symbol heuristic) argued a one-row blast radius reachable by "reword, or a one-line `_NOT_SYMBOLS` addition" — but `_NOT_SYMBOLS` ships inside the plugin cache; a consumer repo running the installed plugin cannot edit it, and a two-segment capitalised product name (`MediPlan`, `FinTrack`) now hard-blocks finalization on every touched row naming it, permanently, with zero recourse | **rejected-with-reason, escalated** — this is the THIRD independent review to raise this exact gap (Internal Plan Review "architecture/high"; the original Stage-3 pass's finding #5 with `LinkedIn`/`WhatsApp`/`PowerPoint`; now this pass with a sharper "no consumer recourse at all" framing). A rule three independent reviewers keep re-raising is evidence about the rule (`iteration-reviews.md`'s own stated principle, applied to itself). Demoting `code-symbol` to non-blocking inside this gate was considered and rejected here too — it would contradict this iterate's own approved AC1, which names "code symbol" as one of the four detection kinds F11 must STOP on, and weakening an approved acceptance criterion is not a call this session makes unilaterally. **Recommended, explicitly, as the very next follow-up iterate** — flagged in this run's F12 closing summary — rather than deferred a fourth time with the same reasoning. |
| 3 | MEDIUM | `_row_map`'s dict comprehension lets a LATER duplicate id in the same `spec.md` silently overwrite an earlier one; a dirty new row this run adds ABOVE an existing clean legacy row sharing its id is shadowed by the clean one and never reaches `_row_findings` at all — I4 is the check that names a duplicate id a defect, but I4 is not wired into `run_all_checks`, so nothing at F11 ever sees it either | **accepted-and-fixed** — `_new_duplicate_id_findings` reports any id duplicated at HEAD but not already duplicated at base as an unconditional, unresolvable-by-this-gate finding (rather than trying to guess which occurrence is dirty, which a dict-based comparison cannot answer soundly) — the only way past it is making the id unique again, at which point exactly one row remains to judge honestly. New test: `test_a_new_duplicate_id_at_head_is_flagged`. |
| 4 | MEDIUM | I8's one-`git-blame`-subprocess-per-TBD cost was deferred as a performance nit before this same diff's doubt-fix #5 (round 1) widened its own fan-out: a wholly-TBD adoption now renders a per-FR heading with `TBD_MARKER` for EVERY requirement, making the freshly-adopted repo the MAXIMUM-fan-out case instead of the minimum the original deferral assumed | **rejected-with-reason, deferred** — I8 is advisory-only dashboard content, never on the F11 blocking path; a slow compliance audit is a UX cost, not a correctness one. Still a real, now-sharper-priced follow-up (batch to one `git blame --porcelain` per spec file) — noted for the same next-iterate slot as finding #2 rather than fixed under this iterate's existing scope. |
| 5 | MEDIUM | `fr_criteria`'s heading/bold anchor regex accepts `FR[-\s]?\d+(?:\.\d+)*` and does not zero-pad (`normalise_fr_id` only turns a space into a dash), while `fr_table_reader` enforces the canonical `FR-XX.YY` shape on TABLE row ids — a criterion folded in under a mistyped anchor (`### FR-1.02` for the canonical `FR-01.02`) pools under a key no table row or check will ever look up, invisible to `_touched_ids`/`_row_findings` on both sides of the join, with I6 seeing only "no criteria" rather than the real cause | **accepted-and-fixed** — `_orphan_anchor_findings` reports a NEW (not present at base), non-canonical-shaped anchor id that carries a real criterion, making the mismatch itself visible rather than silently dropping the content it guards (it does not attempt to judge the criterion's own shape — that stays `_row_findings`'s job once the id is fixed). New test: `test_orphan_criterion_anchor_with_non_canonical_id_is_flagged`. |
| 6 | LOW | `_new_reject_findings` compared `(id, reason)` pairs as a SET, losing multiplicity: a legacy reject sharing the same pair as a NEW row this run adds with the identical id/reason masked the new one | **accepted-and-fixed** — rewritten with `collections.Counter`, reporting only the surplus beyond however many were already present at base. New test: `test_a_second_row_with_the_same_malformed_id_and_reason_is_flagged`. |

All four accepted fixes are pinned by new real-git regression tests in a new
file, `shared/tests/test_check_fr_hygiene_doubt3.py` (split out from the
start rather than growing `test_check_fr_hygiene_delta_scope.py` past 300
lines again). The two rejections are both escalations of previously-recorded
decisions, not new unexamined risk — see the Test Completeness Ledger's
updated rows in the iterate spec for the pass/fail evidence.

## Rejected alternatives

- Global promotion of I1/I2/I6 out of `_ADVISORY_CHECKS`.
- A producer-conditional (`/shipwright-project` vs `/shipwright-adopt`)
  advisory/blocking split.
- Stamping a new "TBD since" marker line next to the existing TBD sentinel.
- Folding the I7 shape-check primitive into `fr_criteria.py` itself, rejected
  to keep that module's criteria-FINDING logic (shared by S5, the cross-layer
  hard gate, and I6) untouched by any future tightening of the shape rule.
