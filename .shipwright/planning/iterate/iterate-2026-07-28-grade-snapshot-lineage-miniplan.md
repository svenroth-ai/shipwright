# Mini-Plan — A grade snapshot names the tree it measured

Run-ID: `iterate-2026-07-28-grade-snapshot-lineage` · complexity medium · change

## What is broken

`grade_snapshot` events carry `grade` + `score` + `ts` and nothing identifying **which tree**
produced the number. Every iterate regenerates compliance inside its own worktree and commits the
resulting event into its PR; `shipwright_events.jsonl` merges by union, so all branches' snapshots
land in one file on `main`. The WebUI consumer folds every snapshot into one series ordered by
`ts` (`shipwright-webui server/src/core/run-data-join.ts::projectGradeTrend` — its only filter is
"has a grade"). The sparkline therefore plots a mixture of divergent trees as if it were one
project's control-posture trend: `A 92.5 → F 49.0 → A 91.5 → B 87.4 → C 79.9 → F 49.0` in five days.

## Why the alternative was rejected (the decision this iterate had to make)

The card offered: *attribute the snapshots*, **or** *restrict emission to main-lineage regens*.

Probe: for 18 of the 183 snapshots on `main`, find the commit that introduced the line
(`git log -S <event-id> -- shipwright_events.jsonl | tail -1`). **18/18 came in through an iterate
PR squash commit**, and `git status --porcelain shipwright_events.jsonl` on `main` is clean.
Every snapshot ever emitted came from a worktree on `iterate/<slug>`. Nothing regenerates
compliance on `main` — F5b, `ensure_current` and `resolve_churn_conflicts` all run in the worktree,
and no producer runs post-merge.

⇒ Restriction yields **zero** points. It does not fix the trend, it switches it off. **Decision:
attribute.**

A middle option (emit only when the merge-base equals the current `origin/main` tip) was also
rejected: it makes emission depend on local fetch freshness and drops data silently, so a
producer that has quietly stopped looks identical to a quiet project.

## Implementation

**1. `shared/scripts/tree_lineage.py` (new, stdlib-only, ~90 LOC)**

```python
@dataclass(frozen=True)
class TreeLineage:
    lineage: str          # "main" | "branch" | "unknown"
    branch: str | None
    base: str | None      # 40-hex merge-base with the default branch

def resolve_tree_lineage(project_root: Path | str) -> TreeLineage: ...
```

> **Revised after the Step 3.5 external plan review** (Gemini approve / GPT revise). The three
> paragraphs below replace the first draft's "fall back to `main`", "derive unless explicitly
> supplied" and "40-hex base"; the full disposition table is in the spec.

- `git -C <root>` for every call (never process-cwd — the producer runs in a worktree whose tree
  is not the shell's cwd), `shell=False`, bounded 5 s timeout, non-zero exit → `None`.
- **default branch, conservatively:** `symbolic-ref --short refs/remotes/origin/HEAD` *only when
  its target ref resolves*; else the first candidate that actually exists among
  `origin/{main,master,trunk}` then local `{main,master,trunk}`; else **no default could be
  established** → `lineage="unknown"`. Never assume the literal `main` exists.
- `base`: `merge-base HEAD <origin/default or local default>`, stamped only when it is lowercase
  hex of length **7–64** (not assumed 40, so a SHA-256 repo keeps its attribution).
- **`lineage` by ancestry, not just by name:** `"main"` when branch == default branch **or**
  `merge-base --is-ancestor HEAD <default>` — the second covers a detached HEAD at *any*
  default-branch commit, not only the tip. `--is-ancestor` is read by exit code: `0` ancestor,
  `1` genuinely diverged, anything else "could not tell" → keep `"branch"` when a branch name is
  known, otherwise `"unknown"`.
- Every failure degrades; nothing raises.

Placed **top-level under `shared/scripts/`, not under `lib/`** — the established ADR-045 seam
(`shared/scripts/tests_block.py`: *"top-level, not under lib/, so the compliance plugin can import
it too without a lib-namespace collision"*). The compliance emitter lives in the plugin's own
`scripts/lib/` namespace, so a shared `lib.X` import would shadow it.

**2. `plugins/shipwright-compliance/scripts/lib/_grade_snapshot.py`**

Extend the existing lazy `sys.path.insert(shared/scripts)` block (already there for
`tools.record_event`) with `from tree_lineage import resolve_tree_lineage`. Stamp `lineage` always,
`branch`/`base` when resolved. Keep the `commit`-is-omitted comment and extend it to say what
replaced it. Attribution failure must still append the snapshot.

**3. `shared/scripts/tools/record_event.py`**

`--lineage` / `--branch` / `--base` are **deliberately not added** (external plan review,
approach/medium): a CLI able to pass `--lineage main` from a branch worktree could manufacture a
false main-lineage point in the very log the trend reads, and validating the vocabulary would not
help — `main` is a legal value; the lie is the assertion. The branch instead *always* derives from
`--project-root`, so no caller anywhere can assert provenance.

This file is baselined at 769 lines (`state: exception`, ADR-111), so anti-ratchet blocks any
growth. Following the convention this file already set with `lib/fr_gates.py` — **extract, don't
append** — the grade/score validation moves out with the attribution into a shared shape module
(below), taking the branch from 10 lines to 2 and ratcheting the file **down** to 767.

**3b. `shared/scripts/grade_snapshot_shape.py` (new)** — one owner for the event's wire shape,
used by *both* producers. They previously built the event independently, so the CLI enforced a
score range the emitter did not, and a field added to one would silently not exist on the other.

**4. Tests** — unit (resolver, real git fixture repos), emitter stamping, CLI derivation +
validation, io-boundary round-trip through `append_event` → `read_events`, and one real-flow
integration test that runs a compliance regen and asserts the appended snapshot describes that tree.

**5. `docs/hooks-and-pipeline.md`** — add the missing `grade_snapshot` row to the Event Emission
Points table, plus the attribution vocabulary and the **absent `lineage` = legacy, pre-attribution**
rule that consumers need.

## Deliberate non-goals

- **Cadence/volume** (35 snapshots in a day) — the other half of the same observation, fixed
  separately. Nothing here changes how often a snapshot is emitted.
- **The consumer** — lives in `shipwright-webui`; carded.
- **A main-lineage producer** — required before `lineage == "main"` is ever non-empty (today it
  filters to empty, correctly). A new producer with its own trigger/cost decision; carded, not
  smuggled in.
- **Backfilling the 183 legacy events** — the emitter cannot know retroactively which tree measured
  what. They stay unattributed and are *defined* as unknown rather than guessed.

## Risks

- **Wire-shape change on a cross-repo boundary.** Mitigated: purely additive, unknown fields are
  ignored by existing readers, and the union merge driver merges lines not fields.
- **`git` calls in a producer that must never fail.** Mitigated: bounded timeout, no shell,
  every path degrades to `None`, emitter still appends on total attribution failure.
- **Honest-but-inert.** This makes the data correct without making the chart correct. Stated
  openly in the spec's *Known gap* rather than implied to be a full fix.
