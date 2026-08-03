# External plan review — iterate-2026-08-01-grade-snapshot-dirty-capture

Provider: `openrouter` · reviewers: `openai` (success, **revise**), `gemini`
(degraded — reply cut off at `finish_reason=length`, one finding legible).
`reviews_succeeded: 1`, contradiction: not comparable (only one full answer).

**Outcome: the plan changed.** Gemini's high-severity reducibility finding was
accepted and it removed five of the eight GPT findings outright, because the
mechanism they were defending no longer exists.

## The architectural change

The plan proposed a run-scoped JSON store,
`.shipwright/runs/<run_id>/source_state.json`, to carry one boolean across the
`finalize_iterate` → `update_compliance` **subprocess** boundary.

Gemini (approach/reducibility, high): a file-backed store is an over-production for
a single boolean; subprocesses inherit environment variables for free.

Verified before accepting — the store's only unique capability is reaching a
process that is **not a descendant** of the capturer, and that consumer does not
exist:

- `emit_grade_snapshot` has exactly **one** caller (`update_compliance.py:185`), so
  capture at that module's entry covers every automatic emission.
- **No hook and no shell script invokes `update_compliance`** (grepped across
  `hooks.json`, `*.sh`, and every `hooks/` package). There is no detached producer.

So the file store would have carried five defensive mechanisms — atomic exclusive
create, path-safe run-id validation, containment checks, tree-identity binding, a
versioned schema — to serve no reachable case. Dropped per *Simplicity First*.

**Adopted transport:** `capture_dirty()` writes its result into `os.environ`
(`SHIPWRIGHT_SOURCE_DIRTY` + `SHIPWRIGHT_SOURCE_DIRTY_RUN`). `subprocess.run`
inherits the parent environment by default, so a parent needs **one line at its
entry** and no `env=` plumbing at the spawn site. The value is honoured only when
the recorded run id matches the reader's — the "run-id-primary stamp" the card asks
for, without a file.

## Dispositions

| # | Sev | Finding | Disposition |
|---|---|---|---|
| G1 | high | file store is an over-production for one boolean | **ACCEPTED** — store dropped; env transport adopted (above) |
| 1 | high | "first capture wins" is not race-safe across processes; partial JSON reads | **DISSOLVED** — no shared mutable file. Env is per-process-tree and written once before any spawn |
| 2 | high | `--run-id` feeds a filesystem path → traversal / symlink escape | **DISSOLVED** — no path is built from the run id. It is still passed through `safe_run_id`, which already refuses whitespace, control/format characters and unsubstituted `{}` placeholders |
| 3 | med | "non-wired paths degrade honestly" is too strong | **ACCEPTED, with the inventory measured.** `emit_grade_snapshot` has one caller, so the child-entry capture covers every automatic emission. Of the four spawning parents only `finalize_iterate` writes tracked files before spawning (`_record_event` → `shipwright_events.jsonl`); `finalize_security_compliance` writes nothing first. The residual — a *sibling* process that wrote earlier in the same run — is named in the spec's Out-of-scope, not papered over |
| 4 | med | a run id reused across worktrees attaches a prior capture to a different tree | **ACCEPTED IN PART** — env does not persist across runs the way a file would, which removes the durable form of this. The run-id binding is kept so a stale export in an operator shell cannot be honoured by a different run |
| 5 | med | a semantically-valid-but-wrong store (`{"dirty":"false"}`) must not be trusted | **DISSOLVED as a store schema; kept as a parse rule.** The env value is accepted only as exactly `"1"` or `"0"`; anything else reads as unknown |
| 6 | med | other consumers/validators of the wire shape may break | **ACCEPTED — checked, and it is additive.** No in-repo exact-keyset assertion on a `grade_snapshot` exists (the one `event == {}` pins "raises before mutating"), and `change_history.collect_events` filters the type out. Historical events simply lack the key. The cross-repo WebUI note goes in `docs/hooks-and-pipeline.md` |
| 7 | low | `--run-id` vs `SHIPWRIGHT_RUN_ID` precedence is ambiguous | **ACCEPTED** — explicit `--run-id` wins; env is the fallback. Pinned by a test |
| 8 | low | "cannot dirty the tree" also depends on the file not already being tracked | **DISSOLVED** — no file is written |

## What both reviewers agreed was right

Capture-before-write as the core approach; reusing the `source_state` seam rather
than rebuilding it; and omitting the field when the state is unknown rather than
guessing a default.
