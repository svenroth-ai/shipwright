# Investigation: dependency-aware, parallel campaign scheduling

**Run:** `iterate-2026-09-20-campaign-dag-scheduler` · **Type:** investigation / design proposal · **Spec Impact:** NONE (no code shipped this run; framework planning artifact, no product FR)

## Question posed

Today a campaign's sub-iterates carry one campaign-wide `branch_strategy`
(`serial`/`stacked`/`independent`/`single-branch`) plus free-text dependency
notes in each sub-iterate's own spec prose. There is no structured
per-sub-iterate `depends_on` and no scheduler that computes which sub-iterates
are launchable now vs. must wait.

Sven's actual goal is broader than "add a DAG": at the start of a campaign, he
wants to clarify with the operating session what is actually needed, then have
the run do serially what must be serial and in parallel what can be parallel —
with guided and autonomous execution mixed per sub-iterate, escalating to him
only where it needs him. A structured DAG is one candidate mechanism for that,
not a foregone conclusion — this document verifies the premise and sketches
options rather than committing to an implementation.

## Finding 1 — the original serial-merge rationale is verifiably stale

`campaign-mode.md`'s own "Why interleaved-serial" section states the reason
interleaved-serial (PR #246, merged `2ec6e2be`, 2026-06-13) replaced
build-all-then-drain: **every sub-iterate regenerated the same *derived*
artifacts** (`shipwright_events.jsonl`, `triage.jsonl`, compliance MDs, the
dashboard). Building all PRs before merging meant siblings never saw each
other, so every merge had to 3-way-merge and regenerate those snapshots
against an advancing `origin/main` — recurring merge theater. Interleaved-serial
fixed it by keeping only one open campaign PR at a time.

That premise no longer holds, verified against the current code rather than
assumed:

- **`shared/scripts/lib/derived_snapshots.py`** (added by
  `iterate-2026-07-27-derived-snapshots-off-branch`, PR #480 — six weeks after
  #246) now lists **12 paths** — `shipwright_test_results.json`, the compliance
  MDs, the dashboard, `session_handoff.md`, etc. — that **must never enter an
  iterate commit at all**. They are reset to `HEAD` on integrate
  (`restore_derived_to_head`) and enforced as an F11 hard error
  (`check_no_derived_snapshots_committed`). The module's own docstring names
  the reason: "every iterate rewrites the same twelve shared paths regardless
  of what it changed, so N parallel iterates collide N(N-1)/2 times on files
  carrying no information about any of the changes." **There is nothing left
  for sibling branches to 3-way-merge or regenerate for this class of file —
  the collision surface #246 was built to avoid has been deleted, not just
  reduced.**
- The **two files that do still ship per-tree** — `shipwright_events.jsonl` and
  `.shipwright/triage.jsonl` — are deliberately excluded from that list because
  they are append-only logs. `.gitattributes` declares
  `merge=union` for both (git's native line-union strategy), and
  `shared/scripts/tools/resolve_churn_conflicts.py` runs a post-merge
  dedup + validation pass over the unioned result. Per the `.gitattributes`
  comments, this machinery shipped `iterate-2026-06-07-scaffold-churn-merge-machinery`
  (`.shipwright/triage.jsonl` itself tracked since campaign
  `2026-06-05-track-triage-jsonl`) — i.e. it already existed when #246 was
  decided on 2026-06-13, but interleaved-serial's "only one open PR" model made
  it moot at the time because nothing else could collide anyway. It has been
  production far beyond a single campaign since: `feedback_one_loop_per_repo_is_false`
  recorded three campaigns running **concurrently** on 2026-09-10 (15 PRs
  merged from ~9 distinct branches) with no invented serialization rule
  standing in the way, and no report of an events/triage collision from that
  day.

**Conclusion: the specific failure mode interleaved-serial exists to prevent
is gone.** What interleaved-serial still buys today is narrower than its
original rationale: each unit branches from a **freshly-fetched
`origin/<default>`** (`resolve_base_branch`), so a dependent unit's build
naturally starts after its dependency merged. That property is worth keeping —
it is the actual safety mechanism this proposal must generalize, not the
merge-theater argument, which is now historical.

## Finding 2 — today's scheduler has zero dependency awareness

`shared/scripts/lib/autonomous_loop.py::cmd_next` is a strict FIFO: it scans
`state["units"]` in list order and hands the caller the **first** `pending`
unit, marks it `in_progress`, and returns. There is no concept of "which units
are ready" — only "which unit is next in the list." `branch_strategy` only
controls the **base ref** each unit resolves to (`serial` = always fresh
`origin/<default>`); it says nothing about *when* a unit may start.

Sub-iterates themselves are rows in a markdown table inside `campaign.md`
(`id`/`slug`/… columns), parsed by `campaign_status.parse_campaign_skeleton`
into `status.json`'s `sub_iterates` list. Today's only way to express "R4 needs
R2 and R3" is prose inside R4's own spec file — invisible to `cmd_next`,
`campaign_status.py`, and the WebUI alike.

The orchestrator's per-unit loop (`campaign-mode.md` steps 3a–3i) currently
assumes exactly one `in_progress` unit at a time: worktree guard → spawn →
wait for `DONE` → record → review cascade (3f-bis) → merge (3g) → next.
**Correction (post-review — see Finding 4): this is not merely a bookkeeping
gap.** An earlier draft of this document claimed running multiple units
concurrently was just missing bookkeeping, reasoning that the Agent tool
already runs multiple `Task` spawns concurrently when issued in one message.
That is true of the Agent tool in general and false of this loop specifically
— campaigns share **one worktree**, not one per unit, and a real concurrency
change has to displace machinery that exists *specifically* to prevent the
exact race concurrent units would cause.

## Finding 4 — the real blocker is the shared worktree and its lock, not the scheduler

`references/campaign-worktree.md` mandates **one worktree per campaign slug**
(`$main_root/.worktrees/campaign-{slug}`), shared by the orchestrator *and
every runner it spawns* — enforced as an exact path compare in
`shared/scripts/lib/worktree_location.py` at two call sites (campaign-mode
step 3c and the runner's own Step 1.0). The session lock's stated purpose is
verbatim: *"two operators… can spawn a sub-iterate-runner whose `git checkout
-b` races the other's in the one shared directory."* **The framework already
built a lock whose entire reason for existing is to prevent the concurrency
this proposal wants to introduce.**

Compared to that, DAG-vs-waves scheduling logic is a rounding error: a
ready-set computation is roughly ten lines
(`all(state[d] == "complete" for d in deps)`); a wave/barrier model needs
about the same amount of code for a strictly less expressive result. **The
follow-up planning pass should not spend its budget on that choice** — real
parallel *building* means N checkouts on disk, a lock model that is per-unit
rather than per-campaign, and re-examining whether `restore_derived_to_head`
races siblings over the twelve derived paths once more than one is live.

## Finding 5 — a concrete corruption path in today's review-then-merge step

`campaign-mode.md` step 3f-bis computes the review diff as
`git diff "$(git merge-base origin/{default} HEAD)"...HEAD` — a bare `HEAD` of
the **shared** worktree. With two units in flight, `HEAD` is whichever branch
was checked out most recently. Run concurrently as-is, the review cascade
could review one unit's diff, then `git add reviews.json && git commit && git
push` that record onto a *different* unit's branch — producing a review
record that reads as genuine but reviewed the wrong diff, silently defeating
the one gate that can still stop delivery before merge. Two related gaps in
the same area: `autonomous_loop._reconcile_in_progress` resets **every**
`in_progress` unit on resume, so resuming a partially-parallel run would reset
live siblings, not just the crashed one; and a 3f STRICT-STOP fired while
other spawned runners are still executing has no defined cancellation
semantics (a running `Task` cannot be cancelled, yet step 4 releases the
session lock unconditionally).

## Cost note (revised — measured evidence, not assumption)

Parallel building buys wall-clock, not tokens or dollars — each concurrent
`sub-iterate-runner` (plus its review cascade) costs the same regardless of
whether it ran alongside another unit or after it. An earlier draft of this
document, and the first architecture-review pass over it (see "External
validation" below), reasoned that this made the wall-clock saving hard to
justify against the added machinery, on the assumption that campaigns already
run mostly unattended so elapsed time matters less. **That assumption is
false, measured**: Sven's most recent campaign ran **two days elapsed**,
serially, with no attempt made to identify which units could have proceeded
independently. Cycle time is a standing goal (alongside maximizing
automation — running campaigns with as little manual babysitting as
possible), not a one-off complaint. This reopens the case for real parallel
building (Increment 2) rather than deferring it — the safety issues in
Findings 4–5 are still real and still must be engineered properly, but they
are no longer a reason to decline the work, only a reason to plan it
carefully.

## Finding 3 — a reusable mechanism already exists for "guided vs. autonomous per unit"

The single-session pipeline (`SS2`, PR #342) already solved a structurally
identical problem: per-*gate* policy (`auto-default` / `orchestrator-approve` /
`hard-stop`) driven by `shared/config/gate_catalog.json` +
`shared/scripts/lib/gate_policy.py`, with constitution-locked gates that can
never be auto-answered. Extending that same vocabulary to "per-sub-iterate
merge policy" (auto-merge vs. pause-for-Sven vs. always-stop) would reuse a
tested mechanism instead of inventing a second one, and keeps the "guided and
autonomous mixed in the same run" requirement consistent with how the rest of
the framework already expresses exactly that distinction.

**Correction (post-plan-review — see the plan doc, v2): this reuse does not
actually type-check as scoped.** `gate_policy.py`'s catalog requires every
gate's `phase` to be one of a fixed set with an id prefixed by it, and the
resolver is inert unless `run_config.mode == "single_session"` — campaigns
are not single-session pipeline runs. Extending it to cover a campaign-merge
phase is a real, separate feature, not a reuse. **Descoped from the
implementation plan**; guided-vs-autonomous-per-unit is left as a named
future campaign rather than bundled into this one.

## DAG vs. waves — settled, not left open (post-review)

An earlier draft of this document posed DAG-vs-waves as the open decision for
the follow-up planning pass. An architecture review (Opus, prompted with this
document plus external research — see "External validation" below) found that
framing wrong: **a ready-set computation over `depends_on` is ~10 lines
(`all(state[d] == "complete" for d in deps)`); a wave/barrier model needs
about the same amount of code for a strictly less expressive result** (it
can't let a unit start the moment its own one dependency finishes if a
same-wave sibling is still running, and it needs the operator to fix batches
in advance instead of letting the scheduler discover them). There is no real
tradeoff here — **use `depends_on` (a DAG), cycle-checked at `campaign_init`
time.** This is also the shape GitLab CI's production `needs:` DAG pipelines
and GitHub Actions' rewritten 2026 job-graph scheduler both use, and it
matches how Anthropic's own multi-agent research system coordinates parallel
subagents ("an explicit, dependency-aware DAG where edges delineate strict
dependencies") — not a novel choice, an established one.

**Rejected explicitly: expressing dependencies as code structure** (the
`pipeline()`/`parallel()` composable-function shape this session's own
Workflow tool uses). `campaign.md` is a human-authored, git-tracked markdown
table that `campaign_status.py` projects into `status.json` for the WebUI and
compliance tooling; encoding the graph as imperative code would sever that
projection path for no offsetting benefit.

## What the review changed: parallel *building* is a harder problem than the schema — but no longer a deferred one

The `depends_on` schema is cheap and low-risk on its own. **Actually running
two `sub-iterate-runner`s at once is not** — Finding 4/5 above found it
requires displacing machinery (the shared-worktree lock) that exists
specifically to prevent it, and it has at least one concrete corruption path
(3f-bis's diff-source bug) that is not yet fixed. An earlier draft of this
document (and the first architecture-review pass over it) treated this as a
reason to ship the schema alone now and defer real concurrency indefinitely.
**Revised, given the measured two-day campaign and the operator's standing
automation/cycle-time goals (see the Cost note above): plan both together as
one combined design, sequenced as ordered sub-iterates, rather than treating
Increment 2 as optional future work.** Standalone, Increment 1 delivers no
throughput benefit at all (the scheduler still runs one unit at a time) — its
value only materializes once Increment 2 exists, so decoupling them was itself
part of what made Increment 1 look unjustified on its own.

**Increment 1 — data + guided/autonomous mixing.** Ships first as the
foundation Increment 2 schedules against:
- Add the `depends_on` column to `campaign.md` (cycle-checked at
  `campaign_init`), carried through `parse_campaign_skeleton` → `status.json`
  → `units.json`.
- Add an optional `mode` per sub-iterate row, resolved through
  `gate_policy.py`'s existing vocabulary at the merge decision (3g):
  `auto-default` merges without asking, `orchestrator-approve` pauses for
  Sven's explicit go-ahead, `hard-stop` always stops for review. Defaults to
  today's behavior when omitted.
- Add the interactive campaign-design conversation at `campaign_init` time
  (this session's `AskUserQuestion` exchange is a working precedent in
  miniature) that walks through proposed sub-iterates and asks which ones
  actually collide — per `feedback_one_loop_per_repo_is_false`'s own guidance:
  "ask what it would actually collide with. Name the file, the module, or the
  gate." This is where `depends_on` and `mode` get populated, not inferred
  from prose.
- `cmd_next` changes only to *respect* `depends_on` ordering (skip a pending
  unit whose deps aren't all `complete` yet) — still one unit `in_progress` at
  a time, so none of Finding 4/5's concurrency hazards apply.

**Increment 2 — actual parallel building.** Built as part of the same planned
effort, on top of Increment 1's data: per-unit worktrees (displacing the current
one-worktree-per-campaign lock model), a `next-batch`/`--max-parallel` mode on
`cmd_next` returning the whole ready-set, fixing 3f-bis's diff source so it
reads the *correct* unit's branch rather than the shared worktree's `HEAD`,
and concurrent bookkeeping in `loop_state.json`/`_reconcile_in_progress`
(currently resets *every* `in_progress` unit on resume). **Keep the merge
lane strictly serial even here** — one PR merged and CI-reverified against
current `origin/main` at a time — because Shipwright has no merge queue (it
was explicitly deferred, see `project_merge_queue_deferred_docchurn` in
project memory) and two individually-green PRs can still break `main`
together. This is the increment most likely to need `/shipwright-plan`'s
external review, since it touches `cross_component`-flagged files
(`autonomous_loop.py`, `campaign_status.py`, `campaign-mode.md`,
`campaign-worktree.md`) and changes a safety mechanism, not just a schema.

## Decision on the second review round

The second architecture-review round (below) returned `approve` (openai) and
`revise` (glm). GLM's revise argued for measuring the manual multi-session
path (Option C) on the next real campaign before committing to Increment 2's
worktree/lock redesign, reasoning the two-day campaign shows "nobody *tried*
the free option, not that it fails."

The operator (Sven) reviewed both verdicts and rejected GLM's revise
recommendation, for the following reason: the manual path requires the
operator himself to open each session, decide timing, and watch for merges —
it proves parallel execution is *possible*, but it does not reduce how much
the operator has to personally drive, which is the actual goal here
(maximizing automation), not merely proving parallelism works or shaving
cycle time by handing him a second manual task. GLM's suggestion answers "is
parallel execution technically viable" — already established — not "does this
reduce how much the operator has to personally drive." Based on that
reasoning, this iterate proceeded directly to full deep planning for
Increment 1 and 2 as one combined design, without running the manual-path
experiment.

## External validation

An Opus architecture-review pass (prompted with this document, the live
scheduler/worktree/lock code, and the external research below) confirmed
Finding 1, corrected Finding 2's original "just a bookkeeping gap" claim into
Findings 4–5 above, endorsed `depends_on` over waves, and proposed the
Increment 1/2 split. Supporting external research: GitLab CI's `needs:`
keyword is a production DAG scheduler (jobs start as soon as their declared
dependencies finish, independent of stage order); GitHub Actions rewrote its
2026 engine as a distributed job-graph scheduler for the same reason; and
Anthropic's own published account of its multi-agent research system
describes coordinating parallel subagents via "an explicit, dependency-aware
Directed Acyclic Graph (DAG) where nodes represent distinct subtasks and edges
delineate strict data or logical dependencies" — while also cautioning that
multi-agent parallelism is a poor fit for *densely* interdependent or
context-sharing subtasks. Shipwright's sub-iterates are typically sparse and
share no context, so that caution does not argue against Increment 2 — but it
does argue for keeping dependencies genuinely sparse rather than treating the
DAG as free structure to lean on.

## Explicit non-goals of this run

- No scheduler or schema code changed in this iterate — investigation and
  proposal only, per instruction.
- WebUI (per-sub-iterate launch controls, autonomous/guided toggle, DAG-state
  display) is out of scope until the monorepo side above exists; the WebUI
  would only consume what the monorepo exposes.
- Not blocking `codex-plugin-execution-reliability` (the motivating campaign):
  its R2/R3 have no stated cross-dependency and can already be hand-run in
  parallel today by starting two `/shipwright-iterate` sessions — per
  `feedback_one_loop_per_repo_is_false`, `branch_strategy: serial` only
  serializes a campaign's *own* sub-iterates, never the repository.

## Recommended next step

**Increment 1** (`depends_on` + `mode` as data, campaign-design conversation,
`cmd_next` respects ordering but stays single-active-unit) fits a **medium**
iterate: it touches `cross_component`-flagged files but changes no runtime
concurrency, so the integration-coverage gate needs a composition test proving
`cmd_next` correctly withholds a unit whose `depends_on` isn't yet complete —
smaller in scope than a true concurrency test. WebUI (per-sub-iterate launch
controls, autonomous/guided toggle, DAG-state display) stays out of scope
until this ships, consuming what it exposes.

**Increment 2** (actual parallel building: per-unit worktrees, redesigned
lock, fixed 3f-bis diff source, concurrent `loop_state.json` bookkeeping,
merge lane still serial) is its own separate iterate or small campaign,
deliberately not bundled with Increment 1, and should go through
`/shipwright-plan`'s deep planning + external review given it changes a
safety mechanism (the worktree lock) rather than adding a schema. Expect the
`check_integration_coverage` F11 gate to demand a real
`category:"integration"` composition test (mirror
`test_campaign_serial_composition_integration.py`, the test that proved #246's
own fix) proving two independent units actually build concurrently, a
dependent one actually waits, and the review cascade at 3f-bis reviews the
*correct* unit's diff when more than one is in flight.
