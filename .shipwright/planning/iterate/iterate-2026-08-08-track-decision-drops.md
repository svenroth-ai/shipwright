# Iterate Spec: track-decision-drops

- **Run ID:** iterate-2026-08-08-track-decision-drops
- **Type:** change
- **Complexity:** medium (Stage 1 keyword estimate was `small`, confidence
  0.6; overridden up to `medium` on Repo-Scout-equivalent evidence: this
  touches `touches_io_boundary` — the write_decision_drop.py/aggregate_decisions.py
  JSON producer/consumer boundary is being redesigned — plus multiple
  verifiers, an SSoT meta-test, and mandated doc updates across
  hooks-and-pipeline.md's two matrices. See mini-plan for the full trace.)
- **Status:** draft

## Goal

`.shipwright/agent_docs/decision-drops/` — the per-run ADR staging directory
iterate F3 writes and `/shipwright-changelog` folds at release — is
gitignored. 214 real decision drops (measured 2026-08-08) exist only on the
operator's one machine; `decision_log.md` was last folded 2026-07-20. At the
current ~10-week release cadence, ten weeks of architectural decisions are
absent from CI, from every second checkout, and are lost with the disk.

Track the directory (except the local `INDEX.md` render) so each decision
drop becomes durable at PR-merge time — not deferred to the next release —
and do this in all three places a decision-drop-producing project can exist:
this repo, the shared onboarding template every `/shipwright-adopt`d project
receives, and the separate `shipwright-webui` repo. A `.gitignore`-only
change does not achieve this: today's write path deliberately writes the
drop file directly onto the **main checkout's disk** (bypassing the calling
iterate's own worktree) specifically because a gitignored file written into
an ephemeral worktree would be destroyed by `git worktree remove`. Once
tracked, that redirect stops being a durability mechanism and starts being
the bug — an untracked file lands on main with nothing to commit it. This
run redirects the write into the iterate's own worktree so F6 stages it and
it ships in that iterate's own CI-gated PR, matching the established
per-tree/PR-committed model this codebase already uses for
`shipwright_events.jsonl`, `reviews.json`, `ci_supplychain_ack.json`, and
campaign `status.json`.

**This run supersedes ADR-050** (2026-05-19), which rejected tracking this
directory citing merge churn. The reasoning for `INDEX.md` staying local
(the source of that churn) is preserved; only the JSON payload's durability
changes, and the ~10-week cadence that makes deferred aggregation too slow
is new evidence ADR-050 didn't have.

**This run also revises a load-bearing premise of ADR-127** (PR #596,
merged 2026-08-07 — the day before this run), which built
`lib/decision_drops_index.py` explicitly on "this directory is permanently
gitignored." That premise is corrected here, not silently invalidated.

## Scope: this run is PR 1 of 2 (internal Opus review finding)

**This run (PR 1):** the gitignore change (3+1 locations), the write-path
redesign, verifier/SSoT-test updates, F3/F6/changelog doc updates, and
Layer-1 context loading. No data files move.

**PR 2 (explicit follow-up, NOT this run):** the one-time backfill of the
214 existing drops from the main checkout into git, after a gitleaks +
prompt-scan pass (they are 10 weeks of never-scanned agent-authored free
text going into a public repo) and after measuring the Group-F compliance
audit / `test_architecture_md_reflects_arch_impact.py` against them. Reasons
for the split: a 214-file data PR mixed with a code change risks pr-review
truncation on a Tier3a-sensitive diff (where `--skip-pr-review` is ignored),
and PR 1's own gitignore relaxation is a prerequisite for PR 2's files being
addable at all. Filed as a triage follow-up at F12.

## Acceptance Criteria

- [x] `.gitignore:172` ignores only `decision-drops/INDEX.md` and
      `decision-drops/*.tmp`, not the directory.
- [x] `shared/templates/shipwright-gitignore.template:45` — same rule, so
      every `/shipwright-adopt`ed project receives the corrected default.
- [x] `plugins/shipwright-adopt/scripts/lib/gitignore_check.py` — verified
      (not changed): it's a generic `git check-ignore` classifier with no
      hardcoded decision-drops assumption.
- [x] `write_decision_drop.drop_dir()` resolves against `project_root`
      directly (no `resolve_main_repo_root`) — writes into the calling
      iterate's own worktree.
- [x] `lib/decision_drops_index.py`'s `drop_dir()` — same change, kept in
      lock-step with the producer; docstring rewritten (no longer "never
      committed").
- [x] `aggregate_decisions.drop_dir()` — same change; "deliberate asymmetry"
      docstring rewritten (the asymmetry no longer exists).
- [x] F11 verifier (`verifiers/iterate_checks.py`, the check resolving
      `main_root` to find the CURRENT run's own drop) — same change.
- [x] `test_decision_drop_ssot.py` gains a `_WORKTREE_LOCAL` registry
      (forward/coverage/reverse triad) asserting these files must NOT
      resolve against main root — inverted, not deleted, so a future
      regression that reintroduces a main-root write still fails red.
      Coverage scan widened repo-wide mid-run after it missed a real site
      (see Re-verification section) — 7 registry entries, not the
      originally-scouted handful.
- [x] `references/F6.md`'s NOTE (do NOT stage F3 decision-drops) replaced
      with a real `git add` line + rationale blockquote, matching the style
      of the four existing per-tree-artifact blockquotes in that file.
- [x] `agents/sub-iterate-runner.md`'s F6 bullet updated to match. (No
      separate `references/F3.md` file exists in this skill version — F3's
      write-path behavior is governed by `write_decision_drop.py` itself,
      not a prose F3 reference doc; nothing there to update.)
- [x] `/shipwright-changelog` Step 6 (`plugins/shipwright-changelog/skills/changelog/SKILL.md`)
      stages the release-time deletions `aggregate_decisions()` makes on
      disk (`git add -A` on the decision-drops dir, staged after
      `aggregate_decisions.py` runs) — else the next release re-folds the
      same drops under new ADR numbers.
- [x] `references/context-loading.md` Layer-1 item 4a reads pending
      `decision-drops/*.json` (bounded: 20 most recent, one line each, via
      the new `render_recent_drops_summary`) alongside `decision_log.md`.
- [x] `docs/hooks-and-pipeline.md` — both matrices updated: Artifact Write
      Matrix gained a dedicated `decision-drops/*.json` row and had the
      `INDEX.md` row's "gitignored main-repo path" claim corrected; Artifact
      Read Matrix gained a `decision-drops/*.json` row (iterate B2, bounded
      20 most recent); the Churn-artifact table's stale "gitignored... same
      shared main-repo directory" reasoning corrected in place.
- [x] `docs/guide.md` — the artifacts table's `decision-drops/<run_id>.json`
      row corrected (was "gitignored, main-repo path").
      `shared/glossary.md` — the Decision-Drop term entry corrected (kept
      the glossary's own 540-LOC hard cap by trimming elsewhere in the same
      entry). `.shipwright/agent_docs/architecture.md` — checked: its one
      stale mention is inside a dated historical changelog bullet (ADR-127's
      own 2026-08-07 entry), correctly left as a historical record rather
      than rewritten — this run's own entry (written at F3) supersedes it in
      the same way ADR-127's note below supersedes ADR-050's premise.
- [x] `.shipwright/planning/adr/127-decision-log-drops-index.md` gets a note
      (not a rewrite) that its "permanently gitignored" premise was revised.
- [x] Additional consumers verified/dispositioned (not silently assumed
      unchanged) — **7, not the originally-scouted 5**, and one named item
      turned out not to exist: `verifiers/decision_log_gate.py` comment
      (fixed), `lib/churn_merge.py`'s premise comment (fixed),
      `lib/section_file_list.py`'s `FRAMEWORK_BOOKKEEPING` (checked, no
      change needed — it classifies framework ownership independent of git
      status), `verifiers/common.py` (checked — grep found no
      `_MAIN_REPO_ONLY` constant there at all; it lives in
      `phase_quality/_run_id.py` for the unrelated events-log SSoT, and
      `common.py`'s own decision-drops handling never had a main-root
      redirect to begin with), plus three found only by re-verifying rather
      than trusting the scout: `plugins/shipwright-compliance/scripts/audit/group_f.py`
      (F5 arch-drift detective — real bug, fixed),
      `test_architecture_md_reflects_arch_impact.py` (a test file, invisible
      to the coverage scan's own test-file exclusion — fixed, and a new
      hermetic worktree test added), and
      `test_gitignore_canon_merge.py::test_empirical_round_trip_fresh_repo`
      (asserted the pre-run behavior empirically — fixed).
- [x] `shipwright-webui` repo: same gitignore rule fix — reachable locally,
      applied, plus a doc-comment correction in that repo's
      `decision-drops.ts` reader (behavior unchanged) recording the
      resulting visibility-timing consequence for its "Decisions" panel.
      Left uncommitted (separate repo/remote — operator's call).
- [x] This run's own ADR explicitly supersedes ADR-050 by number —
      `.shipwright/planning/adr/128-track-decision-drops.md`, decision-drop
      `iterate-2026-08-08-track-decision-drops_001.json` (F3).
- [x] Abandoned-run regression (a drop on an unmerged, later-deleted branch
      is now lost, vs. today's harmless main-disk clutter that still gets
      folded) recorded as an accepted consequence: mini-plan addendum item
      9, Self-Review item 4, and Test Completeness Ledger row 12/13.

## Spec Impact

- **Classification:** none
- **NONE justification:** framework-internal developer tooling (durability
  of the framework's own architectural-decision staging mechanism), not a
  product-facing functional requirement — identical justification to
  ADR-127's own Spec Impact section, which this run extends.

## Out of Scope

- The 214-file backfill itself (PR 2, named above).
- Rebuilding the campaign lineage-scoping code
  (`architecture_doc.records_in_run_set`) — now largely redundant but
  harmless; removing it is a separate cleanup.
- Any change to the Group-F compliance detective's reconciliation logic
  itself — only its input (a real, tracked directory instead of a
  gitignored one) changes.
- Building a drop-recovery sweep for abandoned branches (named as a future
  escape hatch, not built speculatively).

## Design Notes

n/a — no UI surface; Python library/CLI/doc/config change.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `write_decision_drop.py` (iterate F3, now worktree-local) | `aggregate_decisions.py` (release-time, reads the merged main checkout) | JSON (`decision_drop.schema.json`) |
| `write_decision_drop.py` | `lib/decision_drops_index.py` (local `INDEX.md` render) | JSON → Markdown |
| `/shipwright-changelog` Step 6 (deletion commit) | any subsequent checkout / CI | git tree state |

`touches_io_boundary` fires (the JSON producer/consumer pair's resolution
strategy is being redesigned) — Boundary Probe run below.

## Confidence Calibration

- **Boundaries touched:** the three rows above, plus every downstream
  consumer of `drop_dir()`'s resolution (F11 verifier, SSoT test, Group-F
  compliance audit, the architecture-doc drift test).
- **Empirical probes run:**
  - Counted the real drop backlog on the live main checkout: 214 `*.json`
    files (not the brief's slightly-stale 202), confirming the durability
    problem is real and current, not hypothetical.
  - Confirmed `decision_log.md`'s last entry is dated 2026-07-20 (ADR-328),
    matching the brief's claim.
  - Traced `aggregate_decisions.aggregate()`'s actual deletion behavior
    (unlinks folded drops) against `/shipwright-changelog` Step 6's commit
    pathspec and found the deletions are never staged today — harmless only
    because the directory is currently gitignored; this is what would cause
    duplicate-ADR corruption at the next release if left unfixed while
    tracking the directory (internal Opus review, finding 1).
  - Read `test_decision_drop_ssot.py` in full and confirmed it currently
    hard-requires (not just permits) `resolve_main_repo_root` in the two
    producer/verifier files — a silent relaxation would discard the
    protection that exists because "every iterate ADR since ADR-049 was
    silently lost" (the test's own docstring).
  - Resolved the apparent campaign-mode contradiction by reading
    `sub-iterate-runner.md:11` and `check_iterate_isolation.py` together:
    "no worktree" for a sub-iterate means no *additional* per-sub-iterate
    worktree — the campaign orchestrator already runs inside one
    `.worktrees/<slug>`, and sub-iterates branch-hop within it. `project_root`
    for a sub-iterate is that shared worktree, never main, so the redesign
    holds there unchanged.
  - Grepped for every `decision-drops` / `DROP_DIRNAME` reference across
    `shared/scripts`, `plugins/*/skills`, `docs/`, and `.shipwright/planning/`
    to build the consumer list in the Acceptance Criteria above, rather than
    trusting the brief's three named locations.
- **Test Completeness Ledger** (reconciled against actual Build output):

  | # | Testable behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | `.gitignore` ignores `decision-drops/INDEX.md` and `*.tmp`, not the dir | tested | `test_gitignore_canon_merge.py::test_empirical_round_trip_fresh_repo` — real `git check-ignore` against the actual template: `d.json` not ignored, `INDEX.md`/`d.json.abc123.tmp` ignored |
  | 2 | `write_decision_drop.drop_dir()` resolves to `project_root` (no main-root jump) from inside a real worktree | tested | `test_write_decision_drop.py::test_drop_dir_plain_repo_is_repo_local`, `::test_drop_written_from_worktree_lands_in_the_worktree` |
  | 3 | `decision_drops_index.drop_dir()` — same | tested | exercised via `test_decision_drops_index_producers.py` (CLI + rebuild against `drop_dir(tmp_path)`); resolution itself pinned by SSoT row 6 |
  | 4 | `aggregate_decisions.drop_dir()` — same | tested | `test_aggregate_decisions.py::test_drop_dir_resolves_the_calling_checkout_not_main` |
  | 5 | F11 verifier (`check_architecture_documented`) finds the current run's own drop in ITS worktree, not main's | tested | `test_verify_iterate_finalization.py::test_architecture_documented_reads_the_worktrees_own_drop_not_main` — new: a decoy drop+doc entry in main for a different run_id does NOT satisfy this run's gate; documenting in the worktree's own architecture.md does |
  | 6 | `_WORKTREE_LOCAL` SSoT registry: forward — no registered file calls `resolve_main_repo_root` for decision-drops | tested | `test_decision_drop_ssot.py::test_decision_drop_sites_do_not_redirect_to_main_root` |
  | 7 | `_WORKTREE_LOCAL` SSoT registry: coverage — no unaccounted raw join anywhere in the REPO (widened from `shared/scripts`-only after it missed `group_f.py` — see Re-verification section) | tested | `test_decision_drop_ssot.py::test_no_unaccounted_decision_drop_site_redirects_to_main_root` |
  | 8 | `_WORKTREE_LOCAL` SSoT registry: reverse — every entry still builds a raw join | tested | `test_decision_drop_ssot.py::test_registry_not_stale` |
  | 9 | `/shipwright-changelog` Step 6 stages the release-time drop-file deletions | tested (existing coverage, not new) | `test_decision_drops_index_producers.py::test_aggregate_folding_a_drop_refreshes_the_drops_index_to_empty` proves `aggregate()` deletes on disk; the Step 6 `git add -A` staging itself is a doc/skill-prose change with no Python surface to unit-test — verified by reading the SKILL.md diff, not executed |
  | 10 | Layer-1 context-loading read is bounded (20 most recent, one line each) | tested | `test_decision_drops_index.py::test_recent_summary_bounds_to_the_limit_most_recent`, `::test_recent_summary_empty_when_no_drops` |
  | 11 | A decision-drop written in one worktree does not appear in a sibling worktree | tested | `test_write_decision_drop.py::test_sibling_worktrees_do_not_share_pending_drops` |
  | 12 | An uncommitted drop is lost when its worktree is removed (accepted tradeoff, not silently introduced) | tested | `test_write_decision_drop.py::test_uncommitted_drop_is_lost_with_the_worktree` |
  | 13 | A committed-then-merged drop survives worktree removal and is aggregated (the real durability round-trip: producer → worktree file → commit → merge → consumer) | tested | `test_write_decision_drop.py::test_committed_drop_survives_worktree_removal_and_is_aggregated` — this is the Affected-Boundaries round-trip probe (Self-Review item 7) |
  | 14 | Group-F `F5` arch-drift detective resolves decision-drops against `project_root`, not main (the 6th consumer found during re-verification, outside the original scout) | tested (existing coverage sufficient) | `test_audit_groups_c_f.py::TestF5ArchDrift` — plain-`tmp_path` tests already exercise the corrected resolution identically to before, since the old `resolve_main_repo_root(tmp_path)` on a non-git dir already fell back to `project_root` |
  | 15 | `test_architecture_md_reflects_arch_impact.py`'s own drift-oracle resolves against `project_root` (the 7th consumer — a test file itself, outside the SSoT coverage scan's file-exclusion) | tested | `test_discovery_sanity_skips_when_dir_absent`, `::skips_when_present_but_empty`, `::ok_when_present_with_nonarch_drop` plus the two live-repo tests skip cleanly against this worktree's actual (empty) drops dir |

  Rows 16-24 added post-Stage-3 (doubt-reviewer findings, disposition detail
  in the Review Cascade section above):

  | # | Testable behavior | Disposition | Evidence |
  |---|---|---|---|
  | 16 | An already-adopted project's stale blanket `decision-drops/` ignore rule is RETRACTED (not just left alone) on next self-heal, and the replacement narrow rules are added in the same pass | tested | `test_gitignore_canon_retraction.py` (6 tests); `test_gitignore_selfheal.py::test_self_heal_retracts_superseded_decision_drops_rule` — empirically confirms a decision-drop JSON becomes trackable while INDEX.md stays ignored |
  | 17 | Retraction never touches a hand-written line outside the target's own managed marker block | tested | `test_gitignore_canon_retraction.py::test_merge_does_not_retract_a_rule_outside_the_managed_block` |
  | 18 | F11 fails when a decision-drop is present in the working tree but absent from this iterate's own commit(s) (multi-commit/merge-commit aware, not a single `git show`) | tested | `test_decision_log_gate.py::test_decision_drop_committed_fails_when_drop_is_unstaged`, `::test_decision_drop_committed_passes_when_drop_landed_in_an_earlier_commit` (real bare-origin + branch fixture) |
  | 19 | F11 SKIPs (not fails) when the directory is still gitignored in a project that hasn't self-healed yet | tested | `test_decision_log_gate.py::test_decision_drop_committed_skips_when_directory_gitignored` |
  | 20 | A drop whose file mtime predates the tracking cutoff is quarantined (moved, never deleted), not aggregated; freshness reads mtime, not the JSON `date` field | tested | `test_decision_drop_legacy.py` (13 tests, incl. `test_is_legacy_drop_ignores_narrative_date_field` — the exact case that broke my first mtime-vs-date-field design attempt against the pre-existing `test_authoring_date_preserved`); `test_aggregate_decisions.py::test_legacy_drop_quarantined_not_aggregated`, `::test_mixed_fresh_and_legacy_batch` |
  | 21 | Quarantine is report-only under `--dry-run` (no file actually moved) | tested | `test_aggregate_decisions.py::test_legacy_drop_dry_run_reports_without_moving` |
  | 22 | F6's decision-drop staging is glob-scoped to `{run_id}_*.json`, not the whole directory — an unrelated sibling run's leftover drop in a shared campaign worktree survives untouched | tested | `test_write_decision_drop.py::test_f6_decision_drop_add_is_glob_scoped_to_run_id` (drift guard reading F6.md itself), `::test_unrelated_sibling_drop_survives_run_id_scoped_staging` |
  | 23 | `verifiers/common.py`'s two raw decision-drop joins (C1/C4 iterate fallbacks) are registered in the SSoT registry and pass all three registry tests | tested | `test_decision_drop_ssot.py` (all 3 tests re-run with `common.py` added) |
  | 24 | The `.gitignore`/template congruence test still passes with the new quarantine-dir rule added to both | tested | `test_gitignore_template_congruent.py::test_template_and_framework_block_are_congruent` |

  0 untested-testable rows.

- **Confidence-pattern check:** asymptote (depth) — yes: the "does tracking
  even require redesigning the write path?" question surfaced the actual
  correctness break (duplicate-ADR-at-release, F6 actively forbidding the
  stage) that a shallow `.gitignore` edit would have shipped silently.
  Coverage (breadth): the internal Opus review's own file-by-file grep
  surfaced 5 consumers this iterate's own scout had not found; folded into
  the Acceptance Criteria above rather than left as review-only notes.

## Verification (medium+)

- **Surface:** none
- **Justification:** pure Python library/CLI/config/doc change with no
  HTTP, browser, or CLI-user-facing surface of its own — `shared/tests/`
  is the executable surface and is exercised directly via the Test
  Completeness Ledger above, not through F0.5's E2E runner.

## Architecture Review

- **Brief:** `.shipwright/planning/iterate/iterate-2026-08-08-track-decision-drops/architecture_brief.md`
- **Verdicts:** deepseek=approve · openai=revise (not a `reject` from either —
  proceeded per skill, finding integrated below)
- **Smallest thing that would do (per reviewers):** both name option 2
  (redirect the write into the worktree, track everything but `INDEX.md`)
  as the smallest correct mechanism. deepseek: "no findings." openai:
  smaller still — ship the tracked worktree-local artifact lifecycle only;
  defer the Layer-1 context-loading addition.
- **Findings:**
  - openai (medium, simpler-alternative): the new Layer-1 reader is a
    separate standing context-injection mechanism, not required to make
    drops durable/CI-visible, and its "20 most recent" policy becomes a
    permanent retrieval/context-budget contract. Suggests deferring it until
    there's evidence agents can't otherwise consult the tracked directory.
    **Rejected, with reason recorded** — same shape as ADR-127's own
    reconciliation of an analogous proportionality objection: this item was
    named explicitly by the operator in the run's own opening brief
    ("tracking the folder fixes durability but not the ten-week blind spot
    in what agents actually see"), as a stated second half of the problem,
    not a self-initiated addition made during design. The proportionality
    concern is valid in the abstract and is recorded rather than dismissed,
    but overriding an explicit, scoped operator instruction is not this
    review's role. The design already bounds the cost the finding is
    concerned about (20 most recent, one line each, reusing the existing
    render shape) rather than an unbounded read.
  - deepseek: no findings; approved as proposed, citing the same per-tree
    artifact precedent (`shipwright_events.jsonl`, `reviews.json`) the plan
    itself cites.
- **Reconciliation:** proceeded with the write-path redesign and the bounded
  Layer-1 reader as designed. Both reviewers independently converged on
  option 2 over options 1/3/4 in the brief — option 1 (gitignore-only) was
  not defended by either, corroborating the internal Opus review's verdict
  that a shallow flip does not fix the problem.

## Re-verification: worktree/main-root resolution + sweep behavior

Per the run's explicit instruction to *re-verify*, not re-confirm, both items
the tracking change inverts:

- **`test_decision_drop_ssot.py`** rewritten (not just re-run): the pre-run
  invariant — every worktree-reachable decision-drop site MUST redirect via
  `resolve_main_repo_root` — is now the opposite: NONE may. Registry
  (`_WORKTREE_LOCAL`) covers all 6 real producer/consumer sites.
- **Coverage scope widened repo-wide.** The original coverage test only
  scanned `shared/scripts`. Running it as designed would have missed a real
  regression: `plugins/shipwright-compliance/scripts/audit/group_f.py` (the
  F5 arch-drift detective) still resolved `drops_dir` via
  `resolve_main_repo_root`, undetected by the earlier consumer sweep because
  it lives outside `shared/scripts`. Found by re-deriving the coverage scan
  rather than trusting the existing scope, fixed (drops_dir now resolves
  directly against `project_root`), and the coverage test itself widened to
  scan the whole repo so a future plugin-side regression can't hide in the
  same blind spot again.
- **`git worktree remove` sweep:** an uncommitted decision-drop is now LOST
  when the worktree is torn down (`test_uncommitted_drop_is_lost_with_the_worktree`)
  — the opposite of the pre-run guarantee, and an accepted tradeoff (mini-plan
  addendum item 9): durability now comes from being committed (F6) before
  removal, not from redirecting the write off the worktree's disk. A
  committed-then-merged drop survives via git history
  (`test_committed_drop_survives_worktree_removal_and_is_aggregated`).
- **`git add -A` sweep:** confirmed empirically, not assumed —
  `test_gitignore_canon_merge.py::test_empirical_round_trip_fresh_repo` now
  proves via real `git check-ignore` against the actual template that
  `decision-drops/*.json` is untracked-but-not-ignored (so `git add -A .../decision-drops/`
  picks it up) while `INDEX.md` and its atomic-write `*.tmp` siblings stay
  ignored (confirmed against `atomic_write.py`'s actual `mkstemp` naming, not
  assumed) — a stray temp file from a crashed write can never appear as
  untracked clutter for an unrelated broad `git add -A` to sweep. Checked
  `lib/derived_snapshots.py`'s `DERIVED_SNAPSHOTS`/`CHURN_ALLOWLIST`
  registries: neither decision-drops nor its JSON payloads are members, so
  the F11 restore-to-HEAD and churn-merge machinery do not treat them as a
  derived artifact that must never be committed — confirming no conflict
  with the opposite (intentionally-committed) direction this run takes them.

## Bloat-gate remediation (Stop hook, post-Self-Review)

The bloat anti-ratchet Stop hook blocked on two frozen-baseline files this
run's docstring edits grew past their recorded `current`:

- `plugins/shipwright-compliance/scripts/audit/group_f.py` (397 vs. baseline
  395, `state: grandfathered`) — tightened the same three prose blocks the
  redesign touched (no content lost) back to 389 lines, 6 under budget.
- `plugins/shipwright-iterate/agents/sub-iterate-runner.md` (498 vs. baseline
  497, `state: exception`) — rewrapped one line back to 497.
- `shared/tests/test_verify_iterate_finalization.py` (1583 vs. baseline
  1556, `state: exception`, `adr: ADR-093`) — tightened the new worktree
  test first (1572), then bumped `current` to 1572 in
  `shipwright_bloat_baseline.json` in this same commit. This mirrors
  ADR-093's own sanctioned remediation (it bumped two files' `current` for
  the same reason) and ADR-127's identical move for `artifact_migrations.py`
  — a same-commit bump for a cohesive addition to an already-`exception`
  file, not a new exception ADR for 16 lines.

All three re-tested green after trimming; ruff clean repo-wide.

## Cross-repo: shipwright-webui

Applied the mirrored `.gitignore` fix locally at
`C:\01_Development\shipwright-webui\.gitignore` (same INDEX.md/`*.tmp`-only
exclusion, replacing the old blanket `/.shipwright/agent_docs/decision-drops/`
line). Also corrected the now-false "written to the MAIN tree BY DESIGN...
gitignored" header comment in that repo's
`server/src/core/mission-context/decision-drops.ts` — a pure reader, no
behavior change — to document the actual consequence: its "Decisions" panel
will show a pending decision only after the writing iterate's PR merges, not
immediately at F3 time, since a drop no longer lands on the main checkout's
disk from an unmerged worktree. Confirmed no test in that repo asserts the
old timing. **Left uncommitted** — a separate repo/remote/release cycle;
committing and opening its own PR there is the operator's call, not this
run's.

## Self-Review

1. **Spec Compliance — pass.** Every Acceptance Criteria item below is
   checked off or explicitly dispositioned. No feature beyond the goal was
   added; the two extra consumer fixes found during re-verification
   (`group_f.py`, `test_architecture_md_reflects_arch_impact.py`) are the
   same invariant the spec already commits to ("no site may redirect to
   main root"), not new scope.
2. **Error Handling — n/a, justified.** Pure path-resolution and doc/config
   change; no new external-service or user-input boundary. Existing
   validation (500-char field caps, hard reject) untouched.
3. **Security Basics — n/a, justified.** No user input, no secrets, no
   auth surface. The one open security item (214 never-scanned backfill
   files) is explicitly PR 2's job, not this run's.
4. **Test Quality — pass.** All new/rewritten tests assert on outcomes
   (drop file location, git-ignore status via real `git check-ignore`,
   aggregation counts) not internals. Happy path
   (`test_committed_drop_survives_worktree_removal_and_is_aggregated`) and
   accepted-loss path (`test_uncommitted_drop_is_lost_with_the_worktree`)
   both covered.
5. **Performance Basics — n/a.** No loops over unbounded data; the one new
   reader (`render_recent_drops_summary`) is explicitly capped at 20.
6. **Naming & Structure — pass.** `write_decision_drop.py` trimmed back
   under the 300-line guideline after the docstring rewrite;
   `shipwright-changelog/skills/changelog/SKILL.md` sits at exactly 400
   (guideline, non-blocking). No other touched file crossed a size
   guideline.
7. **Affected Boundaries — pass, not n/a.** `touches_io_boundary` fired; a
   real round-trip probe exists:
   `test_committed_drop_survives_worktree_removal_and_is_aggregated` writes
   the drop in a worktree, commits it, merges the branch, removes the
   worktree, then asserts `aggregate()` on the main checkout finds it and
   folds it into `decision_log.md` — producer → file-on-disk → consumer,
   across the actual worktree/merge boundary the redesign changes.
8. **Test Hygiene Probe — pass.** `scan_test_hygiene.py --files` against
   every new/changed test file in this run: `no findings`.

## Review Cascade (model=opus, per this run's brief)

**Stage 1 — spec-reviewer:** REJECT → fix → PASS. First pass flagged
`F6.md`'s new staging bullet for not explaining *why* an unstaged drop is
lost now (durability moved from file location to `git add`, the inverse of
the pre-2026-08-08 model) — fixed by adding the rationale blockquote
documented above under `F6.md`; re-verified PASS.

**Stage 2 — code-reviewer:** verdict **APPROVE WITH NITS** — "the core
resolution change is correct and uniform." Three MEDIUM must-fix-before-merge
findings, now addressed:

1. `decision_drops_index.py`'s `_pending_drops`/`render_recent_drops_summary`
   sorted by filename, not the drop's own `date` field — broke the "20 most
   recent" claim for non-date-prefixed run_ids (campaign `trg-*` sub-iterates).
   **Fixed:** `_pending_drops` now sorts on `(date, filename)`; added
   `test_recent_summary_orders_by_date_not_by_filename` pairing an older
   `trg-*` drop that nonetheless sorts alphabetically *after* a newer
   `iterate-*` one — the old filename-sort would have kept the older `trg-`
   drop as "most recent" and evicted the actually-newer one.
4. `write_decision_drop.py:273-275` carried an obsolete comment
   ("The drop lives next to the MAIN repo...") contradicting this run's own
   fix. **Fixed:** rewritten to state both the drop and `INDEX.md` resolve
   against the calling checkout directly.
7. `test_decision_drop_ssot.py`'s `_prod_py_files()` used
   `sorted(_REPO_ROOT.rglob("*.py"))`, walking `.venv`/`.git`/`.worktrees`
   fully before the exclusion filter ran. **Fixed:** rewritten as `os.walk`
   with in-place `dirnames[:]` pruning, matching the module's own scan-scope
   rationale (repo-wide, but a `.worktrees`-heavy checkout must not pay for
   walking sibling checkouts it will immediately discard).

Follow-ups #2/#3/#5/#6/#8/#9/#10 (NITs, non-blocking) deferred — see
Acceptance Criteria / triage for the one with product consequence (decision
drops aren't gitleaks/prompt-scanned on the write path; filed as triage
`trg-a382b3a2` against the main-repo outbox, not blocking this PR).

**Re-verification (same agent, resumed via SendMessage):** confirmed all
three CLOSED — the date-sort fix is byte-checked against the ISO format
guarantee and the `render_decision_drops_index` row-order blast radius (no
test asserts multi-row order there; producer/renderer byte-equality still
holds); the comment fix removes the contradiction; the `os.walk` pruning is
confirmed topdown+in-place so exclusions never get descended into. Verdict
unchanged: **APPROVE WITH NITS.** Surfaced two more (fixed immediately,
one-liners, no further re-review needed): `dirnames` wasn't sorted (added
`sorted(...)` alongside the prune, for deterministic traversal order across
machines) and the new test's own docstring had the alphabetical-order claim
backwards (corrected). One pre-merge carry-over, unrelated to code
correctness: `.shipwright/agent_docs/decision-drops/` is still empty in this
worktree because F3 hasn't run yet — confirm at F3/F6 that this run's own
drop is actually staged (this PR is the first live exercise of `F6.md`'s new
`git add` line), and stage it before the F6 bloat-baseline refresh.

Re-verified: `shared/tests/test_decision_drop_ssot.py`,
`test_decision_drops_index.py`, `test_write_decision_drop.py` (34 tests) and
the wider decision-drop-adjacent slice of `shared/tests/` (182 passed, 2
skipped) all green; `ruff check` clean on every touched file.

**Stage 3 — doubt-reviewer:** this diff touches cross-plugin imports
(`shared/scripts` consumed by `plugins/shipwright-compliance`,
`plugins/shipwright-changelog`, `plugins/shipwright-iterate`), so it runs
per the cascade's trigger condition (model=opus). Returned 7 findings (3
HIGH, 2 MEDIUM, 2 LOW). Per the cascade's advisory-must-address contract,
every finding was FIXED (none rebutted) — each was concrete, evidenced by
exact file:line, and reproduced a genuine failure scenario:

1. **HIGH — gitignore add-only merge can't retract a stale rule.** Any
   already-adopted downstream project that previously took the blanket
   `/.shipwright/agent_docs/decision-drops/` ignore rule would keep it
   forever (add-only merge never removes anything), silently losing every
   future iterate's ADR (write lands in the worktree, F6's `git add` hits an
   ignored path, `git worktree remove` destroys it). **Fixed:** a second
   marker-delimited SUPERSEDED block in `gitignore_canon.py` /
   `shipwright-gitignore.template` lists retracted rules; `_strip_superseded`
   removes them from a target's own managed block in the same merge pass
   that adds replacements — reusing the EXISTING self-heal pipeline
   (`setup_iterate_worktree.py` → `gitignore_selfheal` → `plan_merge`), so
   zero new wiring is needed for an adopted project to self-heal on its next
   iterate. `shared/tests/test_gitignore_canon_retraction.py` (6 tests) +
   `test_gitignore_selfheal.py::test_self_heal_retracts_superseded_decision_drops_rule`.
2. **HIGH — F11 never checked a decision-drop reached a commit.**
   `check_adr_in_iterate_history`/`_run_drop_files` only look at the working
   tree, so a drop F3 wrote but F6 forgot to `git add` reads exactly like a
   committed one — this run's own F11 pass goes green, then
   `git worktree remove` destroys it with nothing to reconstruct it from.
   **Fixed:** new `check_decision_drop_committed` F11 verifier, mirroring
   `check_events_has_commit`'s tri-state pattern via `_iterate_changed_paths`
   (the full-branch view, not a single `git show`, so a multi-commit iterate
   or a merge commit `ensure_current` left on top isn't misread as "nothing
   changed"). SKIPs when no drop exists, no `--commit` supplied, or the
   directory is still gitignored (legitimate opt-out). 6 new tests in
   `test_decision_log_gate.py`, including a real bare-origin +
   `iterate/<slug>` branch fixture to exercise the multi-commit path (a
   simple linear-history fixture can't — `_branch_base_commit` needs ≥2
   corroborating trunk-name candidates).
3. **HIGH — the 214-file legacy backfill is exposed the moment this PR
   merges.** No longer gitignored, so `/shipwright-changelog`'s existing
   directory-level `git add -A .shipwright/agent_docs/decision-drops/` could
   sweep the pre-tracking backfill into a public commit unscanned before the
   planned PR2 gitleaks/prompt-scan pass runs. **Fixed:** new
   `lib/decision_drop_legacy.py` — `partition_by_freshness`/
   `quarantine_legacy_drops` physically move (never delete) any drop whose
   *file* mtime predates `LEGACY_CUTOFF_DATE` (2026-08-08) into a gitignored
   sibling `decision-drops-legacy-pending-scan/`, wired into
   `aggregate_decisions.aggregate()` before the fold (report-only under
   `--dry-run`), with a loud CLI warning. Freshness reads filesystem mtime,
   NOT the drop's JSON `date` field — an early attempt using the `date` field
   broke the pre-existing `test_authoring_date_preserved` (a backdated
   narrative date for the rendered decision_log.md entry is legitimate and
   orthogonal to whether the file was ever scanned); mtime is the correct
   provenance signal. New `test_decision_drop_legacy.py` (13 tests) + 3 new
   `test_aggregate_decisions.py` cases (quarantined-not-aggregated, dry-run
   reports without moving, mixed fresh+legacy batch). Both `.gitignore` and
   the SSoT template gained the new directory's ignore rule
   (`test_gitignore_template_congruent.py` stays green).
4. **MEDIUM — sub-iterate directory-level `git add` can sweep a sibling's
   leftover drop into the wrong PR.** Unlike every other F6 directory-level
   add, `decision-drops/` is a single FLAT directory shared by every run
   that has touched a worktree; a campaign's sub-iterates branch-hop inside
   ONE shared worktree, so an unrelated/aborted sibling's never-committed
   drop would be swept into this run's own commit, misattributing that
   ADR's origin. **Fixed:** `F6.md`'s staging line narrowed to
   `decision-drops/{run_id}_*.json` (glob-scoped to this run's own files,
   matching `write_decision_drop.py`'s own naming), with a note explaining
   why this one add is scoped while the others correctly stay
   directory-level (they're already run-scoped by directory structure, e.g.
   `planning/iterate/<run_id>/`). New drift-guard test pinning the glob in
   F6.md plus a behavioral regression test proving a sibling run's drop
   survives untouched (`test_write_decision_drop.py`, 2 new tests).
5. **MEDIUM — SSoT registry gap + overclaiming comment.**
   `test_decision_drop_ssot.py`'s `_WORKTREE_LOCAL` registry comment read as
   an exhaustive "every file that builds a decision-drop path" list, but
   `verifiers/common.py`'s two raw joins (C1/C4 iterate-phase fallbacks)
   weren't in it — both already resolve correctly (no main-root redirect),
   so the repo-wide coverage scan (`test_no_unaccounted_...`) already
   protected them structurally, but the registry's own named checks
   (`test_registry_not_stale`, forward-direction) didn't cover them by name,
   and the comment's completeness claim didn't hold. **Fixed:** registered
   `common.py`; rewrote the comment to state the registry is a documented
   named subset, not the sole enforcement, and to make the test-file
   exclusion in `_prod_py_files()` an explicit, reasoned scope decision
   (a stale test asserting removed behavior fails loudly on its own when
   run — not a gap this registry needs to also cover).
6. **LOW — `aggregate_decisions.py`'s "two parallel iterates can never
   claim the same ADR number" guarantee is now undocumented as
   conditional.** It assumes `/shipwright-changelog` always runs against ONE
   shared checkout; since `drop_dir` now resolves directly against
   `project_root` with no main-root redirect, a hypothetical future
   worktree-isolated changelog run would each hold its own
   `decision_log.md.lock`, breaking cross-run serialization. Not a live bug
   (changelog isn't worktree-isolated today, per its own SKILL.md). **Fixed:**
   documented the precondition in the module docstring so a future change to
   changelog's execution model has to reckon with it explicitly.
7. **LOW — two stale "gitignored decision-drops" statements.**
   `plugins/shipwright-compliance/tests/test_f5_event_scope.py`'s docstring
   described a "shared main-rooted decision-drops dir" (the pre-fix
   redirect); `group_f.py`'s F5 comment described the prior oracle's failure
   mode without flagging it as historical. **Fixed:** both rewritten —
   the test docstring now matches `_check_f5`'s own already-updated
   docstring (worktree-local, tracked); the F5 comment now explicitly dates
   the gitignored state to iterate-2026-06-06 and cross-references the
   current tracked state.

All fixes verified: `uvx ruff check .` clean repo-wide; the full new/changed
test slice (decision-drop legacy quarantine, gitignore retraction/self-heal,
F11 commit-membership, SSoT registry, F6 glob-scoping) passes. Not yet
re-verified by the doubt-reviewer agent itself (a second Stage-3 pass was
judged unnecessary — every finding was fixed as specified, not rebutted or
reinterpreted, and each fix carries its own new regression test).

**Post-cascade full-suite regressions (2, both fixed):** a full
`shared/tests/` run (not covered by the targeted slice above) caught two
genuine regressions the targeted testing missed:

- The Stop-hook bloat gate blocked on three files this cascade's own fixes
  grew: `test_aggregate_decisions.py` and `test_write_decision_drop.py`
  freshly crossed 300 lines, and `aggregate_decisions.py` (already
  grandfathered at 303) ratcheted to 311. **Fixed:** split the legacy-
  quarantine integration tests into `test_aggregate_decisions_legacy.py` and
  the F6 glob-scoping tests into `test_f6_decision_drop_staging.py`
  (mirroring the `test_gitignore_canon_retraction.py` split earlier in this
  same run); trimmed `aggregate_decisions.py`'s docstrings back to exactly
  303 lines (its baseline — no ratchet).
- `test_artifact_path_canon.py::test_no_legacy_artifact_paths[planning-migrated]`:
  MEDIUM #4's new F6.md note used a bare `planning/iterate/<run_id>/` instead
  of the canonical `.shipwright/planning/iterate/<run_id>/` every other line
  in that file uses. **Fixed:** added the missing prefix.
- `test_verifiers_dual_mode.py::TestIterateChecksDirOnly::test_adr_check_accepts_strict_local_drop_fallback`:
  a stale monkeypatch of `decision_log_gate.resolve_main_repo_root` —
  removed by this run's own core change, so the attribute no longer exists.
  **Fixed:** rewrote the test to assert the current (and now only) behavior
  directly — a drop written into the worktree's own `decision-drops/` is
  found with no other checkout involved — dropping the obsolete redirect
  simulation entirely.

Both fixed files individually re-verified green
(`test_artifact_path_canon.py`, `test_verifiers_dual_mode.py`); a fresh full
`shared/tests/` run confirmed no further fallout: 8829 passed, 34 skipped,
20 deselected, 0 failed.

## Finalization

### F0 — Fresh Verification Gate

Leak-guard: one false positive (`shipwright_model_config.json`, dirtied by an
unrelated concurrent session building the agent-model-tiers feature in the
main checkout) — amended into `main_tree_snapshot.json`'s
`baseline_amendments` per the established never-delete-another-session's-file
procedure; re-verified `ALLOW (isolated)`. Mirrored merge gates: 3/3 PASS.

Canonical suite runner (`run_test_suite.py`) initially came back RED with 26
failures confined to `test_hooks.py` in `shared/tests` (19) and
`shipwright-build` (7), all `FileNotFoundError: [WinError 2]` from
`subprocess.run(["bash", ...])`. Investigated rather than assumed: a direct
comparison against a pristine `main` checkout with zero diff applied
reproduced the identical 19+7 failures, appearing to confirm a pre-existing,
diff-unrelated environment gap. That conclusion turned out to be an artifact
of *how* the suite was invoked, not a real defect: the failing runs had been
launched through a subprocess chain whose `PATH` lacked `bash`, while the
interactive shell used for the comparison had it. A clean re-invocation of
the exact same canonical command directly from that shell (after clearing an
unrelated stale `.coverage.f0.lock` left by an earlier misfired background
launch — killed the orphaned process tree, confirmed via `Win32_Process`
`CommandLine` inspection that it was this run's own leftover and not the
separate, legitimately concurrent `plan-reviewer-configurable` session) came
back fully **GREEN**: 18/18 units PASS in 6.3 min. Diff-coverage gate: 95%
(threshold 80%), 6 missing lines across defensive branches in
`decision_drop_legacy.py`, `aggregate_decisions.py`, and
`decision_log_gate.py`. No known-failure record needed — F0 closes clean.
