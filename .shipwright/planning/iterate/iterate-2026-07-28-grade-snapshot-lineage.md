# Iterate ADR — A grade snapshot names the tree it measured

- **Run-ID:** iterate-2026-07-28-grade-snapshot-lineage
- **Standalone iterate** (NOT a campaign). Closes triage `trg-72a9d195`.
- **Complexity:** medium · **spec_impact:** none · **affected_frs:** FR-01.10
  — *justification:* FR-01.10 requires `/shipwright-compliance` to "produce audit-ready evidence".
  That text stays true verbatim; no `spec.md` changes. This run makes one piece of that evidence
  say **which tree it describes**, so it stops being audit-ready-looking and starts being
  audit-ready. Nothing is added to, removed from, or reworded in what the requirement promises, so
  no `change_type` applies.
- **Owns:** the `grade_snapshot` event's wire shape and the producer that stamps it.
  **Does NOT own** the emission *cadence* (35 snapshots in one day) — that is the volume half of
  the same observation, being fixed separately. Nothing here changes how often a snapshot is
  emitted; this iterate changes only what each snapshot *says about itself*.
  **Does NOT own** the consumer — the Ship's-Log sparkline lives in `shipwright-webui`
  (`server/src/core/run-data-join.ts::projectGradeTrend`); this iterate makes the filter
  *possible* and hands it over with a card, it does not draw the chart.

## Problem statement

`grade_snapshot` (M-Pre-3) exists so the WebUI Ship's-Log can trend the Control Grade. Each event
carries `grade` + `score` + `ts` + `session` — and **nothing that identifies which tree produced
the number**. `commit` is omitted deliberately and correctly (`_grade_snapshot.py:86-88`: the
finalize-time regen runs before the F6 commit, so HEAD would still be the *previous* commit), but
nothing was put in its place.

The Control Grade is a property of a **tree state**, not of the repository in the abstract. Every
iterate runs in its own worktree branched off `origin/main`, regenerates compliance at F5b, and
commits the resulting event into its PR. `shipwright_events.jsonl` merges by **union**
(`docs/hooks-and-pipeline.md:129`), so every branch's snapshots land in one file on `main` with
nothing to tell them apart. The consumer folds all of them into one chronological series ordered
by `ts`:

```ts
// shipwright-webui server/src/core/run-data-join.ts
if (o.type !== "grade_snapshot") continue;
const grade = asString(o.grade);
if (grade === null) continue;      // the ONLY filter that exists
rows.push({ idx: i, key: tsEpoch(ts), snap: { ts, grade, score: … } });
```

Observed on `main`: `A 92.5 → F 49.0 → A 91.5 → B 87.4 → C 79.9 → F 49.0` inside five days, plus
35 identical `F 49.0` points on 2026-07-27 alone from 15 distinct sessions. The sparkline is not
noisy — it is **a mixture of different subjects plotted as if they were one**. A reader concludes
the project's control posture is collapsing and recovering daily. It is not: `main`'s grade is
`F 49.0` and has been stable; the `A`/`B`/`C` points are other trees, measured against bases
that are days old.

The divergence is large because it is not marginal. The Security dimension caps the whole grade
(`dashboard.md:10` — *"Capped: security failing (3 open high/critical)"*), and its input
`.shipwright/compliance/ci-security.json` is a **tracked** file that only reached
`open_high_critical: 3` on 2026-07-27. A worktree branched before that date measures a tree where
the cap does not exist and honestly scores `A 91.5` — for a base that no longer describes `main`.
Two points minutes apart on the merged timeline can differ by 40+ points and **both be correct
about their own tree**.

## The decision this needed

The card asked for a decision, not a field: *attribute each snapshot so consumers can filter to
the main lineage, **or** restrict emission to main-lineage regens.* One probe settles it.

**Probe — where does every snapshot on `main` actually come from?** For a sample of 18 of the 183
`grade_snapshot` events, the commit that introduced the line into `shipwright_events.jsonl`:

```
$ git log --format='%h %s' -S <event-id> -- shipwright_events.jsonl | tail -1
evt-233c9260 -> 16b1da88 feat(compliance): grade_snapshot event per Control-Grade regen … (#359)
evt-024abc36 -> bd7121b7 fix(shared): a multi-root pytest session names its own cause (#469)
evt-d096c5c5 -> 00ff3949 fix(iterate): the reviewer cascade gets an owner … (#482)
…                                                                    (18/18 identical shape)
```

**18 of 18 arrived via an iterate PR squash commit.** `git status --porcelain
shipwright_events.jsonl` on `main` is clean, so there are no uncommitted main-tree appends either.
Every snapshot that has ever existed was emitted inside a worktree, on `iterate/<slug>`, before
its own commit. **Main-lineage snapshots: zero, out of 183.**

So the second option is not a trade-off, it is a deletion: *restricting emission to main-lineage
regens produces an empty series.* Under the current architecture nothing regenerates compliance
on `main` at all — F5b runs in the worktree, `ensure_current` and `resolve_churn_conflicts`
regenerate in the worktree, and no producer runs after a merge. Restriction would not fix
M-Pre-3's sparkline; it would switch it off and call that a fix.

**Decision: attribute. Every snapshot names the tree it measured; nothing is suppressed.**

Attribution is also the only option that keeps the branch measurements, which are the *only*
data that can ever answer "did this change improve the grade" (base vs. head). Throwing them
away to fix an ordering bug would be trading a real signal for a filter we can implement.

## Alternatives considered

1. **Restrict emission to main-lineage regens** — REJECTED by the probe above: 0/183 snapshots
   qualify, so the trend goes empty. Rejected on evidence, not preference.
2. **Restrict to "fresh-base" regens** (emit only when the merge-base equals the current
   `origin/main` tip) — keeps *some* points and would cut volume, but makes emission depend on
   local fetch freshness, and drops data **silently**: an unattributed no-op leaves no trace in
   the log, so a producer that has quietly stopped emitting looks exactly like a quiet project.
   Rejected: fail-open in the direction that is hardest to notice.
3. **Record `commit` (HEAD) after all** — rejected for the reason the original author gave, which
   is still correct: at F5b, HEAD is the previous commit, so `commit` would actively mislabel the
   snapshot. `base` does not have this defect (below).
4. **Backfill the 183 existing events** — rejected as not possible honestly. The emitter cannot
   know retroactively which tree measured what; reconstructing it from the introducing commit is
   archaeology that would produce a *guess* wearing a data field's clothes. They stay
   unattributed and are defined as `unknown` (below).
5. **Add a main-lineage producer now** (regen on `main` after each merge, or at worktree setup
   where HEAD *is* `origin/main`'s tip with zero delta) — genuinely required for a
   `lineage == "main"` series to be non-empty, and deliberately NOT done here: it is a new
   producer with its own trigger and cost decision (a full compliance regen on the critical path
   of every merge). Filed rather than smuggled in. See *Known gap*.

## Design

### Three fields, all derived, none asserted

Every `grade_snapshot` gains:

| Field | Value | Why this one |
|---|---|---|
| `lineage` | `"main"` \| `"branch"` \| `"unknown"` | The filter consumers need, as a closed vocabulary — not a bare boolean, so "the producer tried and could not tell" is expressible. |
| `branch` | short branch name (`iterate/foo`, `main`) | Human-readable provenance; what a reader wants when a point looks wrong. |
| `base` | 40-hex merge-base of HEAD with the default branch | The *stable coordinate*. It names a real, already-existing commit on `main` that the measured tree extends, and — unlike HEAD — it is true whether or not F6 has run yet. This is what lets a consumer order points along `main`'s history instead of by wall-clock `ts`. |

`lineage` is **computed, never passed in** — there is no way to assert it (see *Provenance cannot
be manufactured* below).

**Resolving the default branch — conservatively (external review, edge-case/high).** The first
draft fell back to the literal string `main` whenever `origin/HEAD` was absent. That silently
misattributes: in a `master`/`trunk` repo, a regen *on the default branch* would be labelled
`"branch"`, and a stray local branch named `main` would be labelled `"main"`. The resolution is
tiered, and every tier must *resolve to a real ref*:

1. `symbolic-ref --short refs/remotes/origin/HEAD` → strip `origin/`, **and verify the ref exists**.
2. Otherwise the first candidate that actually exists, in order:
   `origin/main`, `origin/master`, `origin/trunk`, local `main`, `master`, `trunk`.
3. Otherwise **no default branch could be established** → `lineage="unknown"`, `branch` kept,
   `base=None`. Never assume `main` exists.

**Deciding `lineage` — by ancestry, not just by name (external review, edge-case/medium).**
`lineage = "main"` when *either*:

- the checked-out branch name equals the resolved default branch (covers local `main` that is
  ahead of `origin/main` — still the main lineage), **or**
- HEAD is an ancestor of (or equal to) the default ref — `git merge-base --is-ancestor HEAD <default>`.
  This is what makes a **detached HEAD** correct at *any* main commit, not only at the tip, and it
  is exactly the property that matters: *the measured tree contains nothing that is not already on
  main.* An iterate branch always fails it, because it carries unmerged commits.

`--is-ancestor` distinguishes its answers by exit code, and this resolver honours that: `0` =
ancestor, `1` = genuinely not an ancestor, anything else (shallow clone with truncated history, a
broken repo) = **could not tell**, which falls back to the name comparison alone rather than
silently reading "error" as "not an ancestor".

### `unknown` vs. absent — a distinction that carries information

- **`lineage` absent** → the event predates attribution. The 183 legacy events. Consumers must
  treat this as unknown provenance and exclude it from a main-lineage series.
- **`lineage: "unknown"`** → the producer ran, tried, and could not resolve the tree (no git, not
  a repo, empty repo). This is emitted *explicitly* rather than by omitting the field, so a
  degrading producer is visible in the log instead of looking like an old event.

### Provenance cannot be manufactured (external review, approach/medium)

The first draft gave `record_event.py` `--lineage` / `--branch` / `--base` flags that "derive
unless explicitly supplied", validating only that `--lineage` was in the vocabulary. That hands
the manual path a way to write `--lineage main` from a branch worktree — a *false* main-lineage
event, indistinguishable from a real one, in the exact log the grade trend is read from. Validating
the vocabulary does not help: `main` is a valid value; the lie is the assertion itself.

**Those flags are not added.** `record_event.py --type grade_snapshot` *always* derives attribution
from `--project-root`, and the CLI has no way to say otherwise. This is smaller than the
alternative and makes the invariant absolute rather than merely enforced: **no caller, anywhere,
can assert a lineage.** Replay of a historical snapshot is not a use case the CLI needs — its own
docstring already forbids running it against a live project.

### What `base` guarantees, precisely (external review, dependency/medium)

`base` is **a common ancestor reachable from the default branch** — that is git's guarantee, and
nothing stronger. It is *not* promised to sit on the default branch's **first-parent** chain; with
merge commits or criss-cross history it need not. The consumer follow-up must therefore use general
ancestry / topological ordering, not first-parent indexing. (This repository squash-merges, so its
`main` is linear and the two coincide *here* — an observation about this repo, deliberately not
baked into the contract.)

`base` is validated as lowercase hex of length 7–64 before it is stamped, rather than assuming the
40-char SHA-1 form, so a SHA-256 repository is not silently rejected.

### Failure posture

Attribution is best-effort and **must never abort a compliance regen** — same contract as the
rest of the emitter (`update_compliance` wraps it best-effort). Every git call degrades to `None`
rather than raising; a partial resolution emits what it has (`lineage` + `branch`, no `base`)
rather than discarding all three.

### Where the resolver lives (ADR-045)

New module **`shared/scripts/tree_lineage.py`** — top-level under `shared/scripts/`, *not* under
`lib/`. This is the established seam: `shared/scripts/tests_block.py` carries the comment *"Shared
skip-vs-fail SSOT (top-level, not under lib/, so the compliance plugin can import it too without a
lib-namespace collision — ADR-045)"*. `_grade_snapshot.py` lives in the compliance plugin's own
`scripts/lib/` namespace, so an import of shared `lib.X` would shadow it; the top-level namespace
has no such collision, and the emitter already reaches `shared/scripts` this way for
`tools.record_event`.

The module is **stdlib-only and self-contained**, including its own small `git -C` runner. It is
deliberately not reusing `source_state_git._git`: that name is private, and this module is
lazily imported from a plugin across the ADR-045 seam where every transitive import is another
chance to bind the wrong `lib`. The duplication is ~15 lines of `subprocess.run` and is a
deliberate cost, recorded here so a reviewer reads it as a choice rather than an oversight.

All git invocations use `git -C <root>` (never process-cwd), because the producer runs inside a
worktree where the shell's cwd is not the tree being measured.

## Acceptance criteria

- **AC1** — `resolve_tree_lineage(root)` returns `lineage="main"` for a repo checked out on its
  default branch, and `lineage="branch"` on a branch carrying unmerged commits. *(unit)*
- **AC2** — `base` is the merge-base of HEAD with the default branch; for a branch with commits on
  top of the default, it is the branch point, **not** HEAD. Stamped only when it is lowercase hex
  of length 7–64. *(unit)*
- **AC3** — The default branch is resolved conservatively: `origin/HEAD` is honoured only when its
  target ref exists; a `master`-default repo with no `origin/HEAD` resolves to `master` (not the
  literal `main`) via the existence-checked candidate probe; a repo where **no** candidate exists
  yields `lineage="unknown"` with `branch` preserved — never an assumed `main`. *(unit)*
- **AC4** — Detached HEAD is decided by ancestry, not by name: detached at the default tip **and**
  detached at an older default-branch commit both yield `lineage="main"`; detached on an unmerged
  branch commit yields `"branch"`. *(unit)*
- **AC5** — Every failure mode degrades instead of raising: no git binary, not a repo, empty repo →
  `TreeLineage("unknown", None, None)`. A resolvable branch whose merge-base is unobtainable
  (shallow clone / unrelated histories) keeps `lineage` + `branch` with `base=None`. An
  `--is-ancestor` call that *errors* (exit code ≠ 0/1) falls back to the name comparison rather
  than being read as "not an ancestor". *(unit)*
- **AC6** — `emit_grade_snapshot` stamps `lineage` on every event it appends, and includes
  `branch`/`base` when resolved. A resolver that **raises** still yields an appended snapshot
  carrying `lineage="unknown"` — attribution never takes down a compliance regen. *(unit)*
- **AC7** — `record_event.py --type grade_snapshot` always derives attribution from
  `--project-root`, and exposes **no flag** by which a caller could assert `lineage`, `branch` or
  `base`. *(unit — asserts the absence of the flags, so re-adding them fails the test)*
- **AC8** — Round-trip: a stamped snapshot survives `append_event` → `read_events` with all three
  fields intact and JSON-typed as declared (`lineage` str, `base` str-or-absent). *(io-boundary)*
- **AC9** — Real-flow: a compliance regen run against a fixture project appends a `grade_snapshot`
  whose `lineage`/`branch`/`base` describe *that* tree — proving the producer, the resolver and
  the event writer compose, not just that each works alone. *(integration)*
- **AC10** — The contract is documented where a consumer will look: `docs/hooks-and-pipeline.md`
  gains a `grade_snapshot` row in the Event Emission Points table plus the attribution vocabulary,
  the absent-means-legacy rule, and what `base` does and does not guarantee.

## Scope

**In:** `shared/scripts/tree_lineage.py` (new), `shared/scripts/tools/record_event.py`,
`plugins/shipwright-compliance/scripts/lib/_grade_snapshot.py`, their tests,
`docs/hooks-and-pipeline.md`.

**Out:** emission cadence/volume (separate fix); the webui consumer (separate repo, carded); a
main-lineage producer (carded, see below); backfilling the 183 legacy events (not honestly
possible).

## Known gap — stated, not hidden

After this change, a consumer filtering `lineage == "main"` gets **an empty series**, because
nothing regenerates compliance on `main` (the probe above). That is the correct empty — "we have
never measured `main`" is the truth — but it means this iterate makes the data honest without yet
making the sparkline useful. The two follow-ups are carded, not assumed:

1. **Consumer** (`shipwright-webui`): `projectGradeTrend` must filter/group by attribution. The
   most useful series available *today* needs no new producer: group branch snapshots by `base`,
   keep the latest per base, and order the bases by **ancestry / topological position** in the
   default branch's history (not by first-parent index — see *What `base` guarantees*) — a
   main-lineage series reconstructed from branch measurements.
2. **Producer** (this repo): something must measure `main` itself if `lineage == "main"` is ever
   to be non-empty.

## External-Plan-Review-Findings (Step 3.5 — Gemini 3.1 Pro + GPT-5.6 via OpenRouter, both succeeded)

Verdicts: Gemini **approve** · GPT **revise** · no contradiction. All six GPT findings and all
four Gemini findings addressed or explicitly dispositioned:

| # | Reviewer | Sev | Finding | Disposition |
|---|---|---|---|---|
| 1 | GPT | high | Unconditional `main` fallback misattributes `master`/`trunk` repos and mislabels a stray local `main` | **Fixed** — tiered, existence-checked default resolution; no default ⇒ `unknown` (AC3) |
| 2 | GPT | med | Manual CLI could assert a false `--lineage main` | **Fixed** — the flags are not added at all; derivation only (AC7) |
| 3 | GPT | med | `base` is not guaranteed on the first-parent chain | **Fixed** — contract restated as *ancestor reachable from the default branch*; consumer note corrected |
| 4 | GPT | med | Partial git states (shallow, detached variants) undertested | **Fixed** — ancestry-based `lineage`; `--is-ancestor` exit-code triage; AC4 + AC5 |
| 5 | GPT | low | Subprocess on the regen path; emitter must survive a resolver exception | **Fixed** — 5 s timeout, emitter try/except ⇒ `unknown` (AC6) |
| 6 | GPT | low | Validate externally supplied `base`/`branch`; don't hard-code 40 chars | **Partly moot** (no external supply after #2); hex 7–64 validation kept for SHA-256 tolerance (AC2) |
| 7 | Gemini | med | Shallow CI clones break `merge-base` | **Verified not reachable** — no workflow under `.github/workflows/` invokes `update_compliance`/`finalize_iterate`; the producer never runs in CI. Degradation to `base=None` is correct if that changes (AC5) |
| 8 | Gemini | low | Decode/strip subprocess stdout | **Fixed** — `text=True`, `encoding="utf-8"`, `.strip()` |
| 9 | Gemini | low | Strict deserialization could reject legacy events | **Verified moot** — `lib.config.read_events` returns plain dicts via `read_jsonl_records`; no schema layer exists |
| 10 | Gemini | low | `symbolic-ref` failure must hook cleanly | **Fixed** — same tiered resolution as #1 |

## Guardrails honored

- Additive wire change: unknown fields are ignored by every existing reader; the union merge
  driver is unaffected (it merges lines, not fields).
- No change to `grade`/`score` semantics, to emission cadence, or to the idempotency contract.
- The emitter's best-effort posture is preserved: a compliance regen never fails because
  attribution failed.

## External-Code-Review-Findings (Step 3.7 — GPT-5.6 + Gemini 3.1 Pro via OpenRouter)

Run in **two halves**: the 1125-line diff truncated both providers in one pass (`finish_reason=length`
/ empty reply). Consequence, disclosed rather than hidden: **each half reported the other half as
missing** — the production pass said "no tests, no docs", the tests/docs pass said "no resolver, no
shape module". Those are scope artifacts of the split, dismissed on evidence, and they are why the
`code` marker records `gemini=reject`. Three findings were substantive; all three are fixed:

| Sev | Finding | Fix |
|---|---|---|
| low → real | `UnicodeDecodeError` is a `ValueError`, so strict UTF-8 decoding escapes the module's "nothing here raises" contract; direct resolver callers have no outer handler | `errors="replace"` **and** `ValueError` added to the caught set — two independent defences — plus a behavioural test |
| med → real | `merge-base --is-ancestor` exiting non-0/1 was classified `"branch"`, contradicting the code's own comment that anything else means "could not tell" | Exit code triaged: `0` main, `1` branch, otherwise `"branch"` only when a branch **name** is known, else `"unknown"` — a detached HEAD with no ancestry answer is genuinely unknowable |
| med → real | The CLI derivation test only ran against a non-repo and asserted `"unknown"` — a CLI hardcoded to stamp `"unknown"` would have passed it | Two real-git CLI tests added: default-branch checkout → `main`, unmerged branch → `branch` + branch-point `base` |

## Confidence Calibration

**Boundaries touched.** (1) The `grade_snapshot` record on the durable, tracked
`shipwright_events.jsonl` — a **cross-repo** boundary read by `shipwright-webui`. (2) The
`.gitattributes` union merge driver that merges that file. (3) The `record_event.py` CLI argument
surface. (4) `update_compliance`'s stdout payload. (5) The ADR-045 import seam between
`shared/scripts` and the compliance plugin's own `scripts.lib` namespace.

**Empirical probes run** — every load-bearing claim in this ADR was measured, not assumed:

| Probe | Finding |
|---|---|
| `git log -S <event-id> -- shipwright_events.jsonl \| tail -1` over 18 of 183 snapshots | **18/18** introduced by an iterate PR squash commit ⇒ zero main-lineage snapshots exist ⇒ the "restrict emission" option deletes the trend. **This probe is the decision.** |
| `git status --porcelain shipwright_events.jsonl` on `main` | Clean — so the 18/18 is not an artifact of uncommitted main-tree appends |
| Read `.shipwright/compliance/dashboard.md` on `main` | `F (49/100)`, *"Capped: security failing (3 open high/critical)"* — `main`'s true grade IS the low one; the `A`/`B`/`C` points are other trees |
| `git show <sha>:.shipwright/compliance/ci-security.json` | `open_high_critical: 3` with `scan_date` 2026-07-27 — the cap is recent, so a worktree branched earlier honestly scores `A`. Confirms divergence is real and base-dependent, not noise |
| `grep -rln "update_compliance\|finalize_iterate" .github/workflows/` | No match — the producer never runs in CI, so Gemini's shallow-clone finding is unreachable today |
| Read `lib/config.read_events` | Returns plain dicts via `read_jsonl_records`; no schema layer ⇒ legacy events cannot fail validation |
| `wc -l shared/scripts/tools/record_event.py` vs `shipwright_bloat_baseline.json` | Baselined 769, `state: exception` ⇒ any growth is a ratchet ⇒ extract-don't-append; measured **767** after |
| **Script-mode E2E** — real `uv run shared/scripts/tools/record_event.py --type grade_snapshot` against a throwaway repo on an unmerged branch | `lineage:"branch"`, `branch:"iterate/e2e"`, `base` == the branch point exactly. This probe exists because `record_event.py` is invoked **both** as a script and as a module (`tools.record_event`), which are different `sys.path` situations — the tests only cover module mode, so the new top-level `grade_snapshot_shape` import could have resolved in tests and failed in production. It does not. |
| **This run's own F5b regen** — the production emitter, unprompted, on the real repo | `{"grade":"B","score":85.8,"lineage":"branch","branch":"iterate/grade-snapshot-lineage","base":"78be49fd…"}`, and `git merge-base HEAD origin/main` == `78be49fd…`. This is the defect caught in the act: **this worktree scores `B 85.8` while `main` scores `F 49.0`**, so without attribution this very event would have union-merged onto `main` and rendered as a spontaneous 37-point jump on the sparkline — the exact artifact the card reported. It now says what it is. |

**Test Completeness Ledger** — principle: testable ⇒ tested. Every behaviour this diff introduces:

| # | Behaviour | Disposition | Evidence |
|---|---|---|---|
| 1 | Default branch checkout → `lineage="main"` | tested | `test_tree_lineage.py::test_default_branch_is_main_lineage` |
| 2 | Branch with unmerged commits → `"branch"` | tested | `::test_branch_with_unmerged_commits_is_branch_lineage` |
| 3 | Branched but not diverged → still `"main"` | tested | `::test_branch_with_no_commits_of_its_own_is_still_main_lineage` |
| 4 | Local default ahead of its remote → still `"main"` | tested | `::test_default_branch_ahead_of_its_remote_is_still_main_lineage` |
| 5 | `base` is the branch point, not HEAD | tested | `TestBase::test_base_is_the_branch_point_not_head` |
| 6 | `master`/`trunk` default repos resolve correctly | tested | `TestDefaultBranchResolution` (2 tests) |
| 7 | No resolvable default → `"unknown"`, never assumed `main` | tested | `::test_no_resolvable_default_yields_unknown_not_assumed_main` |
| 8 | `origin/HEAD` beats a stray local `main` | tested | `::test_stray_local_main_does_not_hijack_a_master_repo` |
| 9 | Detached at tip / at an older default commit → `"main"` | tested | `TestDetachedHead` (2 tests, incl. `base` assertion) |
| 10 | Detached on an unmerged commit → `"branch"` | tested | `::test_detached_at_unmerged_branch_commit_is_branch_lineage` |
| 11 | Detached HEAD stamps no branch name | tested | `::test_detached_head_reports_no_branch_name` |
| 12 | Non-repo / missing dir / empty repo → `unknown,None,None` | tested | `TestDegradation` (3 tests) |
| 13 | Unrelated histories keep lineage+branch, drop `base` | tested | `::test_unrelated_histories_keep_lineage_and_branch_but_drop_base` |
| 14 | Absent git binary / timeout → `"unknown"` | tested | `TestDegradation` (2 tests) |
| 15 | Undecodable git output degrades, never raises | tested | `::test_undecodable_git_output_degrades_instead_of_raising` |
| 16 | `--is-ancestor` error: named branch → `"branch"`, detached → `"unknown"` | tested | `TestUnresolvableAncestry` (3 tests) |
| 17 | `lineage_fields` projection: full / unknown-only / partial | tested | `TestLineageFields` (3 tests) |
| 18 | Implausible `base` dropped; SHA-256 width accepted | tested | `::test_implausible_base_is_dropped_not_stamped`, `::test_sha256_width_object_name_is_accepted` |
| 19 | Shape validates grade/score and coerces score to float | tested | `test_grade_snapshot_shape.py::TestGradeAndScore` (6 tests) |
| 20 | Validation raises **before** mutating the event | tested | `::test_validation_runs_before_attribution` |
| 21 | Every event from the shape is attributed | tested | `TestAttributionIsUnavoidable` (3 tests) |
| 22 | A raising resolver still yields an attributed event | tested | `::test_a_raising_resolver_still_yields_an_attributed_event` |
| 23 | Emitter stamps branch/base/lineage from a real tree | tested | `test_grade_snapshot_regen.py::TestEmitterAttributesTheTree` (4 tests) |
| 24 | Emitter's return payload reports `lineage` | tested | `::test_snapshot_from_a_real_repo_names_its_branch_and_base` |
| 25 | CLI derives real attribution (not just `"unknown"`) | tested | `test_grade_snapshot_event.py::test_the_cli_resolves_a_real_tree_not_just_unknown` + `::…_main_lineage_on_the_default_branch` |
| 26 | CLI exposes **no** flag to assert attribution | tested | `::test_no_flag_can_assert_attribution` (parametrized ×3) |
| 27 | Attribution survives the JSONL round-trip with declared types | tested | `::test_attribution_survives_the_round_trip_with_declared_types` |
| 28 | **Integration** — regen in a branch tree lands an attributed event | tested | `TestComplianceRegenComposition::test_regen_in_a_branch_tree_lands_an_attributed_snapshot` |
| 29 | Pre-existing consumers still ignore `grade_snapshot` | tested | `TestAdditiveConsumer` (unchanged, still green) |

**29 behaviours, 29 tested, 0 untestable, 0 testable-but-untested.** The WebUI's filtering is
deliberately *not* a row here: it is not a behaviour this diff introduces, and listing it as
"untestable" would be dressing an out-of-scope item in a `reason_code` to look covered. It is
carded (`trg-d190cc37`).

Totals: **70 tests** (55 `shared/tests` + 15 `shipwright-compliance`), full
roots green — `shared/tests` 6064 passed / 16 skipped, compliance root 11 passed, `ruff` clean.

**Confidence-pattern check.**
- *Asymptote (depth):* the probes went past the symptom. The card described a missing field; the
  probe showed the alternative fix was impossible, which changed the deliverable from "add a field"
  to "make a decision and record why the other option is not one".
- *Coverage (breadth):* both producers of this event are covered, not just the one the card named —
  the CLI could otherwise have kept writing unattributed snapshots through a second door.
- *Integration composition:* `cross_component` does **not** fire on this diff (no
  `events_log.py`, no hooks, no phase validators — checked against
  `risk_detectors.CROSS_COMPONENT_FILE_PATTERNS`), so no integration behaviour is mandated. One is
  recorded anyway (#28): three parts — the `update_compliance` dashboard branch, the emitter, and
  the git resolver — each pass their own unit tests while still producing an unattributed event if
  the wiring between them is wrong, which is precisely the defect being fixed.
- *Honest limit:* this run makes the **data** correct. It does not make the **chart** correct, and
  it does not create a main-lineage series — `lineage == "main"` filters to empty today. Both are
  carded (`trg-d190cc37`, `trg-1603000f`) and stated in *Known gap* rather than implied away.
