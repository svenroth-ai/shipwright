# Iterate Spec: gate-hardening-leftovers

- **Run ID:** iterate-2026-10-25-gate-hardening-leftovers
- **Type:** change
- **Complexity:** medium
- **Status:** implemented

## Goal
Small leftovers of the finished campaign `brief-driven-run-a-real-gates` (A3, A4, A5 and the two follow-up iterates). Each was located in code on `origin/main` (5b6686ae5) and decided with evidence:

1. A3 accepted lows: `_validate_plan`'s docstring claims the split membership check "keeps it from naming a path outside `.shipwright/planning/`", but the check only runs when splits resolve (PR #904 Tier-3 review). `test_skip_reason_accepts_only_non_blank_strings` never passes a blank or whitespace-only string, so its name claims a rule it does not test.
2. A4 notes: (a) `single_session_apply` detects the override refusal by comparing `blockMessage` with the class NAME string `OverrideRefused`; (b) the design freeze must stay behind the gate; (c) the guided retry cap only holds if the master stops: after the terminal `ask_human` rejection, `single-session-next` re-dispatches the same task again and again; (d) an override record cannot prove a person made it.
3. A5 note: for a non-final split the build skill runs `archive_split` (sections move to `split_NN_sections`, `sections` becomes `[]`) before its result is applied. The build gate then sees no current sections: `_validate_build` asks "No sections found for current split" and the canon `build_checks` per-section checks compare nothing. Probed: a real build/01 of a two-split run is rejected by the enforced gate.
4. A3's three validator test files carry `FR-01.01/AC01` (pipeline order); what they prove is `FR-01.01/AC02` (a phase that failed its own checks is not marked finished).
5. `phase_task_core._check_owner_version` defaults a missing task `version` to 0, while dispatch, apply and recover default it to 1: a version-less task is refused `stale_version` with the descriptor's own version.
6. A raw `claim-phase-task` idempotent re-claim does not rotate `version` (only `single-session-next` does).

## Acceptance Criteria
- [x] AC-1 (item 1): `_validate_plan`'s docstring states the split membership check runs only when the run's splits resolve. `test_skip_reason_accepts_only_non_blank_strings` asserts that a blank and a whitespace-only value under either key yield `""` and that a blank `reason` falls through to a non-blank `skip_reason`.
- [x] AC-2 (item 2a): `single-session-apply --override-reason` whose locked-config hook raises `phase_gate.OverrideRefused` (or a subclass of it with another name) returns `reason: "override_requires_human"`; a hook exception of an unrelated class that is merely NAMED `OverrideRefused` returns `reason: "on_complete_failed"`. The decision is an `except phase_gate.OverrideRefused` in the composed completion hook, not a string comparison.
- [x] AC-3 (item 2b): a design apply whose enforced gate rejects with a retry due or the `ask_human` terminal leaves the run config byte-identical (no `splits_frozen`, no `runConditions.splitMode`) — pinned by a test. The order gate → split read → freeze-in-lock is documented, with the limit that the gate and the freeze read the split authority separately.
- [x] AC-4 (item 2c): a gate rejection that takes the `ask_human` terminal (guided past `MAX_GATE_RETRIES`, a non-retryable finding, or an unknown autonomy) records `gateTerminal = {phaseTaskId, version, issues}` in loop state. While it matches the frontier task at its current version, `single-session-next` and the read-only resolver return `{action: "ask_human", reason: "phase_gate_terminal", task, version, issues, override_allowed, recover_useful}` with exit 0 (`recover_useful` false for an archived split; the marker is also written for a terminal no loop state counted) and claim nothing (run config and loop state unchanged). `single-session-recover` lifts it (fresh tries); an `--override-reason` apply with the last descriptor still completes; a crash-resume after retryable rejections still dispatches; an unreadable loop state never blocks the resolver. Autonomous runs are unchanged (they take the `failed` terminal, no marker).
- [x] AC-5 (item 2d): `docs/hooks-and-pipeline.md` states the exact limit of an override record: it records the caller-supplied reason, the run's autonomy and the entrypoint, and proves nothing about who ran the command.
- [x] AC-6 (item 3): after `archive_split` moved split `01-a` on, `validate_phase("build", split_id="01-a")` judges `split_01_sections`: passes when they are complete with tests, asks when one is incomplete, and asks "No sections found for split '01-a'" when nothing is archived for it. `run_build_checks(split_id="01-a")` runs every section check (completion, B3, B6, C1, C4, C5, phase_history sections, preferring the `01-a` history entry) over those archived sections — a missing `work_completed` event for an archived section is reported. Without `split_id`, or with `split_id == current_split`, both are unchanged. The archived bucket counts only when `completed_splits` names the exact split. An ask on an archived split carries `kind: archived_split` and is not retryable. The canon checks get `split_id` only for an archived split. A canon `run_build_checks` without a `split_id` parameter yields an ask-level `canon_degraded` note instead of a `TypeError`.
- [x] AC-7 (item 4): the three A3 validator test modules (`test_phase_validators_split.py`, `_canon.py`, `_late.py`) are tagged `FR-01.01/AC02`.
- [x] AC-8 (item 5): one constant `DEFAULT_TASK_VERSION = 1` in `phase_task_core`, read through one helper by the owner check, dispatch descriptor, apply CAS and both recover paths. A version-less `in_progress` task completes with `expected_version=1` (was `stale_version`).
- [x] AC-9 (item 6): decided document-only, with evidence in the ADR and the hooks doc.

## Spec Impact
- **Classification:** none
- **ADD:** none · **MODIFY:** none · **REMOVE:** none
- **NONE justification:** restores what FR-01.01 already requires: AC02 (a phase that did not satisfy its checks is not marked finished and the run pauses for a person — a non-final build that did satisfy them is not wrongly refused, and a guided run really does pause at the cap) and AC03 (the override record is described for what it proves). Requirement text unchanged. Affected FR: FR-01.01.

## Out of Scope
- The v1 `update-step` path (passes no split id; its build/01 behaviour after `archive_split` is unchanged).
- Authenticating a person behind an override (no mechanism exists to do it honestly; documented instead).
- Rotating `version` on a raw `claim-phase-task` (decided against, see AC-9).
- `shared/scripts/lib/phase_invocation_mode.py` reads `task.get("version")` without a default; it cannot import the run plugin's constant and only reports the value.

## Design Notes
n/a (no UI).

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `shared/scripts/tools/archive_split.py` (build skill, non-final split) | `phase_validators._validate_build`, `tools.verifiers.build_checks` | `shipwright_build_config.json` `split_NN_sections` / `sections` / `current_split` |
| `single_session_apply._gate_rejected` → `loop_state.record_gate_rejection` / `record_gate_terminal` | `single_session_loop.resolve_next_dispatch` (`gate_terminal_for`) | `.shipwright/run_loop_state.json` `attempt` / `gateRejections` / `gateTerminal` |
| `single-session-next` | the master (run SKILL.md loop) | `{action: "ask_human", ...}` JSON on stdout, exit 0 |
| `phase_task_lifecycle` task records | owner check / dispatch / apply / recover | `phase_tasks[].version` (absent = 1) |

## Confidence Calibration
- **Boundaries touched:** the four rows above.
- **Empirical probes run:**
  1. archive_split -> build gate (before the fix, scratch probe with the real `archive_split`): `validate_phase("build", split_id="01-a")` asked "No sections found for current split" and canon C1 reported "no complete sections to check" — finding, fixed.
  2. Same producer after the fix: the real `archive_split` output read by both readers gives the archived sections (parity test); C1 reports the missing event for the archived section; the split's own `phase_history` entry is chosen over the current split's — no finding.
  3. Skew probe: a `run_build_checks` stub without `split_id` -> ask-level `canon_degraded`; a compatible verifier raising an internal `TypeError` propagates (not mistaken for skew) — no finding.
  4. Loop state round trip: apply writes `gateTerminal`, resolver reads it; malformed marker version, another run id, another task, another version, `None` state and an unreadable file (`{bad`) each read as "no marker" and never block — no finding.
  5. CLI boundary through the real `orchestrator.py` subprocess: three real gate rejections of the project phase, then `single-session-next` exits 0 with `ask_human`, run config byte-identical, override with the last descriptor completes, the successor dispatches — no finding.
  6. Version-less task (`version` key removed): completes with `expected_version=1` (was `stale_version`), recover and redispatch go 1 -> 2 — finding on base, fixed; re-probe no finding.
- **Edge cases not probed (acceptable):** a concurrent second master racing the marker write (the loop is serial by design, single writer of `run_loop_state.json`); an installed plugin cache mixing a new run plugin with an old `shared/` tree beyond the `split_id` signature (covered by the generic `[gate-error]` path).
- **Test Completeness Ledger:** see `shipwright_test_results.json` `iterate_latest.test_completeness` (F5).
- **Confidence-pattern check:** asymptote reached on each boundary (a finding was fixed and followed by two no-finding probes, or two no-finding probes from the start); integration composition covered by `integration-tests/test_gate_cap_holds_cli.py` (apply, loop state, resolver and CLI composed through real subprocesses).

## Verification (medium+)
- **Surface:** cli
- **Runner:** `uv run pytest integration-tests/test_gate_cap_holds_cli.py` — real `orchestrator.py` subprocesses (`write-config`, `single-session-next`, `single-session-apply`): the guided cap answering `ask_human` and the override; and a two-split run whose build/01 is archived by the real `archive_split.py` CLI before apply, passing its gate and driving on to `complete` (red on the base validator).

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** items 1, 2a, 2b, 4, 5, 6 sound; 2c's counter-derived refusal was wrong after a crash-resume and invisible to the resume card; item 3 needed the empty-`current_split` guard, one prefix rule, a version-skew guard and an answer for retries that cannot fix an archived split.
- **Findings:**
  - architecture/medium — counters cannot tell a crash-resumed dispatch from a capped one: fixed (persisted `gateTerminal` keyed to task + version).
  - completeness/medium — refusal only in `next_dispatch`, the resume card would still say dispatch: fixed (check in `resolve_next_dispatch`).
  - correctness/medium — "guided" is the wrong condition, absent/typo autonomy also takes `ask_human`: fixed (condition is `terminal == "ask_human"`; `override_allowed` reported).
  - completeness/low — marker must match this run and this frontier task: fixed (`gate_terminal_for` checks runId, task, version).
  - architecture/medium — keep `_validate_plan`'s empty-`current_split` guard, one prefix rule: fixed (`sections_for_split`, used by plan and build, mirrored + pinned).
  - architecture/medium — gate retries on an archived split cannot fix anything: fixed (`kind: archived_split`, non-retryable).
  - architecture/low — `verify_phase.py` / compliance `audit_adapters` consumers and arity: fixed (positional default `split_id`, arity unchanged), plus version-skew guard for an older installed `run_build_checks`.
  - correctness/low — 2a has no import cycle and still writes nothing on refusal; check refusals only on `on_complete_failed`: integrated.
  - completeness/low — all version readers listed: integrated (`task_version` everywhere in the run plugin; `phase_invocation_mode.py` out of scope).
  - completeness/low — AC-3 byte-identity only holds for a retry-due / ask_human rejection: fixed (AC-3 reworded).
  - completeness/low — new `ask_human` action must reach the loop reference, SKILL.md and maybe the WebUI; plan canon gets no split_id: fixed for docs; WebUI and plan canon disclosed as follow-ups.
- **Known limitations:** plan canon checks get no `split_id`; the WebUI may not know the `ask_human` next action.
- **Status:** 10 fixed, 1 disclosed

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes
- **Severity:** low (verdict: approve)
- **Summary:** both defects are real and nothing existing absorbs them; take A's archived-split reader for the build gate and B's explicit `gateTerminal` marker for the cap; not C; D only for override provenance and the raw claim.
- **Findings:**
  - necessity/low — build it, D only for AC-5 / AC-9: agreed, already the shape.
  - smallest-option/low — counters cannot carry the terminal; B is the smallest correct mechanism, C is riskier: agreed.
  - completeness/medium — pin the marker's lift/keep rules on every path; clear it explicitly; say it covers only the single-session loop: fixed in part — new test (a plain pass with the last descriptor moves on), docs state the scope; explicit clearing declined: the marker is keyed to (task, version) and every lifting path changes one of them, so a second reset path would only add a way to drift.
  - security/low — raw `claim-phase-task` is not gated: disclosed in the hooks doc next to the raw-claim decision.
  - complexity-cost/low — two readers of the `split_NN_sections` format: fixed — a parity test feeds the real `archive_split` output to both readers; a single key constant next to `archive_split` declined (that module's own key derivation is out of scope; the mirror test pins the readers).
  - completeness/low — a split neither current nor archived: fixed — asserted non-retryable "No sections found for split X".
- **Known limitations:** raw `claim-phase-task` is not refused past the cap; `archive_split` and the readers derive the bucket key separately.
- **Status:** 3 fixed, 2 disclosed, 1 declined

## External Plan Review
- **Branch:** A (available) · **Verdicts:** glm=approve · openai=revise
- **Findings:**
  - openai/high — the mini-plan still described the superseded counter-derived cap: accepted-and-fixed (mini-plan rewritten to the persisted `gateTerminal` design: writer, reader, tests).
  - openai/medium — version-skew guard missing from the plan, and an internal `TypeError` must not read as skew: accepted-and-fixed (planned explicitly; test that a compatible verifier raising `TypeError` propagates).
  - openai/medium — the archived-split view must pick that split's own `phase_history` entry: accepted-and-fixed (the view sets `current_split` to the requested split; conflicting-history test in `shared/tests`).
  - glm/medium — consult the marker only when the counters corroborate it: rejected-with-reason (the counters cannot carry the terminal, which is why the marker exists; the key is run id + task id + version, recover only ever raises the version and ids are per run).
  - glm/low — mirror test should cover empty-archived and `split_id == current_split`: accepted (case matrix already has both; plus a parity test over real `archive_split` output).
  - glm/low — a persisted explicit `version: 0`: checked, no writer emits it (grep: no `"version": 0` / `get("version", 0)` left in the run plugin or shared scripts).
  - glm/low — the subclass test must use a genuine subclass: confirmed (it does; the impostor is a separate class with the same name).
  - glm/low — WebUI may not know `ask_human`: disclosed as a follow-up.

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-10-25-gate-hardening-leftovers/architecture_brief.md`
- **Verdicts:** glm=approve · openai=approve
- **Smallest thing that would do (per reviewers):** as proposed — option B's version-keyed marker plus the archived-split reader.
- **Findings:**
  - glm/low simpler-alternative — probe option C (archive at the start of the next split): rejected-with-reason (the build skill owns that step; moving it changes the final split's archive timing and the v1 path, and the internal architecture review judged it larger and riskier).
  - glm/low proportionality — keep the marker exactly as scoped: accepted (no manual clear, no general paused state).
  - glm/low ownership — mark the skew shim as removable: accepted-and-fixed (code comment at the guard).
- **Reconciliation:** the mini-plan had rejected C as the larger change; both reviewers approve the chosen shape.

## Code Review Cascade
- **spec-reviewer (opus):** PASS. Notes: AC-3 byte-identity covered only the retry-due rejection — fixed (parametrized over the `ask_human` terminal); AC-9's ADR is due at F3 — done.
- **code-reviewer (opus):** approve, 7 low. Fixed: integration test of a real two-split run archived by the `archive_split.py` CLI (red on the base validator); stale comments in `single_session_apply` / `single_session_recovery`; the skew shim accepts `**kwargs`. Declined: making `_human_can_override` public (tests monkeypatch the private name; a rename widens the diff); dropping the `DEFAULT_TASK_VERSION` facade re-export (the facade re-exports every core name by convention); an `is_archived_split` helper (optional, the three sites stay pinned by tests).
- **doubt-reviewer (opus):** proceed-after-addressing, 2 medium + 2 low, all fixed: the `ask_human` answer carries `recover_useful` (false for an archived split, docs say not to offer more tries); an uncounted `ask_human` terminal writes the marker onto this run's loop state or a fresh one; the canon checks get `split_id` only for an archived split; the archived bucket requires the exact name in `completed_splits`.

## External Code Review
- **Verdicts:** glm=approve · openai=revise (full merge-base diff, untracked files included)

| Finding | Severity | Disposition |
|---|---|---|
| openai: a `canon_degraded` ask on an archived split kept its kind, so `recover_useful` read true | medium | accepted-and-fixed — every ask on an archived split gains `archived_split: true`; `recover_useful` reads the flag; two tests |
| glm: the run-plugin mirror had no non-dict guard | low | accepted-and-fixed — guard added, non-dict cases in the mirror matrix |
| glm: "No sections found" wording changed for `split_id == current_split` | low | accepted-and-fixed — "current split" wording kept unless archived; pinned |
| glm: unreadable loop state fails at `begin_dispatch`, not at the resolver | low | rejected-with-reason — unchanged pre-existing behaviour; the resolver must stay read-only and never block on it |

