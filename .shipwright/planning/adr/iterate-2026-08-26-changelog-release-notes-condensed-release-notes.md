# Condensed, mechanically-gated GitHub Release notes

## Context

`/shipwright-changelog` tags and pushes a release but never creates a GitHub
Release page — clicking the tag on GitHub shows only the one-line tag
annotation, never the `CHANGELOG.md` content a person actually wants to read.
The raw `CHANGELOG.md` section for a typical release runs 100-450+ dense,
multi-sentence bullets (confirmed against this repo's own v0.32.0 section),
which is unreadable as a release-page summary.

## Decision

Add a Step 7 to `/shipwright-changelog` that condenses the just-released
`CHANGELOG.md` section (read from the tagged git blob, never the worktree
file) into a short, structured body — Highlights / Features / Breaking
Changes / Changed / Fixed / Security, English, no emoji — via a single
tool-less LLM completion call, then mechanically sanitizes and validates that
output before publishing it as a GitHub Release with `gh release create
--verify-tag`. The condensed body always ends with a link back to the full
tagged `CHANGELOG.md` section, so nothing the condensation drops is actually
lost.

## Architecture Review reconciliation

Both external reviewers (deepseek: high severity, openai: medium) argued for
dropping the LLM condensation entirely in favor of republishing the tagged
CHANGELOG section verbatim (Option B), calling the condensation pipeline a
disproportionate "second editorial pipeline" and noting most of the
validator's surface exists only to guard against the injection risk the LLM
step itself introduces. Decision: keep the plan. Two things settle it: (1)
the raw CHANGELOG section is never lost — every condensed body links straight
to it, one click away; (2) the reviewers' implicit worry (an LLM writing
unchecked to a public page) is exactly what `validate_release_notes.py`
already guards against — a deterministic generate-then-gate validator (fixed
heading vocabulary, size cap, required links, mention/reference
neutralization, image/external-link rejection) in front of a tool-less,
no-side-effect completion call, the standard shape for any LLM output
reaching a public surface. The reviewers' own prior-art example
(`release-please`/`semantic-release`, fully mechanical) was the alternative
already discarded once the operator read the real 454-line raw section for
v0.32.0 and judged it unreadable as a release page.

## Consequences

A release now gets a readable GitHub Release page, forward-only (no backfill
for the 40+ existing tags). Failure at any stage (missing `gh`, unauthenticated,
condensation failure, validation failure, `gh release create` failure) is
reported in the Step 7 summary banner and never blocks
`/shipwright-changelog`'s phase completion — the tag remains the source of
truth. The next release's setup script advisory-warns (never blocks) when the
immediately preceding tag has no release, so a silently-failed/skipped step
surfaces once at the next release instead of rotting unnoticed.

## Review cascade findings (fixed)

Internal Plan Review (17, all fixed): `--verify-tag` divergent-tag guard,
mechanical validator added, tests relocated off the ADR-045 collision path,
tagged-blob (not worktree) read, `gh release view` exists-check,
next-release advisory notice, prompt-injection neutralization, size cap,
compare-link derived from `git tag --list` (not CHANGELOG heading order,
which risks a 404). Round 2 review cascade (external code review 7 + Stage 2
code-reviewer 3 + Stage 3 doubt-reviewer 2 = 11, all fixed): a whole-file
size pre-check that would have broken every future release on this repo's
own 450KB+ CHANGELOG.md, a link-host prefix bypass
(`widgets-archive` matching `widgets`), a code-span-breaking mention
neutralization bug, an empty-last-section check masked by the appended
footer, an ADR-045 import collision (`repo_identity.py` moved from
`shared/scripts/lib/` to `shared/scripts/` top level, matching
`changelog_sections.py`'s precedent), and a heading-level validation bypass
(the vocabulary gate scanned only exact `## ` lines, so a `#`/`###`+/indented
heading could carry unauthorized text past it — confirmed live by
hand-tracing before the fix).

## Rejected alternatives

Option B (verbatim republish of the tagged CHANGELOG section, no LLM, no
validator) — the Architecture Review's own recommended "smallest thing that
would do." Declined per the reconciliation above: it optimizes away the
actual complaint (raw section unreadable as a release page) rather than
solving it, and the validator surface the reviewers called disproportionate
guards a real, already-accepted risk (LLM output reaching a public page),
not a hypothetical one.
