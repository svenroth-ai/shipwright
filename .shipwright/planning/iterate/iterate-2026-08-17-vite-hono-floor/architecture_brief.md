# Architecture Brief: vite-hono-floor

## The problem

A shipped stack-profile file (`shared/profiles/vite-hono.json`) declares a
starting dependency version floor for every project scaffolded from it. That
floor can go stale relative to disclosed vulnerabilities in the named
package, and nothing today notices when it does. This has already happened
once: the profile's floor went stale, two separate downstream projects
independently discovered and hand-patched their own copies, and the source
profile itself never changed — so a third project scaffolded today would
start from the same stale floor again.

## What already exists here

- `/shipwright-security` — scans a project's actual dependency tree
  (Trivy/Semgrep/etc.) after it has been built. Runs on-demand, not part of
  the scaffolding step.
- `shipwright_accepted_risks.yaml` + an accepted-risk CLI — a hand-maintained
  register of findings this repo has already scanned and accepted, for this
  repo's own dependencies.
- No Dependabot or other live vulnerability feed is run in this repo, by
  standing decision.
- No existing check reads the `shared/profiles/*.json` files themselves for
  known-vulnerable declared versions.

## What would newly, permanently exist

A small hand-maintained JSON registry mapping (profile, package) pairs to a
minimum safe version and the CVEs that justify it, plus a checker script run
as part of the existing `shared/tests` suite (already wired into CI). Adding
an entry is a manual, human act — there is no automatic feed populating it.
Whoever discovers a new vulnerable floor in the future is the one who keeps
it correct, the same way this repo's other hand-maintained security
registers are kept correct today.

## Options on the table

- **A:** Do nothing structural — fix the one known-stale floor now, and rely
  on someone noticing and hand-bumping the next one when it's found.
- **B:** Add a gate that checks each shipped profile's declared floor
  against a live vulnerability-database lookup at CI time.
- **C:** Add a gate that checks each shipped profile's declared floor
  against a small, hand-maintained registry of known-vulnerable floors,
  checked in CI via the existing test suite.
- **D:** Change whatever consumes a profile at scaffold time to resolve and
  write the latest matching version, rather than trusting the profile's
  declared string at all.

## Constraints that are not negotiable

This repo runs no Dependabot and no live vulnerability-database dependency
in any existing gate, by standing decision.
