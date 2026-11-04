# Architecture Brief: native UI surface for the F0.5 surface check

## The problem

A native-only mobile app (Expo / React Native, no browser build) cannot finish a medium or larger iterate that changes its app
code: the surface check treats every `.tsx` file as web UI, demands a browser run, and a browser run needs a Playwright report
that such an app cannot produce. Every app iterate therefore ends red and a person accepts the red by hand. The same check also
treats a backend package's `src/*.ts` files as web UI.

## What already exists here

- The surface check accepts the surface values `web` (needs a Playwright report), `cli`, `api` and `none`.
- Test reports are staged per run (JUnit, Playwright, Jest-style JSON) and cross-checked against run id, tested revision, and the
  `tests_run` count.
- The web surface already restricts its evidence to results of one runner kind (Playwright).
- A shared rule decides which changed paths are "UI"; Browser Verify uses the same rule.

## What would newly, permanently exist

Nothing standing. This changes machinery that already exists: the surface check gains one more accepted surface value and the rule
for which staged results count as evidence for it.

## Options on the table

- **A:** a new surface value `native` that accepts Jest-style results for test files under the native package that holds the
  touched UI; whether a package is native is derived from its `package.json` at the verified commit.
- **B:** a project-level setting (config file or stack profile) that declares the UI platform as native; the existing `web` value
  then accepts non-Playwright reports for that project.
- **C:** leave the check as is; the operator accepts the red per run.
- **D:** stop treating `.tsx` / `src/` paths as UI altogether when the project has no browser target.

## Constraints that are not negotiable

A surface value must not let a web app skip its browser run. Existing evidence rules (this run, this revision, passing results,
`tests_run` backed by them) stay.
