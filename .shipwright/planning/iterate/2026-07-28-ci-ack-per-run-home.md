# Iterate: the CI supply-chain ack gets a home that is not a derived snapshot

- **Run ID:** `iterate-2026-07-28-ci-ack-per-run-home`
- **Type:** CHANGE
- **Complexity:** medium
- **Spec Impact:** NONE (behavior of the gate is preserved; only where the
  record lives changes)
- **Date:** 2026-07-28

## Problem

Two F11 checks, both `ERROR` severity, cannot be satisfied at the same time by
an iterate that touches `.github/workflows/**`.

- `check_ci_supplychain_ack` reads the acknowledgement from the **committed**
  `shipwright_test_results.json`. Its disk fallback only fires when
  `git show <commit>:shipwright_test_results.json` *fails* — i.e. when the file
  is untracked at that commit. The file is tracked on `main`, so the committed
  copy always wins, and that copy carries no ack for the current run.
- `check_no_derived_snapshots_committed` lists that same file in
  `DERIVED_SNAPSHOTS` and errors when the commit touches it.

Commit the file and the second check fails; leave it out and the first fails.

Observed on `iterate-2026-07-28-main-self-heal` (PR 497) and resolved there by
committing the file — the acknowledgement is the safety-relevant record, the
merge collision is a cost. That is the right call under duress and the wrong
one to institutionalise.

### Empirically confirmed, not inferred

A probe built a real repo with `shipwright_test_results.json` tracked on `main`
(as on shipwright `main`), committed a workflow-touching iterate both ways, and
ran both checks on each commit:

| Scenario | `ci_supplychain_ack` | `no_derived_snapshots_committed` |
|---|---|---|
| A — commit the results file | **ok** | **FAIL** (1 derived snapshot committed) |
| B — do not commit it | **FAIL** (no ack recorded) | ok |

In scenario B the ack *is present on disk*. The fallback does not fire because
`git show` succeeds and returns `main`'s ack-less copy. This is the reported
mechanism exactly.

### A third failure the report did not name

`restore_derived_to_head` restores every dirty `DERIVED_SNAPSHOTS` path to
`HEAD` during finalization. `shipwright_test_results.json` is one of them, so it
**actively reverts** an ack that was correctly recorded pre-F6. The ack is not
merely unshippable — it is erased by ordinary run hygiene.

### Why this is urgent relative to the parked refresh

`iterate/derived-snapshots-refresh` moves the derived snapshots off branches
entirely and regenerates them post-merge. That branch itself adds
`.github/workflows/refresh-derived-snapshots.yml`, so it is a
`touches_ci_supplychain` iterate — blocked by the very deadlock it would
deepen. After it lands the ack becomes **unreachable** rather than merely
conflicted: there is no committed copy of the file on a branch at all.

## Decision

Give the acknowledgement its own **per-run home**:

```
.shipwright/planning/iterate/<run_id>/ci_supplychain_ack.json
```

This is the directory `reviews.json` already occupies. It is tracked, not
gitignored, not derived, and per-run — so it cannot collide between parallel
iterates, and `restore_derived_to_head` never touches it.

The alternative offered in the report — falling back to the working tree when
the committed copy names a different run — was **rejected**. It contradicts the
gate's own thesis, stated in its docstring: an ack "that lives only in the
working copy would never ship in the PR". It would also still be erased by
`restore_derived_to_head`, and it does not survive the parked refresh, which
removes the committed copy altogether. It buys a green gate, not a durable
record.

**The gate's enforcement is unchanged, with one honest exception.** Run binding,
content fingerprint, decision-reference and statement validation all still apply,
the flag is still recomputed from the diff, and the new unsafe-run-id branch
strictly strengthens it.

The exception is **durability**, raised by the Stage-1 spec review. Under the old
layout the results file was always tracked, so the ack had to be in the commit to
be read at all. AC-2's worktree fallback means an ack that exists only on the
author's disk now satisfies the gate. In the normal flow F6's directory-level add
stages it, so this is reachable only by an author who bypasses F6 — but it is a
real difference and is **not** claimed away: the check now names its source and
appends "read from the working tree, not the commit; stage it or it will not ship
in the PR" when the ack did not come from the commit. Making it a hard failure
(mirroring `check_review_record` for its neighbour `reviews.json`) is the
stronger design and is filed as a follow-up rather than taken here, because it
changes AC-2 and belongs in a run scoped to it.

## Acceptance Criteria

- **AC-1** — `record_ci_supplychain_ack.py` writes the ack to
  `.shipwright/planning/iterate/<run_id>/ci_supplychain_ack.json`.
- **AC-2** — `check_ci_supplychain_ack` reads the **committed** per-run file
  first, falling back to the working-tree copy when it is untracked at that
  commit (a brand-new file in an amend-less flow).
- **AC-3** — Legacy compatibility: an ack recorded in
  `iterate_latest.ci_supplychain_ack` is still honoured, so the 39 in-flight
  iterate branches do not break. It is read only when no per-run ack exists, and
  is subject to identical run/fingerprint/field validation — the fallback adds no
  dodge.
- **AC-4** — A workflow-touching iterate that records an ack and commits the
  per-run file satisfies **both** checks simultaneously (the deadlock is gone).
- **AC-5** — `restore_derived_to_head` does not erase the ack.
- **AC-6** — `DERIVED_SNAPSHOTS` still contains `shipwright_test_results.json`;
  this change does not weaken the derived-snapshot gate.
- **AC-8** *(added mid-run, Stage-3 doubt review)* — The content fingerprint binds
  content for **every** CI path the flag fires on, including non-ASCII filenames.
  Scope note: this is a **pre-existing false-green**, not a defect this change
  introduced. It is fixed here rather than filed because it is the same hazard
  family the run is about, because the run's own new documentation would otherwise
  claim the distinction was closed when it was not, and because a security gate
  that silently accepts arbitrary content is not a thing to leave open once
  measured. The fix is three `core.quotePath=false` flags at the path producers.
- **AC-7** — Docs updated in the same diff: `docs/hooks-and-pipeline.md`,
  `.shipwright/agent_docs/conventions.md`, the iterate `SKILL.md` risk-taxonomy
  row, and the F5/F6 references that name the ack's location and staging.
  `F5.md` named no location to correct, but it is where the writer's sequencing
  belongs (record after the final results write, before F6 stages it), so it now
  carries the invocation rather than being skipped as vacuous — external code
  review, which read the AC more literally than the Stage-1 pass did.
  **`conventions.md` is constrained:** it is a dated append-log with a 600-char
  per-entry budget gate, and the 2026-07-18 entry was already at 587. A verbose
  supersede marker failed that gate at 705, so the entry instead *replaces* the
  now-wrong path text with "a per-run ack file — moved 2026-07-28" (566). It no
  longer misdirects, which was the Stage-1 objection, but it does not restate the
  new location either; the live normative surfaces (`SKILL.md`,
  `hooks-and-pipeline.md`, `F5.md`, `F6.md`) and the F3a entry carry that.

## Affected Boundaries

- **Artifact seam (write→commit→read):** the ack is written by a CLI, committed
  by F6, then read back through `git show`. Producer and consumer must agree on
  the path and the JSON shape → `touches_io_boundary`, round-trip test required.
- **F11 verifier surface:** `check_ci_supplychain_ack` is load-bearing and must
  keep failing closed.
- **F6 add-list:** the new per-run file must be staged, or the ack does not ship.

## Confidence Calibration

- **Boundaries touched:** artifact write/read seam
  (`ci_supplychain_ack.json`), F11 verifier surface, F6 staging list.
- **Empirical probes run:**
  1. *Deadlock reproduction* (pre-change) — real git repo, results file tracked
     on `main`, both commit strategies. Result: A `ack=ok, derived=FAIL`;
     B `ack=FAIL, derived=ok`. **Deadlock confirmed**, and scenario B confirmed
     the precise mechanism: the ack was present on disk but `git show` *succeeded*
     and returned `main`'s ack-less copy, so the disk fallback never fired.
  2. *F6 staging, verified not assumed* — external review called the staging
     change a hard dependency. Reading the add-list shows F6 already stages
     `.shipwright/planning/iterate/<run_id>/` at **directory** level (that is how
     `reviews.json` ships today), so the new file is carried with no F6 code
     change. Pinned by a drift test rather than claimed.
  3. *`git show <sha>:<path>` is a Windows trap* — found by the round-trip test
     failing with `Filename too long`. git stats the whole argument as a possible
     filename first, probing `<cwd>/<sha>:<path>`; on a deep checkout that crosses
     the 260-char `MAX_PATH` and git reports a read error indistinguishable from a
     genuine one. **This was not in the plan** and would have made the gate pass on
     a shallow checkout and fail on a deep one. Now read by blob OID
     (`ls-tree` → `cat-file blob <oid>`), which carries no path at all.
  4. *`restore_derived_to_head` erasure* — asserted against a real restore
     (the probe fails if the restore was a no-op), confirming the new home
     survives the hygiene step that erased the old one.
- **Test Completeness Ledger:** see below.
- **Confidence-pattern check:**
  - *Asymptote (depth)* — the round-trip test drives the **real** CLI into a
    **real** commit and reads it back through the **real** verifier. That depth is
    what surfaced probe 3; a mocked seam would have reported success.
  - *Coverage (breadth)* — new location, legacy location, precedence between
    them, absent ack, stale run, mismatched fingerprint, corrupt file, unsafe run
    id (both when it matters and when it must stay silent), idempotent re-record.
  - *Integration composition* — the deadlock is a composition failure between two
    checks that each passed in isolation, so the decisive tests run **both** over
    one real commit. `test_the_old_home_still_deadlocks` additionally pins the
    premise, so the fix cannot quietly become unnecessary without notice.

## Test Completeness Ledger

| # | Behavior | Status | Evidence |
|---|---|---|---|
| 1 | The ack's path is the per-run planning dir and is not derived | `tested` | `test_ack_relpath_is_the_per_run_planning_dir` |
| 2 | Verifier accepts a committed per-run ack | `tested` | `test_passes_with_a_committed_per_run_ack` |
| 3 | Genuine absence at the commit falls back to the worktree copy | `tested` | `test_per_run_ack_untracked_at_the_commit_falls_back_to_the_worktree` |
| 4 | Per-run ack wins over a legacy ack | `tested` | `test_per_run_ack_takes_precedence_over_a_legacy_ack` |
| 5 | A present-but-invalid per-run ack does NOT fall back to a valid legacy one | `tested` | `test_invalid_per_run_ack_does_not_fall_back_to_a_valid_legacy_ack` |
| 6 | Mismatched fingerprint rejected in the new home | `tested` | `test_per_run_ack_with_a_wrong_fingerprint_is_rejected` |
| 7 | Corrupt per-run ack fails closed | `tested` | `test_corrupt_per_run_ack_fails_closed` |
| 8 | Legacy `iterate_latest` ack still honoured | `tested` | `test_legacy_iterate_latest_ack_is_still_accepted` |
| 9 | Legacy leg keeps run + fingerprint binding | `tested` | `test_legacy_ack_is_still_run_and_fingerprint_bound` |
| 10 | No ack anywhere still fails | `tested` | `test_no_ack_anywhere_still_fails` |
| 11 | Unsafe run id fails closed | `tested` | `test_unsafe_run_id_fails_closed` |
| 12 | Unsafe run id stays silent on a non-CI diff | `tested` | `test_unsafe_run_id_does_not_fire_when_no_ci_file_is_touched` |
| 13 | **Both F11 gates green on one workflow-touching commit** | `tested` | `test_both_gates_are_simultaneously_satisfiable` (integration) |
| 14 | The old home genuinely deadlocked (premise pin) | `tested` | `test_the_old_home_still_deadlocks` (integration) |
| 15 | `restore_derived_to_head` leaves the per-run ack intact | `tested` | `test_restore_derived_to_head_does_not_erase_the_per_run_ack` |
| 16 | `DERIVED_SNAPSHOTS` still lists the results file | `tested` | `test_results_file_is_still_a_derived_snapshot` |
| 17 | Round-trip: CLI → commit → verifier, both gates green | `tested` | `test_round_trip_cli_write_commit_verifier_read` |
| 18 | CLI leaves the derived snapshot byte-identical | `tested` | `test_cli_does_not_write_the_ack_into_the_derived_snapshot`, `test_leaves_the_derived_results_file_untouched` |
| 19 | CLI refuses an unsafe run id | `tested` | `test_cli_rejects_an_unsafe_run_id` |
| 20 | Re-recording after a CI edit overwrites cleanly | `tested` | `test_cli_is_idempotent` |
| 21 | F6 keeps the directory-level add that carries the ack | `tested` | `test_f6_reference_stages_the_per_run_directory` (mutation-checked: narrowing the add to `reviews.json`, and dropping the ack from the add line, both FAIL) |
| 22 | A commit-sourced ack reports no caveat | `tested` | `test_passes_with_a_committed_per_run_ack` |
| 23 | A worktree-sourced ack passes but is reported as not shipping | `tested` | `test_per_run_ack_untracked_at_the_commit_falls_back_to_the_worktree` |
| 24 | A legacy-sourced ack names the legacy leg | `tested` | `test_legacy_iterate_latest_ack_is_still_accepted` |
| 25 | A legacy ack read from DISK is also reported as not shipping | `tested` | `test_legacy_ack_read_from_disk_is_reported_as_not_shipping` |
| 26 | An absent path reads as absent, not an error | `tested` | `test_absent_path_is_absent_not_an_error` |
| 27 | An unreadable commit is an error, not an absence | `tested` | `test_unreadable_commit_is_an_error_not_an_absence` |
| 28 | A non-blob (tree/symlink mode) is refused as not a regular file | `tested` | `test_a_tree_is_not_a_regular_file` |
| 29 | The committed reader RAISES instead of reporting absent | `tested` | `test_reader_raises_rather_than_reporting_absent` |
| 30 | **The gate fails closed when CI content cannot be read** | `tested` | `test_gate_fails_closed_when_ci_content_cannot_be_read` |
| 31 | CRLF and LF content hash alike | `tested` | `test_crlf_and_lf_hash_alike` |
| 32 | bytes and str readers agree for valid UTF-8 (in-flight acks stay valid) | `tested` | `test_bytes_and_str_readers_agree_for_valid_utf8` |
| 33 | Non-UTF-8 content is stable across the write/verify seam | `tested` | `test_non_utf8_content_is_stable_across_the_real_seam` (rewritten — the first version compared the function to itself and touched neither reader) |
| 34 | An absent path hashes differently from an empty one | `tested` | `test_absent_is_distinct_from_empty` |
| 35 | `load_ack` enforces the run-id guard itself | `tested` | `test_load_ack_guards_the_run_id_itself` |
| 36 | An unrecognised `schema_version` is refused | `tested` | `test_unrecognised_schema_version_is_refused` |
| 37 | **A non-ASCII workflow name still binds CONTENT** | `tested` | `test_non_ascii_workflow_name_still_binds_content` (mutation-checked: removing the `core.quotePath=false` fix makes benign and malicious digests identical, and the test FAILS) |
| 38 | A pathspec metacharacter does not glob onto another entry | `tested` | `test_pathspec_metacharacters_do_not_glob_onto_another_entry` |
| 39 | An ack path that exists but is not a regular file is an error | `tested` | `test_worktree_ack_path_that_is_a_directory_is_an_error` |

0 untested-testable behaviors. 39 behaviors, 39 tested.

Rows 37–39 come from the Stage-3 doubt review, which was briefed that this run had
already fixed the same hazard in one place and missed a copy **twice**, and told to
assume a third. There was one, and it was the most serious defect found in the run.

`_normalize` handled `core.quotePath` for the risk-flag REGEX but not for the
subsequent content READ. git quotes a non-ASCII path and escapes its bytes octally,
and `_normalize` then ran `replace("\\", "/")` over it — turning `\303` into `/303`
and manufacturing fake path separators. The resulting name addressed no file, so
**both** readers reported "absent" and hashed the `<absent>` sentinel. The
fingerprint over that path was therefore content-INDEPENDENT: acknowledge a benign
`résumé-check.yml`, then commit `pull_request_target:` plus a secret echo under the
same name, and the digest is unchanged and the gate green. That is verbatim the
false-green the module's own docstring says the content binding exists to prevent.
**Measured, not theorised** — a probe produced two identical digests for benign and
malicious content, and `core.quotePath=false` on the path producers fixed it.

Row 38 is a regression this iterate itself introduced: `git show <rev>:<path>`
resolves a LITERAL path, while `ls-tree -- <path>` takes a PATHSPEC with wildmatch,
so the OID rewrite let `ci[1].yml` glob onto `ci1.yml`. Fixed with
`--literal-pathspecs` plus an equality check on the returned entry, which the first
version never made.

Rows 26–36 come from the Stage-2 code review, which found the sharpest defect of
the run: the `git show <commit>:<path>` spelling this iterate condemned and
replaced was still live in `commit_reader` — *"the iterate discovered this bug and
fixed one of its two occurrences"* — and that occurrence fed the security-load-bearing
fingerprint, where every git failure was mapped to `None` and hashed as the
`<absent>` sentinel a genuinely DELETED path gets. Not merely a spurious red: an
ack recorded against a deleted workflow could license arbitrary committed content
for that path on any checkout where the read failed. Row 30 is the regression test
for that fail-open; rows 26–29 pin the absent-vs-broken distinction it rests on.

Rows 31–33 are the second Stage-2 finding: the two sides of the write→verify seam
decoded text differently (`errors="replace"` vs `errors="ignore"`), so one latin-1
byte in a workflow comment produced two digests and red-lined the author
permanently with a message naming the wrong cause. Hashing bytes fixed it and
immediately exposed a defect of its own — a CRLF worktree file no longer matched
its LF blob, which the discarded text mode had been hiding. Row 31 pins the
explicit normalization; row 32 pins that already-recorded acks stay valid.

**Qualifying row 32, measured rather than assumed.** A probe compared the old
text-mode digest against the new one across four content shapes. Identical for
plain LF, for a CRLF worktree against its LF blob, and for multibyte UTF-8 — so
the 39 in-flight branches keep their acks. It **differs for a file containing a
lone `\r`** (classic-Mac line endings): Python's universal-newline translation
folded a lone `\r` into `\n`, and the new normalization deliberately does not.
That is the correct trade, not an oversight — git does not round-trip a lone `\r`,
so folding it buys no false-red protection and only makes two genuinely different
files hash alike, which is precisely what a security fingerprint must not do. The
cost is bounded and safe: an ack recorded on such a file must be re-recorded, and
the failure mode is a re-record prompt, never a false green. Both sides of the new
code treat a lone `\r` identically, so no author is red-lined for a file they did
not edit.

Rows 22–25 cover the `source` reporting added while answering reviews. They were
written because those responses introduced behaviour, and behaviour added while
answering a review is still behaviour the ledger owes a test — the rule the
Stage-1 review established, applied again when the external code review found
row 25's case: a legacy ack read from disk was labelled merely `legacy` and
skipped the non-shipping warning, reproducing on the old leg the exact hole this
change closes on the new one.

**Not `cross_component`.** The diff touches an F11 verifier and its writer CLI —
not the merge/churn/event-log resolver, hooks, phase validators or campaign
drain that `CROSS_COMPONENT_FILE_PATTERNS` names. Integration coverage is
supplied anyway (rows 13, 14, 17) because the defect *was* a composition
failure, so the strongest evidence is compositional regardless of the flag.
