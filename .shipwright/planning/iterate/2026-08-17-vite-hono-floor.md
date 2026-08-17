# Iterate Spec: vite-hono-floor

- **Run ID:** iterate-2026-08-17-vite-hono-floor
- **Type:** change
- **Complexity:** medium (overridden up from auto-detected `small` — see Complexity Override below)
- **Status:** implemented

## Complexity Override

`classify_complexity.py` returned `small` (scope-keyword match, confidence
0.5). Overridden to `medium` because the request carries positive evidence
beyond a one-line version bump: it requires an ADR-recorded policy decision
among three named alternatives, a possible new enforcement mechanism, and a
demonstrated fail-before/pass-after regression test. `medium` is the tier
that buys the iterate spec, mini-plan-with-alternative and external review
this decision needs.

## Goal

`shared/profiles/vite-hono.json` declares `"hono": "^4.7.0"` — a floor that
admits every version vulnerable to CVE-2026-69207/-71848/-71849/-71850 (fix
line 4.12.34). Raise the floor to the fix line, and decide + record how
shipped profile floors stay honest over time so this does not silently
regress again (it already regressed once: shipwright-webui and leadwright
each hand-patched their own copies without the source profile changing).

## Acceptance Criteria

- [x] `shared/profiles/vite-hono.json`'s `stack.backend.hono` constraint is
      `^4.12.34` (the fix line, not a snapshot of whatever npm resolves
      today).
- [x] A decision on drift-prevention is made and recorded in the ADR
      (decision drop), weighing the three options the card names, with the
      accepted cost stated honestly. **Final decision: option (a)** — see
      the ADR; a general registry+checker mechanism was built and reviewed
      first, then reverted per the Architecture Review below.
- [x] A test asserts the vite-hono profile's hono constraint cannot resolve
      below 4.12.34, asserted on the declared range (not a resolved
      lockfile), and the vulnerable-floor case is shown to FAIL before the
      fix existed, not merely pass after it —
      `shared/tests/test_profile_dependency_floors.py`.

## Spec Impact

- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** No FR in `.shipwright/planning/01-adopted/spec.md`
  describes stack-profile dependency floors or their maintenance policy.
  FR-01.07 (`/shipwright-security`) covers scanning a *scaffolded* project
  after the fact; this change is earlier in the lifecycle — the shipped
  starting state a new project scaffolds *from* — and FR-01.01 explicitly
  keeps vulnerability scanning out of the run pipeline's own FRs. This is
  not a behavior-preserving refactor either (it changes a shipped security
  posture and adds a new enforced check), so it does not route through the
  SIMPLIFY sub-mode despite Spec Impact being NONE.

## Out of Scope

- `supabase-nextjs.json` and other profiles — no known-vulnerable floor
  found there in this pass; not a general dependency-refresh campaign.
- The consumer-side repairs already tracked on shipwright-webui's and
  leadwright's own boards.
- Widening the security gate (shipwright-security / Trivy scan-time
  thresholds) to block medium-severity CVEs — separate decision.

## Investigation — who reads `stack.backend`

Before editing: traced every reader of `shared/profiles/*.json`'s `stack`
block (`shared/scripts/dev_server/profile_config.py`,
`plugins/shipwright-adopt/scripts/lib/profile_matcher.py`,
`plugins/shipwright-design/scripts/checks/setup-design-session.py`,
`plugins/shipwright-test/scripts/lib/test_runner.py`, and
`plugins/shipwright-project/skills/project/references/project-scaffolding.md`).
None of them mechanically transcribe `stack.backend.hono` into a generated
`package.json` — `dev_server`/`test_runner` only read `services`/`testing`;
`profile_matcher` only reads `stack` for brownfield *detection*, not
generation. The `stack` block is descriptive text the `/shipwright-project`
scaffolding step and `/shipwright-build` read as their source of truth for
"which versions to scaffold with" and copy by hand when authoring the new
project's `package.json` — an LLM-agentic consumption, not a script
chokepoint. This matches the evidence in the card: shipwright-webui's
pre-fix `package.json` carried this profile's exact `^4.7.0` string. So the
floor is real and consumed, just not through code that a gate can intercept
at generation time (there is no scaffold script to add a resolver step to —
see Design Notes on option (c)).

## Design Notes

Not UI-facing; no mockups.

Three options were weighed for keeping shipped profile floors honest
(explicit ask). A hand-curated registry + generic checker was built first
(a bounded variant of option (b)), reviewed and hardened through two review
rounds, then reverted after the Architecture Review pass below concluded it
was disproportionate to one known stale floor. Final decision: option (a)
— fix the floor, add one narrow pinned regression test — plus a
near-zero-cost complementary mitigation (a scaffolding-agent instruction,
the light reading of option (c)). Full reasoning in the mini-plan and the
ADR decision drop.

## Affected Boundaries

n/a — no serialized producer/consumer pair changes. The profile JSON itself
is read by scripts listed above; none of those read/write shapes change.

## Confidence Calibration

- **Boundaries touched:** n/a (see Affected Boundaries)
- **Empirical probes run:**
  - Traced every reader of `shared/profiles/*.json` stack blocks (see
    Investigation above) — confirmed no mechanical package.json writer
    exists, ruling out option (c)'s heavy (resolver-script) reading.
  - Built a general registry+checker mechanism first; ran it against the
    real `shared/profiles/vite-hono.json` pre-fix (`^4.7.0`) — confirmed it
    flagged a violation, then re-ran post-fix (`^4.12.34`) — confirmed
    clean. Two review rounds (internal plan review, external `--mode
    iterate`) drove real correctness fixes to it.
  - Ran `--mode architecture` (the pass that asks "should this exist at
    all", over a brief listing options without their rejection reasons) —
    both reviewers pushed back on the mechanism's proportionality
    (`openai=revise`, `deepseek=reject`). Per protocol, stopped and asked
    the operator; the operator chose to simplify. The registry/checker were
    deleted and replaced with the two tests below, which reproduce the same
    fail-before/pass-after evidence directly against the real profile file.
- **Test Completeness Ledger:** see table below.
- **Confidence-pattern check:** asymptote — the first "should this exist?"
  probe (architecture review) DID produce a finding after the plan-review
  pass had already said the design was sound, so per the anti-pattern rule
  a further probe was warranted: the deletion was itself verified (lint +
  full test file run, both green) rather than assumed correct because the
  reviewers said so. Coverage — every row below is `tested`, 0
  untested-testable.

| # | Testable behavior | Disposition | Evidence / reason_code |
|---|---|---|---|
| 1 | `vite-hono.json`'s declared hono range resolves to >= 4.12.34 | tested | `test_profile_dependency_floors.py::test_vite_hono_hono_floor_meets_the_cve_fix_line` PASSED |
| 2 | The same floor-parsing/comparison catches the pre-fix vulnerable value (fail-before proof) | tested | `test_profile_dependency_floors.py::test_floor_parsing_would_have_caught_the_pre_fix_vulnerable_version` PASSED |

## Internal Plan Review (opus-plan-reviewer)

> Reviewed the registry+checker mechanism, which was later deleted per the
> Architecture Review below. Kept here as the historical record — every
> fix this pass drove was real work against real code, even though the
> file it was applied to no longer ships. The findings below no longer
> apply to anything in the diff; nothing here needs further action.

- **Ran:** yes
- **Severity:** high
- **Summary:** Floor bump correct and complete; ADR honest about the manual-registration cost; Spec Impact NONE well-defended. One HIGH (fail-open on an emptied registry, with the real-artifact test passing vacuously in that case) and several MEDIUM/LOW findings on parser strictness, search scope, and untested silent-skip paths.
- **Findings:** (1) HIGH architecture — empty/lost `floors` array fails open, real-artifact test passes vacuously — **fixed** (in the now-deleted mechanism). (2) MEDIUM architecture — option (c) only ruled out in its heavy (resolver-script) reading, a lighter prompt-level variant was not considered — **fixed**, adopted independently of the registry and retained after its deletion. (3) MEDIUM security — `parse_floor` false negatives on upper-bound-only/OR/prerelease ranges — **fixed** (in the now-deleted mechanism; this finding read a pre-fix snapshot, independently already addressed via the external review round moments earlier). (4) MEDIUM completeness — search scoped to `stack` only, entries profile-scoped only — **fixed** (in the now-deleted mechanism). (5) MEDIUM architecture — untested silent-skip paths indistinguishable from tampering, unguarded profile-JSON read — **fixed** (in the now-deleted mechanism). (6) LOW completeness — `docs/guide.md` Chapter 8 mention — **declined**, no precedent (sibling checks aren't named there either) and this isn't a new skill/command/flag/phase; still applies to the final, smaller diff. (7) LOW completeness — test docstring overclaim; enforcement-instrument wording — **fixed** (in the now-deleted mechanism's test file; the final test file has no such docstring claim to overclaim).
- **Known limitations:** none disclosed — every finding was fixed or declined-with-reason, none accepted as a residual gap.
- **Status:** 1 HIGH fixed, 5 MEDIUM fixed, 1 LOW declined (reason recorded, still applies), 1 LOW fixed — superseded by the Architecture Review's broader "should this exist" finding.

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-08-17-vite-hono-floor/architecture_brief.md`
- **Verdicts:** deepseek=reject · openai=revise
- **Smallest thing that would do (per reviewers):** Fix `vite-hono.json`'s hono floor to `^4.12.34` and add one narrowly-scoped, already-in-suite test asserting that profile's declared hono range cannot admit a version below 4.12.34; record option (a) in the ADR. No separate registry, entries, or generic range-parsing machinery.
- **Findings:** `openai` (revise, medium/proportionality) — a generic `(profile, package) -> minimum` registry is permanent, manually-curated inventory-keeping for a problem with one known instance; a direct test expresses the same fact with nothing left to maintain. `deepseek` (reject, high/proportionality + medium/simpler-alternative) — same conclusion, more strongly stated: the registry still depends on the same human discovery it exists to compensate for, so it buys generality without buying more actual coverage; the semver parser, fail-closed grammar and duplicate-entry validation are permanent code for a single curated entry.
- **Reconciliation:** Both reviewers independently recommended the identical alternative without seeing each other's output — strong convergent signal. Per protocol, a `reject` verdict stops the run for the operator rather than being resolved unilaterally. Presented the choice (keep the hardened mechanism / simplify to the reviewers' suggestion / hybrid); **operator chose to simplify**. `shared/config/profile_security_floors.json`, `shared/scripts/tools/check_profile_security_floors.py` and its test file were deleted. Replaced with `shared/tests/test_profile_dependency_floors.py` — the two tests the reviewers described, reproducing the same fail-before/pass-after evidence directly against the real profile file. The scaffold-instruction sentence (light reading of option (c)) was kept: neither reviewer's objection was about it, and internal plan review had independently recommended it on its own merits.

## Verification (medium+)

- **Surface:** none
- **Justification:** This changes the Shipwright framework's own shipped
  profile data + a scaffolding reference doc, and adds one pinned pytest
  test; there is no `dev_server` / web/CLI/API surface to start for the
  monorepo itself (per `shipwright_run_config.json`, this repo is a
  library/framework — "no deployable web service in the repo root"). The
  verification instrument is `shared/tests/test_profile_dependency_floors.py`,
  run at F0/F0.5/F11 like any other unit test.
