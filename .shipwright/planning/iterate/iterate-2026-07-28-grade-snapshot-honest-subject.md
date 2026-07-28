# Iterate ADR — A grade snapshot tells the truth about its own subject

- **Run-ID:** iterate-2026-07-28-grade-snapshot-honest-subject
- **Standalone iterate.** Closes `trg-ca4fc0e7`, `trg-c97faa35`, `trg-aea8c97e`, `trg-465a2caf`.
- **Complexity:** medium · **spec_impact:** none · **affected_frs:** FR-01.10
  — *justification:* FR-01.10 requires `/shipwright-compliance` to "produce audit-ready evidence".
  Unchanged verbatim; no `spec.md` touched. This run repairs evidence that was shipped stating
  something false about itself.
- **Follows** `iterate-2026-07-28-grade-snapshot-lineage` (PR #485, merged `ee07a3b5`). That run
  added tree attribution to `grade_snapshot`. An internal reviewer cascade run **after** the merge
  found that the attribution was wrong in the single case it exists for, that its central integrity
  claim had an open back door, and that the probe the whole design decision rested on could not
  discriminate. This run fixes all three.

## Why there is a second iterate

PR #485 shipped with external LLM review only (plan + code, two providers, two rounds). The
internal `spec-reviewer → code-reviewer → doubt-reviewer` cascade was recorded `not_run` because
this session's standing directive gates the Agent tool behind an explicit operator request. The
operator then granted it. Running the cascade against the **merged** code produced four findings
that the external reviews had not, three of them verified by reproduction here.

That is the finding worth keeping: **the two review routes are not substitutable.** The external
route reads a diff; the cascade reads the *claims* and attacks them.

## Finding 1 — attribution was wrong in exactly the case it exists for (HIGH)

`resolve_tree_lineage` decided `lineage` by **ancestry**: `"main"` when HEAD is an ancestor of the
default ref. An iterate worktree is created **at the fork point** (`git worktree add … origin/<default>`)
and the snapshot is emitted at **F5b — before F6, the only mandated commit**. So at emission HEAD
*is* the fork point, ancestry answers `"main"`, and the event is stamped as the default branch's own
while the working tree it graded holds the entire uncommitted change set.

Reproduced:

```
$ # branch at the fork point, dirty working tree
TreeLineage(lineage='main', branch='iterate/simulated', base='b28dc1c7…')
```

The result is worse than the defect the previous run set out to fix: the phantom point is no longer
merely unlabelled, it is labelled **authoritative**.

**Why the previous run's live "proof" missed it.** Its own F5b emission read `lineage: "branch"` and
was written into the ADR as confirmation. It read `"branch"` only because a `chore(triage): sweep`
commit (`645eb967`) happened to land on that branch before F5b, so HEAD was not the fork point.
A single lucky observation was read as verification — the exact confidence anti-pattern the
calibration step exists to prevent.

**Root cause, shared with Finding 3:** `lineage` and `base` are derived from **committed** state,
while `grade`/`score` are computed from the **working tree**. Nothing reconciled the two.

**Fix.** A named non-default branch is `"branch"`, full stop — ancestry is no longer consulted for
it. Ancestry was only ever needed for a **detached** HEAD, which has no name to reason from.

The old test asserted the bug (`test_branch_with_no_commits_of_its_own_is_still_main_lineage`,
"calling it branch would misreport the subject"). It is inverted, not deleted — the mistake was
mine and the record should show it.

## Finding 2 — "cannot be asserted" had a back door (REJECT)

The previous run deleted the `--lineage`/`--branch`/`--base` flags and claimed the invariant was
*"absolute rather than merely enforced: no caller, anywhere, can assert a lineage."* That was
audited across the two **producers** and missed the log's generic **mutator**:

```
record_event.py --type event_amended --amends <snapshot-id> \
  --fields '{"lineage":"main","branch":"main","score":99.9}'
```

`build_event` validated only a `tests` sub-dict inside `--fields`; `apply_amendments` overlays with
a blind `{**e, **overlay}` — no allowlist, no target-type check. Reproduced end to end: a snapshot
honestly emitted as `lineage=branch score=12` reads back to every amendment-folding reader as
`lineage=main branch=main score=99.9`.

The claim was also rendered verbatim into `docs/hooks-and-pipeline.md` — the file `CLAUDE.md`
designates the single source of truth — addressed at a cross-repo consumer deciding whether to
trust the field.

**Not a regression introduced by #485:** the channel could always overlay arbitrary fields,
including `score`. What #485 added was the false claim about it.

**Fix.** The refusal now sits in the same branch, in the same shape as the `tests` validation
already there, keyed off `ATTRIBUTION_KEYS` owned by the shape module so the two cannot drift.
Verified safe: those keys occur on **no other event type**, and none of the 27 existing amendments
overlays them. The doc now states the two limits that remain — this is not tamper-evidence against
arbitrary Python, and `--grade`/`--score` are *still* caller-supplied, so a correctly-attributed
point can still carry a grade nobody computed.

## Finding 3 — `base` cannot carry the consumer recipe it was given (MEDIUM-HIGH)

The shipped doc told consumers to *"group snapshots by `base`, keep the latest per base, and order
the bases by ancestry."* Applied to `"branch"` snapshots that plots `main@base + an unmerged diff`
at `main@base`'s coordinate — the original mixture defect, re-indexed from wall-clock to commit
position and made to look authoritative. Worse, N concurrent iterates off one tip share one `base`,
so "latest per base" **discards N-1 real measurements**; with the observed cadence (35 snapshots,
15 sessions, one day) that is the normal case.

And on the main-lineage path `base` collapses: where HEAD is an ancestor of the default ref,
`merge-base(HEAD, default) == HEAD`, so for a pre-commit regen `base` **is** the previous commit —
precisely the defect for which recording `commit` was rejected, under a doc rule claiming `base`
"answers which tree without that defect."

**Fix — the consumer contract, not the field.** A `lineage: "branch"` snapshot is now documented as
**not a point on the default branch's trend at all**. It answers a different question (did this
branch move the grade relative to what it forked from — a per-branch delta). Only `"main"`
snapshots belong on the timeline; see the withdrawn-`dirty` section for what still cannot be said about them.

## Finding 4 — the probe that decided the design could not discriminate (HIGH, evidence)

PR #485 rejected the "restrict emission" alternative on this, labelled *"This probe is the decision"*:
18 of 183 snapshots, `git log -S <id> -- shipwright_events.jsonl | tail -1`, 18/18 an iterate PR
squash commit.

**The result is entailed by the merge strategy.** This repo squash-merges every PR, so *every* line
reaching the default branch is introduced by exactly one squash commit regardless of which tree
produced the measurement. "All emitted in worktrees" and "some emitted on a default-branch tree and
later swept in" produce byte-identical output. The probe measured which snapshots **survived**, not
which were **emitted**.

The generalisation built on it was false too. Verified here:

- Every one of the 11 `PHASE_REPORTS` entries includes `dashboard` — the branch that emits. **Every**
  compliance regen produces a snapshot.
- `/shipwright-compliance` SKILL.md:87 runs `update_compliance --project-root "$(pwd)"`.
- `shipwright-run`'s orchestrator regenerates after **every completed pipeline phase**, on the
  default branch in greenfield and adopted projects — where `"main"` would be the *dominant* value.

**The decision still stands, on different legs.** Restriction remains wrong because a fresh-base
condition drops data *silently* (a stopped producer is indistinguishable from a quiet project), and
because branch measurements are the only data that can answer base-vs-head. Both arguments survive
scrutiny; the probe does not. The spec and the doc are corrected so no future reader inherits the
bad inference.

## Also fixed

- `test_stray_local_main_does_not_hijack_a_master_repo` did not pin what it claimed — proven by
  mutation: with the entire `origin/HEAD` tier deleted, all four default-branch tests stayed green,
  because `origin/main` did not exist in that fixture so the candidate probe reached
  `origin/master` unaided. Replaced with an origin carrying **both** `main` and `trunk` and
  `origin/HEAD → trunk`, where only the tier under test can produce the right answer. Re-verified by
  mutation: the new test fails when the tier is removed.
- AC3's first clause (a **dangling** `origin/HEAD` must fall through to the candidates) was
  implemented but untested, against a ledger claiming zero untested behaviours. Now covered.
- `Path(project_root)` was the one statement that could raise past the module's "nothing here
  raises" contract. Guarded + tested.
- `branch` was stamped verbatim onto a tracked, cross-repo, append-only artifact with no bound.
  Now dropped if >255 chars or carrying control characters.
- Two tests hard-coded SHA-1's 40-char width next to a production rule deliberately widened to 7–64
  for SHA-256 — they would have turned red on a `sha256` default while the code was right.
- `campaign_status.py`'s `# events carry no branch` became false the moment #485 shipped.

**Investigated and dismissed:** the review claimed `import grade_snapshot_shape` in the compliance
test resolved only via another test's `sys.path` side effect. Falsified — the module-level
`import scripts.tools.update_compliance` in the same file wires `shared/scripts` deterministically,
verified by importing it in a clean interpreter and printing `sys.path`. No change made.

## Acceptance criteria

- **AC1** — A named non-default branch resolves `"branch"` regardless of ancestry, including at the
  fork point with no commits of its own. *(unit, mutation-verified)*
- **AC2** — A detached HEAD is still decided by ancestry: at the tip and at an older default-branch
  commit both `"main"`; on an unmerged commit `"branch"`; unobtainable ancestry `"unknown"`. *(unit)*
- **AC4** — `record_event.py --type event_amended --fields` rejects `lineage`/`branch`/`base`/`dirty`
  and still accepts every other correction. *(unit)*
- **AC5** — `origin/HEAD` beats a higher-priority candidate (origin carrying both `main` and
  `trunk`); a **dangling** `origin/HEAD` falls through to the candidates. *(unit, mutation-verified)*
- **AC6** — `resolve_tree_lineage` degrades rather than raising for a non-path `project_root`; an
  overlong or control-laden branch name is dropped, not stamped. *(unit)*
- **AC7** — The emitter stamps the corrected attribution: a worktree at the fork point with an
  uncommitted change set lands `lineage="branch"`. *(integration)*
- **AC8** — `docs/hooks-and-pipeline.md` states the corrected consumer contract: branch snapshots
  are not timeline points, `base` collapses to the previous commit on the main path with **no field
  disclosing whether the graded content matches it**, and main-lineage snapshots are the *normal*
  case in adopted projects.

## Guardrails honored

- **No wire-shape change at all.** The corrected `lineage` rule changes which *value* a snapshot
  carries, not which keys exist, so no consumer needs to know this shipped.
- No change to emission cadence, to `grade`/`score` semantics, or to the legacy-event policy.
- The refusal in the amendment path is surgical: only the four attribution keys, verified against
  every historical amendment.

## Withdrawn during the run: the `dirty` field

`dirty` (tracked files modified relative to HEAD) was designed, implemented, tested and then
**removed before commit**. It is recorded here rather than quietly dropped, because the reason is
the interesting part.

The intent was to disclose the committed-vs-working-tree split directly. Measuring it at emit time
cannot work: **every automatic producer writes tracked files before the snapshot is emitted.**
Found in two rounds —

1. `update_compliance` rewrites its own 5–7 tracked artifacts before the `dashboard` branch emits.
   *Measured: `dirty: true` on a pristine repo.* Addressed with an exclusion list.
2. The exclusion list was then pinned to `DERIVED_SNAPSHOTS` — which `test_derived_snapshots.py`
   explicitly asserts does **not** contain `shipwright_events.jsonl` or `.shipwright/triage.jsonl`,
   the two the producer chain also writes first. *Measured: the run-orchestrator appends
   `phase_completed` to the tracked log, then regenerates → `dirty: true` with zero uncommitted
   source.* The pin enforced the wrong equality in both directions.

Combined with this iterate's own doc rule ("`dirty: true` → provisional, do not plot"), that would
have marked **every** main-lineage point provisional and emptied the trend a second time — the
field's meaning inverted: it would have discriminated *producer* (automatic vs. hand-run), not
*content*.

Two failed attempts on the same field is a design signal, not a patch signal. Correctness here
depends on enumerating every artifact any of 11 call sites writes before emitting — a moving target.
The right design captures dirtiness **before** the producer starts writing and passes it in (the
seam `source_state.py` already models), which is its own change. Filed as `trg-10aa91e3`, and
`docs/hooks-and-pipeline.md` rule 5 now states the gap plainly instead of pointing at a field that
lies.

The alternative — shipping it — was rejected for the same reason the previous run's defect was
worth fixing at all: a wrong label is worse than an absent one.
