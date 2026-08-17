# Mini-Plan: vite-hono-floor

- **Run ID:** iterate-2026-08-17-vite-hono-floor

## Work Breakdown

1. Raise `shared/profiles/vite-hono.json` `stack.backend.hono` from
   `^4.7.0` to `^4.12.34` (fix line for CVE-2026-69207/-71848/-71849/-71850).
2. Add `shared/config/profile_security_floors.json` — a small, hand-curated
   registry: `{profile, package, min_safe_version, cve_ids, recorded_date,
   note}`. Seeded with one entry (hono / vite-hono / 4.12.34).
3. Add `shared/scripts/tools/check_profile_security_floors.py` — reads the
   registry + `shared/profiles/*.json`, parses each declared range's floor
   (strip the `^`/`~`/operator prefix, compare the dotted-version tuple),
   and reports any profile whose declared floor resolves below its
   registered minimum. CLI exit 1 on violation, 0 clean — same shape as
   `check_ci_gate_coverage.py` and friends in the same directory.
4. Add `shared/scripts/tools/tests/test_profile_security_floors.py` —
   exercises the real registry/profiles (post-fix, must be clean) plus a
   `tmp_path` fixture proving the checker *would* have caught the
   pre-fix `^4.7.0` floor (the fail-before/pass-after requirement).
5. Record the decision (chosen mechanism + accepted cost + rejected
   alternatives) as an ADR decision drop at F3.

## Alternative Approach Considered

**Alternative: ship only the one-line fix (option (a), bump-on-discovery),
with no new checker.** Cheapest, zero new surface area, and explicitly
called "a legitimate outcome" by the card if chosen and stated honestly.

**Why the chosen approach (a bounded static-registry checker) instead:**
This exact failure already happened once — the profile drifted silently and
two consumer repos independently rediscovered and hand-patched it. A
registry + checker costs one script, one small JSON file, and a
test file; it is the same shape as several checks this repo already runs
(`check_ci_gate_coverage.py`, `check_repair_safety.py`) and slots into
`shared/scripts/tools/tests`'s existing CI wiring (`ci.yml`'s per-dir shared-
tests loop) with zero `ci.yml` changes — corrected from an earlier draft
that named `shared/tests` as the collecting root; confirmed by reading
`ci.yml` directly. The enforcement instrument is that pytest test, not a
`ci.yml` step of its own — an accepted cost recorded in the ADR. Unlike the
card's literal option (b), it needs no live vulnerability-database network
call — the registry is hand-maintained, same trust model as this repo's
existing `shipwright_accepted_risks.yaml` / Trivy-register pattern (no
Dependabot, by explicit prior decision). Its honestly-accepted cost: it only
catches what has been manually registered — it is not a live CVE feed, and
a future CVE against a floor not yet in the registry will not be caught
until someone adds an entry (same limitation this repo already accepts
elsewhere). That cost is small enough, and the regression risk demonstrated
enough (two independent hand-patches), to prefer it over doing nothing
structural.

**Why not literal option (c) (scaffold-time resolution):** ruled out by the
Investigation in the iterate spec — there is no mechanical scaffold step
that writes `stack.backend` values into a generated `package.json`; that
consumption happens by an LLM agent reading the profile as descriptive text
during `/shipwright-project` Step 7 / `/shipwright-build`. There is no code
chokepoint to attach a "resolve latest matching version" step to without
inventing one, which is a materially larger change than this card scopes
(and the card explicitly says do not open a general dependency-refresh
campaign here). This rules out only the *resolver-script* reading of
option (c). Internal plan review (opus-plan-reviewer) correctly pointed out
that ruling out the heavy reading does not rule out a near-free lighter one:
since the actual consumption is LLM-agentic, instructing that agent directly
is cheap. Adopted alongside the registry — `shared/profiles/vite-hono.json`'s
`notes` field and `plugins/shipwright-project/skills/project/references/
project-scaffolding.md` now both say the `stack` versions are minimums to
resolve-latest-against, not strings to copy verbatim. This does not replace
the registry gate (a prose instruction is not enforced), it is defense in
depth against the SAME root cause the registry gate catches after the fact.

## Review Findings — Reconciliation

External review (`external_review.py --mode iterate`, deepseek=approve,
openai=revise) and internal plan review (`opus-plan-reviewer`, severity
high) both ran; every finding was triaged below. Full findings text lives in
the run's review record; this is the disposition summary.

- **[fixed, HIGH]** A registry entry list that goes empty/lost makes the
  checker report clean, and the real-artifact test asserting `violations ==
  []` would pass vacuously in that case too. Added
  `test_registry_pins_the_hono_entry_at_or_above_the_fix_line`, which reads
  the registry's own content and fails if the hono entry is ever removed or
  weakened — independent of whether `check_profile_floors` still returns
  anything.
- **[fixed, MEDIUM — external, both providers]** `parse_floor` used to
  regex-search for "the first dotted number", which mis-scores comparator
  sets, `||` disjunctions, upper-bound-only ranges, and prerelease tags.
  Replaced with a fully-anchored simple-grammar match that raises
  (fail-closed, reported as a violation) on anything outside
  `^`/`~`/`>=`/`=` + a bare version — verified this also resolves the
  internal review's independently-raised version of the same finding (that
  finding read a pre-fix snapshot of the file; re-verified against the
  fixed parser directly, all four cases now raise).
- **[fixed, MEDIUM — internal]** `find_package_version` was scoped to
  `stack` only, missing the `{"framework": name, "version": range}` shape
  `testing.unit`/`testing.e2e` use for vitest/Playwright floors. Now
  searches the whole profile document (excluding profile-file metadata keys
  like the profile's own `version`) and recognizes both shapes.
- **[fixed, MEDIUM — internal]** Entries were profile-scoped only, so the
  same vulnerable package in a second profile needed its own entry. Added
  `"profile": "*"` wildcard support.
- **[fixed, MEDIUM — internal]** The two silent-`continue` paths (registry
  entry naming a missing profile file; registered package no longer
  declared) were indistinguishable from tampering and untested. Added
  `find_stale_registry_entries` (printed as a non-failing `NOTE` by the
  CLI) plus tests for both paths. Also wrapped the per-profile JSON read in
  `ProfileFloorError` (was a raw, unguarded `json.loads`).
- **[declined, LOW — internal, docs/guide.md Chapter 8]** Checked precedent:
  neither `check_ci_gate_coverage.py` nor `check_repair_safety.py` — the two
  most comparable existing checks — is named in `docs/guide.md`'s
  quality-gates chapter. This is an internal pytest-level check, not a new
  skill/command/flag/pipeline-phase (the trigger CLAUDE.md names for a guide
  update), so no entry was added, consistent with the sibling checks.
- **[fixed, LOW — internal]** `test_no_violation_for_packages_outside_the_registry`'s
  docstring claimed to cover "a profile with no registry entry at all" but
  the fixture only had an unregistered *package* inside a registered
  profile. Added a second, genuinely unregistered profile
  (`supabase-nextjs`) to the fixture so the docstring is now accurate.
- **[declined — verified false, MEDIUM x2, external both providers +
  internal]** All three raised the same concern: is `shared/scripts/tools/tests`
  actually collected by CI, or does the plan only assert that it is? Read
  `.github/workflows/ci.yml` line 172 directly: `for dir in shared/tests
  shared/scripts/tests shared/scripts/tools/tests; do ... pytest "$dir" ...`
  — confirmed the directory is in the loop today, no `ci.yml` change
  needed. The mini-plan's own wording error (see above) is what made this
  look uncertain; the CI wiring itself was never actually missing.

## Test Plan

- New: `shared/scripts/tools/tests/test_profile_security_floors.py` (see
  Test Completeness Ledger in the iterate spec for the five behaviors
  covered).
- Existing: no existing test currently reads `shared/profiles/vite-hono.json`
  for its hono version, so no existing test needs updating; confirmed via
  `grep -rn "vite-hono" shared/tests plugins/*/tests`.

## Post-Architecture-Review Update — mechanism reverted

Everything above this line describes and reconciles findings against the
registry+checker mechanism. That mechanism was subsequently deleted: the
`--mode architecture` pass (`openai=revise`, `deepseek=reject`) concluded it
was disproportionate to one known stale floor, and the operator — asked per
protocol on the `reject` verdict — chose to simplify. See the iterate spec's
`## Architecture Review` section and the ADR for the full reconciliation.

**Final test plan:** `shared/tests/test_profile_dependency_floors.py` — two
tests: the pinned real-profile assertion, and the fail-before-proof test.
Both green; see the iterate spec's Test Completeness Ledger. The Work
Breakdown's items 2-4 above (registry, checker, checker's test file) were
built, then removed; item 1 (the floor bump) and item 5 (the ADR) stand as
originally planned, with the ADR's content rewritten to record the final
decision.

## Stage-2 Code Review — Reconciliation

`code-reviewer` returned 5 LOW findings against the simplified diff:

- **[fixed]** The scaffolding-instruction sentence had been appended to
  `vite-hono.json`'s `notes` field, a prose blob with no other readers.
  Moved to a new `stack._comment` key (sibling to `runtime`/`frontend`/
  `backend`) — confirmed safe by re-reading `profile_matcher.py`'s
  `_flatten_profile_deps` (only reads named `runtime`/`frontend`/`backend`/
  `auth` sub-keys, never a blind `stack.values()`); `notes` reverted to its
  original text. Re-ran `test_dev_server_multiservice.py` (4 passed) and
  `plugins/shipwright-adopt/tests/test_stack_detector_multi_service.py`
  (11 passed).
- **[declined — no blocking change requested]** The `project-scaffolding.md`
  doc-side instruction is "close to decorative" per the reviewer (an LLM
  reading a scaffolding reference doc, not an enforced check). Left as-is:
  it is the light reading of option (c), a real (if unenforced) mitigation,
  and the reviewer did not ask for a change.
- **[fixed]** The two tests didn't exercise the identical read+compare path
  — the pass case read the profile file, the fail-before case called `_floor`
  on a hardcoded string via separate assertions. Parametrized into one
  `test_hono_floor_meets_the_cve_fix_line` over
  `[(declared_from_profile, True), ("^4.7.0", False)]`, both cases now run
  through the same `_floor()` call and the same comparison.
- **[fixed]** `_REPO_ROOT` used `parent.parent.parent`; the repo's sibling
  test files (e.g. `test_accepted_risks*.py`) use `parents[2]`. Matched the
  convention.
- **[declined, recorded in ADR]** The `stack._comment` mitigation only
  touches `vite-hono.json`, not `supabase-nextjs.json` or other profiles.
  Recorded in the ADR's Accepted Cost section rather than extended: the card
  explicitly scoped one known-vulnerable floor and ruled out a general
  dependency-refresh campaign; no vulnerable floor was found in the other
  profiles in this pass.

## External Code-Review Cascade — Reconciliation

`external_review.py --mode code` (medium+, independent of the internal
cascade per `iteration-reviews.md`) ran twice:

- **First call** fed a diff filtered to only the three code-level files
  (test, profile JSON, scaffolding doc), excluding the ADR/spec/mini-plan.
  `openai` returned `revise`: "the diff does not add or modify the
  referenced ADR decision drop," i.e. it could not see the ADR because it
  was never shown it. `deepseek` returned `degraded` (empty reply). This
  is the documented failure mode of a filtered diff producing a false
  finding, not a real defect — the ADR exists and is part of this run's
  diff, just not the slice that was sent.
- **Second call** used the complete diff — the three code files plus the
  ADR, iterate spec, and mini-plan. `openai` returned `approve`: "the ADR
  records and honestly bounds the chosen drift-prevention approach... ship
  as-is." `deepseek` again returned `degraded` (empty reply both times —
  a provider-side issue, not diff-related).
- Recorded the run's `external_code` review-record row from the second
  (complete-diff) call, `--contradiction-resolution` noting deepseek's
  degraded (not conflicting) status.
