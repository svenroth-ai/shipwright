# Mini-plan: B2b wizard brief keeps the stack profile it names

Spec: campaign brief-driven-run-b-intake-design-e2e, sub-iterate B2b.

## Finding (brief contract)
The WebUI wizard (shipwright-webui `client/src/components/wizard/IntentWizard/contract.ts`, `composeNewBrief`) hands /shipwright-run ONE prose line: `<idea> (Intake - Users: ..; Saves data: ..; Runs: ..; Stack profile: <name>; ...)`. brief_intake parses no key from it (description only) and never reads any `profile` field, so the profile came only from `persistence`. No brief version exists for the file route (version 1 belongs to the package route, brief_package.py).

## Changes
1. shared/scripts/lib/brief_profile.py (new sibling, loaded by file path, ADR-045): find the named profile (`profile` / `stack_profile` field, else the `Stack profile:` item inside the `(Intake ...)` trailer), resolve it ONLY through profile_resolver.resolve_profile (project > user > bundled), return profile / reason / extra; unusable name -> profile null + profile_requested + profile_error + warnings (control characters stripped), never another profile.
2. shared/scripts/lib/brief_intake.py: map_brief(brief, explicit=None) lets the explicit choice beat inference (env questions follow the chosen profile); intake() asks the sibling; key alias stack_profile -> profile; CLI exits 3 on profile_error. Net -3 lines (293), synonym tables re-wrapped, duplicate sibling loaders folded into _sibling().
3. shared/scripts/lib/brief_dir_intake.py: fixture refusal message reworded in place (only the OPERATOR sets the switch; an agent must never set it), net zero lines.
4. Docs: run SKILL.md (named-profile note, NEVER rule), brief-intake.md (contract section, NEVER rule).
5. Tests: shared/tests/test_brief_profile.py; plugins/shipwright-run/tests/test_brief_profile_e2e.py (brief -> intake CLI -> write-config -> run config -> get-next-step).

## Alternative considered
Teach write-config to read the brief: rejected, the intake already returns the profile and Step 4 passes it on; one place decides.
