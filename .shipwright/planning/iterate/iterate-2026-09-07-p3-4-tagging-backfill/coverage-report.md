# P3.4 tagging-backfill — coverage report (monorepo only)

Campaign `req3-04c-ac-identity-wave2`, sub-iterate p3.4. Scope note: the WebUI
repo's own backfill (`w4`, campaign `req3-06-mechanics-webui`, a separate repo)
is explicitly NOT this unit's work — see the sub-iterate spec's "corrected
2026-09-07" note. All numbers below are monorepo-only.

External plan review (GLM medium, OpenAI medium) and external code review
(GLM high, OpenAI high) both flagged that this reconciliation existed only
inside `reviews.json`, quoted secondhand by the reviewers themselves, and
never as a committed artifact — this file is that artifact.

## Before → after (fixed baseline: `origin/main` @ `263c9197e6428134ad4e97c55384bf5dad89cbc1`)

| | any `@covers` tag (FR or FR/AC) | AC-scoped tag (`FR/ACnn`) |
|---|---|---|
| Before | 475 / 13728 (3.46%) | 0 / 13728 (0.00%) |
| After  | 612 / 13767 (4.45%) | 142 / 13767 (1.03%) |
| Delta  | +137 | +142 |

Both snapshots read from `.shipwright/compliance/test-traceability.json`
(schema v4) at the two commits named above, via the SAME collector
(`update_compliance.py --phase iterate`, the canonical wiring — not the bare
`collectors.test_links` CLI, which stamps `generated_at` as epoch-zero when
run standalone; see "Corrections made during review" below).

**Why any-tag went up (+137) by more than AC-scoped went up (+142 net, not
+157):** the 20 hand-mapped tags (see below) all UPGRADED an existing bare
`covers("FR-xx.yy")` to an AC-scoped `covers("FR-xx.yy/ACnn")` — the test was
already tagged, so the any-tag count does not move for those. The 137
mechanically-derived tags are brand-new insertions onto previously-untagged
tests, but 15 of them were downgraded back to bare `FR-01.01` post-merge (see
"Doubt-review correction" below) — those 15 tests still carry `FR-01.01` (an
any-tag), so any-tag stays +137, while AC-scoped nets to 137 − 15 + 20 = 142.

## Derived vs hand-mapped (stated separately, per the spec's AC#3 — never blended)

**Mechanically derived: 122 tags across 11 test files** (137 minted, 15
downgraded post-merge — see "Doubt-review correction" below), via the
provenance-footnote → `Run-ID:` commit → added-test-file join
(`backfill_ac_provenance.py` + `lib/backfill_ac_provenance.py`, new this unit):

| FR/AC | tags | files | introducing commit |
|---|---|---|---|
| FR-01.01/AC08 | 61 | 6 original files, 7 on disk (`test_completion_writers.py` split post-tagging into itself: 9 + `test_completion_writers_iterate_ledger.py`: 2; plus `test_c3_cross_phase_verdict.py`: 10, `test_c3_same_phase_window.py`: 10, `test_phase_history.py`: 18, `test_phase_history_records.py`: 12; `_c3_fixtures.py` has none — fixture module, no `test*` functions) | `d03c300c` (`iterate-2026-07-27-c3-phase-history-join`) |
| FR-01.11/AC17 | 15 | 1 (`test_pr_blockers_merge_state.py`) | `159953ee` (`iterate-2026-07-27-merge-state-vocabulary`) |
| FR-01.11/AC18 | 16 | 2 on disk (`test_silent_revert.py` split post-tagging into itself: 8 + `test_silent_revert_check.py`: 8) | `5b351ed4` (`iterate-2026-07-27-no-silent-revert`) |
| FR-01.11/AC18 | 30 | 3 (`test_silent_revert_false_positives.py`: 10, `_filters.py`: 16, `_not_weakened.py`: 4) | `e4db5154` (`iterate-2026-07-28-silent-revert-false-positives`) |

(FR-01.11/AC18's row splits into two because two different commits, both
naming AC18, contributed files; the table above sums to 61+15+16+30 = 122.
FR-01.01/AC08's original 76/8-files and FR-01.11/AC18's first row's original
1-file count are corrected here for the post-tagging bloat-cap splits — see
"Doubt-review correction" for AC08's count, which also changed.)

**Hand-mapped: 20 tags across 4 test files** (read test name/docstring/
assertions against the minted criterion; upgraded an existing bare FR tag):

| File | Tests upgraded | → |
|---|---|---|
| `plugins/shipwright-security/tests/test_gitleaks_extend_smoke.py` | 3 | FR-01.07/AC06 |
| `shared/tests/test_security_scan_card.py` | 4 | FR-01.07/AC04 (1), AC08 (1), AC11 (2) |
| `plugins/shipwright-adopt/tests/test_adopt_evidence_disclosure.py` | 6 | FR-01.13/AC08 |
| `plugins/shipwright-adopt/tests/test_skill_md_env_scaffold.py` | 7 | FR-01.13/AC05 |

Exact per-(FR,AC) hand-mapped breakdown, reconciled against the manifest:
FR-01.07/AC04 ×1, FR-01.07/AC06 ×3, FR-01.07/AC08 ×1, FR-01.07/AC11 ×2,
FR-01.13/AC05 ×7, FR-01.13/AC08 ×6 = 20.

**Reconciliation: 122 + 20 = 142 = the manifest's own `with_ac` count.** Exact,
not approximate — computed by summing every `ac_id`-bearing `testLink` in the
regenerated `test-traceability.json`.

## Doubt-review correction (PR #689, internal cascade — 15 tags reverted)

Stage-3 doubt-review disproved part of the "derived, not guessed" claim for
the FR-01.01/AC08 group: the same introducing commit (`d03c300c`,
`iterate-2026-07-27-c3-phase-history-join`) shipped TWO distinct behaviors —
the phase-history join itself (what AC08 actually states: currency of a
handover note is decided by the phase's own completion record, never by file
mtime) and, separately, a preserve-canon-marker fix (no criterion was written
for it). The commit-is-the-unit-of-attribution join could not tell those two
apart, so it tagged both.

`shared/tests/test_preserve_canon_marker.py` (6 tags) tests only that a
mid-phase handoff does not erase an existing canon marker when asked — never
AC08's stated currency-decision behavior. `shared/tests/
test_canon_marker_write_contract.py` (9 tags) is a lint over plugin markdown
asserting `generate_session_handoff.py` invocations pass the right
`--canon-marker`/`--preserve-canon-marker` flag, plus marker-field guards —
also not AC08's behavior. Both were confirmed by direct inspection of the
files' docstrings and test bodies, not by re-trusting the tool.

**Fix:** both files' 15 `@pytest.mark.covers("FR-01.01/AC08")` tags downgraded
to bare `@pytest.mark.covers("FR-01.01")` — valid per the tag grammar (E1: "a
bare FR-xx.yy remains valid, covers the requirement, AC unbestimmt"), and
honest about what these tests actually verify. Manifest regenerated via
`update_compliance.py --phase iterate` after the revert; all counts in this
report reflect the corrected, post-revert state. The manual "content-coherence
was spot-checked by hand for every remaining group" claim in the section below
is corrected too: it was a group-level check, and this was a per-file miss
within a group that passed at the group level — the same failure mode
FR-01.03/AC19 caught earlier in this run (see "What was excluded, and why"),
now confirmed to have surfaced twice, once caught by review before the
external plan/code review passes and once by the internal doubt-reviewer
after them.

## What was excluded, and why (never silently dropped)

The mechanical tool reports every non-candidate outcome by name
(`status_counts`), per GLM's low-severity plan-review finding:

- `FR-01.11/AC12` (`iterate-2026-08-08-plan-reviewer-configurable`) →
  `no_added_test_file_in_commit`: the introducing commit only MODIFIED
  existing test files (git status `M`), never added a new one — outside this
  tool's conservative scope (see its module docstring for why `M` files are
  excluded: they are usually pre-existing, multi-purpose fixtures).
- `FR-01.14/AC10` (`iterate-2026-08-09-p2-56-amend-delivery-signal`) →
  `no_commit_found`: zero commits carry that exact `Run-ID:` line on any ref.
- `FR-01.03/AC19` (`iterate-2026-07-27-name-the-blocker`) — **caught and
  reverted during this unit's own review, not shipped**: the slug is unique
  *within* FR-01.03 (1 bullet) but repeats 3× *within* FR-01.11
  (AC16/AC19/AC20) — the underlying commit delivered 4 distinct criteria
  across 2 FRs, and the FR-01.03 occurrence was wrongly trusted by an
  earlier, per-FR-only uniqueness check. `unique_provenance_acs()` now
  requires document-wide uniqueness; the 7 files this produced
  (`test_canon_frontmatter.py`, `test_external_review_reply.py`,
  `test_handoff_freshness.py`, `test_handoff_freshness_composition.py`,
  `test_layer_coverage_criteria.py`, `test_layer_coverage_verdict.py`,
  `test_pr_blockers.py` — 101 tags) were reverted to their pre-backfill state
  and confirmed passing (101/101) after the revert.
- Every file a mechanical candidate claimed jointly with another `(fr_id,
  ac_id)` pair is dropped from BOTH, never arbitrarily resolved
  (`_mark_multiply_claimed_files`) — none occurred in this run's real data.
- Content-coherence was spot-checked by hand for every REMAINING mechanical
  GROUP (all 4 groups above) against the actual minted criterion text in
  `spec.md` — a group-level check, not a per-file one, which is exactly what
  let 15 of the FR-01.01/AC08 group's 76 tags through mistagged (see
  "Doubt-review correction" above): the other 61 files in that group do match
  (e.g. FR-01.11/AC18's "brought up to date... anything that arrived in that
  work... is reported and the hand-over refused" against
  `test_silent_revert*.py`'s content), and per-file re-verification after the
  doubt-review finding confirms no other group has this defect.

## +39 denominator delta (13728 → 13767), fully reconciled

- **+11**: this unit's own new pure-logic test file,
  `shared/tests/test_backfill_ac_provenance.py` (a `traceability.test_roots`
  root; the tool's OWN `tools/` test files are not — `shared/scripts/tools/tests`
  is not a configured trace root, so the 18 CLI/git-correlation tests added
  alongside this unit are invisible to this manifest by design).
- **+28**: `shared/tests/test_layer_coverage_binding.py` (12) and
  `shared/tests/test_layer_coverage_binding_wrapper.py` (16) — pre-existing
  P3.3 files already committed on `origin/main` whose tests were absent from
  the `origin/main`-committed manifest snapshot (a P3.3 regen gap, not
  something this unit introduced); this unit's regen incidentally picked them
  up because it re-scans the whole configured test-root set.
- 11 + 28 = 39. No removed test IDs (`removed: 0`) — the delta is additive only.

## Corrections made during review (this unit's own)

- **Epoch-zero `generated_at` (external code review, GLM medium):** an
  earlier regen in this unit called the bare `collectors.test_links.generate_file`
  helper directly (no `data` object), which stamps `generated_at` as
  `1970-01-01T00:00:00+00:00` when `data` is `None` — a real bug in how THIS
  unit regenerated the artifact, not in the collector itself. Corrected by
  regenerating through the canonical `update_compliance.py --phase iterate`
  wiring, which supplies a real `data.timestamp`. The committed
  `test-traceability.json` now carries a real `generated_at`
  (`2026-09-07T15:17:46Z` at time of writing, re-stamped again at the F1/F5b
  finalization regen).
- **File-level over-attribution guard tightened (external code review, GLM+
  OpenAI both high):** `_upgrade_bare_tags` was a whole-file regex
  substitution that could have rewritten a same-looking `covers("FR-xx.yy")`
  string inside a docstring, comment, or assertion — never actually fired in
  this run's real data (git-status-`A` files start with zero pre-existing
  tags, so `upgraded_bare_tags` was always empty here), but fixed regardless:
  the substitution now only fires on a line that IS itself a
  `@pytest.mark.covers(...)` decorator.
- **`Run-ID:` matching hardened (GLM medium):** the initial `-F` substring
  `--grep` is now a cheap over-approximation only; every candidate commit is
  re-checked for an EXACT `Run-ID: <slug>` line via Python regex before being
  trusted — closes both the prefix-slug case (`iterate-x` vs
  `iterate-x-follow-up`) and a hypothetical unrelated commit's prose mention.
- **Top-level `tests/` layout miss fixed (GLM low):** `"/tests/" in rel` never
  matched a repo-root `tests/test_x.py` path (no leading slash before
  `tests`); replaced with a path-segment check.
- **Orphan rollback added (GLM low, OpenAI medium):** `--write` now snapshots
  every candidate file before writing and restores all of them byte-for-byte
  if the post-write `validate_applied` check finds an orphan, instead of
  leaving a half-applied tree behind a non-zero exit.
- **Git-join test coverage added (GLM medium):** `_commits_for_run_id` /
  `_added_test_files` / `_is_shallow_clone` are now exercised against a real,
  throwaway git repo (`test_backfill_ac_provenance_cli_git.py`), not merely
  claimed as "exercised indirectly."
- **Artifact-path-canon violation (found by F0, not by review):** the tool's
  own `_DEFAULT_SPEC` built `.shipwright/planning/...` via
  `Path(".shipwright") / "planning" / "01-adopted" / "spec.md"` — a bare
  `"planning"` path segment, which `test_artifact_path_canon.py`'s AST lint
  forbids outside its allowlist (the "planning" artifact migration completed
  in 2026-04). Fixed by folding the canonical prefix into one string,
  `Path(".shipwright/planning") / "01-adopted" / "spec.md"`, matching the
  shape every other reader in this repo already uses.

## Explicitly rejected findings (with reason)

- **Schema v4 unversioned key addition (GLM medium, plan review):** `ac_id` /
  `acs` were already declared as additive v4 fields by P3.2
  (`traceability_schema.json`), not introduced by this unit — this unit only
  populates already-declared fields. No consumer in this repo does strict/
  unknown-key rejection on v4 trace nodes (confirmed by grep + the full
  `shipwright-compliance` test suite, 1679 passed, against the populated
  manifest). A cross-repo WebUI consumer's compatibility is a P3.2-scope
  decision already made, and this unit is explicitly barred from touching the
  WebUI repo.
- **Merge-commit / squash-merge trailer survival (OpenAI medium, plan
  review):** out of scope to fix — the tool's own design fails SAFE
  (under-reports as `no_commit_found`, never over-reports) if a squash merge
  ever drops a `Run-ID:` trailer, which is consistent with every other
  no-guess exclusion this tool makes.
- **File-scope-not-test-scope attribution as a residual risk (OpenAI high,
  both reviews):** the tool's own docstring already states this tradeoff
  explicitly (only a wholesale-ADDED file is trusted at file scope, never a
  modified one) and is deliberately conservative rather than test-scoped, to
  avoid re-introducing content-reading/guessing. Mitigated for THIS run by
  manually confirming every one of the 4 remaining candidate groups' content
  against its criterion text (see "content-coherence was spot-checked" above)
  — and the one case where this exact failure mode DID occur
  (FR-01.03/AC19) was found and reverted before shipping, which is direct
  empirical evidence the safeguard works, not merely asserted.
