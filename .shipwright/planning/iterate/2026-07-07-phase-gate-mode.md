# Iterate: SS2 — Non-interactive phase-gate mode (per-gate policy)

**Run ID:** `iterate-2026-07-07-phase-gate-mode`
**Campaign:** `2026-07-07-single-session-pipeline` · sub-iterate **SS2**
**Type:** FEATURE (additive enabler) · **Complexity:** medium
**Spec:** `.shipwright/planning/iterate/campaigns/2026-07-07-single-session-pipeline/sub-iterates/SS2-phase-gate-mode.md`

## Intent

The enabler for the single-session pipeline. Catalog every interactive
`AskUserQuestion` + END-TURN gate across the project/design/plan/build/deploy
phase skills, assign each a policy (`auto-default | orchestrator-approve |
hard-stop`), provide a run_config-driven mechanism the skills read under
`single_session` mode, and make each phase skill HONOR it (no END-TURN on
auto-default; approve/hard-stop still stop, per constitution). Additive:
`multi_session` (default/legacy) is completely unaffected — the mechanism is
inert unless `mode == "single_session"`.

## Spec Impact: ADD (new mechanism, additive)

## Sensitive-gate decisions (confirmed by Sven, 2026-07-07)

- **Design mockups** (`design.preview-approval`, `design.review-loop-finalize`)
  → **orchestrator-approve** (subagent generates + runs the automated
  FR-coverage self-check, then STOPS so a human eyeballs the pixels; never ships
  unreviewed UI autonomously).
- **Plan sign-off** → **auto-run plan; defer human plan-review to SS3's
  cross-phase gate-list**. No new within-phase plan-approval gate is invented in
  SS2 (plan.interview answers from context; external-review falls back to
  self-review).
- **Deploy/PROD danger family** (`deploy.prod-deploy-confirm`,
  `prod-migration-apply`, `destructive-migration`, `migration-verify-failed`,
  `manual-rollback`) + `build.destructive-sql` / `build.migration-apply-fail`
  → **hard-stop** (constitution-locked; the resolver additionally clamps
  constitution gates away from auto-default in code).

## Mechanism

- `shared/config/gate_catalog.json` — SSoT: every gate → `{phase, policy,
  default_answer, constitution, fires_in_fresh_pipeline, summary}`.
- `shared/scripts/lib/gate_policy.py` — self-validating loader (raises on a
  corrupt catalog: bad policy, auto-default missing a default_answer, a
  constitution gate marked auto-default, duplicate/unknown ids), the **resolver**
  (`mode != single_session` → `interactive` = today's behaviour, mechanism inert;
  `single_session` → catalog policy), and `render_catalog_markdown` (doc
  generator).
- `shared/scripts/tools/resolve_gate_policy.py` — CLI the skills invoke. Mode
  precedence: `--mode` > `SHIPWRIGHT_RUN_MODE` env > `run_config.mode` (via
  `--project-root`) > `multi_session`. Subcommands: `--gate <id>`, `--phase <p>
  --list`, `--list`, `--render-doc`.
- `shared/prompts/single-session-gate-discipline.md` — the canonical honoring
  contract (runtime-reachable via the shared/ self-heal).
- Each of the 5 phase `SKILL.md` gets a compact "Single-Session Gate Discipline"
  pointer block (deploy is grandfathered at 453 LOC → minimal pointer + an
  offsetting trim to stay ≤ 453).
- `docs/gate-catalog.md` — generated from the JSON; drift-guarded.

## Scope boundary

SS2 catalogs the 5 named phases only (per the sub-iterate spec). `test` /
`changelog` / `security` gates are a deliberate follow-up — the JSON catalog is
trivially extensible; noted (not silently dropped) in the doc. The WebUI
"Review mockups" preview button for the paused design gate is a WebUI-track
follow-up (coordinated separately per campaign.md), not part of this monorepo
sub-iterate.

## Acceptance Criteria (from SS2 spec)

- [ ] documented gate catalog (every phase, every gate) with assigned policy
- [ ] gate-mode mechanism the skills read under single_session
- [ ] each phase skill honors auto-default (no END-TURN) and still stops on
      approve/hard-stop
- [ ] dry-run test per phase; constitution AskUserQuestion discipline respected
- [ ] sensitive-gate policies confirmed by Sven ✅

## Confidence Calibration

- **Boundaries touched:** `touches_io_boundary` — the resolver reads
  `shipwright_run_config.json` (`mode`) and parses `shared/config/gate_catalog.json`
  (`json.load`), and writes the generated `docs/gate-catalog.md`.
  (`touches_auth`/`touches_rls` reported by the classifier are prose
  false-positives — no auth/RLS code — recorded in `degraded[]`.)
- **Empirical probes run:**
  - Generated `docs/gate-catalog.md` via the real CLI on Windows → 90 lines,
    **pure LF, no CRLF** (proves the cp1252-stdout + newline handling).
  - `resolve_gate_policy.py --gate deploy.prod-deploy-confirm --mode single_session`
    → `hard-stop`; `--gate project.interview --mode single_session` → `auto-default`;
    `--mode multi_session` → `interactive` (mechanism inert).
  - 52 SS2 tests pass; ruff@0.15.15 clean; `deploy/SKILL.md` = **453 LOC** (no
    bloat ratchet — verified).
- **Test Completeness Ledger:**

  | Behavior | Disposition | Evidence |
  |---|---|---|
  | Catalog self-validates; raises on corrupt (bad policy / missing default / constitution-auto-default / dup id) | tested | `test_gate_catalog` (validate_* + `test_load_raises_on_corrupt_catalog`) |
  | Resolver inert under multi_session / unknown mode | tested | `test_multi_session_is_inert_for_every_gate`, `test_unknown_mode_is_inert` |
  | Resolver per-gate policy under single_session | tested | `test_single_session_{auto_default,orchestrator_approve,hard_stop}` |
  | Constitution clamp — never auto-answer a locked gate | tested | `test_resolver_never_auto_answers_a_constitution_gate`, `test_validate_rejects_constitution_auto_default` |
  | Unknown gate id fails loudly | tested | `test_resolver_unknown_gate_raises`, CLI `test_unknown_gate_exits_2` |
  | Mode precedence (explicit>env>config>default) | tested | `test_mode_precedence_*`, `test_mode_default_when_nothing_set` |
  | run_config mode round-trip (Boundary Probe) | tested | `test_run_config_mode_round_trip`, `test_read_run_config_mode_*` |
  | Per-phase dry-run (5 phases) | tested | `test_dry_run_per_phase[project|design|plan|build|deploy]` |
  | Sensitive-gate policies pinned to Sven's decisions | tested | `test_known_sensitive_gates_have_confirmed_policies` |
  | Doc generated + deterministic + JSON↔doc drift | tested | `test_render_markdown_*`, `test_gate_catalog_doc_sync` |
  | CLI wiring (--gate/--phase/--list/--render-doc/env/project-root) | tested | `test_resolve_gate_policy.py` (9 tests) |
  | Honoring block present in all 5 skills + shared contract exists | tested | `test_phase_gate_discipline_present` |
  | deploy/SKILL.md stays ≤ 453 (no ratchet) | tested | `test_bloat_baseline` (shared suite) |
  | Phase-runner subagent actually honors the block at RUNTIME | untestable → `covered-by-existing-test` deferred to SS3 | Execution (spawn subagent, observe no-END-TURN) is SS3/SS4 scope; SS2 ships the mechanism + prose + drift guards only |

  0 testable-but-untested behaviors.
- **Confidence-pattern check:**
  - *Asymptote (depth):* the resolver, validator (incl. corrupt-catalog +
    constitution-clamp fail-closed paths), and the config-read Boundary Probe are
    fully unit-covered — more tests wouldn't move confidence.
  - *Coverage (breadth):* all 5 phases dry-run tested; all ~47 gates iterated in
    both multi/single resolution; doc-drift + honoring-block presence guarded.
  - *Integration composition:* `cross_component` is NOT triggered (no
    merge/churn/hooks/verify_phase/campaign machinery touched → no
    integration-coverage gate). The config→mode→policy chain and the JSON→render→
    committed-doc chain are each covered end-to-end by a single test.
