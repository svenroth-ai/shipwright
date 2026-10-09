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

**How the 100 lines are counted** (one definition, `shared/scripts/lib/review_diff_threshold.py`):
added + removed lines against the merge-base with the trunk (`git diff --numstat
--no-renames <merge-base>`, untracked files included before the commit), without
`.shipwright/`, `CHANGELOG-unreleased.d/`, `shipwright_events.jsonl` and
`shipwright_test_results.json`. Strictly greater than 100: exactly 100 does not
trigger. Not `git diff HEAD~1 | wc -l`, which counts headers and context lines
and sees only the last commit. **Enforced at small:** F11's `check_cascade_trigger`
re-measures the branch and re-reads the risk flags. The `code` row must then be
`completed`, or `not_run` with a `--reason-code` from the closed `review_not_run`
set that this gate accepts: `unavailable`, `delegated-to-orchestrator` or
`user-opt-out`. A free-text disposition alone fails, and so does every other
code. A diff F11 cannot measure (no trustworthy trunk base, or a trunk tip no
remote trunk ref contains) or an unreadable risk-flag source counts as triggered,
never as quiet. A missing complexity in the F5c entry is in scope, not a skip.

### When Self-Review is Sufficient
- Trivial/small complexity with no risk flags
- Diff of at most 100 changed lines
- No security-sensitive files touched

### Invocation
The code-reviewer subagent from `shipwright-build` is reused. Provide:
- The diff (`git diff HEAD~1`)
- The iterate spec or affected FR section
- The self-review results

### Reviewer Cascade — `spec-reviewer` → `code-reviewer` → `doubt-reviewer`

The reused `shipwright-build` reviewers form a three-stage cascade (the same one
`/shipwright-build` Step 6 runs — see that plugin's `references/code-review.md`,
including its "Model tier" note — the `review` tier resolved at this skill's
own SKILL.md §F applies at every spawn in the cascade, standalone or delegated).

**Who runs it.** **A standalone iterate spawns the cascade itself**, from
SKILL.md Step 8, before F6 (commit) — it has the `Agent` tool, so there is no
delegate. Only in **campaign mode** does the question of delegation arise at
all: the sub-iterate-runner subagent carries the `Agent` tool and spawns the
cascade itself (`agents/sub-iterate-runner.md` Step 3.7, at the resolved review tier), and only
when a spawn cannot happen does it hand the cascade to the orchestrator's
`3f-bis` fallback (`campaign-mode.md`). Do not read that fallback as a general
rule — that misreading is what let standalone runs finish with no internal
review at all.

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
security-sensitive file, diff of at most 100 changed lines — does NOT run the cascade, even
if API keys are present. Self-review is the only review for those.

Note that this is an exemption for *quiet* small runs, not for small runs as
such: a small iterate that touches auth or ships a 200-line diff satisfies a
threshold above and the cascade **does** fire. That mirrors the internal
reviewer's own rule ("When Self-Review is Sufficient" — small **and** no risk
flags **and** at most 100 changed lines), which is what makes the two routes genuinely
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

1. this agent has **no usable `Agent` tool** — absent from its tools list, or unavailable at runtime (the sub-iterate-runner lists it, so for a runner this means the spawn itself failed);
2. the tool **errored** when called (a permission *denial* counts here — say so);
3. the run is a **campaign sub-iterate built by the runner under `--autonomous`**,
   where there is no operator to ask — this excuses questions, never the runner's own Step 3.5/3.7 spawns, which need no operator. A *standalone* run that an operator merely
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
2. record `code` — **and `doubt`, which Stage 3 cannot reach without a Stage 2 pass**
   — as `not_run`, each with a disposition naming *why* and specifically **which
   of the four** blockers above applied, because "a session directive" reads
   identically whether or not anyone asked. The code follows the blocker: #1 in a
   campaign and #3 → `--reason-code delegated-to-orchestrator`; #1 standalone and
   #2 → `unavailable`; #4 → `user-opt-out`. Record `doubt` `not_run` only **when
   Stage 3 would have applied to this diff**; on a docs-only or trivial surface it
   is `not_applicable` naming the conditional rule, because saying "blocked" about
   a pass never due is the false statement this record exists to prevent. Do
   **not** record either `completed` "by substitution": that claims the contract's pass ran, and it did not;
3. in campaign mode the same escalation is what ADR-029 already specifies —
   a runner that cannot spawn delegates the cascade to the orchestrator's
   `3f-bis`. This section is its standalone-mode counterpart, which was
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

The diff path is resolved via `review_scratch.py` — not a bare `/tmp/...`
literal, which bash and native Python resolve to different files on
Windows (root cause + design: `code-review.md` Step 6b in `shipwright-build`).
This whole block is one shell invocation, so the local variable is safe to
reuse within it. `RUN_ID` is assigned via `RUN_ID='{run_id}'` — SINGLE
quotes, not double quotes and not a heredoc. A heredoc looked stronger
(round-9 fix) but is actually WEAKER here: its quoted terminator only
blocks `$()`/backtick expansion, not a line-based collision — a value
containing a newline followed by a line matching the heredoc's own
delimiter terminates it early and lets injected commands run (PR #676
round-11 finding, confirmed by direct reproduction). A single-quoted string
has no such per-line terminator; it ends ONLY at the next literal `'`
character, so it safely contains embedded newlines, `$()`, backticks, and
`"` alike. `run_id` is minted in `RUN_ID_STRICT` form
(`shared/scripts/lib/iterate_entry.py`:
`^iterate-\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*$`) and rejected before this
step if malformed — that charset contains no `'` and no newline, so
`RUN_ID='{run_id}'` is provably safe given that precondition, which is
exactly the "validate before embedding" fix the round-11 review asked for.
Every later use references `"$RUN_ID"` — a variable expansion never
re-executes the metacharacters inside its own value:

```bash
RUN_ID='{run_id}'
DIFF_FILE="$(uv run "{shared_root}/scripts/tools/review_scratch.py" resolve --run-id "$RUN_ID" --name shipwright-review-diff.txt)"
trap 'ec=$?; uv run "{shared_root}/scripts/tools/review_scratch.py" cleanup --run-id "$RUN_ID"; exit "$ec"' EXIT
git diff HEAD > "$DIFF_FILE"

uv run --project "{plan_plugin_root}" "{shared_root}/scripts/tools/external_review.py" \
  --mode code \
  --diff-file "$DIFF_FILE" \
  --spec-file "{iterate_spec_path}" \
  --plugin-root "{plan_plugin_root}" \
  --project-root "{project_root}" --run-id "$RUN_ID" \
  --driver "{driver}" \
  > "{project_root}/.shipwright/planning/iterate/$RUN_ID/external-code-review-raw.json" 2> "{project_root}/.shipwright/planning/iterate/$RUN_ID/external-code-review-raw.stderr.txt"
```

(`--driver` is **required, no default** — the harness actually driving this
session, `claude` or `codex`, `codex` also when `CODEXTENDER_ACTIVE` is set
(even though the harness is `claude`) — same resolution rule as
[iteration-planning.md](iteration-planning.md) Step 3.5, **read directly, not
only inherited from it**: this cascade fires whenever a diff exceeds 100
lines or touches a security-sensitive file (see "Full Code Review Trigger"
above), which happens at any complexity, not only medium+ where Step 3.5
runs — a small run with no plan/architecture call must still resolve `codex`
here on its own. A Codex-authored diff must never be reviewed by another
OpenAI-family model, so this cascade's identity swap has to track the same
session's driver, not a hardcoded value.)

(The redirect writes the ONE canonical basename "Recording each review pass"
below names for `external_code` — `record_review_pass.py record` REJECTS a
`--payload-file` under a different name, exit 2 — trg-3b206c08.)

The `trap ... EXIT` above is what makes cleanup unconditional — a straight-line
`cleanup` call as the block's last line only runs if every prior line
succeeded, so a failed review command (or `set -e` in the caller's shell)
would otherwise skip it and leave the diff file (which can contain source
code) on disk. The trap fires on every exit path — success, failure, or
`skipped: "empty_diff"` — exactly once. It captures `$?` into `ec` BEFORE
running `cleanup` and re-exits with `ec` at the end: without that, a
successful cleanup command becomes the new last-command-run, and bash
reports *its* exit status (0) for the whole block, silently turning a
failed `external_review.py` into an apparent success.

(`uv run --project` is uv's own flag, distinct from the script's
`--project-root` a few lines below — `--project` points uv at
`shipwright-plan`, the plugin that declares the `openai` dependency
`external_review.py` imports; without it `uv run` resolves package context
from cwd, which has no such declaration outside this monorepo, and the
import silently fails.)

**`{plan_plugin_root}` resolution and `uv run` failure — canonical for every
site in this file, `iteration-planning.md`, `sub-iterate-runner.md`, and
`shipwright-build`'s `code-review.md` that pass `--project "{plan_plugin_root}"`.**
It resolves the same way `{plugin_root}`/`{shared_root}` already do for the
running session — the installed `shipwright-plan` plugin's root. This was
already harmless-if-wrong before this iterate (`--plugin-root` only matters
for `--mode plan`, never these `--mode code`/`iterate`/`architecture` calls),
but `--project` makes it load-bearing: a missing or unresolved value now
makes `uv run` itself fail before any provider is reached. Treat a non-zero
`uv run` exit, or stdout that is not the expected JSON, exactly like
`shipwright-plan not installed` in [iteration-planning.md](iteration-planning.md)'s
Internal Plan Review degraded handling — the pass did NOT run; record it
`not_run --reason-code unavailable` with that reason as the disposition, never parsed as a
completed review; the two capture files are its required evidence (`campaign-step-3-5-plan-review.md` → *Unavailable*). F6 stages the whole run dir: a `<stem>.stderr.txt` that backs no `unavailable` row is deleted before commit.

(`--run-id` additively records this call as an `external_review` timing span,
parent `review` — see [iterate-timings](iterate-timings.md).)

Read the redirected file back and parse `reviews.glm.feedback` +
`reviews.openai.feedback` (or `reviews.opus.feedback` under `--driver codex`; `reviews.model-1/2.feedback` when `provider` is `gateway`;
required, no default, never hardcoded — see iteration-planning.md). Merge any
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

Eight types under `reviews`, all materialized up front, each closed by the
pass that owns it: `self` · `plan` · `plan_internal` · `architecture_internal` ·
`code` · `doubt` · `external_code` · `spec`. `architecture_internal` is the
newest — added alongside the medium+ Internal Architecture Review sub-step
(`iteration-planning.md`), a fresh-context arm separate from `plan_internal`
so it escapes the plan's own reasoning frame; below medium+ it closes
`not_applicable` (the arm doesn't run there), same pattern every
complexity-gated type already follows.

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
carried by the external route closes `spec` `not_run --reason-code unavailable`
with a disposition, and `_substitution_note` reports what that does not buy.

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

**F11 stops the run while any type is still `pending`** — at every
complexity, trivial included — so an empty Review row in the Mission view always
means "genuinely not run", never "nobody wrote it down". It also stops a record
whose `self` row is not `completed` with evidence (the Self-Review runs at every
complexity, so an all-`not_run` record fails everywhere), and any `not_run` /
`not_applicable` row without a closed-vocabulary `reason_code` (below). A `spec` row absent from **both** sections
counts as pending: the schema tolerates the absence so older records stay
readable, and a live run gets nothing from that — it cannot dodge the row by
declining to write it. The reviewers
already return structured JSON; before this record existed it survived only as
ADR prose and was thrown away.

Materialize at Step 7 entry (immediately before the first reviewer spawn), not
merely "early" — a vague timing is what let this drift; `init` is idempotent,
so calling it again elsewhere is harmless, but Step 7 is where it must always
have run by:

```bash
uv run "{shared_root}/scripts/tools/record_review_pass.py" init \
  --project-root "{project_root}" --run-id "{run_id}"
```

**Immediate-write ordering mandate (MANDATORY).** The instant a reviewer or
`external_review.py` call returns, write its reply to a file verbatim and call
`record_review_pass.py record` — before any other reasoning, before spawning
the next reviewer, before anything else. **The payload file MUST use its
kind's ONE canonical basename** (table below) — never an ad-hoc name. This is
not stylistic: `record_review_pass.py` now REJECTS a `--payload-file` whose
basename does not match (exit 2, `canonical_basename_error` in
`lib.review_payloads`), and a path-based PR-review classifier that hides/skips
this file family from the reviewing model depends on a closed, predictable
name per kind — trg-3b206c08, measured 40+ ad-hoc basenames for the same
handful of kinds on `origin/main` before this rule existed. A `Bash` call to
`external_review.py` should redirect its own stdout straight to the durable
canonical path in the same command (e.g.
`... > .shipwright/planning/iterate/{run_id}/external-plan-review-raw.json`)
so the write lands before the agent ever reasons about the result. **This is a
mitigation, not a guarantee** — it is agent-followed prose, not code-enforced,
and a compaction landing in the instant between a subagent returning and this
write happening can still lose the finding. For the Step 8 cascade specifically
(`spec-reviewer`/`code-reviewer`/`doubt-reviewer`), the `SubagentStop` hook
`write-review-payload-on-stop.py` (`plugins/shipwright-build/hooks/hooks.json`)
is the code-level backstop for exactly that window: it fires synchronously as
part of the subagent's own lifecycle, independent of the orchestrator's
remaining context, and salvages the raw reply directly to the SAME canonical
basename Step 8's own write targets (the table below — `spec_review_reply.json`
/ `code_review_reply.json` / `doubt_review_reply.json`) if `reviews.json`
doesn't already show the type terminal by the time the subagent stops, so a
resuming session records straight from that path with no extra copy step
(trg-3b206c08). It requires the spawn prompt to state the run_id in plain text
(SKILL.md Step 8) — the hook can only read it from the subagent's own
transcript, never from an env var (`SHIPWRIGHT_RUN_ID` is documented, in this
same repo, as unreliable for a Claude-Code-launched hook subprocess). No
equivalent hook exists for `external_review.py` (a plain CLI call, not a
Task-tool subagent) — the stdout-redirect instruction above is what closes
that window instead.

**A pass that RAN** — write the reviewer's reply to a file verbatim (raw JSON,
or the whole message with its ```json block; both are accepted) and hand it over:

```bash
uv run "{shared_root}/scripts/tools/record_review_pass.py" record \
  --project-root "{project_root}" --run-id "{run_id}" \
  --review-type {self|plan|spec|code|doubt|external_code|plan_internal|architecture_internal} --status completed \
  --from {self-review|spec-reviewer|code-reviewer|doubt-reviewer|external-review-json|external-prose} \
  --payload-file "{project_root}/.shipwright/planning/iterate/{run_id}/{canonical basename for this --review-type — table below}" \
  [--model-tier {resolved review tier}] [--provider openrouter] [--marker-status completed]
```

`--model-tier` is **required** for the three review-role passes (`spec`/`code`/`doubt`, the `review` tier) and for `plan_internal`/`architecture_internal` (both the `plan_review` tier) — the value resolved in §F, same one passed at the spawn (see "Model tier" above; each internal-arm pass's own invocation shape is the table row below, not this template). Omit it for `self`/`plan`/`external_code`, which are not Agent-tool spawns — and for a row recorded with **`--transport codex`** (the driving harness could not spawn an independent Agent-tool subagent; see `shared/prompts/codex_review_dispatch.md`), which also omits `--model-tier`: the row carries no legal Claude tier, and the floor verifier already exempts a `codex`-transport row rather than reading one.

For `external-review-json`, the recorder reads the payload once, then derives
both findings and each reviewer verdict from that in-memory snapshot. It stores
the validated pair on the authoritative review row and writes the companion
marker from that same pair. An operator's `--contradiction-resolution` is stored
beside the verdicts, so `repair-markers` cannot lose the decision. A current envelope
must be `glm`/`openai`, `glm`/`opus` (under `--driver codex`), or the
now-historical `deepseek`/`openai`; an implicit historical envelope remains
readable as `gemini`/`openai`. A completed current
marker without both verdicts blocks.
Record and marker status are bound: a completed record can only write or repair
a completed marker, while a skipped marker cannot carry reviewer evidence.

| Pass | `--review-type` | `--from` | canonical basename (`.shipwright/planning/iterate/{run_id}/…`) | payload |
|---|---|---|---|---|
| Step 7 Self-Review | `self` | `self-review` | `self-review-payload.json` | `{"items":[{"name","verdict":"pass\|fail\|n/a","note"}]}` — one entry per checklist item |
| External plan/iterate review (Branch A) | `plan` | `external-review-json` | `external-plan-review-raw.json` | `external_review.py` stdout, verbatim. Add `--marker-status` |
| `spec-reviewer` (Stage 1, HARD-GATE) | `spec` | `spec-reviewer` | `spec_review_reply.json` | the subagent's reply verbatim (`{stage, verdict, spec_citations[]}`). Must be `completed` before a `completed` `code` row |
| Internal `code-reviewer` (Stage 2) | `code` | `code-reviewer` | `code_review_reply.json` | the subagent's reply |
| `doubt-reviewer` (Stage 3) | `doubt` | `doubt-reviewer` | `doubt_review_reply.json` | the subagent's reply |
| External code cascade | `external_code` | `external-review-json` | `external-code-review-raw.json` | `external_review.py` stdout. Add `--marker-status` |
| Internal Plan Review (medium+, before Branch A/B/C) | `plan_internal` | `none` (no adapter matches `opus-plan-reviewer`'s shape) | — (no payload file) | metadata-only — `--recorded-by opus-plan-reviewer --model-tier {resolved}`, no `--payload-file`. Findings live in the iterate spec's `## Internal Plan Review` section, not this row |
| Internal Architecture Review (medium+, always-and-first, before Branch A/B/C) | `architecture_internal` | `none` (no adapter matches `architecture-internal-reviewer`'s shape) | — (no payload file) | metadata-only — `--recorded-by architecture-internal-reviewer --model-tier {resolved}`, no `--payload-file`. A separate fresh-context agent, not `opus-plan-reviewer` — spawned over the architecture brief + spec, never the plan, to escape the plan's own reasoning frame. Findings live in the iterate spec's `## Internal Architecture Review` section, not this row |

**The basename column is enforced, not advisory** — `lib.review_payloads.CANONICAL_PAYLOAD_BASENAMES`
is the single source of truth `record_review_pass.py record` validates
`--payload-file` against (exit 2 on a mismatch); this table must always
restate that dict's values verbatim, never invent its own (trg-3b206c08).
**One name per kind, not per round:** when a pass loops (a Stage 1 REJECT
re-run, an external `revise` verdict), the canonical file holds only the
LATEST round — it is overwritten, never suffixed (`-round2`, …); the
recorded row is what persists the outcome, an earlier round's raw file is
disposable scratch once superseded.

**A pass that did NOT run** must say so with its closed-vocabulary code (and may
name the rule in a disposition — a bare "skipped" is rejected):

```bash
uv run "{shared_root}/scripts/tools/record_review_pass.py" record \
  --project-root "{project_root}" --run-id "{run_id}" \
  --review-type doubt --status {not_run|not_applicable} --reason-code diff-below-threshold \
  --disposition "docs-only diff; the doubt pass is conditional per iteration-reviews.md"
```

`not_applicable` when the phase matrix says the pass does not apply at this
complexity or change shape; `not_run` when it applied but was skipped (opt-out,
missing keys, degraded provider).

**`--reason-code` — REQUIRED on every `not_run` / `not_applicable` row (`record` and `close-missing`).**
One code from the closed `review_not_run` vocabulary in `shared/scripts/lib/reason_codes.py`
(`unavailable`, `trivial-auto`, `delegated-to-orchestrator`, `diff-below-threshold`,
`complexity-below-threshold`, `user-opt-out`, `config-disabled`, `missing-keys`, `no-spawn-site`).
Given alone it supplies a rule-naming disposition; given with `--disposition` both are stored. A
completed pass has no code, and a code outside the vocabulary is refused at the CLI. F11 refuses a
skipped row without one at every complexity. F11 verifies the run being finalized; a record
written before this rule carries codeless legacy rows and would fail if it were re-verified.

- **Trivial:** record `self` (always), then close everything else with ONE command —
  `uv run "{shared_root}/scripts/tools/record_review_pass.py" close-missing --project-root
  "{project_root}" --run-id "{run_id}" --status not_applicable --reason-code trivial-auto`.
  Any other closed code is accepted too, when a more specific one applies.
- **Small and up:** each type names a code that fits IT — `trivial-auto` is refused. The gate checks
  that a code is present and is not the trivial default; which code fits is the reviewable claim in
  the diff — codes are context-free by decision (no type-to-code matrix in the verifier), so
  `delegated-to-orchestrator` / `no-spawn-site` describe the campaign-runner context only and are
  never to be read as approval. Likewise `self`'s "evidence" is attribution (`recorded_by` /
  `provider`), not proof the Self-Review was done. `record --force` rebuilds a row, so a forced
  rewrite of a skipped row must pass its `--reason-code` again. The usual ones:
  `complexity-below-threshold` (`plan`, `plan_internal`, `architecture_internal` below medium),
  `diff-below-threshold` (`code`/`spec`/`doubt`/`external_code` with no risk flag and a small diff),
  `user-opt-out` / `config-disabled` / `missing-keys` (an external pass the operator, config or keys
  ruled out), `delegated-to-orchestrator` / `no-spawn-site` (campaign runner, below).

### Campaign sub-iterate rows

The sub-iterate-runner subagent carries the `Agent` tool, so it performs
`self`, `plan` and `external_code` **and** spawns both internal-arm reviews
(`plan_internal`, `architecture_internal`; Step 3.5) and the internal cascade
(`spec` → `code` → `doubt`; Step 3.7) itself, each with the resolved tier passed
explicitly. **Who did the work decides the name**
(`agents/sub-iterate-runner.md` Step 3.7 carries the actor table): a row is
`completed` only for a pass whose own subagent returned. The `not_run` rows
below are the **fallback** for a runner whose spawn cannot happen (the `Agent`
tool unavailable, erroring or denied at runtime) — the orchestrator's `3f-bis`
then runs the cascade and promotes `spec`/`code`/`doubt` with `--force`
(`plan_internal`/`architecture_internal` are never promoted). Each `…` below
stands for the invocation
prefix, i.e. `uv run "{shared_root}/scripts/tools/record_review_pass.py" record
--project-root "{project_root}" --run-id "{run_id}"` — so `…` already includes
`record`, and the lines below continue from there:

```bash
# the external run — under its OWN name, never as `code`.
# `--from`/`--payload-file` are NOT optional: a row recorded without a payload
# carries findings_count 0 and is indistinguishable from a fabricated one.
… --review-type external_code --status completed \
  --from external-review-json \
  --payload-file "{project_root}/.shipwright/planning/iterate/{run_id}/external-code-review-raw.json" \
  --provider openrouter --marker-status completed

# …or, when it did not run. `not_run` REQUIRES a --reason-code (a disposition is
# optional), and the marker vocabulary is narrower than the result-JSON one —
# `skipped_diff_below_threshold` is a valid result.json status but NOT a valid
# --marker-status.
… --review-type external_code --status not_run --reason-code {config-disabled|user-opt-out|missing-keys|unavailable} \
  --disposition "{the rule that applies, e.g. external_code_review.enabled is false for this project}" \
  --marker-status "{skipped_user_opt_out | skipped_config_disabled}"  # omit for missing-keys / unavailable

# the internal cascade when the runner SPAWNED it — one call per stage, the
# SKILL.md Step 8 shapes with the Stage payload file each reply was written to.
# Capture `reviewed=$(git -C "{project_root}" rev-parse HEAD)` BEFORE the spawn and use that value:
# a SHA taken at record time would credit a fix the reviewer never saw.
# (`spec_review_reply.json` / `code_review_reply.json` / `doubt_review_reply.json`):
… --review-type spec --status completed --from spec-reviewer \
  --payload-file "{project_root}/.shipwright/planning/iterate/{run_id}/spec_review_reply.json" \
  --recorded-by spec-reviewer --model-tier {review_tier} \
  --verdict pass --reviewed-commit "$reviewed"
# (`code`: --from code-reviewer; `doubt`: --from doubt-reviewer, or
#  `--status not_applicable --reason-code diff-below-threshold` when Stage 3 did not apply.
#  Every completed one carries `--verdict pass --reviewed-commit <HEAD when the reviewer ran>`:
#  the pair 3f-bis verifies before it skips its re-review. A REJECT is never `completed`.)

# the delegated internal cascade — FALLBACK, recorded as NOT having run, when
# the runner could not spawn. Stage 1 has a row of its own and is delegated
# with the rest; omitting it leaves `spec` pending and reds the sub-iterate at F11.
… --review-type spec --status not_run --reason-code delegated-to-orchestrator \
  --disposition "blocker 1 (Agent spawn failed: tool unavailable, errored or denied at runtime): the sub-iterate-runner could not spawn the Stage-1 spec-reviewer; delegated with the rest of the cascade (ADR-029, campaign mode only)"

# `--reason-code` is load-bearing at small: F11's check_cascade_trigger refuses a
# free-text-only `code` row when a risk flag is set or the diff is > 100 lines.
… --review-type code --status not_run --reason-code delegated-to-orchestrator \
  --disposition "blocker 1 (Agent spawn failed: tool unavailable, errored or denied at runtime): the sub-iterate-runner could not spawn the cascade; delegated to the campaign orchestrator (ADR-029, campaign mode only)"

# Stage 3 cannot precede Stage 2
… --review-type doubt --status not_run --reason-code delegated-to-orchestrator \
  --disposition "blocker 1 (Agent spawn failed): Stage 3 runs only behind a Stage 2 pass, and the internal cascade did not run in this campaign sub-iterate"

# the internal plan-review arm (Step 3.5) — recorded by the runner when it
# SPAWNED opus-plan-reviewer (metadata-only, as in iteration-planning.md Step 4 item 0):
… --review-type plan_internal --status completed \
  --recorded-by opus-plan-reviewer --model-tier {plan_review_tier}
# NEVER promoted at 3f-bis: when the spawn could not happen the row stays
# `not_run` for the life of the sub-iterate (the orchestrator has no
# internal-arm spawn site), and below medium it is `not_applicable`:
… --review-type plan_internal --status not_run --reason-code no-spawn-site \
  --disposition "Agent spawn failed (tool unavailable, errored or denied at runtime) so opus-plan-reviewer did not run; the orchestrator has no internal-arm spawn site, so this row is not delegated like spec/code/doubt"

# the internal architecture-review arm — same treatment.
… --review-type architecture_internal --status completed \
  --recorded-by architecture-internal-reviewer --model-tier {plan_review_tier}
… --review-type architecture_internal --status not_run --reason-code no-spawn-site \
  --disposition "Agent spawn failed (tool unavailable, errored or denied at runtime) so architecture-internal-reviewer did not run; the orchestrator has no internal-arm spawn site, so this row is not delegated like spec/code/doubt"
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
  --status not_run --reason-code {the code that applies} --disposition "predates the per-run review record"
```

`close-missing` never closes `self` as completed (it cannot assert a pass in bulk), so record the
Self-Review first — a record closed entirely by `close-missing` fails F11 at every complexity.

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
