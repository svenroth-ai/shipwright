# Step E.18 — Inherited Baseline + Catalogue-Confirmation Follow-up

Runs **after Step E.17** (which produces the backfill report and the repo-wide
skip inventory) and **before Step F** (so the first compliance seeding already
sees the register).

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/tools/record_inherited_baseline.py" \
  --project-root <cwd> [--failures-json <path>] [--dry-run]
```

## Why this step exists

An onboarded project is not required to arrive perfect, only to arrive
**honestly described**. Before this step, two dishonesties shipped by default:

- the requirements catalogue was derived by reading code and **nothing said so**,
  so traceability, coverage and drift all measured against a catalogue that
  looked confirmed and was not;
- inherited failures and untested capabilities were counted as **this project's**
  failures, so the first `/shipwright-test` run read red and stayed red — and an
  operator who learns to ignore red is worse off than one with a single failure.

This repository is the proof for the first: its own catalogue came from
onboarding, and an entire campaign now exists to repair it years later.

## What it does

1. **Writes `shipwright_known_failures.json`** — the accepted-baseline register.
   Two independent blocks, deliberately kept apart:

   | Block | Holds | Read by |
   |---|---|---|
   | `known_failures[]` + `baseline_failure_count` | tests that were **already failing** | `shipwright-compliance` (`collect_known_failures`) today; the test phase once `trg-12b4cf3f` lands |
   | `inherited_coverage_gaps` | requirements with no `@FR`-tagged test, and tests that are switched off | the same, additively |

   **A coverage gap never feeds `baseline_failure_count`.** That number is what
   `rtm_generator` uses to turn a `passed < total` gap into `COVERED (baseline)`
   — it buys forgiveness. Spending it on absences nobody observed would let a
   genuine future failure read as green.

2. **Files the confirmation follow-up** (`adopt-derived-catalogue-confirmation`)
   asking that the derived requirements be taken through
   `shared/requirement-elicitation.md` **with a person**. Reading the code is a
   start and is not enough. Note the scope: the framework's own requirement-
   grilling campaigns cover *our* repositories — nothing else would ever give an
   onboarded project the same treatment, so onboarding files it itself.

3. **Files one follow-up per non-empty inherited gap class**
   (`adopt-inherited-gaps::<class>`). This is the destination a brownfield
   journey-coverage gap routes to **instead of blocking a test run**.

This step is the **single owner** of triage filing for these artifacts — it is
the first step that runs after the Triage Inbox is scaffolded (Step E.16), so
filing from Step E would write into a store that does not exist yet. All cards
are idempotent (`dedup_key`, no recency window, `to_outbox=False`) so they land
in the Step H commit and a re-adopt never duplicates them.

## `--failures-json` — recording an observed baseline

Optional. Onboarding does **not** run an arbitrary repository's test suite, so by
default no baseline is observed and the register records exactly that:
`baseline_observed: false`, `baseline_source: "not_run"`. That is a different
fact from "clean", and writing a confident zero would erase the difference.

When a baseline run *was* made, pass its result:

```json
{
  "source": "adopt baseline run",
  "command": "npx vitest run",
  "failing_tests": [
    {"test": "auth.spec.ts::login", "description": "pre-existing, unrelated to adoption"}
  ]
}
```

Rules, all **fail-closed** (a non-zero exit, never a silently empty register):

- `source` **and** `command` are required and non-empty. "Observed" is a claim
  that a run happened; a hand-written list of test names is not evidence of one.
- An empty `failing_tests` under a real command is legitimate — that is an
  observed **green** baseline, recorded as observed.
- A declared `baseline_failure_count` that disagrees with the listed failures is
  rejected: one of the two is wrong, so neither is trusted.
- Only `test`, `description`, `ticket`, `added`, `count` are copied. The payload
  may be assembled from raw test output, and this file is committed at Step H —
  an environment dump or a traceback carrying a home path must not ride along.

## Preconditions

`.shipwright/adopt/derived-catalogue.json` must exist (written by Step E). Without
it the step cannot know which requirements exist, so every gap it reported would
be a guess — it exits non-zero and names the step that writes it.

The two Step E.17 inputs (`.shipwright/backfill/backfill-report.json`,
`.shipwright/adopt/traceability-baseline.json`) are **optional**: a zero-test repo
backfills to nothing and a repo with no rot has no inventory, and the cleanest
possible inheritance must not read as an onboarding failure.

## Output

JSON on stdout: `derived_requirements`, `unconfirmed_requirements`,
`baseline_observed`, `baseline_failure_count`, `inherited_coverage_gaps` (counts),
`confirmation_dedup_key`, `triage`. Step H renders the first two in the handoff
banner and passes `unconfirmed_requirements` to the commit-message builder.
