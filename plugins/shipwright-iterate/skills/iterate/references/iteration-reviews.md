# Iteration Reviews Reference

Consolidated protocol for: Self-Review, Full Code Review trigger, Session Handoff.

---

## Why Self-Review is Mandatory

Self-review is non-negotiable regardless of complexity or external-review
availability. Trivial changes hide trivial mistakes; small iterations
accumulate. This is the "2x denken" pass — re-read your own diff with a
critic's eye before committing.

- **Trivial / small complexity:** Self-Review Checklist is the only review.
- **Medium+ complexity:** Self-Review + External LLM Review (or interactive
  opt-out per [iteration-planning.md](iteration-planning.md) Branch B) +
  code-reviewer subagent for large diffs.

---

## Self-Review Checklist

Run AFTER implementation, BEFORE commit. All change types, all complexity levels.
This is the 8-point checklist; for each item: pass or fail + 1-sentence
explanation. Fix all failures before committing.

### 1. Spec Compliance
Does the code implement what was specified?
- All features/endpoints/components from the spec exist
- No extra features added beyond the spec (YAGNI)

### 2. Error Handling
Are system boundaries properly guarded?
- API routes have try/catch with meaningful error responses
- External service calls (DB, APIs) handle failures
- No unhandled null/undefined at data boundaries

### 3. Security Basics
Is user input treated as untrusted?
- No raw user input in SQL queries (use parameterized queries)
- No raw user input in HTML output (use framework escaping)
- No hardcoded secrets, API keys, or tokens in source
- Auth/permission checks on protected routes

### 4. Test Quality
Do tests validate behavior, not implementation?
- Tests assert on outcomes, not internal state
- At least one happy-path and one error-path test per feature
- No tests that always pass regardless of implementation

### 5. Performance Basics
Any obvious performance issues?
- No N+1 query patterns (loop of DB calls → use join/include)
- List endpoints paginated (no unbounded result sets)
- No large synchronous blocking in async handlers

### 6. Naming & Structure
Is the code consistent with the existing codebase?
- File and folder locations match project conventions
- No single file exceeds 300 lines (split if needed)
- Variable/function names follow existing patterns

### 7. Affected Boundaries
Were producer and consumer of any changed serialized format identified,
AND was a real round-trip probe run? See `references/round-trip-tests.md`.
- For every changed serialized format: producer + consumer pair listed
- Round-trip test (producer→file-on-disk→consumer) exists and passes
- For user-edited formats: all 8 probe categories from
  `references/boundary-probes.md` checked
- If `touches_io_boundary` risk flag fired: round-trip test is mandatory
  (Safety-enforced in Override Classes — skippable only with explicit
  risk acknowledgment in the iterate ADR)
- If no boundaries touched: mark `n/a` with one-line justification

### 8. Test Hygiene Probe
Run the static probe against changed test files and resolve any findings.
The probe surfaces silent-skip patterns that mask CI tooling absence or
collection-time-only `@pytest.mark.skipif` decorators that can't carry a
CI gate structurally. See ADR-044 + ADR-045.

The same command also scans changed **TS/JS** specs (Playwright / Vitest /
Jest). There a `test.skip` / `it.skip` / `describe.skip` / `test.fixme` /
`test.todo` / `xit` (incl. chained `.skip.each` / `.only.each` /
`.concurrent.only`) must carry a structured **quarantine annotation**
(`@quarantine` comment block with `reason` + `owner` + `ticket` +
`expires: YYYY-MM-DD`); an **expired** or >180-day-out `expires` fails, and a
focused test (`.only` / `fit` / `fdescribe`) is an **unconditional** failure
that can never be quarantined. A runtime conditional `test.skip(cond, 'reason')`
(first arg not a string) is exempt. The TS/JS leg is diff-scoped by line — an
expired or bare skip only fails a PR that introduces or edits it.

```bash
uv run shared/scripts/tools/scan_test_hygiene.py --diff
```

- **Mandatory at medium+**
- Advisory at trivial / small
- Skip rules (Python): an explicit `# test-hygiene: allow-silent-skip — <rationale>`
  marker comment on the offending line (or in a contiguous comment block
  immediately above it) suppresses a finding. The rationale must
  describe a setup-condition or upstream-state gate (not a binary-on-PATH
  gate, which is exactly what the rule catches).
- Skip rules (TS/JS): the `@quarantine` block above the skip is the only
  escape for a `skip`/`fixme`/`xit`; there is no escape for `.only`/`fit`.
- Exit code: `0` = no findings (pass); `1` = findings present (fail —
  either fix or document with the marker/quarantine); `2` = usage error.

### Output Format
```
Self-Review:
  1. Spec Compliance:    [pass/fail] {explanation}
  2. Error Handling:     [pass/fail] {explanation}
  3. Security Basics:    [pass/fail] {explanation}
  4. Test Quality:       [pass/fail] {explanation}
  5. Performance Basics: [pass/fail] {explanation}
  6. Naming & Structure: [pass/fail] {explanation}
  7. Affected Boundaries:[pass/fail/n/a] {explanation}
  8. Test Hygiene Probe: [pass/fail/n/a] {explanation}

Action: {Fix items X, Y before commit / All clear, proceed to commit}
```

Then **record the pass** (`--review-type self --from self-review`) per
"Recording each review pass" below — the same eight items as
`{"items":[{"name","verdict","note"}]}`. At trivial and small complexity this is
the ONLY review that runs, so it is the only thing the Review artifact can show.

---

## Full Code Review Trigger

### When to Spawn `code-reviewer` Subagent
- Diff exceeds **100 lines** of changed code
- Change touches **security-sensitive files** (auth, middleware, RLS policies, migrations)
- Complexity = **medium+** (always)

### When Self-Review is Sufficient
- Trivial/small complexity with no risk flags
- Diff under 100 lines
- No security-sensitive files touched

### Invocation
The code-reviewer subagent from `shipwright-build` is reused. Provide:
- The diff (`git diff HEAD~1`)
- The iterate spec or affected FR section
- The self-review results

### Reviewer Cascade — `spec-reviewer` → `code-reviewer` → `doubt-reviewer`

The reused `shipwright-build` reviewers form a three-stage cascade (the same one
`/shipwright-build` Step 6 runs — see that plugin's `references/code-review.md`).

**Who runs it.** **A standalone iterate spawns the cascade itself**, from
SKILL.md Step 8, before F6 (commit) — it has the `Agent` tool, so there is no
delegate. Only in **campaign mode** does the question of delegation arise at
all: the sub-iterate-runner subagent has no `Agent` tool, so
`agents/sub-iterate-runner.md` Step 3.7 hands the cascade to the orchestrator
(see `campaign-mode.md` for what that currently does and does not cover). Do not
read the campaign delegation as a general rule — that misreading is what let
standalone runs finish with no internal review at all.

All three stages run in this fixed order:

1. **`spec-reviewer` (Stage 1, HARD-GATE).** Spec-compliance only: does the diff
   match the iterate spec / affected FR? A REJECT cites the exact spec line and
   **blocks Stage 2** — the `code-reviewer` does not run until `spec-reviewer`
   returns PASS. Re-review the fixed diff until PASS.
2. **`code-reviewer` (Stage 2, quality).** The existing 5-axis review, run only
   behind a Stage-1 PASS.
3. **`doubt-reviewer` (Stage 3, conditional, advisory).** After Stage 2 passes,
   and **only** when the diff touches a non-trivial surface — migrations,
   async/concurrency, cross-plugin imports, or irreversible ops — a fresh-context,
   disprove-biased pass. Docs-only / trivial diffs skip it. It is
   advisory-must-address: the implementer answers each doubt in writing (fix or
   reasoned rebuttal) before commit; it does not hard-block the way Stage 1 does.

All three are **internal** Claude subagents. The external cascade below stays a
generic code-quality second opinion on the diff — the spec-compliance and doubt
roles are not cascaded to external LLM providers.

---

## External Code-Review Cascade (medium+, default on)

Cascade an external LLM review of the diff against the iterate spec. This is a
second-opinion gate that mirrors the existing mini-plan-review Branch A/B/C
interactive opt-out flow.

### Trigger Rule

The cascade fires on **its own** conditions — the same thresholds as the
internal reviewer, evaluated independently:

- Diff > 100 lines, OR
- security-sensitive files touched, OR
- complexity = medium+

A trivial/small iterate that meets **none** of the three — no risk flag, no
security-sensitive file, diff under 100 lines — does NOT run the cascade, even
if API keys are present. Self-review is the only review for those.

Note that this is an exemption for *quiet* small runs, not for small runs as
such: a small iterate that touches auth or ships a 200-line diff satisfies a
threshold above and the cascade **does** fire. That mirrors the internal
reviewer's own rule ("When Self-Review is Sufficient" — small **and** no risk
flags **and** under 100 lines), which is what makes the two routes genuinely
symmetric rather than merely both present.

**It is NOT conditional on the internal `code-reviewer` having fired.** It used
to be — the rule read *"fires iff the internal subagent fired in this run"* —
and that wired the two reviews in series behind a single point of failure: if
the internal pass could not run for any reason (tool unavailable, session
policy, a crash, or simply not being invoked), the external pass was excused
along with it and a medium+ iterate could finish with **no code review at all**.

That was not theoretical bookkeeping. Of the 27 review records in this repo when
the rule was changed, **15 recorded `code = not_run` and ran the external review
anyway** — every agent overrode the rule, because following it would obviously
have been wrong. A rule that is universally routed around is evidence about the
rule. The two reviews are now independent routes to the same guarantee.

### When the internal reviewer cannot run — escalate, never lapse

**0. First establish that it genuinely cannot run.** This ladder is for a *real*
blocker, and there are exactly four:

1. this agent type has **no `Agent` tool** — structurally the sub-iterate-runner;
2. the tool **errored** when called (a permission *denial* counts here — say so);
3. the run is a **campaign sub-iterate built by the runner under `--autonomous`**,
   where there is no operator to ask. A *standalone* run that an operator merely
   described as "autonomous" is **not** this case: the person who wrote that
   invocation is present, so ask them;
4. the operator was asked and **declined** — including an answer that declines by
   deferring ("later", "just do the external one").

**Anything not on this list is not a blocker.** Name it verbatim and treat the
pass as unproven rather than inventing a fifth class. If a question goes
unanswered, that is not "declined" — say the question was asked and got no
answer.

A standing session policy that a request would lift — e.g. *"do not call the
Agent tool unless the user requested it"* — **is not a blocker until** the
request has been made and declined. **And a project whose `CLAUDE.md` states
that review subagents are requested by default has already made it**: the policy
is satisfied, nothing is gated, and there is nothing to ask. **Read the file —
do not assume it.** A project onboarded before the grant shipped, or one that
deleted the section, is the ungranted case below. The grant covers the review
cascade only: dynamic workflows, deep-research and parallel implementation
subagents are asked for separately, every time. **Absent such a grant**, nothing carries one across
compaction, a handoff or a resume, so **if you cannot establish from this
session that permission was given, ASK** — a redundant question costs one line;
a lost pass costs the review. (SKILL.md B1's resume replay-check re-runs Step 4
and Step 7, never Step 8, so a resumed run reaches F11 without ever having
asked.) It is conditional and one sentence lifts it,
so SKILL.md Step 8 asks *before Stage 1*. Recording `not_run` because nobody
asked is a silent skip wearing an escalation's clothes: it produces the same
green gate as a genuine blocker while costing a pass the external route cannot
replace (the spec-compliance and doubt roles are not cascaded externally).

If the cascade genuinely cannot be run, the responsibility moves **outward**, it
does not disappear:

1. the external review becomes **mandatory** and carries the pass — record it
   `--review-type external_code --status completed`;
2. record `code` — **and `doubt`, which Stage 3 cannot reach without a Stage 2
   pass** — as `not_run`, each with a disposition naming *why* and specifically
   **which of the four** blockers above applied, because "a session directive"
   reads identically whether or not anyone asked. Record `doubt` `not_run` only
   **when Stage 3 would have applied to this diff**; on a docs-only or trivial
   surface it is `not_applicable` naming the conditional rule, because saying
   "blocked" about a pass that was never due is the same false statement this
   record exists to prevent. Do **not** record either
   `completed` "by substitution": that claims the pass the contract describes
   ran, and it did not;
3. in campaign mode the same escalation is what ADR-029 already specifies —
   the runner has no `Agent` tool, so the cascade is delegated to the
   orchestrator. This section is its standalone-mode counterpart, which was
   missing.

**This is enforced, not merely instructed.** At medium+ the F11 verifier
`check_review_record` fails the run unless at least one of `code` /
`external_code` is `completed`. `not_applicable` on both does not satisfy it —
otherwise the gate would be passable by re-labelling. See
`shared/scripts/tools/verifiers/review_record_check.py`.

For build (per-section opt-in, default off) see
`{build_plugin_root}/skills/build/SKILL.md` Step 6c.

### Operator Warning — Diff Exposure

Enabling the external code-review cascade transmits the staged diff to
a third-party LLM provider (OpenRouter or OpenAI direct,
depending on which keys are configured). Diffs are higher-risk than
plans because they may contain secrets, customer data, or code under
restrictive license terms accidentally checked into the patch. If those
risks apply to your project, set
`shipwright_iterate_config.json` → `external_code_review.enabled: false`
to opt out at the project level (one-time switch — falls into Branch C
"user_disabled" below).

### Branch A — `available` (keys present, not user-disabled)

```bash
git diff HEAD > /tmp/shipwright-review-diff.txt

uv run "{shared_root}/scripts/tools/external_review.py" \
  --mode code \
  --diff-file /tmp/shipwright-review-diff.txt \
  --spec-file "{iterate_spec_path}" \
  --plugin-root "{plan_plugin_root}"
```

Parse `reviews.deepseek.feedback` + `reviews.openai.feedback`. Merge any
high/medium-severity findings into the iterate ADR's
`External-Code-Review-Findings` table. Address before commit (apply fix,
rerun tests) — same disposition pattern as the mini-plan-review block:
each finding marked `accepted-and-fixed` or `rejected-with-reason`.

If the CLI returns `skipped: "empty_diff"` (which happens when the diff
file is empty or whitespace-only), the cascade is recorded as
`skipped_user_opt_out` with reason `empty_diff` and the run continues.

If the CLI exits **non-zero** or the JSON has `"degraded": true` (keys were
present but every review leg failed — bad key, API param error, timeout), the
external review **did not run**. Do NOT mark the cascade `completed`: surface
the `degraded_reason`, then treat it exactly like Branch B `missing_keys` —
re-check keys (Option 1) or fall back to self-review and record the opt-out
(Option 2). A degraded gate must never be recorded as a passing review.

### Branch B — `missing_keys`

STOP and ask the user verbatim:

> External LLM code-review is the recommended cascade for this medium+
> shared-infra change, but no `OPENROUTER_API_KEY` or
> `OPENAI_API_KEY` was found in `.env.local`.
>
> **Option 1 (recommended):** Add a key to `.env.local` and say "ready" —
> I'll re-check and run the cascade.
> **Option 2:** Skip external code-review. The internal subagent already
> ran and its findings stand. Mark this run as opted-out in the iterate
> ADR.
>
> Which option?

- Option 1 → re-check via `check-external-review-keys.py`, then Branch A.
- Option 2 → log opt-out (with user's reason) in the iterate ADR. No
  further work — the internal subagent review remains the cascade gate.

### Branch C — `user_disabled`

`shipwright_iterate_config.json` → `external_code_review.enabled: false`.
Print a notice and skip the cascade. The internal subagent review remains.

The cascade has its own opt-out flag — it is intentionally NOT controlled by
the plan/iterate-mode `external_review.feedback_iterations: 0` knob. Users
can disable plan/iterate external review while keeping the code-review
cascade on, and vice versa.

### Write the cascade marker (all branches)

Record the pass per **Recording each review pass** below with
`--review-type external_code --marker-status {completed | skipped_user_opt_out |
skipped_config_disabled}`. That writes the record AND dual-writes
`external_code_review_state.json` — distinct from the plan/iterate-step
`external_review_state.json`. The two markers represent independent gates and
never collide.

---

## Recording each review pass (MANDATORY — F11 gate)

Every review pass writes its result to the run's review record:

```
.shipwright/planning/iterate/{run_id}/reviews.json
```

Six types under `reviews`, all materialized up front, each closed by the pass
that owns it: `self` · `plan` · `code` · `doubt` · `external_code` · `spec`.

**`spec` used to live in a sibling `gates` object, and no longer does.** The
`reviews` object is a CROSS-REPO contract, and the webui consumer
(`shipwright-webui` `server/src/core/mission-context/review-record.ts`) used to
reject a record whose `schema_version` differed by strict `!==`, or whose
`reviews` carried any key outside its own five — while an invalid record does
**not** fall back to the marker view: it renders every row as a data-integrity
fault (`review-state.ts`). A sixth key would therefore have reported every
healthy record as corrupt, so `spec` was parked outside everything the consumer
inspected.

That reader shipped its tolerant half in `ce21323e` (PR #339): the version is now
a **floor** (`>=`) and an unrecognised `reviews` key is rendered as an extra row
instead of rejected. `spec` was promoted on the strength of it. Two consequences
that are not obvious:

* **`schema_version` stays `1`.** A floor makes a bump worthless to the consumer,
  while `validate_record` still rejects a version newer than its own constant —
  so a bump only creates casualties among plugin caches that have not updated.
* **Records written before the promotion keep `spec` under `gates`,** and are
  read from there permanently. They are immutable and git-tracked; 65 of them
  existed at promotion time and not one carried `spec` under `reviews`. Without
  that read path this repo's own fail-closed F11 gate would have called all 65
  corrupt.

**Deployment, not merge, is the gate.** This plugin auto-updates through the
marketplace cache; the webui is hand-deployed. A new producer against an
un-redeployed webui makes every row render "could not be read", which is false
under version skew.

**Stage 1 can now prove it ran.** `spec-reviewer` closes `spec`; `code-reviewer`
closes `code`; `doubt-reviewer` closes `doubt`. The gate enforces the cascade's
own ordering: **a `code` row recorded `completed` while `spec` is not `completed`
FAILS**, because Stage 2 cannot legitimately have run without its HARD-GATE
passing first. `external_code` is deliberately outside that rule — the
spec-compliance and doubt roles are not cascaded to external providers, so a run
carried by the external route closes `spec` as `not_run` with a disposition, and
`_substitution_note` reports what that does not buy.

> **Do not re-attempt: carrying the Stage-1 verdict inside the `code` row.**
> That shape was built and then WITHDRAWN on
> `iterate-2026-07-28-cascade-delegated-to-nobody` after three independent
> reviewers disproved it. `status=completed` let a Stage-1-only row satisfy the
> medium+ code-quality floor although Stage 2 provably had not run;
> `status=not_run` discards the findings; the write ordering was unknowable at
> write time because a REJECT you intend to fix is not terminal; and the verdict
> was never validated, so `{verdict: ERROR}` recorded as non-blocking. `spec`
> having its own row is what makes all four moot — `--recorded-by` was prose,
> not proof.

**A completed code row must carry evidence, not just a status.** At medium+ the
floor is satisfied only by a `code` / `external_code` row carrying at least one
of: a non-empty `findings` list, a non-blank `provider`, a non-blank
`raw_excerpt`, or a non-blank `recorded_by` naming an adapter other than `none`.
`--status completed` with `--from` omitted produces a row with none of them —
indistinguishable from one nobody earned — and that no longer greens the gate.

**F11 stops the run while any type is still `pending`** (small+; skipped at
trivial), so an empty Review row in the Mission view always means "genuinely not
run", never "nobody wrote it down". A `spec` row absent from **both** sections
counts as pending: the schema tolerates the absence so older records stay
readable, and a live run gets nothing from that — it cannot dodge the row by
declining to write it. The reviewers
already return structured JSON; before this record existed it survived only as
ADR prose and was thrown away.

Materialize once, early in the run:

```bash
uv run "{shared_root}/scripts/tools/record_review_pass.py" init \
  --project-root "{project_root}" --run-id "{run_id}"
```

**A pass that RAN** — write the reviewer's reply to a file verbatim (raw JSON,
or the whole message with its ```json block; both are accepted) and hand it over:

```bash
uv run "{shared_root}/scripts/tools/record_review_pass.py" record \
  --project-root "{project_root}" --run-id "{run_id}" \
  --review-type {self|plan|spec|code|doubt|external_code} --status completed \
  --from {self-review|spec-reviewer|code-reviewer|doubt-reviewer|external-review-json|external-prose} \
  --payload-file "{path to the reply}" \
  [--provider openrouter] [--marker-status completed]
```

For `external-review-json`, the recorder re-derives each reviewer verdict from
the full provider legs, stores the validated pair on the authoritative review
row, and writes the companion marker from that same pair. A current envelope
must be `deepseek`/`openai`; an implicit historical envelope remains readable
as `gemini`/`openai`. A completed current marker without both verdicts blocks.

| Pass | `--review-type` | `--from` | payload |
|---|---|---|---|
| Step 7 Self-Review | `self` | `self-review` | `{"items":[{"name","verdict":"pass\|fail\|n/a","note"}]}` — one entry per checklist item |
| External plan/iterate review (Branch A) | `plan` | `external-review-json` | `external_review.py` stdout, verbatim. Add `--marker-status` |
| `spec-reviewer` (Stage 1, HARD-GATE) | `spec` | `spec-reviewer` | the subagent's reply verbatim (`{stage, verdict, spec_citations[]}`). Must be `completed` before a `completed` `code` row |
| Internal `code-reviewer` (Stage 2) | `code` | `code-reviewer` | the subagent's reply |
| `doubt-reviewer` (Stage 3) | `doubt` | `doubt-reviewer` | the subagent's reply |
| External code cascade | `external_code` | `external-review-json` | `external_review.py` stdout. Add `--marker-status` |

**A pass that did NOT run** must say so and name the rule — a bare "skipped" is
rejected:

```bash
uv run "{shared_root}/scripts/tools/record_review_pass.py" record \
  --project-root "{project_root}" --run-id "{run_id}" \
  --review-type doubt --status {not_run|not_applicable} \
  --disposition "docs-only diff; the doubt pass is conditional per iteration-reviews.md"
```

`not_applicable` when the phase matrix says the pass does not apply at this
complexity or change shape; `not_run` when it applied but was skipped (opt-out,
missing keys, degraded provider).

### Campaign sub-iterate rows

The sub-iterate-runner subagent has no `Agent` tool, so it performs `self`,
`plan` and `external_code` and performs neither internal stage. It records
exactly this — **who did the work decides the name** (`agents/sub-iterate-runner.md`
Step 3.7 carries the actor table). Each `…` below stands for the invocation
prefix, i.e. `uv run "{shared_root}/scripts/tools/record_review_pass.py" record
--project-root "{project_root}" --run-id "{run_id}"` — so `…` already includes
`record`, and the lines below continue from there:

```bash
# the external run — under its OWN name, never as `code`.
# `--from`/`--payload-file` are NOT optional: a row recorded without a payload
# carries findings_count 0 and is indistinguishable from a fabricated one.
… --review-type external_code --status completed \
  --from external-review-json --payload-file "{external_review.py stdout}" \
  --provider openrouter --marker-status completed

# …or, when it did not run. `not_run` REQUIRES a disposition, and the marker
# vocabulary is narrower than the result-JSON one — `skipped_diff_below_threshold`
# is a valid result.json status but NOT a valid --marker-status.
… --review-type external_code --status not_run \
  --disposition "{the rule that applies, e.g. external_code_review.enabled is false for this project}" \
  --marker-status "{skipped_user_opt_out | skipped_config_disabled}"

# the delegated internal cascade — recorded as NOT having run.
# Stage 1 has a row of its own and is delegated with the rest; omitting it
# leaves `spec` pending and reds the sub-iterate at F11.
… --review-type spec --status not_run \
  --disposition "blocker 1 (no Agent tool): the sub-iterate-runner cannot spawn the Stage-1 spec-reviewer; delegated with the rest of the cascade (ADR-029, campaign mode only)"

… --review-type code --status not_run \
  --disposition "blocker 1 (no Agent tool): the sub-iterate-runner cannot spawn the cascade; delegated to the campaign orchestrator (ADR-029, campaign mode only)"

# Stage 3 cannot precede Stage 2
… --review-type doubt --status not_run \
  --disposition "blocker 1 (no Agent tool): Stage 3 runs only behind a Stage 2 pass, and the internal cascade did not run in this campaign sub-iterate"
```

A bare `--disposition "delegated"` is **rejected** (a disposition must name a
rule: more than one word, ≥12 chars). Spell the limit out — that string is the
only evidence a later reader gets.

**Immutable after completion.** Re-recording a closed type exits `3`; use
`--force` only to correct a genuinely wrong record.

**A run that predates this record** (mid-flight when it landed) closes
everything still open in one command:

```bash
uv run "{shared_root}/scripts/tools/record_review_pass.py" close-missing \
  --project-root "{project_root}" --run-id "{run_id}" \
  --status not_run --disposition "predates the per-run review record"
```

---

## Session Handoff Protocol

### Trigger
Context pressure detected: conversation exceeds ~70% of available context window.
Heuristic signals:
- Tool result truncation increasing
- 15+ tool calls on a single iterate run
- Agent notices it's losing track of earlier context

### Required Payload
Write to `.shipwright/agent_docs/session_handoff.md`:

```markdown
# Session Handoff: {run_id}

## State
- **Run ID:** {run_id}
- **Branch:** {branch_name}
- **Complexity:** {original} → {current if escalated}
- **Phase:** {active phase when handoff triggered}

## Completed Phases
- [x] Intent classification: {type}
- [x] Complexity assessment: {level}
- [x] Iterate spec: {path or "skipped"}
- [x] Mini-plan: {path or "inline" or "skipped"}
- [ ] Build: {partial / not started}
- ...

## Files Modified
{list of files changed so far}

## Test Status
{last test run: pass/fail, counts}

## Remaining
{phases still to complete}

## Blocked/Parked
{any parked visual groups, unresolved items}

## Resume Command
/shipwright-iterate  (Step B1 detects the iterate/* branch and offers Resume/Abandon/Complete)
```

### Generation Rules
- Best-effort: write what's known, don't block on missing fields
- Commit to branch before handoff
- Include enough context for next session to resume without re-reading all files

### How Resume Works (Step B1 in SKILL.md)
When a new session starts, Step B1 checks for existing `iterate/*` worktrees and `session_handoff.md`. If found, it offers three options: Resume (`cd` into the worktree, skip to the remaining phase), Abandon (remove the worktree + branch, start fresh), or Complete (skip to finalization). The handoff file is the primary source of truth for what was done and what remains.
