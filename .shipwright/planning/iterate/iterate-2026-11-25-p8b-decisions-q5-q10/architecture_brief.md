# Architecture Brief: changelog release decisions (hand-written entries, version check, PR body, refresh refusal)

## The problem
The release skill leaves hand-written "Unreleased" changelog entries out of the release, accepts malformed or
non-increasing version numbers, advertises a `--from` option nothing implements, passes the PR description with literal
`\n` characters, leaves evidence files staged after a refused evidence refresh, and writes cherry-picked bullets where
the release never picks them up.

## What would newly, permanently exist
One new CLI subcommand (`release.py pr-body`) and three small helper modules (a SemVer check, a PR-body writer, an
"Unreleased" section reader). One aggregator flag (`--move-unreleased`). Everything else changes existing machinery.

## Options
- Do nothing: keep the behaviour and document the gaps.
- Fix only in the skill prose (instruct the model), no code.
- Fix in the release CLI and the shared aggregator, with tests and golden traces.
