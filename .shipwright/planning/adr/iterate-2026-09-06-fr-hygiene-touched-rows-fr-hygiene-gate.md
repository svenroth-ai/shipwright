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

### Tier-3 PR-review gate (PR #679, `openai/gpt-5.6-luna`)

**Reviewer finding:** `_blame_epoch` (`group_i_tbd_age.py`) trusts `git blame --porcelain`'s
`committer-time` for the synthetic "Not Committed Yet" pseudo-commit that
blames an uncommitted line. The module docstring already claimed this reads
as the current wall-clock time on this repo's own git (empirically probed
during the original doubt round), but the reviewer's underlying concern —
that some git releases instead report `0` for that same pseudo-commit,
turning an uncommitted TBD into a manufactured ~20,000-day-stale finding — is
a real, version-dependent behavior this function had no defence against
either way. Re-verified the ORIGINAL claim first (this repo's git: still
non-zero, confirmed by a fresh probe), then treated the reviewer's point as
a portability gap rather than dismissing it on that single data point.
**Fixed:** `_blame_epoch` now treats any non-positive parsed
epoch as unavailable (`None`, the module's existing "skip it" convention),
matching the reviewer's own suggested remedy exactly. New test
`test_blame_epoch_treats_non_positive_committer_time_as_unavailable` pins the
defensive branch directly (via a faked subprocess result, since it is not
reproducible against this machine's own git) rather than relying on a
specific CI runner's git version to exercise it.

### Tier-3 PR-review gate, round 2 (PR #679, `openai/gpt-5.6-luna`)

**Reviewer finding:** `_new_duplicate_id_findings` (`_fr_hygiene_touched.py`) was called
once per touched `spec.md` path, counting duplicate ids only WITHIN that one
file's text — but FR ids are catalog-wide, and `fr_hygiene.py`'s own
`global_base_rows` already pools rows across every touched path for exactly
this reason. A new duplicate id with exactly one occurrence added to each of
two touched spec files had one occurrence per file on either side of the
per-file count, so neither file's local count ever exceeded one — invisible,
confirmed by reproducing it: the existing single-file test still passed, and
a new cross-file case failed under the old implementation.
**Fixed:** `_new_duplicate_id_findings` now takes the list of
every touched path's base/head text and pools counts across all of them
before comparing, matching `global_base_rows`'s existing scope (touched paths
only — this does not scan the whole catalogue, consistent with this gate's
documented "touched only" boundary). `fr_hygiene.py` calls it once, outside
the per-path loop. New test
`test_a_new_duplicate_id_split_across_two_touched_files_is_flagged` pins the
cross-file case; the existing single-file duplicate test still passes
unchanged. The review's non-blocking comment (trim repeated review-process
narrative from the ADR/spec) is deferred — noted, not actioned in this PR, to
avoid re-editing settled sections mid-review-cascade.

### Tier-3 PR-review gate, round 3 (PR #679, `openai/gpt-5.6-luna`) — three
findings across two review passes, addressed together

**Reviewer finding (vacuous criterion shape, flagged in the very first review
pass on this PR, before the I8/round-2 fixes above — never actually
addressed by an intervening commit, confirmed by reading
`fr_criterion_shape.py`'s regex directly before this fix):** `_GIVEN_WHEN_THEN_RE` was
`\bgiven\b.*?\bwhen\b.*?\bthen\b` — the three keywords in order, with `.*?`
(possibly zero characters) between them, so a literal `Given when then`
matched despite carrying no actual clause. A blocking gate accepting a
vacuous criterion as "well-formed" defeats the whole point of I7.
**Fixed:** the regex now requires `\s+\S` (at least one
non-whitespace character) between `given`/`when`, between `when`/`then`, and
after `then`, so each keyword must be followed by real content before the
next keyword (or end of string) is reached. New tests
`test_vacuous_given_when_then_is_not_well_formed`,
`test_vacuous_missing_when_clause_is_not_well_formed`, and
`test_vacuous_missing_then_clause_is_not_well_formed` pin exactly the three
cases the review named (`Given when then`, `Given x when then`, `Given x when
y then`); all six pre-existing tests in the same file still pass, including
the well-formed and punctuated real-world example.

**Reviewer finding (Finding A — pre-existing duplicate, edited non-surviving
occurrence):** `_new_duplicate_id_findings` only ever compared duplicate-id
SETS (`_dupes(head) - _dupes(base)`), so an id already duplicated at base
stayed excluded even when this run edited one of its occurrences' actual
content — `_row_map`'s last-wins collapse means the edit can land on the
occurrence that does NOT survive the dict join, so `_touched_ids` sees no
change at all for that id (the surviving occurrence's cells never moved).
Reproduced first: a two-occurrence duplicate seeded at base, one occurrence's
Description edited to leak an implementation detail at HEAD while the other
stays byte-identical, failed to be flagged under the prior implementation.
**Fixed:** replaced the count-only `_dupes` helper with
`_pooled_occurrences` (pools every active row's `(name, description)` content
by id, across every touched path) and compare the pooled OCCURRENCE
MULTISET, not just the count — an unchanged duplicate (identical multiset on
both sides) stays excluded, matching the existing "touched only" boundary,
while any duplicate whose multiset differs is reported, whether the id is
newly duplicated or pre-existing with an edited member. New test
`test_editing_one_occurrence_of_a_pre_existing_duplicate_id_is_flagged` pins
the reproduced case; the existing new-duplicate and cross-file tests still
pass unchanged.

**Reviewer finding (Finding B — content-only edit to an already-rejected
row):** `_new_reject_findings` keyed multiplicity on `(id, reason)` alone —
editing an already-rejected row's raw cell content while its id and
rejection reason stayed the same (still `non_canonical_id`, still that id)
matched an existing base-side key and was silently absorbed as "already
there"; the content changed, but a rejected row never produces an
`FrTableRow`, so nothing else in this gate judges the changed text either.
**Fixed:** the comparison key became `(id, reason, raw)`, where `raw` is the
reader's own pipe-joined-cells fingerprint (`fr_table_reader._reject` already
captures it, first 200 chars) — an edit to the row's content changes `raw`
and therefore the key, so it is counted as new regardless of `(id, reason)`
staying identical. New test
`test_editing_an_already_rejected_rows_content_is_flagged` pins this; the
existing same-`(id, reason)`-legacy-vs-new test (which never edits content,
only adds a second row) still passes unchanged. **Superseded in round 4
below**: `raw` itself is truncated to 200 characters, so this fix had its own
blind spot for an edit landing entirely past that boundary — see the round-4
section.

**Incidental**: `_fr_hygiene_touched.py` crossed 300 lines while implementing
the Finding-A fix (312 lines after the edit). Split the four structural-
anomaly detectors (`_orphan_anchor_findings`, `_pooled_occurrences`,
`_new_duplicate_id_findings`, `_new_reject_findings` — defects that make a
row INVISIBLE to the touched/clean comparison, as opposed to judging what a
visible row says) into a new sibling module, `_fr_hygiene_anomalies.py`,
matching this iterate's own established precedent (`fr_hygiene.py` was
itself split out of an earlier oversized file the same way). `fr_hygiene.py`
now imports the anomaly detectors from `_fr_hygiene_anomalies` and the
core comparison helpers from `_fr_hygiene_touched`; no test imports the
internal functions directly (all go through the public
`check_fr_hygiene_on_touched_rows` entry point), so the split needed no test
changes.

### Tier-3 PR-review gate, round 4 (PR #679, `openai/gpt-5.6-luna`) — two
further correctness gaps, plus a documentation-tone note

**Reviewer finding (duplicate-id detection still scoped to touched files
only):** the round-3 fix pooled every TOUCHED spec's base/head text, but a
new row can collide with an id that lives in a spec.md this run's diff never
touches at all — a catalogue file outside the diff was never read, so its
occurrence of the id was invisible and the new row's one occurrence looked
unique. **Fixed:** duplicate-id detection now enumerates the WHOLE FR
catalogue at base and at HEAD via `git ls-tree` (`_fr_hygiene_catalog.py`,
new module — `_catalog_spec_paths_at`/`catalog_spec_paths_at`), reads every
catalogue `spec.md` (touched or not) on both sides, and pools those texts for
`_new_duplicate_id_findings` specifically; every OTHER check in this gate
(row hygiene, orphan anchors, rejects) stays scoped to touched paths only —
duplicate identity is the one property that is genuinely catalogue-wide, not
a property of what this run happened to edit. New test
`test_a_new_duplicate_id_against_an_untouched_catalog_file_is_flagged` seeds
a second spec.md on the trunk that the run's own commit never touches, then
adds a colliding id in the touched file; fails under the round-3 code path,
passes under this one.

**Reviewer finding (reject fingerprint truncated at 200 characters):** the
round-3 fix keyed the reject comparison on `raw` — the reader's own
pipe-joined-cells field — but that field is itself truncated to 200
characters for display, so an edit landing entirely AFTER character 200 kept
an identical `(id, reason, raw[:200])` triple and stayed silently absorbed as
unchanged. **Fixed:** `fr_table_reader._reject` now also captures
`raw_digest` (a sha256 of the FULL, untruncated pipe-joined cells) alongside
the existing truncated `raw` (kept as-is for any existing display/preview
use); `_new_reject_findings` keys on `(id, reason, raw_digest)` instead. New
test `test_editing_an_already_rejected_row_past_the_raw_truncation_boundary_is_flagged`
constructs two rows whose first 200 characters are byte-identical and whose
content differs only after that boundary — verified by direct computation,
not assumption, that `raw[:200]` is identical between the two rows before
relying on the test to prove the fix; fails under the round-3 `raw`-only key,
passes under `raw_digest`.

**Documentation-tone note (not a code finding):** one review pass in this
round separately flagged this ADR's own review-disposition sections — the
verdict-style headings this document uses to record each pass's outcome —
as reading like an attempt to direct a CURRENT review rather than as neutral
history. That specific complaint did not recur in the very next pass over
the same unchanged text, and the pattern itself already existed in this same
ADR (the I8 and round-2 sections above) across several earlier passes without
being flagged — evidence this was model-level noise on that one pass rather
than a stable, repeatable objection. Treated as a genuine, if narrow, piece
of feedback anyway rather than dismissed outright: every verdict-style
heading in this document (`**BLOCK**`/`**Accepted-and-fixed**`) is reworded
to neutral, declarative phrasing (`**Reviewer finding:**`/`**Fixed:**`) that
preserves the exact same substantive content — what was found, what was
verified, what changed, which test pins it — without a word that could read
as asserting a verdict on whatever review is currently in progress. The
review's other, longer-standing comment (trim the ADR's repeated
review-process narrative for length) remains deferred, as recorded in round
2 above — a separate concern from this one, about volume rather than tone.

### Bloat gate: `fr_table_reader.py` crossed 300 lines from the `raw_digest`
addition

The round-4 `raw_digest` fix (above) added ~14 lines to
`shared/scripts/lib/fr_table_reader.py`, taking it from 297 to 311 and
tripping the Stop-hook bloat gate (`bloat_gate_on_stop.py`) as a NEW crossing
— unlike the git pre-commit anti-ratchet hook, the Stop hook blocks a first-
time crossing too, not only growth past an existing baseline entry, and this
file had no prior baseline entry. Split, not exempted, per the gate's own
"How to clear this block" preference — but this module carries a documented,
tested, three-load-style sibling-import contract (ADR-045: flat, package, and
file-location-under-a-sentinel), so an arbitrary chunk-split risked breaking
whichever style the split didn't anticipate.

**What actually moved.** Two independent, low-risk changes, done together:

1. **The `_sibling` loader mechanism** (import-style resolution, the
   `_ALLOWED_SIBLINGS` allowlist, the `_SIBLINGS` cache) split into
   `_fr_table_reader_loader.py`. The load-style detection ITSELF still runs
   inside `fr_table_reader.py` (a bare relative import of a fresh sibling
   module would fail under the "flat" style, which has no package context to
   resolve one) — only the actual `importlib.import_module` dispatch, keyed
   by an explicitly-PASSED `package` string, moved out. `_sibling()` in
   `fr_table_reader.py` is now a thin wrapper forwarding its own
   `__package__` to the loader.
2. **The module docstring's numbered "convergence rules" list** (~30 lines,
   items 1-8) was pure duplication: ADR-107 already carries the same rules as
   a fuller C1-C10 table with rationale, written when the reader was first
   consolidated. Replaced with a short pointer paragraph; no rule's substance
   was lost, only its second, staler copy.

**Verified, not assumed, that the split preserves every load style**:
`integration-tests/test_fr_table_reader_load_styles.py` (13 cases — all four
load styles × three checks, plus the leaf-import guard) passes unchanged
except for two lines updated to the new attribute path
(`reader._loader_mod._SIBLINGS`/`_ALLOWED_SIBLINGS`, since those names moved
off the `fr_table_reader` module object itself). The full fr_table_reader
consumer surface (101 tests across `test_fr_table_reader_boundaries.py`,
`_contract.py`, `_probes.py`, `test_fr_table_shape_convergence.py`,
`test_requirements_catalog_parsers.py`, `test_requirements_corpus_matrix.py`)
also passes unchanged. Final size: `fr_table_reader.py` 259 lines,
`_fr_table_reader_loader.py` 84 lines — both under the 300-line guideline
with margin, no baseline entry needed.

### Tier-3 PR-review gate, round 5 (PR #679, `openai/gpt-5.6-luna`) — a
reviewer claim checked and NOT reproduced, hardened anyway

**Reviewer finding:** `_orphan_anchor_findings` calls
`fr_table_reader.CANONICAL_FR_RE.match(fr_id)`, and the review's concern was
that `.match` only anchors at the START of the string, so an id carrying a
canonical PREFIX but extra trailing characters (`FR-01.02.03`,
`FR-01.02suffix`) could slip past as if canonical.

**Checked empirically before changing anything**, per this session's own
standing practice of never trusting a review claim's specifics without
verifying: `CANONICAL_FR_RE` (`requirement_model.py`) is
`^FR-\d{2}\.\d{2}$` — already `$`-anchored. A direct interpreter probe
confirmed `.match("FR-01.02.03")` and `.match("FR-01.02suffix")` both
already return no match (the pattern's own end anchor rejects them); the
ONE case where `.match` and `.fullmatch` genuinely differ is a literal
trailing-newline string (`"FR-01.02\n"`, which `.match` accepts and
`.fullmatch` does not) — a shape `fr_criteria`'s anchor-id extraction does
not produce. **The two specific exploit shapes the review named do not
reproduce.**

**Fixed anyway.** Pairing `.match` with an end-anchored pattern is a real
bug shape in general, even in the one place it happens not to bite today —
a future edit to `CANONICAL_FR_RE` that dropped the trailing `$` would
silently reopen exactly the hole the review described, with nothing here to
stop it. Switched to `.fullmatch`, which is unconditionally correct and
costs nothing (identical result for every real anchor-id input). New test
`test_a_new_anchor_with_a_canonical_prefix_but_extra_suffix_is_flagged`
pins the named `FR-01.02.03` case at the gate level (not just the regex in
isolation) — it already passed before this change (confirming the "not
reproduced" finding) and continues to pass after, so the test also serves
as a non-regression pin for the `.fullmatch` swap itself.

### Tier-3 PR-review gate, round 6 (PR #679, `openai/gpt-5.6-luna`) — an
existing non-canonical anchor's edited criterion was invisible

**Reviewer finding:** `_orphan_anchor_findings` skips every head anchor
whose id appears anywhere in `base_ids`, even when its criterion block was
edited or a new block was added under that existing non-canonical id;
`_touched_ids` then filters that id out because it has no canonical table
row. Requested: compare base and head criterion blocks/digests for
non-canonical anchors and report any newly added or changed block (or
otherwise fail closed on a touched non-canonical anchor), plus a regression
test covering an existing `FR-1.02` anchor whose criterion is edited or
supplemented.

**Confirmed genuine by direct code inspection** (unlike round 5): the prior
body kept a `base_ids`/`seen` id-SET exclusion —
`if fr_id in seen or fr_id in base_ids: continue` — which drops an id the
moment it is found anywhere at base, with no look at whether the content
under it changed. A criterion added or edited under an ALREADY-malformed
anchor (`### FR-1.02` present at base, its acceptance criteria changed at
head) is exactly as invisible to every downstream FR-catalogue check as one
under a brand-new malformed anchor — neither ever joins a canonical table
row's pool — but the old code only ever reported the "brand-new anchor id"
half of that bug class.

**Fixed** by switching the comparison from an id SET to pooled criterion
CONTENT, reusing `_fr_hygiene_touched._whole_doc_criteria_texts` (already
built for exactly this: FR id → every criterion text pooled for that id
across the whole document, canonical or not, via the same
`fr_criteria.iter_anchored_blocks`/`block_criteria(strict=False)` primitives
`_orphan_anchor_findings` used directly before). For every non-canonical id
present at head with a non-empty pooled criteria list: if its pooled
criteria match base's pooled criteria for that id exactly (as a sorted
comparison), it is untouched legacy and stays excluded — same "touched
only" boundary as every other detector in this module; otherwise (new id at
head, or an existing id whose pooled criteria differ) it is reported. This
also let `_orphan_anchor_findings` drop its direct dependency on
`fr_criteria` entirely (ruff flagged the now-unused import; removed).

**New test**
`test_an_existing_non_canonical_anchors_edited_criterion_is_flagged`
(`shared/tests/test_check_fr_hygiene_doubt4.py`) seeds a base spec with an
`FR-1.02` anchor carrying a criterion, then edits that criterion's text at
head with no other change — pins exactly the case the review named. Full
targeted suite (`test_check_fr_hygiene.py` + `_doubt3.py` + `_doubt4.py`,
24 tests) and `uvx ruff@0.15.15 check .` both pass after the change.

## Rejected alternatives

- Global promotion of I1/I2/I6 out of `_ADVISORY_CHECKS`.
- A producer-conditional (`/shipwright-project` vs `/shipwright-adopt`)
  advisory/blocking split.
- Stamping a new "TBD since" marker line next to the existing TBD sentinel.
- Folding the I7 shape-check primitive into `fr_criteria.py` itself, rejected
  to keep that module's criteria-FINDING logic (shared by S5, the cross-layer
  hard gate, and I6) untouched by any future tightening of the shape rule.
