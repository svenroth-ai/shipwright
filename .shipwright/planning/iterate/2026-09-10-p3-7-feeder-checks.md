# Iterate Spec: P3.7 — Two feeder checks: AC without a test (anti-ratcheted) and a test whose AC vanished (hard)

- **run_id:** iterate-2026-09-10-p3-7-feeder-checks-anti-ratcheted
- **Campaign:** req3-04c-ac-identity-wave2, sub-iterate p3.7 — the two feeder checks P3.6's own
  design doc (`.shipwright/planning/iterate/2026-09-09-p3-6-keystone-gate.md`, §3(b), §7, §10 item 8)
  named as "not p3.6's" and handed off explicitly.
- **Affected FRs:** FR-01.11 (AC-identity / evidence-ledger area — same FR as P3.1–P3.6)
- **Source sub-iterate spec:**
  `.shipwright/planning/iterate/campaigns/req3-04c-ac-identity-wave2/sub-iterates/p3.7-feeder-checks-anti-ratcheted.md`
- **Design of record:** `Spec/design/2026-07-22-req3-campaign-SPEC.md` §8 E2; P3.6 design doc §3(b),
  §7 (the two-PR unbind sequence, `removed_with_bindings`), §10 item 8 (the hand-off card,
  `trg-f68795d2`).

## 1. Problem, restated from the hand-off

SPEC §8 E2 names two checks P3.6 deliberately does not build, ASYMMETRIC BY DESIGN:

* **(a) "AC without a test."** P3.6's own measurement (design doc §2.1): 259 of 268 minted ACs
  have no test binding today. A hard block on that population on day one would be a blanket
  blocker, not a gate — so this is **anti-ratcheted**: only a *newly* unbound AC, not already
  grandfathered, blocks.
* **(b) "a test whose AC vanished."** No legacy backlog exists for this predicate — nothing has
  ever validated that a `@covers` tag's AC id still exists. **Hard from day one, no baseline.**

Three named shapes (P3.6 design §7, §10 item 8b; triage card `trg-f68795d2`) can make a test's
bound AC effectively vanish without the criterion's own text ever changing in the blocking PR:

  (i)   **two-PR unbind sequence** — PR1 drops a `@covers` tag's `/ACnn` suffix (no AC text
        changes); PR2, later, edits that AC's text against an already-unbound base.
  (ii)  **outright deletion** of a minted criterion that still had a binding.
  (iii) **id rotation** on the same criterion (`[AC01] foo` -> `[AC55] foo`, wording unchanged) —
        reads as removal-plus-addition, never enters P3.6's `changed` set.

The hand-off states these collapse to one remediable condition: *a binding tag whose AC no
longer exists in the spec.* §3 below verifies that claim rather than assuming it.

## 2. Reused primitives (no second parser, no second link walk)

* `lib.ac_identity.read_all` — the same minted-criteria reader `_keystone_ac_digest` /
  `_keystone_criteria` use.
* `verifiers._keystone_links.links_for` — P3.6's manifest link counter.
* `verifiers._keystone_criteria.ac_criteria_digests` — P3.6's per-AC digest.
* `verifiers._layer_coverage_ac._spec_paths` / `spec_text_at` — the union-of-both-sides reader,
  same §5.1 argument (a spec renamed/removed between base and head must still be compared).
* `verifiers._keystone_ac_digest.read_base_manifest` / `require_manifest_shape` /
  `MANIFEST_RELPATH` — the base-manifest three-way reader.
* `verifiers._layer_coverage_regen._merge_base` — base-sha resolution, fail-closed on no
  resolvable merge base.

New modules: `verifiers/_ac_binding_state.py` (pure, state-only: minted / bound / unbound /
orphaned) and `verifiers/_ac_binding_regression.py` (base-vs-head: a binding regression on
unchanged text).

## 3. Does "one shared condition" actually close all three shapes? — traced, not assumed

Arm 1 (`_ac_binding_state.BindingState.orphaned`): for every active FR, walk the manifest's
current `acs` keys; any key not in the CURRENT spec's minted set for that FR is an orphan. This
directly and unconditionally catches:

* **(ii) outright deletion** — the criterion is gone; the manifest (regenerated from a
  not-yet-updated `@covers` tag) still carries a binding under the old id.
* **(iii) id rotation** — the old id's binding is now unminted at head.

**Tracing (i) through arm 1 shows it does NOT close it.** PR1 "deletes the `/ACnn` suffix from
a `@covers` tag" (P3.6 design §7) — the tag becomes a bare, VALID FR-level tag. Nothing about it
names a vanished AC id. The regenerated manifest's `acs` map simply stops carrying a key for
that AC at all (`_test_links_requirements.file_hit` only files a hit under `acs_by_key` when the
tag names an `ac_id`). That state is structurally identical, to arm 1, to an AC that was *never*
bound — i.e. it is feeder (a)'s anti-ratcheted territory, not an orphan.

This is disclosed rather than left as an unverified assumption (the same honesty the P3.6 design
doc models throughout: several of its own "closed" claims from an earlier round turned out to
introduce a new gap, found and named at the next round). **A second arm is needed and built:**

**Arm 2** (`_ac_binding_regression.binding_regressions`): an AC whose criterion digest is
IDENTICAL at base and head (so it is invisible to every text-diff-keyed check, P3.6's own
`binding_removed` included), that had `>=1` manifest link at base and has `0` at head. This is
exactly P3.6's own diagnosis of its blind spot (design doc §7): *"Closing it needs a signal that
does not depend on the AC's text changing."* Blocking this blocks **PR1 itself** — the commit
that performs the unbind — at its origin rather than waiting for PR2's exploit of the
already-unbound state, **whenever the base manifest's own record of the binding is
trustworthy** (external plan review, openai, HIGH — §5a finding 2 narrows this claim; the base
manifest is stale-by-construction, the same disclosed limit P3.6's own §7 already accepts).

Deliberately does not fire on a `changed`/`added`/`removed` AC (P3.6's own `binding_removed`/
`unbound` walk owns those) — only the complement, "nothing about the text moved."

**Verdict: two arms, one shared mission ("a test's binding must still point at something
real"), not one shared code path.** The module docstrings name this correction explicitly so a
future reader does not assume the brief's summary was independently re-verified and found exact.

## 4. Feeder (a) — anti-ratchet design

`shipwright_ac_coverage_baseline.json`: `{"unbound": ["FR-xx/ACnn", ...]}`. Rule, modelled on
`shared/scripts/lib/anti_ratchet.py`'s own block rule adapted from a per-file LOC ceiling to a
per-AC set membership: **an unbound AC not already in the baseline blocks; an existing baseline
entry does not, regardless of how long it has been unbound.** Absent baseline -> empty
grandfathered set (every unbound AC is new — the opposite default from the bloat baseline's
"fail open", deliberate: the bloat baseline is a *pre-existing repo artifact*; this one is
introduced by this very PR, so "absent" cannot mean "trust the whole population"). Present-but-
corrupt baseline -> infra fault (fail CLOSED, same as `anti_ratchet.py`). `--write` regenerates
it from current state; shrinking (an AC gains a binding) needs no baseline update to stay clean
— reported as `resolved_since_baseline`, informational only.

**Seeded empirically against the real repo** (§6 below): 259 unbound ACs, matching P3.6's own
measurement almost exactly (P3.6 measured 259/268 on an earlier commit).

## 5. CI wiring

Two new `(gate)` steps in `.github/workflows/ci.yml`, both `pull_request`-only, both ordered
after the traceability-manifest regeneration step (same reason as the Keystone gate: they read
the manifest that step rewrites in place from this run's own JUnit). Neither is mirrored by
`scripts/verify_local.py` — added to its `CI_ONLY_GATES` registry with the same structural
reason as the Keystone gate (a local invocation would grade against a committed manifest, not
one regenerated from a real run).

## 5a. External Plan Review Findings (Step 3.5 — glm + openai, 2026-09-10)

| # | Provider | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | HIGH | An unreadable/untrustworthy spec path at head was silently EXCLUDED (warning, not blocked) in an earlier version of `_ac_binding_state.read_binding_state`, making the hard-from-day-one orphan check fail OPEN on exactly the input it exists to catch. | **Fixed.** Three-way contract now matches `spec_text_at`'s own: `""` (genuinely absent) proceeds as zero minted criteria + a warning (any still-bound AC correctly orphans); `None` (real read fault) or untrustworthy markers now RAISE `ReadError`, mapped to `infra_fault`/exit 2 by both CLIs — matching P3.6's own HEAD-side convention. Pinned by `test_an_unreadable_spec_path_raises_readerror_not_excludes`, `test_a_genuinely_absent_spec_path_proceeds_as_zero_criteria_with_a_warning`, `test_untrustworthy_markers_raise_readerror`, and a real-git CLI test deleting the whole spec file. |
| 2 | openai | HIGH | Arm 2's only evidence of "had a binding at base" is the base manifest, stale-by-construction; the module's "closes the two-PR sequence" claim overstates what a stale/incomplete base artifact can prove. | **Fixed (wording).** Narrowed to "detects PR1 whenever the base manifest's own record of the binding is trustworthy" in both the CLI and the pure-module docstrings — the underlying staleness is the SAME disclosed limitation P3.6's own design doc §7 already accepts for `binding_removed`'s reduction check; not independently fixable inside this PR (base is immutable). |
| 3 | openai | medium | The seeded baseline + a canonical AC-id key constructor should be explicit deliverables/contracts, not implicit. | **Rejected-with-reason, already true.** The seeded baseline (`shipwright_ac_coverage_baseline.json`, 259 entries) is a committed deliverable of this sub-iterate; the key format (`f"{fr_id}/{ac_id}"`) is the SAME string both the producer (`_write_baseline`) and reader (`_load_baseline`) use, generated by one script — no cross-format risk to normalize against yet. |
| 4 | openai | medium | Both gates depend on the manifest-regeneration step covering the SAME test scope as the PR (sharding/filters could make valid bindings vanish -> false blocks). | **Rejected-with-reason.** `ci.yml` already runs a dedicated `Verify test-root JUnit coverage (gate)` step (in `verify_local.py`'s own `CI_ONLY_GATES` registry) asserting every planned test root produced its JUnit BEFORE the regeneration step this gate depends on — the exact assurance requested already exists as a sibling gate, inherited by P3.7 for free (same as P3.6). |
| 5 | openai | low | Arm 2 detects an AC-without-test regression on a criterion that still EXISTS, not literally "a test whose AC vanished" (arm 1's predicate) — risks confusing future maintainers. | **Fixed (wording).** Added an explicit "Naming, precisely" paragraph at the top of `_ac_binding_regression.py`'s docstring distinguishing the two arms' actual predicates before the reader reaches the longer trace. |
| 6 | glm | medium | A PR can unbind an AC and `--write` the ratchet baseline in the SAME PR, grading itself against its own updated grandfather set. | **Rejected-with-reason**, filed as `trg-91532c29`. Same accepted house precedent the bloat baseline already carries (same-PR-editable; review + post-merge detective audit is the real control, not a same-PR technical block). Reading the baseline from the merge-base was considered and rejected: it would make THIS introducing PR fail its own new gate, since `origin/main` has no baseline file yet. |
| 7 | glm | medium | An AC reported `resolved_since_baseline` (bound) that later regresses (unbound again in a LATER PR) stays silently grandfathered forever — the suggested single-run fix (`baseline - resolved_since_baseline`) does not actually close it (no cross-run memory). | **Rejected-with-reason**, filed as `trg-91532c29` (same card as #6 — both stem from the baseline being a flat, memory-less snapshot). Real closure needs either periodic `--write` refresh (documented in the baseline file's own `$comment`) or a persisted resolution ledger — real design work, its own follow-up. |
| 8 | glm | low | `links_for`-derived "bound" should be confirmed tag-derived, not execution-derived (a failed/skipped-but-tagged test should still count as bound). | **Fixed.** Clarified in `BindingState.bound`'s own field docstring; pinned by `test_a_bound_ac_with_a_failed_or_skipped_link_is_still_bound_not_unbound` (already true — `links_for` returns every filed link regardless of `status`/`executed`; this only adds a test and the doc). |
| 9 | glm | low | Whether a coordinated FR removal (criteria + tests + FR deleted together) is caught by ANY layer was not traced. | **Rejected-with-reason.** Both feeder checks scope to `active_requirements(manifest)` (same as P3.6's own `_keystone_links`) — a fully-removed FR is invisible to both checks by construction, silently, same as it already is to P3.6. Not a new gap this sub-iterate introduces; out of scope to trace exhaustively here. |
| 10 | glm | low | Baseline schema has no version marker; a future format change risks silent misread. | **Fixed.** Added `schema_version: 1`, tolerated absent (pre-dates the key) but rejected if present and unrecognised. Pinned by `test_a_baseline_missing_schema_version_is_still_accepted` and `test_an_unrecognised_schema_version_is_an_infra_fault`. |
| 11 | glm | low | The first contributor to trip arm 2 on a legitimate refactor has no rollout guidance. | **Rejected-with-reason, already sufficient.** `orphaned_bindings`/`binding_regressions` already surface the exact `FR-xx/ACnn` id(s) as dedicated JSON keys, and the CLI's own `remedy` field already names both sanctioned resolutions. A burn-in period was considered and rejected — feeder (b) is explicitly SPEC-mandated to be hard from day one (§8 E2), and §6's probe shows zero pre-existing violations to burn in against. |

Verdicts: glm `approve` (with the above findings), openai `revise` (with the above findings, all
addressed above). Both HIGH findings fixed; all MEDIUM findings fixed or rejected with a stated,
verifiable reason (a house precedent, an existing sibling gate, or a bootstrapping paradox for
this introducing PR specifically); all LOW findings fixed or rejected with a reason.

## 6. Empirical probes (Step 3.8 boundary — real repo, real git)

```
$ uv run shared/scripts/tools/check_ac_coverage_ratchet.py --project-root . --write
unbound_count: 259   (matches P3.6 design §2.1's 259/268 to within drift since that commit)

$ uv run shared/scripts/tools/check_ac_coverage_ratchet.py --project-root .
status: clean (0 new_unbound against the freshly-written baseline)

$ uv run shared/scripts/tools/check_orphan_ac_binding.py --project-root . \
    --head-sha $(git rev-parse HEAD) --base-sha $(git rev-parse HEAD~1)
status: clean (orphaned_bindings: [], binding_regressions: [])
```

Zero pre-existing violations for feeder (b), same reading P3.6's §2.3 reached for the keystone
gate itself. Real-git test fixtures (`shared/scripts/tools/tests/_keystone_repo.py`, reused —
not a mock) additionally pin: an outright-deleted bound criterion orphans (arm 1); an id
rotation orphans the old id (arm 1); a suffix-dropped binding with unchanged criterion text
regresses (arm 2) while an in-PR criterion edit does not double-report against P3.6's own
`binding_removed` (arm 2 stays silent when the digest changed).

## 7. Known limitations (disclosed, not fixed)

* **Feeder (a)'s baseline is a snapshot, not live — two related holes, both raised by external
  plan review (glm, medium x2; §5a findings 6/7), both tracked at `trg-91532c29` rather than
  fixed here.** (i) An AC that becomes unbound and is immediately re-baselined in the SAME PR
  that unbound it would pass — the baseline has no "who added this line" provenance. Not fixed:
  the same trust boundary every anti-ratchet baseline in this repo already carries
  (`shared/scripts/lib/anti_ratchet.py`'s own docstring: files outside the baseline are
  advisory), and review is the control, not a technical one — reading the baseline from the
  merge-base was considered and rejected, since it would make THIS introducing PR fail its own
  new gate (`origin/main` has no baseline file yet). (ii) An AC that gets bound (reported
  `resolved_since_baseline`) but whose baseline entry is never removed stays grandfathered even
  if it regresses again in a LATER PR — the single-run computation this gate does has no memory
  of the intermediate bound state, so subtracting `resolved_since_baseline` at check time (the
  reviewer's own suggestion) does not actually close it. Real closure needs either periodic
  `--write` refresh (now documented in the baseline file's own `$comment`) or a persisted
  resolution ledger, real design work deserving its own review.
* **Arm 1 and arm 2 both stop at the AC layer, never AC coverage *breadth*.** Neither checks
  whether a bound test satisfies the FR's `required_layers` — that is `cross_layer_coverage` /
  P3.6's own scope boundary (design §7), not this sub-iterate's.
* **The advisory item — "a changed test body suspects its AC" — is deferred**, per the
  sub-iterate spec's own explicit permission ("implement if time/complexity allow ... do not
  let it block"). Named explicitly, not left as a silent TBD (the `trg-875104ac` lesson this
  campaign already learned once): triage card `trg-33a474e2` names the mechanism sketch (diff a
  bound test's body between base/head where the AC's own digest is unchanged; ADVISORY only,
  human judges whether the edit weakens or merely refactors).
* **Arm 2 reads the base manifest, which is stale-by-construction** (read from the last commit
  at base, never regenerated) — the same disclosed gap P3.6's own design doc §7 already accepts
  for its `binding_removed` reduction check, inherited here rather than re-solved. External plan
  review (openai, HIGH; §5a finding 2) is why §3/§4's own claim that arm 2 "closes" the two-PR
  sequence is now worded narrower everywhere it appears: it detects PR1 whenever the base
  manifest's own record of the binding is trustworthy, not unconditionally.

## 8. Self-Review (Step 3.6 — 7-item checklist)

| # | Item | Verdict | Note |
|---|---|---|---|
| 1 | Spec Compliance | pass | Both ACs met: (a) blocks only on a ratchet (§4, pinned by `test_check_ac_coverage_ratchet.py`), (b) blocks from day one, no baseline (§3, pinned by `test_check_orphan_ac_binding.py`). Asymmetry documented at every reader touchpoint: both module docstrings, `ci.yml` step comments, `hooks-and-pipeline.md`, `guide.md`. |
| 2 | Error Handling | pass | Both CLIs follow the family's 0/1/2 exit contract; a manifest/baseline read fault is `infra_fault` (2), never a silent green. Unreadable spec paths are excluded with a warning, never misreported as unbound/orphaned (`_ac_binding_state`'s own stated rule). |
| 3 | Security Basics | pass | No new input trust boundary beyond what P3.6 already crosses (git blob reads via the same `spec_text_at`/`read_base_manifest`); the baseline file is read/written under `project_root`, no path traversal (fixed relative filename, `--baseline` override is an operator-supplied path, same trust level as `--project-root`). |
| 4 | Test Quality | pass | Real-git fixtures (no mocked reader) for both CLIs; pure-unit tests for `_ac_binding_state` cover minted/bound/unbound/orphaned and the "excluded, not misreported" rule; one subprocess smoke per CLI. Empirically probed against the real repo (§6). |
| 5 | Performance Basics | pass | Per PR: one extra `ac_identity.read_all` pass over each named spec path (already read by the Keystone gate in the same job) and a handful of `links_for` walks — no new test executions, no network calls. |
| 6 | Naming & Structure | pass | Mirrors the P3.6 family's own module split (`_keystone_links`/`_keystone_ac_digest`/`_keystone_base_manifest`) rather than inventing a new shape; both new source files are well under the 300-LOC limit. |
| 7 | Affected Boundaries (ADR-024) | pass | Producer: `test_links.generate_file()` (the traceability manifest, unchanged by this sub-iterate). Consumer: these two new CLIs, read-only. Round-trip probed for real in §6 against the actual committed manifest + spec.md — not merely unit-fixture data. |

## 9. Deferred, not built here

* The advisory "changed test body" check — triage `trg-33a474e2`.
* Any F11 (local) advisory mirror of either check — both are CI-only by the same reasoning
  P3.6's own Q4 ruling gave (`verify_local.py`'s `CI_ONLY_GATES` entries here).
