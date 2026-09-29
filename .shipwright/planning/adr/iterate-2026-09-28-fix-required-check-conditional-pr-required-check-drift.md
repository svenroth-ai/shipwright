# Required-check presence and PR execution

## Context

FR-01.17/AC06 compares the host's must-pass names with the checks a repository can report. The first comparison ignored jobs with a job-level condition, so it called a configured PR check nonexistent even when that check reported. GitHub reports a successful check for a skipped job; whether a job ran is a different question from whether its check exists.

## Decision

Derive two sets in one pass per workflow (`workflow_check_sets`):

- **possible** — every job of a non-dormant workflow, including job-`if:`-gated ones. Only this set can disprove a phantom name.
- **every-PR candidates** — checks provably run on every PR into the target branch. Only these can be called unenforced. A job qualifies with no `if:`, or one of `github.event_name ==/!= '<literal>'` / `true`. A workflow qualifies with a `pull_request` trigger that has no `paths`/`paths-ignore`, no partial `types`, and only literal `branches` (listing the target) or `branches-ignore` (not listing it).

Everything the small classifier cannot prove (globs, other expressions) stays possible-only. Two small correctness fixes ride along: a YAML-boolean `if: false` counts as conditional, and `on: [pull_request]` / `on: pull_request` are not dormant.

## Alternatives and limits

- Requiring all conditional jobs was rejected: a skipped job's check says nothing about completed work. Ignoring all conditional jobs was the false-phantom defect this iterate repairs.
- A shell/payload parser proving that a `workflow_run` stage posts a commit status was built, then **removed**: it grew without a stopping point and can never prove arbitrary scripts. Posted statuses (`POSTED_STATUS_CONTEXTS`) stay candidates exactly as before this iterate. **Not provable:** whether the stage-2 script really posts the status, or that stage 1's branch filter admits the target branch. Also silent by design: filters that do fire on every PR but are not proved (`branches: ['**']`, `types` missing a default).
- Branch-glob matching, `needs` exclusion, boolean-expression evaluation and matrix-guard reasoning were removed for the same reason; weaker analysis can only miss a phantom, never invent one.
- Name parity is not policy effectiveness: a required `if: false` job reports Success without running, and a path-filtered workflow can leave a required context pending. The guide says to audit those separately.
