# Architecture Brief: Shipwright's own project profile (U5)

## Campaign context (read this first)
This is unit U5 of a six-unit campaign in this repository, built serially. Merged: U1 (rule object, loader, validation), U2 (`render_architecture_rules.py` writes a profile's rules into a project's `conventions.md`), U3a/U3b (supabase rules and ESLint template), U4 (bundled `claude-plugin` profile with six plugin-project rules). U6 (code-reviewer reads the rendered rules) runs after this unit and is a consumer of the rendered block. Operator decision (campaign brief section 3/U5): Shipwright's repo keeps its repo-only rules in its own project profile.

## The problem
This repository names the generic `python-plugin-monorepo` profile in its three configs, which carries no architecture rules, so agents working in this repo never see its plugin-project rules or the rules that exist only here (one pytest root per process, the pre-commit bloat anti-ratchet, the bloat baseline), although these are enforced or at least written down elsewhere.

## What already exists here
- Bundled `claude-plugin` profile (six rules, incl. one registered hook); render tool and loader; lookup order project > user > bundled; project profile shadows a bundled name whole.
- Root `conftest.py` session guard; `scripts/hooks/pre-commit` + `anti_ratchet_check.py`; `.github/workflows/bloat-check.yml`; `shipwright_bloat_baseline.json`.
- Name-keyed CI and CodeQL template tables apply to bundled names only.

## What would newly, permanently exist
One tracked file `.shipwright/profiles/shipwright-monorepo.json` (a copy of `claude-plugin` plus three repo-only rule objects), the three configs naming it, and a rendered rules block in this repo's `conventions.md`. A test pins the copy against the bundled profile so it cannot drift silently; the repo-only mechanism paths are drift-tested.

## Options on the table
- A: project profile copy + three rules, switch the configs.
- B: add the repo-only rules to the bundled `claude-plugin` profile.
- C: keep `python-plugin-monorepo` and render nothing for this repo.
- D: switch to bundled `claude-plugin` without any repo-only rules.

## Constraints that are not negotiable
No new FRs. Test, compliance and dev-server resolution must not change. A mechanism counts as enforcement only if something invokes it.
