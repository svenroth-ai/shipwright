# Driven-run phase gate enforced by default (campaign A5)

Run: `iterate-2026-10-25-a5-test-migration-and-flip` (campaign `brief-driven-run-a-real-gates`, sub-iterate A5). Builds on A4 (`iterate-2026-10-24-a4-gate-seam-and-override`).

## Decisions

1. **The flip.** `ENFORCE_PHASE_GATE_DEFAULT = True`. Every `single-session-apply` of an ok:true result runs the phase validators plus canon checks. Tests can still pass `enforce_gate` per call, and no shipped caller does: an AST guard test pins this, so `--override-reason` (recorded) stays the only production bypass.
2. **Precondition: the verifiers resolve in every install layout.** Proven by `test_phase_gate_cache_layouts.py`, which covers the Claude cache, its `plugins/` mirror, the Codex bundle and the checkout, with a negative control. The real installed cache was also probed by hand. A layout without `shared/scripts/tools/verifiers` fails closed with a non-retryable `canon_degraded` ask. The message now says this is an installation problem and names the fix.
3. **One shared minimal-valid-project builder** in `shared/testkit/minimal_valid_project.py`. It is a bare module with no `lib`/`scripts`/`tools` package, so it is ADR-044-safe from both test roots. A validator or canon change the builder no longer satisfies must update the builder in the same diff. The builder records `phase_history` under a run id it mints itself, the way a skill does, never under the run's `runId`. Canon C1 is satisfied via the `phase_history` terminal outcome rather than a `phase_completed` event; see decision 9 for why.
8. **The canon `phase_history` run id is resolved, not assumed** (A5 review, doubt high). The check matches one run id exactly. The phase skills mint their own `SHIPWRIGHT_RUN_ID`, and project/design/plan used to overwrite even a pre-set one. With the old gate (verifying by `config.runId` only), every real driven phase would have been rejected at its first apply, and an unattended run could never finish.
   - The fix has three parts:
     - `orchestrator_pkg/gate_run_id.canon_run_id` picks the id to verify. Only an entry recorded during THIS task counts: claimed (`startedAt`) <= `at` <= now + 5 min, `split` absent or matching. Among those, the run's `runId` if one carries it, else the newest one's id; with none, a sentinel id no entry carries, so the check fails. Review round 2: an earlier split's or claim's entry under the exported `runId` used to pass the rule, which made the gate a rubber stamp for plan/02 and every re-run.
     - project/design/plan now keep a pre-set id (`: "${SHIPWRIGHT_RUN_ID:=…}"`).
     - `phase-runner.md` exports the run's `runId` before a skill's finalization block.
     - The build check `phase_history[build] has sections` takes the newest entry for the id, preferring `current_split`'s, not the first (build/01's), which rejected build/02 on every attempt once one id labels every split.
   - `integration-tests/test_phase_gate_real_skill_canon.py` runs the skills' real finalization blocks (extracted from the reference docs) against the gate, both with a minted id and with the exported one, and across a second split (plan/02 without its entry is rejected; build/02, via the build skill's own block, passes on its own entry). It also shows a phase with no audit entry is still rejected.
   - Option rejected: making skills alone responsible. Each Bash call is its own shell and the export is prose an LLM follows; a deterministic gate rule does not depend on that.
9. **Known event loss, documented as such.** A phase skill records `phase_completed` before apply. `record_event` dedups by (phase, splitId) within a session, first wins, so the loop's own end event (with `phaseTaskId`) is dropped in real driven runs. That is pinned by the real-skill test. The builder therefore skips the skill event, so the tests that pin the loop's pair measure the loop. C1's event lookup is not scoped per run or split.
10. **An unknown retry state is terminal.** No loop state, or one that is foreign or malformed, cannot be counted. An enforced rejection then takes the autonomy's terminal at once (`ask_human` / `failed`) instead of reporting an uncapped retry forever.
11. **Rollback is a code change:** set `ENFORCE_PHASE_GATE_DEFAULT = False` in a commit. There is no runtime switch.
4. **`--force-status skipped` on an in_progress task needs no recorded reason.** It is an operator escape hatch:
   - `skipped` is not `done`;
   - the design validator refuses a skipped task as an exemption;
   - no successor is planned, so the next `single-session-next` answers `blocked`.
   The override reason exists to tell "passed" from "waved through", and a skip cannot be read as a pass.
5. **Inform notes on the v2 pass path are returned, not persisted.** The master relays `gate.inform`. Only overrides write a validation record.
6. **Runs started before A5 and resumed after it** are gated from their next apply on. `--override-reason` is the documented way past a phase they cannot satisfy. `SHIPWRIGHT_ENFORCE_CRITICAL_GATES` is untouched and stays opt-in.
7. **Classifier override.** Step 2 classified the change `large` (conf 0.75, `touches_migrations`). That signal came from prose keywords ("migrate tests"); no DB migration is involved. The run proceeded at `medium`, matching the BRIEF's complexity for A5, and the diff-driven Step 3.4 re-check confirmed `medium` with no risk flags.

**Touch-set deviation from BRIEF D10, recorded:**
- `test_single_session_loop_branches` was not edited: its only apply hits `not_found` before the gate.
- Also edited, because each flipped (raw `complete-phase-task` ok:true, or an assertion on the default): `test_lifecycle_cli`, `test_single_session_gate_seam`, `test_single_session_gate_hardening`, `test_cross_surface_backcompat`, `test_phase_invocation_mode_integration`.
- Production edits beyond the flip:
  - `phase_validators_canon.py`: the `canon_degraded` message names the installation fix.
  - deploy `SKILL.md`: stale Stop-hook completion text.
- Added in the review round:
  - `orchestrator_pkg/gate_run_id.py`.
  - The unknown-state terminal in `phase_gate.py`.
  - The `SHIPWRIGHT_RUN_ID` keep-if-set lines in the project/design/plan finalization references.
  - `phase-runner.md` (export the run's `runId`).
  - Run `SKILL.md`: the needs_validation template is corrected.
  - The A4 changelog drop no longer says "off by default".

## Architecture Review

- External `--mode architecture` (codex driver): glm **approve**, openai **approve**.
- Internal `architecture-internal-reviewer` (opus): **approve**.
- All three reviewers took option A as the smallest option that meets acceptance.
- Option B (tests switch the gate off) fails "not weakened". Option C (opt-in) leaves an unattended run unsafe by default.

How the findings were handled:
- **Builder ownership note:** accepted. The coupling note is in hooks-and-pipeline.md.
- **Fail-closed when the checks cannot load:** already covered (negative control). The message now names the fix.
- **Resumed in-flight runs:** accepted and documented.
- **Critical-gates switch named:** accepted.
- **No production bypass:** accepted, via an AST guard test.
- **Per-call off allowed for pure pre-gate unit tests:** rejected. No migrated test needed it, and every migrated test runs the real gate.

## External-Plan-Review-Findings

Plan review: glm and openai both approve. Internal `opus-plan-reviewer`: approve.

| Finding | Disposition |
|---|---|
| Land e2e with the flip | accepted-and-fixed: same commit |
| Builder module name collision | rejected-with-reason: the name is unique in the repo; the docstring documents the import mechanism |
| C1 via phase_history hides the event path | rejected-with-reason: the loop's own `phase_started`/`phase_completed` pair is still pinned by `test_loop_emits_one_tracked_start_end_pair_per_split` (sole_mode) against the real loop |
| Layout test must not depend on the installed cache | accepted: the four layouts are temp copies; the hand probe is extra |
| Raw `complete-phase-task` coverage | accepted-and-fixed: `test_lifecycle_cli` pins the ok:true refusal and the ok:false strict-stop |
| Runtime budget | accepted: the e2e runs 2 full drives in ~10s |
| Default flip covered without an explicit override | accepted-and-fixed: the e2e and CLI drives pass no enforce flag |
| Rejection leaves no completion and no successor | accepted-and-fixed: asserted at every rejection in the e2e |
| Fix hint on `canon_degraded` | accepted-and-fixed |
| Force-skip without a reason | rejected-with-reason: decision 4; a recorded reason or event for skips is a separate change, noted as an open item |
| Gate passes leave no durable record | rejected-with-reason: decision 5; persisting a gate summary is a separate change |
| Stale run SKILL.md:291 prose | accepted-and-fixed (review round): the template now says skipping does not finish the run; that no driven command re-checks a needs_validation run is stated as a known gap |
| Every pipeline phase has a validator | accepted-and-fixed: pin test added |
| Stale runner can still apply after re-dispatch (sessionUuid not rotated) | open note, pre-existing CAS property |
| Layout test copies shared/ more than once | accepted as-is |

## External-Code-Review-Findings

External code review: openai and glm both approve.

| Finding | Disposition |
|---|---|
| `_APPENDIX` read at import | rejected-with-reason: it is a `Path`, read lazily inside `_project()` |
| Bypass scan skips `shared/testkit`, whitelists `None` | rejected-with-reason: `None` means "use the default" in `apply_phase_result`; `shared/testkit` is test code |
| Hardcoded changelog date | accepted-and-fixed: today's UTC date |
| `_plan` falls back to split 01's FR | accepted-and-fixed: raises on an unknown split |
| `_finish_phase` RMW without lock | accepted as-is: test-only, sequential |
| e2e fixed phase sequence | accepted as-is: the fixed sequence is the assertion (dispatch order) |

## Self-Review

1. Spec Compliance: pass
2. Error Handling: pass
3. Security Basics: pass
4. Test Quality: pass
5. Performance Basics: pass
6. Naming & Structure: pass
7. Affected Boundaries: pass (result contract → apply → validators, round-tripped by subprocess drives; install layout → verifiers, probed in four layouts)

The payload is `self-review-payload.json` in the run dir.

## Confidence Calibration

Boundaries:
- phase-runner result contract → `single-session-apply` → phase validators and canon checks
- `phase_validators` → `shared/scripts/tools/verifiers` across install layouts

Probes run: 6.
- Four layouts: clean.
- Negative control: fails closed.
- Real installed cache by hand: clean.
- Ad hoc driven-run probes: a control run reached `complete`. Each planted defect was rejected at the right phase:
  - failing unit tests, at test
  - a deleted release tag, at changelog
  - an incomplete build section on split 02, at build/02-ui

One finding came up during the build: C1 needed a phase_history fallback. It was fixed, and later probes found nothing new, so the asymptote is reached.

Not probed: third-party install layouts other than the four shipped. That is acceptable because such a layout fails closed with an install hint rather than passing.
