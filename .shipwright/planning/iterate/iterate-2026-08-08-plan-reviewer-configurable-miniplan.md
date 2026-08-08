# Mini-Plan: plan-reviewer-configurable

## Approach
0. Tests first (AC-11): extend `test_resolve_model_tier_cli.py` (rename/widen
   the "all three roles" assertion + docstring to four), add `plan_review`
   cases to `test_model_tier_config.py`, add a `plan_internal` case to the
   model-tier floor-note test, add a test asserting the AC-2 warning-message
   fix names `--plan-review-model`, and the Boundary Probe round-trip test
   (`load_model_config` → `resolve_model_tier` → `agent_model_param` on the
   new key).
1. `shared/scripts/lib/model_tier_config.py`: add `"plan_review"` to `ROLES`.
   Every consuming function (`load_model_config`, `resolve_model_tier`,
   `agent_model_param`, the `floors` cleaning loop) already iterates `ROLES`
   generically — zero role-specific branches to touch. Update the module
   docstring + `#: The three spawn roles` comment (now four).
2. `shared/scripts/tools/resolve_model_tier.py`: add `--plan-review-model`,
   add `"plan_review": args.plan_review_model` to `flag_values`. The `for role
   in sorted(ROLES)` loop picks it up automatically. Fix the `_warn` path in
   `resolve_model_tier` (model_tier_config.py) so an invalid-tier warning
   names the real flag (`--plan-review-model`, not `--plan_review-model`) —
   map role→flag via `role.replace("_", "-")`. Update the CLI's own
   docstring/usage/example.
3. `shared/schemas/model_config.schema.json`: add `"plan_review": {"$ref":
   "#/$defs/Tier"}` under `properties`, and `"plan_review": {"$ref":
   "#/$defs/RankedTier"}` under `properties.floors.properties`. Update the
   schema's top-level description and the `floors` description ("Only the
   'review' role..." → "review and plan_review").
4. `plugins/shipwright-plan/agents/opus-plan-reviewer.md`: frontmatter
   `model: opus` → `model: inherit`, matching every other agent. This is what
   makes the Agent-tool `model=` parameter authoritative — no frontmatter pin
   left to out-rank it, so no runtime precedence assumption is needed.
   `plugins/shipwright-plan/skills/plan/references/step-5-external-review.md`
   Step 5-int: before spawning `opus-plan-reviewer`, run
   `resolve_model_tier.py --plan-review-model {flag|omitted}`, parse
   `.plan_review.agent_param`, pass it as the Agent tool's `model=` when
   non-null. No review-record row — verified `record_review_pass.py` is never
   called anywhere under `plugins/shipwright-plan/` (it is an
   `/shipwright-iterate`-only, run_id-keyed artifact); "no marker of its own"
   stays true, unchanged from today.
5. `plugins/shipwright-iterate/skills/iterate/references/iteration-planning.md`:
   new sub-step before the existing Branch A/B/C block, **medium+ only**
   (trivial/small have no spec/mini-plan file to hand the reviewer) — spawn
   `shipwright-plan:opus-plan-reviewer` over the iterate spec + mini-plan,
   `Ran: yes|no` (with an explicit "shipwright-plan not installed" message on
   spawn failure) in the iterate ADR, same fix/disclose/decline triage and
   high-severity STOP as Step 5-int (reusing gate id
   `plan.internal-review-high-severity-declined` — see step 9). No
   fallback-gating checkpoint needed — verified iterate's self-review already
   runs unconditionally at every complexity, unlike `/shipwright-plan`'s
   conditional Self-Review Fallback; this arm is additive alongside it, not a
   trigger for it. Records a `plan_internal` row when it runs (this arm has a
   run_id, unlike Step 5-int). Document the cross-plugin dependency here and
   in `docs/hooks-and-pipeline.md`.
6. `shared/scripts/lib/review_record_schema.py`: add `"plan_internal"` to
   `REVIEW_TYPES` (additive per the module's own docstring — no
   `SCHEMA_VERSION` bump).
   `shared/scripts/tools/verifiers/review_record_model_tier.py`: replace the
   single `_REVIEW_ROLE_TYPES` tuple + hardcoded `.get("review")` with a
   `_ROLE_REVIEW_TYPES = {"review": ("spec","code","doubt"), "plan_review":
   ("plan_internal",)}` map, loop over both roles.
7. This repo's `shipwright_model_config.json`: add `"plan_review": "opus"`,
   and `git add` it — verified untracked at the main root (`.gitignore`
   allows it via `!/shipwright_*_config.json` but it was never staged), so
   without an explicit add this AC's diff would be invisible to CI/reviewers.
8. `docs/guide.md` Appendix B rows for `/shipwright-plan` and
   `/shipwright-iterate` gain `--plan-review-model`; `docs/hooks-and-pipeline.md`
   gets the same treatment as the previous iterate's Subagent Timing entry,
   plus the cross-plugin-dependency note from step 5.
   `shipwright-iterate`'s `SKILL.md` `Usage:` line + §F summary and
   `iteration-planning.md`'s own §F block get the fourth role added.
   `campaign-mode.md`'s invocation line gets the same. CHANGELOG entry notes
   the benign stale-plugin-cache warning (`unrecognized key(s)
   ['plan_review']`) and to run `bash scripts/update-marketplace.sh`.
9. No `gate_catalog.json` change — `gate_policy.py`'s `COVERED_PHASES` has no
   `"iterate"` entry (verified 2026-08-08), so AC-5/AC-10's STOP-and-ask path
   reuses `plan.internal-review-high-severity-declined` rather than minting a
   rejected `iterate.*` id.

## Alternative considered — reuse the `review` role instead of a new one
Rejected. This repo's own `shipwright_model_config.json` already sets
`review: sonnet` (a deliberate cost choice for the spec/code/doubt cascade).
If `opus-plan-reviewer` consulted the same role, this repo's plan reviewer
would silently drop from opus to sonnet the moment this iterate merges — the
exact "silent downgrade" class trg-88621183 exists to make loud, self-
inflicted by the fix meant to prevent it. A dedicated `plan_review` role costs
one enum member and one CLI flag (the whole module is built around "roles are
enumerated directly, not a registry" — see its own docstring) and keeps every
project's two dials independent, which is also literally what `trg-cb2b8cb9`
proposed before being (wrongly) dismissed as a duplicate.

## Alternative considered — duplicate the reviewer agent inside shipwright-iterate
Considered so `/shipwright-iterate` has no cross-plugin dependency. **Resolved
2026-08-08: reuse wins.** Empirical check performed — this iterate's own
internal plan review (the WICHTIG-mandated Opus pass over its own spec +
mini-plan) was spawned as `shipwright-plan:opus-plan-reviewer` from within
this `shipwright-iterate`-driven session and completed successfully,
confirming the subagent registry is session-global regardless of which
plugin's skill is currently driving. Reuse: one prompt to maintain, one place
`opus-plan-reviewer.md`'s own future edits land. The one real cost — a
consumer installing only `shipwright-iterate` cannot use the internal arm —
is accepted and documented (AC-5) rather than paid for with a duplicate agent
definition.
