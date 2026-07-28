# Iterate: the release aggregator writes a version once, or says why not

- **Run ID:** `iterate-2026-07-27-changelog-aggregator-idempotency`
- **Intent:** CHANGE (correctness defect in the release-path writer + SSoT extraction)
- **Complexity:** medium (classifier: `estimate=medium`, `prior_source=history`,
  `history_n=20`, `risk_flags=[]`; the keyword estimate `trivial` is not upheld —
  the change crosses the ADR-045 plugin/shared boundary, retires a duplicated
  implementation, and widens an acceptance criterion)
- **Spec Impact:** MODIFY — `affected_frs = [FR-01.09]` (`/shipwright-changelog`).
  The re-run criterion added by PR #452 is widened in place to cover the
  release-time assembly path and both refusal causes. FOLD, not MINT — no new
  FR id (`shared/fr-authoring.md`).
- **Source:** scoped out of `iterate-2026-07-27-changelog-writer-preserve-history`
  (PR #452, merged `97392eea`) — see its "Out of scope" section, lines 292-305.

## Problem

`/shipwright-changelog` SKILL.md **Step 4** makes
`shared/scripts/tools/aggregate_changelog.py` the writer the release path
actually invokes. PR #452 fixed the *other* writer
(`plugins/shipwright-changelog/scripts/lib/changelog.py`) and deliberately left
this one alone, because importing the fix across the plugin→shared boundary is
the wrong direction across the ADR-045 `lib`-collision hazard.

`_insert_section` always inserts above the first versioned heading and never
looks for a section that version already has. Its only idempotency comes from
consuming the drop files, and `_atomic_write` runs **before** the unlink loop.

Reproduced empirically against the real `aggregate()`:

| # | Scenario | Result |
|---|---|---|
| P1 | release interrupted between write and unlink; operator re-runs | `'## [0.3.0]'` occurrences = **2** — a second, identical section |
| P3 | file already holds two sections for the target version | aggregator writes a **third**; no refusal arm exists |

**Root cause:** the aggregator has no notion of "this version is already
written". It is an inserter, in a workflow whose failure mode is re-running.

### The hazard a naive fix introduces (P2)

Replacing the same-version section unconditionally would be **worse than the
duplicate**, and this is the design crux of the iterate.

The unlink loop is not atomic. Probe P2: 3 drops, write succeeds, unlink
deletes 2 and then the process dies. The recorded section holds 3 bullets; the
surviving drop set renders **1**. An unconditional replace overwrites 3 bullets
with 1 — silent loss of released history. The old duplicate-section bug, by
contrast, loses nothing; it only produces an ugly file.

So "replace" is only safe when the replacement cannot lose anything. The rule
this iterate implements:

| State on disk | Action |
|---|---|
| **no drops pending** (the release completed and was re-run) | **no-op** — today's early return; the changelog is never even read |
| no section for this version | **insert** (today's behaviour, unchanged) |
| exactly one section, and its body matches what the drops now render | **replace** in place, then consume the drops — the interrupted release converges |
| exactly one section, and its body does **not** match | **refuse** — name the file, version and cause; leave `CHANGELOG.md` and every drop untouched |
| more than one section for this version | **refuse** — which is authoritative is not knowable |

The second refusal arm is exactly the partial-unlink state: the operator is told
that the recorded section disagrees with the pending entries, instead of having
the disagreement resolved by deletion.

**What "matches" compares, precisely.** The equality test is on the section
**body** — everything the section owns below its `## [version]` heading —
normalised for line endings and trailing whitespace. The heading itself is
excluded, because it carries the release **date**, and `release_date` defaults
to *today*. An interrupted release resumed the next morning renders
`## [0.3.0] - 2026-04-24` against a recorded `## [0.3.0] - 2026-04-23`: comparing
the heading would refuse the single scenario this iterate exists to fix. The
safety property is *no bullet is lost*, and the date is not a bullet. A replace
therefore adopts the newly rendered heading — the file ends up as though this
run had been the first — and an operator who wants the original date pins it
with `--release-date`, which SKILL.md Step 4 already documents.

### Two implementations of one predicate

PR #452 put the section predicates in
`plugins/shipwright-changelog/scripts/lib/changelog_sections.py`. The aggregator
carries its own `_find_structural_insertion_line`. They already disagree:

- `## [unreleased]` (lowercase) — the shared predicate treats it as the
  Unreleased block; the aggregator treats it as a released version and inserts
  above it.
- `[Unreleased]` followed by a link-reference footer — the shared predicate
  stops at the footer and inserts above it; the aggregator walks past it and
  inserts below.

Neither loses content, so nothing has failed yet. Adding the replace logic as a
**third** copy is what `conventions.md:50` records as the failure mode ("when N
readers share one arithmetic, extract it to ONE SSoT or a predicate WILL
drift").

## Mini-Plan

1. **Promote** `changelog_sections.py` to `shared/scripts/changelog_sections.py`
   — top level, **not** under `lib/`, per ADR-045, so both sides import it bare
   without binding `sys.modules['lib']`. This is the pattern `conventions.md:50`
   records for `tests_block.py` and `markdown_table.py`.
2. **Delete** the plugin-local copy. `changelog.py` reaches the shared module by
   putting `parents[4] / "shared" / "scripts"` on `sys.path` — verified to
   resolve in **both** layouts: the repo (`plugins/<name>/scripts/lib/` →
   repo root) and the runtime plugin cache
   (`cache/shipwright/<name>/<version>/scripts/lib/` → `cache/shipwright`),
   which is why `shipwright-compliance/scripts/lib/test_evidence.py:21` already
   works. `shared/` is delivered to the cache by the `ensure_shared_cache`
   SessionStart hook.
3. **Retire** `_find_structural_insertion_line` from the aggregator. The
   aggregator takes **all four** structural answers from the shared module —
   `insertion_index` for where a new section goes, `section_starts` for how many
   sections claim this version, `section_end` for the span one owns, and the
   `continues_section` predicate underneath both. Taking only the insertion
   point and hand-rolling a target-section scanner would remove one duplicate
   and create another.
4. **Add** the decide-and-splice arm to the aggregator, per the table above.
   The refusal is raised inside the lock, **before** the write and before the
   unlink, so a refusal leaves the release exactly as it found it — including
   under `--dry-run`, where a refusal is still a refusal and not a successful
   preview. (`file_lock` is a `@contextmanager` with `try/finally`, so an
   exception releases the lock — verified, not assumed.)
5. **Widen** FR-01.09's re-run criterion; add tests in **new** modules
   (`test_changelog_aggregation.py` carries a bloat-baseline entry at its exact
   current length, so growing it in place would ratchet the gate).

### Alternative considered — and rejected

**Copy the predicates into the aggregator (a third implementation).** No
cross-boundary import, no plugin-cache dependency, smallest diff. Rejected: it
makes permanent the divergence documented above, and the two copies are already
provably inconsistent on two shapes. The extraction is the reason this was
carved out as its own iterate rather than folded into PR #452.

**Merge the sections instead of refusing** (union the recorded bullets with the
newly rendered ones). It would make the partial-unlink case recover
automatically. Rejected as YAGNI *and* as dishonest: bullet-level union needs
to parse a section a human may have edited, and it would silently invent a
history nobody wrote. Stopping and naming the disagreement is what the
existing criterion asks for.

## Acceptance Criteria

- **AC1** `shared/scripts/changelog_sections.py` is the ONE implementation of
  the section predicates. The plugin-local copy is deleted and
  `plugins/shipwright-changelog/scripts/lib/changelog.py` reaches the shared
  module; the plugin writer's **behaviour** is unchanged — every existing
  assertion in its suite still passes, unedited. (Its `test_integration.py`
  gains a `PYTHONIOENCODING` fix to a **pre-existing** Windows harness defect,
  recorded under "Out of scope". No assertion changed.)
- **AC2** The aggregator takes its insertion point from that same module;
  `_find_structural_insertion_line` no longer exists.
- **AC3** Aggregating a version whose section is already recorded **and whose
  body matches what the current drops render** replaces it in place: the version
  appears exactly once. With the release date pinned, the file after run 2 is
  byte-identical to the file after run 1; resumed on a **later date** it still
  holds exactly one section, now carrying the new date.
- **AC4** That converging re-run still consumes the drop files, so a release
  interrupted between write and unlink reaches a clean state on re-run.
- **AC5** Aggregating a version whose recorded section does **not** match what
  the current drops render raises `AggregatorError` naming the file, the version
  and the cause; `CHANGELOG.md` is byte-unchanged and **every drop file is still
  on disk**.
- **AC6** A file already holding more than one section for the target version
  refuses the same way, with the count in the message, leaving file and drops
  untouched.
- **AC7** Both refusals surface through the CLI as a non-zero exit with the
  reason on stderr.
- **AC8** `--dry-run` reports the action it would take without writing
  `CHANGELOG.md` and without unlinking any drop — and a state that would be
  refused is refused under `--dry-run` too (same error, same non-zero exit),
  never reported as a successful preview.
- **AC9** Insertion still lands below `[Unreleased]` and above the most recent
  released section, and never above the `# Changelog` title, after the swap to
  the shared predicate.
- **AC10** A replaced span is bounded by what the section owns, so trailing
  prose and the Keep-a-Changelog link-reference footer survive a replace.
- **AC11** The result dict names what happened (`section_action` ∈
  `inserted | replaced | unchanged | none`), and `changelog_updated` means
  "bytes were written", not "the run succeeded": a converging re-run that finds
  the file already saying exactly this reports `unchanged` with
  `changelog_updated=False`, skips the write, and **still consumes the drops**.
- **AC12** Re-running a **completed** release — the section is recorded and no
  drops remain — is a clean no-op: no write, no error, `section_action="none"`.
  (Today's early return already does this; nothing pins it, and the refusal arm
  must never reach this state.)
- **AC13** `plugins/shipwright-changelog/scripts/lib/changelog.py` resolves
  `changelog_sections` from `shared/scripts/`, asserted on the imported module's
  `__file__` — so a stale plugin-local copy shadowing the shared one is caught
  as a test failure rather than as divergent behaviour in the field.
- **AC14** `spec.md` FR-01.09's re-run criterion is widened to cover the
  release-time assembly path and both refusal causes.

## Affected Boundaries

- `CHANGELOG.md` — a user-authored file rewritten in place. The boundary that
  matters; every AC above is asserted on the bytes on disk.
- `CHANGELOG-unreleased.d/**` — the drop set. Refusals must not consume it.
- The **cross-plugin import boundary** (ADR-045): a shared top-level module
  imported bare from a plugin whose own `scripts/lib` is a regular package.
- No `*_config.json`, `.env*`, `hooks.json`, `*_state.json` or wire format is
  touched — checked against `IO_BOUNDARY_FILE_PATTERNS`; no
  `cross_component` or `ci_supplychain` path matches either.

## Review cascade

### External plan review (`external_review.py --mode iterate`, openrouter)

`gemini=approve`, `openai=revise`, no contradiction (verdicts within one step).
Every finding dispositioned; the plan above already carries the accepted ones.

| # | Finding | Sev | Disposition |
|---|---|---|---|
| GPT-1 | The action table omits "section recorded, drop set **empty**" — a completed release re-run. If that renders an empty section and compares, it refuses, making a successful release non-idempotent. | high | **Accepted.** Read the code: `aggregate()` returns early on an empty section, so the state is already correct — but nothing pinned it and the plan did not name it. Now the first row of the action table, **AC12**, with a test. |
| GPT-2 | The comparison is non-deterministic: `release_date` defaults to *today*, so a run resumed the next day refuses. | med | **Accepted — the most valuable finding.** It would have false-refused the exact scenario being fixed. Comparison is now on the section **body**; heading/date excluded; a replace adopts the new heading. Both dates are tested. |
| GPT-3 | Reusing only `insertion_index` leaves the target-section scanner to be hand-rolled, recreating the drift the extraction removes. | med | **Accepted.** Mini-Plan step 3 now takes `section_starts` / `section_end` / `continues_section` from the shared module too. |
| GPT-4 | `replaced` vs `unchanged` undefined; an unconditional atomic write of identical bytes still churns the file. | med | **Accepted.** AC11 now defines all four actions and requires the write to be skipped when bytes are identical — while still consuming the drops. |
| GPT-5 | The move changes a **deployment** boundary; the promoted module must actually reach the runtime plugin cache, and every importer of the deleted file must be found. | med | **Accepted.** Verified empirically that top-level `shared/scripts/*.py` reach the cache (`tests_block.py`, `markdown_table.py` are both there) and that `parents[4]` resolves in both layouts. Importers grepped: `changelog.py` only. Import-origin assertion is **AC13**. |
| GPT-6 | Dry-run refusal contract ambiguous — could report a refusal as a successful preview. | med | **Accepted.** AC8 now states a refused state is refused under `--dry-run` too. |
| GPT-7 | Bare import after `sys.path` mutation could resolve a shadowing `changelog_sections`. | low | **Accepted as covered.** Deleting the plugin-local copy removes the only competing module; AC13's `__file__` assertion is the standing guard. |
| GEM-1 | Whitespace differences could trigger a false refusal. | med | **Accepted** — same fix as GPT-2; the comparison normalises line endings and trailing whitespace. |
| GEM-2 | Raising inside the lock could leave a dangling lock file. | low | **Dismissed with evidence.** `shared/scripts/lib/file_lock.py:47` is a `@contextmanager` with `try/finally` → `_release(fh)` then `fh.close()` on any exception. Verified by reading it, not assumed. |
| GEM-3 | A replace could duplicate or orphan the link-reference footer. | low | **Accepted as covered by AC10.** The rendered section never contains a footer, and `section_end` bounds the replaced span to what the section owns, so the footer is outside it. Pinned by a test rather than argued. |

### Internal review cascade (spec-reviewer → code-reviewer → doubt-reviewer, Opus)

All three ran against the merge-base diff plus the files on disk. Verdicts:
spec-compliance **REJECT** (4 blockers), code-review **no critical/high** (3
medium, 9 low), doubt **9 objections** (1 high, 4 medium, 4 low). Every blocker
and medium is fixed below; the cascade found things all four external legs
missed, which is why it runs.

| # | Finding | Sev | Fix |
|---|---|---|---|
| SPEC-1 / DOUBT-1 | **The widened FR-01.09 criterion overclaimed.** It scoped *both* refusal causes over "written directly" too, but `update_changelog` replaces a lone same-version section unconditionally — and `test_update_changelog_replaces_same_version_section` pins that overwrite. An (E) criterion contradicted by a green test. | high | **The honesty gate doing its job.** Split into two criteria: the duplicate-section refusal covers both writers; the body-mismatch and heading-marking refusals are scoped to the release-assembly path. Implementing them in the direct writer would change its contract with no AC — out of scope, now stated. |
| SPEC-2 | `assert "2" in message` cannot fail — the message embeds a pytest tmp path, which routinely contains a `2`. | high | `assert "2 sections" in message`. |
| SPEC-3 | AC5's "names the cause" untested: both arms name file + version, so an implementation raising the *wrong* message passed. | high | Both arms now assert an arm-unique phrase, CLI included. |
| SPEC-4 | AC1 claimed the plugin suite "passes untouched" while the diff edits `test_integration.py`. | high | AC1 reworded to "behaviour unchanged, no assertion changed"; the harness fix recorded under "Out of scope". |
| CODE-M1 / DOUBT-6 | `spec_from_file_location` never returns `None` for a `.py` path, so the friendly "shared/ is missing" `ImportError` was **dead code** — the real failure was a bare `FileNotFoundError`. Reachable: `ensure_shared_cache` is fail-open. | med | Check `path.is_file()` instead of the spec. |
| CODE-M2 / DOUBT-3 | **The comparison was asymmetric.** The recorded side is bounded by `section_end`; the rendered side was not. A multi-line drop bullet whose continuation `continues_section` rejects would mismatch forever — false-refusing the exact interrupted release this change exists to fix, blaming a hand edit that never happened. | med | Both sides now go through `section_body`. Test with a multi-line bullet. |
| CODE-M3 / DOUBT-4 | The AC2 guard test claimed "holds no heading pattern" while `_warn_if_legacy_unreleased_has_bullets` still carried one — case-SENSITIVE where the shared predicate lowercases, so `## [unreleased]` got the right insertion point and **no split-brain warning**. The test's `re.compile` filter could not see an inline `re.search`. | med | The warner moved onto a new shared `unreleased_start`; the guard scan widened to `re.search`/`re.findall`. |
| DOUBT-2 | **"cannot lose anything" was literally false at the heading.** A replace rewrites the whole heading line, so `## [0.3.0] - 2026-04-23 [YANKED]` silently loses the yank marker and a withdrawn release reads as normal. | med | New `heading_annotation` predicate; a heading carrying more than a version and a date is **refused**. Tested. |
| DOUBT-5 | `ensure_shared_cache` re-mirrors `shared/` only when its sentinel is absent, so a cached copy predating this module never refreshes — and the module-scope binding made that break the **whole** `lib.changelog` import, including functions that never touch the predicates. | med | Resolution moved inside `update_changelog`. (PEP-562 `__getattr__` was tried first and reverted: ruff — a hard CI gate — reports the names as undefined.) |
| CODE-L2 | The promoted `insert_section` lacked the unterminated-last-line guard its sibling has: `# Changelog` with no trailing newline yielded `# Changelog## [0.3.0]`. Pre-existing, but this is now billed as the ONE implementation. | low | Guard ported; tested. |
| CODE-L4 | `apply_section` had no `Unreleased` guard, unlike `entry_version` in the same module; `--version` is unvalidated. | low | Guard added; tested. |
| DOUBT-8 | The em-dash fix landed in the **test harness**, not the product: refusal messages still carried non-ASCII into a Windows console pipe — the one string an operator must read. | low | Refusal messages are ASCII, asserted by `err.encode("ascii")` in the CLI test. |
| CODE-L9 | `st_mtime_ns` equality can PASS through a rewrite on a coarse clock. | low | Byte comparison instead. |
| CODE-L5 | `_insert_section` alias existed only for a test import. | low | Deleted; the test imports the shared name. |
| CODE-L1, L8 | Unused `heading` binding; `SectionConflict` declared far from its raiser. | low | Both fixed by the module split. |
| CODE-L10 | SKILL.md never said `changelog_updated: false` can mean success — an agent could read it as failure and retry. | low | Documented, with the four `section_action` values. |
| CODE-L3 | On a CRLF file a converging re-run reports `replaced` and rewrites one section as LF. | low | **Accepted, documented.** Insertion already did this pre-change; giving the aggregator the plugin writer's BOM/EOL guarantees is the recorded follow-up. |
| CODE-L7 | The module is loaded under two identities (path-loader vs bare import), so `except SectionConflict` would not cross that boundary. | low | Inert — the plugin never calls the splice — and now structural: the splice lives in `changelog_splice`, which the plugin does not load. Recorded in its docstring. |
| DOUBT-7 | Insertion moved above prose trailing an `[Unreleased]`-only file. | low | Real divergence, now **pinned by a test** rather than left to be rediscovered. |
| SPEC-M8 | `test-traceability.json` still lists the deleted test. | low | Regenerated at F5b. |
| SPEC/CODE/DOUBT "stale diff" | All three noted the diff snapshot lagged the worktree (the two normalization tests added after the external review). | proc | Diff regenerated before commit; noted for future cascades. |

**Clean bills of health** (stated so they are not re-litigated): no bullet-loss
path exists on a replace — the compared span *is* the replaced span, and the
doubt reviewer failed to construct a counter-example across fences, tables,
HTML comments, setext headings and section-at-EOF; body equality cannot be
reached accidentally by a remove-and-add pair; `normalize_body` leaves
indentation alone, so nested list items stay distinct; the lock is held across
snapshot→decision→write→unlink and released on the exception path; `parents[4]`
resolves in **three** layouts (repo, versioned cache, and the `_heal_plugins`
mirror); every crash state is recoverable.

### Self-Review (8-point checklist)

1. **Spec compliance — pass.** Every AC1-AC14 has code and a test. Nothing was
   added beyond the plan except two things, both forced and both disclosed:
   the splice extraction into `changelog_sections.py` (the bloat gate; see
   below) and the `PYTHONIOENCODING` fix in the changelog plugin's
   `test_integration.py`.
2. **Error handling — pass.** The two refusal arms are the error handling. They
   raise before any write and any unlink, are re-typed at the aggregator
   boundary so the CLI contract (`AggregatorError` → exit 1) is unchanged, and
   the lock releases on the exception path (`file_lock` is a `@contextmanager`
   with `try/finally`). `LockTimeout` handling is untouched.
3. **Security basics — n/a.** No user input, no network, no secrets, no
   auth surface. Paths come from `--project-root`; the drop-file reader keeps
   its existing symlink skip and 64 KiB size bound.
4. **Test quality — pass.** Assertions are on bytes on disk (`changelog_text`)
   and on the drop set (`drop_texts`), not on return values alone. Happy path
   (converge) and error path (both refusals) are both covered. Falsifiability
   was *measured*, not assumed: neutralising `normalize_body` turns 8 of 10
   convergence tests red.
5. **Performance — n/a.** One extra pass over the changelog's lines, on a file
   read once per release.
6. **Naming & structure — pass** *after a fix*. The first cut left
   `aggregate_changelog.py` at 505 lines against a bloat baseline of 458 — a
   ratchet the pre-commit gate blocks. Rather than bump the baseline, the splice
   cluster moved into `changelog_sections.py` (411 and 289 respectively, both
   below their limits, and the baseline entries were lowered to the new exact
   counts rather than left with dead headroom). `changelog.py` likewise went
   over 300 and the loader was extracted to `_shared_sections.py` (287 / 74).
7. **Affected boundaries — pass.** The changed format is `CHANGELOG.md`.
   Producer: `aggregate_changelog` (and `changelog.update_changelog`). Consumer:
   the same writers on the next run, plus
   `verifiers/changelog_checks._extract_latest_version_from_changelog`. The
   round trip that matters — write, then read back and write again — is exactly
   what the convergence tests drive, on the real file. No `touches_io_boundary`
   path matched (`.env*`, `hooks.json`, `settings.json`, `*_config.json`,
   `*_state.json`), so the flag did not fire; the round-trip coverage exists
   anyway because it *is* the subject of the change.
8. **Test hygiene probe — pass.** `scan_for_silent_skip_without_ci_guard` over
   all six changed/added test files: **0 findings**. No `pytest.skip` was added.

## Confidence Calibration

- **Boundaries touched:** `CHANGELOG.md` (a user-authored file rewritten in
  place) and `CHANGELOG-unreleased.d/**` (the pending drop set). Plus the
  cross-plugin import boundary (ADR-045). No `*_config.json`, `.env*`,
  `hooks.json` or `*_state.json` — checked against `IO_BOUNDARY_FILE_PATTERNS`;
  no `cross_component` or `ci_supplychain` path matches either, so no risk flag
  fires. Round-trip coverage exists anyway, because the round trip *is* the
  subject of the change.

- **Empirical probes run:**
  - *Pre-change P1* — interrupted release, drops restored, re-run:
    `'## [0.3.0]' occurrences = 2`. The duplicate reproduced against the real
    `aggregate()`, not argued from the source.
  - *Pre-change P3* — a file already holding two sections for the version:
    the aggregator wrote a **third**. No refusal arm existed.
  - *Pre-change P2* — **the probe that changed the design.** 3 drops, write
    succeeds, unlink deletes 2 and dies: the record holds 3 bullets, the
    survivors render 1. An unconditional replace would have deleted released
    history — strictly worse than the bug being fixed. This is why the
    same-version replace is conditional and why there is a refusal arm at all.
  - *Post-change* — the same probe script re-run: P1 now `occurrences = 1`,
    P3 now raises `AggregatorError` instead of writing a third copy.
  - *Mutation probe (are the tests falsifiable?)* — `normalize_body` reduced to
    `return text`: **8 of 10** convergence tests go red, including both
    normalization tests added after the external review. Restored and
    re-verified green. The suite is not vacuous.
  - *Pre-existing-failure check* — the one red test on this machine
    (`test_generate_refuses_ambiguous_file_and_leaves_it_untouched`) was run
    against **unmodified `main` at 97392eea** and fails identically there. Not
    caused by this change; fixed anyway, and disclosed under "Out of scope".

- **Test Completeness Ledger** — every behaviour this diff introduces or
  changes. Principle: *testable ⇒ tested*. **0 testable-but-untested.**

  | # | Behaviour | Status | Evidence |
  |---|---|---|---|
  | 1 | No section for the version → insert | `tested` | `test_first_release_reports_inserted` + `TestStructuralInsert` (6 cases) |
  | 2 | Body matches, same date → one section, byte-identical file | `tested` | `test_rerun_after_interrupted_release_writes_the_version_once` |
  | 3 | Body matches, later date → one section, new date, old gone | `tested` | `test_rerun_resumed_on_a_later_date_still_writes_the_version_once` |
  | 4 | The converging re-run consumes the drops | `tested` | `test_converging_rerun_consumes_the_drop_files` |
  | 5 | `unchanged` skips the write, still consumes drops | `tested` | `test_converging_rerun_reports_unchanged_without_writing` (byte comparison, not mtime) |
  | 6 | Completed release re-run → clean no-op, refusal unreachable | `tested` | `test_rerunning_a_completed_release_is_a_clean_noop` |
  | 7 | Body mismatch (partial unlink) → refuse, naming the cause | `tested` | `test_partial_unlink_refuses_instead_of_deleting_released_bullets` |
  | 8 | Hand-edited section → same refusal | `tested` | `test_hand_edited_section_refuses` |
  | 9 | >1 section → refuse, reporting the count | `tested` | `test_duplicate_sections_refuse_with_the_count` (`"2 sections"`, not bare `"2"`) |
  | 10 | Heading carrying a marking a re-render would erase → refuse | `tested` | `test_yanked_marker_on_the_heading_refuses` |
  | 11 | `--version Unreleased` → refuse | `tested` | `test_aggregating_the_unreleased_block_refuses` |
  | 12 | Every refusal leaves file bytes AND drops untouched | `tested` | asserted in all five refusal tests |
  | 13 | The two refusal arms are distinguishable | `tested` | arm-unique phrases asserted in both library and CLI tests |
  | 14 | `--dry-run` previews a replace without writing or unlinking | `tested` | `test_dry_run_reports_the_replace_without_writing_or_unlinking` |
  | 15 | `--dry-run` still refuses, and exits non-zero | `tested` | `test_dry_run_still_refuses_...` + `test_dry_run_cli_also_exits_nonzero_on_a_refusal` |
  | 16 | Both refusals reach the CLI as non-zero + stderr | `tested` | two `agg_main` tests |
  | 17 | Refusal text is ASCII (survives a Windows pipe) | `tested` | `err.encode("ascii")` in the CLI mismatch test |
  | 18 | Replaced span bounded — footer/prose survive, once, in order | `tested` | `test_replace_preserves_trailing_prose_and_link_footer` (counts + ordering) |
  | 19 | Trailing whitespace is formatting, not a conflict | `tested` | `test_trailing_whitespace_in_the_recorded_section_still_converges` |
  | 20 | CRLF vs LF is formatting, not a conflict | `tested` | `test_crlf_recorded_section_matches_an_lf_rendered_one` |
  | 21 | A multi-line bullet still converges (symmetric comparison) | `tested` | `test_a_multi_line_bullet_still_converges` |
  | 22 | `insert_section` terminates an unterminated last line | `tested` | `test_insert_terminates_an_unterminated_last_line` |
  | 23 | Lowercase `## [unreleased]` bullets are still reported | `tested` | `test_lowercase_unreleased_bullets_are_still_reported` |
  | 24 | New release lands above prose trailing an `[Unreleased]`-only file | `tested` | `test_new_release_lands_above_prose_trailing_an_unreleased_block` |
  | 25 | ONE implementation: no plugin copy, no heading pattern in the aggregator | `tested` | 4 tests in `test_changelog_sections_shared.py` |
  | 26 | The plugin writer resolves the SHARED module | `tested` | `test_plugin_writer_resolves_changelog_sections_from_shared` (clean subprocess) |
  | 27 | Missing `shared/` → actionable `ImportError`, not `FileNotFoundError` | `tested` | `test_missing_shared_raises_an_actionable_import_error` |
  | 28 | A failed load leaves no half-initialised module registered | `tested` | `test_a_failed_load_does_not_leave_a_broken_module_registered` |
  | 29 | The predicates load lazily, so only the splice depends on `shared/` | `tested` | `test_the_writer_only_needs_the_shared_module_when_it_splices` |
  | 30 | `section_action` reports all four values honestly | `tested` | asserted across items 2-6 |
  | 31 | Marketplace-**cache** layout resolves `parents[4]` | `untestable` — `requires-manual-visual-judgment` | Reproducing the cache tree in a test would assert my own fixture, not the installed layout. Verified by inspection of the real cache (`cache/shipwright/shared/scripts/` holds `tests_block.py`/`markdown_table.py`) and by `shipwright-compliance/scripts/lib/test_evidence.py` already depending on the same hop in production. Both reviewers independently confirmed it resolves in **three** layouts. |
  | 32 | FR-01.09 criterion widening | `untestable` — `covered-by-existing-test` | A spec sentence is prose. What it now claims is exactly items 1-17; the narrowing after the cascade exists so it claims nothing more. |

- **Confidence-pattern check.**
  *Depth (asymptote):* every claim is asserted on the **bytes on disk** and on
  the **drop set**, not on a return value — those are the two things a release
  can destroy. Falsifiability was measured by mutation, not assumed.
  *Breadth (coverage):* insert, replace, unchanged, no-op and all four refusal
  arms; library and CLI; dry-run and live; LF and CRLF; single-line and
  multi-line bullets; first, last and only section in a file; trailing prose and
  link footers.
  *The asymptote that was missed the first time:* the external panel approved
  the code, and the internal cascade then found a **high-severity honesty
  defect in the spec** plus two assertions that could not fail. Breadth of
  reviewers is not depth — the passes that read the *files* rather than the
  diff are the ones that caught it. Both normalization tests exist only because
  a reviewer noticed the rule they encode was unpinned.
  *Integration composition:* none required — no `cross_component` machinery is
  touched (checked against `CROSS_COMPONENT_FILE_PATTERNS`). The cross-plugin
  composition that does exist (plugin writer → shared module) is covered by the
  clean-subprocess test at item 26, which is the shape `conventions.md:88`
  prescribes for exactly this boundary.

## Out of scope

- **The direct writer's refusal arms.** `update_changelog` replaces a lone
  same-version section unconditionally; only the duplicate-section refusal
  exists there. Giving it the body-equality and heading-marking arms changes
  its contract and would require retiring
  `test_update_changelog_replaces_same_version_section`, which pins the current
  behaviour. FR-01.09 is worded to match what each writer actually guarantees —
  the same discipline PR #452 applied, now applied to this iterate's own claim.
- **BOM / line-ending preservation in the aggregator.** The plugin writer has
  it (PR #452 AC12); the aggregator does not, so a replace rewrites one section
  with LF inside a CRLF file. Insertion already behaved this way, so this is
  not a regression, but the `replaced` arm widens the surface. Folding the two
  splices together is the natural follow-up and is why `changelog_splice`
  documents the divergence at the top.
- **A pre-existing Windows test-harness defect, fixed in passing.**
  `plugins/shipwright-changelog/tests/test_integration.py` decoded child output
  as UTF-8 without telling the child to encode it, so a non-ASCII byte in a
  message made `result.stderr` `None`. It reproduces on unmodified `main`
  (verified at 97392eea) and is invisible in CI, which is Linux/UTF-8. Fixed
  because F0 must be honestly green on the developer's platform; no assertion
  was changed. The **product** half of the same defect is fixed properly: the
  refusal messages are ASCII.

- `shared/scripts/tools/verifiers/changelog_checks.py::_VERSION_HEADING_RE` is a
  **third** version-heading regex, deliberately left alone. It is a *reader*
  answering "what is the latest released version", and it is semver-specific by
  design (`v?\d+\.\d+\.\d+`) so a `## [Unreleased]`-adjacent non-semver heading
  cannot be mistaken for a release. Folding it into the section predicates would
  widen what it accepts and weaken the tag-drift check it exists for. Recorded
  here so the next reader does not have to re-derive it.
- Fenced code blocks and HTML comments are still not recognised — a
  `## [1.1.0]` inside a fence parses as a heading. Inherited limitation of the
  shared predicate, documented by PR #452. With the refusal arm in place this
  now fails **closed** for the aggregator (a changelog documenting its own
  format triggers the duplicate-section refusal rather than a bad write).
- Making `git tag` / PR creation code rather than instruction (FR-01.09
  criteria 1, 3, 7, 8, 9 remain `prompt-only (mechanisable)`) — REQ-3 Phase 3.
- Migrating files already corrupted by the duplicate-section bug: AC6 stops on
  the wreckage rather than compounding it, which is the correct arm.
