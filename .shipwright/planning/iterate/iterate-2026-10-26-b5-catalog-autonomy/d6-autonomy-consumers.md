# D6 autonomy consumer list (B5)

Source: `git grep -nE "autonomy|autonomous" -- plugins shared` (tracked files, tests and *.jsonl excluded).
276 matching lines in 84 files. Rule: `unattended` behaves at least as `autonomous` at every site keyed on `autonomous`;
a site keyed on human presence (the phase-gate override) deliberately keeps refusing it.

| file | hits | disposition |
|---|---|---|
| `plugins/shipwright-adopt/scripts/lib/config_writer.py` | 1 | UNCHANGED: writes supervised; the schema enum now names it |
| `plugins/shipwright-adopt/skills/adopt/references/step-b5-route-discovery.md` | 1 | REVIEWED: no behavior keyed on the autonomy value |
| `plugins/shipwright-build/agents/section-builder.md` | 4 | CHANGED: unattended behaves as autonomous |
| `plugins/shipwright-build/agents/section_builder_contract.schema.json` | 1 | REVIEWED: no behavior keyed on the autonomy value |
| `plugins/shipwright-build/skills/build/SKILL.md` | 3 | CHANGED: orchestrated mode line |
| `plugins/shipwright-build/skills/build/references/autonomous-loop.md` | 4 | CHANGED: unattended = sequential, fan-out needs allow_parallel_builders |
| `plugins/shipwright-build/skills/build/references/code-review-interview.md` | 1 | REVIEWED: no behavior keyed on the autonomy value |
| `plugins/shipwright-build/skills/build/references/code-review.md` | 3 | CHANGED: autonomous-or-unattended |
| `plugins/shipwright-build/skills/build/references/first-actions.md` | 3 | REVIEWED: no behavior keyed on the autonomy value |
| `plugins/shipwright-build/skills/build/references/migration-safety.md` | 3 | CHANGED: unattended named (3 sites) |
| `plugins/shipwright-build/skills/build/references/requirement-writeback.md` | 1 | REVIEWED: no behavior keyed on the autonomy value |
| `plugins/shipwright-changelog/skills/changelog/SKILL.md` | 2 | CHANGED: Steps 4, 5, 9 (net -1 line; discipline block in references/first-actions.md) |
| `plugins/shipwright-changelog/skills/changelog/references/first-actions.md` | 2 | REVIEWED: no behavior keyed on the autonomy value |
| `plugins/shipwright-deploy/skills/deploy/SKILL.md` | 1 | CHANGED: hard-stop regardless, unattended included |
| `plugins/shipwright-iterate/agents/sub-iterate-runner.md` | 2 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `plugins/shipwright-iterate/agents/sub_iterate_runner_contract.schema.json` | 1 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `plugins/shipwright-iterate/scripts/hooks/iterate_stop_guard.py` | 5 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `plugins/shipwright-iterate/scripts/lib/risk_detectors.py` | 3 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `plugins/shipwright-iterate/scripts/tools/campaign_progress.py` | 4 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `plugins/shipwright-iterate/skills/iterate/SKILL.md` | 4 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `plugins/shipwright-iterate/skills/iterate/references/F12.md` | 2 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `plugins/shipwright-iterate/skills/iterate/references/F5b.md` | 2 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `plugins/shipwright-iterate/skills/iterate/references/autonomous-contract.md` | 3 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `plugins/shipwright-iterate/skills/iterate/references/campaign-dependency-graphs.md` | 1 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md` | 8 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `plugins/shipwright-iterate/skills/iterate/references/campaign-step-3-4-risk-recheck.md` | 3 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `plugins/shipwright-iterate/skills/iterate/references/campaign-step-3-5-plan-review.md` | 4 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `plugins/shipwright-iterate/skills/iterate/references/campaign-worktree.md` | 2 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md` | 2 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `plugins/shipwright-run/scripts/lib/inference.py` | 3 | UNCHANGED: infers guided; unattended is never inferred (package only) |
| `plugins/shipwright-run/scripts/lib/orchestrator.py` | 1 | CHANGED: usage text |
| `plugins/shipwright-run/scripts/lib/orchestrator_pkg/cli.py` | 2 | CHANGED: --autonomy choices += unattended |
| `plugins/shipwright-run/scripts/lib/orchestrator_pkg/config_factory.py` | 2 | PASS-THROUGH: stores the value, no branch on it |
| `plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py` | 17 | ALREADY HANDLES: TERMINAL_BY_AUTONOMY has unattended=failed; override allowlist guided/autonomous only (human-presence site, correctly refuses unattended) |
| `plugins/shipwright-run/scripts/lib/orchestrator_pkg/single_session_apply.py` | 1 | ALREADY HANDLES: docstring of the terminal; code delegates to phase_gate |
| `plugins/shipwright-run/scripts/lib/orchestrator_pkg/step_planning.py` | 1 | PASS-THROUGH: copies config autonomy into the step payload |
| `plugins/shipwright-run/scripts/lib/orchestrator_pkg/validation_record.py` | 1 | PASS-THROUGH: records the autonomy string |
| `plugins/shipwright-run/scripts/lib/single_session/loop_state.py` | 1 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `plugins/shipwright-run/skills/run/SKILL.md` | 6 | CHANGED: levels, Step 3 master-side preflight rule |
| `plugins/shipwright-run/skills/run/references/autonomy-levels.md` | 4 | CHANGED: new Unattended section (the one rule) |
| `plugins/shipwright-run/skills/run/references/brief-intake.md` | 5 | CHANGED: CLI accepts unattended; Step 3 preflight |
| `plugins/shipwright-run/skills/run/references/inference-rules.md` | 1 | CHANGED: level table |
| `plugins/shipwright-run/skills/run/references/single-session-loop.md` | 5 | VERIFIED: already states unattended refuses override and takes the failed terminal |
| `plugins/shipwright-test/agents/test-runner.md` | 2 | CHANGED: unattended behaves as autonomous |
| `plugins/shipwright-test/skills/test/SKILL.md` | 1 | CHANGED: auto-fix line |
| `plugins/shipwright-test/skills/test/references/first-actions.md` | 1 | CHANGED: gate-discipline block (test phase now cataloged) |
| `plugins/shipwright-test/skills/test/references/step-1-unit-tests.md` | 1 | CHANGED: autonomous-or-unattended |
| `plugins/shipwright-test/skills/test/references/step-2-smoke-test.md` | 1 | REVIEWED: no behavior keyed on the autonomy value |
| `plugins/shipwright-test/skills/test/references/step-3-playwright-e2e.md` | 2 | CHANGED: auto-fix mode |
| `shared/config/gate_catalog.json` | 13 | CHANGED: unattended_answer + test/changelog gates (SSoT) |
| `shared/config/gate_catalog.md` | 9 | REVIEWED: no behavior keyed on the autonomy value |
| `shared/constitution.md` | 5 | CHANGED: confirm tables name unattended (line 73 already 'regardless of autonomy level'; override paragraph already refuses unattended) |
| `shared/prompts/single-session-gate-discipline.md` | 4 | CHANGED: Autonomy unattended section |
| `shared/schemas/run_config.v2.schema.json` | 3 | CHANGED: enum += unattended, supervised (adopt writes it) |
| `shared/scripts/checks/check_unit_attempt.py` | 1 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/hooks/capture_session_id.py` | 1 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/hooks/check_destructive_migration.sh` | 1 | VERIFIED: comment only ('regardless of autonomy level'); no autonomy branch |
| `shared/scripts/hooks/write_terminal_marker.py` | 2 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/lib/branch_base.py` | 2 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/lib/brief_dir_intake.py` | 4 | ALREADY HANDLES: brief autonomy overrides derived value |
| `shared/scripts/lib/brief_intake.py` | 1 | UNCHANGED BY DESIGN: _ALWAYS_ASK keeps the wizard question; a package run answers it from brief.json |
| `shared/scripts/lib/brief_package.py` | 5 | ALREADY HANDLES: AUTONOMY_VALUES includes unattended |
| `shared/scripts/lib/campaign_graph.py` | 1 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/lib/campaign_session_lock.py` | 1 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/lib/campaign_wave.py` | 2 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/lib/gate_policy.py` | 8 | CHANGED: validator, resolver autonomy input |
| `shared/scripts/lib/gate_unattended.py` | 3 | REVIEWED: no behavior keyed on the autonomy value |
| `shared/scripts/lib/iterate_stop_guard.py` | 6 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/lib/iterate_stop_guard_transcript.py` | 16 | UNRELATED: iterate's --autonomous flag, not run_config.autonomy |
| `shared/scripts/lib/loop_claim.py` | 2 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/lib/loop_state.py` | 17 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/lib/review_unavailable.py` | 1 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/lib/unit_lease.py` | 5 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/surface_verification.py` | 1 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/tools/ci_supplychain_authorship_guard.py` | 8 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/tools/record_ci_supplychain_ack.py` | 2 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/tools/record_hard_blocker.py` | 2 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/tools/reset_tool_counter.py` | 1 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/tools/resolve_gate_policy.py` | 7 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/tools/review_unavailable_note.py` | 3 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/tools/verifiers/_iterate_run_id.py` | 1 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/scripts/tools/verifiers/integration_coverage.py` | 2 | UNRELATED: iterate / campaign 'autonomous' loop machinery, not run_config.autonomy |
| `shared/templates/agent-docs/session-handoff.md.template` | 1 | PASS-THROUGH: names the field in a template |
| `shared/templates/claude-md-template.md` | 1 | PASS-THROUGH: names the field in a template |

## Raw grep

```
plugins/shipwright-adopt/scripts/lib/config_writer.py:197:        "autonomy": "supervised",
plugins/shipwright-adopt/skills/adopt/references/step-b5-route-discovery.md:53:- `confidence: medium` + non-interactive run (autonomous adopt,
plugins/shipwright-build/agents/section-builder.md:3:description: Autonomous TDD build agent for a single section. Spawned by orchestrator in autonomous mode. Reads spec, writes tests, implements, reviews, commits, and updates dashboard/state.
plugins/shipwright-build/agents/section-builder.md:10:You are an autonomous build agent implementing a single section using TDD. (`autonomy: unattended` runs behave as autonomous here.)
plugins/shipwright-build/agents/section-builder.md:43:7. **Source-of-truth priority** (rendering conflicts ONLY): Spec > Architecture > Chrome > Mockup > shadcn Rules > Screenshot. **STOP instead when mockup and section description contradict each other about what the screen or flow *does*** (a step in one and absent in the other, a different path through the product) — applying the ladder there silently discards a design a human judged against real use. Report it quoting both sides and let a person decide; the expected resolution is that the requirement is corrected to match the mockup. In autonomous mode this is a **section failure with a reason**, never a coin-flip you resolve yourself. Full rule: `{plugin_root}/skills/build/references/requirement-writeback.md`.
plugins/shipwright-build/agents/section-builder.md:65:If `success == false` (missing required vars): note in result JSON but continue — autonomous mode does not block on env vars; but `action: "error"` / `kind` / exit 2-3 is a profile problem: stop and show the message.
plugins/shipwright-build/agents/section_builder_contract.schema.json:5:  "description": "JSON schema for the result returned by section-builder subagent. Used by the autonomous section loop to verify subagent output.",
plugins/shipwright-build/skills/build/SKILL.md:13:> **Autonomous orchestrated mode:** When invoked by `/shipwright-run` in autonomous or unattended mode,
plugins/shipwright-build/skills/build/SKILL.md:32:| Autonomous Section Loop | [autonomous-loop](references/autonomous-loop.md) |
plugins/shipwright-build/skills/build/SKILL.md:287:When invoked with `--autonomous`, build all pending sections sequentially. Full procedure: [autonomous-loop](references/autonomous-loop.md). When NOT autonomous: skip this section, proceed to Step 12.
plugins/shipwright-build/skills/build/references/autonomous-loop.md:3:When invoked with `--autonomous` flag (or when `/shipwright-run` dispatches in `autonomy: autonomous` or `unattended` mode), build all pending sections sequentially without manual gates.
plugins/shipwright-build/skills/build/references/autonomous-loop.md:7:**Flag:** `/shipwright-build --autonomous` or `/shipwright-build --from 02 --autonomous`
plugins/shipwright-build/skills/build/references/autonomous-loop.md:23:uv run "{shared_root}/scripts/lib/autonomous_loop.py" init \
plugins/shipwright-build/skills/build/references/autonomous-loop.md:70:**When NOT using `--autonomous`:** skip this section entirely, proceed to Kern Step 12 (manual next-section prompt).
plugins/shipwright-build/skills/build/references/code-review-interview.md:7:"auto-fixed (autonomous mode)".
plugins/shipwright-build/skills/build/references/code-review.md:168:**Autonomous mode** (`autonomy` is `autonomous` or `unattended` in `shipwright_run_config.json`):
plugins/shipwright-build/skills/build/references/code-review.md:173:3. Log fix in decision log with context "auto-fixed (autonomous mode)"
plugins/shipwright-build/skills/build/references/code-review.md:291:   autonomous/guided handling rule as the internal subagent findings.
plugins/shipwright-build/skills/build/references/first-actions.md:228:`autonomous-loop.md`'s `section-builder` spawn, `execution.resolved` for
plugins/shipwright-build/skills/build/references/first-actions.md:253:  code-review findings auto-fix, as in autonomous mode).
plugins/shipwright-build/skills/build/references/first-actions.md:257:  **hard-stop** — an explicit human decision, always, regardless of autonomy.
plugins/shipwright-build/skills/build/references/migration-safety.md:41:regardless of autonomy level (`unattended` included).
plugins/shipwright-build/skills/build/references/migration-safety.md:76:**Migration apply is a serialized critical section.** In autonomous / unattended mode with parallel section-builders, only one agent at a time may create/apply migrations. See section-builder agent docs for serialization protocol.
plugins/shipwright-build/skills/build/references/migration-safety.md:89:In autonomous / unattended subagent mode: log the manual step as a warning, skip tests matching `blocks_tests_for` keywords, and flag in result JSON.
plugins/shipwright-build/skills/build/references/requirement-writeback.md:47:guided and autonomous paths cannot drift apart.
plugins/shipwright-changelog/skills/changelog/SKILL.md:143:**Autonomous mode** (`autonomy` is `autonomous` or `unattended` in `shipwright_run_config.json`):
plugins/shipwright-changelog/skills/changelog/SKILL.md:251:**Autonomous mode** (`autonomy` is `autonomous` or `unattended` in `shipwright_run_config.json`):
plugins/shipwright-changelog/skills/changelog/references/first-actions.md:6:(`unattended` autonomy behaves at least as `autonomous`). Resolve before you stop:
plugins/shipwright-changelog/skills/changelog/references/first-actions.md:17:Gates: `changelog.version-suggestion` and `changelog.entry-preview` are `auto-default` (accept), matching the autonomous-mode text in Steps 4 and 5.
plugins/shipwright-deploy/skills/deploy/SKILL.md:75:Under single-session pipeline mode (`run_config.mode == "single_session"`), interactive gates follow a per-gate policy — resolve via `${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/tools/resolve_gate_policy.py --phase deploy --list`. PROD / destructive-migration / rollback gates stay **hard-stop** (explicit human confirmation, always, regardless of autonomy, `unattended` included). Full contract: `shared/prompts/single-session-gate-discipline.md`.
plugins/shipwright-iterate/agents/sub-iterate-runner.md:10:You are an autonomous iterate agent executing a single sub-iterate within a campaign.
plugins/shipwright-iterate/agents/sub-iterate-runner.md:117:- **Branch B — `missing_keys`:** autonomous; cannot prompt. Log, proceed, record the opt-out;
plugins/shipwright-iterate/agents/sub_iterate_runner_contract.schema.json:224:          "description": "Machine-readable escalation cause. `complexity_large` is the original Step 2 case. `ci_supplychain_requires_operator` is the Step 3.4 case: the diff touches the CI trust boundary (.github/workflows/**, dependency-updater config, composite actions, shipped CI templates), which check_ci_supplychain_ack gates at EVERY complexity. The runner hands back rather than writing its own acknowledgement — the ack names the recorded posture decision a change agrees with, and a machine authoring its own permission slip defeats the gate (operator decision 2026-08-01). `architecture_review_rejected` is the Step 3.5 case: either external architecture reviewer answered `reject`; the interactive contract is STOP-and-ask, the autonomous runner cannot ask, so it halts the unit and carries both verdicts plus the recommended alternative inline for the orchestrator to surface at campaign end.",
plugins/shipwright-iterate/scripts/hooks/iterate_stop_guard.py:6:"""Iterate Stop hook -- keeps an ``--autonomous`` run going until it is delivered.
plugins/shipwright-iterate/scripts/hooks/iterate_stop_guard.py:59:        autonomous = scan.autonomous
plugins/shipwright-iterate/scripts/hooks/iterate_stop_guard.py:62:            branch=str(pointer.get("branch") or ""), autonomous=autonomous,
plugins/shipwright-iterate/scripts/hooks/iterate_stop_guard.py:64:            scan={"autonomous": scan.autonomous, "tools": scan.tools, "offset": scan.offset,
plugins/shipwright-iterate/scripts/hooks/iterate_stop_guard.py:73:            if blocker and autonomous:
plugins/shipwright-iterate/scripts/lib/risk_detectors.py:205:    r"(^|/)(autonomous_loop|events_log)\.py$",
plugins/shipwright-iterate/scripts/lib/risk_detectors.py:207:    # entirely in `autonomous_loop.py` (state machine, fencing, atomic
plugins/shipwright-iterate/scripts/lib/risk_detectors.py:212:    # cross_component the moment `autonomous_loop.py` itself wasn't also
plugins/shipwright-iterate/scripts/tools/campaign_progress.py:4:Reads/updates status.json and provides units for autonomous_loop.py init.
plugins/shipwright-iterate/scripts/tools/campaign_progress.py:7:    # List units in autonomous_loop.py-compatible format
plugins/shipwright-iterate/scripts/tools/campaign_progress.py:100:    """Output units in the format autonomous_loop.py init --units-from expects."""
plugins/shipwright-iterate/scripts/tools/campaign_progress.py:203:    p_list = sub.add_parser("list-units", help="List units for autonomous_loop.py")
plugins/shipwright-iterate/skills/iterate/SKILL.md:36:**Governing rules:** read and follow `shared/constitution.md` (ALWAYS / ASK FIRST / NEVER). **Under `--autonomous` the run is done ONLY at F11 MERGED with green checks plus the F12 summary — a closing summary, progress report or question before that is a contract violation (a green build or F0 is not a result); create the phase checklist (`TaskCreate`) right after the worktree exists, and the only legitimate early stop is a recorded hard blocker: [autonomous-contract](references/autonomous-contract.md).** **BEFORE any other tools:**
plugins/shipwright-iterate/skills/iterate/SKILL.md:131:| `cross_component` | FRAMEWORK cross-component machinery (diff-driven, `classify_complexity.CROSS_COMPONENT_FILE_PATTERNS`): merge/churn/event-log resolver (`integrate_main`, `ensure_current`, `churn_merge`, `gitattributes_*`, `resolve_churn_conflicts`, `events_log`), Claude-Code hooks + hook fan-out (`hooks.json`, `**/hooks/*.py`), pipeline phase validators (`verify_phase`, `get_phase_context`), campaign drain (`autonomous_loop`, `campaign_*`, `campaign-mode.md`) | medium | **integration coverage** — a real-scenario integration test proving the components compose (reference: `shared/tests/test_parallel_merge_cascade_integration.py`), recorded as a `category:"integration"` behavior in the Test Completeness Ledger. NON-dodgeable: the F11 verifier `check_integration_coverage` RECOMPUTES the flag from the diff, applies at **EVERY complexity**, and STOPs without it; infra failures (unobtainable diff, git fault) fail closed, and only a non-git context skips. **`medium` here is the CLASSIFICATION escalation floor — what the flag forces a *run* to be classified as — not an enforcement floor for the gate.** The two were coupled until iterate-2026-08-01-coverage-gate-recompute-order, which meant the recompute was reached only for runs that had already self-reported into the enforcing band, i.e. never for the missed-detection case it exists to catch. + full test suite |
plugins/shipwright-iterate/skills/iterate/SKILL.md:182:See `references/iteration-reviews.md` for trigger rules. **Dispatch rule, checked before any of the three spawns below:** see `shared/prompts/codex_review_dispatch.md` for the full Codex-driver procedure. Codex CLI driving → `review_via_codex.py`; Claude Code incl. Codextender → spawn as normal (proxy-mapped to `sol`). It never applies to a delegated campaign sub-iterate — see `references/campaign-mode.md` step 3f-bis, which states this rule for the orchestrator's own spawn instead). **A standing grant in `CLAUDE.md` outranks this — if the project states that review subagents are requested by default, spawn them and do NOT ask.** Only when no such grant exists and a session policy gates spawning: ask for the go-ahead as your FIRST action here — before Stage 1. Such a policy (e.g. a standing *"do not call the Agent tool unless the user requested it"*) is **conditional**: one sentence from the operator lifts it for the rest of the session. It is not a capability limit. Ask only when all three hold — the cascade is required for this diff; the `Agent` tool is in **this agent's capabilities** (asking without it wins a "yes" and fails anyway); and permission was not **already given earlier in this session** (it holds for the whole session — do not re-ask). A question asked at finalization buys nothing, because the work is already built. **If the answer is no**, that is blocker #4 — follow the escalation ladder in `references/iteration-reviews.md` (external review mandatory; `code` and `doubt` recorded `not_run --reason-code user-opt-out` with a disposition naming *operator-declined*). **Under `--autonomous`** you cannot block to ask — but that prevents *acquiring* permission, **not using permission already held**; only when it is absent and unobtainable do you record `code = not_run --reason-code unavailable` with a disposition naming the mode, run the external review, and surface the ungated pass in the **closing run summary (F12)** so the operator can lift it next time. **This session spawns the cascade itself** — a standalone iterate has the `Agent` tool, so there is no delegate and nothing to wait for: `spec-reviewer` (Stage 1, **HARD-GATE** — a REJECT blocks Stage 2 until the diff is fixed and re-reviewed) → `code-reviewer` (Stage 2) → `doubt-reviewer` (Stage 3, conditional, advisory-must-address). **Pass `model=<the review tier resolved in §F>` to the Agent tool at each of the three spawns** (omit the parameter when the resolved value is `inherit` — the Agent tool has no `inherit` literal of its own). **State the run_id in plain text in every spawn prompt** (e.g. "This review is part of iterate run `{run_id}`.") — the `SubagentStop` salvage hook (`write-review-payload-on-stop.py`) can only find it in the subagent's own transcript, never from an env var. **The instant each subagent returns, write its reply to its payload file and call `record_review_pass.py record` before any other reasoning or spawning the next reviewer** — this is a mitigation, not a guarantee (it is agent-followed prose, not code-enforced; the salvage hook above is the code-level backstop for exactly the window this instruction cannot close by itself). It runs **before F6 (commit)**, because a review that lands after the commit reviews something already shipped. It reviews the **code diff**; artifacts written afterwards by Steps 11a/11b and finalization ship in the same commit unreviewed, so "before F6" buys *not after*, not *reviews everything that ships*. **Every stage closes its own row**: `spec` from Stage 1, `code` from Stage 2 (`--from code-reviewer`), `doubt` from Stage 3 — every `record_review_pass.py record` call for these three carries `--model-tier "{resolved_review_tier}"` (the same value passed at the spawn above). Row-ordering and evidence rules for these records, and why the runner contract's 'delegated' wording (§5b) is campaign-only and does not apply here: [review-cascade-spawn](references/review-cascade-spawn.md).
plugins/shipwright-iterate/skills/iterate/SKILL.md:208:See `references/campaign-mode.md` for the full protocol: campaign setup, autonomous **interleaved-serial** loop (init/next/record/**merge**/finalize — build one sub-iterate → PR → CI-green → merge → next from fresh `origin/main`; `branch_strategy: serial` is the default), sub-iterate-runner contract, F12 release prompt. **Review steps in autonomous-loop briefing (ADR-029 — campaign mode ONLY):** the sub-iterate-runner contract mandates **Step 3.4 (Diff-Driven Risk Re-Check)**, **Step 3.5 (External Plan Review)** and **Step 3.7 (Code Review Cascade)** between Build and Finalization for medium+ iterates; **Step 3.4 runs ALWAYS and comes first**. In campaign mode the runner carries the `Agent` tool and spawns the internal arms (Step 3.5) and the cascade (Step 3.7) itself at the review tiers its brief carries; only a runner whose spawn fails delegates the code review back to the orchestrator (`3f-bis`). A standalone iterate spawns the cascade itself too (Step 8). Skipping these review steps silently is a contract violation under ADR-029 — Step 3.4 duties (complexity raise, STOP on a CI-trust-boundary diff) and why it comes first: [campaign-review-briefing](references/campaign-review-briefing.md). **Manual sub-iterate stamp (campaign S1):** a hand-run sub-iterate (`/shipwright-iterate --campaign <slug> --sub-iterate-id <id> "<sub-iterate spec path>"`, or any direct invocation on a campaign sub-iterate spec) MUST stamp its `work_completed` event exactly like the runner does: `"campaign": "<slug>"` and `"sub_iterate_id": "<id>"` in the F5b `--event-extras-json` (`references/F5b.md`).
plugins/shipwright-iterate/skills/iterate/references/F12.md:42:is the surface SKILL.md Step 8 promises under `--autonomous`: the operator learns
plugins/shipwright-iterate/skills/iterate/references/F12.md:61:here and in the PR body whenever it is not `none` (an autonomous run adds `--file-triage`, which
plugins/shipwright-iterate/skills/iterate/references/F5b.md:124:when the iterate is a campaign sub-iterate — spawned by the autonomous loop OR
plugins/shipwright-iterate/skills/iterate/references/F5b.md:139:> the old write-once main-tree file; the autonomous-loop 3g main-tree
plugins/shipwright-iterate/skills/iterate/references/autonomous-contract.md:1:# Autonomous contract (`--autonomous`)
plugins/shipwright-iterate/skills/iterate/references/autonomous-contract.md:3:An `--autonomous` iterate is **done only when its PR is MERGED with green required checks (F11 delivery) and F12 has printed its summary.** Nothing before that is a result.
plugins/shipwright-iterate/skills/iterate/references/autonomous-contract.md:35:The `iterate_stop_guard.py` Stop hook blocks every Stop of an `--autonomous` iterate whose run pointer is still live (`deliver_pr.py` retires it at MERGED/CLOSED) and names the next unfinished phase in the block reason. It lets a Stop through only while a launched background task is unfinished (below), after a recorded hard blocker, once its PR is MERGED out of band (below), or when the counters run out (3 consecutive blocks without a tool call in between, 40 per run). Interactive iterates are never blocked.
plugins/shipwright-iterate/skills/iterate/references/campaign-dependency-graphs.md:63:  `autonomous_loop.py::cmd_next` gained ONE `kind == "sub_iterate"`-gated
plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md:3:When invoked with `--campaign <slug>` and `--autonomous`, run the campaign's
plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md:13:**Flags:** `/shipwright-iterate --campaign <slug> [--autonomous] [--sub-iterate-id <id>]` (the last for a single hand-run sub-iterate — stamps the event per SKILL.md §5b)
plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md:15:> **Review steps in autonomous-loop briefing (ADR-029).** When briefing
plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md:16:> a sub-iterate-runner under `--autonomous`, include a reminder that the
plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md:189:   uv run "{shared_root}/scripts/lib/autonomous_loop.py" init \
plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md:513:           uv run "{shared_root}/scripts/lib/autonomous_loop.py" record \
plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md:537:         uv run "{shared_root}/scripts/lib/autonomous_loop.py" record \
plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md:1689:**When NOT using `--autonomous`:** skip this section entirely, proceed
plugins/shipwright-iterate/skills/iterate/references/campaign-step-3-4-risk-recheck.md:39:already a valid status (`autonomous_loop.VALID_STATUSES`), the whole result is
plugins/shipwright-iterate/skills/iterate/references/campaign-step-3-4-risk-recheck.md:62:an active autonomous-loop unit's process carries (this campaign loop's own
plugins/shipwright-iterate/skills/iterate/references/campaign-step-3-4-risk-recheck.md:63:sub-iterate runner, or `shipwright-build`'s unrelated `--autonomous` loop
plugins/shipwright-iterate/skills/iterate/references/campaign-step-3-5-plan-review.md:8:wins; this one owns only what differs in an **autonomous** runner — it cannot ask
plugins/shipwright-iterate/skills/iterate/references/campaign-step-3-5-plan-review.md:106:the shape; `autonomous_loop.py record` does not validate reason-code fields, so the
plugins/shipwright-iterate/skills/iterate/references/campaign-step-3-5-plan-review.md:111:Operator decision (finalization-claims-hardening §5.2): an autonomous run MAY continue
plugins/shipwright-iterate/skills/iterate/references/campaign-step-3-5-plan-review.md:174:`autonomous_loop.py record` exits `3` for any `escalated` result, so the WHOLE wave
plugins/shipwright-iterate/skills/iterate/references/campaign-worktree.md:49:`autonomous_loop.py`'s `file_lock` only serializes `loop_state.json` writes and
plugins/shipwright-iterate/skills/iterate/references/campaign-worktree.md:271:SAME `loop.lock` / `file_lock` `autonomous_loop.py` already serializes every
plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md:247:3. the run is a **campaign sub-iterate built by the runner under `--autonomous`**,
plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md:249:   described as "autonomous" is **not** this case: the person who wrote that
plugins/shipwright-run/scripts/lib/inference.py:4:Infers scope, profile, and autonomy from user description and project state.
plugins/shipwright-run/scripts/lib/inference.py:15:        "autonomy": "guided",
plugins/shipwright-run/scripts/lib/inference.py:120:        "autonomy": "guided",
plugins/shipwright-run/scripts/lib/orchestrator.py:12:    uv run orchestrator.py write-config --scope <scope> --profile <profile> --autonomy <guided|autonomous|unattended>
plugins/shipwright-run/scripts/lib/orchestrator_pkg/cli.py:59:    p.add_argument("--autonomy", default="guided", choices=["guided", "autonomous", "unattended"])
plugins/shipwright-run/scripts/lib/orchestrator_pkg/cli.py:239:            args.scope, args.profile, args.autonomy,
plugins/shipwright-run/scripts/lib/orchestrator_pkg/config_factory.py:143:    autonomy: str,
plugins/shipwright-run/scripts/lib/orchestrator_pkg/config_factory.py:284:        "autonomy": autonomy,
plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py:55:# What a gate rejection does once MAX_GATE_RETRIES is exhausted, per run autonomy.
plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py:56:# ``unattended`` (campaign U) behaves at least as autonomous. An unknown value takes the
plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py:58:TERMINAL_BY_AUTONOMY = {"guided": "ask_human", "autonomous": "failed", "unattended": "failed"}
plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py:60:# The ONLY autonomy levels with a human who can decide an override (ASK FIRST in the
plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py:64:_HUMAN_AUTONOMY = frozenset({"guided", "autonomous"})
plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py:74:def autonomy_of(config: dict[str, Any]) -> str:
plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py:75:    """The run's autonomy, normalised (stripped, lower-case); absent reads as guided."""
plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py:76:    raw = config.get("autonomy")
plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py:81:    raw = config.get("autonomy")
plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py:87:            "error": f"autonomy {config.get('autonomy')!r} has no human to decide an "
plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py:88:                     "override (constitution ASK FIRST; allowed: guided, autonomous)."}
plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py:147:    autonomy is not on the ``_HUMAN_AUTONOMY`` allowlist. The lifecycle hook re-checks the
plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py:148:    autonomy on the LOCKED config, so a config edited in between cannot slip through.
plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py:171:    The autonomy is read from the config the lifecycle passes in (the one read under the
plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py:183:                 "autonomy": config.get("autonomy"), "entrypoint": "single-session-apply"},
plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py:241:    retry is due, else ``ask_human`` / ``failed`` per autonomy: once the dispatch
plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py:263:        "terminal": TERMINAL_BY_AUTONOMY.get(autonomy_of(config), "ask_human") if final else None,
plugins/shipwright-run/scripts/lib/orchestrator_pkg/single_session_apply.py:120:    (guided — still non-mutating) or ``failed`` (autonomous — ``mark_phase_failed``
plugins/shipwright-run/scripts/lib/orchestrator_pkg/step_planning.py:87:                "autonomy": config.get("autonomy"),
plugins/shipwright-run/scripts/lib/orchestrator_pkg/validation_record.py:226:    ``autonomy``, ``entrypoint``); its non-None values are merged into the record so
plugins/shipwright-run/scripts/lib/single_session/loop_state.py:14:autonomous loop's ``.shipwright/loop_state.json``.
plugins/shipwright-run/skills/run/SKILL.md:102:| **Autonomy** | Default: `guided` (phases stop at gates for you); user can choose `autonomous` or `unattended` (approved Brief package only) |
plugins/shipwright-run/skills/run/SKILL.md:116:Autonomy:   {guided | autonomous | unattended}
plugins/shipwright-run/skills/run/SKILL.md:132:    - "Change autonomy"
plugins/shipwright-run/skills/run/SKILL.md:150:  --autonomy "{autonomy}" \
plugins/shipwright-run/skills/run/SKILL.md:223:person (guided) or stop failed (autonomous). Completing over the checks
plugins/shipwright-run/skills/run/SKILL.md:381:- [autonomy-levels.md](references/autonomy-levels.md) — Guided vs autonomous vs unattended behavior (within phases)
plugins/shipwright-run/skills/run/references/autonomy-levels.md:14:Interactive process through Spec and Design with autonomous Build and Test
plugins/shipwright-run/skills/run/references/autonomy-levels.md:33:Autonomous, with no human reachable. **Rule:** every site keyed on "autonomous" treats
plugins/shipwright-run/skills/run/references/autonomy-levels.md:50:  "autonomy": "guided"
plugins/shipwright-run/skills/run/references/autonomy-levels.md:56:/shipwright-run --autonomous "Build a todo app"
plugins/shipwright-run/skills/run/references/brief-intake.md:22:The result has the shape below plus `source: "package"`, `brief_dir`, `autonomy`, `ux_shape`,
plugins/shipwright-run/skills/run/references/brief-intake.md:25:- **Brief fields override derived values:** `profile`, `deploy_target` and `autonomy` come from
plugins/shipwright-run/skills/run/references/brief-intake.md:61:- The CLI `--autonomy` accepts `guided|autonomous|unattended`. A package's `unattended` is written as
plugins/shipwright-run/skills/run/references/brief-intake.md:107:  "remaining_questions": ["autonomy"],
plugins/shipwright-run/skills/run/references/brief-intake.md:138:   brief. Ask only `remaining_questions` (typically just `autonomy`) plus each
plugins/shipwright-run/skills/run/references/inference-rules.md:36:| `autonomous` | Autonomous | Proceed without asking. Exceptions: PROD deploy, destructive DB operations |
plugins/shipwright-run/skills/run/references/single-session-loop.md:115:   - autonomous runs take the failed terminal themselves: apply returns the normal
plugins/shipwright-run/skills/run/references/single-session-loop.md:135:   the run's autonomy are written to `validation_overrides[]` in the same locked write as
plugins/shipwright-run/skills/run/references/single-session-loop.md:136:   the completion. A blank reason, an `ok:false` result and any autonomy other than
plugins/shipwright-run/skills/run/references/single-session-loop.md:137:   `guided` / `autonomous` (so `unattended`, a typo, or none at all) are refused. That
plugins/shipwright-run/skills/run/references/single-session-loop.md:173:- **Strict-stop:** any `ok:false` phase result (and an autonomous gate terminal) halts
plugins/shipwright-test/agents/test-runner.md:3:description: Autonomous test execution agent. Runs unit tests, smoke tests, Playwright E2E with auto-fix. Spawned by orchestrator in autonomous mode.
plugins/shipwright-test/agents/test-runner.md:10:You are an autonomous test execution agent (`autonomy: unattended` behaves as autonomous). You run all test layers and auto-fix failures.
plugins/shipwright-test/skills/test/SKILL.md:157:project file. On failure: diagnose, autonomous fix, retry, then ASK after 2.
plugins/shipwright-test/skills/test/references/first-actions.md:115:(`unattended` autonomy behaves at least as `autonomous`). Resolve before you stop:
plugins/shipwright-test/skills/test/references/step-1-unit-tests.md:16:**Autonomous mode** (`autonomy` is `autonomous` or `unattended` in `shipwright_run_config.json`):
plugins/shipwright-test/skills/test/references/step-2-smoke-test.md:31:2. **Attempt autonomous fix** based on diagnosis. Examples:
plugins/shipwright-test/skills/test/references/step-3-playwright-e2e.md:31:5. **Auto-fix mode** (autonomous / unattended mode or `--fix` flag):
plugins/shipwright-test/skills/test/references/step-3-playwright-e2e.md:61:2. **Attempt autonomous fix** based on diagnosis. Examples:
shared/config/gate_catalog.json:6:    "orchestrator-approve": "Under single_session the subagent STOPS and returns a gate-pending result to the orchestrator to surface to a human; it never auto-answers. Under autonomy 'unattended' the master/CLI auto-approves ONLY a gate with constitution=false that carries a reviewed `unattended_answer` (see `unattended_policy`); every other orchestrator-approve gate escalates. A future autonomous orchestrator MAY surface-and-wait or auto-approve ONLY gates with constitution=false; a constitution=true orchestrator-approve gate (e.g. skip-test-layer, >3 failed fixes, a missing secret) always reaches a human.",
shared/config/gate_catalog.json:7:    "hard-stop": "Under single_session the subagent ALWAYS stops for an explicit human decision; no autonomy setting bypasses it. Constitution-locked class (PROD deploy, destructive SQL, migration-apply failure, rollback)."
shared/config/gate_catalog.json:9:  "constitution_lock": "INVARIANT for SS3+: a gate with constitution=true is NEVER auto-approvable by any autonomy level, regardless of whether its policy is orchestrator-approve or hard-stop. constitution=true is the real lock signal; policy only distinguishes 'surface to the orchestrator' (orchestrator-approve) from 'a human must decide here, full stop' (hard-stop).",
shared/config/gate_catalog.json:10:  "unattended_policy": "autonomy 'unattended' is opt-in per gate. A gate may carry `unattended_answer` (a reviewed, non-empty string) only if it is orchestrator-approve, constitution=false and not denylisted (gate_unattended.UNATTENDED_DENYLIST, pinned by a test); validate_catalog rejects it anywhere else. The resolver only REPORTS the answer (should_stop stays true): the master/CLI applies it after its own hash and FR-coverage checks. Initial allowlist: design.preview-approval, design.review-loop-finalize, design.upload-screen-mapping.",
shared/config/gate_catalog.json:298:      "summary": "A generated migration contains DROP/TRUNCATE/DELETE-without-WHERE. Constitution ASK-FIRST 'regardless of autonomy level' — irreversible data loss."
shared/config/gate_catalog.json:322:      "default_answer": "Log the manual step as a warning, skip tests in blocks_tests_for, and flag it in the result JSON (the existing autonomous-mode degrade).",
shared/config/gate_catalog.json:325:      "summary": "A post-apply manual step matches the applied migration. Build already degrades this in autonomous mode."
shared/config/gate_catalog.json:358:      "default_answer": "Auto-accept and fix every finding, logging each as 'auto-fixed (autonomous mode)' — mirrors build's existing autonomous behaviour.",
shared/config/gate_catalog.json:361:      "summary": "Step 6b guided-mode per-finding triage. Already fully suppressed (auto-accept) in build's autonomous mode."
shared/config/gate_catalog.json:406:      "summary": "Step 4: confirm the suggested release version. Already auto-accepted in changelog's autonomous mode."
shared/config/gate_catalog.json:415:      "summary": "Step 5: preview and confirm the generated entry. Already skipped in changelog's autonomous mode."
shared/config/gate_catalog.json:478:      "summary": "A destructive migration was flagged (any target, DEV or PROD). Constitution ASK-FIRST 'destructive SQL — always confirm, even in autonomous mode'."
shared/config/gate_catalog.json:505:      "summary": "The canonical PROD deploy confirmation (after the backup clone). Constitution ASK-FIRST 'PROD deployments — always confirm + backup, regardless of autonomy level'. The strongest gate."
shared/config/gate_catalog.md:13:- **`orchestrator-approve`** - Under single_session the subagent STOPS and returns a gate-pending result to the orchestrator to surface to a human; it never auto-answers. Under autonomy 'unattended' the master/CLI auto-approves ONLY a gate with constitution=false that carries a reviewed `unattended_answer` (see `unattended_policy`); every other orchestrator-approve gate escalates. A future autonomous orchestrator MAY surface-and-wait or auto-approve ONLY gates with constitution=false; a constitution=true orchestrator-approve gate (e.g. skip-test-layer, >3 failed fixes, a missing secret) always reaches a human.
shared/config/gate_catalog.md:14:- **`hard-stop`** - Under single_session the subagent ALWAYS stops for an explicit human decision; no autonomy setting bypasses it. Constitution-locked class (PROD deploy, destructive SQL, migration-apply failure, rollback).
shared/config/gate_catalog.md:67:| `build.destructive-sql-confirm` | hard-stop | conditional | yes (locked) | A generated migration contains DROP/TRUNCATE/DELETE-without-WHERE. Constitution ASK-FIRST 'regardless of autonomy level' - irreversible data loss. |
shared/config/gate_catalog.md:70:| `build.migration-post-apply-manual-step` | auto-default | conditional | no | A post-apply manual step matches the applied migration. Build already degrades this in autonomous mode. **Default:** Log the manual step as a warning, skip tests in blocks_tests_for, and flag it in the result JSON (the existing autonomous-mode degrade). |
shared/config/gate_catalog.md:74:| `build.code-review-finding-triage` | auto-default | conditional | no | Step 6b guided-mode per-finding triage. Already fully suppressed (auto-accept) in build's autonomous mode. **Default:** Auto-accept and fix every finding, logging each as 'auto-fixed (autonomous mode)' - mirrors build's existing autonomous behaviour. |
shared/config/gate_catalog.md:89:| `changelog.version-suggestion` | auto-default | always | no | Step 4: confirm the suggested release version. Already auto-accepted in changelog's autonomous mode. **Default:** Accept the suggested version (derived from commit types: breaking = major, feat = minor, else patch). |
shared/config/gate_catalog.md:90:| `changelog.entry-preview` | auto-default | always | no | Step 5: preview and confirm the generated entry. Already skipped in changelog's autonomous mode. **Default:** Accept the generated changelog entry and proceed (git history and the unreleased drops remain the audit trail). |
shared/config/gate_catalog.md:102:| `deploy.destructive-migration-confirm` | hard-stop | conditional | yes (locked) | A destructive migration was flagged (any target, DEV or PROD). Constitution ASK-FIRST 'destructive SQL - always confirm, even in autonomous mode'. |
shared/config/gate_catalog.md:105:| `deploy.prod-deploy-confirm` | hard-stop | conditional | yes (locked) | The canonical PROD deploy confirmation (after the backup clone). Constitution ASK-FIRST 'PROD deployments - always confirm + backup, regardless of autonomy level'. The strongest gate. |
shared/constitution.md:62:- Diagnose test failures before skipping — attempt autonomous fix (e.g., restart services, seed data, fix config), escalate to user if fix fails after 2 attempts
shared/constitution.md:73:- PROD deployments (always confirm + backup, regardless of autonomy level)
shared/constitution.md:81:  `autonomous` run can override (`unattended`, or no autonomy set, cannot), and a
shared/constitution.md:115:| PROD deploy | Always confirm, even in autonomous or unattended mode |
shared/constitution.md:116:| Destructive SQL | Always confirm, even in autonomous or unattended mode |
shared/prompts/single-session-gate-discipline.md:33:| `hard-stop` | **Still STOP.** An explicit human decision is required regardless of autonomy: PROD deploy, destructive SQL, migration-apply failure, rollback (`shared/constitution.md` ASK FIRST / NEVER). |
shared/prompts/single-session-gate-discipline.md:37:Under `autonomy: unattended` the resolver adds `unattended_answer` to a gate's
shared/prompts/single-session-gate-discipline.md:42:behaves at least as `autonomous` everywhere else.
shared/prompts/single-session-gate-discipline.md:59:  `constitution: true` is NEVER auto-approvable by any autonomy level — even an
shared/schemas/run_config.v2.schema.json:11:    "autonomy",
shared/schemas/run_config.v2.schema.json:39:    "autonomy": { "enum": ["guided", "autonomous", "unattended", "supervised"] },
shared/schemas/run_config.v2.schema.json:133:          "autonomy": { "type": "string", "description": "Driven path only: the run's autonomy level when the override was applied, so an override in an autonomous run can be told apart afterwards." },
shared/scripts/checks/check_unit_attempt.py:36:  `autonomous_loop.cmd_record`'s own exit code for the same condition)
shared/scripts/hooks/capture_session_id.py:13:  autonomous-loop env vars, only emitted when set by the parent runner.
shared/scripts/hooks/check_destructive_migration.sh:7:# These ALWAYS require explicit user confirmation, regardless of autonomy level.
shared/scripts/hooks/write_terminal_marker.py:6:"""Stop hook: write terminal marker for autonomous loop synchronization.
shared/scripts/hooks/write_terminal_marker.py:38:    # build's --autonomous loop polls the DONE file it writes) — a packaging
shared/scripts/lib/branch_base.py:3:Extracted from ``autonomous_loop.py``
shared/scripts/lib/branch_base.py:12:change) for every existing caller (``autonomous_loop.cmd_next``,
shared/scripts/lib/brief_dir_intake.py:15:* brief fields override derived values (``profile``, ``deploy_target``, ``autonomy``).
shared/scripts/lib/brief_dir_intake.py:136:    for key in ("profile", "autonomy", "deploy_target"):
shared/scripts/lib/brief_dir_intake.py:179:        deploy_target=brief["deploy_target"], answered=["description", "profile", "deploy_target", "autonomy"],
shared/scripts/lib/brief_dir_intake.py:181:        autonomy=brief["autonomy"], ux_shape=brief["ux_shape"], ui_host=brief["ui_host"],
shared/scripts/lib/brief_intake.py:29:_ALWAYS_ASK = ["autonomy"]  # non-brief question the wizard never sets -> always still asked
shared/scripts/lib/brief_package.py:21:  field (``autonomy``, ``allow_parallel_builders``, ``deploy_target``...) is protected.
shared/scripts/lib/brief_package.py:65:    "version", "profile", "deploy_target", "autonomy", "ux_shape", "source_class",
shared/scripts/lib/brief_package.py:72:AUTONOMY_VALUES = ("guided", "autonomous", "unattended")
shared/scripts/lib/brief_package.py:102:    if "autonomy" in brief and brief["autonomy"] not in AUTONOMY_VALUES:
shared/scripts/lib/brief_package.py:103:        issues.append(_issue("bad_value", "brief.json", f"autonomy must be one of {AUTONOMY_VALUES}"))
shared/scripts/lib/campaign_graph.py:18:``autonomous_loop.py`` imports ``branch_base``/``file_lock`` today. Two
shared/scripts/lib/campaign_session_lock.py:8:``autonomous_loop.py``'s ``file_lock`` only serializes ``loop_state.json``
shared/scripts/lib/campaign_wave.py:70:    collide with it. A shipwright-build ``--autonomous`` section id (that
shared/scripts/lib/campaign_wave.py:126:    shipwright-build `--autonomous` section) passes through unchanged; the
shared/scripts/lib/gate_policy.py:12:                                (constitution-locked; no autonomy bypasses it).
shared/scripts/lib/gate_policy.py:170:def read_run_config_autonomy(project_root: Any) -> Optional[str]:
shared/scripts/lib/gate_policy.py:171:    """The run's ``autonomy`` from run_config, or ``None`` (same total-read guard as
shared/scripts/lib/gate_policy.py:179:    value = parsed.get("autonomy") if isinstance(parsed, dict) else None
shared/scripts/lib/gate_policy.py:197:    autonomy: Optional[str] = None,
shared/scripts/lib/gate_policy.py:212:    ``autonomy="unattended"`` adds ``unattended_answer`` (the reviewed answer of an
shared/scripts/lib/gate_policy.py:225:        "autonomy": autonomy,
shared/scripts/lib/gate_policy.py:243:        "unattended_answer": unattended_answer_for(gate, autonomy),
shared/scripts/lib/gate_unattended.py:3:``autonomy: unattended`` is opt-in per gate. An ``orchestrator-approve`` gate that is
shared/scripts/lib/gate_unattended.py:58:def unattended_answer_for(gate: dict[str, Any], autonomy: Optional[str]) -> Optional[str]:
shared/scripts/lib/gate_unattended.py:62:    if autonomy != UNATTENDED or validate_unattended(gate.get("id", "?"), gate):
shared/scripts/lib/iterate_stop_guard.py:1:"""Stop-guard for an ``--autonomous`` iterate run.
shared/scripts/lib/iterate_stop_guard.py:3:An autonomous iterate is only done when its PR is MERGED and the checks are
shared/scripts/lib/iterate_stop_guard.py:13:* the latest iterate invocation in the session is not ``--autonomous`` (or is a
shared/scripts/lib/iterate_stop_guard.py:103:    """Persist the one legitimate reason an autonomous run may stop early."""
shared/scripts/lib/iterate_stop_guard.py:227:           autonomous: bool, tool_count: int, scan: dict | None = None,
shared/scripts/lib/iterate_stop_guard.py:236:    if not autonomous:
shared/scripts/lib/iterate_stop_guard_transcript.py:3:is the latest and is it autonomous, how many tool calls happened, and which run
shared/scripts/lib/iterate_stop_guard_transcript.py:32:    autonomous: bool
shared/scripts/lib/iterate_stop_guard_transcript.py:40:    """``(autonomous, campaign)`` from an iterate invocation's arguments.
shared/scripts/lib/iterate_stop_guard_transcript.py:43:    ``--autonomous`` count; a flag name inside the free-text description does not.
shared/scripts/lib/iterate_stop_guard_transcript.py:55:    if tokens and tokens[-1] == "--autonomous":
shared/scripts/lib/iterate_stop_guard_transcript.py:56:        flags.add("autonomous")
shared/scripts/lib/iterate_stop_guard_transcript.py:57:    return "autonomous" in flags, "campaign" in flags
shared/scripts/lib/iterate_stop_guard_transcript.py:114:    """``True`` = an autonomous standalone iterate was started, ``False`` = an
shared/scripts/lib/iterate_stop_guard_transcript.py:131:    autonomous, campaign = parse_flags(args)
shared/scripts/lib/iterate_stop_guard_transcript.py:132:    return autonomous and not campaign
shared/scripts/lib/iterate_stop_guard_transcript.py:136:    """Latest-invocation autonomy, tool_use count and the end offset.
shared/scripts/lib/iterate_stop_guard_transcript.py:139:    autonomy, so a 100 MB transcript is not re-read on every Stop. A different
shared/scripts/lib/iterate_stop_guard_transcript.py:144:    autonomous, tools, start = bool(state.get("autonomous")), int(state.get("tools", 0)), int(state.get("offset", 0))
shared/scripts/lib/iterate_stop_guard_transcript.py:150:            autonomous, tools, start, reset = False, 0, 0, bool(state)
shared/scripts/lib/iterate_stop_guard_transcript.py:172:                        autonomous = found
shared/scripts/lib/iterate_stop_guard_transcript.py:175:    return Scan(autonomous, tools, consumed, reset, background)
shared/scripts/lib/loop_claim.py:5:sibling of ``autonomous_loop.py``'s single-unit ``cmd_next``/``cmd_record``;
shared/scripts/lib/loop_claim.py:257:            # confirmed TERMINAL (autonomous_loop.py). A campaign already
shared/scripts/lib/loop_state.py:6:``_load_units_from`` moves here from ``autonomous_loop.py`` — R1's share of
shared/scripts/lib/loop_state.py:10:``autonomous_loop.py::cmd_next``'s existing single-unit contract for it is
shared/scripts/lib/loop_state.py:25:``branch_base`` the SAME bare-sibling way ``autonomous_loop.py`` does —
shared/scripts/lib/loop_state.py:30:``autonomous_loop.py`` adds only the parent ``shared/scripts``.
shared/scripts/lib/loop_state.py:45:# sys.path. `autonomous_loop.py` happens to add it before importing this
shared/scripts/lib/loop_state.py:119:    `loop_state.json` status as `"complete"` verbatim (`autonomous_loop.py`'s
shared/scripts/lib/loop_state.py:279:    at `autonomous_loop.py::cmd_init` time, a different command entirely.
shared/scripts/lib/loop_state.py:312:# ``autonomous_loop.py`` has exactly one call site instead of two.
shared/scripts/lib/loop_state.py:385:    writer (``autonomous_loop.py``, ``loop_claim.py``) uses, so a row's
shared/scripts/lib/loop_state.py:447:    callers (`autonomous_loop.cmd_record`'s fallback-path and result-path
shared/scripts/lib/loop_state.py:579:    ``autonomous_loop._reconcile_in_progress`` with exactly one change: the
shared/scripts/lib/loop_state.py:669:        # `.shipwright/planning/adr/iterate-2026-09-22-r2-worktree-capability-autonomous-loop-bloat.md`:
shared/scripts/lib/loop_state.py:776:# `autonomous_loop.py` dispatcher glue (R4). Kept HERE, not there: that
shared/scripts/lib/loop_state.py:779:# already-exception-filed module instead, leaving `autonomous_loop.py`'s own
shared/scripts/lib/loop_state.py:797:    # `cmd_next` (autonomous_loop.py) is still the live dispatch path for
shared/scripts/lib/loop_state.py:851:    (`autonomous_loop.cmd_finalize`) MUST only reach this function once the
shared/scripts/lib/loop_state.py:919:    `autonomous_loop.cmd_next`/`cmd_record` path — a fencing check that
shared/scripts/lib/review_unavailable.py:88:#: (blocker #2, an autonomous run without spawn permission) is unchanged.
shared/scripts/lib/unit_lease.py:15:guarded by the SAME ``loop.lock`` / ``file_lock`` ``autonomous_loop.py``
shared/scripts/lib/unit_lease.py:60:`autonomous_loop.py`'s (`_reconcile_in_progress`, `cmd_next`), not this
shared/scripts/lib/unit_lease.py:73:for the new fencing-based claims, `autonomous_loop.cmd_next`'s legacy path
shared/scripts/lib/unit_lease.py:121:    """Exact match first (``autonomous_loop.cmd_record``'s own convention),
shared/scripts/lib/unit_lease.py:260:            # Stage-2 code review (high): `attempt` is `autonomous_loop`'s own
shared/scripts/surface_verification.py:229:    The path is shared with the autonomous-loop runner output dir, so
shared/scripts/tools/ci_supplychain_authorship_guard.py:12:#: Injected around an active autonomous-loop unit process — not only a
shared/scripts/tools/ci_supplychain_authorship_guard.py:13:#: campaign sub-iterate runner (autonomous_loop's spawn of
shared/scripts/tools/ci_supplychain_authorship_guard.py:15:#: `--autonomous` loop sets this SAME var around its own `section-builder`
shared/scripts/tools/ci_supplychain_authorship_guard.py:16:#: spawn (`plugins/shipwright-build/skills/build/references/autonomous-loop.md`,
shared/scripts/tools/ci_supplychain_authorship_guard.py:17:#: Step 3b) — it is one shared identifier for "an autonomous-loop-spawned
shared/scripts/tools/ci_supplychain_authorship_guard.py:31:    """Refuse outright while running inside an active autonomous-loop unit.
shared/scripts/tools/ci_supplychain_authorship_guard.py:43:            "is running as an active autonomous-loop unit (a campaign "
shared/scripts/tools/ci_supplychain_authorship_guard.py:44:            "sub-iterate runner, or a shipwright-build --autonomous "
shared/scripts/tools/record_ci_supplychain_ack.py:26:environment: that variable is injected around any active autonomous-loop unit
shared/scripts/tools/record_ci_supplychain_ack.py:27:(this campaign's own runner, or an unrelated `shipwright-build --autonomous`
shared/scripts/tools/record_hard_blocker.py:6:"""Record the one legitimate reason an --autonomous iterate may stop early.
shared/scripts/tools/record_hard_blocker.py:9:autonomous run's PR is not MERGED. A recorded hard blocker lifts the guard for
shared/scripts/tools/reset_tool_counter.py:4:Used by the orchestrator between sections in autonomous mode
shared/scripts/tools/resolve_gate_policy.py:39:    read_run_config_autonomy,
shared/scripts/tools/resolve_gate_policy.py:59:    p.add_argument("--autonomy", help="run autonomy (default: run_config.autonomy); "
shared/scripts/tools/resolve_gate_policy.py:70:def _resolved_rows(catalog: dict, mode: str, phase: str | None, autonomy: str | None) -> list[dict]:
shared/scripts/tools/resolve_gate_policy.py:75:        r = resolve_gate_policy(gid, mode=mode, catalog=catalog, autonomy=autonomy)
shared/scripts/tools/resolve_gate_policy.py:125:    autonomy = args.autonomy or read_run_config_autonomy(args.project_root)
shared/scripts/tools/resolve_gate_policy.py:129:            result = resolve_gate_policy(args.gate, mode=mode, catalog=catalog, autonomy=autonomy)
shared/scripts/tools/resolve_gate_policy.py:152:    print(json.dumps({"mode": mode, "gates": _resolved_rows(catalog, mode, args.phase, autonomy)}, indent=2))
shared/scripts/tools/review_unavailable_note.py:10:``--file-triage`` (autonomous runs) also files ONE triage card per run asking
shared/scripts/tools/review_unavailable_note.py:93:                "unavailable (the reviewer could not run) and continued autonomously. "
shared/scripts/tools/review_unavailable_note.py:114:                        help="also file one re-run triage card for this run (autonomous runs)")
shared/scripts/tools/verifiers/_iterate_run_id.py:33:and a campaign / autonomous-loop run falls through to
shared/scripts/tools/verifiers/integration_coverage.py:41:    r"(^|/)(autonomous_loop|events_log)\.py$",
shared/scripts/tools/verifiers/integration_coverage.py:43:    # `autonomous_loop.py` into these sibling modules (bloat-budget driven)
shared/templates/agent-docs/session-handoff.md.template:32:- `shipwright_run_config.json` — scope, profile, autonomy
shared/templates/claude-md-template.md:73:- @shipwright_run_config.json — pipeline state (scope, profile, autonomy, current/completed steps)
```
