# Iterate — Adopted repos: honest evidence, and a remedy that works

- **Run ID:** `iterate-2026-08-05-adopt-derived-evidence-rollout`
- **Intent:** CHANGE
- **Complexity:** medium (Stage-2; `cross_split` — adopt + compliance)
- **Cards:** `trg-66cb695e` (P2.18, supersedes `trg-515060a6`)
- **Spec Impact:** MODIFY — FR-01.10, FR-01.13
- **Decision paper:** `.shipwright/planning/iterate/2026-07-30-derived-snapshots-decision.md`
  (Weg B, delivered for this repo as PR #512)

---

## Why

PR #480 stopped iterate branches from carrying the seven derived compliance
documents, for a measured reason: a branch-local derivation reads the *branch's*
git history and an event log missing every concurrently-merging branch. That was
correct, and it left the committed evidence frozen. PR #512 unfroze it **for this
repository** — the release stages the seven, and `--refresh-pr` opens a
documents-only PR in between.

Card `trg-66cb695e` asks what must be rolled out so adopted (customer) repos get
the same. The answer, measured rather than assumed, is: **nothing** — and that is
the finding that reshapes this iterate.

### What already reaches an adopted repo (verified, not assumed)

| Claim | Evidence |
|---|---|
| The `shared/` tree ships to end users | `scripts/update-marketplace.sh:201-207` syncs it to the cache root; plugins resolve `{plugin_root}/../../shared/`. `refresh_compliance_docs.py` + all four `compliance_*` tools confirmed present in the installed cache |
| `--refresh-pr` ships | `plugins/shipwright-compliance/skills/compliance/SKILL.md` Step 2c |
| The release-time check-in ships | `plugins/shipwright-changelog/skills/changelog/SKILL.md` Step 5.5 |
| An adopted repo can cut a release at all | adopt scaffolds `CHANGELOG-unreleased.d/` (`config_writer.py:245`) and enables the `changelog` phase (`config_writer.py:193`) |
| No customer-side ruleset precondition | `preflight_pr` (`compliance_delivery.py:189`) requires only an `origin`, a default branch, a clean tree, a git identity and `gh` — no monorepo assumption, no bypass actor, no key |

So both halves of Weg B are already installed and already portable. The card's
"roll out the release step and the command" has no work in it.

### What is actually missing

Three gaps, each verified in code.

**G1 — The evidence names nothing, then freezes.**
Adopt's Step F seeds through the *ordinary* producer, `_provenance.py:60`, which
writes `banner_line(SourceState(run_id=data.run_id))` — no `base=`, no
`release=`; those exist only on #512's refresh path
(`compliance_provenance.stamp`). Worse, `run_id` does not resolve either:
`latest_work_event` matches only `type == "work_completed"`
(`collectors/change_history.py:174`), adopt's event is `type: "adopted"`
(`event_seeder.py:68`), and its optional backfill events carry no `adr_id`
(`event_seeder.py:93-102`). The seeded documents therefore render
`Source-State: run=(unknown)` and stay that way, because `restore_derived_to_head`
and `check_no_derived_snapshots_committed` apply unconditionally in adopted repos
too.

**Observed, not inferred (probe, 2026-08-06):** driving `latest_work_event` →
`banner_line` with an adopt-shaped event log (one `adopted` event plus one
backfill `work_completed`) renders exactly `Source-State: run=(unknown)`; with the
fix it renders `Source-State: run=(unknown) base=abc123def456`. So an adopted
repository's evidence today names *nothing* about the state it describes — no run,
no base, no release — and then freezes.

The value needed is already recorded: the `adopted` event carries
`commit_at_adoption` (`event_seeder.py:75`) — the repository's HEAD as onboarding
read it, which is precisely what `base=` means everywhere else in the system.

**G2 — Nobody is told.**
The Step H handoff lists five next steps and mentions neither the refresh cadence,
nor `/shipwright-compliance --refresh-pr`, nor `/shipwright-changelog`. The
generated CLAUDE.md carries one line — "Compliance + dashboard refresh" — which
reads as if the documents stay current. Customers never receive `docs/guide.md`,
where #512 wrote the explanation.

**G3 — The audit reports the problem and points somewhere that cannot fix it.**
Group E compares the **on-disk** document against the **last snapshot commit**
(`audit_staleness.py:12-17`). Its suggestion is `/shipwright-compliance --fix`
(`group_e.py:56-60`), which writes the working tree only (`_apply_fix`). That
clears the case Group E was designed for — a hand-edit, where re-rendering
restores the snapshot's content. It cannot clear the case an adopted repo is in,
where the committed snapshot is genuinely behind: re-rendering moves the on-disk
copy further from the snapshot, and the next audit reports the same finding. Only
a new snapshot commit clears it — a release, or `--refresh-pr`.

G3 is ranked first: an omission leaves someone uninformed, a wrong pointer sends
them in a circle.

### Why the tidy fix for G1 is the wrong one

The obvious move is to teach the ordinary producer to carry `base=`, so every
regeneration everywhere names its base. **Rejected, with evidence.** `base=`
changes with every commit, and the tracked documents are regenerated after every
pipeline phase and at every iterate finalization — so a moving `base=` in the
ordinary producer reintroduces exactly the permanently-dirty churn that
`iterate-2026-05-22-deterministic-render-timestamps` removed. The stamp belongs
only on the paths that *deliver* a fixed point. That is why #512 put it on the
release and on-demand paths, and adoption is the third such path: it is the one
moment an adopted repo's evidence is committed by design.

---

## Scope

Confirmed with the operator on 2026-08-05:

- Fix all three gaps.
- `base=` names **the commit the repository was at when onboarding read it**
  (pre-onboarding HEAD) — literally what the documents were computed from, and
  the same meaning `base=` already carries. Not the adoption commit, which would
  need a stamp-then-amend cycle to name a commit that does not exist yet at
  seeding time.

**Explicitly out of scope**

- Any post-merge producer (Weg A). Rejected by three architecture reviews on
  2026-07-30; not to be designed for, per the card.
- Widening the refresh set — `triage_inbox.md` stays out by the standing operator
  scope pin (`compliance_refresh.EXCLUDED`).
- Any customer-side ruleset, credential or bypass precondition. There is none,
  and this iterate must not introduce one.
- Changing the ordinary producer's banner (see above).

---

## Acceptance Criteria

- **AC-1** — Given a repository being onboarded, when the compliance evidence
  documents are seeded, then each markdown evidence document's `Source-State:`
  line names the commit the repository was at when onboarding read it.
- **AC-2** — Given that commit cannot be established (absent, the literal `HEAD`
  fallback, or a repository with no commits), when the documents are seeded, then
  no commit is named and the rest of the banner is unchanged — never a
  plausible-looking value.
- **AC-3** — Given onboarding is not a release, when the documents are stamped,
  then they claim no release.
- **AC-4** — Given onboarding hands over, then the handover states that the
  committed evidence is refreshed at releases and on demand rather than
  continuously, and names both ways to refresh it.
- **AC-5** — Given a later session reads the generated project guidance
  (`CLAUDE.md`), then it finds that same statement, so the fact outlives the
  handover banner.
- **AC-6** — Given the audit reports an evidence document as no longer matching
  its committed snapshot, then the suggested command names the path that can
  actually produce a new snapshot, alongside the existing local re-render.

---

## Affected Boundaries

- **Provenance banner** (`source_state.banner_line` ⟷ `parse_banner_line`) —
  producer/consumer round-trip; a new writer joins it. `touches_io_boundary`
  expected → Boundary Probe + round-trip test.
- **Event log → compliance provenance** — `adopted` event's `commit_at_adoption`
  becomes an input to a rendered document for the first time.
- **Audit finding text** — consumed by operators and by the WebUI's finding list.

## Spec Impact — MODIFY

FOLD, not MINT: both are existing capabilities being completed.

- **FR-01.10 (/shipwright-compliance)** — append ACs for (a) evidence produced at
  onboarding naming the state it was built from, and (b) a staleness report
  naming a remedy that can clear it.
- **FR-01.13 (/shipwright-adopt)** — append an AC for the handover stating the
  refresh cadence and how to refresh.

## Confidence Calibration

- **Boundaries touched:**
  - The provenance banner (`banner_line` ⟷ `parse_banner_line`) — a third writer
    joined the producer side.
  - Event log → rendered evidence: the `adopted` event's `commit_at_adoption`
    reaches a document for the first time.
  - Audit finding text → `audit_report` rendering (and the WebUI finding list).
  - `refresh_compliance_docs.py` CLI surface — a fifth mode.

- **Empirical probes run** (each one answered a question the code did not):
  1. *Does the shared tree actually reach end users?* — read
     `update-marketplace.sh:201-207` and listed the installed cache. **Yes**; all
     of #512's tools are physically present. This is what collapsed the card's
     "roll out the release step and the command" to zero work.
  2. *What does an adopted repo's banner actually say?* — drove
     `latest_work_event` → `banner_line` with an adopt-shaped event log.
     **`Source-State: run=(unknown)`**; with the fix, `run=(unknown) base=…`.
     Inference until this was run.
  3. *Does `stamp_fixed_point(release=None)` remove a stale `release=`?* — **yes**,
     it rewrites the whole banner line. Answered a review finding with evidence
     rather than argument.
  4. *What does it do with a banner-less document?* — **silently skips it and
     omits it from its return value.** Nobody asked this; it produced the
     `partial` status and the validate-before-write ordering.
  5. *Is `refresh_compliance_docs.py` bloat-baselined?* — **no** (188 entries,
     not among them). Falsified my own stated reason for a separate module.
  6. *`safe_commit` behaviour on `HEAD` / `not-a-sha` / abbreviations* — rejects
     the first two, accepts 7-40 hex. Fixed the shape of the three-way resolver.
  7. *Is Step H drivable by code?* — **no, it is agent prose.** Cut the
     integration-test scope and stopped a harness that would have re-implemented
     the prose and proven nothing.
  8. *Does adopt stage anything, anywhere?* — **no.** `git add` appears nowhere in
     the skill, its references or its scripts. Pre-existing and harmless until a
     stamp entered the flow: the stamp writes the worktree and `git commit`
     records the index, so unstated staging order decides whether the stamp ships.
     Found by the Stage-1 reviewer, confirmed by grep, fixed in Step H.

- **Test Completeness Ledger:** see `iterate_latest.test_completeness` in
  `shipwright_test_results.json` (F5) and the F5c entry. Every behaviour below is
  `tested`; **zero** testable-but-untested.

| # | Behaviour | Status | Evidence |
|---|---|---|---|
| 1 | Supplied base reaches every markdown document's banner | tested | `test_stamps_every_markdown_member_with_the_supplied_base` |
| 2 | An existing run id survives stamping | tested | `test_the_run_id_already_in_the_banner_survives` |
| 3 | An abbreviated base is **refused**, because git resolves a short id as a *ref* first and would stamp a real-but-wrong commit | tested | `test_an_abbreviated_base_is_refused_rather_than_resolved` |
| 3b | A padded base is still accepted (validate the trimmed value, send the trimmed value) | tested | `test_a_padded_base_is_still_accepted` |
| 4 | A stale `release=` is removed, not inherited | tested | `test_a_stale_release_claim_is_removed_not_merely_left_alone` |
| 5 | Absent / literal `HEAD` / malformed / non-resolving base → `no_base`, nothing written | tested | `test_no_base_is_claimed_when_it_cannot_be_established` (4 params) |
| 6 | This mode never resolves `HEAD` | tested | `test_head_is_never_resolved_by_this_mode` — spies **both** module objects; asserts no HEAD-ish **substring** in any argument *and* that git is not reached at all, so neither half passes vacuously |
| 7 | A **present** banner-less document → `partial`, non-zero exit, tree untouched | tested | `test_a_bannerless_document_aborts_without_touching_the_tree` |
| 8 | An **incomplete** set → `incomplete_set`, non-zero, **whether or not a base resolves** — its own status, so absence is never described as an unstampable banner | tested | `test_an_incomplete_set_stops_the_adoption_either_way` (2 params: with and without a resolvable base — the second was the actual hole) |
| 9 | Nothing to stamp at all → `no_documents`, non-zero (no green-on-vacuum) — checked **before** the base, so a commitless repo whose Step F also produced nothing cannot exit 0 | tested | `test_nothing_to_stamp_at_all_is_reported_rather_than_passing` |
| 9b | A write that fails mid-set puts the originals back (`write_back` has no rollback) | tested | `test_a_failed_write_puts_the_originals_back` |
| 10 | Stamped set is exactly the `.md` half of `REFRESH_SET` | tested | `test_the_stamped_set_is_exactly_the_markdown_half_of_the_refresh_set` |
| 11 | What is written parses back (boundary round-trip) | tested | `test_what_is_written_parses_back_to_what_was_meant` |
| 12 | **integration** — the adoption *commit* carries the stamp | tested | `test_the_adoption_commit_carries_the_stamp` (reads blobs out of the commit, plus an independent `git show` check) |
| 13 | **integration** — a writer between stamp and commit is caught **and repaired** by the one permitted amend → re-verify, **and the amend overlays rather than replaces** (unrelated paths survive) | tested | `test_a_writer_between_stamp_and_commit_is_caught` |
| 14 | **integration** — a commitless repository still onboards, **and `--verify-commit` genuinely rejects a base-less commit** (what makes Step H's skip load-bearing rather than dead prose) | tested | `test_a_repository_with_no_commits_can_still_be_onboarded` |
| 15 | **integration** — the Group E remedy's first step reaches a clean tree | tested | `test_the_group_e_remedy_reaches_a_clean_tree` — with the `preflight_pr` substitution **declared** in the docstring |
| 16 | **integration** — `--restore` restores the evidence *and* preserves unrelated staged work | tested | `test_restore_does_not_clear_unrelated_work` — asserts exit code, restored content, and that the unrelated file still exists and is still staged |
| 17 | Group E suggests a remedy that can clear the finding, on one line | tested | `test_suggestion_names_a_path_that_can_actually_clear_the_finding` |
| 17b | …and names **only flags `/shipwright-compliance` actually accepts** — checked against the SKILL, so a remedy telling the operator to type a non-existent command fails | tested | `test_suggestion_names_only_flags_the_skill_actually_accepts` |
| 18 | Handover names both refresh paths | tested | `test_handoff_names_both_ways_to_refresh_the_evidence` |
| 19 | Handover says the evidence is **not** continuously refreshed | tested | `test_handoff_says_the_evidence_does_not_stay_current` — matches `not\s+continuously` adjacently, so an inverted banner fails |
| 20 | Step H orders stamp → **commit** → verify | tested | `test_step_h_stamps_before_committing_and_verifies_after` — anchors on the step **headings**, since both flags are also cross-referenced in prose and `index()` on a flag finds a mention |
| 21 | Step H stages **after** stamping | tested | `test_step_h_stages_after_stamping` |
| 22 | Step H distinguishes `no_base` (continue) from `partial` (stop) | tested | `test_step_h_distinguishes_no_base_from_partial` |
| 23 | The generated CLAUDE.md carries the same statement **including the cadence** (`not continuously`), not merely the two commands | tested | `test_generated_claude_md_carries_the_same_statement` |

- **Confidence-pattern check:**
  - **Asymptote (depth):** the deepest failure mode here is "reported stamped,
    shipped unstamped". It is covered at three depths — the mode's own return
    value (#7), the commit's blobs (#10), and an adversarial writer between the
    two (#11). #11 is the one that would actually catch a regression; the other
    two pass in its absence.
  - **Coverage (breadth):** all six ACs map to at least one row. AC-2's four ways
    of failing are parametrised rather than represented by one example, because
    the R3 finding was precisely that one of the four had been treated differently
    from the others.
  - **Integration composition:** `cross_component` does **not** fire — no hooks,
    merge/churn resolver, phase validator or campaign-drain path is touched. The
    four integration rows exist because the *ordering* claim is not provable
    in-process, not because the flag demanded them.
  - **Known limit, stated rather than papered over:** Step H is agent-driven
    prose, so nothing mechanically proves the agent stamps before committing.
    Rows 20-22 pin the *instructions*; rows 12-14 pin the *tool chain* they
    invoke. A driven end-to-end adoption would need Step H to become code — a
    larger change than this one, and not obviously desirable.
  - **Second known limit — the Stage-3 doubt pass did not run.** It was spawned
    and was terminated mid-run by the account's monthly spend limit. Not
    substituted by a self-pass, because the party who wrote the code is the one
    that cannot supply adversarial fresh context. Sized rather than hand-waved:
    the external code review ran on a separate billing path and returned the one
    medium finding *both* internal stages had missed (`no_base` bypassing the
    completeness gate) — the exact class Stage 3 hunts. Five passes ran; the
    residual risk is real and bounded. Full disposition in the review record.
