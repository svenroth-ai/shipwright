# Mini-Plan: agent-model-tiers

- **Run ID:** iterate-2026-08-07-agent-model-tiers

## 1. Files to create/modify

**New:**
- `shared/schemas/model_config.schema.json` — schema for `shipwright_model_config.json`
- `shared/scripts/lib/model_tier_config.py` — loader + resolver (`resolve_model_tier`, `load_model_config`, precedence flag > project config > unset)
- `shared/scripts/tools/resolve_model_tier.py` — thin CLI wrapper, `classify_complexity.py`-style
- `shared/scripts/lib/tests/test_model_tier_config.py` (or `shared/tests/`, root TBD by test-root rule) — resolver unit tests, adapted from the reusable frontmatter test
- `integration-tests/test_agent_model_frontmatter_unchanged.py` — adapted reverse/forward drift test: asserts the 11 agent files' `model:` values are untouched by this diff (guards the "no frontmatter pins" constraint structurally, not just by review)
- `integration-tests/test_model_tier_spawn_instructions_present.py` — drift test: both `SKILL.md` files contain the flag + spawn-tier instruction text, mirroring `test_skill_step_6_rules_present.py`

**Edit:**
- `plugins/shipwright-iterate/skills/iterate/SKILL.md` — banner usage line (2 new flags — `--execution-model` is deliberately not one of them, per AC-3), Step F (Planned Run Summary) resolved-tier row, Step 8 spawn-tier instruction
- `plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md` — cascade invocation block gets the resolved-tier note + `record_review_pass.py --model-tier` in the recording block
- `plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md` — step 3c (`sub-iterate-runner` spawn) and step 3f-bis (delegated review cascade) get resolved-tier notes
- `plugins/shipwright-build/skills/build/SKILL.md` — banner usage line (3 new flags)
- `plugins/shipwright-build/skills/build/references/first-actions.md` — §G's `resolve_model_tier.py` call, the new "Model tiers" section, and the SESSION REPORT template's `Model tiers:` row (build's SKILL.md was trimmed to a pointer under its 300-line cap, so the actual resolution step lives here, not in SKILL.md itself)
- `plugins/shipwright-build/skills/build/references/autonomous-loop.md` — step 3c (`section-builder` spawn) resolved-tier note
- `plugins/shipwright-build/skills/build/references/code-review.md`, `code-review-protocol.md` — spawn-tier notes
- `plugins/shipwright-build/skills/build/references/browser-verify.md` — step 5c (`browser-fixer` spawn) resolved-tier note
- `shared/scripts/tools/record_review_pass.py` — `record` subcommand gains `--model-tier` (optional)
- `shared/scripts/lib/review_record_core.py` — `make_entry` gains `model_tier` key
- `shared/scripts/lib/review_record_schema.py` — `model_tier` added to `_OPTIONAL_STRINGS`, so `validate_entry` type-checks the new field instead of leaving it unvalidated (closes the gap the F11 note's own defensiveness would otherwise need to cover alone)
- `shared/scripts/tools/verifiers/review_record_model_tier.py` (NEW — split from `review_record_floor.py`, which was already at 264/300 lines) — `model_tier_note()`, wired into `review_record_check.py`'s passing-result message (never the blocking predicate chain) via a `_safe_model_tier_note()` wrapper in `review_record_check.py` that degrades to no note on any exception, so the advisory path can never crash the whole F11 verifier
- `docs/hooks-and-pipeline.md` — new config file's data-flow row (config-data-flow table) per CLAUDE.md's "modifying what a plugin reads at startup" rule

## 2. Work breakdown

1. **Schema + resolver core.** Write `model_config.schema.json` (three optional
   keys `review`/`finalization`/`execution`, enum `opus|sonnet|haiku|inherit`,
   plus optional `floors` block with the same three keys). Write
   `model_tier_config.py`: `load_model_config(project_root)` (defensive —
   missing file → `{}`, malformed JSON → `{}` + stderr warning, mirroring
   `external_review_config.py`'s `_load_project_iterate_config`);
   `resolve_model_tier(role, project_root, flag_value=None)` → precedence
   flag > project config > unset; raises `ValueError` on an unknown role (whitelist
   `{"review","finalization","execution"}`); returns `(resolved_tier, source)`,
   where `resolved_tier` is always a `TIERS` literal (`"inherit"` for unset —
   never `None`) and `source` is `"flag"|"project_config"|"unset"`. A separate
   `agent_model_param(resolved_tier)` maps `"inherit"` to `None` (omit the
   Agent tool `model` param) and passes any other tier through unchanged.
   Test expectation: unit tests for all four precedence branches + the
   unknown-role rejection + malformed-config fail-soft, run BEFORE the CLI
   wrapper exists (red first).
2. **CLI wrapper.** `resolve_model_tier.py` — flat argparse (`--project-root`,
   `--review-model`, `--finalization-model`, `--execution-model`, each
   optional), resolves all three roles in ONE call and prints one JSON object
   keyed by role: `{"review": {"resolved":, "source":, "agent_param":},
   "finalization": {...}, "execution": {...}}`. Test expectation:
   subprocess-level smoke test (JSON shape, default-run resolves all three to
   `inherit`, flags resolve independently per role) — kept thin since the
   logic is already unit-tested in step 1.
3. **`reviews.json` field.** Extend `make_entry` in `review_record_core.py`
   with `model_tier: str | None = None` parameter → guarded assignment
   (`if model_tier is not None: entry["model_tier"] = model_tier`). Extend
   `record_review_pass.py`'s `record` subcommand with `--model-tier`
   (optional, default `None`), threaded through to `make_entry`. Test
   expectation: existing `record_review_pass.py` tests keep passing
   unmodified (backward-compat — omitted flag ⇒ the key is absent entirely
   from the entry, no stray `null`, so old readers see plain absence); one
   new test asserts the field round-trips.
4. **F11 floor predicate.** `model_tier_note(record, project_root)` in
   `review_record_model_tier.py`: reads `floors` from `shipwright_model_config.json`
   (absent ⇒ no-op, green); for each of `code`/`spec`/`doubt` present with
   `status == "completed"`, compares its `model_tier` against the configured
   floor for role `review` using a fixed tier-rank order
   (`inherit(unranked) < haiku < sonnet < opus` — a `null`/`None` model_tier,
   meaning "not recorded", is treated as **unknown, not below-floor** — an
   absent field must never silently rank as a violation, since older records
   and any run that used session-inherit legitimately never populated it).
   Returns an ADVISORY finding (not a STOP) — the brief explicitly scopes this
   as a loud-not-blocking complement. Wire into `check_review_record()`'s
   call sequence after `code_review_floor`. Test expectation: no-floor-configured
   no-op, below-floor advisory fires, at-or-above-floor silent, unknown
   (`None`) tier never flagged.
5. **Iterate SKILL.md wiring.** Banner usage line gets the two flags
   (`--review-model`/`--finalization-model`; no `--execution-model` — iterate
   has no execution-role spawn in its own tree). New sub-step inside §F
   (Planned Run Summary) calls `resolve_model_tier.py` once (it always
   resolves all three roles in a single call; iterate keeps only `review` and
   `finalization` from the output) and prints a `Model tiers:` row
   (`review=<resolved|inherit> (source)`, etc.).
   Step 8's spawn paragraph gains one sentence: pass the resolved `review`
   tier as the Agent tool's `model` parameter for `spec-reviewer`/
   `code-reviewer`/`doubt-reviewer`, omitting the parameter entirely when the
   resolved value is `None`/`inherit`. `iteration-reviews.md`'s cascade
   invocation block gets the same note plus `--model-tier "{resolved_review_tier}"`
   added to the `record_review_pass.py record` calls. `campaign-mode.md`
   step 3c (`sub-iterate-runner` spawn) passes the resolved `finalization`
   tier; step 3f-bis passes the resolved `review` tier to its own delegated
   cascade and to its `record_review_pass.py --force` calls. Test expectation:
   the new drift test (step below) plus a manual read-through — this step is
   prose, not executable code, so its "test" is the drift assertion that the
   instruction text exists verbatim-enough to match a stable anchor string.
6. **Build SKILL.md wiring.** Same banner line. `autonomous-loop.md` step 3c
   (`section-builder`) passes resolved `finalization` tier. `code-review.md` /
   `code-review-protocol.md` spawn paragraphs pass resolved `review` tier.
   `browser-verify.md` step 5c (`browser-fixer`) passes resolved `execution`
   tier. Test expectation: same drift test as step 5, build side.
7. **Drift tests.** `test_model_tier_spawn_instructions_present.py` —
   line-anchored search (not full-file substring match, to survive later
   edits) for a stable marker string in both `SKILL.md`s and the touched
   reference files, mirroring `test_skill_step_6_rules_present.py`'s existing
   anchor style. `test_agent_model_frontmatter_unchanged.py` — golden-hash (or
   direct `model:` value assertion) over all 11 frontmatter files, adapted
   from the reusable test's line-anchored frontmatter parser (not the
   `PINNED_OPUS` hardcode set, which is deleted).
8. **`docs/hooks-and-pipeline.md`.** Add `shipwright_model_config.json` to the
   config-data-flow table (who writes it: operator; who reads it:
   iterate/build at Planned-Run-Summary time) per CLAUDE.md's mandatory
   same-diff update rule for "what a plugin reads at startup."

## 3. Component hierarchy

n/a (no UI).

## 4. Data model changes

None (no database). New JSON config file + one new optional JSON field on an
existing artifact (`reviews.json` entries) — covered under Affected Boundaries
in the iterate spec, not a data-model change.

## 5. Test strategy

- Unit: resolver precedence (4 branches), unknown-role rejection, malformed
  config fail-soft — `shared/scripts/lib/tests/` (or wherever
  `external_review_config.py`'s own tests live — mirror that root exactly to
  stay inside the one-root-per-process rule).
- Unit: `make_entry`/`record_review_pass.py` `--model-tier` round-trip,
  backward-compat (omitted flag).
- Unit: `model_tier_note()` — 5 cases (no config, below floor, `inherit`
  flagged when a floor is configured, at/above floor, unknown/`None` tier
  never flagged).
- Drift: spawn-instruction presence in both `SKILL.md`s (+ touched reference
  files).
- Drift: frontmatter unchanged across all 11 agent files.
- Boundary Probe (small+, `touches_io_boundary` fired): round-trip the config
  file — write a `shipwright_model_config.json`, resolve, assert the resolved
  value matches; write a malformed one, assert fail-soft `{}` not a raise.
- No E2E/browser surface — this is a CLI/config feature; F0.5 surface = `cli`,
  runner = the pytest invocation above.

## 6. Alternative approach (considered and rejected)

**Alternative: a single flat `SHIPWRIGHT_MODEL_TIER` env var (one value, no
roles) instead of a three-role config/flag scheme.** Simpler to implement —
one env read, no schema, no CLI wrapper. **Rejected** because it cannot
express the operator's actual requirement: "the operator sets `review: opus`
locally and switches their session to Sonnet without the cascade following
them down" (BRIEF, "The requirement" section) needs *independent* control per
role — a flat var would force review, finalization, and execution to move
together, which is exactly the "hardcode one tier for everything" shape the
BRIEF's REJECTED section already ruled out for the frontmatter-pin design (a
single value forces the same tradeoff onto `security-fixer` as onto
`spec-reviewer`, just moved from static YAML to a slightly more dynamic env
var). The three-role split is settled in the BRIEF ("ROLES." section) and is
not re-litigated here — this alternative is recorded to show the flat-var
option was considered and why the roled design was kept instead.

## Architecture Review

Both `--mode iterate` and `--mode architecture` external review calls
returned `revise` (no `reject`). Full record — verdicts, findings and the
reconciliation against this file's own §6 Alternative-approach rejection —
lives in the iterate spec's `## Architecture Review` section (and, from F3
onward, the iterate ADR), per SKILL.md Step 4 / iteration-planning.md §2a.
