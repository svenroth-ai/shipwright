# ADR: shipwright-adopt seeds phase_tasks[] entries marked established-at-adoption

**Run-ID:** iterate-2026-09-09-s2-adopted-config-shape
**Campaign:** p4-04-retire-write-once-steps, sub-iterate s2 of 6 (adopted-config-shape)

## Context

Campaign `p4-04-retire-write-once-steps` decision (1), made concrete: adopt
seeds `phase_tasks[]` entries marked as established-at-adoption, carrying the
same claim `completed_steps` carries today ("these phases are not
outstanding"), expressed in the shape readers are migrating to. Nothing is
invented — s1 already migrated the one reader whose regression a person sees
(`compliance/mermaid.py`, the dashboard phase strip) to read `phase_tasks[]`
first. This sub-iterate is the WRITER side for FUTURE adoptions only; the
already-adopted repo's on-disk config is a separate, explicit gap
(sub-iterate s2b).

## Decision

`plugins/shipwright-adopt/scripts/lib/config_writer.py`'s `write_run_config`
gains a new helper `_adopted_phase_task(step, *, now)` and calls it once per
entry in `completed_steps`, writing the results into a new `phase_tasks`
key alongside the existing `completed_steps` / `phase_history` writes (not
instead of them — those two fields still have live readers this campaign
migrates one sub-iterate at a time; dropping their emission is s5's job).

Each seeded entry:
- `status`: `"skipped"` for `test`, `"done"` for everything else — mirroring
  the split `phase_history`'s `outcome` already makes (`adopted-skipped` vs
  `adopted`). Both are TERMINAL `PhaseTaskStatus` values, so
  `mermaid._phase_tasks_status`'s finished-status set renders the phase
  `complete` rather than `pending` (AC1).
- `establishedAtAdoption: true` — an additive marker (schema
  `PhaseTask.additionalProperties` is `true`) plus a matching flag inside
  `result`, so an adopted-in entry is visibly distinct from one an actual
  phase-runner executed (AC2).
- Every other field required by `shared/schemas/run_config.v2.schema.json`'s
  `PhaseTask` (`phaseTaskId`, `phase`, `splitId`, `sessionUuid`, `version`,
  `title`, `slashCommand`, `prerequisites`, `executionCount`, `createdAt`) is
  populated with a well-formed, schema-conformant value.

## Consequences

- A newly adopted repo's dashboard phase strip (the s1 reader) renders every
  `completed_steps` phase as complete, matching today's behavior via
  `completed_steps` — proven with a producer-to-file-to-real-consumer
  boundary probe (`test_phase_tasks_read_as_complete_by_dashboard_phase_strip`)
  that loads the actual `mermaid.py` module by file path and feeds the real
  `write_all()` output through it.
- `design` is in the adopted `pipeline` list but was never in
  `completed_steps`'s default (`["project", "plan", "build", "test"]`) and so
  gets no `phase_tasks[]` entry either — unchanged by this diff. In practice
  this is inert: `write_run_config` always stamps the run-level `status`
  `"complete"`, and `mermaid._get_phase_status` short-circuits on that value
  before it ever consults `phase_tasks[]`, so every pipeline phase — `design`
  included — already renders `complete` for a real adopted config, both
  before and after this diff (proven with the actual produced `status` value
  in the same boundary-probe test, not just the synthetic probe above).
- The already-adopted repo's on-disk config (no `phase_tasks[]` at all) is
  unaffected by this sub-iterate — that gap is s2b's explicit scope, not
  silently left open by this one.
- Unblocks the verifiers migration in s4, which needed a defined
  `phase_tasks[]` shape for adopted repos to migrate against.

## Rationale

Per-writer migration (rather than inventing a new claim adopt never made) is
the architecture-approved approach (external review 2026-09-06, GPT+GLM,
`--mode architecture`, APPROVE): "nothing is invented — it is the existing
seed expressed in the shape readers are moving to." Extending seeding to
`design` (which `completed_steps` never claimed) would be exactly the kind
of invented claim that review rejected doing implicitly.

## Rejected Alternatives

- **Seed a `phase_tasks[]` entry for `design` too, to fully cover the
  `pipeline` list** — raised by external code review (see below) and
  rejected: `completed_steps` never claimed `design` was established either,
  so seeding it now would invent a claim this sub-iterate has no basis for.
  Empirically moot besides: the run-level `status` short-circuit already
  renders `design` (and every phase) `complete` for a real adopted config
  regardless. If adopt should someday claim `design` is established at
  adoption, that is a product decision for a future sub-iterate, not an
  implicit expansion of this one's scope.
- **Drop `completed_steps` / `phase_history` emission now that
  `phase_tasks[]` exists** — rejected: those fields still have live readers
  this campaign has not migrated yet (s3/s4); dropping their emission is s5's
  job, once every reader is migrated.

## External-Plan-Review-Findings

Both GLM and OpenAI reviewed the sub-iterate spec text (`--mode iterate`,
before any implementation existed) and returned `revise`, each observing the
same gap from a different angle: the mini-plan (the spec itself) named the
acceptance criteria but not the concrete mechanism.

| Finding (severity) | Disposition |
|---|---|
| GLM/OpenAI: no concrete field/schema named for the "established-at-adoption" marker (HIGH) | accepted-and-fixed — implemented as a TERMINAL `status` (`done`/`skipped`) plus an additive `establishedAtAdoption: true` field, documented in this ADR and in `docs/hooks-and-pipeline.md`'s schema block |
| GLM/OpenAI: already-adopted repos on disk are unaddressed (MEDIUM) | rejected-with-reason — explicitly out of scope by campaign decomposition; that gap is sub-iterate s2b, named as such in both the sub-iterate spec and the campaign card |
| GLM/OpenAI: no consumer-side change named, so seeding alone might not fix rendering (MEDIUM) | rejected-with-reason — the consumer (`compliance/mermaid.py`) was already migrated in sub-iterate s1 of this same campaign; verified end-to-end by the boundary-probe test against the real `mermaid.py` module |
| GLM: seeding may break other `phase_tasks[]` readers that assume entries correspond to actually-executed work, e.g. s4's verifiers (MEDIUM) | accepted-and-fixed via the visible `establishedAtAdoption` marker — any reader that cares about provenance can branch on it; no existing reader currently does, so nothing regresses today |
| OpenAI: idempotency / partial-adoption re-run not addressed (MEDIUM) | rejected-with-reason — `write_run_config` fully overwrites `shipwright_run_config.json` on every call (as it already did for `completed_steps`/`phase_history`); no new idempotency risk is introduced, and re-adoption is not part of this sub-iterate's ACs |
| OpenAI: legacy entries lack a migration/read-default (MEDIUM) | rejected-with-reason — same as the already-adopted-repos finding above: s2b's scope, not s2's |
| GLM/OpenAI: ACs not concretely testable as written (LOW) | accepted-and-fixed — added a schema-shape test and a real-consumer boundary probe, not just a status-string assertion |

## External-Code-Review-Findings

| Finding (severity) | Disposition |
|---|---|
| OpenAI: `design` is in the adopted `pipeline` but never seeded a `phase_tasks[]` entry (`completed_steps` never included it), so it could render non-complete, violating AC1 (MEDIUM) | rejected-with-reason — see Consequences/Rejected Alternatives above: empirically moot (run-level `status` short-circuit), and extending coverage to a phase `completed_steps` never claimed would invent a claim outside this sub-iterate's basis. A regression test (`test_phase_tasks_read_as_complete_by_dashboard_phase_strip`, `design` assertion) makes this verifiable, not just asserted |
| OpenAI: the boundary-probe test only checked the four emitted phases, missing `design` (MEDIUM) | accepted-and-fixed — added an explicit `design`-phase assertion against the real produced `status` value in the same test |
| GLM: `sessionUuid`/`phaseTaskId` point at a session/id that never existed; a future consumer joining against a session store would get a dangling reference (LOW) | rejected-with-reason — mirrors the schema's own required shape, and no such consumer exists in the diff or the repo today; acceptable as-is per the reviewer's own note |
| GLM: the schema-shape test hardcodes required-field names/regexes instead of loading `shared/schemas/run_config.v2.schema.json` via `jsonschema` (LOW) | rejected-with-reason — `plugins/shipwright-adopt` is deliberately `jsonschema`-dependency-free (`enrichment_schema.py`'s own docstring: "Dependency-free by design ... The schema is small enough to hand-code."); the regex/required-set check mirrors the schema's patterns character-for-character, consistent with that existing repo convention |

## Delegated-Review-Findings (3f-bis)

Stage 2 (code-reviewer), run by the campaign orchestrator against the merge-base
diff after the runner's own review cascade closed:

| Finding (severity) | Disposition |
|---|---|
| `handoff_pipeline.render_pipeline_phases` (called unconditionally by `generate_session_handoff.py`) gates purely on non-empty `phase_tasks[]`, with no schemaVersion/provenance check. An adopted repo's 4 seeded entries against the full 7-phase pipeline rendered a self-contradictory "Finished: 4 of 7" block alongside `status: complete` — the same "looks like phases are outstanding" failure AC1 targets, via a second unmigrated reader (HIGH) | accepted-and-fixed — `render_pipeline_phases` now returns `[]` when every `phase_tasks[]` entry is `establishedAtAdoption: true`, matching its own pre-existing "adopted runs are byte-identical" contract. New producer→file→real-consumer boundary probe (`test_phase_tasks_render_no_pipeline_block_in_session_handoff`) plus a synthetic-config unit test pair in `shared/tests/test_handoff_pipeline_phases.py` |
| `phase_quality._engagement.has_phase_tasks` classifies presence of `phase_tasks[]` as orchestrator-driven; an adopted repo's all-`establishedAtAdoption` array now flips `resolve_source`'s telemetry label from `standalone` to `orchestrator` (MEDIUM — telemetry-only, does not gate logic) | accepted-and-fixed — `has_phase_tasks` now excludes an array where every entry is `establishedAtAdoption: true`. New tests in `shared/tests/test_phase_quality_v2_phase_tasks.py` |
| The adopted config is a hybrid: a v1 shape (no `schemaVersion`, no `completed_phase_task_ids`, no `splits_frozen`) now also carrying a v2 `phase_tasks[]` field. Repo readers use two different discriminators for "is this v2/driven" — `schemaVersion == 2` vs. mere `phase_tasks[]` presence — and the adopted config lands on opposite sides depending on which reader asks; the two findings above are direct instances (MEDIUM — architectural, no immediate additional bug found beyond the two above) | accepted-with-reason, documented here rather than code-changed — recorded as the rule future sub-iterates (s3/s4) must apply to any further presence-keyed reader they touch: **`phase_tasks[]` presence no longer implies a v2/driven run; use `schemaVersion == 2` for drivenness and `establishedAtAdoption` for provenance.** Seeding `completed_phase_task_ids` alongside was considered and deferred — it would resolve group_b B5's cross-check symmetry, but a v1 config growing more v2-shaped fields piecemeal, without seeding `schemaVersion: 2` itself, risks new hybrid-shape ambiguity of its own; a decision for a future sub-iterate with that specific consumer in view, not this delegated-review window |
| `adopted_phase_tasks.build_adopted_phase_task` derives `phase`/`slashCommand` from the caller-supplied `step` with no enum check; `write_all(..., completed_steps=[...])` is a public keyword parameter, so an out-of-vocabulary value would silently mint a schema-violating entry (LOW — no live production trigger today) | accepted-and-fixed — raises `ValueError` for a `step` outside the schema's `Phase` enum |
| `test_phase_tasks_entries_satisfy_schema_required_fields` hardcoded copies of the schema's `required` set and two regex patterns instead of reading them from `shared/schemas/run_config.v2.schema.json`, so the test cannot detect drift in the schema it claims to pin (LOW) | accepted-and-fixed — reads `required`, `PhaseTaskId`, `slashCommand` and `PhaseTaskStatus` straight from the schema file (still no `jsonschema` dependency, consistent with this plugin's dependency-free convention) |
| `write_iterate_config`'s docstring lost its `shared/config/external_review.json` keep-in-sync cross-reference when trimmed for bloat-ceiling headroom (LOW) | accepted-and-fixed — cross-reference restored as a one-line addition; `config_writer.py` stayed at 304 LOC, under the 305 ceiling |

## Self-Review

1. Spec Compliance: pass — AC1 (does not render as skipped) and AC2
   (adopted-in vs executed distinguishable) both implemented and tested.
2. Error Handling: pass — pure dict construction over an in-memory list, no
   new failure modes.
3. Security Basics: pass — no untrusted input; `sessionUuid` is a locally
   generated `uuid4`, not a secret.
4. Test Quality: pass — two existing tests extended, two new tests added
   (schema-shape probe, real-consumer boundary probe).
5. Performance Basics: pass — O(len(completed_steps)), always a handful of
   entries, no new I/O.
6. Naming & Structure: pass — new helpers follow the module's existing
   private-helper naming (`_write_json`, `_utc_now_iso`).
7. Affected Boundaries (ADR-024): pass — producer
   `plugins/shipwright-adopt/scripts/lib/config_writer.py`, consumer
   `plugins/shipwright-compliance/scripts/lib/mermaid.py` (migrated in s1);
   round-trip probe is
   `test_phase_tasks_read_as_complete_by_dashboard_phase_strip`, loading the
   real `mermaid.py` module by file path and feeding the real `write_all()`
   output through it.

## Confidence Calibration

Skipped — effective complexity is `small` (Step 3.4 risk re-check: no
upgrade, no risk flags) and no `touches_io_boundary` flag is set, so the
gate does not fire per `agents/sub-iterate-runner.md` Step 3.8. Self-Review
(above) is the only review for this boundary beyond the review cascade;
the real-consumer boundary probe under Self-Review item 7 already exercises
the producer→file→consumer path this campaign cares about.
