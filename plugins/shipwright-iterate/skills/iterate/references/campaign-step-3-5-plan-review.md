## Step 3.5 — External Plan Review + Architecture Review (runner contract)

The full body of `agents/sub-iterate-runner.md` Step 3.5, extracted so the runner
stops carrying its own inlined copy of `references/iteration-planning.md` Step 4
(the duplication is why the architecture pass shipped un-wired in campaigns while
the skill, the guide and the spec all claimed "every medium+ Branch A"). Where
this file and `iteration-planning.md` disagree on the *review itself*, that file
wins; this one owns only what differs in an **autonomous** runner — it cannot ask
an operator, it has no `Agent` tool, and it resolves its own `--driver`.

**Trigger** — from Step 3.4's `plan_review_required`: effective complexity
`medium`+, OR any canonical risk flag, OR diff > 100 lines. **Skip** only when
none hold. Then `uv run "{shared_root}/scripts/checks/check-external-review-keys.py"`
and branch on its JSON.

### Branch A — `available`

`--driver` is self-resolving (no caller substitutes a `{driver}` placeholder): the
runner is only ever spawned as a Claude Code subagent, so the *harness* is
`claude`; `codex` when `CODEXTENDER_ACTIVE` is set (the subagent inherits the
spawning session's environment). This is the external roster only (a
Codex-backed author needs a non-OpenAI second reviewer); reviewer *dispatch*
is unaffected — Codextender spawns Agent-tool subagents like any Claude Code
session. Real Codex-driven campaigns: trg-a27ab4d9.

**Call 1 — the plan review.**

```bash
mkdir -p "{project_root}/.shipwright/planning/iterate/{run_id}"
uv run --project "{plan_plugin_root}" "{shared_root}/scripts/tools/external_review.py" --mode iterate \
  --plan-file "{mini_plan_path}" --spec-file "{sub_iterate_spec}" \
  --plugin-root "{plugin_root}" --driver "$([ -n "${CODEXTENDER_ACTIVE:-}" ] && echo codex || echo claude)" > "{project_root}/.shipwright/planning/iterate/{run_id}/external-plan-review-raw.json" 2> "{project_root}/.shipwright/planning/iterate/{run_id}/external-plan-review-raw.stderr.txt"
```

Read it back (canonical basename, trg-3b206c08) and parse `reviews.glm.feedback` +
`reviews.openai.feedback` (`reviews.opus.feedback` under `--driver codex`; required,
never hardcoded). Merge high/medium findings into the iterate ADR's
`External-Plan-Review-Findings` table, each `accepted-and-fixed` /
`rejected-with-reason`, before Finalization. A non-zero exit, a reply that is not
the expected JSON, or `degraded: true` means the review did NOT run → *Unavailable* below.

**Call 2 — the architecture review** (same step, same two models, no extra row and
no marker of its own). It asks the one question the plan review cannot: *should this
be built at all, and what is the smallest thing that would do?* Author
`.shipwright/planning/iterate/{run_id}/architecture_brief.md` from
`shared/templates/architecture_brief.md` — options **without** the reasons any were
rejected, never a copy of the mini-plan; three lines when nothing permanent is added.
It runs on **every** Branch A of a unit that got here (no author-set trigger).

```bash
uv run --project "{plan_plugin_root}" "{shared_root}/scripts/tools/external_review.py" --mode architecture \
  --spec-file "{sub_iterate_spec}" \
  --brief-file "{project_root}/.shipwright/planning/iterate/{run_id}/architecture_brief.md" \
  --plugin-root "{plan_plugin_root}" --project-root "{project_root}" --run-id "{run_id}" \
  --driver "$([ -n "${CODEXTENDER_ACTIVE:-}" ] && echo codex || echo claude)" > "{project_root}/.shipwright/planning/iterate/{run_id}/architecture-review-raw.json"
```

Read `verdicts` (`{glm, openai|opus}`, each `approve | revise | reject`) and the two
`reviews.*.feedback` texts. A non-zero exit or unparseable stdout is NOT a verdict:
record `reviews.architecture.status: "unavailable"` with a `reason` and proceed, as
for a provider that did not answer. **Record `reviews.architecture` for every
outcome** (`completed` + the `verdicts`, or the `skipped_*` / `missing_keys` /
`unavailable` value) — a non-halting `revise` must not vanish silently. `approve` → proceed. Any other value (`unknown` = unparseable, `unavailable` = the provider did not answer) is NOT a reject — proceed and note it in the ADR, exactly as a degraded provider is handled elsewhere. `revise` → integrate like any other
finding (ADR table). Both go under `## Architecture Review` in the sub-iterate's F3
decision-drop (a campaign unit has no iterate spec to hold it; section format:
`iteration-planning.md` step 2a) — where the withheld reasoning re-enters the record.
The brief is written by the agent that already built the change, so it anchors on
that choice — a known limitation (the internal arm cannot run here); keep "do
nothing" and a no-new-mechanism option on the table, as the template asks.

**A `reject` from EITHER architecture reviewer — HALT THE UNIT.** (The two
architecture verdicts only — the `--mode iterate` plan review carries no halt.) The interactive contract is
"STOP and ask the operator"; the runner cannot ask, so the answer is the shape
Branch B already uses for a condition it cannot resolve itself: **stop, record
everything, let the orchestrator surface it at campaign end.** Do NOT finalize,
commit, push or record further review rows, and do not "reconcile" the reject
yourself — the operator decides between taking the alternative, keeping the plan,
or reworking. In this order: (1) `mkdir -p` the directory of the path Step 6 resolves (attempt-scoped
`$(dirname "{state_path}")/runs/{loop_id}/{unit_id}/a{attempt}` when `unit_id` is present, else its
pre-R5a fallback); (2) save the halted
work — it exists only as uncommitted changes in a per-unit worktree the drain may
clean up — `git -C "{project_root}" add -N . && git -C "{project_root}" diff --binary HEAD > <that dir>/halted.patch`;
(3) **write the result to that directory's `result.json`, `halted_patch` set, BEFORE
returning it** (3e reads that file, not your return value: a missing file is
recorded as a synthetic `failed` and the whole payload is lost); (4) return the same
JSON. The `plan` row is deliberately left unrecorded on a halt (F11 never runs for
this unit; `result.json` carries the decision). Return `status:"escalated"`,
`reason_code:"architecture_review_rejected"` with the whole decision inline:

```json
{"sub_iterate_id": "{sub_iterate_id}", "status": "escalated",
 "reason": "architecture_review_rejected: an operator must choose the alternative, keep the plan, or rework",
 "reason_code": "architecture_review_rejected", "detected_complexity": "medium",
 "architecture_review": {
   "verdicts": {"glm": "reject", "openai": "approve"},
   "recommended_alternative": "{the reviewers' smallest-thing-that-would-do, one line}",
   "findings": ["{each high/medium finding, one line}"]},
 "halted_patch": "{path written above}"}
```

`verdicts` are copied verbatim from the CLI. `recommended_alternative` is required and
non-blank: when the rejecting reviewer names none, write
`"none named by the reviewers - see findings"` — never invent one. The schema checks
the shape; `autonomous_loop.py record` does not validate reason-code fields, so the
runner is the enforcement point.

### Unavailable — the run continues, loudly

Operator decision (finalization-claims-hardening §5.2): an autonomous run MAY continue
when the external review cannot run, never silently, and no env-var waiver exists.
Applies to the plan call above and to the code call (runner Step 3.7 item 2).

1. **Keep the capture.** Both redirects (`>` and `2>`) truncate on every call, so the
   files hold the LAST attempt's output. They ARE the evidence: F11's review-record
   check (and `record_review_pass.py record`) refuse `--reason-code unavailable` on
   `plan` / `external_code` unless the raw file is the adapter's failure envelope
   (`success: false` or `degraded: true`) or, when it holds no JSON, the `.stderr.txt`
   is non-empty. A successful reply refuses the claim — record it `completed`. Stage
   the capture with `reviews.json` at F6: it is read from the commit.
2. **Record** the row `not_run --reason-code unavailable` (Recording below; no
   `--marker-status`) and carry on with the build — no halt, no retry loop. At medium+
   the code-review floor then waits for the delegated cascade: `external_code`
   `unavailable` plus `code` `not_run --reason-code delegated-to-orchestrator` passes
   F6-verify, because 3f-bis promotes `code` to `completed` before any merge (or stops).
3. **Be loud**, once, after the last external pass of the run:
   `uv run "{shared_root}/scripts/tools/review_unavailable_note.py" --project-root "{project_root}" --run-id "{run_id}" --file-triage`
   prints the line and files ONE re-run triage card per run (idempotent; exit 1 = the
   card was NOT filed — say so, never drop it). Put its line in `result.json`
   `reviews.unavailable_note` (`"none"` when every pass ran); whoever opens the PR pastes
   it into the body, and campaign-end step 5 prints it. F11's passing review-record line
   names the passes too.

The architecture call (Call 2) adds no row; its `unavailable` stays as described above.

### Branch B — `missing_keys`

Autonomous; cannot prompt. Log, proceed, record the opt-out; the orchestrator
surfaces it at campaign end. Neither call runs. (`uv run --project` failure ≠ this
branch — `iteration-reviews.md`'s note: `--status not_run --reason-code unavailable`,
no `--marker-status`.)

### Branch C — `user_disabled`

`external_review.feedback_iterations: 0`: notice + skip both calls; record
`skipped_config_disabled` in the ADR.

### Recording

Always record the pass — writes the review record AND dual-writes the legacy marker.
Every pass here records its row (`self` 3.6, `plan` + `plan_internal` +
`architecture_internal` here, `code` + `doubt` 3.7, `external_code` cascade); F11
STOPs while any is `pending` and refuses a `not_run` row without its `--reason-code`
(Branch B → `missing-keys`, Branch C → `config-disabled`, a `uv run` / capability
failure → `unavailable`, which needs its capture — *Unavailable* above; a `--disposition` is
optional beside it). **The architecture call adds no row** — its verdicts live in the ADR section and
in `result.json` `reviews.architecture`. Both internal-arm commands are in
`iteration-reviews.md` → *Campaign sub-iterate rows*.

```bash
uv run "{shared_root}/scripts/tools/record_review_pass.py" record \
  --project-root "{project_root}" --run-id "{run_id}" --review-type plan \
  --status "{completed | not_run}" --provider "{openrouter | null}" \
  --marker-status "{completed | skipped_user_opt_out | skipped_config_disabled}" \
  [--from external-review-json --payload-file "{project_root}/.shipwright/planning/iterate/{run_id}/external-plan-review-raw.json"] \
  [--reason-code "{missing-keys | config-disabled | unavailable}"] [--disposition "{why}"]
```

### What the orchestrator does with a halted unit

`autonomous_loop.py record` exits `3` for any `escalated` result, so the WHOLE wave
STRICT-STOPs exactly as it does for `complexity_large` / `ci_supplychain_requires_operator`
(`campaign-mode.md` 3f) — no unit of that wave merges, `escalated` is terminal, and a
false reject costs a stalled wave until an operator looks (parity with the
interactive STOP, accepted). For a claimed R5a row (`attempt_id` set) `record`
stores the ROW as `failed` (`resolve_record_status` collapses `escalated`), with the
prose `reason` as `failure_reason`; only the persisted `result.json` at the row's
`result_path` keeps `status`, `reason_code` and `architecture_review`. Campaign-end
step 5 therefore scans every non-complete unit's `result_path`, never the row status.

**Known limitation:** this step runs after Step 3 (Build) — its trigger reads the diff
(Step 3.4) — so a reject arrives once the build cost is spent; `halted.patch` keeps
that work recoverable for the operator's "keep the plan" choice.
