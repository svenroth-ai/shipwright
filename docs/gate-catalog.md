# Single-Session Phase-Gate Catalog

> **GENERATED** from `shared/config/gate_catalog.json` by
> `gate_policy.render_catalog_markdown` (Campaign 2026-07-07, SS2). Do NOT
> edit by hand - edit the JSON and regenerate (shell-agnostic writer):
> `uv run shared/scripts/tools/resolve_gate_policy.py --render-doc --output docs/gate-catalog.md`

Single-session pipeline phase-gate catalog (Campaign 2026-07-07, SS2). SSoT for every interactive AskUserQuestion + END-TURN gate across the project/design/plan/build/deploy phase skills, with a per-gate non-interactive policy. Read by resolve_gate_policy.py; consumed by phase-runner subagents under run_config.mode == 'single_session'. The mechanism is INERT (every gate resolves to 'interactive') for any config that is not an explicit single_session run - a standalone or adopted project is unaffected. docs/gate-catalog.md is GENERATED from this file (gate_policy.render_catalog_markdown) - edit here, then regenerate.

## Policies

- **`auto-default`** - Under single_session the subagent proceeds with the documented default_answer and does NOT call AskUserQuestion / end the turn.
- **`orchestrator-approve`** - Under single_session the subagent STOPS and returns a gate-pending result to the orchestrator to surface to a human; it never auto-answers. A future autonomous orchestrator MAY surface-and-wait or auto-approve ONLY gates with constitution=false; a constitution=true orchestrator-approve gate (e.g. skip-test-layer, >3 failed fixes, a missing secret) always reaches a human.
- **`hard-stop`** - Under single_session the subagent ALWAYS stops for an explicit human decision; no autonomy setting bypasses it. Constitution-locked class (PROD deploy, destructive SQL, migration-apply failure, rollback).

**Covered phases:** project, design, plan, build, deploy.
**Pending (follow-up):** test, changelog, security - test / changelog / security phase gates are a deliberate SS2 follow-up (not silently dropped). This catalog is additive - extend `gates` to cover them. The sub-iterate spec scoped SS2 to project/design/plan/build/deploy.

## `project`

| Gate | Policy | Fires | Constitution | Summary / default |
|---|---|---|---|---|
| `project.pipeline-vs-standalone` | auto-default | never | no | A.1 first-turn: full pipeline vs standalone spec. Skipped when shipwright_run_config.json already exists (the orchestrator pre-writes it). **Default:** Full Pipeline |
| `project.target-directory` | auto-default | never | no | Inline/chat only: where to create the project. Skipped when the pipeline supplies the project path. **Default:** The project name inferred from the seed description (or the current directory). |
| `project.out-of-sequence-continue` | orchestrator-approve | never | no | No dispatch token (phaseTaskId) was handed to the skill, yet a driven run is LIVE (get_phase_context: requires_out_of_sequence_warning). A hand-invoked /shipwright-project during a driven run; the orchestrator owns sequencing, so it should not fire in a well-formed single-session run. |
| `project.session-conflict` | orchestrator-approve | never | no | Existing session/state conflict at setup. 'Start fresh' discards existing work and must never be auto-picked; a fresh pipeline dir has no conflict. |
| `project.surface-assumptions` | auto-default | always | no | Pre-interview: surface inferred assumptions for correction (inline prose, borderline gate). **Default:** Proceed with the inferred assumptions (derived from the seed requirements). |
| `project.interview` | auto-default | always | no | The requirements interview (adaptive depth). The primary interactivity surface; the pipeline always supplies a seed. **Default:** Answer each requirements question from the seed description/spec and record it as an assumption; a pipeline run always carries a seed to derive from. |
| `project.manifest-confirm` | auto-default | always | no | Step 4: confirm the proposed split-structure manifest before creating split directories. **Default:** Approve the proposed split/decomposition manifest as-is (agent-generated and regenerable). |
| `project.supabase-project-ref` | orchestrator-approve | conditional | no | supabase-nextjs profile only: the external Supabase project ref. Cannot be invented; surface to a human or defer linking. |
| `project.supabase-access-token` | orchestrator-approve | conditional | yes (locked) | supabase-nextjs profile only: the Supabase access token (a secret). Never fabricate or hardcode (constitution NEVER); surface or defer linking. |

## `design`

| Gate | Policy | Fires | Constitution | Summary / default |
|---|---|---|---|---|
| `design.out-of-sequence-continue` | orchestrator-approve | never | no | No dispatch token (phaseTaskId) was handed to the skill, yet a driven run is LIVE (get_phase_context: requires_out_of_sequence_warning). A hand-invoked /shipwright-design during a driven run; the orchestrator owns sequencing. |
| `design.brand-extraction-confirm` | auto-default | conditional | no | Step 2.5: confirm auto-extracted brand tokens. Fires only when an existing website is known. **Default:** Use the site-extracted brand tokens as the foundation (they remain overridable downstream). |
| `design.design-interview` | auto-default | always | no | Step 3: 3-5 design-system/brand/layout questions. Every field has a documented default. **Default:** Untitled UI flavor + Clean & Modern character + Sidebar nav (or the Step 2.5 extracted tokens if present); the visual direction is re-checked at design.preview-approval. |
| `design.screen-list-confirm` | auto-default | always | no | Confirm the proposed screen list after the design interview. **Default:** Accept the FR-derived screen list (re-verified by the FR-Coverage Gate at finalize). |
| `design.preview-approval` | orchestrator-approve | always | no | Step 3.5: first pixels-seen checkpoint (3 preview screens). SENSITIVE (Sven): a human must eyeball the visual direction - never auto-approved. |
| `design.chrome-nav-confirm` | auto-default | always | no | Step 3.7: confirm the derived chrome/navigation structure. **Default:** Accept the screen-list-derived navigation (mechanical; cheaply corrected later via Chrome Change Propagation). |
| `design.review-loop-finalize` | orchestrator-approve | always | no | Step 8.5: all-screens sign-off + phase exit. SENSITIVE (Sven): the design phase's human approval gate - subagent runs the automated FR-Coverage self-check, then stops for a human. |
| `design.iterate-what-to-change` | orchestrator-approve | never | no | Single-screen iteration mode only (@file HTML arg). Not reached in a fresh from-scratch pipeline run. |
| `design.upload-screen-mapping` | orchestrator-approve | never | no | Upload-integration mode only (--upload). Mapping uploaded artifacts to screens is human intent; not reached in a fresh pipeline run. |

## `plan`

| Gate | Policy | Fires | Constitution | Summary / default |
|---|---|---|---|---|
| `plan.validate-input` | orchestrator-approve | never | no | No/invalid spec path at startup. The orchestrator supplies the spec, so this should not fire; on failure return control rather than hang. |
| `plan.out-of-sequence-continue` | orchestrator-approve | never | no | No dispatch token (phaseTaskId) was handed to the skill, yet a driven run is LIVE (get_phase_context: requires_out_of_sequence_warning). A hand-invoked /shipwright-plan during a driven run; the orchestrator owns sequencing. |
| `plan.interview` | auto-default | always | no | The design-decision interview (adaptive 3-5 questions). Largest interactivity surface; answered from context under single_session. **Default:** Answer each design-decision question from the loaded project context (spec, CLAUDE.md, conventions.md, architecture.md) and record it as an assumption in the plan interview record. Human plan-review is deferred to SS3's cross-phase gate-list (Sven, 2026-07-07). |
| `plan.context-check` | auto-default | conditional | no | Fires only on self-assessed large context: 5-10 bullet outline for approval before writing the plan. **Default:** Self-summarize and proceed to write the plan without blocking on outline approval (a context-hygiene optimization; downstream review/verification still runs). |
| `plan.external-review-missing-keys` | auto-default | conditional | no | Step 5 Branch B: no external-review API key. Not silently skippable; the self-review fallback preserves the gate. **Default:** Option 2: skip external review, fall back to the mandatory self-review ('2x denken') pass, and log the opt-out reason ('non-interactive single-session run; no OPENROUTER key provisioned'). |
| `plan.external-review-findings` | auto-default | conditional | no | Step 5 Branch A: adjudicate external-review findings. Soft gate ('discuss') - auto-integrate + log under single_session. **Default:** Autonomously integrate high-confidence findings and decline the rest with a logged reason; every finding is recorded to decision_log.md (audit trail preserved). |

## `build`

| Gate | Policy | Fires | Constitution | Summary / default |
|---|---|---|---|---|
| `build.section-file-required` | orchestrator-approve | never | no | No/invalid section-file arg. The orchestrator passes the path in the brief; a miss is a wiring bug - return control. |
| `build.out-of-sequence-continue` | orchestrator-approve | never | no | No dispatch token (phaseTaskId) was handed to the skill, yet a driven run is LIVE (get_phase_context: requires_out_of_sequence_warning). A hand-invoked /shipwright-build during a driven run; the orchestrator owns sequencing. |
| `build.env-validation-missing-vars` | orchestrator-approve | conditional | no | validate_env.py reports missing required env vars. Secret/env provisioning is a human/orchestrator responsibility; never auto-skip. |
| `build.destructive-sql-confirm` | hard-stop | conditional | yes (locked) | A generated migration contains DROP/TRUNCATE/DELETE-without-WHERE. Constitution ASK-FIRST 'regardless of autonomy level' - irreversible data loss. |
| `build.migration-preflight-fail` | orchestrator-approve | conditional | no | Migration preflight (CLI/auth/connectivity) failed before apply. Environment repair the subagent can't self-do; return control (do not run tests against a stale schema). |
| `build.migration-apply-fail` | hard-stop | conditional | yes (locked) | Migration apply failed mid-run (DB may be in partial state). Constitution ASK-FIRST 'stop immediately' - human diagnosis required. |
| `build.migration-post-apply-manual-step` | auto-default | conditional | no | A post-apply manual step matches the applied migration. Build already degrades this in autonomous mode. **Default:** Log the manual step as a warning, skip tests in blocks_tests_for, and flag it in the result JSON (the existing autonomous-mode degrade). |
| `build.browser-verify-prereq-unresolved` | orchestrator-approve | conditional | no | Frontend changed but no dev-server/URL resolves for browser verify. Do NOT silently skip; return control for a dev_url/port. |
| `build.browser-verify-fix-exhausted` | orchestrator-approve | conditional | no | browser_verify still failing after 3 browser-fixer retries. Return the diagnosis to the orchestrator; don't auto-swallow a reproduced UI failure. |
| `build.debugging-escalation-3-failures` | orchestrator-approve | conditional | yes (locked) | 2 failed fixes same root cause, or 3 total. Constitution ASK-FIRST + NEVER 'loop >3 debugging attempts without escalating' - surface attempt-log + alternatives. |
| `build.code-review-finding-triage` | auto-default | conditional | no | Step 6b guided-mode per-finding triage. Already fully suppressed (auto-accept) in build's autonomous mode. **Default:** Auto-accept and fix every finding, logging each as 'auto-fixed (autonomous mode)' - mirrors build's existing autonomous behaviour. |

## `deploy`

| Gate | Policy | Fires | Constitution | Summary / default |
|---|---|---|---|---|
| `deploy.out-of-sequence-continue` | orchestrator-approve | never | no | No dispatch token (phaseTaskId) was handed to the skill, yet a driven run is LIVE (get_phase_context: requires_out_of_sequence_warning). A hand-invoked /shipwright-deploy during a driven run; the orchestrator owns sequencing. |
| `deploy.missing-env-vars` | orchestrator-approve | conditional | no | validate_env.py reports missing required deploy vars. Provisioning deploy secrets is a human responsibility; auto-skip risks a broken deploy. |
| `deploy.test-gate-failed` | orchestrator-approve | conditional | yes (locked) | Tests missing/red at the deploy gate. Constitution ASK-FIRST 'skipping test layers'; in a healthy pipeline the prior test phase passed, so this should not fire. |
| `deploy.migration-prereqs-missing` | orchestrator-approve | conditional | no | Migrations exist but a prerequisite (config.toml / project link / access token) is missing. Credential/linking provisioning is outside the subagent's reach. |
| `deploy.dev-pending-migrations-apply` | auto-default | conditional | no | Pending DEV migrations. Constitution explicitly permits non-prod idempotent apply; the non-idempotent case escalates. **Default:** Apply the pending DEV migrations when supports_idempotent_apply is true (non-prod, preflight ok) - constitution-permitted; otherwise surface to the orchestrator. |
| `deploy.prod-migration-apply` | hard-stop | conditional | yes (locked) | PROD + migrations: present dry-run, require explicit confirmation before apply. Constitution ASK-FIRST 'PROD deployments' + 'migration apply'. |
| `deploy.destructive-migration-confirm` | hard-stop | conditional | yes (locked) | A destructive migration was flagged (any target, DEV or PROD). Constitution ASK-FIRST 'destructive SQL - always confirm, even in autonomous mode'. |
| `deploy.migration-verify-failed` | hard-stop | conditional | yes (locked) | Post-apply migration_verifier failed (live schema mismatch). Couples rollback + migration-failure ASK-FIRST classes; 'Override and continue' must never be auto-picked. |
| `deploy.post-migration-manual-steps` | orchestrator-approve | conditional | no | A post-apply manual step matches a just-applied migration. An out-of-band human action; the subagent cannot perform or truthfully confirm it. |
| `deploy.prod-deploy-confirm` | hard-stop | conditional | yes (locked) | The canonical PROD deploy confirmation (after the backup clone). Constitution ASK-FIRST 'PROD deployments - always confirm + backup, regardless of autonomy level'. The strongest gate. |
| `deploy.manual-rollback-select-confirm` | hard-stop | never | yes (locked) | Operator-initiated PROD rollback (--rollback flag only). Constitution ASK-FIRST 'Rollback decisions'; not part of the normal deploy flow. |
| `deploy.smoke-fail-auto-rollback` | auto-default | conditional | no | Smoke test failed -> automatic rollback (git-tag revert for DEV, clone restore for PROD). A documented non-gate; announces itself. **Default:** Auto-revert to last-known-good and ANNOUNCE it (rollback-discipline Pattern 3: a silent rollback is worse than the failure). Not an AskUserQuestion gate today - the documented auto exception to the rollback ASK-FIRST rule. |

