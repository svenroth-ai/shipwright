# Producer-side hygiene filtering for mined acceptance criteria

## Context

FR-01.02 #5's rollout-transition grace (`trg-9583d3a8`) only helps a project
whose `spec.md` content already existed before the gate's own rollout instant
(2026-09-12T06:23:06Z). `/shipwright-adopt` onboarding runs after that instant
get no grace, and `plugins/shipwright-adopt/scripts/lib/test_acceptance_miner.py`
mines `describe`/`it`/`test_*` labels straight from a target repo's own test
files into acceptance-criteria bullets — which routinely carry exactly the
code-symbol/HTTP-verb shapes `fr_hygiene_detectors.violations()` bans. Every
future onboarding after rollout would hit this the moment `/shipwright-project`
Step 8 re-verifies the generated `spec.md`. Tracked as `trg-ac2ef362`,
deliberately left out of scope by `iterate-2026-09-12-project-gate-rollout-transition`
as a separate, larger unit of work.

## Decision

Filter every mined bullet through the identical shared detector the gate uses
(`fr_hygiene_detectors.violations`, loaded via `shared_loader.load_shared_module`
— the ADR-044/045-safe idiom already used by 8 other `/shipwright-adopt`
scaffolders) before it is ever appended. A dirty bullet is dropped, except a
JS `"<describe>: <it>"` combination whose bare `it` half is clean, which drops
only the offending describe prefix rather than the whole bullet. Deduplicate
each file's surviving bullet list (first-seen order) since prefix-stripping
two differently-dirty describes can collapse them to identical text. Filtering
runs before the existing 10-bullet cap, so dirty candidates never consume a
cap slot a clean one could have used.

## Consequences

Mined acceptance criteria are gate-clean at generation time, for every
onboarding from now on — not just ones the rollout-transition grace happens to
cover. A test suite whose every mined label is dirty yields zero bullets for
that candidate file and falls through to the next sibling test file (same as
a file with no test calls at all), a small behavior change from before the
fix (previously unreachable, since nothing filtered). A heavily PascalCase-
describe codebase (typical React/TS) can lose most of its mined bullets
silently — a "N bullets dropped" surfacing feature was considered and
rejected as separate scope (see Rejected). The fix adds a new module-level
hard dependency on `shared/` for this one file, matching the precedent already
set by the plugin's other 8 shared_loader consumers.

## Rationale

Two architecture options were reviewed (Option A: fix the producer / Option B:
extend gate-side grace). Both the internal architecture review and two rounds
of external LLM architecture review (glm + openai) approved Option A: it fixes
the conflict at its source, generalizes to every future onboarding rather than
one point in time, needs no change to the universal gate, and reuses an
existing cross-plugin loader idiom this plugin already has 8 precedents for.
Extending the gate's grace window would have institutionalized a widening
exemption that a producer could keep re-triggering indefinitely.

## Rejected

(1) Gate-side grace extension — would need to keep growing indefinitely as
every future onboarding manufactures a new post-rollout violation; punts the
real fix downstream forever. (2) A "N bullets dropped" reporting feature for
silently-lost mined content — real failure mode, but a genuinely separate,
addable-later unit of work; not needed to close `trg-ac2ef362`. (3) AST-level
test parsing instead of regex — accuracy delta not worth a Jest/Babel
dependency for this plugin. (4) Remediating the "installed-base window" (repos
already onboarded between the gate's rollout instant and this fix's own
release, whose mined `spec.md` may already carry violations) — out of scope
for this run; tracked as a dedicated follow-up, `trg-655cf276`.

## Follow-ups

- `trg-ac2ef362` — closed by this run once its own PR exists (referenced in
  the PR description; the sixth Acceptance Criterion in the iterate spec is
  the tracking item).
- `trg-655cf276` — installed-base window: repos onboarded between the gate's
  rollout instant (2026-09-12T06:23:06Z) and this fix's release may already
  carry mined `spec.md` violations; this run does not remediate them.

## Verification

Surface: none (pure Python string-filtering logic; no startable web/cli/api
surface exists to drive). 27 unit tests across
`plugins/shipwright-adopt/tests/test_test_acceptance_miner.py` (12,
pre-existing) and `test_test_acceptance_miner_hygiene.py` (15, new) cover
every branch: JS combined/prefix-strip/drop, Python docstring/humanized-
name/drop, per-file dedup (including bullets never stripped), cap-vs-filter
ordering, all-dirty fallthrough to the next sibling candidate, nested-describe
innermost-only attribution, and empty/whitespace-only label guards on both
the JS and Python sides.

Full review cascade completed: self, spec (spec-reviewer), plan_internal
(opus-plan-reviewer), plan (external, glm+openai), code (code-reviewer),
doubt (doubt-reviewer), external_code (external, glm+openai, 3 rounds to
`approve`/`approve`). See
`.shipwright/planning/iterate/2026-09-16-adopt-miner-hygiene-gate-conflict.md`
for the full spec, Architecture Review section, and Confidence Calibration.
