# Iterate Spec: rollback-uses-target-ref

- **Run ID:** iterate-2026-07-27-rollback-uses-target-ref
- **Type:** bug
- **Complexity:** medium
- **Status:** draft
- **Triage:** trg-74b945bc (critical, `kind: bug`, FR-01.08) — supersedes
  trg-c9dc5a16 / trg-7c6de478 / trg-84db1841

## Goal

Make the hosting phase's way back honest: a rollback must actually put the
requested version onto the target, refuse when the stored data has already
moved past that version, wait for a slow start-up instead of declaring a
release dead after one ten-second question, and — when the way back itself
fails — say plainly that nothing is confirmed running and stop.

## Root Cause (F-debug, Path C)

**Phase 1 — Read error.** No exception; the defect is a silent false success.
Error site *and* error source are the same function,
`plugins/shipwright-deploy/scripts/lib/rollback.py:29-41`. `rollback_git`
accepts `target_ref`, then issues `environment/vcs/rest/update` with only
`envName` + `context` — byte-identical to the call `deploy_from_git` makes —
and returns `success: True` with `"Rolled back {env} to {target_ref} via git"`.
Observed: the environment re-pulls branch HEAD (after a bad release, the bad
code) and the operator is told the rollback landed. Expected: the environment
runs `target_ref`, or the operation reports failure.

**Phase 2 — Reproduce.** Deterministic, no network. Stub `get_client`, capture
every outbound `_call`, run `rollback_git("dev-demo", "v1.2.3")`:

```
environment/vcs/rest/update  {'envName': 'dev-demo', 'context': 'ROOT'}
target_ref 'v1.2.3' present in ANY outbound call param: False
success reported                                       : True
```

**Phase 3 — Recent changes.** **Not a regression.** `git log` on the path shows
four commits, all security/lint sweeps; the defect is present in the file's
introducing commit `432661af` (2026-03-21) verbatim. The comment there —
*"Update the VCS project branch to the target ref"* — states an intent the code
never implemented.

**Phase 4 — Component boundary.** The break is at `rollback_git` →
`JelasticClient._call`. `environment/vcs/rest/update` takes
`session, envName, context` and **has no ref parameter at all** (confirmed
against this repo's own API table, `Spec/jelastic-cloud-deployment.md:48`, and
`references/jelastic-api.md`). In Jelastic the ref is a property of the VCS
*project*, set at `createproject` time via `branch`. So `target_ref` had nowhere
to go and was dropped into the message string.

> **Root cause (one sentence):** `rollback_git` never pins the ref onto the VCS
> project before calling `vcs/update` — the update endpoint carries no ref — so
> `target_ref` is dead data that reaches only the success message, and the
> update re-pulls branch HEAD while the message claims the requested version.

## Acceptance Criteria

*(AC1–AC10 as first drafted, then revised by the external plan review — see
`## External Plan Review` below. AC11–AC14 are review-added.)*

- [ ] **AC1 — the requested version is actually sent.** Given
  `rollback.py --strategy git --target-ref v1.2.3`, when it runs, then the
  outbound hosting-call sequence is `getprojects` → `editproject` →
  `update`, and the `editproject` request carries `v1.2.3`.
- [ ] **AC2 — no success is reported for a version that was not used.** Given
  the ref-pinning call fails, when rollback runs, then it returns
  `success: false`, the update call is never issued, and no output claims the
  environment is on `v1.2.3`.
- [ ] **AC3 — the report never over-claims.** Given the target cannot confirm
  which ref is live after the update, when rollback completes, then
  `ref_verified` is `"unconfirmed"`, `verification_error` names why (transport
  failure vs. no matching project), and the message says the ref was pinned and
  updated but not confirmed. `"confirmed"` appears only when a read-back
  returned the requested ref; a read-back returning a different ref yields
  `success: false` with `ref_verified: "mismatch"`.
- [ ] **AC4 — stored data that moved on stops the rollback and asks.** Given
  migration files exist in the working tree that are absent at the target ref,
  when rollback runs without `--ack-data-drift`, then it makes **no** hosting
  call, returns `success: false` with `data_drift.drifted: true` and
  `mutated: false`, names each drifted migration and the target profile's
  `data_rollback_strategy`, and exits `1`. Untracked migration files count as
  drift; a target ref git cannot resolve is `unknown` and refuses the same way.
- [ ] **AC5 — the liveness check waits for the target's deadline.** Given a URL
  that starts answering only after ~3 s and a policy of
  `poll_interval 1s / max_wait 20s`, when the liveness check runs, then it
  reports `success: true` with `attempts > 1`.
- [ ] **AC6 — an exhausted deadline is a failure with evidence.** Given a URL
  that never answers, when `max_wait` elapses, then the result is
  `success: false` and carries `attempts`, `waited_ms` and `deadline_seconds`.
- [ ] **AC7 — the deadline belongs to the target.** Given
  `--profile shared/profiles/deploy/jelastic.json`, when the liveness check
  runs, then `timeout`, `poll_interval` and `max_wait` are read from that
  profile, each explicit CLI flag overrides **only its own field**, and
  `policy_source` reports the winning origin per field
  (`profile:<target_id>` / `cli` / `default`).
- [ ] **AC8 — callers with no deadline keep today's single attempt.** Given
  neither `--max-wait` nor `--profile`, when the liveness check runs, then
  exactly one request is made (`attempts == 1`) — the existing
  `/shipwright-test` call site is unchanged.
- [ ] **AC9 — a failed way back names the state and stops, at the right
  altitude.** Two failure classes, never conflated:
  - *Refused before any hosting call* (bad ref form, data drift, unresolvable
    ref, unreadable profile): `mutated: false`, `halt: false`, exit `1`, and
    the message says the target was **not touched** — it makes no claim about
    what is running.
  - *Started and did not finish* (pin failed mid-write, update failed,
    read-back mismatch): `mutated: true`, `halt: true`, exit `3`, and the
    message states in plain words that this rollback did **not** verify which
    version is running, names `last_attempted` and `what_it_found`, and stops.
- [ ] **AC10 — stopping is never reported as restoring.** Given the clone
  strategy stops the failed environment, when it reports, then `restored` is
  `false` and the remaining operator steps are stated.
- [ ] **AC11 — pinning never destroys the rest of the project config.** Given
  the VCS project carries a repository URL and credentials, when the ref is
  pinned, then `editproject` is sent the **full** project object read back from
  `getprojects` with only `branch` replaced; if the current config cannot be
  read, rollback refuses (`mutated: false`, exit `1`) rather than risking a
  sparse overwrite.
- [ ] **AC12 — a half-done rollback names what it changed.** Given `editproject`
  succeeded and `update` failed, when it reports, then the payload carries
  `previous_ref` (what the project was pinned to before) and states that the
  project is now configured for `target_ref` while the running application was
  not re-verified — so the operator knows a restart would pull the rollback ref.
- [ ] **AC13 — only supported ref forms are accepted.** Given a `--target-ref`
  that is not a valid git ref name, when rollback runs, then it is rejected
  before any hosting call or git call (`mutated: false`, exit `1`). Ref
  comparison at read-back is canonical: `refs/heads/main` and `main` match.
- [ ] **AC14 — the deadline is never overshot.** Given a per-request timeout
  larger than the time remaining, when the liveness check polls, then each
  request timeout and each sleep is capped to the remaining time, so
  `waited_ms <= max_wait * 1000`. The single exception is the **first** attempt,
  which may straddle a deadline shorter than one second — a check that never
  asks at all would be worse than a sub-second overrun — and even then it is
  bounded by one second, never by the request timeout. Negative durations and a
  zero poll interval are rejected as usage errors.
- [ ] **AC15 — a target whose data does not move is not asked about data.**
  Given a profile declaring `data_rollback_strategy: none-app-only`, when a
  rollback runs, then the stored-data check is skipped entirely and reports
  `not-applicable` naming the target — an unresolvable local ref or local
  migration difference must not refuse a rollback for a target that has no data
  tier moving underneath it.

## External Plan Review

Run before build via `external_review.py --mode iterate` (openrouter;
gemini-3.1-pro-preview + gpt-5.6-terra, 2/2 succeeded, not degraded).
Adopted, with the resulting AC/plan changes:

| # | Finding | Disposition |
|---|---|---|
| 1 | `editproject` may be PUT-like — a sparse `{envName, context, branch}` write could wipe the repo URL/credentials | **Adopted.** Read → merge → write. AC11. Unreadable config now refuses instead of writing. |
| 2 | Pin-succeeds-then-update-fails leaves the project configured for the rollback ref while the old code runs | **Adopted.** AC12 — record `previous_ref`, report the config state. No auto-restore: "stop" must not mean "mutate again". |
| 3 | "Neither version is running" over-claims for a pre-flight refusal | **Adopted.** AC9 split into refused-before-mutation (exit 1) vs. started-and-unfinished (exit 3). |
| 4 | Ref forms: `branch=` may not accept a tag/SHA; read-back needs canonical comparison | **Adopted.** AC13 + documented supported forms. |
| 5 | `target_ref` reaches git — command-injection surface | **Adopted.** Argument arrays, `shell=False`, `--` separator, strict ref regex (AC13). No token or request params in error output. |
| 6 | A separate `data_drift.py` is over-production for one git call | **Adopted in spirit, module kept.** Logic reduced to two git calls; the module survives because `rollback.py` lands at ~250 LOC and the repo's bloat gate hard-caps it at 300 — inlining would breach it. |
| 7 | Where do repo root + migrations dir come from at runtime? | **Adopted.** `--project-root` (default cwd) + `--migrations-dir` (default `supabase/migrations`); the gate only runs when the profile's `data_rollback_strategy != "none-app-only"`. |
| 8 | AC7 precedence is per-field, and `deadline_source` would over-claim on mixed input | **Adopted.** Per-field `policy_source`. (The claim that `timeout` is missing from the schema is **incorrect** — `smoke_test.timeout_seconds` already exists; no schema change.) |
| 9 | Polling can overshoot `max_wait`; boundary values unhandled | **Adopted.** AC14. |
| 10 | Read-back failure must record *why*, and must not swallow programming errors | **Adopted.** AC3 gains `verification_error`; only `JelasticError`/`URLError` downgrade. |
| 11 | Bare `deploy_profile` import may not resolve from every entrypoint | **Adopted.** Path bootstrap at the executable boundary + an E2E test that runs both CLIs by subprocess from an unrelated cwd. |
| 12 | The stated F0.5 runner omits the unit suites, and an HTTP server does not observe Jelastic calls | **Adopted.** Runner widened to the whole plugin test dir; the E2E points `JELASTIC_API_URL` at a **local recording stub server**, so real client code makes real HTTP and the test inspects what was sent. |
| 13 | The Jelastic token may lack scope for `editproject`/`getprojects` | **Noted, not resolvable here** — no live target. Recorded in the profile's `known_gaps` and in `rollback-strategy.md`. |

## External Code Review

Run on the implementation diff via `external_review.py --mode code` (openrouter,
2/2 legs returned, not degraded). The gemini leg returned a **truncated
reasoning fragment rather than a finding list** — treated as content-degraded
and mined only for the one concrete observation it reached before cutting off.
All four gpt-5.6-terra findings were accepted and fixed before commit:

| # | Finding | Severity | Disposition |
|---|---|---|---|
| 1 | The drift gate ran even for a target declaring `data_rollback_strategy: none-app-only`, which the adopted plan said it would skip — such a target could be refused over a local ref it has no stake in | high | **accepted-and-fixed.** A real spec-vs-code gap I introduced: the exemption was written into the plan and never implemented. Gate moved into `data_drift.gate` and short-circuits on `none-app-only`. New AC15 + five gate tests. |
| 2 | `is_valid_ref` applied git's rules to the whole string, so `feature/.hidden` and `release.lock/tip` passed | medium | **accepted-and-fixed.** Rules are per slash-separated component; validation now is too. (The reviewer's `@` example was already rejected — the first-character class excludes it.) |
| 3 | A raw `urllib.error.URLError` from the read-back escaped `_verify_ref` instead of downgrading to `unconfirmed` | medium | **accepted-and-fixed.** Unreachable through the shipped client (`_call` wraps it), but the error tuple is a defensive contract, so `URLError` joined it. Programming errors still propagate. |
| 4 | The last attempt was floored at a one-second timeout regardless of time remaining, so `waited_ms` could exceed `max_wait` | high | **accepted-and-fixed.** Every attempt after the first is now capped to the remaining time and skipped when none is left; only the first may straddle a sub-second deadline, bounded by one second. AC14 restated to the exact guarantee, with a test per branch. |
| 5 | (gemini fragment) `_check_health` reused the full per-request timeout, so a health probe could run past the deadline | low | **accepted-and-fixed.** The health probe now counts against the same deadline. |

## Spec Impact

- **Classification:** modify
- **ADD:** none (MINT-vs-FOLD gate → FOLD: this completes a capability
  FR-01.08 already claims; no new user-observable capability)
- **MODIFY:** FR-01.08 — retire the explicit *"it does not hold today — the
  automatic version revert reports success while fetching the current state.
  Tracked as a critical open defect."* caveat now that the defect is fixed, and
  append acceptance criteria for the target-owned liveness deadline, the
  stored-data drift refusal, and the failed-way-back state statement.
- **REMOVE:** none
- **NONE justification:** n/a

## Out of Scope

- Migrating the deploy runtime to read the deploy profile for **everything**
  (auth, environments, migrations). Only the liveness policy and
  `data_rollback_strategy` are wired up here; the rest stays SKILL.md-driven
  (still an open follow-up from `rollback-discipline.md`'s Phase-0 note).
- Implementing Vercel / Compose-VPS executable flows. They stay declarative
  stubs.
- Automatic **data**-tier rollback (running down-migrations). This iterate
  detects the drift and refuses; it does not undo data.
- Backfilling `@FR-01.08` test tags — plugin test dirs are outside the
  traceability collector's manifest roots (separate campaign).

## Design Notes

No UI. Design check skipped (`Tier 0`, CLI-only change).

**Why pinning + a graded verdict, rather than a new endpoint we trust blindly.**
`JelasticClient._call` already raises on `result != 0`, so a wrong endpoint or
parameter name surfaces as a *reported failure*, never a false success — the
design is fail-closed by construction. The ref-pin endpoint
(`environment/vcs/rest/editproject`) and the read-back
(`environment/vcs/rest/getprojects`) are documented-not-live-verified here (no
`JELASTIC_TOKEN` in this environment); that is recorded honestly in the
jelastic profile's `known_gaps` and in `rollback-strategy.md`. The read-back is
**best-effort**: unavailable read-back downgrades the claim to
`ref_verified: "unconfirmed"` instead of inventing confirmation.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `shared/profiles/deploy/*.json` (hand-authored, schema-validated) | `shared/scripts/deploy_profile.py:load_profile` → `smoke_policy` / `data_rollback_strategy` | JSON |
| `shared/scripts/deploy_profile.py:smoke_policy` | `shared/scripts/smoke_test.py:run_smoke_test` | in-process dataclass |
| `plugins/shipwright-deploy/scripts/lib/rollback.py:main` (stdout) | deploy SKILL.md operator / automated caller | JSON |

**Risk flags recomputed from the actual diff** (`risk_detectors`, the
authoritative diff-driven source — the message-based classifier is not):
`touches_io_boundary` **false**, `cross_component` **false**,
`touches_ci_supplychain` **false**, `touches_build` **false**. I had expected
`touches_io_boundary` to fire; it does not, because its file patterns cover
`.env*` / `hooks.json` / `settings.json` / `*_config.json` / `*_state.json` and
a deploy profile is none of those. So the Boundary Probe is **Advisory** here,
not Safety-enforced — and it was run anyway: profile file → `load_profile` →
`smoke_policy` → `run_smoke_test`, driven through the **real** shipped profiles
rather than a hand-written fixture, plus the same path end-to-end through the
CLI. `cross_component` being false also means no integration-coverage
obligation; the E2E suites exist because the change deserves them, not because
a gate demanded them.

## Confidence Calibration

- **Boundaries touched:** deploy-profile JSON → `deploy_profile.load_profile` /
  `smoke_policy` → `smoke_test.run_smoke_test`; VCS project object →
  `jelastic_client.get_vcs_project` → `set_vcs_ref` → the wire; rollback CLI
  stdout JSON → operator / automated caller.

- **Empirical probes run:**
  - *Repro before any fix* — stubbed the client, captured every outbound call,
    ran `rollback_git("dev-demo", "v1.2.3")`. Result: one call,
    `environment/vcs/rest/update {envName, context}`; the ref appeared in **no**
    request parameter; `success: True`. This is the defect, reproduced 100%.
  - *Why the ref had nowhere to go* — read this repo's own API tables
    (`Spec/jelastic-cloud-deployment.md:48`, `references/jelastic-api.md`):
    `vcs/update` takes `session, envName, context` and no ref at all. So the fix
    could not be "pass the argument through"; the ref had to be pinned onto the
    VCS project first.
  - *Profile round-trip through the real files* — `load_profile` → `smoke_policy`
    over all three shipped profiles, asserting every resolved value equals what
    the JSON declares. Finding: all three had declared
    `poll_interval_seconds` / `max_wait_seconds` since they were written, and
    nothing had ever read them.
  - *Deadline behaviour against a real late-starting server* — a server that
    answers 503 until N seconds, driven with real wall-clock. Finding: the
    original E2E assertion was timing-flaky (the first probe could consume the
    entire deadline), and `waited_ms` overshot `max_wait` because the last
    attempt was floored at a one-second timeout. Both fixed; the guarantee is
    now stated exactly and asserted per branch.
  - *Injection probe* — `detect(repo, "v1; touch pwned")` against a real git
    repo, asserting no `pwned` file appears. The ref is rejected at the shape
    check before any subprocess is constructed.
  - *Secret-leak probe* — ran the real CLI against a recording HTTP stub with a
    sentinel token and asserted it appears in neither stdout nor stderr.
  - *Import-resolution probe* — both CLIs run by subprocess with `cwd` set to an
    unrelated temp dir, proving the bare `deploy_profile` import resolves from a
    normal invocation (no unit test can establish this).

- **Test Completeness Ledger** — 40 behaviours, **0 testable-but-untested**.
  Mirrored verbatim into `shipwright_test_results.json.iterate_latest.test_completeness`.

  | # | Testable behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | The ref is pinned via `editproject`, before `update` | tested | `test_target_ref_is_sent_to_the_host_before_the_update` PASSED |
  | 2 | A failed pin never issues the update | tested | `test_pin_failure_never_issues_the_update_and_never_reports_success` PASSED |
  | 3 | No report claims a rollback that did not complete | tested | `test_report_never_claims_a_rollback_that_did_not_complete` PASSED |
  | 4 | `editproject` carries the full project object | tested | `test_pin_sends_the_full_project_object_with_only_the_branch_replaced` PASSED |
  | 5 | Unreadable current config refuses without writing | tested | `test_unreadable_project_config_refuses_instead_of_writing` PASSED |
  | 6 | Read-back agreeing → `confirmed` | tested | `test_readback_confirming_the_ref_reports_confirmed` PASSED |
  | 7 | Read-back disagreeing → failure + `mismatch` | tested | `test_readback_returning_a_different_ref_is_a_failure` PASSED |
  | 8 | Read-back unavailable → `unconfirmed` + reason | tested | `test_unavailable_readback_downgrades_the_claim_and_says_why` PASSED |
  | 9 | A raw `URLError` downgrades rather than escaping | tested | `test_a_raw_transport_failure_also_downgrades_rather_than_escaping` PASSED |
  | 10 | A parse bug propagates, never masked as unavailable | tested | `test_readback_parse_bug_is_not_swallowed_as_unavailable` PASSED |
  | 11 | `refs/heads/x` and `x` compare equal | tested | `test_refs_heads_prefix_compares_canonically` PASSED |
  | 12 | Update failure names config state + `previous_ref` | tested | `test_update_failure_reports_the_changed_configuration_and_the_previous_ref` PASSED |
  | 13 | Invalid ref rejected before any host call | tested | `test_invalid_ref_forms_are_rejected_before_any_host_call` (5 cases) PASSED |
  | 14 | Clone strategy reports stopping, not restoring | tested | `test_clone_strategy_reports_stopping_not_restoring` PASSED |
  | 15 | Clone stop failure halts and names the state | tested | `test_clone_stop_failure_halts_and_names_the_state` PASSED |
  | 16 | A refusal claims nothing about what is running | tested | `test_a_refusal_says_the_target_was_not_touched` PASSED |
  | 17 | CLI arg validation still refuses with exit 1 | tested | `test_git_strategy_requires_target_ref`, `test_clone_strategy_requires_clone_name` PASSED |
  | 18 | Drift: no new migrations → clean | tested | `test_no_new_migrations_is_clean` PASSED |
  | 19 | Drift: committed migration since the ref | tested | `test_a_committed_migration_added_since_the_ref_is_drift` PASSED |
  | 20 | Drift: untracked migration also counts | tested | `test_an_uncommitted_migration_still_counts_as_drift` PASSED |
  | 21 | Drift: unresolvable ref → `unknown`, not clean | tested | `test_an_unresolvable_ref_is_unknown_not_clean` PASSED |
  | 22 | Drift: no migrations dir → not-applicable | tested | `test_a_project_without_migrations_is_not_applicable` PASSED |
  | 23 | Drift: non-git dir → unknown | tested | `test_a_non_git_directory_is_unknown` PASSED |
  | 24 | Drift: no project root → not-checked, not clean | tested | `test_no_project_root_reports_not_checked_rather_than_clean` PASSED |
  | 25 | Drift: a custom migrations dir is honoured | tested | `test_a_migrations_dir_outside_the_default_is_honoured` PASSED |
  | 26 | Ref validation accepts/rejects per component | tested | `test_valid_refs_are_accepted` (5), `test_dangerous_or_malformed_refs_are_rejected` (20) PASSED |
  | 27 | A metacharacter ref never reaches git | tested | `test_a_shell_metacharacter_ref_never_reaches_git` PASSED |
  | 28 | Gate refuses and names the target's strategy | tested | `test_drift_refuses_and_names_the_targets_strategy` PASSED |
  | 29 | Gate: `--ack-data-drift` lifts the refusal | tested | `test_acknowledging_the_drift_lifts_the_refusal`, E2E `test_acknowledging_the_drift_proceeds` PASSED |
  | 30 | Gate: `none-app-only` skips the question entirely | tested | `test_a_target_whose_data_never_moves_skips_the_question` PASSED |
  | 31 | Gate: undeclared strategy still refuses, says so | tested | `test_an_undeclared_strategy_still_refuses_and_says_it_is_undeclared` PASSED |
  | 32 | Liveness: no deadline → exactly one request | tested | `test_without_a_deadline_exactly_one_request_is_made` PASSED |
  | 33 | Liveness: a slow start is waited out | tested | `test_a_slow_start_is_waited_out_rather_than_called_a_failed_release` PASSED |
  | 34 | Liveness: exhausted deadline fails with evidence | tested | `test_an_exhausted_deadline_fails_and_records_the_evidence` PASSED |
  | 35 | Liveness: the deadline is not overshot | tested | `test_the_deadline_is_not_overshot_by_a_long_request_timeout`, `test_a_deadline_shorter_than_one_request_still_asks_exactly_once` PASSED |
  | 36 | Liveness: the health probe shares the deadline | tested | `test_the_health_probe_counts_against_the_same_deadline` PASSED |
  | 37 | Liveness: nonsensical durations rejected | tested | `test_nonsensical_durations_are_rejected` (4 cases) PASSED |
  | 38 | Profile: real profiles → policy round-trip; per-field precedence; malformed input rejected | tested | `shared/tests/test_deploy_profile.py`, 17 PASSED (incl. a guard that fails if the profile glob matches nothing) |
  | 39 | Client: `getprojects` context match, no-match raises, `set_vcs_ref` preserves every field incl. non-scalars, drops stale `session`/`envName` | tested | `test_get_vcs_project_picks_the_matching_context_from_a_list`, `test_get_vcs_project_raises_when_no_context_matches`, `test_set_vcs_ref_sends_every_field_back_with_only_branch_replaced`, `test_set_vcs_ref_never_forwards_a_stale_session_or_envname` PASSED |
  | 40 | *(category: integration)* profile file → reader → CLI subprocess → real HTTP → recorded request sequence, from an unrelated cwd, token absent from stdout/stderr | tested | `test_rollback_e2e_cli.py` 8 + `test_smoke_e2e_cli.py` 4 PASSED — real HTTP stub, real temp git repo, real subprocesses, no mocking |

  **Not in the ledger, and why:** the `editproject` / `getprojects` endpoint
  names cannot be verified without a live Jelastic environment
  (`requires-external-nondeterministic-service`). This is *not* a coverage hole
  in disguise — the design is fail-closed, so a wrong endpoint yields a reported
  failure, and rows 1–12 pin every behaviour that depends on the call *sequence*
  rather than on the endpoint being correct. Recorded in the profile's
  `known_gaps`. Documentation prose is not a behaviour; the one measurable
  documentation constraint (SKILL.md must not ratchet its bloat baseline) is
  enforced by the anti-ratchet gate: 451 → 446.

- **Confidence-pattern check:**
  - *Asymptote (depth).* Reached — and both times the extra probe paid. The
    first "this is done" produced a self-review that found four defects
    (an inaccurate state name, a silent non-scalar drop, a wrong policy source,
    a flaky test). The second "this is done" went to the external cascade, which
    found four more, two of them high: a gate exemption I had *written into the
    plan and not implemented*, and a deadline cap that did not hold. Ledger row
    36 and rows 30/39 exist only because those passes ran.
  - *Coverage (breadth).* 40 rows, every one `tested`, 0 untested-testable, 0
    `untestable` rows needed. 102 tests in the deploy plugin (was 24), 13 in the
    liveness suite (was 3), 17 new for the profile reader.
  - *Integration composition.* `cross_component` does not fire — this touches no
    merge/churn resolver, Claude-Code hook, phase validator or campaign machinery.
    Composition is nonetheless proven end-to-end: two E2E suites drive the real
    CLIs by subprocess against a real HTTP stub, a real git repo and the real
    shipped profile, so profile → reader → CLI → client → wire is exercised as
    one path rather than as four mocked units.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run pytest plugins/shipwright-deploy/tests -v`
  (a single plugin dir: pytest cannot collect two plugins' `tests/conftest.py`
  in one session — `ImportPathMismatchError`. Both E2E CLI suites therefore live
  under the deploy plugin; the shared liveness unit tests run in F0.)
- **Evidence path:** `.shipwright/runs/iterate-2026-07-27-rollback-uses-target-ref/surface_verification.json`
- **Justification (surface=none):** n/a — both changed surfaces are executable
  CLIs; the E2E spec drives them by subprocess against a real local HTTP
  server and a real temporary git repository.
