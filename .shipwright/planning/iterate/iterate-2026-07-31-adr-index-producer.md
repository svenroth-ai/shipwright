# Iterate Spec: adr-index-producer

- **Run ID:** iterate-2026-07-31-adr-index-producer
- **Type:** change
- **Complexity:** medium (operator-locked — see "Complexity note")
- **Status:** draft

## Goal

`.shipwright/planning/adr/INDEX.md` is a committed derived view of the ADR spec
folder that has no producer on the path that changes it. Give it one — refresh
the index at the moment an iterate records its ADR — and give the generator a
real title source so refreshing it stops destroying human wording.

## Complexity note

`classify_complexity.py` returned `large` (conf 0.7) and then `small` (conf 0.6)
for the *same* task on two phrasings, both `prior_source: keyword`. It scored the
prose, not the change, so neither value is evidence. Locked to **medium** from
actual scope: this changes the semantics of a shared generator that every adopted
repo inherits, adds a producer call site, and rewrites a committed artifact.

## Root cause (established before any fix — Path C discipline, applied to a Path B change)

`aggregate_decisions.aggregate()` calls `rebuild_adr_index()` from inside the
`if rendered and not dry_run:` branch, which itself only runs when the folded
`valid` drop list is non-empty. Two earlier guards (`if not dd.is_dir()` and
`if not drops`) return before the lock is even taken. So the index is refreshed
**only** as a side-effect of a release pass that had drops to fold.

An ADR spec file that an iterate writes straight into
`.shipwright/planning/adr/<NNN>-<slug>.md` therefore never reaches `INDEX.md`
until some later release pass happens to have drops. Nothing else refreshes it.

Reproduced in this repo (2026-07-31, worktree `adr-index-producer`): 39 ADR files
on disk, **29** listed in `INDEX.md`, 10 unlisted (106–115). Matches the
independently measured webui symptom (ADR-133 listed, 134–138 unlisted).

## Why this is not the derived-snapshots work

`INDEX.md` is not a member of `DERIVED_SNAPSHOTS`, and registering it there would
be the wrong fix. That list exists for views that are both conflict-generating
**and wrong when derived on a branch** (`change-history.md` reads the branch's
pre-squash SHAs and an event log missing every concurrently-merging branch).
Reason two does not hold here: `INDEX.md` derives from the ADR *folder listing*,
which on a branch is correct and complete — the iterate puts its ADR file there
in the same commit, so view and truth travel together. Registering it would strip
the index row out of the very commit that adds the ADR. The fix runs the opposite
direction: make the index move **with** the ADR file.

Adjacent to but not a duplicate of `trg-ad29a709` (that one is
`derived_snapshots.py` / `integrate_main.py` ordering; this one is a call site).

## Acceptance Criteria

- [ ] **AC1** — An iterate that writes an ADR spec file and records its
      decision-drop (F3) leaves `INDEX.md` listing that file, in the same commit.
- [ ] **AC2** — A release pass refreshes `INDEX.md` even when it folds zero
      drops; a `--dry-run` pass writes nothing.
- [ ] **AC3** — The generated label for an ADR comes from that ADR file's own
      first `#` heading (with a leading `ADR-NNN`/`ADR NNN` prefix stripped), and
      falls back to the filename slug when the file has no heading.
- [ ] **AC4** — Two ADR files sharing one number both appear, and row order is
      stable against title edits (ties break on filename, not on label).
- [ ] **AC5** — A drift guard fails loudly when the committed `INDEX.md` is not
      byte-equal (LF-space) to the generated render, and its failure message
      names the regeneration command.
- [ ] **AC6** — The `_template-*.md` scaffolding file is excluded rather than
      rendered as if it were an ADR. The skip is exactly `_template-` and NOT
      every `_`-prefixed file: `_archive-agent-doc-updates.md` is real content
      the previous index linked, and delisting it would be a silent loss.
- [ ] **AC7** — A title containing markdown link metacharacters (`[`, `]`) does
      not corrupt the generated link.
- [ ] **AC8** — This repo's `INDEX.md` is regenerated in this PR (38 rows: 37
      ADRs + the `_archive-*` doc; only `_template-*` is excluded per AC6) and
      `aggregate_decisions.rebuild_adr_index` keeps working as an import path
      for consumer repos that already call it.

## Spec Impact

- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** This changes framework-internal machinery only. The
  nearest requirement, FR-01.03 (`/shipwright-plan`), promises that design
  decisions "are recorded in the project's decision log with its reasoning" —
  that obligation is met by `decision_log.md` and is untouched here. `INDEX.md`
  is a navigational view over the ADR spec *folder*, not the decision log, and
  no FR states a promise about it. Nothing user- or system-observable that a
  requirement names changes behavior.

## Out of Scope

- Registering `INDEX.md` in `DERIVED_SNAPSHOTS` (argued against above).
- Renaming any ADR file to make a generated label read better — that breaks every
  existing link.
- Reconciling a heading whose ADR number disagrees with its filename number. The
  filename stays the identity; a mismatch is a separate drift class, recorded as
  a known limit in `read_adr_title`'s docstring rather than fixed here.
- Repairing webui's index (already done target-side, PR #334).
- Registering `INDEX.md` in `CHURN_ALLOWLIST` so two parallel ADR-writing
  iterates auto-reconcile. This change does create that conflict class (the view
  is now regenerated on a branch), but wiring the churn resolver trips the
  `cross_component` risk flag and its mandatory integration-coverage test, and
  the current failure is a loud, safe abort rather than corruption. Filed as
  **trg-1acb5304** with the suggested implementation.

## Design Notes

Tier-2 design check: no UI. The one presentation decision is the row label, and
it is settled by AC3 — the ADR file's own title, verbatim after prefix-stripping,
because any transformation reintroduces "the generator cannot express what the
human wrote".

Module placement follows the repo's existing extraction precedent (ADR-102
`lib/file_lock.py`, ADR-103 `verifiers/git_helpers.py`): the render moves to
`shared/scripts/lib/adr_index.py` so the drop *producer* does not have to import
from the *aggregator* — that dependency runs backwards and this module set is
demonstrably careful about producer/consumer direction. `aggregate_decisions.py`
re-exports `rebuild_adr_index` so the existing import path keeps working.

Split shape mirrors the `gate_catalog` precedent exactly: a pure
`render_adr_index(folder) -> str` plus a writing `rebuild_adr_index(root)`, which
is what makes a byte-equality drift guard possible.

## Mini-Plan

**Chosen: extract the render, then give it two producers and a guard.**

1. New `shared/scripts/lib/adr_index.py` — `read_adr_title()`,
   `render_adr_index()` (pure, LF), `rebuild_adr_index()` (writes via the
   shared `durable_atomic_write`). Skips `_template-*`; ties break on filename;
   escapes backslashes and brackets in labels, angle-brackets odd destinations.
2. `aggregate_decisions.py` — re-export `rebuild_adr_index` for the existing
   import path; restructure `aggregate()` so the refresh runs on every
   non-`dry_run` call, including the zero-drop early returns (candidate **a**).
3. `write_decision_drop.py` `main()` — refresh the index after a successful drop,
   best-effort (candidate **b**). `main()` is the right seam because
   `finalize_bundle` shells out to this CLI, so it covers both F3 paths while
   leaving the library function a pure drop writer.
4. Three test files, split at real seams to stay under the 300-LOC rule:
   `test_adr_index.py` (renderer), `test_adr_index_writing.py` (atomicity,
   locking, stray files), `test_adr_index_producers.py` (call sites, CLI, drift
   guard — candidate **c**).
5. Regenerate this repo's `INDEX.md` (Sven's 2026-07-30 decision: the fix carries
   its own regeneration, one PR, no immediate re-drift).
6. Update `F3.md`, **`F6.md`'s explicit add list**,
   `docs/hooks-and-pipeline.md`, `docs/guide.md`, `README.md`, and the generated
   file's own "Auto-generated by" header, which currently names the wrong
   producer.

**Alternative considered — call-site-only (candidate (a) alone), no label change.**
Move `rebuild_adr_index()` out of the `if valid:` branch and stop. One-line
diff, no new module, no test churn.

**Rejected because it is actively harmful without the label decision.** The
generator derives labels purely from the filename slug, so it structurally cannot
emit `TT6` (filenames are lowercase) and cannot preserve wording a human added.
Making the generator run *more often* without fixing its label source means the
first run silently downgrades `ADR-104` and `ADR-105`, someone hand-fixes them
again, and the cycle repeats — the naive run measured 12 lines added, 2 lost.
Candidate (c) has the same defect mirrored: a drift guard over slug-derived labels
would flag the hand-polished rows as drift and force them back to the machine
form. Adopting (a) alone would convert a stale-index problem into a
wording-destruction treadmill, so the label source is a precondition for the call
site, not an optional extra.

**Also rejected — front-matter as the title source** (the other half of candidate
(ii)). It would require touching all 39 ADR files to add a field they do not have
today. The first `#` heading is already present in **39/39** files and is already
the human title, so it is a title source that costs zero migrations.

## Revisions from external plan review (2026-07-31)

`external_review.py --mode iterate` via OpenRouter; gemini-3.1-pro-preview
`approve`, gpt-5.6-terra `revise`, no contradiction. Raw reply:
`external-plan-review.json`. Six findings accepted, all folded into the plan:

- **R1 — a real regeneration command (GPT #6, low).** AC5 promises the drift
  failure names a command, but the plan only defined a library API, and the
  obvious substitute is a trap: pointing someone at `aggregate_decisions.py`
  would *fold and delete their decision-drops* as a side effect of refreshing an
  index. Add `shared/scripts/tools/rebuild_adr_index.py` — a side-effect-limited
  CLI — and use that one string verbatim in the generated header, the drift-guard
  message, `F3.md`, and `hooks-and-pipeline.md`.
- **R2 — the heading contract is under-specified (GPT #4 + Gemini #1/#2,
  medium).** `read_adr_title()` must take the first ATX **level-1** heading
  (`# `, never `##`) that is outside YAML front matter and outside fenced code
  blocks — otherwise a `# run this` line inside a ```bash fence becomes an ADR
  title. Prefix-stripping needs a digit boundary so `ADR-1040 Notes` is not read
  as `ADR-104`, and a heading that is *only* a prefix must fall back to the slug.
- **R3 — writer safety (GPT #2, medium).** Two producers now write the index.
  `rebuild_adr_index()` owns its own synchronization: take the index file lock,
  scan and render inside it, and write through a temp file + atomic replace so an
  interrupted run cannot leave a partial `INDEX.md`. Both call sites get this by
  construction because there is exactly one writing implementation.
- **R4 — a missing ADR folder is a strict no-op (GPT #3, medium).** Refreshing on
  every non-dry-run call must not *create* `.shipwright/planning/adr/` or an
  empty `INDEX.md` in repos that never adopted ADRs. That would mint a new
  committed artifact as a side effect of an unrelated release pass.
- **R5 — best-effort must be loud (GPT #5 + Gemini #3, medium).** A swallowed
  index-write failure hands the developer a green local run and a red CI drift
  guard. Catch `OSError` only (programming errors still propagate), and warn to
  stderr naming the index path and the R1 command.
- **R6 — prove the commit boundary, do not assume it (GPT #1, high).** AC1 says
  *same commit*, and the plan only established *same worktree*. F3 does run
  before F6, but **F6 stages an explicit per-path list and never `git add -A`**,
  so a regenerated `INDEX.md` that nobody adds is simply never committed — the
  proposed test would pass while AC1 failed in reality. This is the finding that
  most changes the work: `INDEX.md` must be named in F6's add list, documented in
  `F3.md`, and asserted against committed content (`git show`), not the working
  tree.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `lib/adr_index.rebuild_adr_index` | humans; `test_adr_index_drift` | Markdown (`INDEX.md`) |
| ADR author (first `#` heading) | `lib/adr_index.read_adr_title` | Markdown heading |
| `write_decision_drop.main` (F3) | — | invokes the producer |
| `aggregate_decisions.aggregate` (release) | — | invokes the producer |

The changed serialized format is `INDEX.md` itself: its label column gains a new
source (the ADR file's heading). Line endings are the live hazard —
`core.autocrlf=true` means the working tree is CRLF while the render is LF, so
every comparison is done in LF-space via `read_text()`, exactly as the
`gate_catalog` drift guard does.

## Confidence Calibration

- **Boundaries touched:** `INDEX.md` render/parse; the ADR-heading convention;
  two producer call sites (F3 drop write, release aggregation).

- **Empirical probes run:**
  - Counted the folder against the index: 39 ADR files, 29 rows, 10 missing
    (106–115) — the defect reproduces here, not just in webui.
  - Extracted the first `#` heading from all 39 ADR files: **39/39 have one**, so
    the title source is universally available and the slug fallback is a safety
    net rather than the common path.
  - Diffed a prototype heading-based render against the committed index: the
    hand-polished ADR-105 row regenerates **byte-identically**, confirming the
    hand-edit was reproducing the heading all along.
  - Read the committed bytes: `INDEX.md` is CRLF on disk and `gate_catalog.md`
    is too, and `core.autocrlf=true` — so comparisons must be LF-space.
  - Traced the bundled F3 path: `finalize_bundle_lib.f3_argv` invokes
    `write_decision_drop.py` as a **subprocess**, so `main()` is the single
    chokepoint covering both the manual and bundled F3 paths.
  - Found this repo has its own duplicate ADR number (two `097-` files), so the
    duplicate-tolerance constraint is testable against real data, not a webui-only
    hypothetical.
  - Prototype render reordered the two `097-` rows because ties broke on the
    (now changing) label — caught before implementation and fixed by breaking
    ties on filename.
  - Checked the ADR-045 lib-collision rule: `write_decision_drop.py` already
    eager-imports `from lib.iterate_entry import ...`, so adding
    `from lib.adr_index import ...` widens no import surface.

- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | F3 drop write refreshes `INDEX.md` in the worktree (AC1) | tested | test_f3_drop_write_refreshes_the_index PASSED |
  | 2 | Release pass refreshes with zero drops (AC2) | tested | test_aggregate_refreshes_with_zero_drops PASSED |
  | 3 | `--dry-run` writes nothing (AC2) | tested | test_aggregate_dry_run_writes_nothing PASSED |
  | 4 | Label read from `#` heading, ADR-prefix stripped (AC3) | tested | test_title_comes_from_the_h1_heading + test_adr_number_prefix_is_stripped_in_every_observed_style[4 styles] PASSED |
  | 5 | Falls back to slug when no heading (AC3) | tested | test_falls_back_to_the_slug_when_there_is_no_heading PASSED |
  | 6 | Duplicate numbers both listed (AC4) | tested | test_duplicate_numbers_both_appear PASSED |
  | 7 | Tie order stable against title edits (AC4) | tested | test_tie_order_is_stable_against_title_edits PASSED |
  | 8 | Drift guard fails on a stale index (AC5) | tested | test_drift_guard_actually_fails_on_a_stale_index PASSED |
  | 9 | Committed `INDEX.md` matches the render (AC5/AC8) | tested | test_committed_index_is_not_stale PASSED |
  | 10 | `_`-prefixed scaffolding excluded (AC6) | tested | test_the_template_is_excluded + test_the_skip_does_not_swallow_real_underscore_files PASSED |
  | 11 | `[`/`]` in a title escaped (AC7) | tested | test_link_metacharacters_in_a_title_are_escaped PASSED |
  | 12 | `aggregate_decisions.rebuild_adr_index` import path preserved (AC8) | tested | test_rebuild_is_importable_from_aggregate_decisions PASSED |
  | 13 | Missing ADR folder = no-op: no dir, no empty index created (R4) | tested | test_missing_folder_is_a_strict_noop + test_cli_on_a_repo_without_adrs_creates_nothing PASSED |
  | 14 | F3 index refresh is best-effort — an unwritable index does not fail the drop (R5) | tested | test_f3_refresh_is_best_effort_and_warns PASSED |
  | 15 | A failed F3 refresh warns on stderr naming the regeneration command (R5) | tested | test_f3_refresh_is_best_effort_and_warns PASSED |
  | 16 | `##` is not read as the title (R2) | tested | test_h2_is_not_read_as_the_title PASSED |
  | 17 | A `# ` line inside a fenced code block is not read as the title (R2) | tested | test_heading_inside_a_fenced_code_block_is_not_the_title + test_tilde_fenced_code_block_is_also_skipped + test_longer_fence_is_not_closed_by_a_shorter_one PASSED |
  | 18 | A `#` line inside YAML front matter is not read as the title (R2) | tested | test_heading_inside_yaml_front_matter_is_not_the_title PASSED |
  | 19 | `ADR-1040 Notes` is not mis-stripped to `104` (R2) | tested | test_four_digit_number_is_not_mis_stripped PASSED |
  | 20 | A heading that is only an `ADR-NNN` prefix falls back to the slug (R2) | tested | test_heading_that_is_only_a_prefix_falls_back_to_the_slug PASSED |
  | 21 | Index write is atomic — no partial file on interrupted write (R3) | tested | test_failed_write_leaves_the_previous_index_intact PASSED |
  | 22 | `rebuild_adr_index.py` CLI regenerates and reports (R1) | tested | test_cli_regenerates_the_index PASSED |
  | 23 | The command named in the drift-guard message is the one that exists (R1) | tested | test_regen_command_names_a_script_that_exists PASSED |
  | 24 | **AC1 end-to-end: the index row ships in the same COMMIT as the ADR (R6)** | tested | test_index_row_ships_in_the_same_commit_as_the_adr PASSED (git show HEAD:) |
  | 25 | A longer fence is not closed by a shorter one (ext. code review) | tested | test_longer_fence_is_not_closed_by_a_shorter_one PASSED |
  | 26 | A backslash before `]` cannot break out of the link label (ext. code review) | tested | test_backslash_before_a_bracket_cannot_break_out_of_the_label PASSED |
  | 27 | A `)` in a filename does not truncate the destination (ext. code review) | tested | test_destination_with_parens_uses_angle_brackets + test_ordinary_filenames_are_not_angle_wrapped PASSED |
  | 28 | The regen command is layout-independent for adopted repos (code review M4) | tested | test_regen_command_is_layout_independent PASSED |
  | 29 | The render is LF in BYTES, not just through read_text (code review M3) | tested | test_render_is_written_verbatim_lf_even_on_windows PASSED |
  | 30 | A LockTimeout does not fail the F3 drop (code review M1) | tested | test_f3_refresh_survives_a_lock_timeout PASSED |
  | 31 | Nothing transient is left in the tracked ADR folder (code review L1) | tested | test_rebuild_leaves_nothing_but_the_index_in_the_adr_folder PASSED |
  | 32 | `_archive-*` is NOT delisted; only `_template-*` is skipped (doubt review) | tested | test_the_skip_does_not_swallow_real_underscore_files PASSED |
  | 33 | F6's add path is derived from F6.md, not restated (doubt review) | tested | test_f6_add_list_names_the_adr_folder + _f6_adr_add_path PASSED |

- **Confidence-pattern check:** filled at Step 7.5, before F0.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run pytest shared/tests/test_adr_index_producers.py shared/tests/test_adr_index_writing.py -q`
- **Evidence path:** `.shipwright/runs/iterate-2026-07-31-adr-index-producer/surface_verification.json`
- **Result:** exit 0, `tests_run: 22`.

Originally planned as `surface: none` on the reasoning that a plugin monorepo has
nothing startable. That was wrong for *this* change: it ships an executable —
`shared/scripts/tools/rebuild_adr_index.py` — and the runner drives it as a real
subprocess against real ADR folders (`test_cli_regenerates_the_index`,
`test_cli_on_a_repo_without_adrs_creates_nothing`), plus the F3 producer end to
end into a real git commit read back with `git show`. Claiming no surface when a
new CLI exists would have been the spec-only-authorship dodge F0.5 exists to
catch.
