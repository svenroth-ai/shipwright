# Iterate Spec: inline-suppression-ratchet

- **Run ID:** iterate-2026-08-05-inline-suppression-ratchet
- **Type:** feature
- **Complexity:** medium
- **Status:** draft

## Goal
Decide the open schema question on triage card **trg-9a2539df** (P2.20) and
implement the decided alternative. The card has been re-filed twice without
its content changing — `trg-87174b37` → `trg-095cd2bf` (retitled into the
phase scheme) → `trg-9a2539df` (re-filed to carry a launch payload) — which is
itself the point: the question kept being *carried forward* rather than
answered.

The question: an inline `# nosemgrep: <rule-id>` is a real, in-effect
silencing of a security finding on production code. It carries a
justification comment but no owner, no expiry and no central visibility.
Should `shipwright_accepted_risks.yaml` gain an entry type
(`target`) for it?

**Operator decision (2026-08-05): NO — decline the entry type, and make the
existing position enforceable instead of merely documented.** The register's
`target` vocabulary stays at four values; no schema bump, no adopter
migration. In its place this run adds a per-rule **anti-ratchet baseline** so
inline suppressions cannot grow unnoticed, gives each accepted rule a
recorded rationale, and renders the count on the compliance dashboard.

## Why the entry type was declined

1. **An offline reconciler would have to mirror Semgrep and would drift.**
   The register's `check` gate is offline and read-only by design. Faithful
   offline discovery of inline suppressions means re-implementing Semgrep's
   own suppression semantics: per-language comment syntax, the bare
   `nosemgrep` form (which suppresses *every* rule on the line, not one),
   the adjacency rule (matched line *or* preceding line), and rule-id prefix
   matching. Each is a drift site.
2. **Drift is asymmetric, and a reconciler degrades dangerously.** In a
   *both-directions* gate a mirror error produces a false `STALE`, which
   advises the operator to delete a register entry that is doing its job.
   The codebase has already paid for this failure mode once: the
   `ignore_unreadable` branch in `accepted_risks_cli._format_check` exists
   solely to stop the gate recommending "remove the record" over a YAML
   typo. A **counting** ratchet has the opposite bias — over-counting is
   absorbed by the baseline and never advises a deletion.
3. **The register's defining field does not fit.** `expires` is what the
   register is *for* ("an acceptance without a due date is a blanket
   suppression"). But `non-literal-import` on the ADR-045 dynamic loader is
   not a time-bounded risk acceptance; it is a permanent consequence of how
   the loader works. Forcing 20 such sites into an expiry-keyed register
   produces entries renewed by ritual, which devalues the entries whose date
   genuinely means something (the declined SHA-pinning posture). A risk
   acceptance says *"real, accepted until DATE"*; an inline suppression says
   *"a false positive at this site, permanently"*. Conflating them is the
   category error the existing `accepted_risk_scan` docstring already warns
   about.

**Explicitly rejected alternative:** adding the value to `STATIC_TARGETS`.
That forces the drifting mirror from (1) and turns CI red at every adopter
holding even one `# nosemgrep`.

## Acceptance Criteria
- [x] Discovery lives in a shared leaf and returns per-rule site counts from
  git-tracked, non-prose files. Delivered as a TRIO rather than one module —
  `inline_suppression_scan` (discovery) / `inline_suppression_baseline` (the
  document) / `inline_suppressions` (the rule + one entry point) — because the
  single module crossed the 300-LOC cap; the seam mirrors the register's own.
  Both spellings Semgrep honours (`nosemgrep`, `nosem`) are matched
  case-insensitively; the bare form is out of scope and disclosed.
- [x] A repo-root baseline `shipwright_inline_suppressions.json` records, per
  rule, the accepted site count plus a `rationale_ref` naming a **recorded
  decision** (validated by the same `DECISION_REF_RE` the register uses,
  imported — not duplicated) and a rule-specific `statement`.
- [x] The ratchet rule. **BLOCK:** measured sites `>` `max_sites`; a rule with
  **no** entry; a **dead** entry (rule suppressed nowhere); an unreadable or
  worktree-missing file. **ADVISORY:** a rule whose count merely shrinks.
  *The `dead` class was added in Stage-2 review* — the first version asserted
  that block in a test while the contract promised it could not happen, so
  `shrunk` and `dead` are now separate and `shrunk` genuinely never reaches
  `ok`.
- [x] A malformed baseline fails **closed** (mirrors
  `accepted_risks.RegisterError`); an **absent** baseline reads as empty and
  therefore blocks any discovered rule as unrecorded, rather than passing.
- [x] A live repo guard in `shared/tests/` runs the ratchet against THIS repo,
  binding on the path CI already requires — the same wiring the accepted-risk
  register uses. It calls `reconcile` directly; the CLI is an operator
  front-end with its own exit-code tests, and the docs say so precisely.
- [x] Synthetic negative controls prove **every** block fires, and that shrink
  does not. 81 tests in `shared/tests` + 9 dashboard tests.
- [x] The compliance dashboard renders an inline-suppression block that states
  it is deliberately not register-tracked. Visibility, not reconciliation — and
  it says so in the rendered text, without citing a Shipwright-internal run id
  that would not resolve in an adopter project.
- [x] The declined-entry-type decision is recorded as a decision drop (F3), so
  the position is **decided** rather than inherited — what the triage card asks
  for.
- [x] The three prose statements of the position (`accepted_risks.py`,
  `accepted_risk_scan.py`, the register file header) point at the decision and
  at the ratchet, pinned by a drift test so they cannot silently revert to a
  bare assertion.
- [x] **The suppression PRODUCER knows about the gate.** `shipwright-security`'s
  SKILL.md Step 4, its `suppression-syntax.md` reference, and `guide.md` all now
  say that adding a suppression is a two-file change. Added after Stage-3 review
  found the pipeline's own producer emitting changes the gate would reject with
  no instruction to update the baseline.

## Spec Impact
- **Classification:** none
- **NONE justification:** monorepo-internal security-governance tooling. Adds
  a gate and a dashboard row; changes no product-facing behaviour and no FR.
  The register's own public schema is deliberately **unchanged** — that is the
  decision this run records.

## Out of Scope
- **The bare `nosemgrep` form** (no rule id), which suppresses every rule on
  its line. Measured on this repo: all 9 occurrences of the bare token are
  **prose mentions in docstrings**, zero are real suppressions, so a
  bare-token scan would be 100% false-positive. Counting the explicit form
  only is therefore the non-drifting choice; the blind spot is disclosed here
  rather than engineered around with a heuristic that would misfire.
- **A pre-commit hook.** The bloat anti-ratchet has one; this deliberately
  does not. A file under `scripts/hooks/` or `**/hooks/*.py` would trip the
  `cross_component` risk flag and pull an integration-coverage obligation into
  a change that otherwise has none. The pytest live guard is the binding gate,
  matching the closest precedent (the accepted-risk register also has no
  pre-commit hook).
- **Per-site (path+line) keying.** Per-rule counting cannot see a suppression
  *moved* from one file to another at constant count. That is a refactor whose
  net risk is unchanged, so the detection value is low while the churn cost —
  a baseline edit on every file move — is high. Disclosed, not closed.
- **Scan-time SARIF reconciliation.** Semgrep reports its own inline
  suppressions authoritatively as `suppressions:[{kind:inSource}]`
  (already read by `security_findings._result_is_suppressed`). That is a
  faithful discovery channel, but only at scan time, so it cannot back an
  offline gate. Recorded here as the design that a future card would build on
  if per-site expiry is ever genuinely wanted.
- **Resolving rule ids the way Semgrep does.** Semgrep accepts an id PREFIX,
  so the count is per *spelling*, not per rule: the same rule under two
  spellings becomes two entries and neither ratchets. Closing this means
  re-implementing Semgrep's matching — the drift the whole design refuses — so
  it is disclosed in the module docstring and in `docs/security-ci-setup.md`
  (Stage-3 doubt review, D5). What still holds: no spelling grows unrecorded.
- Changing `.trivyignore*`, the `SHIPWRIGHT_SEMGREP_*` env channel, or any
  existing register entry.

## Design Notes
n/a — no UI surface. The one rendered artifact is a markdown block in the
compliance dashboard's security section.

## Affected Boundaries
- **`shipwright_inline_suppressions.json`** — a new hand-written JSON file
  parsed by `json.loads` at a process boundary.
- The source-tree walk is a read-only boundary (file contents → counts).

**Correction — `touches_io_boundary` does NOT fire, and the planning note that
said it would was wrong.** Re-checked against the real diff with the
authoritative detector (Step 3.4): `is_io_boundary_change` is **path-only**,
and its content-keyword half (`json.load(s)?` and friends) is *deliberately
deferred*, documented as such in `risk_detectors.py` itself. The five path
patterns are `.env*`, `hooks.json`, `settings.json`, `*_config.json`,
`*_state.json`; this baseline is `shipwright_inline_suppressions.json` and
matches none.

Observed, not filed: a repo-root hand-written `shipwright_*.json` is
semantically the same class as `*_config.json`, so the naming pattern misses
it. That is **pre-existing and consistent** — `shipwright_bloat_baseline.json`
has the identical property — not a gap this change introduced, and the
detector's narrowness is a recorded decision rather than an oversight. Left
alone deliberately.

**The Boundary Probe was done anyway** (Ledger row 20, round-trip through the
file boundary). It is recorded as voluntary, not as satisfying a flag — a probe
claimed as mandated when nothing mandated it is exactly the kind of
after-the-fact justification the Confidence Calibration exists to refuse.

**Full diff-driven re-check result — no risk flag fires on this diff:**
`cross_component` False · `touches_ci_supplychain` False · `touches_io_boundary`
False · `touches_build` False. Stage 1's `touches_migrations` was a prose match
on the word "schema" in the task description and is confirmed a false positive.
Complexity stays **medium** on scope (11 new files, a new binding CI gate, a
dashboard surface), not on a safety floor — there is none.

## Confidence Calibration
- **Boundaries touched:** `shipwright_inline_suppressions.json` — hand-written
  JSON parsed at a process boundary; plus the read-only source-tree boundary
  (file contents → per-rule counts). Neither raises `touches_io_boundary` —
  see the correction under Affected Boundaries; the round-trip probe was run
  regardless.

- **Empirical probes run:**
  - **The measurement, before writing any baseline.** Ran the scanner against
    this repo: 5 rules / 27 sites — but 7 of them came from
    `plugins/shipwright-security/skills/security/references/suppression-syntax.md`,
    a document *explaining* the syntax, including two invented rule ids
    (`rule.id`, `rule.id.here`). This is the string/prose false-positive class
    the external review predicted (GPT #1), materialising in real data. It is
    also *wrong* on the merits: Semgrep never applies a Python rule to a
    markdown file, so a suppression comment there is in effect for nothing.
    Fixed by excluding prose suffixes — as a **denylist of prose**, never an
    allowlist of code, so a missed entry is a loud false positive rather than a
    silent miss. Re-measured: **5 rules / 20 sites, all real `.py`**.
  - **The gate actually fires (behavioural probe, not a unit test).** Appended
    a real `# nosemgrep` to `shared/scripts/smoke_test.py`, then ran the
    shipped CLI and the live guard: CLI exit `1` naming
    `shared/scripts/smoke_test.py:222` as the new site, guard test RED.
    Restored; `git status` clean; CLI back to `no drift.` A gate proven only by
    fixtures is a gate proven only against itself.
  - **The gate caught its own source (dogfooding).** With the CLI tests added,
    the live repo guard went RED on
    `shared/scripts/inline_suppression_scan.py:74` — the `#:` comment
    documenting the regex format wrote the pattern with a *literal* example
    rule id, so it matched itself and invented a rule called `rule`. This is
    the disclosed string-literal limitation, produced by the module explaining
    itself, and it BLOCKED exactly as specified. Fixed by writing the format
    with angle-bracket placeholders (which the character class excludes by
    design) and recording in the comment that the brackets are load-bearing.
    Two things are now evidenced rather than asserted: the `<`/`{` exclusion
    works, and the limitation is real enough to hit its own author within one
    session.
  - **Self-review found a laundering hole the tests did not.** `scan
    --as-baseline` emitted `rationale_ref: "ADR-000"` and a sentence-length
    TODO `statement`, both of which PASS validation — so the skeleton could be
    piped straight into the baseline for a green gate with no real governance,
    while the CLI told the operator the placeholders were rejected. Both
    placeholders are now `"TODO"` (failing `DECISION_REF_RE` and the 20-char
    minimum respectively), pinned by
    `test_inline_suppressions_cli.py::test_the_skeletons_placeholders_are_rejected_by_the_gate`.
  - **The register's own gate still passes** after the three prose edits:
    `test_accepted_risks_repo_guards.py` green (the register file is parsed by
    `check`, so a comment edit that broke its YAML would surface here).
  - **The dashboard block renders against real repo state** — 5 rows, all
    counts equal to baseline, plus the "visibility, not per-site review"
    disclaimer.
  - **Full compliance plugin suite**: 1627 passed / 5 skipped — no regression
    from the `ci_security` render change.
  - `uvx ruff@0.15.15 check .` — all checks passed.

- **Test Completeness Ledger:** 81 tests in `shared/tests` + 9 in
  `plugins/shipwright-compliance/tests`. **Re-derived from `--collect-only`
  after the Stage-2 and Stage-3 fixes, not carried forward** — the first
  version was written before those fixes, and Stage-3 (D2) correctly found it
  citing three tests that no longer existed and one row stating the delivered
  contract backwards. An evidence table nobody re-ran is the same defect this
  run exists to fix, one level up.

  | # | Testable behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | Both suppression forms this repo really uses are found (own line; trailing on a code line) | tested | `scan::test_finds_the_standalone_comment_form` + `::test_finds_the_trailing_comment_form` |
  | 2 | A comma-separated rule list counts one site per rule | tested | `scan::test_splits_a_comma_separated_rule_list` |
  | 3 | Each site is a locatable `path:line`, and output is sorted so diagnostics are byte-stable | tested | `scan::test_sites_carry_a_locatable_path_and_line` + `::test_output_is_sorted_for_stable_diagnostics` |
  | 4 | Every documented comment marker is recognised (a missed marker under-counts silently) | tested | `scan::test_every_documented_comment_marker_is_recognised` |
  | 5 | **Every spelling Semgrep honours is counted** — `nosem`, `nosemgrep`, both uppercased. Keying to the lowercase literal left a working bypass | tested | `scan::test_every_spelling_semgrep_honours_is_counted` (4 params) |
  | 6 | A Unicode space (NBSP) before the colon still matches, as it does for Semgrep | tested | `scan::test_a_non_breaking_space_before_the_colon_is_still_a_suppression` |
  | 7 | A suppression at line start, with no marker before it, is counted | tested | `scan::test_a_suppression_is_recognised_at_line_start_without_a_marker` |
  | 8 | A rule id in ordinary prose (no marker, real text before it) is not counted | tested | `scan::test_a_rule_id_in_ordinary_prose_is_not_counted` |
  | 9 | **A non-UTF-8 source file is still scanned.** The decode is only reached after the token matched, so skipping on decode error meant discarding a file known to hold a suppression — fail-open, reachable with any cp1252 file | tested | `scan::test_a_non_utf8_source_file_is_still_scanned` |
  | 10 | A genuine binary blob is skipped without raising the partial-count alarm | tested | `scan::test_a_binary_blob_is_skipped_without_suspicion` |
  | 11 | **A large file is scanned, not capped out.** No size cap exists: 2 MB was a silent bypass, 50 MB-and-block only moved the defect | tested | `scan::test_a_large_file_is_scanned_rather_than_capped_out` |
  | 12 | A token straddling a streaming-chunk boundary is still found (the overlap) | tested | `scan::test_a_token_straddling_a_chunk_boundary_is_still_found` |
  | 13 | An unreadable file is REPORTED, not skipped — a partial count is a bypass | tested | `scan::test_an_unreadable_file_is_reported_not_skipped` |
  | 14 | **A tracked file missing from the worktree is reported** (sparse checkout, `rm` without `git rm`, MAX_PATH) — `is_file()` swallows the OSError, so this used to vanish into an advisory `shrunk` | tested | `scan::test_a_tracked_file_missing_from_the_worktree_is_reported` |
  | 15 | The file set comes from `git ls-files`; untracked files are not counted | tested | `scan::test_a_git_tree_counts_tracked_files_and_ignores_untracked` |
  | 16 | A non-git tree falls back to a walk, REPORTS the narrower mode, and skips vendored/worktree dirs | tested | `scan::test_a_non_git_tree_falls_back_to_a_walk_and_says_so` + `::test_the_fallback_walk_skips_vendored_and_worktree_directories` |
  | 17 | **`files_examined` is reported**, so "0 suppressions in 3702 files" cannot be confused with "0 files examined" | tested | `scan::test_scan_reports_how_many_files_it_examined` |
  | 18 | Prose files are not counted (a suppression in markdown is in effect for nothing) | tested | `scan::test_prose_files_are_not_counted` |
  | 19 | **Shipwright's own record artifacts (`.json`/`.jsonl`) are not counted** — governance artifacts QUOTE code, and JSON has no comment syntax. Stage-3 predicted the `.jsonl` half; the F0 suite found the `.json` half live, red on this run's own `reviews.json` | tested | `scan::test_shipwrights_own_record_artifacts_are_not_counted` (2 params) |
  | 20 | `.txt` is still scanned — Semgrep supply-chain rules run over `requirements.txt` | tested | `scan::test_a_requirements_txt_is_still_scanned` |
  | 21 | Disclosed limit 1: a rule id inside a string literal IS counted — pinned so a future change to it is deliberate | tested | `scan::test_a_rule_id_inside_a_string_literal_is_a_known_false_positive` |
  | 22 | Disclosed limit 2: the bare form (no rule id) is not counted | tested | `scan::test_the_bare_form_without_a_rule_id_is_not_counted` |
  | 23 | A corrupt baseline fails closed — 5 shapes (unparseable, non-object, bad schema, missing `rules`, non-list `rules`) | tested | `baseline::test_a_corrupt_baseline_fails_closed` (5 params) |
  | 24 | A duplicate JSON key is refused (`json.loads` silently keeps the last) | tested | `baseline::test_a_duplicate_json_key_is_refused` |
  | 25 | A half-filled entry is an ERROR, not a skipped row — 8 shapes incl. `max_sites: true`, since `bool` subclasses `int` | tested | `baseline::test_a_half_filled_entry_is_an_error_not_a_skipped_row` (8 params) |
  | 26 | An unknown TOP-LEVEL key is refused, while `_readme` is allowed (JSON has no comments, so the instructions live in the file) | tested | `baseline::test_an_unknown_top_level_key_is_refused` + `::test_the_readme_key_is_allowed_because_json_has_no_comments` |
  | 27 | **`max_sites: 0` is refused** — dead on arrival and unsatisfiable; absence already means "may never be suppressed" | tested | `baseline::test_a_max_sites_of_zero_is_refused` |
  | 28 | A duplicate rule entry is refused | tested | `baseline::test_a_duplicate_rule_entry_is_refused` |
  | 29 | `rationale_ref` validation IS the register's regex OBJECT, not a copy that can drift | tested | `baseline::test_rationale_ref_validation_is_the_registers_own_rule` |
  | 30 | **Boundary probe:** the baseline round-trips through the file boundary unchanged | tested | `baseline::test_baseline_round_trips_through_the_file_boundary` |
  | 31 | A seeded baseline is accepted by the same reader and pins the exact count with no headroom | tested | `baseline::test_a_seeded_baseline_is_accepted_by_the_gate_that_reads_it` + `::test_a_seeded_baseline_pins_the_exact_count_with_no_headroom` |
  | 32 | Growth beyond `max_sites` BLOCKS | tested | `rule::test_growth_beyond_the_baseline_blocks` |
  | 33 | A rule with no baseline entry BLOCKS as unrecorded | tested | `rule::test_a_rule_with_no_baseline_entry_blocks_as_unrecorded` |
  | 34 | A shrinking count is advisory and never reaches `ok` | tested | `rule::test_shrinking_is_advisory_and_never_blocks` |
  | 35 | **A rule suppressed NOWHERE is a `dead` entry and BLOCKS** — its own class, not a slice of `shrunk`, so the shrink promise stays literally true | tested | `rule::test_a_rule_suppressed_nowhere_is_a_dead_entry_and_blocks` |
  | 36 | An exactly-matching count passes with no advisory | tested | `rule::test_an_exactly_matching_count_passes_cleanly` |
  | 37 | An unreadable file blocks at the rule layer too | tested | `rule::test_an_unreadable_file_blocks_because_the_count_is_partial` |
  | 38 | An ABSENT baseline does not silence the gate, but a clean tree still passes | tested | `rule::test_an_absent_baseline_does_not_silence_the_gate` + `::test_an_absent_baseline_with_no_suppressions_passes` |
  | 39 | The block report names the rule, the exact site, and a remedy | tested | `rule::test_the_block_report_names_the_rule_the_site_and_a_remedy` |
  | 40 | The CLI's three exit codes stay distinct: 0 clean, 1 drift, 2 baseline-unreadable | tested | `cli::test_check_exits_zero_on_a_compliant_tree` + `::test_check_exits_one_on_a_ratchet` + `::test_check_exits_two_on_a_corrupt_baseline` |
  | 41 | An advisory-only result exits 0 AND does not print the word "drift" | tested | `cli::test_check_exits_zero_when_the_only_finding_is_advisory` |
  | 42 | A missing baseline is disclosed rather than passing quietly | tested | `cli::test_check_discloses_a_missing_baseline_rather_than_passing_quietly` |
  | 43 | The `--as-baseline` skeleton is rejected if committed unedited, each placeholder independently, and pins the real counts | tested | `cli::test_the_skeletons_placeholders_are_rejected_by_the_gate` + `::test_each_skeleton_placeholder_is_rejected_independently` (2 params) + `::test_the_skeleton_pins_the_real_measured_counts` |
  | 44 | **Seeding refuses a PARTIAL count** — `seed_baseline` discards `unreadable`, so a skeleton over an unreadable file would freeze numbers too low | tested | `cli::test_seeding_refuses_a_partial_count` |
  | 45 | **Prose after a comma is diagnosed, not just blocked** — a phantom rule id gets a NOTE naming the cause | tested | `cli::test_prose_after_a_comma_is_diagnosed_not_just_blocked` |
  | 46 | **A `--project-root` that is not a directory fails CLOSED** (it used to print "no drift." and exit 0) | tested | `cli::test_a_project_root_that_is_not_a_directory_fails_closed` |
  | 47 | `scan` lists each site so an operator can act on it | tested | `cli::test_scan_lists_each_site_for_the_operator` |
  | 48 | THIS repo complies, asserted over all FOUR blocking classes and deliberately not over `shrunk` | tested | `guard::test_no_inline_suppression_has_outgrown_its_baseline` |
  | 49 | THIS repo's baseline is non-empty, cites recorded decisions, and each statement NAMES ITS OWN RULE's subject (not merely differing from the others) | tested | `guard::test_the_baseline_is_loadable_and_non_empty` + `::test_every_baseline_entry_cites_a_recorded_decision` + `::test_every_baseline_statement_names_its_own_rules_subject` |
  | 50 | THIS repo measures in `git` mode, not the broader walk | tested | `guard::test_the_file_set_comes_from_git_in_this_repo` |
  | 51 | The decision stays decided: all three prose sites name it and the control, and the baseline points back at the register | tested | `prose_pointers` (4 tests) |
  | 52 | The dashboard keeps three states distinct: reader/baseline broken, zero suppressions, suppressions present | tested | `view::test_a_clean_tree_says_none_rather_than_rendering_nothing` + `::test_an_invalid_baseline_warns_instead_of_rendering_a_reassuring_zero` + `::test_an_unreachable_shared_reader_warns_and_counts_nothing` |
  | 53 | The dashboard renders an unrecorded suppression as DRIFT and an over-baseline count as exceeded | tested | `view::test_a_suppression_with_no_baseline_entry_renders_as_drift` + `::test_a_count_over_its_baseline_is_flagged_in_the_table` |
  | 54 | The dashboard states it is visibility, NOT per-site review, and discloses a non-git file set | tested | `view::test_the_section_states_that_it_is_visibility_not_per_site_review` + `::test_a_non_git_tree_discloses_the_broader_file_set` |
  | 55 | The rendered block cites no Shipwright-internal run id (it renders into adopter projects) | tested | `view::test_the_rendered_block_cites_no_shipwright_internal_run_id` |

  Prefixes: `scan` = `test_inline_suppression_scan.py`, `baseline` =
  `test_inline_suppression_baseline.py`, `rule` =
  `test_inline_suppressions.py`, `cli` = `test_inline_suppressions_cli.py`,
  `guard` = `test_inline_suppressions_repo_guard.py`, `prose_pointers` =
  `test_inline_suppressions_prose_pointers.py` (all under `shared/tests/`);
  `view` = `plugins/shipwright-compliance/tests/test_inline_suppression_view.py`.

  **0 untested-testable. 0 `untestable` rows.** Bold rows are behaviors that did
  not exist until a review found the defect they now pin.

- **Confidence-pattern check:** *Asymptote (depth)* — this run contains **six**
  confidence reversals, and not one came from reasoning about the design. Each
  layer caught what the layer before it could not, which is the argument for
  having them: a single "am I confident?" at any point would have returned yes.
  (1) The external plan review rejected the source-extension allowlist as a
  bypass class. (2) The first real *measurement* then found 7 phantom sites and
  2 invented rule ids from a documentation file — the fixtures would have
  stayed green forever. (3) *Self-review* found the `--as-baseline` skeleton
  advertising itself as rejected while it validated clean. (4) The *deployed
  gate*, run against its own source, twice counted the comment explaining its
  own regex. (5) *Stage-2 code review* found the `nosem` alias — a live,
  undisclosed bypass — and *Stage-3 doubt review* then found the fail-open I
  introduced while fixing Stage-2's performance finding: skipping a file that
  failed to decode **after** its bytes had already matched the token. (6) The
  **F0 suite itself** then went red on this run's own `reviews.json`: Stage-3
  had predicted that tracked append-logs quoting a suppression would false-block
  and I excluded `.jsonl`, but Shipwright's governance artifacts are `.json`
  too, and the review record embeds the very reviewer prose that discussed
  suppression syntax. The reviewer named the class; only running the gate over
  the real tree found its second member.

  *Coverage (breadth)* — 55 rows, every one `tested`; the four blocking classes
  (ratchet / unrecorded / dead / unreadable) and the one advisory class each
  have a control proving they behave as specified, plus a behavioural probe
  against the deployed gate.

  *Integration composition* — `cross_component` did **not** fire (re-confirmed
  against the real diff), so no `category:"integration"` row is owed. The
  dashboard rows nonetheless exercise the real cross-plugin import chain rather
  than a mocked reader.

  *What is NOT claimed.* Three limits are disclosed rather than closed: string
  literals are counted, the bare form is not, and rule ids are matched as
  written rather than as Semgrep resolves them — so the count is per *spelling*,
  not per rule. Closing any of them means re-implementing Semgrep's semantics,
  which is the drift this design was chosen to avoid, so they are recorded in
  the module docstring and in `docs/security-ci-setup.md` instead.

## Verification (medium+)
- **Surface:** cli
- **Runner command:**
  `uv run --extra dev pytest shared/tests/test_inline_suppression_scan.py shared/tests/test_inline_suppressions.py shared/tests/test_inline_suppressions_cli.py shared/tests/test_inline_suppressions_repo_guard.py shared/tests/test_inline_suppressions_prose_pointers.py -v`
- **Evidence path:**
  `.shipwright/runs/iterate-2026-08-05-inline-suppression-ratchet/surface_verification.json`
