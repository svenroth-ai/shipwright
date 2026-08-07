# Iterate Spec: agent-model-tiers

- **Run ID:** iterate-2026-08-07-agent-model-tiers
- **Type:** change
- **Complexity:** medium (override — Stage 1 keyword/history classifier returned
  `small` at confidence 0.6; the actual diff spans `shared/scripts/lib`,
  `shared/scripts/tools` (+ `verifiers/`), `shared/schemas`,
  `plugins/shipwright-iterate/skills/**`, `plugins/shipwright-build/skills/**`,
  and both plugins' `tests/` — a cross-plugin, cross-split touch that Stage 1's
  message-only detectors under-count. Set per SKILL.md §7 ("under-classification
  stays cheap... over-classification does not, because complexity locks").
- **Status:** draft

## Goal

Every subagent definition carries `model: inherit`, so when the operator drops
the session to a cheaper tier, the review cascade (`spec-reviewer`,
`code-reviewer`, `doubt-reviewer`) and the unattended finalization drivers
(`section-builder`, `sub-iterate-runner`) follow silently — and the run still
reports passed reviews with no record of which tier produced them. Give the
operator a per-run, per-role override (`review` / `finalization` / `execution`)
that defaults to today's behavior (`inherit`, bit-identical) unless explicitly
set via an invocation flag or a project config file, and record the resolved
tier every review pass actually ran on.

## Acceptance Criteria

- [ ] A new optional `shipwright_model_config.json` (schema:
  `shared/schemas/model_config.schema.json`) maps `review` / `finalization` /
  `execution` to `opus` | `sonnet` | `haiku` | `inherit`; file absent = all
  three unset.
- [ ] A shared resolver (`shared/scripts/lib/model_tier_config.py` +
  `shared/scripts/tools/resolve_model_tier.py` CLI) implements precedence
  **flag > project config > unset**, where unset/`inherit` both resolve to "no
  `model` parameter" (bit-identical to current behavior — the Agent tool has no
  literal `inherit` value, so deferral is omitting the parameter).
- [ ] `/shipwright-iterate` accepts `--review-model` / `--finalization-model`
  flags (documented in the banner usage line), resolves them at Planned Run
  Summary time, and prints `review=<resolved> (<source>),
  finalization=<resolved> (<source>)`. **`--execution-model` is deliberately
  NOT one of iterate's flags** — iterate's own skill tree has no
  execution-role Agent-tool spawn of its own (browser-fixer's spawn is
  build's; iterate only references its retry *pattern* by pointer, at
  `F0.5.md`/`design-and-testing.md`) — advertising a flag with no live
  consumer was flagged and corrected during review (internal Opus plan
  review, finding "completeness/medium: `--execution-model` is a dead flag
  on iterate").
- [ ] `/shipwright-build` accepts all three flags — `--review-model` /
  `--finalization-model` / `--execution-model` — same resolution point
  (SKILL.md §G), same printed format (`<resolved> (<source>)` per role, via
  `first-actions.md`'s SESSION REPORT template).
- [ ] Every Agent-tool spawn instruction reachable from iterate's and build's
  own skill trees for the 6 in-scope agents (`spec-reviewer`, `code-reviewer`,
  `doubt-reviewer` = review; `section-builder`, `sub-iterate-runner` =
  finalization; `browser-fixer` = execution) is updated to pass the resolved
  tier — both the standalone cascade (iterate SKILL.md Step 8, build's
  `code-review.md`/`code-review-protocol.md`) and the campaign-delegated one
  (`campaign-mode.md` step 3f-bis and the `sub-iterate-runner` spawn at step
  3c).
- [ ] `record_review_pass.py record` accepts `--model-tier`; the persisted
  entry in `reviews.json` carries the tier the session resolved and reported
  for this role (a self-report — nothing correlates it with the Agent-tool
  `model=` parameter actually used at the spawn, an honest, known limit) — or
  the key is absent entirely when not supplied (no stray `null`, so
  pre-existing records and old readers stay valid).
- [ ] A new F11 predicate reads an optional `floors` block from
  `shipwright_model_config.json` and flags (never blocks — advisory only,
  regardless of whether a floor is configured) a completed review-role pass
  whose `model_tier` is below the configured floor, ran under `inherit`, or
  is absent entirely — absence is flagged, not silent, because
  `check_review_record` only ever reads the CURRENT run's own record, so an
  absent tier here is this run's own unconfirmed pass, not a historical
  record predating the field. **Lives in a new sibling module
  `review_record_model_tier.py::model_tier_note()`, not inside
  `review_record_floor.py`** — that file was already at 264 lines against the
  repo's 300-line source cap (itself the product of an earlier split off
  `review_record_check.py` on the same seam), so the predicate would have
  pushed it over. Wired into `review_record_check.py` by concatenating the
  note onto the passing `CheckResult`'s message (`substitution_note`'s
  existing shape), never into the blocking predicate chain — and the call is
  itself wrapped in a try/except that degrades to no note on any unexpected
  failure, so the advisory path can never take F11 down.
- [ ] Campaign mode: the orchestrator resolves tiers once per campaign run and
  passes them into every `sub-iterate-runner` spawn (finalization role) and
  into its own delegated review-cascade spawns (step 3f-bis, review role).
- [ ] Drift test asserts the flag-parsing + spawn-tier instruction is present
  in both `plugins/shipwright-iterate/skills/iterate/SKILL.md` and
  `plugins/shipwright-build/skills/build/SKILL.md`, mirroring
  `tests/test_skill_step_6_rules_present.py`'s anchor pattern.
- [ ] Unit tests for the resolver (precedence, `inherit` literal accepted,
  unknown role rejected, malformed project config fails soft) adapted from the
  reusable frontmatter-drift test at
  `<scratchpad>/test_agent_model_pinning.reusable.py`, re-pointed from the
  abandoned `PINNED_OPUS` hardcode design at the new config-driven resolver.
- [ ] No agent frontmatter file changes `model:` — all 11 stay exactly as they
  are today (`inherit` / `opus` / `sonnet`); the feature is additive-only via
  Agent-tool call parameters, never frontmatter edits.

## Spec Impact

- **Classification:** modify
- **ADD:** none
- **MODIFY:** FR covering the iterate/build subagent-invocation contract —
  folded as an additive capability (per-role model override) on the existing
  "review cascade" / "autonomous finalization" behavior; not a new
  user-observable capability on its own (MINT-vs-FOLD gate: this completes
  existing subagent-spawning machinery with an operator control, it does not
  introduce a capability the product lacked). Exact FR ID resolved during
  Step 2 (Repo Scout has not yet located `spec.md`'s split index at spec-write
  time; recorded in the mini-plan and F7 payload once located).
- **REMOVE:** none
- **NONE justification:** n/a (Classification is MODIFY)

## Out of Scope

- `test-runner`, `security-fixer`, `section-writer`, `opus-plan-reviewer`,
  `phase-runner` spawn sites — they live in `shipwright-test`,
  `shipwright-security`, `shipwright-plan`, `shipwright-run` skills, which the
  BRIEF's SCOPE section does not name ("Parse the flags in iterate and
  build"). Their frontmatter stays `inherit`/`opus` unchanged and they are
  unaffected by this diff.
- Frontmatter pins (`model: opus` / `model: sonnet` hardcoded in agent `.md`
  files) — REJECTED design from the abandoned prior attempt; not rebuilt.
  LANDMINE per BRIEF.
- A role registry abstraction — also a dropped design from the abandoned
  attempt; the three roles (`review`/`finalization`/`execution`) are enumerated
  directly in the resolver, not indirected through a registry file.
- `haiku` is accepted as a resolvable literal (Agent tool supports it) but no
  role defaults to it and nothing in this diff recommends it — included only
  so the config schema doesn't need a follow-up bump the day someone wants it.
- Changing what the WebUI's existing `shipwright_run_config.json` reader does
  — out of scope by the config-home decision (new file, not a run_config
  block), so the existing reader is untouched. A WebUI card for the new file
  is not built in this diff (no webui submodule present in this checkout to
  build it in); the decision only fixes the *size* such a card would be.

## Design Notes

n/a — no UI surface; this is an operator-facing CLI-flag + config-file
control read by Claude Code skill prose, not an application UI.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| Operator / project maintainer (hand-authors) | `shared/scripts/lib/model_tier_config.py::load_model_config` | JSON (`shipwright_model_config.json`) |
| `resolve_model_tier.py` (stdout) | Claude (the running iterate/build session), reading the printed JSON to decide the Agent-tool `model=` argument | JSON (stdout) |
| iterate/build session's `record_review_pass.py record --model-tier ...` call | `review_record_model_tier.py`'s new floor predicate, F11 `check_review_record` | JSON (`reviews.json` entry field) |

`touches_io_boundary` risk flag fires (new `.json` config file read + JSON
stdout contract) → Boundary Probe sub-step required in Build TDD; safety-floor
minimum `small` already subsumed by the medium override above.

Registering `model_tier` in `review_record_schema.py`'s `_OPTIONAL_STRINGS`
makes `validate_entry` stricter, not just additive: a `reviews.json` entry
carrying a non-string `model_tier` (only reachable via a hand-edited or
third-party-written record — the normal write path is CLI-`choices`-validated)
now fails schema validation, so `read_record`/`check_review_record` fail
CLOSED on that record instead of silently accepting the unknown key as before
this diff. Advisory feature, one new closed-fail path.

## Architecture Review

- **Brief:** `.shipwright/planning/iterate/iterate-2026-08-07-agent-model-tiers/architecture_brief.md`
- **Verdicts:** deepseek=revise · openai=revise
- **Smallest thing that would do (per reviewers):** A single `--review-model`
  flag (deepseek) or a single `--agent-model` flag (openai) applied to every
  in-scope spawn, with an env var or explicit-only override, and no
  persistent config file, resolver CLI, per-role split, or F11 floor.
- **Findings:**
  - *Proportionality* (deepseek, high; openai, medium) — the config file,
    schema, resolver, CLI, and F11 floor are broader machinery than "an
    operator occasionally choosing an explicit tier" needs.
    **Rejected, with reason** (see Reconciliation).
  - *Per-role taxonomy adds complexity without demonstrated need* (deepseek,
    medium) — collapse `review`/`finalization`/`execution` into one flag.
    **Rejected, with reason** (see Reconciliation).
  - *Existence: recording `inherit` doesn't identify the actual model that
    ran* (openai, medium) — the default path doesn't prove provenance.
    **Accepted as a real, permanent limit — not fixed, disclosed.** Neither
    reviewer's alternative fixes this either (a single flag's recorded value
    is exactly as much a self-report as three roles' are); Claude Code
    exposes no hook to verify which model actually executed a spawn. This is
    already the honest disclosure `make_entry`'s docstring and spec AC-6
    carry after the Stage-3 doubt-reviewer pass raised the same point
    (doubt 3): "a claim about the spawn, not independently verified
    evidence of it."
  - *Drop the F11 floor check entirely* (deepseek, low) — "the operator can
    inspect `reviews.json` directly." **Rejected, with reason** (see
    Reconciliation).
- **Reconciliation:** Both reviewers independently proposed collapsing the
  three roles into one flag — exactly the "Alternative approach" the
  mini-plan already recorded and rejected (§6): a flat, single-value control
  cannot express the operator's actual requirement, stated in the BRIEF that
  commissioned this run — "the operator sets `review: opus` locally and
  switches their session to Sonnet without the cascade following them down"
  needs *independent* per-role control, since `security-fixer` (execution)
  and `spec-reviewer` (review) have different cost/quality tradeoffs and
  should not be forced to move together. The BRIEF's "ROLES." section
  settles this as three named roles, not a design left open to this run to
  re-derive; a flat env var was the BRIEF's own REJECTED shape, restated by
  both reviewers without the rejection reason in front of them (the brief
  correctly withheld it, per architecture-review protocol). The floor check
  stays for the same reason recording the tier stays: `reviews.json` already
  holding the value is not the same as an operator being told, unprompted,
  that a value they care about was not met — the whole point of turning a
  "silent downgrade" into a "loud" one (BRIEF). No `reject` verdict from
  either reviewer, so this is integrated as a recorded disagreement, not a
  stop-and-ask.

## Confidence Calibration

- **Boundaries touched:** the three rows above — project config file read,
  resolver stdout contract, `reviews.json` entry field.
- **Empirical probes run:**
  - Config round-trip (write real `shipwright_model_config.json`, resolve,
    assert match) — PASSED (`test_model_tier_config.py`, 16 cases incl.
    hostile-string injection, malformed JSON, non-object JSON).
  - MAIN-repo-root resolution from an actual `git worktree add` (not a
    mocked path) — PASSED
    (`test_resolves_from_main_repo_root_not_worktree_cwd`).
  - BRIEF's designated first question, answered analytically rather than by a
    live probe (a throwaway plugin agent + cache-sync round-trip was judged
    too invasive to run inside this session for a question the platform
    already answers structurally): **does Claude Code resolve a placeholder
    in an agent's `model:` frontmatter field? No.** The `Agent` tool's own
    schema (directly inspectable this session) defines `model` as an
    explicit call-time parameter with no `inherit` literal of its own —
    that IS the documented override channel. Nothing describes frontmatter
    template interpolation beyond `hooks.json`'s specific
    `${CLAUDE_PLUGIN_ROOT}` path substitution (CLAUDE.md's own
    "Conventions" section names that as the one templated field). This
    confirms the **medium** (spawn-time flag) path per the BRIEF's own
    branching, not the **small** (frontmatter placeholder) path.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Resolver precedence: flag > project config > unset | tested | `test_model_tier_config.py::test_flag_wins_over_project_config`, `::test_project_config_wins_over_unset`, `::test_unset_resolves_to_inherit_with_source_unset` PASSED |
  | 2 | Explicit `inherit` flag is distinguishable from unset (`source="flag"`) | tested | `::test_explicit_inherit_flag_is_source_flag_not_unset` PASSED |
  | 3 | Unknown role raises `ModelTierConfigError` | tested | `::test_unknown_role_raises` PASSED |
  | 4 | Malformed / non-object config fails soft to `{}` | tested | `::test_malformed_config_fails_soft_to_empty`, `::test_config_not_a_json_object_fails_soft` PASSED |
  | 5 | Invalid tier value (incl. hostile string) dropped, never echoed into resolved output | tested | `::test_invalid_config_tier_value_dropped_not_raised`, `::test_hostile_config_value_never_echoed_into_resolved_output` PASSED |
  | 6 | Invalid flag value ignored, falls back to config (not silently to unset) | tested | `::test_invalid_flag_value_ignored_falls_back_to_config` PASSED |
  | 7 | `floors` block round-trips; invalid floor value dropped | tested | `::test_floors_round_trip`, `::test_floors_invalid_value_dropped` PASSED |
  | 8 | Config resolved from MAIN repo root, not a linked worktree's own cwd | tested | `::test_resolves_from_main_repo_root_not_worktree_cwd` (real `git worktree add`) PASSED |
  | 9 | `agent_model_param` omits for `inherit`, passes through explicit tiers | tested | `::test_agent_model_param_omits_for_inherit`, `::test_agent_model_param_passes_through_explicit_tier` PASSED |
  | 10 | CLI resolves all three roles in one call; flags independent per role | tested | `test_resolve_model_tier_cli.py` (2 cases) PASSED |
  | 11 | `record_review_pass.py --model-tier` round-trips into the `reviews.json` entry; `inherit` is a recordable literal; invalid value rejected at the CLI | tested | `test_record_review_pass_model_tier.py::test_model_tier_round_trips_into_the_entry`, `::test_inherit_is_a_recordable_literal`, `::test_invalid_model_tier_rejected_at_the_cli` PASSED |
  | 12 | Omitted `--model-tier` leaves no stray key (backward compat with every existing caller) | tested | `::test_omitted_model_tier_leaves_no_stray_key` PASSED |
  | 13 | F11 floor note: silent when no floor configured | tested | `test_review_record_model_tier_floor.py::test_no_floor_configured_is_silent` PASSED |
  | 14 | F11 floor note: below-floor tier flagged, `result.ok` stays `True` (never blocks) | tested | `::test_below_floor_tier_is_flagged_but_still_passes` PASSED |
  | 15 | F11 floor note: `inherit` tier flagged as unconfirmed when a floor is configured | tested | `::test_inherit_tier_is_flagged_as_unconfirmed_when_floor_configured` PASSED |
  | 16 | F11 floor note: unrecorded (legacy, key absent) tier is silent, never retroactively flagged | tested | `::test_unrecorded_tier_is_silent_not_flagged` PASSED |
  | 17 | F11 floor note: at-or-above-floor tier is silent | tested | `::test_at_or_above_floor_is_silent` PASSED |
  | 18 | `--review-model`/`--finalization-model`(/`--execution-model` on build) flags present in both SKILL.md usage banners | tested | `integration-tests/test_model_tier_spawn_instructions_present.py::test_model_tier_flags_present_in_banner` (2 cases) PASSED |
  | 19 | Spawn-time `model=` instruction present in both SKILL.md files and all 6 touched reference files (iterate: 2 files; build: 3 files) | tested | same module, `test_spawn_time_model_instruction_present`, `test_build_reference_files_carry_the_model_tier_note`, `test_iterate_reference_files_carry_the_model_tier_note` PASSED |
  | 20 | No agent frontmatter `model:` value changed by this diff (11 agents; forward + reverse drift; non-vacuity guard) | tested | `integration-tests/test_agent_model_frontmatter_unchanged.py` (24 cases) PASSED |
  | 21 | Existing review-record test suite has no regression from the new `model_tier` field / floor note | tested | `shared/tests -k "review_record or record_review_pass"` — 175 passed |
  | 22 | Both SKILL.md files stay at or under their existing 300-LOC hard cap after the additive prose | tested | pre-existing `test_kern_skill_md_under_300_loc` (iterate) + `test_build_kern_still_under_300_loc` (build) PASSED — both files land at exactly 300 |
  | 23 | Full-repo lint gate (ruff) clean on every new/edited file | tested | `uvx ruff@0.15.15 check .` — All checks passed |
  | 24 | ADR-045-safe sibling import (`lib.repo_root` via package-qualified path, not a bare `sys.path.insert(lib)`) | tested | `shared/scripts/tests` (391) + `shared/scripts/tools/tests` (523) full-root runs, no import collisions PASSED |

  0 untested-testable rows.
- **Confidence-pattern check:** Asymptote (depth) — the internal Opus plan
  review's "yes this design is sound" was followed by 13 concrete findings
  (4 HIGH), so per the anti-pattern rule one more probe was run before F0:
  the empirical config/worktree round-trip tests above, plus re-deriving the
  F11 wiring against the actual `review_record_check.py` control flow rather
  than trusting the mini-plan's prose description of it (which the reviewer
  caught as describing the wrong — blocking — mechanism). Coverage (breadth)
  — every ledger row is `tested`, 0 `untested-testable`, and the ledger spans
  all eleven spec ACs, including the frontmatter (AC-11) and drift (AC-9)
  structural guards plus the bloat-cap/lint/import-safety checks the internal
  review specifically flagged as missing from the original plan.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run pytest shared/tests/ -q` (the primary root — every
  new behavior this diff introduces has a test here). The other touched
  roots (`shared/scripts/tests`, `shared/scripts/tools/tests`,
  `plugins/shipwright-iterate/tests`, `plugins/shipwright-build/tests`,
  `integration-tests`) are each run as their OWN separate F0.5/F0 invocation
  per the repo's one-root-per-process rule — never combined into one command.
- **Evidence path:** pytest output captured at F0 / F5, one per root
- **Justification (only if surface=none):** n/a (surface=cli)
