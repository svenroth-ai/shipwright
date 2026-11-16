# ESLint config template for supabase-nextjs scaffolds (campaign profile-architecture-rules, U3b)

Run: `iterate-2026-11-16-u3b-eslint-template`. Spec: `.shipwright/planning/iterate/campaigns/profile-architecture-rules/sub-iterates/U3b-eslint-template.md`.

## Decision

`shared/templates/eslint/eslint.config.mjs.template` is a flat config: an ignores entry, a typescript-eslint parser block (`allowTypeImports` needs the parser to see `import type`), then the two lint fragments of the `supabase-nextjs` profile LAST, each between `// BEGIN/END architecture-rule: <id>` marker comments (a later flat-config object that sets the same rule replaces its options, it does not merge). The project skill's scaffolding reference gets one step that writes it into new projects (file tools only, no shell command, no placeholder in double quotes; a doc test pins both) and describes the merge for an existing config (replace marked blocks, else append them last; never skip silently). Always-on tests pin: each profile fragment equals its marked block, parser block first and covering every fragment glob, nothing after the last fragment, no two fragments set the same rule. The Python ESLint emulation of U3a is replaced by a real ESLint test (installs eslint, typescript-eslint, typescript into a temp dir; skips without Node/npm, fails under CI) over the template as shipped, the fixture tree and 16 seeded and 16 compliant cases. Evidence of the one real run: `eslint-seeded-run.txt` in the run folder (ESLint 10.15.0, Node 24.15.0, exit 1, every seeded case flagged by its rule, no fixture or exempt file flagged).

## Architecture Review

Brief stated the campaign context. Verbatim verdicts: `{"glm": "revise", "openai": "approve"}`; internal architecture reviewer: revise. No reject. Disposition: glm and the internal reviewer prefer generating the config from the profile in U2's render tool over a pasted copy. Rejected-with-reason for now: the copy is two fragments, equality is pinned by an always-on test (a stale copy is a test failure); trigger to switch to generation: a third validator rule, a second profile with lint fragments, or adopt-time ESLint output. Internal reviewer high finding (create-next-app already writes an `eslint.config.*`, so copy-if-absent would usually do nothing): accepted-and-fixed in the skill step (merge path, all four config extensions, idempotent, loud fallback) and in the dependency list (devDependencies named with versions). Medium (CI may lose the always-on rule check when Node is absent): accepted-and-fixed, the real-ESLint test fails instead of skipping under CI. Adopted repos get no lint config from Shipwright: out of scope, the rule note already says so.

## External-Plan-Review-Findings (glm revise, openai revise)

| Finding | Disposition |
|---|---|
| "merge the blocks last" underspecified | accepted-and-fixed: replace marked blocks else append last, idempotent, legacy config reported |
| network-dependent install test | accepted-and-fixed: skip without Node, fail under CI; always-on drift test independent of Node |
| unpinned dependency versions | accepted-and-fixed: eslint ^10, typescript-eslint ^8, typescript ^5 in test and skill step |
| assertions must prove each rule runs | accepted-and-fixed: per-file, per-ruleId JSON assertions, fatal messages fail, evidence lists every file |
| `allowTypeImports` may be rejected by core rule (opus-plan-reviewer) | rejected-with-reason: verified under real ESLint 10 in U3a and again here, type-only imports pass |
| fragments override each other | accepted-and-fixed: test that no two fragments set the same rule |
| gate the step on the profile data instead of the name | rejected-with-reason: one shipped template, one profile; revisit with the second |
| fetch ban hits Server Components | rejected-with-reason: U3a rule decision, covered by a seeded src/app case |

## Code review (internal code-reviewer, model=opus: PASS) and doubt review (opus)

| Finding | Disposition |
|---|---|
| medium: merge path lacks the `import tseslint` line | accepted-and-fixed in the skill step |
| medium: devDependency step could overwrite an existing eslint version | accepted-and-fixed: add only when missing, never change a version |
| medium/doubt: npm install once per xdist worker; xdist_group inert under the load distribution | accepted-and-fixed: the four assertions are ONE test; install failure skips outside CI, fails in CI |
| low: caret under cmd.exe, unlocked versions, template header | accepted-and-fixed: ranges without caret, docstring note, header lists versions |
| high (doubt): typescript-eslint absent from the profile's dependency data, greenfield config fails to load | accepted-and-fixed: `linting.typescript-eslint` `^8.0.0` in `supabase-nextjs.json`; the step points the build phase at that block |
| medium (doubt): the Next app is created after step 7 and may replace the file | accepted-and-fixed: the step says to repeat the merge once the app exists. The build skill is not edited (scope, protected path) |
| medium (doubt): ESLint 9 with create-next-app | accepted-and-fixed: probed ESLint 9.39.5 with the template (type import passes, runtime import flagged); the step states 9.39 and 10 are checked |
| low (doubt): appended block replaces the user's options for the same three rules | accepted-and-fixed: the step says to fold or tell the user |

Not done: a real-ESLint case over an eslint-config-next base config (needs a larger install; the merge path stays prose, reviewed). Follow-up for U6 and the build phase: build does not re-merge the blocks itself.

## External-Code-Review-Findings (glm revise, openai revise)

| Finding | Disposition |
|---|---|
| openai medium: `import tseslint` is invalid in a `.cjs` config | accepted-and-fixed: the step says `require` for `.cjs` |
| openai medium: a project with only `.eslintrc*` satisfies "no eslint.config" and would get a flat config that replaces its rules | accepted-and-fixed: step 2 requires no `.eslintrc*`; the legacy case takes the loud-warning path |
| glm medium: evidence file and surface log not in the diff | rejected-with-reason: the reviewed diff excluded `.shipwright/`; `eslint-seeded-run.txt` is committed |
| glm medium: 60 skipped tests undermine "executed once" | rejected-with-reason: the 60 skips are pre-existing host-gated tests; the ESLint test and its evidence file were produced by the same run |
| glm low: `typescript` version source | rejected-with-reason: `stack.runtime.typescript` (^5.9.3) exists |
| glm low: report[rel] KeyError, fixture tree must be TS/JS only | accepted-and-fixed: explicit "not linted" assertion |
| glm low: results file trailing newline | accepted-and-fixed (derived file, not committed) |

## Orchestrator review of U3b (follow-up commit)

| Finding | Disposition |
|---|---|
| high (doubt): real-ESLint test runs `npm install` with install scripts in the default tier | accepted-and-fixed: `--ignore-scripts`, test marked `slow` (excluded by pyproject addopts, follows `test_path_helpers_template_vitest.py`), timeouts 180/120/60 s; the evidence file is regenerated with `pytest -m slow`; the always-on drift tests stay Node-free |
| medium (code): typescript-eslint floor | accepted-and-fixed: `^8.56.0`, the first 8.x release whose peerDependencies accept eslint ^10; `docs/guide.md` Linting row lists it |
| lows (code): checkpoint wording, folded options re-applied, step 3 split into 3a-3e, defineConfig sentence, evidence labels, no-brace glob message, `_write_evidence`, `--version` timeouts | accepted-and-fixed |

## OPEN FOLLOW-UP (for U6 and the build phase): the rules can be silently lost

Project step 7 runs before the Next.js app exists. If the build phase later creates the app and replaces `eslint.config.*`, the marked architecture-rule blocks are gone and nothing checks for them. The step tells the agent to repeat the merge, but the build skill is not edited here and no gate verifies that the blocks are present afterwards. This is not tracked elsewhere; the campaign report carries it.

## Consequences

New supabase-nextjs projects get the rules wired into lint; adopted repos stay instruction only. FR-01.01 AC21-AC22 added, no new FR.
