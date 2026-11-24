# Architecture Brief: release CLI for the first half of the changelog skill (prepare, aggregate)

## The problem
The changelog skill's first steps (banner, mode check, setup, history, version choice, upgrade-notes check, dry run and real
aggregation) are prose a model follows by hand. Measured on 43 full runs, the model sometimes asks the version question after the
dry run has started, forgets to carry the release date and run id across separate shell calls, and re-derives the gate policy from
two prose copies that can disagree. The goal is that these steps are one command each, with the facts the later steps need stored
once.

## What already exists here
- `setup-changelog.py`, `get_phase_context.py`, `resolve_gate_policy.py`, `git_utils.py parse-commits`, `aggregate_changelog.py`,
  `aggregate_decisions.py`, `append_changelog_entry.py`, `write_changelog_drop.py`: all the tools the prose calls today.
- `shared/config/gate_catalog.json`: the gate policy, already machine-readable.
- A frozen golden-trace harness (43 scenario traces, a replay driver, promise tests) that pins today's behaviour.

## Options
1. Do nothing: leave the steps as prose.
2. One new CLI (`release.py`) with `prepare` and `aggregate`, thin wrappers over the tools above through an injectable runner, one
   small run-state file for the release date and run id, the gate answers read from the catalog, the upgrade-notes check done by
   code; the skill prose then says "call this, do what `gates` says".
3. Make each existing tool print the extra facts (date, gates) itself and keep the prose calling the tools one by one.
4. A single `release.py run` that does every step end to end, including the steps that need a person.

## What would newly, permanently exist
One CLI entry point and seven small modules under the changelog plugin, one run-state file (in the git directory, never in the
tree), and a second driver in the golden harness. The skill prose shrinks; the gate policy keeps one source (the catalog).
