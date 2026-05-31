# Path A: FEATURE (new functionality)

Follow the Phase Matrix in SKILL.md Section 6 to determine which steps run.
Step 7 / Step 7.5 / Step 8 / Step 11a / Step 11b headings are kept inline in
SKILL.md because they are anchors for several drift-protection tests.

## Step 1: Iterate Spec (medium+ only)

Create `.shipwright/planning/iterate/{date}-{short-description}.md` using
this template:

```markdown
# Iterate Spec: {short-description}

- **Run ID:** {run_id}
- **Type:** {feature | change | bug}
- **Complexity:** {level}
- **Status:** draft

## Goal
{1-2 sentences — populated from interview answers (Section G)}

## Acceptance Criteria
- [ ] {AC from interview — concrete, testable}
- [ ] {AC 2}

## Spec Impact
{Classify how this iterate changes the FR spec — see Step 2.}
- **Classification:** {add | modify | remove | none — one or more}
- **ADD** (new FR appended): {FR-XX.YY — short title, or `none`}
- **MODIFY** (existing FR changed): {FR-XX.YY — what changed, or `none`}
- **REMOVE** (FR retired → `## Removed Requirements`): {FR-XX.YY, or `none`}
- **NONE justification:** {required only when Classification is solely
  `none` — why this feature/change touches no FR}

## Out of Scope
- {from interview answer — what explicitly will NOT be done}

## Design Notes
{Filled during Design Check. Include affected mockup files,
 design tokens applied, new vs modified components, deviations
 from visual guidelines with justification}

## Affected Boundaries
{Producer/consumer pairs for any changed serialized format.
 Triggers Boundary Probe sub-step in Build TDD when `touches_io_boundary`
 risk flag fires.

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| {file:fn} | {file:fn} | {env / JSON / YAML / ...} |

If no boundaries touched: write `n/a` with one-line justification.}

## Confidence Calibration
{Mandatory at medium+; mandatory at small when `touches_io_boundary`
 fires. Empirical probes run before F0 Fresh Verification Gate.

- **Boundaries touched:** {list from "Affected Boundaries" above}
- **Empirical probes run:** {one-line per probe + finding — real
  round-trip / edge-case tests, not "I re-read the diff"}
- **Test Completeness Ledger:** {every testable behavior this diff
  introduces/changes — one row each, `tested` (evidence) or `untestable`
  (closed-vocab reason_code). The "could-test-but-didn't" disposition is
  forbidden. Mirror into the F5 `iterate_latest.test_completeness` block;
  the F11 verifier `check_test_completeness_ledger` enforces it.}

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | {behavior} | tested | {test_name::case PASSED} |
  | 2 | {behavior} | untestable | {requires-prod-credential ·
  requires-external-nondeterministic-service · requires-physical-device ·
  requires-manual-visual-judgment · requires-interactive-tty ·
  covered-by-existing-test} |

- **Confidence-pattern check:** {asymptote (depth): has any "are you
  confident?"-style question already produced "yes" + a subsequent finding
  this run? If yes, run one more probe before F0. AND coverage (breadth):
  every ledger row `tested`/`untestable`, 0 untested-testable?}}

## Verification (medium+)
{Mandatory at medium+. The runner that will produce the F0.5
 surface_verification block.

- **Surface:** web | cli | api | none
- **Runner command:** {exact command F0.5 will execute}
- **Evidence path:** {where output lands}
- **Justification (only if surface=none):** {one line — why no startable
  surface exists for this change}}
```

## Step 2: Spec Update — classify the Spec Impact (always)

1. Identify which spec file(s) cover the affected area.
2. **Classify the spec impact** as one or more of ADD / MODIFY / REMOVE, or
   NONE. Record it in the iterate spec's `## Spec Impact` section
   (medium+) and carry the same FR IDs into F7 (`--spec-impact`,
   `--affected-frs`, `--new-frs`).
   - **ADD** — a new endpoint, page, flow, or user-visible capability:
     append a new FR table row + an acceptance-criteria block. The new
     FR ID goes to F7 `--new-frs` (and `--affected-frs`).
   - **MODIFY** — an additive side-effect or changed behavior of an
     existing FR: update the FR table-row description + append new
     `- (E) Given … when … then …` acceptance-criteria lines covering
     the new behavior + any idempotency / no-op guarantees. The FR ID
     goes to F7 `--affected-frs`. Reference the run_id + ADR.
   - **REMOVE** — the change deletes a user-visible capability: move the
     FR row out of `## 2. Functional Requirements` into a
     `### Removed Requirements` subsection — never silently delete it.
   - **NONE** — a behavior-preserving internal refactor with no
     user-visible change. Record a one-line justification.
3. **NONE is a classification that must be *justified*, not a default.**
   The Phase Matrix marks this step `always` for FEATURE — that is
   load-bearing. The F11 finalization verifier FAILS a feature/change
   iterate whose commit touched no `spec.md` unless `spec_impact=none` +
   a justification was recorded at F7.
4. If `shipwright_sync_config.json` exists, add/update mappings for the
   affected files.

> **AC shape (medium+).** ACs MUST be assertion-shaped (mechanically
> verifiable by the F0.5 runner), not story-shaped. Story-shaped ACs
> cannot be empirically driven and silently degrade F0.5 to spec-only
> authorship.

## Step 3: Mini-Plan (small: inline, medium: persisted)

See `references/iteration-planning.md` for protocol.
- Small: inline in session
- Medium+: save as `.shipwright/planning/iterate/{date}-{desc}-miniplan.md`

## Step 3b: User Approval Gate (medium+)

Present the iterate spec + mini-plan summary to the user:

> "Here is my plan:
> - **Scope:** {AC summary from iterate spec}
> - **Approach:** {mini-plan summary}
> - **Out of scope:** {boundaries from iterate spec}
>
> Shall I proceed, or would you like to adjust scope, ACs, or approach?"

**CRITICAL: Wait for user approval before proceeding to build.**

For trivial/small: skip (the confirmation question in Section G is sufficient).

## Step 4: External LLM Review (medium auto, or --review flag)

See `references/iteration-planning.md` for invocation.

## Step 5: Design Check (if UI)

See `references/design-and-testing.md` for 2-tier protocol.

## Step 6 — Build (full body)

The Step 6 / Step 7 / Step 7.5 / Step 8 / Step 9 / Step 10 / Step 11a /
Step 11b / Step 12 / Step 13 / Step 14 headings remain in SKILL.md so the
existing drift-protection tests anchor on them. SKILL.md carries the
governance-rule anchors (Test-Update-Klausel, Registry-driven SSoT,
Silent-skip CI-discipline) inline; this file is reference prose only.

### Migration apply (if migration files were created during build)

Read `migrations` config from the stack profile (loaded in Step B2).

**Preflight + Apply:**
1. Run `{migrations.preflight_cmd}` — verify environment ready
2. If `safe_nonprod_only` is true, verify target is non-production
3. If preflight fails: Print diagnostic, instruct user to fix. **Stop.**
4. Run `{migrations.apply_cmd}`
5. If apply fails: **Stop immediately.** Do not run tests. Ask user.
6. Verify with `{migrations.list_cmd}`

**Post-migration manual steps:**
7. Check `post_apply_manual_steps` — match `trigger_tag` against changes
8. If matched: inform user, note blocked test areas, wait for confirmation

Apply immediately after creating the migration, before running tests.

### Test commands

```bash
npx vitest run
npx tsc --noEmit

# Integration tests (if CRUD/DB changes)
npx vitest run --config vitest.integration.config.ts

# pgTAP tests (if new RLS migrations)
supabase test db
```

## Step 13: Escalation Check

See `references/mid-flight-escalation.md`.

## Step 14: Finalize

Go to Finalization (F0 .. F12) in SKILL.md.
