# Iterate Spec: stack profiles declare their test roots (change, medium)

Run-ID: iterate-2026-11-02-profile-declared-test-roots
Origin: GitHub issue #972 (items 1 and 2). Item 3, the "no test folder resolved" warning, shipped in PR #980.

## Problem
The `test_links` collector scans only top-level folders (`tests`, `test`, `__tests__`, `e2e`,
`integration-tests`, `src`, `app`, `packages`). A project built from the `vite-hono` profile keeps its
tests below `server/` and `client/` (`server/tests`, `client/src`, `client/e2e`), so the collector scans
nothing and every requirement reads as untested. Today the only remedy is a hand-written
`traceability.test_roots` in `shipwright_compliance_config.json`, which a new project does not know about.

## Change
A stack profile may declare `traceability.test_roots` (list of folder names or fixed-depth globs relative
to the project root, the same vocabulary as the compliance config). The collector resolves its scan roots in
this order:

1. `traceability.test_roots` in `shipwright_compliance_config.json` (explicit project choice, replaces everything below, unchanged).
2. `traceability.test_roots` of the project's resolved stack profile (profile named in `shipwright_run_config.json`).
3. The conventional top-level defaults (unchanged). A profile list that is empty, or whose folders all fail to exist, counts as absent (defaults apply) and, when non-empty, writes one warning naming the profile.

The `vite-hono` profile declares `server/tests`, `server/src`, `client/src`, `client/e2e`, `client/tests`, `e2e`.
Single folders that do not exist are dropped silently, as for the config today. Only user-independent profiles count: the lookup uses the project's `.shipwright/profiles` and the bundled profiles, never `~/.shipwright/profiles`, so the manifest is the same locally, in CI and in the gate archives.

## Decisions to review
- Reading the profile: the compliance plugin appends `shared/scripts` to `sys.path`, imports `profile_consumer`, removes the entry (the documented stack-profile import convention). No cross-plugin import of another plugin.
- Failure: a missing, broken or sentinel (`generic`, `detecting`) profile never crashes the regen. Sentinel or absent profile means step 3 silently; a broken profile writes one stderr line and falls back to step 3.
- Precedence is replace, not union: a project that writes its own `test_roots` keeps exact control.
- The F11 cross-layer gate regenerates on throwaway archives of the merge base and HEAD; it uses the same resolver, so the archive must contain `shipwright_run_config.json` (tracked) and any project profile under `.shipwright/profiles/` (tracked by the managed gitignore block). A user-level profile (`~/.shipwright/profiles`) is outside the archive, so the gate and a local run could disagree for such a project; recorded as a known limit.

## Out of scope
Profile-declared prune dirs, other profiles (supabase-nextjs etc.) beyond vite-hono, a `--playwright-base` option.

## Acceptance
- AC1: with no compliance config and `profile: vite-hono` in the run config, a tagged test in `server/tests` and one in `client/e2e` are linked into the manifest.
- AC2: a `test_roots` in the compliance config still wins over the profile.
- AC3: an unknown or broken profile name writes one stderr line and the defaults apply; `generic` and no run config stay silent.
- AC4: the schema accepts the new key and rejects a non-list value; every bundled profile still validates.
- AC5: the F11 gate regen on an archive of such a project scans the same roots.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** Design sound; sys.path removal, call-time import, AC5 test location, user-level profile dir and 300-line cap would break the plan as written.
- **Findings:** sys.path guard (high) fixed; module-level import (high) fixed; AC5 test in shared/tests (high) fixed; user-level profile dir (medium) fixed; gitignored run config (medium) disclosed; quiet/dedupe (medium) fixed; union/fallback with defaults (medium) fixed; 300-line cap (medium) fixed; shared entry loop + OSError (low) fixed; docs/changelog (medium) fixed; one-time manifest change (low) disclosed; caching (low) declined, five cheap reads.
- **Known limitations:** run config gitignored => gate archives use default roots; one-time manifest change for existing vite-hono projects.
- **Status:** 10 fixed, 2 disclosed, 1 declined

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes
- **Severity:** low
- **Summary:** Build option A; profile roots must pass the same path checks as the config key.
- **Findings:** necessity (low) accepted; smallest option A, reject D (low) accepted; path escape via project profile (medium) fixed by routing profile entries through the shared entry loop; two schemas drift (low) mitigated by one shared loop and string-item schema; warning must name the source (low) fixed; user-level limit (low) removed by excluding the user dir; profile_consumer import collisions (low) checked, no bare lib/scripts import.
- **Known limitations:** none
- **Status:** 5 fixed, 0 disclosed, 0 declined

## External Plan Review (glm, openai)
- **Verdicts:** glm=revise · openai=revise
- **Findings:** union with defaults contradicted the approved replace precedence (fixed: reverted to replace per tier); profile declares roots but none exist (fixed: warning naming the profile); user-level profile restriction needs an actionable diagnostic (fixed); gate archive test must use a real git repo (fixed); shared-dir-unreachable test (fixed); gitignored run config and sys.path convention (disclosed); schema blast radius (disclosed, existing behaviour).
- **Status:** plan revised, no high finding declined

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-11-02-profile-declared-test-roots/architecture_brief.md`
- **Verdicts:** glm=approve · openai=approve
- **Smallest thing that would do (per reviewers):** as proposed (option A)
- **Findings:** user-level divergence not observable (low, handled by the not-found diagnostic); sys.path convention is accrued tech debt (low, recorded)
- **Reconciliation:** option D (scaffold writes the setting) rejected by all four reviewers: it freezes a profile default into a per-project override. Option B rejected: changes every project's manifest.
