# Iterate Spec: adopt-miner-hygiene-gate-conflict

- **Run ID:** iterate-2026-09-16-adopt-miner-hygiene-gate-conflict
- **Type:** change
- **Complexity:** medium (escalated from Stage-1 `small`/history-fallback — see
  Repo Scout below; the operator's own task text frames this as a genuine
  producer-vs-gate design decision, the same shape the
  `project-gate-rollout-transition` precedent needed an Architecture Review
  for)
- **Status:** in progress
- **Triage:** closes `trg-ac2ef362` ("shipwright-adopt AC-miner conflicts with
  FR-01.02 #5's implementation-detail ban", FR-01.02, P1)

## Goal

`trg-ac2ef362` (minted by `iterate-2026-09-12-project-gate-rollout-transition`
as a disclosed, deliberately out-of-scope follow-up) names a real, *future*
producer-vs-gate conflict: `plugins/shipwright-adopt/scripts/lib/
test_acceptance_miner.py` mines `describe`/`it`/`test_*` labels straight out
of a target repo's own test files into `spec.md` acceptance-criteria bullets.
Those labels routinely carry exactly the code-symbol / HTTP-verb shapes that
FR-01.02 #5 (`_project_gate_extras_rollout.criteria_free_of_implementation_
detail`, via `fr_hygiene_detectors.violations`) bans as a HARD block —
measured directly against the gate in that iterate's own module docstring: a
`describe('UserProfileCard', ...)` prefix or an `it('GET /api/users: ...')`
label both trip `violations()`.

The rollout-transition grace that iterate built (`trg-9583d3a8`) only helps
content that already existed in a project's git history *before* the gate's
own rollout instant (2026-09-12T06:23:06Z). It cannot help a `/shipwright-
adopt` onboarding that runs after that instant: mining happens live, so there
is no historical snapshot to grace against, and even if there were, a fresh
grant would only cover that one onboarding's content once — not the systemic
conflict for the next mining run, or the next fresh onboarding after it.
`shipwright_run_config.json` at this repo's own root shows `adoption.adopted_
at: 2026-05-02` (pre-rollout, hence this repo itself never hit the conflict),
but that is a fact about *this* repo, not a fix for the next one.

Today the gate never actually fires *during* an adopt run — `config_writer.
write_project_config` writes `shipwright_project_config.json` with
`status: complete` directly (adopt's own artifact-writing path), bypassing
`update-step --step project` and therefore `project_checks.
run_project_checks` (the only call site of `check_criteria_free_of_
implementation_detail` — confirmed by reading `project_checks.py`; every
other of the 19 grep hits for that name is docs/tests/decision-records, not a
second runtime caller). The conflict surfaces the first time the "project"
phase is genuinely re-verified afterwards — e.g. an onboarded project later
runs `/shipwright-project` to decompose a new feature and reaches its own
Step 8 — at which point the *entire current* `spec.md`, including the old
mined bullets, is re-checked, and a HARD block with no available grace stops
that unrelated, later phase completion on pre-existing content the operator
of that later run had no part in authoring.

## Acceptance Criteria

- [x] `mine_acceptance_criteria` (and its `_mine_js`/`_mine_py` helpers)
      never emit a bullet that trips `fr_hygiene_detectors.violations()` —
      reusing the identical shared vocabulary the gate itself enforces (no
      duplicated/driftable rule), loaded via the plugin's existing
      `shared_loader.load_shared_module` collision-safe idiom (matches
      `gitleaks_config_scaffolder.py`'s precedent for adopt-into-shared
      imports).
- [x] JS/TS mining: when the combined `"<describe>: <it>"` string is dirty
      but the bare `it` label alone is clean, the describe prefix is dropped
      and the clean `it` label is kept — not discarded outright. (The
      describe-names-the-component convention is the single largest source
      of hits; dropping the whole bullet whenever a describe label happens to
      be a PascalCase component name would gut mining output for a typical
      React/TS codebase, the opposite of "tests are the most honest spec a
      brownfield repo carries".) When the `it` label is itself dirty (no
      describe prefix, or the prefix strip does not clean it), the bullet is
      dropped entirely.
- [x] Python mining: a dirty docstring-derived or humanized-name bullet is
      dropped entirely (no prefix to strip — the humanization step already
      removes `_`, so a dirty bullet there is dirty on its own terms).
- [x] Filtering happens before the existing `_AC_CAP` (10) truncation, so a
      capped result is 10 *clean* bullets where enough clean candidates
      exist, not fewer because dirty ones consumed cap slots.
- [x] No change to `fr_hygiene_detectors.py` itself, `_project_gate_extras_
      rollout.py`, or any other gate-side file — the gate's ban stays
      universal (extension and full-application specs alike, per the
      precedent's own established position) and un-softened; only the
      producer stops manufacturing violations of it.
- [ ] `trg-ac2ef362` is closed, referencing this run's own PR, once that PR
      exists — same process the `trg-9583d3a8`/`trg-aedcfe7b` precedent
      closures used (a `promote --task-ref PR:<N>` close event cannot itself
      carry a PR number that does not exist yet at review time, so it lands
      as a small follow-up append once this run's PR is open).
- [x] Within one mined file's bullets, any bullet that collides (exact string
      match) with another already-kept bullet from the same file is
      deduplicated, preserving first-seen order — applies uniformly, not only
      to bullets the hygiene strip reshaped (External Code Review, glm, low:
      the original wording scoped this to "survives prefix-stripping" only,
      but the implementation always dedups the final list, and narrowing it
      to only-just-stripped bullets would be the more complex, less honest
      option — two literally-identical bullets add no information whether the
      collision came from stripping two differently-dirty describes to the
      same text ("AuthService: validates input" / "UserService: validates
      input" → "validates input"), or from the source file's own test
      descriptions genuinely repeating verbatim). The spec.md acceptance list
      must not carry a literal duplicate line, full stop.
- [x] A new follow-up triage card (`trg-655cf276`) names the disclosed
      residual gap External Plan Review surfaced (both `glm` and `openai`,
      severity high, independently, `SHIPWRIGHT_VERDICT: revise` both): this
      fix stops *future* mining from emitting dirty bullets but does nothing
      for a project already `/shipwright-adopt`-onboarded strictly between
      the gate's rollout instant (2026-09-12T06:23:06Z) and this fix's own
      ship commit — that installed-base window's spec.md, if it mined any
      dirty bullet, still hard-blocks at the next `/shipwright-project` Step
      8 with no grace. See Out of Scope for why this run does not remediate
      that population inline.

## Spec Impact

- **Classification:** none
- **NONE justification:** framework-internal change to a shared plugin
  helper (`plugins/shipwright-adopt/scripts/lib/test_acceptance_miner.py`)
  that only affects *future* onboarded projects' spec.md content, never this
  monorepo's own FR/spec.md. Same justification class the
  `project-gate-rollout-transition` precedent recorded for the identical
  gate family.

## Out of Scope

- **Extending the rollout-transition grace mechanism** (`_project_gate_
  rollout.py`/`_project_gate_grace.py`) to cover miner-sourced content. This
  is a real, considered alternative — see Architecture Review below — but a
  permanent gate-side exemption for adopt-produced bullets would blanket-
  excuse the exact content class the gate exists to catch (mined `describe`
  blocks are close to the canonical case of "a code symbol leaking into a
  business-readable acceptance criterion", not a false positive), undermining
  #5's stated universal intent for that entire content class. Rejected here,
  not merely deferred; see Architecture Review resolution.
- **Adding a machine-readable "N bullets dropped for hygiene" signal** to the
  miner's output or the adopt handoff. Real value for onboarding-review
  visibility, but out of scope for closing `trg-ac2ef362` — the miner already
  documents itself as best-effort/non-exhaustive ("All silent on absence"),
  and adding a reporting surface is a separate, additive unit of work a
  future iterate can pick up if the silent drop turns out to be too opaque
  in practice.
- **AST-level test parsing** — already an explicitly disclaimed non-goal in
  the miner's own module docstring; unrelated to this defect and not
  reopened here.
- **Remediating the installed-base window** (projects `/shipwright-adopt`-
  onboarded between 2026-09-12T06:23:06Z and this fix's ship commit, whose
  spec.md may already carry a dirty mined bullet with no rollout grace
  available). External Plan Review (both `glm` and `openai`, severity high)
  correctly flagged that this run's fix does not reach that population.
  Deliberately not remediated inline: fixing the *producer* stops the bleed
  for every future onboarding (the actual shape of `trg-ac2ef362`'s
  finding — "a different, larger unit of work than grandfathering
  pre-existing content" already drew this same scope line for the sibling
  precedent). Remediating the installed base is a *distinct* problem —
  finding which already-onboarded projects exist, whether they were ever
  re-verified at Step 8, and what a safe one-time fix looks like for content
  already committed to their own `spec.md` — with no shared-monorepo
  registry of adopted projects to enumerate that population from. Tracked as
  `trg-655cf276` (see Acceptance Criteria) rather than solved here, the same
  disposition `trg-9583d3a8` gave the miner conflict itself one iterate ago.

## Design Notes

Reuses the plugin's own established cross-boundary-import idiom rather than
inventing a new one: `shared_loader.load_shared_module("scripts/lib/
fr_hygiene_detectors.py", <sentinel>)`, the same `spec_from_file_location`-
by-path technique `gitleaks_config_scaffolder.py` already uses to consume
`shared/scripts/lib/security_workflow.py` without a naive `from lib import
...`, which would collide: both `plugins/shipwright-adopt/scripts/lib/` and
`shared/scripts/lib/` are packages named `lib`, and Python's regular-package
resolution shadows whichever loads first (ADR-044/045). `fr_hygiene_
detectors.py` has zero internal `lib.`-prefixed imports of its own (only
stdlib `re`), so the by-path load carries none of the boundary-probe hazard
the `[[feedback_cross_plugin_boundary_probe_needs_no_internal_imports]]`
lesson describes for modules that DO have their own further `lib.` imports.

`violations()` is called once per *candidate* bullet during mining (not
post-hoc on the whole file), inside `_mine_js`/`_mine_py`, right where the
bullet string is already assembled — the smallest possible surface, no new
data flow.

## Affected Boundaries

n/a — no new producer/consumer pair, no serialized format's shape changes.
This unit reads an already-parsed in-memory string one more time (through a
pure detector function) before appending it to a list already being built.

## Architecture Review

**Should a fix be built here at all, and if so, producer-side or gate-side?**
Two real options considered:

- **A (this design): producer-side filtering.** The miner drops/reshapes
  bullets that would trip the hygiene detector, reusing the gate's own
  vocabulary so producer and gate can never drift apart (same function,
  imported, not reimplemented).
- **B: gate-side grace.** Extend `_project_gate_rollout`/`_project_gate_
  grace` (or a new sibling) to permanently exempt content that provably came
  from `/shipwright-adopt`'s miner (e.g. a marker in the FR row, or "any
  content from a project whose `adoption.adopted_at` predates this check").

**Resolution (`--autonomous`, no live operator turn):** Option A. The
operator's own task text does not pre-decide between A and B the way the
`trg-9583d3a8` precedent's invocation named its shape explicitly — it states
the conflict and its scope boundary (a producer-vs-gate conflict, "a
different, larger unit of work than grandfathering *pre-existing* content")
without picking a side, so this run makes the call on the merits: Option B
would be the third rollout/grace-shaped resident in this gate family (after
`_layer_coverage_rollout.py` and `_project_gate_rollout.py`), and unlike
those two — which grace content that predates a NEWLY INTRODUCED gate,
i.e. content nobody could have known to avoid — Option B here would grace
content a project's OWN toolchain keeps manufacturing indefinitely, forever,
for every future adopt+re-plan cycle. That is not a transition valve, it is a
permanent carve-out for one producer, which is exactly the "Option B" shape
(`scope == "extension"` skip) the `trg-9583d3a8` precedent's own Architecture
Review already rejected for the same gate, on the same universality
reasoning (#5's I1 ban applies to extension and full-application specs
alike; the mined content is not qualitatively different from a human typing
a symbol into an AC by hand — the gate's whole point is to catch exactly
that). Fixing the emission side is strictly smaller, has no permanent
resident cost, and — unlike a gate-side grace — also improves the *quality*
of what lands in a brownfield project's spec.md for a human reader, which is
the miner's own stated purpose ("the most honest spec a brownfield repo
carries"). **External Plan Review** (`--mode iterate`, over the mini-plan): **glm
revise, openai revise** — no contradiction (verdicts agree). Both
independently flagged the same high-severity gap: the fix only stops
*future* mining from producing dirty bullets, leaving projects already
onboarded between the gate's rollout instant and this fix's ship commit
stranded with no grace (addressed: a new follow-up triage card, see Out of
Scope; the population is external to this monorepo and not enumerable from
here). Both also flagged (medium): verify the exact emitted spec.md text is
what the gate re-reads (addressed: traced the write path — see Confidence
Calibration probe 2, byte-identical, no intermediate transform); and
prefix-stripping can collapse two originally-distinct bullets into a literal
duplicate (addressed: added a per-file dedup AC). openai additionally flagged
(medium, low): confirm the loader is exercised through its real import path,
not just an isolated smoke import (addressed: the existing test file already
imports via `from lib.test_acceptance_miner import ...`, the real
package-context path); and confirm the all-dirty/empty-result case is
handled downstream (addressed: traced to `generate_adoption_artifacts.py`'s
existing `if mined:` guard and `spec_document.py`'s existing TBD-marker
fallback — the same empty-list shape "no sibling test found" already uses,
no new code path needed).

**Architecture Review** (`--mode architecture`, over the brief above):
**glm approved, openai approved** — no contradiction. Both independently
reasoned to Option A on the merits (producer fix, no new standing mechanism)
without having seen this spec's own rejection reasoning for Option B (per
the brief protocol, options were listed without reasons). glm's one
low-severity finding — the new follow-up triage card is itself a small
standing bookkeeping obligation, and suggested closing it immediately if the
installed-base population can be shown empty — is accepted as correctly
identified but not actionable from this monorepo: there is no registry here
of externally-adopted third-party projects to check against (see Out of
Scope), so the card is minted as planned rather than pre-emptively closed on
an unverifiable claim of emptiness.

**External Plan Review, round 2** (`--mode iterate`, re-run once implementation
+ tests landed and the spec above was updated): **glm approved, openai
revise** — no contradiction. glm's earlier high-severity findings were fully
resolved by the round-1 fixes and it moved to approve; its round-2 findings
were all low/medium refinements, addressed as follows: nested describes —
the miner attributes an `it` to its single *innermost* describe only
(pre-existing, unchanged behavior — confirmed by reading `_mine_js`, no
ancestor chain is ever joined), so a dirty *outer* describe name never
enters the checked string at all and needs no stripping; covered by
`test_js_nested_describe_only_innermost_prefix_is_considered`. Cross-file
duplicate bullets — dedup is correctly scoped per-file because
`mine_acceptance_criteria` already never unions bullets across files (one
FR's ACs come from exactly one winning candidate file, "closest sibling
wins" is pre-existing, unchanged behavior), and different FRs render under
separate `### {fr_id}` headings in spec.md, not one shared list — so a
same-text bullet under two different FRs is not the "literal duplicate
line" the AC is about. Loader failing loudly — `load_shared_module` is
called at module-import time, uncaught (the only `try/except ImportError`
wraps choosing between the two `shared_loader` import *paths*, matching
every other adopt-plugin file's identical idiom); a missing `shared/` tree
raises `ImportError` immediately at import, never a silent all-clean or
all-dirty result — this is `shared_loader.py`'s own documented contract,
exercised by the plugin's existing `test_shared_loader.py` suite (5 tests,
unmodified, still passing). Deployed-layout resolution (openai) — the same
`shared_loader.load_shared_module` idiom is already load-bearing in
`gitleaks_config_scaffolder.py`, shipped and running in production adopt
runs; this change adds a second caller of an already-proven mechanism, not
a new one. openai's remaining `revise` (documentation completeness: the
mini-plan's prose didn't spell out the dedup step or the triage-mint step
as explicitly as the spec's own Acceptance Criteria did) is addressed by
this same spec update plus `trg-655cf276` now actually existing (not merely
promised) — no further code change indicated by either reviewer.

**External Code-Review Cascade** (`--mode code`, over the full diff): run
three times. Round 1 (glm+openai both `revise`): the cap-order test didn't
actually discriminate correct from broken orderings (both reviewers,
medium) — fixed by putting dirty labels first in the fixture; and a
docstring-blank-line empty-candidate concern on the Python side (glm, low)
— verified NOT reproducible as literally described (`.strip()` runs before
`.splitlines()`, so a leading blank line can never survive to `doc[0]`;
confirmed by direct probe), but a genuine adjacent gap (an all-underscore
function name humanizes to whitespace-only) was real and fixed with a
guard + test. Round 2 (glm+openai both `revise`): the same blank-label gap
existed on the **JS** side too and was worse there (a blank `it('')` under
a dirty describe could be stripped-and-kept as an empty bullet) — fixed
with the identical guard, two new tests; dedup was implemented more broadly
than the AC's original wording described (glm, low) — resolved by widening
the AC/docstring to match the actual, simpler, more correct behavior
(uniform per-file dedup, not scoped to only stripped bullets) rather than
narrowing the code; and the follow-up triage card's phrasing ("closed by
this run") was premature since no close event exists yet (openai, low) —
fixed via `triage_cli.py amend`. Round 3 (glm+openai both `approve`, no
contradiction): both remaining low findings from round 2's feedback
(`external_code` review-record status and the triage card wording) were
already resolved by the time of this run — glm's citation of "closed by
this run" is the STILL-PRESENT original `append` event's text, which the
`.shipwright/triage.jsonl` append-only format never rewrites; the
superseding `amend` event (verified present, same run) is what any
schema-aware reader (status resolution by file order) actually surfaces —
not a real unfixed defect, an artifact of reviewing raw diff text against
an event-sourced format.

## Confidence Calibration

- **Boundaries touched:** none new (Affected Boundaries above is n/a) — an
  in-process pure-function call added to existing in-process string assembly.
- **Empirical probes run:**
  1. `fr_hygiene_detectors.violations()` called directly, interactively,
     against the two example strings the precedent's own docstring measured
     (`"UserProfileCard: renders the avatar..."` → `['code-symbol']`,
     `"GET /api/users: returns 200..."` → `['http-verb']`) to confirm the
     detector shape before writing the filtering logic, and against
     realistic clean strings, incl. every bullet the existing 14-test suite's
     own fixtures already mine (`"users service: returns the active list
     when called without args"`, `"renders the avatar and username"`, `"foo
     computes the right value"`, `"add returns the sum of two integers"`) —
     all clean, confirming External Plan Review's concern #2 (existing tests
     might need updating for a false-positive) does not apply: none of the
     pre-existing fixture bullets trip the detector.
  2. Traced the write path from `mine_acceptance_criteria`'s return value to
     the text the gate re-reads: `generate_adoption_artifacts.py`'s
     `_record_ac`/mining loop assigns the returned list verbatim to
     `feat["acceptance_criteria"]`; `spec_document.py`'s renderer writes each
     element verbatim as `f"- {ac}\n"`, no further text transformation. What
     `criteria_free_of_implementation_detail` later re-parses via
     `fr_criteria.criteria_for` is therefore byte-identical (modulo the
     literal `"- "` markdown-bullet marker, which the parser already strips
     for every other AC source) to what this filter validated at mine time —
     answers External Plan Review's concern #2 (openai) directly: there is
     no rendering step between the checked value and the gate's input that
     could reintroduce or alter content.
- **Test Completeness Ledger:** see table below.
- **Confidence-pattern check:** asymptote — every branch of the new
  filtering logic (JS combined-clean, JS prefix-stripped, JS both-dirty,
  Python clean, Python dirty) has its own test, not one aggregate assertion.
  Coverage — the existing `test_test_acceptance_miner.py` suite (12 tests;
  corrected from an earlier miscount of 14 — Stage-2 code review, verified
  by `grep -c '^def test_'`)
  is re-run unmodified to confirm zero regression on already-clean mining
  behavior.

| Category | Behavior | Test |
|---|---|---|
| unit | JS: clean combined `describe: it` bullet kept as-is | `test_test_acceptance_miner_hygiene.py` |
| unit | JS: dirty describe prefix (PascalCase component) + clean `it` → prefix dropped, `it` kept | `test_test_acceptance_miner_hygiene.py` |
| unit | JS: dirty `it` label (HTTP verb inline) → bullet dropped entirely | `test_test_acceptance_miner_hygiene.py` |
| unit | JS: no describe (bare `it`/`test`), dirty label → dropped | `test_test_acceptance_miner_hygiene.py` |
| unit | Python: clean docstring-derived bullet kept | `test_test_acceptance_miner_hygiene.py` |
| unit | Python: dirty docstring-derived bullet dropped | `test_test_acceptance_miner_hygiene.py` |
| unit | Python: dirty humanized-name bullet dropped | `test_test_acceptance_miner_hygiene.py` |
| unit | Filtering happens before the 10-item cap (dirty bullets do not consume cap slots) | `test_test_acceptance_miner_hygiene.py` |
| unit | Prefix-stripping across two describes that collapse to the same `it` text dedupes within one file's mined bullets, first-seen order preserved | `test_test_acceptance_miner_hygiene.py` |
| unit | Two-level nested describe: a dirty OUTER describe name never enters the checked string (only the innermost is ever joined) — regression-proofs the single-level attribution External Plan Review round 2 asked to confirm | `test_test_acceptance_miner_hygiene.py::test_js_nested_describe_only_innermost_prefix_is_considered` |
| unit | A candidate file whose every raw label is dirty falls through to the next sibling candidate, same as a file with no test calls at all (internal plan review finding) | `test_test_acceptance_miner_hygiene.py::test_all_dirty_candidate_falls_through_to_next_sibling` |
| unit | JS: blank/whitespace-only `it`/`test` label dropped, bare and under a dirty describe (External Code Review, glm, medium) | `test_test_acceptance_miner_hygiene.py::test_js_bare_empty_it_label_is_dropped` + `::test_js_empty_it_under_dirty_describe_is_dropped_not_stripped_to_blank` |
| unit | Python: whitespace-only humanized name (all-underscore function name) dropped, not emitted as a blank bullet (External Code Review, glm, low) | `test_test_acceptance_miner_hygiene.py::test_py_whitespace_only_humanized_name_is_dropped` |
| unit | Dedup applies to bullets that were never stripped, not only to prefix-stripped ones (External Code Review, glm, low — scope broadened, see AC) | `test_test_acceptance_miner_hygiene.py::test_js_dedup_also_applies_to_bullets_never_stripped` |
| unit | Every candidate dirty (JS and Python, one test each) → `mine_acceptance_criteria` returns `[]`, the same empty-list shape `generate_adoption_artifacts.py`'s existing `if mined:` guard and `spec_document.py`'s existing TBD-marker fallback already handle for "no sibling test found" | `test_test_acceptance_miner_hygiene.py::test_js_all_candidates_dirty_returns_empty` + `::test_py_all_candidates_dirty_returns_empty` |
| unit | Existing 12 pre-change tests still pass unmodified (no regression) | `test_test_acceptance_miner.py` |
| integration | Loaded via `shared_loader.load_shared_module` through the real package-context import path (`from lib.test_acceptance_miner import ...`, the same path every existing test in both files already uses) — not a naive `lib` import, no `sys.modules` collision with the plugin's own `lib` package | `test_test_acceptance_miner.py` + `test_test_acceptance_miner_hygiene.py` (every test's own import statement exercises this) |

*Note (Stage-1 spec-reviewer, non-blocking): `test_test_acceptance_miner.py`
crossed the 300-line guideline mid-build (Self-Review item 6) and was split
into `test_test_acceptance_miner.py` (pre-existing 12 tests, unmodified) +
`test_test_acceptance_miner_hygiene.py` (all hygiene-filtering tests below).
The table above cites the post-split paths.*

## Verification (medium+)

- **Surface:** none
- **Justification:** pure Python string-filtering logic inside the mining
  helper; no startable web/cli/api surface exists to drive — the miner is a
  library function consumed by adopt's own artifact-generation pipeline, not
  a running service. Verified by unit tests over real describe/it/test
  fixtures, same class of justification the `project-gate-rollout-
  transition` precedent recorded for the sibling gate-side files.
