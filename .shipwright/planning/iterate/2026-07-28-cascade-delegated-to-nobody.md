# Iterate — the reviewer cascade gets an owner, not a forwarding address

- **Run ID:** `iterate-2026-07-28-cascade-delegated-to-nobody`
- **Intent:** BUG (Path C → F-debug)
- **Complexity:** medium (`prior_source: history`, confidence 0.85)
- **Spec Impact:** MODIFY
- **Risk flags:** `cross_component` (touches `campaign-mode.md` + campaign loop
  machinery — recomputed from the diff by `check_integration_coverage`).
  `touches_migrations` was reported by `classify_complexity` from message prose
  and is a known false positive of that classifier; no migration is touched, so
  the `down_sql` enforcement is vacuous. `risk_detectors.py` recomputes from the
  diff and is authoritative.

## 1. Problem

The constitution states the discipline as an ALWAYS rule (`constitution.md:52`):

> Review before done, in stages: spec-compliance **first** … then code quality,
> then … an adversarial pass that tries to disprove the change. **(Build Step 6
> `spec-reviewer`→`code-reviewer`→`doubt-reviewer` and iterate's review-record
> are two implementations of this one discipline.)**

The iterate lifecycle does not implement it. Five defects, one mechanism.

**(A) Standalone: the delegation has no terminus.** `iteration-reviews.md:152`
describes the cascade's execution as something that happens *when the runner
contract delegates it* — "to the orchestrator (campaign mode) or the parent
SKILL.md (standalone)". `sub-iterate-runner.md:169` names the standalone target
as "the parent SKILL.md lifecycle Step 8". `SKILL.md:175-177` is that step in
full: *"Step 8: Full Code Review (conditional) — See `references/iteration-reviews.md`
for trigger rules."* The pointer returns to its own origin. In standalone mode
there is no runner and no orchestrator, so the delegation names the same session
that issued it — and a self-delegation reads as somebody else's job.
`sub_iterate_runner_contract.schema.json:76` blesses this with a legal status
value, `delegated_to_skill`.

**(B) Campaign: the named owner has no step, and could not act in time if it
did.** `campaign-mode.md:16-18` promises "the orchestrator spawns it in parallel
with the runner, after Build completes". The executable loop (`campaign-mode.md`
§75-172) is `3a next` → `3c spawn runner` → `3d wait for DONE` → `3e parse` →
`3f record` → `3g merge` → `3i continue`. **There is no review step.** Nor could
one sit where the prose puts it: the orchestrator blocks at `3d` on the runner's
*terminal* DONE marker, which the runner emits only after Step 4 Finalization —
i.e. after F6 commit and Step 5 push. Reviews are specified to run before commit.
The window the prose describes does not exist.

**(C) The runner's only cascade marker labels the external review as the
internal pass.** `sub-iterate-runner.md` Step 3.7: item 1 delegates the internal
cascade, item 2 runs `external_review.py --mode code`, and item 3 then writes
`mark-review-state.py --review-type code --status completed`. The status
describes item 2's outcome under item 1's name.

**(D) The runner records almost nothing, so the gate's pressure lands on
improvisation.** The runner calls `record_review_pass.py` exactly once — Step 3.5,
`--review-type plan`. `self` (3.6), `code`, `doubt` and `external_code` get no
row; Step 3.7 writes only the legacy marker. Its own F6-verify runs the same
`check_review_record`, which STOPs on any `pending` type. So the runner *cannot*
push without inventing rows the contract never taught it to write — and item 3
models the wrong label for exactly the row it is under most pressure to close.

**(E) The Stage-1 HARD-GATE is structurally unrecordable.**
`REVIEW_TYPES = ("self", "plan", "code", "doubt", "external_code")`
(`review_record_schema.py:45`) has no `spec` row. The artifact whose stated
purpose is that "an empty Review row must mean *genuinely not run*, never
*nobody wrote it down*" cannot represent the one stage the constitution calls
first and blocking.

### What this composes to at medium+

`iteration-reviews.md:169-171` — "the spec-compliance and doubt roles are **not**
cascaded to external LLM providers". The F11 floor
(`review_record_check.py:61`) accepts `code` **or** `external_code`. So the
honest escalation route added by #476 — `code = not_run` + external carries the
pass — is *also* the route on which the HARD-GATE and the adversarial pass
vanish with no counterpart, at a green gate.

**Correction to an earlier reading of mine:** campaign sub-iterates are not
silently unreviewed. Since #476 the floor bites, and since #428 the `pending`
check bites — a medium+ sub-iterate that runs neither review **fails** F6-verify.
The defect is not a silent hole but an under-specified contract that fails
closed and then invites the wrong repair.

## 2. F-debug — the four phases

1. **Read Error.** No exception; the symptom is behavioural. Observed: two
   consecutive medium+ standalone iterates finished with no internal cascade
   (operator, 2026-07-27 22:20; and the run recorded in
   `iterate-2026-07-27-project-granularity-basis`, whose `code`/`doubt` were
   first booked `completed` "by substitution" and later re-booked `not_run`).
   Expected: at medium+ the cascade runs, or its absence names a real blocker.
2. **Reproduce.** Deterministic, no UI: the five defects are each assertable —
   §6 lists one failing test per defect. All five fail on `origin/main@e21a7b71`.
3. **Recent Changes.** **Not a regression.** `git log -S` puts (A) and (B) in
   `f6a14fc7 feat(iterate): runner contract mandates reviews (ADR-029)` — the
   commit that *mandated* the reviews introduced the delegation without a
   terminus — and (C)/(D) in `578370ca` (#428), which upgraded Step 3.5 to
   `record_review_pass.py` and left Step 3.7 on the legacy marker.
4. **Component-Boundary Instrumentation.** The boundary is the hand-off from
   *deciding* a review applies to *performing* it. Every artifact on the
   deciding side is present and correct (trigger rules, phase matrix, floor,
   record schema). Every artifact on the performing side names a different
   document as the actor.

**Root cause (one sentence).** The internal cascade is specified only as an act
of *delegation* and never as an act someone performs, so in both modes its owner
is a document rather than an executable step — and because it has no owner, its
absence is what the record, the marker and the floor were each left to
approximate.

## 3. Decision

Give the cascade an owner where one can exist today, and stop the record from
approximating. **Revised after the external plan review** — see §4a.

- **AC1 — Standalone owns it.** `SKILL.md` Step 8 states that this session runs
  the cascade itself (it has the `Agent` tool), naming the three stages and the
  Stage-1 block, and states explicitly that it runs **before F6 (commit)** — the
  step already sits there, but its placement was never load-bearing in the text.
  No forwarding address.
- **AC2 — The delegation prose is scoped.** The "no `Agent` tool → delegated"
  sentence in `SKILL.md:203`, `iteration-reviews.md:152-154`,
  `campaign-mode.md:15-17` and `sub_iterate_runner_contract.schema.json:76`
  carries an explicit campaign-only marker. `iteration-reviews.md`'s cascade
  section stops being conditioned on the runner contract.
- **AC4 — The runner records what it did, under the right name.** Step 3.7 item
  3 becomes `record_review_pass.py --review-type external_code` for the external
  run; the delegated internal pass is recorded `--review-type code --status
  not_run` with a disposition naming the **capability** limit. Steps 3.6/3.7 gain
  a **status-transition table**: per review type — who performs it, which status
  that actor may write, and what disposition is required. The runner may never
  mark internal `code` or `doubt` completed because the external review ran.
- **AC5 — `delegated_to_skill` is deprecated, not deleted.** Removing an enum
  value invalidates historical `result.json` artifacts. The value stays and its
  description says it is legacy and invalid for new runs;
  `delegated_to_orchestrator` stays and is documented campaign-only.
- **AC6 — The floor names what the substitution costs.** `review_record_check.py`
  keeps `code` OR `external_code` (re-encoding the phase matrix in a verifier is
  a rejected design, and that rejection stands). When the floor is satisfied by
  `external_code` alone at medium+, the message states that Stage-1
  spec-compliance and Stage-3 doubt have **no external counterpart**, so the
  substitution buys code-quality cover only.
- **AC7 — `campaign-mode.md` stops promising a step that does not exist.** The
  "orchestrator spawns it in parallel with the runner, after Build" claim is
  replaced by the truth: the orchestrator regains control only at the runner's
  terminal marker, so today the internal cascade does **not** run for campaign
  sub-iterates, and the external review carries the pass alone. The before-merge
  cascade is named as the tracked follow-up rather than described as current
  behaviour.

## 4. Alternative considered — and why not

**Give the sub-iterate-runner the `Agent` tool** (ADR-029's rejected option (a),
rejected then on token cost alone). The runner would spawn its own cascade
before its own commit, which is where reviews belong, and the campaign half
would need no orchestrator step at all. Not taken: whether a subagent may spawn
subagents at runtime is a capability claim this repo has **never measured**, and
`sub-iterate-runner.md` declares only `Read, Write, Edit, Bash, Glob, Grep`.
Building a contract on an unmeasured capability is the failure mode §2 exists to
prevent. Recorded as the first thing the follow-up must measure.

## 4a. What the external plan review changed

Two providers (gemini, openai via OpenRouter), both `revise`, 11 findings. The
plan as written was wrong in one structural way and unsafe in three others.

**The structural error (openai #1, high).** The original AC3 put the campaign
cascade at a new loop step `3f-bis`, after the runner returns. But the runner's
own F6-verify runs `check_review_record`, which STOPs on any `pending` type —
so the branch can never reach the orchestrator with `code`/`doubt` left open.
Closing them `not_run` "because delegated" then collided with the original AC6,
which declared delegation an invalid blocker. The plan could not be implemented
honestly as written.

**Resolution — and the scope cut it forces.** Delegation is not an excuse in
standalone mode, where the session *can* spawn; it is a genuine **capability
limit** in campaign mode, where the runner demonstrably cannot. AC6 now says
that, and AC4 records it that way, which is honest and passes. The before-merge
cascade itself (old AC3) is **deferred to a follow-up iterate**, because both
reviewers independently said its state machine must be specified before it is
built: bounded retry / abort (gemini #2, openai #3), row-targeted updates rather
than file overwrite (gemini #3, openai #5), a durable Stage-1 verdict the merge
gate can inspect (openai #6), branch/ref provenance and treating reviewer text
as data not shell input (openai #8), and revalidation on the exact merged SHA
(openai #3). Shipping that under-specified, autonomously and overnight, is worse
than shipping the half that is fully specified and telling the operator what
remains. See §5.

**Accepted and applied here:** gemini #1 + openai #4 → AC5 deprecates instead of
deletes. openai #2 → AC1 states the pre-F6 placement explicitly. openai #5 →
AC4 gains the status-transition table. openai #6 → interim: the Stage-1 verdict
is carried in the `code` row's findings with `source: spec-reviewer`, so it is
inspectable before the schema gains a `spec` type. openai #7 → the integration
test composes CLI → record → verifier rather than asserting markdown order.

## 4b. The Stage-1 HARD-GATE rejected this diff — and was right

The first run of `spec-reviewer` returned **REJECT**, high severity, on the
interim promised in §4a: *"the Stage-1 verdict is carried in the `code` row's
findings with `source: spec-reviewer`"*. That was prose only. `--from` accepts a
closed adapter set (`review_payloads.ADAPTERS`) with no `spec-reviewer` route,
and every adapter hard-codes its own `source` — so an agent following the
instruction got an argparse error, and the one reachable fallback
(`--from code-reviewer`) would have stamped **Stage 2's name on Stage 1's work**:
precisely the mislabelling AC4 exists to abolish. Worse, §5's deferral of defect
(E) rested on that interim carrying the verdict, and nothing carried it.

The same failure shape as the bug being fixed — an instruction whose executable
path does not exist — reproduced inside the fix for it. That is the argument for
the cascade in one artifact.

**Resolved by building it (AC8), not by weakening the spec.** A
`from_spec_reviewer` adapter now maps the Stage-1 reply — *first built against
the wrong payload shape; see "The second REJECT" below for the shape that
shipped* — stamps `source: "spec-reviewer"`, and carries the verdict as the
first finding so a REJECT can never record as an empty (= clean) review. Registered in `ADAPTERS`,
documented in `iteration-reviews.md`'s recording section and in SKILL.md Step 8,
pinned by three tests. Two lower-severity findings from the same pass were also
applied: the floor note no longer claims "neither ran" when `doubt` did run, and
the two deferred items are filed as triage at F3a rather than merely promised.

- **AC8 — WITHDRAWN** (see §4d). Carrying the Stage-1 verdict in the `code`
  row is unsound in every variant; the adapter and its prose were removed
  before shipping. Stage 1's absence from the record is now stated as the
  correctness gap it is.

### The second REJECT — the same mistake, one layer down

The re-review rejected AC8 too, and again correctly. My adapter read
`{verdict, findings[]}`; the `spec-reviewer` agent actually emits
`{stage, verdict, spec_citations[], summary}` with `divergence` / `spec_ref` /
`diff_location` / `kind` per entry (`{build_plugin_root}/agents/spec-reviewer.md`).
`_items` raises on a missing key, so the command I had just written into
SKILL.md would have failed on every real Stage-1 reply. The three tests were
green only because they hand-built the invented shape — *"the integration proves
a shape nobody is told to produce"*, which is the failure the diff's own drift
guard is named after.

The tell was in this run's own transcript: to make the path work I had asked my
Stage-1 reviewer, in its prompt, to return `{"verdict", "findings"}` — I bent
the producer to fit the adapter instead of the reverse. Twice now the same
defect class (an instruction with no executable path) survived my self-review
and died at the gate.

**Resolved:** the adapter now reads `spec_citations` (with `findings` as a
back-compat alias), maps `divergence`→text, appends `spec_ref` to the text,
`diff_location`→`file`, `kind`→`category`, and defaults every citation to `high`
on a REJECT (citations carry no severity of their own; a REJECT blocks Stage 2,
so none of its citations is minor). The regression test is driven by parsing the
```json example **out of `spec-reviewer.md` itself**, so the adapter and its
producer cannot drift apart silently. The per-pass table in
`iteration-reviews.md` gained the missing `spec-reviewer` row, and the payload
shape is now written down next to the `--from` value rather than only in a
docstring.

### Stage 2 found the write-once collision the whole design rested on

`spec-reviewer` PASSed on the third round; `code-reviewer` then returned 13
findings, one **high**. Both Stage 1 and Stage 2 were documented as writing the
**same** `code` row — and that row is immutable. The second write raises, and
`--force` replaces the entry wholesale rather than merging, so whichever stage
recorded first would be silently deleted. Since a REJECT loops until PASS, the
normal path always ends at Stage 2, which meant AC8's adapter was inert exactly
where §5 leans on it.

**Resolved:** the `code` row is written **once**, by the stage the cascade ended
at — `--from spec-reviewer` when an unresolved Stage-1 REJECT stops the run,
`--from code-reviewer` on the normal path. Nothing is lost, because *Stage 2
having run is itself the evidence Stage 1 passed*: Stage 1 blocks Stage 2. Both
stages are named in `--recorded-by`. Documented in SKILL.md Step 8 and as a
table in `iteration-reviews.md`, pinned by a CLI test that records `code` twice
and asserts the second write fails.

Two further **medium** correctness findings were the same defect class again —
a third and fourth instance in one run. The adapter raised `AttributeError`
(not `ReviewFindingsError`) on a verdict-less payload, escaping the CLI's
`except` and breaking its JSON-on-stdout contract; and the three relocated
campaign commands carried `record` **twice** once the legend was expanded, so
every one of them would have exited 2. Both fixed and pinned. The remaining
nine findings (severity coercion before fallback, error naming the deprecated
alias, unbounded composed strings, a control-flow simplification, harness
duplication that leaked a temp file per run, dead `sys.path` inserts, an
unanchored fixture regex, a runner command fragment, and a drift guard whose
assertions were true before the fix) were all applied.

## 4d. Stage 3 + external review killed AC8 — and that is the right outcome

`doubt-reviewer` returned two **high** doubts and the external review (GPT; the
Gemini leg came back `unavailable`, so this was a one-provider pass) a third,
all on the same mechanism — carrying the Stage-1 verdict in the `code` row:

1. **The write-once rule required knowing the future.** A Stage-1 REJECT *is*
   terminal from inside the moment it happens, so an agent records
   `code --from spec-reviewer`. Fix, re-review to PASS, Stage 2 runs → immutable
   collision. Both exits are wrong: `--force` erases the Stage-1 REJECT (the
   loss the rule existed to prevent), or the record permanently claims a cascade
   blocked at Stage 1 for a diff Stage 2 actually passed. **This run took
   exactly that path twice.**
2. **A Stage-1-terminal row lies to the floor.** `--status completed` makes
   `_code_review_floor` count it as "a code review HAPPENED" and suppresses the
   substitution note — for a cascade whose own table says "Stage 2 provably
   never ran". `--status not_run` zeroes the findings, discarding the verdict
   and every citation the adapter had just built. Neither status does what the
   design claimed.
3. **The verdict was never validated.** `{"verdict": "ERROR"}` recorded as a
   non-blocking review, bypassing the HARD-GATE entirely.

**Withdrawn, not patched.** `review_spec_stage.py`, the `ADAPTERS` entry, its
test module and every line of prose routing Stage 1 into the `code` row are
gone. The reason it is safe to remove is the reason it was never needed: a
REJECT loops until PASS (`spec-reviewer.md` → "Re-review loop") and an
unresolved REJECT never reaches F6, so **every run that ships ended at Stage
2** — the adapter had no shipping caller. Shipping it would have put a
mechanism in the repo that can satisfy the code-quality floor without a code
review, which is the bug class this iterate exists to abolish.

The honest consequence: **defect (E) is a correctness gap, not a visibility
one**, and §5 now says so. `iteration-reviews.md` carries the same statement
where the recording rule is read, pinned by a test.

Also applied from the same round: the campaign `external_code` command was
split into its `completed` and `not_run` forms (the single form omitted the
`--disposition` that `not_run` requires, and offered `skipped_diff_below_threshold`
as a `--marker-status`, which is a result-JSON value the marker vocabulary
rejects — **two more exit-2 instructions**, the fourth and fifth of this run);
the runner's actor table stopped listing `skipped_*` in a column headed *status
the runner may write*; `campaign-mode.md`'s gap sentence was scoped to
runner-spawned sub-iterates, since a hand-run `--sub-iterate-id` invocation is a
standalone session that does spawn the cascade; and Step 8 no longer reads as a
completeness guarantee it cannot give.

**Left open, deliberately, with the demonstration recorded:** the floor accepts
an `external_code` row carrying no evidence at all (`--from` omitted →
`findings_count: 0`, `provider: null`), and `check_review_record` skips entirely
when the iterate entry is missing. Both are pre-existing fail-open paths this
diff did not introduce and cannot close without changing the floor's contract.
Filed as triage with the doubt-reviewer's constructed counter-example.

## 5. Out of scope — and why

Both items are filed as triage follow-ups carrying this analysis, not dropped.

**(E) The missing `spec` review type — a CORRECTNESS gap.** Adding a sixth
entry to `REVIEW_TYPES` is a schema change: `validate_record` requires every
type to be present, so every existing `reviews.json` becomes schema-invalid the
moment the tuple grows, and the webui Mission contract reads the same file. That
needs a `schema_version` bump and a cross-repo decision the operator is not
available to take.

An earlier draft of this section called (E) merely a *visibility* gap on the
grounds that AC8 would carry the Stage-1 verdict in the `code` row. AC8 is
withdrawn (§4d), so that justification is gone: after this iterate the Stage-1
pass **runs** in standalone mode but the record cannot **prove** it ran — a
`code` row sourced `code-reviewer` is byte-identical whether Stage 1 passed
first or was never spawned. That is the not-run-versus-not-recorded distinction
the record exists to abolish, at the one stage the constitution calls first and
blocking. It is filed as a correctness gap and should be weighed as one.

**The campaign before-merge cascade (old AC3).** Deferred per §4a. Until it
lands, campaign sub-iterates at medium+ ship with the **external** review only —
Stage-1 spec-compliance and Stage-3 doubt do not run for them, and AC7 makes
`campaign-mode.md` say so instead of claiming otherwise. This is a real residual
gap, not a closed one. The follow-up must, in order: (1) measure whether a
subagent can spawn a subagent — if yes, §4's alternative is simpler than any
orchestrator step; (2) if no, specify the `3f-bis` state machine against the
five findings listed in §4a before writing any prose.

## 6. Affected Boundaries

| Boundary | Producer | Consumer | Probe |
|---|---|---|---|
| `reviews.json` | `record_review_pass.py` | `review_record_check.py`, webui Mission | round-trip, §7 |
| runner `result.json` | sub-iterate-runner | `campaign_progress.py`, loop `3f record` | schema validate |
| legacy `external_*review_state.json` | `mark-review-state.py` | webui W2 | unchanged in this diff |

## 7. Confidence Calibration

- **Boundaries touched:** `reviews.json` (producer `record_review_pass.py`,
  consumers `review_record_check.py` + webui Mission) and the runner
  `result.json` contract schema. Neither serialized *shape* changed: no field
  added or removed, no `schema_version` bump, no enum value deleted. What
  changed is which adapter may write a row and what a passing message says.
  `risk_detectors` on the actual diff: `cross_component` **yes**
  (`campaign-mode.md`), `io_boundary` **no**, `ci_supplychain` **no**,
  `touches_build` **no** — so `classify_complexity`'s `touches_migrations` was
  a message-prose false positive, and its `down_sql` enforcement is vacuous.

- **Empirical probes run:**
  - **PROBE1 (the Stage-1 REJECT, reproduced):** `git show <merge-base>:shared/scripts/lib/review_payloads.py`
    → `ADAPTERS` held six values, none of them `spec-reviewer`; feeding that
    tuple to argparse rejects `--from spec-reviewer` with *invalid choice*.
    The instruction SKILL.md was about to ship really was unexecutable. **Fixed
    and re-probed:** `build_findings("spec-reviewer", payload)` now returns
    findings all stamped `source: "spec-reviewer"`.
  - **PROBE2 (a REJECT cannot read as clean):** `{"verdict":"REJECT","findings":[]}`
    → 1 finding, not 0. Without the verdict-as-finding rule an itemless REJECT
    would have recorded byte-identically to an honest clean review.
  - **PROBE3 (the honest campaign shape ships):** the five rows the fixed
    contract prescribes, written by the **real CLI** as a subprocess, pass
    `check_review_record` at `complexity=medium`. The fix does not push runners
    back toward mislabelling to get green.
  - **PROBE4 (the floor still bites):** the same record with `doubt` unrecorded
    fails the gate naming `doubt` — which is what forces the runner to record
    rather than invent.
  - **PROBE5 (laundering is refused):** `--disposition "delegated"` is rejected
    by `disposition_ok` (one word, < 12 chars), so the capability limit must be
    spelled out where a reader sees it.
  - **PROBE6 (the note does not over-claim):** with `doubt = completed` the
    passing message says "Stage-1 did not run (Stage-3 did)", not "neither ran".
  - **PROBE7 (`reviews.json` → webui Mission, the §6 boundary; raised by the
    Stage-1 reviewer):** carrying the verdict as the first finding changes what
    a consumer counts. Measured: a Stage-1 **PASS with zero citations** yields
    `findings_count: 1` on the `code` row, and the verdict entry's `severity` is
    `None` (only a REJECT stamps `high`), `category: spec-compliance`,
    `source: spec-reviewer`. So a clean Stage 1 does **not** inflate any
    high-severity tally; it does make a clean row read as "1 finding" rather
    than "0". That is the intended trade — a row that reads `0` is
    indistinguishable from Stage 1 never having run, which is the failure this
    record exists to abolish. The `findings[].source`/`category` fields are what
    a consumer should group on, and the webui contract already carries both.

- **Confidence-pattern check:** *depth* — the root cause was probed at the
  boundary it actually crosses (prose → CLI → record → verifier), and PROBE1
  shows the same defect class recurring inside the fix, caught by the gate this
  iterate installs. *breadth* — all seven ACs have at least one guard; the two
  deferred items are named, not silently dropped. *integration composition* —
  `cross_component` fires on `campaign-mode.md`, so
  `test_review_record_campaign_shape.py` composes the real CLI, the real record
  and the real verifier rather than asserting markdown order (this was an
  external-plan-review requirement, openai #7).

- **Where confidence is genuinely limited:** the standalone half is enforced by
  *prose that agents follow*, not by a gate that can prove a subagent was
  spawned. A prompt-driven lifecycle cannot structurally prove who ran a
  review — the F11 floor proves only that *a* review happened. This iterate
  narrows the gap (the record can no longer claim the internal pass ran when it
  did not) without closing it, and says so rather than implying otherwise.

## 8. Test Completeness Ledger

**Principle: testable ⇒ tested.** 6 acceptance criteria (AC1, AC2, AC4–AC7 —
AC3 was cut §4a, AC8 withdrawn §4d); 28 behaviours enumerated. 0 testable-but-untested.

*Rows 7 and 22 named tests that the mid-run rename and split had already
removed, and two guards had no row at all — caught by the Stage-1 reviewer, not
by `check_test_completeness_ledger`, which validates classification and counts
but never resolves a test name. An evidence column citing tests that do not
exist is this iterate's own defect class, in the artifact recording the fix.*

| # | Behaviour | Class | Evidence |
|---|---|---|---|
| 1 | Step 8 names the actor ("this session spawns") | tested | `test_step_8_says_this_session_spawns_the_cascade` |
| 2 | Step 8 names all three stages | tested | `test_step_8_names_all_three_stages` |
| 3 | Step 8 states HARD-GATE + pre-F6 placement | tested | `test_step_8_states_the_stage_1_block_and_pre_commit_placement` |
| 4 | SKILL.md ADR-029 sentence carries a campaign marker | tested | `test_skill_campaign_paragraph_scopes_the_adr_029_sentence` |
| 5 | Cascade section not conditioned on the runner contract | tested | `test_cascade_section_is_not_conditioned_on_the_runner_contract` |
| 6 | Reference names the standalone owner explicitly | tested | `test_cascade_section_names_the_standalone_owner_explicitly` |
| 7 | Actor table assigns `external_code` to the runner, `code`/`doubt` away from it | tested | `test_runner_assigns_the_external_run_and_the_internal_pass_to_different_rows` |
| 8 | Runner never writes `code=completed` | tested | `test_runner_never_marks_internal_code_completed_from_an_external_run` |
| 9 | Runner carries a status-transition table with actors | tested | `test_runner_carries_a_status_transition_table` |
| 10 | `delegated_to_skill` retained (back-compat) | tested | `test_delegated_to_skill_is_retained_for_backward_compatibility` |
| 11 | Delegation statuses documented with scope + deprecation | tested | `test_delegated_statuses_are_documented_with_their_scope` |
| 12 | campaign-mode drops the impossible parallel claim | tested | `test_campaign_doc_drops_the_impossible_parallel_claim` |
| 13 | campaign-mode states the residual gap | tested | `test_campaign_doc_states_the_residual_gap_honestly` |
| 14 | **Contract-shaped record passes the floor (CLI→record→verifier)** | tested **(category: integration)** | `test_contract_shape_written_by_the_cli_passes_the_gate` |
| 15 | Passing message names the substitution cost | tested | `test_the_gate_still_reports_what_the_substitution_costs` |
| 16 | No note when the internal cascade actually ran | tested | `test_no_substitution_note_when_the_internal_cascade_actually_ran` |
| 17 | Note does not over-claim when `doubt` ran | tested | `test_substitution_note_does_not_claim_doubt_was_skipped_when_it_ran` |
| 18 | Unrecorded `doubt` blocks the push | tested | `test_unrecorded_doubt_blocks_the_push` |
| 19 | Bare `delegated` disposition rejected | tested | `test_a_bare_delegated_disposition_is_rejected` |
| 20 | CLI has no provenance; contract forbids `code=completed` | tested | `test_runner_may_not_close_code_completed_and_the_contract_says_so` |
| 21 | Runner's pointer and its target are pinned as a pair | tested | `test_the_campaign_recording_commands_exist_where_the_runner_is_sent` — asserts the Step 3.7 pointer AND the three commands at the target, so deleting the pointer cannot stay green |
| 22 | Contract table and integration fixture agree (drift guard) | tested | `test_contract_table_lists_every_row_this_test_writes` (×5) |
| 23 | The `code` row cannot be written twice (immutability, live CLI) | tested | `test_the_code_row_cannot_be_written_twice` |
| 24 | The `code` row is Stage 2's and Stage 1 has none | tested | `test_the_code_row_is_stage_2s_and_stage_1_has_none` |
| 25 | The Stage-1 evidence gap is stated as CORRECTNESS, not cosmetic | tested | `test_the_stage_1_evidence_gap_is_stated_as_correctness_not_cosmetic` |
| 26 | Step 8 does not promise more than the cascade sees | tested | `test_skill_step_8_does_not_promise_more_than_the_cascade_sees` |
| 27 | The actor table never lets the runner close an internal stage `completed` | tested | `test_the_table_never_lets_the_runner_close_an_internal_stage_completed` |
| 28 | `docs/guide.md` Ch. 6 + Ch. 8 describe the corrected behaviour | untestable — `covered-by-existing-test` | the behaviour the prose describes is pinned by `test_review_cascade_decoupled.py` + `test_review_cascade_owner.py`; the guide is narrative and carries no gate of its own |
