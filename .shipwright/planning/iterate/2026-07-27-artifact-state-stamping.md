# Iterate Spec: artifact-state-stamping

- **Run ID:** iterate-2026-07-27-artifact-state-stamping
- **Type:** feature
- **Complexity:** medium
- **Status:** draft
- **Triage card:** `trg-4d5b6a56` (REQ-3 Phase 2 walk, FR-01.10, severity high)
- **Campaign evidence:** `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`

## Goal

A produced artifact should name **which state of the project it describes**, not
just when it was written. Build that identifier-stamping **once** and use it at
the two producers that lack it — the test-results record and the compliance
evidence documents — so a reader (and, later, a gate) can tell a record
regenerated from the current state from one left over from an older one.

## Why the identifier is the run id (the design decision the card poses)

The card says the shape "should match what the staleness check already resolves".
Read as code:

- `audit_staleness.find_snapshot_commit()` locates its reference snapshot by
  scanning the commit trail for a **`Run-ID:` trailer** (or a `chore(release)`
  subject) and returns that commit's SHA. The *identifier it keys on* is the run
  id; the SHA is what it happens to return.
- A SHA cannot be the stamp anyway: **both producers write before the commit
  exists.** F5b renders the compliance MDs and F6 commits them, so the document
  structurally cannot contain the SHA of the commit that carries it.
- The framework already solved this exact problem once. `build_dashboard.md`
  carries `| Run: {run_id}` precisely because — quoting the F11 verifier
  `check_build_dashboard_has_run_id` — "F5b runs BEFORE the F6 commit and the F7
  event, so the dashboard at F11-verify time structurally cannot contain the new
  commit SHA. F5b therefore embeds the iterate `run_id` … as the deterministic,
  timing-independent marker."

So: **run id is the primary identifier**, matching both the staleness check's key
and the one existing precedent. The commit SHA is carried as a *supplementary*
field where a real HEAD exists at production time (the test-results record),
because there the card's complaint is explicitly about "a leftover record from an
earlier commit" — a code-version binding.

**One more rule, taken from the campaign's own finding.** The ledger's verdict on
the neighbouring criterion was that `mode: standalone` fails because "stamping
that field is instruction, not code. A run that omits it passes as pipeline
results." A stamp the model is *told* to type reproduces that defect exactly.
Every value here is therefore **resolved by code** (git HEAD, the event log) and
never typed into a record by a prompt.

## Acceptance Criteria

- [ ] AC1 — One module owns the identifier's shape: `shared/scripts/source_state.py`
      defines the `SourceState` fields, the markdown banner form, and the JSON
      block form. Neither call site re-defines any of them.
- [ ] AC2 — The test-results record carries the stamp as a top-level
      `source_state` block, written by code that resolves `run_id`, HEAD `commit`
      and `dirty` itself. Every other top-level key (`iterate_latest`,
      `coverage`, the per-layer blocks) is preserved **semantically** — same keys,
      same values, same order; the file is re-serialised with this repo's
      canonical form for it (`json.dumps(indent=2)` + trailing newline, identical
      to `record_coverage_total.py`, the existing isolated writer of this same
      file). *Not* byte-for-byte: a load/dump round-trip cannot promise that, and
      claiming it would be the kind of false-at-the-edge criterion this campaign
      exists to remove.
- [ ] AC3 — All five compliance evidence documents (RTM, test-evidence,
      change-history, SBOM, dashboard) carry a `Source-State:` line naming the run
      whose state they were rendered from, directly under `Generated:`.
- [ ] AC4 — The run id a compliance document reports is resolved from the same
      work event that produced its `Generated:` timestamp, so the two lines
      always describe **one** event rather than two different ones. Enforced
      structurally, not by convention: **one** resolver returns **one** event
      object and both fields are read off it — there are not two independent
      "latest event" queries that could disagree.
- [ ] AC5 — Group E staleness semantics are unchanged: `Source-State:` is
      normalised away in the snapshot byte-compare exactly like `Generated:`, so
      an on-demand `update_compliance.py` regen cannot newly report a document as
      stale. The stamp is disclosure; it does not silently become a gate.
- [ ] AC6 — Both serializations round-trip: what the writer emits is what the
      reader parses back, including the unresolvable case (no git, no events).
- [ ] AC7 — Absent inputs degrade honestly, never fabricate: an unresolvable run
      id renders `run=(unknown)` / serialises `null` rather than inventing a value
      or omitting the field.
- [ ] AC8 — Stamping twice is the same as stamping once (idempotent): the JSON
      block is replaced, never nested; a re-render emits exactly one
      `Source-State:` line.
- [ ] AC9 — A corrupt existing test-results record is **never** overwritten: the
      tool exits non-zero and writes nothing, so an unreadable record cannot be
      silently replaced by a near-empty one carrying only a stamp.

## Resolution contract (total — every source, every failure)

Written out because "degrades honestly" is not a specification. Each row is a
ledger behavior below.

| Source unavailable | `run_id` | `commit` | `dirty` |
|---|---|---|---|
| all present | resolved | 40-hex HEAD | computed |
| `git` binary missing / not a repo / timeout | unchanged | `None` | `None` |
| empty repo (no HEAD yet) / detached | unchanged | `None` (or the detached SHA) | computed |
| no event log / no `work_completed` / event without `adr_id` | `None` → renders `(unknown)` | — | — |
| run id contains a newline or control character | `None` → renders `(unknown)` | — | — |

**`dirty` is defined narrowly**, because the loose reading is useless: it means
*tracked files modified relative to HEAD* (`git status --porcelain
--untracked-files=no`), **excluding the stamped artifact itself**. Without that
exclusion the value is always `true` — the tool runs after the record is written,
so the record's own modification would set it. Untracked files are deliberately
ignored: a scratch file in the tree does not change which code the tests ran
against.

**Values are treated as untrusted single-line tokens.** A run id reaching the
markdown banner is rejected (→ `(unknown)`) if it contains a newline or control
character, so a malformed event cannot forge extra banner lines. `git` is invoked
with an argument array (`shell=False`), a fixed `cwd`, and a bounded timeout.

**No schema to update:** verified there is no JSON schema for
`shipwright_test_results.json` (`shared/schemas/` holds only `decision_drop`,
`run_config.v2`, `triage_item`), so a new top-level key validates nowhere and
breaks nothing.

## Spec Impact

- **Classification:** modify
- **ADD** (new FR appended): none — MINT-vs-FOLD gate (`shared/fr-authoring.md`
  §3) resolves to **FOLD**. "Evidence documents name the state they describe" is
  a guarantee *extending* an existing capability (FR-01.10 already promises
  audit-ready evidence and already promises that a document not matching the
  state it came from is reported as invalid). It is not a new capability, and per
  §2 "a bug fix, polish pass, or 'Phase 2 of …'" belongs on the existing FR.
- **MODIFY** (existing FR changed): **FR-01.10** — one new `(E)` acceptance
  criterion: a produced evidence artifact names the state it describes.
- **REMOVE:** none
- **NONE justification:** n/a

### The AC states only the half this iterate delivers

The campaign's own rule (ledger §"true half of the promise"): state what is true
today, file the missing half. After this iterate the artifacts **carry** the
identifier. Nothing yet **refuses** a mismatched one — the refusal lives on the
sibling cards by design (`trg-12b4cf3f` owns the test-phase validator branch,
`trg-a1fd8125` owns the dashboard/report renderers' disclosure). The new AC is
therefore written as "names the state it describes", not "a stale record is
refused". Writing the stronger sentence now would be the exact false-at-the-edge
criterion this campaign exists to remove.

## Ownership boundary (parallel-safe by construction)

This card was extracted from two others so the mechanism is built **once**.

| Owned here | Explicitly NOT owned here |
|---|---|
| `shared/scripts/source_state.py` (new) | the test-phase validator branch (`trg-12b4cf3f`) |
| `shared/scripts/tools/stamp_test_results.py` (new) | the browser-test result reader (`trg-12b4cf3f`) |
| the `Source-State:` line in the 5 renderers | the "when did the cross-check last run" disclosure (`trg-a1fd8125`) |
| `ComplianceData.run_id` + its collector resolution | `.github/workflows/**` (host-checks card) |
| `audit_staleness.normalize()` (consequence of AC5) | anything that *consumes* the stamp as a gate |

Both sibling cards state they do not own stamping. `compliance_report.py` is
touched by both this card and `trg-a1fd8125`, in different regions (header line
vs. cross-check disclosure) — a possible textual merge conflict, not an ownership
overlap. Mitigation: the change in each renderer is **one line**.

### The one deliberate reach into the test plugin, and why

External review's highest-severity finding: a stamping tool nothing calls does
not satisfy AC2. Correct — so the invocation is wired into the place that writes
the record. That place is inside `plugins/shipwright-test/` (the record is
prompt-written: a heredoc in `agents/test-runner.md`, a `Write` at iterate F5),
and the sibling card `trg-12b4cf3f` says it owns "the test plugin".

Resolved by reading both cards literally: this card names "the test-results
**writer**" as its own call site, and the sibling explicitly disclaims stamping.
Its four items (journey coverage, warning-only follow-ups, the accepted-baseline
list, retry reporting) touch none of the write-instruction lines. The edit here is
confined to *adding the stamp invocation after the record is written* — nothing
else in the test plugin is touched.

**Disclosed limit of the wiring.** The record is produced by a prompt, so the
*invocation* is prompt-wired like every other tool in that phase
(`record_event.py`, `record_coverage_total.py`). What this iterate makes
code-resolved is the **values** — which is the half that matters, and precisely
the defect the campaign found in `mode: standalone` ("stamping that field is
instruction, not code"). A run that skips the invocation produces a record with no
`source_state` at all, which is honestly absent rather than falsely stamped. The
missing half — a gate that *refuses* an unstamped or mismatched record — is the
sibling card's, filed and not silently assumed.

## Out of Scope

- Making any gate *enforce* the stamp (both sibling cards; see above).
- Changing `mode: standalone` or the `_validate_test` branch in
  `phase_validators.py` — sibling card.
- Stamping any artifact beyond the two named producers. "Nothing else may add
  stamping" is the card's own constraint.
- `audit-report.md` and `session_handoff.md` / `build_dashboard.md` /
  `triage_inbox.md` — the latter already carries a run id; the others are not
  named call sites.
- Adding a schedule/trigger for the cross-check (explicitly rejected by the
  operator per `trg-a1fd8125`).

## Design Notes

n/a — no UI surface. (Compliance MDs are operator-facing text, not a designed
surface; the added line follows the existing `Generated:` banner convention.)

## Affected Boundaries

Two serialized formats gain a field. Both are producer/consumer pairs across
files, which is the round-trip risk this table exists for.

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `shared/scripts/tools/stamp_test_results.py:main` | `shared/scripts/source_state.py:source_state_from_block` (and, later, the sibling card's gate) | JSON (`shipwright_test_results.json` top-level `source_state`) |
| `shared/scripts/source_state.py:banner_line` (via the 5 compliance renderers) | `shared/scripts/source_state.py:parse_banner_line`; `audit_staleness.normalize` (must strip it) | Markdown line (`Source-State: …`) |

**Note on the risk flag.** The diff-driven `is_io_boundary_change()` will **not**
fire: it matches file *paths* (`*_config.json`, `*_state.json`, `.env*`,
`hooks.json`, `settings.json`) and this diff changes only `.py` files.
`shipwright_test_results.json` is not in those patterns. The flag is therefore
formally absent — but the change is a genuine producer/consumer boundary on two
formats, so the Boundary Probe and a real round-trip test are run **voluntarily**
(spirit over letter). Recorded here so the absence of the flag is disclosed
rather than silently relied on.

## Confidence Calibration

- **Boundaries touched:** the two rows above — the `source_state` JSON block and
  the `Source-State:` markdown line.

- **Empirical probes run** (real executions, not re-reading the diff):
  1. **Ran the actual compliance regen** (`update_compliance.py --phase iterate`) and
     read the five produced documents. All five carried the banner directly under
     `Generated:`. *Finding:* they named `iterate-2026-07-23-req3-phase2-content-mono`
     — the **previous** run — because this run's `work_completed` event does not exist
     until F5b. That is the disclosure the card asked for working as intended, and it
     is invisible with a timestamp alone.
  2. **Ran the real stamp tool** on the repo's own tracked record. Wrote
     `run_id`/`commit`/`dirty` with `iterate_latest` and `coverage` untouched; the
     record's own modification correctly did **not** set `dirty`.
  3. **Ran Group E against the stamped documents** and proved the banner is not the
     cause of staleness: asserted `Source-State` is absent from `normalize()` output
     for every document, then read the first real difference in each — commit counts
     1208 vs 1200, test checkpoints 359 vs 360, license resolution 8/11 vs 11/11.
     Ordinary uncommitted-regen drift, exactly as `audit_staleness` documents.
  4. **Reverted every probe-written artifact** (`git checkout --`) after discovering
     the regen had appended a stray `grade_snapshot` event — the known landmine — so
     no exploratory state ships.
  5. **Ran the cross-plugin file-path loaders** that the doubt reviewer predicted
     would break. `plugins/shipwright-security::test_finalize_security_compliance`
     failed with `ModuleNotFoundError: No module named 'scripts.lib._provenance'`,
     confirming a CI-red I had introduced; after the fix, 6 and 5 tests pass.
  6. **8-category Boundary Probe** on the JSON side: BOM, CRLF, non-ASCII values,
     non-ASCII run id, `#`-in-value, empty and whitespace-only values. Three
     env-file-specific categories (POSIX `export`, inline `# comment`, quoted values
     containing `#`) justified-skipped — neither format is an env file.

- **Test Completeness Ledger:** 0 untested-testable.

  | # | Testable behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | Banner round-trips to its abbreviated form | tested | `test_source_state.py::test_full_state_round_trips_to_its_abbreviated_form` PASSED |
  | 2 | All three `dirty` states survive the banner (clean ≠ unknown) | tested | `::test_all_three_dirty_states_survive_the_banner[True/False/None]` PASSED |
  | 3 | JSON block round-trips exactly, keeping the full SHA | tested | `::test_json_block_round_trips_exactly_including_full_sha` PASSED |
  | 4 | Unresolved fields serialise as `null`, never omitted | tested | `::test_unresolved_fields_serialise_as_null_not_omitted` PASSED |
  | 5 | Garbage into `from_block` yields an empty state, not a half-trusted one | tested | `::test_from_block_yields_an_empty_state_not_a_half_trusted_one` (6 cases) PASSED |
  | 6 | A run id cannot forge a second banner line | tested | `::test_a_forged_newline_cannot_produce_a_second_banner_line` PASSED |
  | 7 | Whitespace-bearing run ids cannot inject a status token | tested | `::test_whitespace_bearing_run_ids_are_refused` (5 cases) PASSED |
  | 8 | Unicode control/separator characters refused | tested | `::test_unicode_control_and_separator_chars_are_refused` (4 cases) PASSED |
  | 9 | An unsubstituted `{run_id}` placeholder is refused | tested | `::test_placeholder_shaped_values_are_refused` (4 cases) PASSED |
  | 10 | A run id containing `clean`/`cleanup` does not forge a verdict | tested | `TestTokenCollisionRegression` (5 cases) PASSED |
  | 11 | `commit` is validated on both sides; a run id is not read back as a commit | tested | `TestCommitIsValidatedOnBothSides` (13 cases) PASSED |
  | 12 | Strip regex is anchored: body prose and layout survive, CRLF intact | tested | `TestBannerStripRegex` (5 cases) PASSED |
  | 13 | git resolution: clean / tracked-modified / untracked-only / excluded artifact | tested | `TestGitResolution` (5 cases) PASSED |
  | 14 | git absent, timeout, non-repo, empty repo all degrade to `None` | tested | `TestGitResolution` (4 cases) PASSED |
  | 15 | git never invoked through a shell, always with a timeout | tested | `::test_git_is_never_invoked_through_a_shell` PASSED |
  | 16 | Stamp writes code-resolved values into the record | tested | `test_stamp_test_results.py::test_writes_the_block_with_code_resolved_values` PASSED |
  | 17 | Every other top-level key, value and order preserved | tested | `::test_every_other_top_level_key_is_preserved_with_its_value`, `::test_key_order_is_preserved_and_the_stamp_is_appended` PASSED |
  | 18 | Canonical serialization form (byte-exact, no CRLF) | tested | `::test_serialised_in_the_repo_canonical_form` PASSED |
  | 19 | Stamping twice equals stamping once; no nesting | tested | `TestIdempotency` (3 cases) PASSED |
  | 20 | A corrupt / array / missing record is never overwritten | tested | `TestRefusalAndDegradation` (3 cases) PASSED |
  | 21 | A *rejected* run id does not fall back to a plausible one | tested | `TestRunIdResolutionPrecedence` (4 cases) PASSED |
  | 22 | All five renderers emit the banner exactly once, under `Generated:` | tested | `test_source_state_stamp.py::TestAllFiveRenderers` (30 cases) PASSED |
  | 23 | Run id and timestamp come off ONE event | tested | `TestOneEventForBothFields` (9 cases) PASSED |
  | 24 | Group E cannot newly report a document stale | tested | `TestGroupEStalenessUnaffected` (5 cases) PASSED |
  | 25 | An ADR reference is never labelled as a run | tested | `TestAdrReferenceIsNotARun` (9 cases) PASSED |
  | 26 | `audit_staleness` stays loadable by file path from a foreign namespace | tested | `TestAuditStalenessStaysFilePathLoadable::test_no_module_level_cross_package_import` PASSED + the real loaders in the security and shared sessions |
  | 27 | The banner renders identically on a repeat render (no drift) | tested | `::test_rendering_twice_is_byte_stable` (5 cases) PASSED |
  | 28 | Git's C-quoting of non-ASCII porcelain paths can defeat an exclusion | untestable | `covered-by-existing-test` — direction is fail-safe (over-reports modification, never under-reports) and unreachable for the ASCII repo-root path both producers use; disclosed in the resolution contract rather than silently relied on |

  **Counts:** testable 28 · tested 27 · untestable 1 · untested-testable **0**.
  **Enumeration basis:** 9 ACs, 9 covered.

- **Confidence-pattern check:**
  - *Asymptote (depth).* No "are you confident?" answer preceded a later finding —
    because the sequence never rested on one. Each review layer found something the
    previous had not: self-review found the `dirty` collapse and the `cleanup`
    substring bug; external code review found the commit-forgery vector and the
    `{run_id}` placeholder; the doubt reviewer found a **CI-red I had introduced while
    fixing the external review's findings**. That last one is the argument for the
    cascade: a fix applied after a review is unreviewed code.
  - *Coverage (breadth).* 28 behaviors enumerated, 0 testable-but-untested, 1
    honestly `untestable` with a closed-vocabulary reason code.
  - *Integration composition.* `cross_component` does **not** fire — the diff touches
    no merge/churn/event-log resolver, no `hooks.json` or `hooks/*.py`, no phase
    validator, no campaign-drain file. Verified against
    `risk_detectors.CROSS_COMPONENT_FILE_PATTERNS` rather than assumed, so no
    `category:"integration"` behavior is owed. The nearest composition risk — two
    producers sharing one mechanism — is covered by probes 1–3, which run the real
    producers end to end.

## Disclosed residuals (accepted, not hidden)

1. **Two files exceed the 300-line guideline** — `shared/scripts/source_state.py`
   (~340) and `collectors/_types.py` (302). Neither is in the anti-ratchet baseline, so
   both are *new crossings*: nudge-only, surfaced by the Group H audit post-merge.
   `_types.py` was already at exactly 300, so the one field this change needs cannot be
   added without crossing.
2. **One baseline entry bumped** — `audit_staleness.py` (365 → 379), which already
   carries `state="exception"` / ADR-095. The other four renderer entries were brought
   back to or below their frozen `current` instead of bumped, by making each renderer's
   change line-neutral or negative.
3. **`normalize()` strips the banner for all 8 registry documents** though only 5 are
   stamped, widening Group E's blind spot for `session_handoff.md`,
   `build_dashboard.md` and `triage_inbox.md` by one line shape. The doubt reviewer
   could not construct a realistic body line beginning with the token in any of the 8.
4. **Non-ASCII paths in the `dirty` exclusion** — see ledger row 28.
5. **The stamp invocation is prompt-wired**, because the record is prompt-written. The
   *values* are code-resolved; a run that skips the invocation leaves the record
   honestly unstamped rather than falsely stamped.

## Verification (medium+)

- **Surface:** none
- **Runner command:** n/a
- **Evidence path:** n/a
- **Justification (surface=none):** this change has no startable app surface —
  it alters two build-time artifact producers inside the framework's own Python
  tooling; there is no server, CLI entry point for an end user, or UI to drive.
  Verified instead by the full pytest suite at F0 plus the round-trip probes.
