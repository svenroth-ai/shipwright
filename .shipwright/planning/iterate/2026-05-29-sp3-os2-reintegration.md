# Iterate Spec — SP3 + OS2 Post-Campaign-B Reintegration

- **Run ID:** `iterate-2026-05-29-sp3-os2-reintegration`
- **Triage ID:** `trg-89d3caa4` (P2.recovery — SP3 + OS2)
- **Intent:** FEATURE (new framework capability across two plugins)
- **Complexity:** medium — `cross_split` (changes span shipwright-iterate +
  shipwright-project planning splits) forces a medium floor: full review +
  full test suite.
- **Spec Reference:** `Spec/external-frameworks-integration.md` §SP3 + §OS2 +
  §6.2 + §10 (post-mortem: §6.2 inline-with-Campaign-B path was missed because
  Campaign B sub-iterate plans never referenced SP3/OS2).

## Problem

Campaign B (PRs #89–#102, merged 2026-05-26) split the iterate and project
`SKILL.md` files but did NOT carry the two patches §6.2 prescribed as riding
inline:

- **SP3** — a `systematic-debugging` sub-skill (`F-debug.md`) inside
  `/shipwright-iterate`. Verified missing 2026-05-27: the F-references list
  goes F0/F0.5/F1/F2/F3/F3a/F4/F5/F5b/F5c/F6/F6.5/F7/F7b/F11/F12 — no F-debug.
- **OS2** — an "assumptions-first" pre-phase block in `/shipwright-project`.
  Verified missing 2026-05-27: grep for `assumptions-first|surface
  assumptions|inferred assumptions` returns zero hits in shipwright-project.

Inline-mitnehmen is no longer an option now that Campaign B is closed, so this
bundle re-establishes both patches as a standalone iterate.

## Spec Impact (FEATURE → classify)

**NONE** against any app `spec.md`. This is a framework-internal change to two
plugin skills (runtime prompts + drift-protection meta-tests). The shipwright
monorepo is an adopted `library`-scope project with no FR rows tracking
plugin-prompt wording. Recorded in the iterate ADR.

## Acceptance Criteria

1. **AC-1 (SP3 file):** `plugins/shipwright-iterate/skills/iterate/references/
   F-debug.md` exists, ≤400 LOC, carries the Iron Law verbatim — "NO FIXES
   WITHOUT ROOT CAUSE INVESTIGATION FIRST" — and a 4-phase structure
   (Read Error → Reproduce → Recent Changes → Component-Boundary
   Instrumentation), with an MIT attribution footer to obra/superpowers
   (© Jesse Vincent).
2. **AC-2 (SP3 routing):** the iterate Kern `SKILL.md` routes BUG intent
   through F-debug before any fix, and states the reviewer gate (reject a fix
   that patches a symptom, not the root cause). `path-c-bug.md` points at
   F-debug as the 4-phase protocol and carries the reviewer-gate language.
   Kern stays ≤300 LOC.
3. **AC-3 (OS2 block):** `plugins/shipwright-project/skills/project/references/
   interview-protocol.md` carries an "assumptions-first" pre-phase block —
   before clarifying questions, the agent lists inferred assumptions
   explicitly (web-app vs CLI, stack, persistence, auth model) and asks for
   correction — with an MIT attribution footer to addyosmani/agent-skills
   (© Addy Osmani). Patch ≤80 LOC delta.
4. **AC-4 (OS2 surfacing):** the project Kern `SKILL.md` Step 1 surfaces the
   assumptions-first behavior so it fires before the first clarifying question.
   Kern stays ≤300 LOC.
5. **AC-5 (tests):** new drift-protection tests
   `plugins/shipwright-iterate/tests/test_f_debug_routing.py` and
   `plugins/shipwright-project/tests/test_assumptions_first_block.py` pin both
   patches (file existence, Iron Law, 4 phases, attribution, Kern wiring).
6. **AC-6 (no bloat trip):** F-debug.md ≤400 LOC; interview-protocol.md delta
   ≤80 LOC; no new bloat-baseline crossing.

## Affected Boundaries

- `plugins/shipwright-iterate/skills/iterate/references/F-debug.md` (NEW)
- `plugins/shipwright-iterate/skills/iterate/SKILL.md` (Path C + Phase Index)
- `plugins/shipwright-iterate/skills/iterate/references/path-c-bug.md`
- `plugins/shipwright-project/skills/project/references/interview-protocol.md`
- `plugins/shipwright-project/skills/project/SKILL.md` (Step 1)
- Two new test files (meta-tests; no runtime IO boundary)

No `*_config.json` / `*_state.json` / `.env*` / `hooks.json` touched →
`touches_io_boundary` NOT set. No app web/CLI surface touched.

## Confidence Calibration

- **Boundaries touched:** two plugin SKILL.md Kerns + two reference docs +
  two meta-test files. All markdown/prose + pytest drift-protection. No
  serialized-format producer/consumer, no runtime config IO.
- **Empirical probes run:**
  - `wc -l` on both Kerns pre-edit (iterate 295, project 229) → both have
    headroom under the 300-LOC drift cap; iterate edited via existing-line
    replacement to avoid net growth.
  - Read `test_skill_references_link.py` (both plugins) → confirmed
    `test_every_kern_link_resolves` requires any new `references/*.md` link to
    resolve on disk; F-debug.md is created before the Kern link is added.
    Confirmed `EXPECTED_F_REFERENCES` is a closed set with NO reverse
    disk→registry drift test, so a new `F-debug.md` does not violate it.
  - Ran the two new tests RED before implementation, GREEN after.
  - Ran both plugins' full pytest suites after implementation.
- **Edge cases NOT probed + why acceptable:** the runtime *behavioral* probes
  in the bundle (a live `/shipwright-iterate "fix bug…"` that routes through
  F-debug; a live `/shipwright-project "build a todo app"` that lists
  assumptions first) are prompt-execution probes that cannot be asserted from
  pytest. They are covered structurally by the drift-protection tests (the
  routing language + Iron Law + assumptions block must exist and be wired);
  the live behavior follows from the prompt the agent reads.
- **Confidence-pattern check (asymptote):** no yes-then-bug pattern observed;
  the failure mode here is a silently-broken drift test (link not resolving,
  Kern over 300 LOC), all of which are caught by running the full suites — so
  the green suite is the empirical floor, not self-assessed confidence.

## Out of Scope

- KA1 (Karpathy in constitution), SP5 (anti-slop PR template) — shipped/tracked
  under P1.1, not here.
- The README/guide.md Acknowledgments patches (§8) — part of P1.1.
