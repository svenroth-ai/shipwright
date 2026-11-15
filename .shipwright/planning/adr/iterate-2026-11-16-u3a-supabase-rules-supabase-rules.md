# supabase-nextjs architecture rules as rule objects, template examples obey them (campaign profile-architecture-rules, U3a)

Run: `iterate-2026-11-16-u3a-supabase-rules`. Spec: `.shipwright/planning/iterate/campaigns/profile-architecture-rules/sub-iterates/U3a-supabase-rules.md`.

## Decision

The six `supabase-nextjs` sentences become U1 rule objects, each with a `why`. Two are mechanical (class `validator`, ESLint fragments for `eslint.config.mjs`): client creation only through `src/lib/supabase/` (`no-restricted-imports` with `importNames` per package: `createClient` from `@supabase/supabase-js`, `createBrowserClient`/`createServerClient` from `@supabase/ssr`, so type imports stay allowed; scope `src/**` minus `src/lib/supabase/**` and test files; BRIEF 4.3) and no `fetch()` in components (`no-restricted-globals` + `no-restricted-properties`; scope `src/components/**` and `.tsx/.jsx` under `src/app/**`). Four stay instruction only: feature modules (`prompt-only (mechanisable)`, BRIEF 4.4: no features folder exists to name), Server Components by default and no business logic in API routes (`prompt-only (judgement)`), migrations (`prompt-only (mechanisable)`, no invoked check). Both API route examples (`conventions.md.template`, `api.md.template`) now validate, authenticate and delegate to helpers under `src/lib/supabase/`. The duplicated prose (Server Components bullet, three API Patterns bullets, one components rule line) is removed; the rules are rendered once from the profile via `{ARCHITECTURE_RULES}` (U2). A committed fixture tree (`shared/tests/fixtures/supabase_nextjs_scaffold/`) holds every TypeScript example of the templates; `test_supabase_nextjs_rules_drift.py` pins fixture == template, that every example is mapped, and that the tree passes the profile's own fragments (small ESLint emulation). Evidence with real ESLint 10: `eslint-seeded-run.txt` (fixture clean, seeded violations flagged, API layer and tests not flagged).

## Architecture Review

Brief stated the campaign context (U1 merged, U2 concurrent, U3b/U4/U5/U6 consume the rules). Verbatim verdicts: `{"glm": "revise", "openai": "revise"}`, no reject. Both found the permanent ESLint emulation disproportionate (U3b brings real ESLint) and one noted the fixture could rot. Disposition: accepted in part - the emulation is documented as scaffolding that U3b replaces, the fixture is pinned to the templates by equality tests (rot is a test failure), and a real ESLint run was done once as evidence; rejected-with-reason: deferring the always-on drift test, because the unit's done-when requires a drift test that always runs and U3b may only start after this unit.

## External-Plan-Review-Findings (glm approve, openai revise)

| Finding | Disposition |
|---|---|
| `createClient`/package names; add `@supabase/ssr` | accepted-and-fixed: `@supabase/ssr` restricted; the catch-all `createClient` import-name pattern was first kept, then removed after the code review proved with real ESLint that it flags every `import * as X` (see below) |
| Dynamic `import()` / `require()` not covered | accepted-and-fixed: stated in the rule note (static imports only) |
| Routes not mechanised (`route.ts`) | accepted-and-fixed: rule note says route handlers are out of scope; the route rule is instruction only |
| Emulator vs ESLint semantics diverge | accepted-and-fixed: real ESLint run recorded; type-only import verified flagged by real ESLint |
| `use client` false positives | accepted-and-fixed: note names the per-line disable as the exception path |

## External-Code-Review-Findings

| Finding | Disposition |
|---|---|
| Fixture tree missing from the diff (glm, openai, high) | rejected-with-reason: the reviewed diff excluded the fixture directory; the 16 files are committed |
| Emulator strips comments, not string literals (medium) | rejected-with-reason: false positives only, no template example hits it; scaffolding replaced by real ESLint in U3b |
| `import type` may not be flagged by real ESLint (medium) | rejected-with-reason: verified with ESLint 10, flagged |
| `src/middleware.ts` session refresh is in scope (low) | accepted-and-fixed: rule note puts the middleware helper under `src/lib/supabase/` |

## Code review round 1 (internal code-reviewer, model=opus: REJECT, 1 high)

| Finding | Disposition |
|---|---|
| high: `{group:['**'], importNames:['createClient']}` flags every namespace import (`import * as React`, shadcn/ui), and helper factories are called `createClient` in Supabase's own guide | accepted-and-fixed: reproduced with ESLint 10 (2 errors), pattern removed, packages alone carry the rule; rule text now names the packages; emulation test gets namespace-import and helper-named-createClient compliant cases |
| medium: heading "the only place that writes queries" contradicts component examples | accepted-and-fixed: "route handlers delegate queries here" |
| low: fence regex needs info-string tolerance; `raise AssertionError` instead of `pytest.fail` | accepted-and-fixed |
| low: middleware in scope; fragments overriding each other in flat config | middleware accepted-and-fixed (rule note); override hint passed to U3b |

## Doubt review (opus) and code review round 2 (PASS)

| Finding | Disposition |
|---|---|
| medium: `import type { User }` flagged across src/ | accepted-and-fixed: restriction moved to `importNames` of the client factories; verified with ESLint 10 (type import clean, factories and namespace import flagged) |
| medium: class `validator` claimed before anything writes the fragment | rejected-with-reason: BRIEF 2.1/2.2 classes a lint rule `validator` and U3b (next unit, same campaign) writes the template; nothing reads the class in between except U2's render |
| medium: `project-scaffolding.md` still says render as bullet list | rejected-with-reason: that file and the render are U2's (concurrent unit); not touched here |
| low: fetch rule flags opengraph/icon files | accepted-and-fixed: ignored; hooks outside components named out of scope in the note |
| low: guide.md lists the old sentences | accepted-and-fixed: two lines reworded |
| low: components.md pointer for vite-hono | accepted-and-fixed: "when the profile declares any" |
| low: flat-config override of same rule; legacy format now unused | passed to U3b / noted: the last bundled legacy list is converted, removal of the legacy format is unblocked |
| low: unreachable `patterns` branch in emulation | accepted-and-fixed: replaced by `paths` importNames handling |

## Consequences

U3b carries these two fragments into `eslint.config.mjs.template` and replaces the emulation with a real ESLint run. New scaffolds get the rules via U2's render; existing projects are untouched. Requirements: no new FR; criteria are FR-01.01 AC16-AC18. Concurrent U2 may also append FR-01.01 criteria at the same spot of `spec.md`; renumber on merge.
