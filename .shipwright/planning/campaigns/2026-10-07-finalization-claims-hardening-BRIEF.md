# Finalization hardening: make the framework do what it claims

**Stand:** 2026-10-07 · **Origin:** audit of the "Driving the AI SDLC with Shipwright" whitepaper against the code
**Not in scope:** editing the whitepaper. Where a claim is hardened here, nothing else is touched.
**Execution:** autonomous campaign, `branch_strategy: serial` with `depends_on` edges, waves build in parallel.

An autonomous run reads **this** document. Progress lives in the campaign's `status.json`.

---

## 0. Why

The whitepaper promises behaviours the gates do not enforce. Measured 2026-10-07:

| Fact | Number |
|---|---|
| Tests carrying an `@FR` tag, monorepo (manifest 2026-09-28) | 1,060 tagged / 16,681 untagged = **6.0%** |
| Same, WebUI (manifest 2026-09-29) | 2,441 / 6,020 = **28.9%** |
| Last 45 merged monorepo PRs that changed tests: how many added a tag | **11** |
| Does iterate Step 6 (TDD) or path-a/b/c tell the agent to tag new tests? | **No.** Only `F0.md:376`, reactively, after the AC ratchet is already red |

The existing gates are narrow: Keystone fires only when AC *text* changes in the spec;
cross-layer coverage fires at medium+ and only for changed FRs; the AC ratchet fires only
for *newly minted* unbound ACs. A test added under an unchanged AC ships untagged, always.

Backfill is **already done** (req3-05 AC-proving tests, last unit 2026-09-16; `backfill_test_links` engine, ADR-104).
Only the **delta since that backfill** is open. See U2. Prevention (U1) comes first so the delta cannot regrow.

## 1. Units and dependency graph (rev. 2 - after plan + architecture review, internal and external)

`depends_on` = "may not START until the dependency has MERGED". Reviews found the first draft's file sets were
NOT disjoint: `iterate_checks.py` sits exactly at its bloat cap (1087, ADR-125) and holds the only check list
(`run_all_checks`, lines 1048-1086) - `verify_iterate_finalization.py` is a 97-line wrapper. The review-record
schema (`lib/review_record_schema.py`, `record_review_pass.py`) and `sub-iterate-runner.md` (capped, 510) are also
shared. So: one foundation unit first, then everything that registers a gate hangs off it.

| id | Unit | Real touch set | depends_on | Cx |
|---|---|---|---|---|
| **U0** | Foundation: gate extension point + shared vocabulary | new `verifiers/_finalization_claims.py` (a list `run_all_checks` splices in ONCE - one edit to `iterate_checks.py`, shrink-neutral); shared closed `REASON_CODES` module; `reason_code` field in review-record schema + F5c entry + writers (`record_review_pass.py`, `lib/review_record_schema.py`), validators updated in the same diff | - | medium |
| **U1** | Test-tag gate + authoring instructions | new `verifiers/tag_binding_gate.py` (NOT `test_*`-named), `SKILL.md` Step 6, `path-a/b/c`, `F0.md` | U0 | medium |
| **U2** | Delta backfill (monorepo) | test files; `backfill-report.*`; bloat exception if needed | - | small |
| **U3** | Review record at trivial / all-`not_run` | `review_record_check.py`, ledger fn extracted to `verifiers/_ledger_*.py` | U0 | medium |
| **U4** | 100-line cascade trigger | new `verifiers/cascade_trigger.py`; constant moved to `shared/scripts/lib`, re-exported by `diff_risk_recheck.py`; `sub-iterate-runner.md` line 157 | U0 | small |
| **U5** | Surface check not bypassable | extracted `verifiers/_surface_*.py`, `surface_verification.py` (463, no headroom) | U0, U3 | medium |
| **U6** | Requirement gate bypasses | `lib/fr_gates.py`, `record_event.py` (777, ADR-111) | U0 | medium |
| **U7** | Baseline freshness (**narrowed, see section 5**) | extend existing `check_architecture_documented` (`iterate_checks.py:979`) via U0's list; `F2.md` | U0 | medium |
| ~~U8~~ | ~~Reflection record~~ **CUT 2026-10-07** (no measured failure; 4/4 reviewers) | - | - | - |
| **U9** | 80% hook measures requirement coverage | `plugins/shipwright-compliance` `check_rtm_coverage.py`, `rtm_generator.py` (764, capped) | - | medium |
| **U10** | Autonomous external review: loud, not silent | `campaign-step-3-5-plan-review.md`, `sub-iterate-runner.md`, F12/PR note | U0, U4 (same file) | medium |
| **U11** | Integration scenario | new test, generated in a tmp dir at runtime (never commit untagged fixtures) | U1, U3, U4, U5, U6, U7 | medium |
| **U12** | Docs reconcile | `docs/hooks-and-pipeline.md`, `docs/guide.md` | all merged units | small |

Waves: **W0** = U0 (+ U2, U9, which have no gate-registry dependency); **W1** = U1 U3 U4 U6 U7 U10;
**W2** = U5; **W3** = U11; **W4** = U12.

**Tag-from-the-start contract (campaign-wide, in every unit's runner prompt):** U1 lands in parallel with its
siblings, and every sibling adds tests. Every unit therefore tags the tests it adds (`pytest.mark.covers`)
from its first commit, and re-runs F11 after rebasing onto a main that already contains U1. A sibling
that goes red only because U1 merged under it is a sequencing artifact: re-run it, and do not count it as one of
its two reds.

**Release propagation:** a released (twice-red) unit releases its dependents with it; U12 documents only what merged.

## 2. Unit specs

### U0 - Foundation
1. `verifiers/_finalization_claims.py` exposes `CLAIM_CHECKS` (ordered list). `run_all_checks` splices it in with
   one edit; `iterate_checks.py` must not grow (move code out to compensate). Meta-test, both directions: every
   entry resolves, every `verifiers/*` check named in docs is registered.
2. One `REASON_CODES` closed vocabulary (per check family), importable by all verifiers and by `record_review_pass.py`.
   Add `reason_code` to the review-record schema and F5c; keep reading old records (free-text `disposition`) as
   legacy. **Validators ship with compatible writers in the same diff.**
3. A per-exemption **count** is part of the F5c entry and printed in the F12 summary and the PR body.

### U1 - Test-tag gate (the core)
**Build it on what exists; do not write a second parser.** Compare two traceability manifests: head
`untagged_tests` + `invalid_tags` minus base `untagged_tests` (base read through
`verifiers/_keystone_base_manifest.py`, fail-closed `ReadError`), plus tests whose normalised body digest changed
(`verifiers/_test_body_suspects.py`). Regenerate through `_layer_coverage_regen`'s collector and cache - the
production collector, not the single-line reference grammar in `lib/fr_tag_grammar.py`, which cannot bind
multi-line Playwright `test(` calls or suite-level tags and would false-STOP most of the WebUI.

**Feasibility spike, 2026-10-07 (this repo, HEAD):** `regenerate_base_head` loads the production collector and
returns in **28 s cold / 11.5 s with the base memoised**; head untagged = **16,969** (16,681 on 2026-09-28, so
~290 untagged tests landed in nine days), `invalid_tags` = 0. Cost accepted for an F11 gate; U1 must reuse the
memoised path and not regenerate a second time per run.

**What counts as a test:** functions inside the project's real test roots only (root `conftest.py` roots, each
`plugins/*/tests`, `testpaths`), found by AST (`def test_*`, `Test*` methods; Playwright/Vitest per the collector).
`**/fixtures/**` is excluded (deliberately untagged or malformed fixture repos live there). Production modules
named `test_*.py` under `verifiers/` or `scripts/` are NOT tests.

**Identity rules (each needs a test):** function-level identity, never the pytest node id (adding a parametrize
case is not a new test); a rename or move is matched by normalised body digest (Python: normalised AST; TS:
token-normalised); docstring/comment-only edits are not modifications; class-level marks apply to methods;
mechanical edits (an import or fixture rename touching many legacy tests) use code `mechanical-refactor`, valid
only when the normalised body diff is limited to renamed identifiers.

**Exemptions are per test, not per diff:** a `file::name` list in the F5c entry, each with a `reason_code`,
path-safe validated. `fixture-or-helper` is valid only if the collector does not collect the function as a test.
Exemption count and share are reported in F12, the PR body and the campaign's final measurement. The iterate's
Spec-Impact FRs are the expected tag set; a new tag pointing at an FR outside it WARNs. Tags resolve through the
fold-map; an unresolved FR id fails.

**Failure modes:** unobtainable diff, collector unavailable, regeneration failure -> STOP with a remediation
(never the lazy-loader SKIP). Applies at every complexity. Hard STOP, ratchet semantics (existing untagged tests untouched).

**Authoring side (same diff, load-bearing):** Step 6 and path-a/b/c tell the agent to tag each new test with the
FR/AC it proves; Path C: the regression test carries the tag of the requirement the bug violates; `F0.md:376`
becomes a safety net.

**Acceptance:** (1) untagged added test -> STOP naming file::test; (2) tagged test under an unchanged AC -> pass and
link in a regenerated manifest; (3) docstring-only edit -> pass; (4) valid per-test exemption -> pass, free text or
per-diff exemption -> STOP; (5) unobtainable diff / collector -> STOP; (6) multi-line Playwright test and a
suite-tag-inheriting test bind; (7) WebUI-shaped project gets the gate through the plugin; (8) parametrize-case
addition, test move with unchanged body, class-level mark, `fixtures/` edit, production `test_*.py` module edit
-> no false STOP; (9) mechanical rename of 200 legacy tests with `mechanical-refactor` -> pass.

### U2 - Delta backfill
1. Measure first (tests added since 2026-09-16, untagged, per root) and record it in the PR body.
2. `backfill_test_links.py --dry-run`; the report **lists files at their bloat cap**. Added decorator lines need
   either same-line tags or one exception ADR (e.g. `test_verify_iterate_finalization.py` 1572,
   `shared/tests/test_record_event.py` 507, `test_rtm_generator.py` 688). Plan that before writing.
3. Write only deterministic high-confidence tags; the rest becomes ONE triage card. No auto-delete.
4. "Manifest regenerates clean" = `_layer_coverage_regen` run on HEAD exits 0 with `invalid_tags: 0`.
WebUI delta is a follow-on in its own repo (section 4).

### U3 - Review record at trivial
All-`not_run` records fail at **every** complexity (today only medium+). At trivial: `self` must be recorded
(unconditional); the other types close with **one** recorded default row (`trivial-auto`), not seven free-text codes.
Closed-vocab per-type codes are required from `small` up. The ledger skip at trivial becomes a recorded row, not a SKIP.
Authoring docs (`SKILL.md`, F5c) updated in the same diff.

### U4 - 100-line trigger
Standalone `small`: risk flag **or** diff > 100 lines -> `code` is `completed`, or `not_run` + closed-vocab code.
Move `PLAN_REVIEW_DIFF_LOC_THRESHOLD` to `shared/scripts/lib` (re-export from `diff_risk_recheck.py`; importing across
the plugin boundary collides, ADR-044/045). Define the counting once: the doc says `git diff HEAD~1 | wc -l`
(patch lines incl. headers); verifier and `sub-iterate-runner.md:154-157` must use the same definition
(merge-base diff, added+removed lines, `>` 100, boundary stated).

### U5 - Surface verification
At medium+ `surface="none"` needs a closed-vocab code AND the verifier re-derives from the diff whether a runnable
surface is touched (API route, UI, SSE/WS, message contract); if so `none` is refused. `tests_run`/`exit_code` are
cross-checked against the staged evidence index, **tied to the verified revision and the detected surface**; absent
or stale evidence fails (test both).

### U6 - Requirement gate
Bug iterates are not exempt; `spec_impact: none` needs a closed-vocab reason; `check_fr_existence` fails closed when
specs are expected but parse to zero requirements; the spec-impact gate also runs at F5b. A `change_type` exemption is
checked against the diff using a **project-aware path classification per change_type** (in this monorepo `tooling`
and `infra` ARE `shared/scripts/**` and `scripts/**`; a global "no runtime code" rule would refuse every legitimate
tooling change). Diff = merge-base to **working tree incl. untracked** (the event is written before the commit).
Cover mixed diffs, renames, unknown paths; test monorepo and WebUI shapes.

### U7 - Baseline freshness (narrowed)
No parallel gate: extend `check_architecture_documented`, which today trusts the self-reported `architecture_impact`.
Map each detected F2 trigger (new route/component/schema/service) to the artifact that must change; an unrelated doc
edit does not satisfy it; an exemption contradicting a detected trigger is refused. **Warn-first** while the
false-positive rate is unknown; hard only after a measured burn-in. Needs confirmation (section 5).

### U8 - CUT
Reflection stays optional ("none" is a legal outcome of F3a). Operator decision 2026-10-07.

### U9 - 80% hook
**Step 1 is a measurement:** compute current FR-bound, executed-passing coverage from the manifest and report it; if
far below 80% the threshold ratchets from the measured value (otherwise the soft-block always fires and overrides
become noise). Separate FR and AC metrics, one counting unit each; join bindings to execution results by commit,
handling skipped and parametrized tests and missing results. The hook reads the **committed/cached** manifest (it
runs on every `git commit`; no regeneration there) with a staleness WARN; regeneration stays in F11/CI. Soft-block +
logged override unchanged; fail-open cases become a visible WARN.

### U10 - Autonomous external review
`not_run` with `reason_code: unavailable`; the run continues, loudly: PR note, F12 line, one triage card to re-run.
`unavailable` requires a captured adapter-error artifact. A bare `not_run` without the code fails the review-record
check. Edits `sub-iterate-runner.md`, hence the edge to U4. Interactive behaviour unchanged.

### U11 - Integration
Scenario built in a **tmp dir at runtime** (never commit untagged fixtures; U1 would block U11's own F11), crossing
U1/U3/U4/U5/U6/U7: each gate asserted in isolation with its own diagnostic so another failing gate cannot mask a
missing check; complexity chosen per case (U4 at small, U5 at medium+).

### U12 - Docs
`docs/hooks-and-pipeline.md` registry + artifact-write matrix; `docs/guide.md` ch. 4, 7.5, 8, App. B.
Every unit that changes what must be RECORDED also updates its authoring instructions in its own diff.

## 3. Autonomy and parallelism contract

- Each unit is trivial–medium, one PR, `Run-ID` footer, review cascade per the CLAUDE.md standing request
  (reviewers only; no extra fan-out).
- The runner has no `Agent` tool; internal reviewers are delegated to the orchestrator (campaign-mode 3f-bis).
- Shared hot files and how collisions are avoided:
  - `iterate_checks.py` is at its exact bloat cap and holds the only check list. U0 creates one extension point;
    every later gate registers there and extracts its code to a new `verifiers/_*.py`. No unit grows `iterate_checks.py`.
  - Review-record schema/writers and `sub-iterate-runner.md` are shared: owned by U0 and the U4 -> U10 edge.
  - `docs/hooks-and-pipeline.md` — rows only, U12 reconciles.
- Every unit pins its tests to **one test root** per pytest process (root `conftest.py` rule).
- F0 runs the mirrored merge gates; each unit runs `uv run scripts/verify_local.py` before the push.
- Stop conditions: a unit red twice -> released (dependents with it), campaign continues; U0 or U1 red -> STRICT-STOP (everything else
  depends on the tag contract being right).

## 4. Out of this DAG (follow-on, same intent)

1. **WebUI parity** (repo `shipwright-webui`): after U1–U10 are in the plugin cache
   (`update-marketplace.sh` + `check_plugin_cache_sync.py --strict`), a small campaign there: delta backfill
   (28.9% tagged today), verify the new gates fire under its stack, and add the local CI mirror the monorepo's
   `verify_local.py` provides (WebUI has none; CI requires 12 checks there).
2. **Event log immutability** (append-only is convention; one hand-edit on record): a tamper-evidence design
   question, not a gate fix. File as a triage card, not a unit.
3. **Iterate coverage of non-iterate PRs** (24% / 28% of PRs bypass the iterate record): a policy decision.

## 5. Decisions the operator must confirm before the first wave

Reviews run 2026-10-07 (internal Opus plan + architecture, external GPT + GLM plan + architecture): all
`revise`, one `reject` (GPT architecture: prefer option C, correct the docs). The operator has decided to harden
the product, so C is not taken; every other finding is integrated above. Cuts proposed by the reviewers:

S5. **Decided: U8 cut; U7 narrowed + warn-first.** GLM and GPT: U8 (reflection) and U7 (baseline freshness) enforce promises with no
    measured failure; U8's output would be overwhelmingly "none", U7's common case a rubber-stamp exemption
    (only 24% of iterates touch architecture today). Operator confirmed 2026-10-07.

Decided by the operator 2026-10-07:

1. **U1 hardness: hard STOP** at every complexity from day one, diff-only (no baseline file).
2. **U10: autonomous runs MAY continue** when the external review cannot run — but never silently: the pass
   is recorded `not_run` with `reason_code: unavailable`, the PR carries a visible note, the F12 summary names
   it, and a triage card is filed so the review can be re-run. No env-var waiver exists.
3. **U9: soft-block stays soft** (override logged); the number and its definition are printed; fail-open
   cases become a visible WARN.

## 6. Verification of the campaign itself

After the last merge: re-run the measurement in §0 on a fresh manifest — share of tests added since the campaign
started that are tagged must be 100% (excluding exemptions), and the 45-PR retrospective
(`git log` + test diffs, same script as the audit) must show a tag in every PR that adds tests.
