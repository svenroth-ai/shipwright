# Architecture rules in stack profiles: rule format, loader, validation (campaign profile-architecture-rules, U1)

Run: `iterate-2026-11-15-u1-rule-format`. Spec: `.shipwright/planning/iterate/campaigns/profile-architecture-rules/sub-iterates/U1-rule-format.md`.

## Decision

A new stdlib module `shared/scripts/profile_architecture_rules.py` freezes the rule object (`id`, `text`, `why`, `enforcement`, `lint` XOR `mechanism`, `note`), the allowed enforcement x lint/mechanism combinations, the loader (old sentence lists accepted, a bad rule is dropped and reported, the profile stays valid) and path checks. The enforcement vocabulary is a copy with a drift test against `lib.constitution_register.ENFORCEMENT` (campaign decision 2.6; `lib/` is not imported or edited). `resolve_profile.py validate` reports rule errors/warnings (`rule_errors`, `rule_warnings`, `rules_valid`) and still exits 0. The shadow warning moved into `ResolvedProfile.shadow_warnings()` and now also fires when a custom profile shadows a bundled one that has rules and declares none. `vite-hono` and `skill-companion-app` declare `[]`. `supabase-nextjs` stays on the legacy list until U3a.

## Architecture Review

Attempt 1 was halted: the first architecture brief did not say that U2-U6 are in the same campaign, and the external reviewer (openai) rejected on "no consumer exists" (glm approve). Operator decision (option A): rewrite the brief with the campaign context; re-run; an override would have been allowed only for a no-consumer-only reject. No override was needed.

Attempt 2 (rewritten brief), verbatim verdicts from `architecture-review-raw.json`: `{"glm": "approve", "openai": "approve"}`. Internal `architecture-internal-reviewer` (model=opus): approve. Findings taken: lint rules are class `validator` (vocabulary copy stays equal to the constitution's); the drift test is the only guard (said in the module docstring); explicit empty lists only where the campaign decided (python-plugin-monorepo is rewritten in U4, chat-first-json is a separate track). Rejected: defer the shadow warning to U5 (U1 scope requires it); inject-safety of rendered text is a U2 concern.

## External-Plan-Review-Findings (round 1 revise, round 2 glm revise / openai approve) and internal plan review (revise)

| Finding | Disposition |
|---|---|
| Legacy id collisions, mixed lists | accepted-and-fixed: ids `legacy-string-<n>`, declared id wins, tested |
| Meaning of `enforcement` None | accepted-and-fixed: "instruction only, class undeclared", frozen in the docstring and docs |
| Invalid-rule recovery, path containment (round 1) | accepted-and-fixed: invalid rules excluded, realpath containment, absolute and `..` rejected |
| Exit code 0 with rule errors | accepted-and-fixed: documented (CLI help, docs), `rules_valid` added |
| Required keys per class, per-tool fragment shape | accepted-and-fixed: tests; eslint needs a `rules` object, ruff a non-empty object (finer ruff shape deferred to U4, first ruff rule) |
| Wrong top-level type, unknown keys, corrupt bundled file | accepted-and-fixed |
| Reuse `profile_model.path_within` | rejected-with-reason: `profile_model` imports the module (circular); same core logic |
| Import `ENFORCEMENT` instead of copying (round 1 glm) | rejected-with-reason: operator-frozen AC (BRIEF 2.6) |

## Consequences

Four scheduled units read this shape. A project profile that shadows `supabase-nextjs` now prints one more stderr warning on resolve (intended). The legacy sentence list is accepted until U3a converts the last bundled user.

The new shadow warning also lands in the `warnings[]` of the resolved profile (`res.warnings`), which adopt and the brief resolver pass on, not only on stderr; both consumers just forward the lines.

Renumbering (orchestrator review): this run's three new requirements are FR-01.23, FR-01.24 and FR-01.25, because open PR #1055 mints FR-01.22 with a different meaning.
