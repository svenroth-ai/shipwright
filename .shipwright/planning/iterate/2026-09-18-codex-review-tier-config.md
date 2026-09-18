# Iterate Spec: codex-review-tier-config

- **Run ID:** iterate-2026-09-18-codex-review-tier-config
- **Type:** feature
- **Complexity:** medium (escalated mid-flight from small — see "Escalation" below)
- **Status:** draft

## Goal

PR #770 gave the internal review cascade (spec/code/doubt/plan-reviewer) a
Codex-CLI fallback transport for when the driving harness cannot spawn an
Agent-tool subagent, but hardcoded its model identity to the literal
`gpt-5.6-sol`. Meanwhile Claude's own review-tier axis
(`shared/scripts/lib/model_tier_config.py` `TIERS`) is a hardcoded 4-value
enum (`opus`/`sonnet`/`haiku`/`inherit`) that has already gone stale once
(missing `fable`, which the Agent tool's own schema already accepts). This
iterate: (1) makes the Codex-side reviewer identity a project-configurable +
per-run-overridable choice, validated by an unconditional syntactic
allowlist (no live-catalog check — dropped after architecture review, see
"Architecture Review" below), instead of one hardcoded literal, mirroring
the config-axis mechanism Claude's axis already has; (2) fixes Claude's own
stale enum by adding `fable`. Scope is the shipwright monorepo
only — the shipwright-webui dropdown that will expose the Codex choice is a
deliberate follow-up iterate in that repo, once this axis exists to expose.

## Escalation

Started as `small` ("add a `codex` tier literal to the existing Claude
axis"). During the Section G confirmation exchange the operator corrected
the framing twice: (1) the goal is NOT a literal usable regardless of
driver, but a genuinely separate, independently-valued axis for when Codex
drives; (2) that axis must be *live*-validated against Codex's real model
catalog, not a second hardcoded list — proven necessary live in this same
session (`codex debug models` on the then-installed codex-cli 0.147.0
listed 4 models; updating to the latest 0.155.0 revealed a 5th,
`gpt-6-astra`, that had shipped in the meantime). The operator then asked
for the same live-discovery treatment on Claude's axis; empirical check
found no equivalent introspection surface exists for the Agent tool's own
model-alias enum (Anthropic's `/v1/models` lists model IDs, not the
tier-alias layer `opus`/`sonnet`/`haiku`/`fable`/`inherit` the Agent tool
consumes) — confirmed by finding `fable` already live in the Agent tool's
own JSON-schema enum in this session's tool list, with no way to query that
enum from a script. Operator decision: Codex gets real live discovery,
Claude gets its hardcoded list corrected (add `fable`) since that is the
only available fix. Per `references/mid-flight-escalation.md`'s
small→medium backfill order: this spec + the mini-plan are written
retroactively, external LLM review runs before further code changes, then
continues at medium.

## Acceptance Criteria

- [ ] AC32 (new, under FR-01.11): Given the internal review cascade's driving
  harness is Codex CLI, when a reviewer role (`review`/`plan_review`) is
  resolved, then the Codex model used is read from project config
  (`shipwright_model_config.json`, new `codex_review`/`codex_plan_review`
  keys) with a per-run override, defaulting to `gpt-5.6-sol` when
  unconfigured — instead of that literal being the only possible value.
- [ ] AC33 (new, under FR-01.11; **revised after external plan review**
  2026-09-18, **then simplified after architecture review** 2026-09-18 —
  glm=revise/high and openai=reject both converged on dropping live-catalog
  validation): Given a Codex reviewer model is being resolved, then (a) an
  unconditional syntactic allowlist (`^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`) is
  checked first, rejecting anything else with a hard error before it ever
  reaches argv construction; (b) the allowlisted value (from
  `shipwright_model_config.json` or `--codex-model`, or the hardcoded
  `gpt-5.6-sol` when neither is present) is passed straight to `codex exec
  -m <value>` — no live-catalog call, no shipwright-side model-name
  validation beyond the syntax check; (c) if the value does not name a real
  Codex model, Codex's own launch fails with its own error, which surfaces
  as this reviewer role's failure — there is no shipwright-maintained copy
  of Codex's model list to go stale.
- [ ] AC34 (new, under FR-01.11): Given Claude drives, when a `review`/
  `plan_review` tier is resolved, then `fable` is a valid literal alongside
  the existing `opus`/`sonnet`/`haiku`/`inherit` — unranked (not added to
  `RANKED_TIERS`/`RANK`, the same floor-exempt treatment `inherit` already
  has), since no capability ordering relative to opus/sonnet/haiku has been
  established for it. Every user-facing enumeration of the tier set
  (iterate/build SKILL.md usage strings, `resolve_model_tier.py`'s own
  docstring, `review_record_core.py`, `external_review_routing.py`,
  `docs/guide.md`) is updated in the same diff, and a drift test asserts
  each site's literal enumerates the exact membership of `TIERS` — a fixed,
  non-alphabetical presentation order (`opus/sonnet/haiku/inherit/fable`,
  matching the sites' own pre-existing convention) whose *membership* is
  cross-checked against `TIERS` at import time, not literally
  `sorted(TIERS)`'s alphabetical order (external code review, LOW×2,
  2026-09-18: two independent reviewers read this AC's original wording as
  requiring alphabetical order, which none of the six sites use) — the same
  staleness bug this AC fixes must not recur the next time a tier is added.
- [ ] AC35 (new, under FR-01.11; **revised after external plan review** —
  OpenAI HIGH #2: a prompt-level static placeholder can record a value that
  didn't actually run once fallback logic exists): Given
  `record_review_pass.py` records a `codex`-transport review row, then the
  value written to `--transport-note` is the **effective** model that
  `run_codex_review` actually launched — `run_codex_review` returns (or
  exposes) that value after its own resolution/fallback/validation, and the
  caller passes exactly that value through, never a value computed earlier
  in the call chain that predates a possible fallback.
- [ ] AC36 (new, under FR-01.11, supersedes FR-01.11/AC2 from
  iterate-2026-09-13): the raise-before-launch lock that removed
  `run_codex_review`'s `model=` parameter (external-review MEDIUM,
  2026-09-17, because "nothing called it") is superseded — a caller now
  legitimately needs to vary the model, so the parameter is reinstated as an
  explicit, validated keyword argument (never a module-global mutation),
  with AC33's syntactic allowlist applied at that exact entry point. The
  supersession and its reasoning (a used, validated, evidenced override is a
  stronger posture than an unused static lock, not a weaker one) is recorded
  in this run's ADR.

## Spec Impact

- **Classification:** modify
- **MODIFY:** FR-01.11 — append AC32/AC33/AC34 (Codex-reviewer
  configurability + syntactic-allowlist validation; Claude tier-enum
  correction). FOLD, not
  MINT: this completes/corrects the internal-review-cascade capability
  FR-01.11/AC31 already describes, it does not introduce a new
  user-observable capability.
- **NONE justification:** n/a (classification is modify).

## Out of Scope

- The shipwright-webui dropdown that will expose the Codex reviewer choice
  (or show it read-only) — separate follow-up iterate in that repo, once
  this axis exists server-side for it to read.
- Any change to the Agent tool's own model-alias enum or to which Claude
  models exist — `fable` is added because it is already valid, not because
  this iterate can discover or grant new aliases.
- A live-discovery mechanism for Claude's axis — established not to exist
  as an accessible introspection surface (see Escalation).
- Re-verifying the two shipwright-webui files that cite "verified live,
  codex-cli 0.147.0" against the now-current 0.155.0 — flagged to the
  operator, not part of this iterate's scope.

## Design Notes

No UI in this iterate (webui is out of scope) — n/a.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `shipwright_model_config.json` (operator-edited) | `shared/scripts/lib/model_tier_config.py` (`resolve_role_tier`, extended for `codex_review`/`codex_plan_review`) | JSON |

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-09-18-codex-review-tier-config/architecture_brief.md`
- **Verdicts:** glm=revise (severity high) · openai=reject
- **Smallest thing that would do (per reviewers):** the config axis
  (`codex_review`/`codex_plan_review` + `--codex-model`) plus the
  unconditional syntactic allowlist — **without** any live-catalog
  validation layer. Codex's own launch error already rejects an invalid
  model; the catalog call buys "detected slightly earlier" at the cost of a
  standing dependency on an undocumented `codex debug models` subcommand
  that had already changed shape mid-session (the very instability that
  motivated adding it), plus fail-closed semantics that make an explicitly
  configured run fragile to catalog flake while unconfigured runs sail
  through — an incentive not to use the feature.
- **Findings:** both reviewers converged on dropping the catalog validator
  (accepted, see Reconciliation). GLM separately confirmed the two-axis
  shape itself (config axis, not folding Codex slugs into Claude's closed
  `TIERS` enum) is correct and should stand — no change needed there.
- **Reconciliation:** accepted in full. `codex_model_catalog.py`,
  `validate_codex_reviewer_model`, `fetch_codex_model_catalog`, the catalog
  cache, and AC33(b)-(d)'s catalog-dependent clauses are dropped. AC33 is
  rewritten below to allowlist-then-launch only. This also retires several
  earlier internal/external-review findings that existed only because the
  catalog layer did (subprocess-hardening spec for `codex debug models`,
  its CI/test-skip-guard shape, its cache-reset test seam, its parser
  defensiveness contract) — noted as moot, not re-litigated.

## External Plan Review (2026-09-18)
- **Verdicts:** glm=revise · openai=revise
- **Findings (converging):** unconfigured/default path must not depend on
  live catalog validation (HIGH, openai) — **fixed**: AC33b now bypasses
  catalog entirely when nothing is configured. Explicit-value +
  catalog-unreachable must not silently substitute a different model than
  requested (MEDIUM, glm) — **fixed**: AC33d now fails closed in that case
  instead of falling back. `--transport-note` must record the effective
  post-fallback model, not a static pre-computed value (HIGH, openai) —
  **fixed**: AC35 revised, `run_codex_review` now returns the effective
  model. Catalog parser needs a defensive shape contract (MEDIUM, openai) —
  **fixed**: mini-plan step 5 now specifies it. Call-site inventory for
  `run_codex_review`/`review_via_codex.py` (MEDIUM, openai) — **fixed**:
  added as mini-plan step 5b. Drift-test brittleness from prose-parsing
  (LOW, both) — **fixed**: mini-plan step 4 now specifies a stable marker
  token per file instead of free-text parsing. Catalog-cache test reset +
  cache-lifetime docstring note (LOW, glm) — **fixed**: mini-plan step 5.
  Hardcoded-default-itself-can-go-stale is a disclosed residual gap (LOW,
  glm) — no action, noted in the ADR.
- **Reconciliation:** no findings declined; all nine integrated as fixes.
- **Status:** revise → 9 fixed, 1 disclosed

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high
- **Summary:** The two-axis decomposition is sound, but the original plan
  reversed a deliberate anti-drift lock (AC2, 2026-09-13) without recording
  it, left its only validation fail-open on a Windows argv-injection
  surface, and had one internal contradiction (AC33 vs. the mini-plan's own
  validator behavior).
- **Findings:** (11 total — see raw payload
  `.shipwright/planning/iterate/iterate-2026-09-18-codex-review-tier-config/internal-plan-review-raw.json`)
  1. HIGH/security — argv-injection via unvalidated resolved slug into
     `codex exec -m <slug>` on a Windows `.cmd` shim — **fixed**: AC33's new
     unconditional syntactic allowlist, independent of the catalog check.
  2. HIGH/architecture — silently reverses the AC2 raise-before-launch lock
     without recording supersession — **fixed**: AC36 + this run's ADR
     record the supersession and reasoning explicitly; verified against
     `codex_review_transport.py`'s own docstring before accepting the
     finding.
  3. HIGH/completeness — AC33 vs. mini-plan validator behavior contradicted
     each other on catalog-fetch failure — **fixed**: AC33 rewritten,
     adopts the safer reading (fall back to the hardcoded default, never
     pass an unvalidated value through).
  4. HIGH/architecture — a second, less-hardened reader of
     `shipwright_model_config.json` plus a guaranteed spurious
     "unrecognized key" warning — **fixed**: mini-plan now extends
     `load_model_config` itself instead of adding a new reader.
  5. MEDIUM/completeness — the tier-literal list is hand-duplicated in ~6
     places beyond `TIERS`; adding `fable` only to `TIERS` leaves the rest
     stale on day one — **fixed**: AC34 now requires updating all six in
     this diff plus a drift test.
  6. MEDIUM/completeness — `fable` in `TIERS` but not `RANK` produces a
     misleading F11 advisory ("unrecognized tier") on a now-legal value —
     **fixed**: mini-plan gives `fable` the same `inherit`-style advisory
     wording in `review_record_model_tier.py`.
  7. MEDIUM/security — the new `codex debug models` subprocess call was
     underspecified on env/binary-resolution/timeout — **fixed**: mini-plan
     now pins `shell=False`, `_resolve_codex_binary()`, `scrubbed_env()`,
     and an explicit short timeout, matching the neighboring hardened code.
  8. MEDIUM/architecture — reusing `--review-model`/`--plan-review-model`
     across two different value domains (Claude tier literal vs. Codex
     slug) is a mis-route risk defended only by prose — **fixed**: mini-plan
     now uses a distinctly-named `--codex-model` flag, and spells out the
     role→config-key mapping explicitly.
  9. MEDIUM/completeness — once configurable, the review record no longer
     names which Codex model actually reviewed — **fixed**: AC35, recorded
     via the existing `--transport-note` field.
  10. LOW/performance — CI/testing shape for the live probe and the
      subprocess-mocked unit tests was underspecified (diff-coverage
      blindness to subprocess-shaped tests) — **fixed**: mini-plan specifies
      `is_codex_available()` skip-guard for the live probe and
      module-object monkeypatching for the mocked cases.
  11. LOW/completeness — no documentation step for AGENTS.md,
      `codex_review_dispatch.md`, `hooks-and-pipeline.md`, `guide.md` —
      **fixed**: added as an explicit mini-plan step.
- **Known limitations:** none disclosed — all 11 findings integrated as
  fixes into the spec/mini-plan.
- **Status:** 11 fixed

## Confidence Calibration

Mandatory at medium (this run). Empirical probes ran through the full
internal + external review cascade (spec-reviewer → code-reviewer →
external code review → doubt-reviewer), not as a separate exercise —
the cascade's own adversarial passes were the probes, and each round's
finding was fixed and re-verified before moving on.

- **Boundaries touched:** `shipwright_model_config.json` (operator/PR-edited)
  → `lib.model_tier_config.load_model_config` (`codex_review`/
  `codex_plan_review` keys) → `tools/review_via_codex.py`'s precedence
  resolution → `lib.codex_review_transport.run_codex_review`'s allowlist →
  `codex exec -m <slug>` subprocess launch.
- **Empirical probes run:**
  1. Hostile `--codex-model` flag (`"gpt-5 && rm -rf /"`) → hard-errors
     before launch — `test_hostile_codex_model_flag_hard_errors` PASSED.
  2. Hostile `shipwright_model_config.json` value (embedded `"` + shell
     metacharacters, the attacker-reachable-via-PR path, not just an
     operator's own flag) → hard-errors before launch AND the raw value is
     absent from the reported reason — `test_hostile_config_value_hard_errors_and_does_not_echo_it`
     PASSED. This probe is the one that found the HIGH: round 1 of this
     probe (doubt-reviewer's own adversarial pass) found the value WAS
     rejected but then echoed verbatim into an error message a downstream
     shell interpolation could break out of — fixed by dropping the raw
     value from the message entirely.
  3. Trailing-newline slug (`"gpt-5.6-sol\n"`) against the allowlist regex
     — found the `^...$` anchor lets a trailing newline through under
     `.match()` (pattern-safety was a caller-convention property, not a
     pattern property) — fixed by switching to `\A...\Z`;
     `test_real_codex_model_slugs_pass_the_allowlist` (now `.fullmatch()`)
     and the hostile-slug parametrize list PASSED after the fix.
  4. Non-string `model` value (`5`, `5.0`, `b"..."`, a list, a dict) →
     `test_non_string_model_raises_transport_error_not_typeerror` PASSED
     (found and fixed: previously reached an undocumented `TypeError`
     instead of the promised `CodexReviewTransportError`).
  5. Empty/whitespace-only config value → warn-and-drop, not silently
     accepted — `test_codex_review_key_empty_string_dropped_with_warning`
     PASSED (found and fixed: originally passed the truthiness check).
  6. Padded config value (`" gpt-5.6-terra "`) → trimmed before storage, not
     passed through to hard-fail the allowlist on a whitespace typo —
     `test_codex_review_key_surrounding_whitespace_is_trimmed` PASSED.
  7. A role added to `ROLE_SCHEMAS` without a matching
     `_ROLE_TO_CODEX_CONFIG_KEY` entry →
     `test_role_to_config_key_drift_guard_raises_before_keyerror` PASSED
     (added at Step 7.5 to close a residual gap: the guard existed as an
     `assert`, stripped under `python -O`, so a future divergence would
     have reached an uncaught `KeyError` instead of the promised
     `RuntimeError` — this probe is what confirms the fix actually fires).
  8. Tier-enumeration drift (`fable` added to `TIERS` but forgotten at one
     of the six hand-written enumeration sites) —
     `test_every_tier_enumeration_site_names_fable` +
     `test_guide_md_has_the_literal_at_every_flag_occurrence` PASSED; this
     probe is what found the original drift test hardcoded its expected
     literal instead of deriving it from `TIERS` (spec-reviewer REJECT,
     round 1), so it could not have caught the staleness bug it exists for.
  9. Asymptote check (probe #9, the "found nothing" probe closing the
     depth loop): real Codex model slugs including
     `transport.CODEX_REVIEW_MODEL` itself against the allowlist —
     `test_real_codex_model_slugs_pass_the_allowlist` PASSED with **no
     finding** — the allowlist accepts every currently-real slug and the
     hardcoded default passes its own check.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | `fable` is a valid Claude tier, unranked like `inherit` | tested | `test_fable_is_a_valid_flag_tier`, `test_fable_is_unranked_like_inherit` PASSED |
  | 2 | `fable` resolves from project config, wins over default | tested | `test_fable_wins_from_project_config` PASSED |
  | 3 | Six hand-written tier-enumeration sites stay in sync with `TIERS` | tested | `test_tier_literal_drift.py` (both tests) PASSED |
  | 4 | `codex_review`/`codex_plan_review` config keys round-trip with no spurious warning | tested | `test_codex_review_key_round_trips_with_no_spurious_warning`, `test_codex_plan_review_key_round_trips_with_no_spurious_warning` PASSED |
  | 5 | Non-string config value dropped, not raised | tested | `test_codex_review_key_non_string_dropped_not_raised` PASSED |
  | 6 | Empty/whitespace-only config value dropped with warning | tested | `test_codex_review_key_empty_string_dropped_with_warning` PASSED |
  | 7 | Padded config value trimmed before storage | tested | `test_codex_review_key_surrounding_whitespace_is_trimmed` PASSED |
  | 8 | A genuinely unknown top-level config key still warns (additive-key safety) | tested | `test_genuinely_unknown_top_level_key_still_warns` PASSED |
  | 9 | JSON schema accepts `fable` as a tier, rejects it as a floor | tested | `test_schema_accepts_fable_tier`, `test_schema_rejects_fable_as_a_floor` PASSED |
  | 10 | JSON schema accepts the two Codex keys, rejects a non-string value | tested | `test_schema_accepts_codex_keys`, `test_schema_rejects_non_string_codex_key` PASSED |
  | 11 | `--codex-model` flag beats config, beats hardcoded default | tested | `test_unconfigured_uses_the_hardcoded_default`, `test_configured_model_is_used`, `test_codex_model_flag_beats_config` PASSED |
  | 12 | `plan_review` reads its own `codex_plan_review` key, independent of `codex_review` | tested | `test_plan_review_role_reads_its_own_config_key` PASSED |
  | 13 | Hostile `--codex-model` flag hard-errors before launch | tested | `test_hostile_codex_model_flag_hard_errors` PASSED |
  | 14 | Hostile config value hard-errors before launch AND is not echoed in the error | tested | `test_hostile_config_value_hard_errors_and_does_not_echo_it` PASSED |
  | 15 | Role-to-config-key drift guard raises `RuntimeError`, not `KeyError` | tested | `test_role_to_config_key_drift_guard_raises_before_keyerror` PASSED |
  | 16 | Allowlist regex rejects a trailing newline (`\A...\Z`, not `^...$`) | tested | `test_codex_review_transport_model_override.py` hostile-slug parametrize (incl. `"gpt-5.6-sol\n"`, `"gpt-5\r\n"`) PASSED |
  | 17 | Non-string `model` raises `CodexReviewTransportError`, not `TypeError` | tested | `test_non_string_model_raises_transport_error_not_typeerror` PASSED |
  | 18 | The hardcoded default itself satisfies its own allowlist | tested | `test_real_codex_model_slugs_pass_the_allowlist` (parametrized with `transport.CODEX_REVIEW_MODEL`) PASSED |
  | 19 | Every `run_codex_review` result (`completed` or `error`) carries the effective model | tested | `test_model_override_is_used_and_returned`, `test_error_result_also_carries_the_effective_model` PASSED |
  | 20 | Real-subprocess E2E: `codex_review`/`codex_plan_review` config-key split resolves end-to-end under a scrubbed env | tested | `test_review_via_codex_e2e.py` (both tests) PASSED — skips on a machine with no `codex` CLI (`is_codex_available()` guard), never silently reported green |
  | 21 | Live Codex model-catalog validation | untestable | n/a — **not built** (see "Architecture Review": rejected after both external reviewers converged; no code exists to test) |

  No `tested`-eligible row is `untestable`; row 21 is a rejected-design
  entry, not a shipped behavior, included for completeness rather than as
  a real ledger gap.

- **Confidence-pattern check:** **Asymptote (depth):** yes, "are you
  confident?"-style self-attestation produced findings multiple times this
  run (spec-reviewer round 1, code-reviewer round 1, both external-review
  legs, doubt-reviewer round 1) — per the decision rule, one more probe ran
  after each fix, and probe #9 above (the real-slug allowlist pass,
  including the hardcoded default) is the probe that found **nothing**,
  closing the loop. **Coverage (breadth):** all 21 ledger rows are
  `tested` or a rejected-design `n/a`; zero testable-but-untested rows.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run pytest shared/tests/test_model_tier_config_codex_and_fable.py shared/tests/test_tier_literal_drift.py shared/tests/test_codex_review_transport.py shared/tests/test_codex_review_transport_model_override.py shared/tests/test_review_via_codex_cli.py shared/tests/test_review_via_codex_model_resolution.py shared/tests/test_review_via_codex_e2e.py -v` — unit tests for the resolver and the syntactic allowlist (`_CODEX_MODEL_SLUG_PATTERN`), plus a real-subprocess E2E test proving the `codex_review`/`codex_plan_review` config-key split resolves end-to-end (no `codex debug models` call — dropped after architecture review, see "Architecture Review" below).
- **Evidence path:** `.shipwright/planning/iterate/iterate-2026-09-18-codex-review-tier-config/` (self-review-payload.json, spec_review_reply.json, code_review_reply.json, external-code-review-raw.json, doubt_review_reply.json) plus the F0 suite's JUnit reports at F5.
