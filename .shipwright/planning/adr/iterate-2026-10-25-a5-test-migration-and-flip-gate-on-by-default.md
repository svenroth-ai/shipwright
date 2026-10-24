# Driven-run phase gate enforced by default (campaign A5)

Run: `iterate-2026-10-25-a5-test-migration-and-flip` (campaign `brief-driven-run-a-real-gates`, sub-iterate A5). Builds on A4 (`iterate-2026-10-24-a4-gate-seam-and-override`).

## Decisions

1. **The flip.** `ENFORCE_PHASE_GATE_DEFAULT = True`. Every `single-session-apply` of an ok:true result runs the phase validators plus canon checks. Tests can still pass `enforce_gate` per call, and no shipped caller does: an AST guard test pins this, so `--override-reason` (recorded) stays the only production bypass.
2. **Precondition: the verifiers resolve in every install layout.** Proven by `test_phase_gate_cache_layouts.py`, which covers the Claude cache, its `plugins/` mirror, the Codex bundle and the checkout, with a negative control. The real installed cache was also probed by hand. A layout without `shared/scripts/tools/verifiers` fails closed with a non-retryable `canon_degraded` ask. The message now says this is an installation problem and names the fix.
3. **One shared minimal-valid-project builder** in `shared/testkit/minimal_valid_project.py`. It is a bare module with no `lib`/`scripts`/`tools` package, so it is ADR-044-safe from both test roots. Canon C1 is satisfied via the `phase_history` terminal outcome, not a `phase_completed` event: `record_event` dedups that event by (phase, splitId), so a fixture event would swallow the loop's own end event. A validator or canon change the builder no longer satisfies must update the builder in the same diff.
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
| Stale run SKILL.md:291 prose | open note, pre-existing (a needs_validation run with skipped tasks has no driven completion path), not changed blind |
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
