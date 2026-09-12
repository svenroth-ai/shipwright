# Retention cap raised to 200 for headroom against branch concurrency

Amends `iterate-2026-08-15-retention-cap-parallel-merge-retention-approximate.md`.

## Context

That ADR investigated `append_iterate_entry.py`'s per-branch retention prune
and found `_apply_retention` re-derives its eviction set from the full
on-disk state on every call, so a merge overshoot self-heals on the very
next append. It modeled and tested that self-heal against roughly 2
concurrent overshooting branches and, on that basis, declined to add new
merge-time or periodic-sweep machinery — accepting a bounded, self-healing
"~50, not exactly" cap instead.

Branch concurrency has grown well past that model since. `git branch -a`
now lists dozens of open `iterate/*` branches, several active in parallel
worktrees at once. A same-day investigation (2026-09-11) measured
`origin/main` sitting at 54 unpinned-adjacent entries against the cap of 50,
and traced several branches each independently pruning a *different* victim
set of other runs' entry files — not the same shared eviction the self-heal
model assumed, but scattered ones, because each branch's fork-point view of
"the oldest entries" differed. One such deletion reached `origin/main` as an
incidental side effect of an unrelated PR (`#726`'s squash removed
`iterate-2026-08-26-fr-table-text-from-named-col.json`).

That investigation's original further claim — that this pruning caused four
PRs to conflict simultaneously and stall the whole queue — was independently
retracted the same day. `git merge-tree --write-tree` showed all four
branches in question merge clean against `origin/main`; GitHub's `mergeable`
flag had simply gone stale on branches sitting many commits behind and
cleared once they moved. **This ADR does not claim or fix a merge-conflict
problem.** What it addresses is narrower: the self-heal model's 2-branch
sizing no longer matches actual concurrency, so the mechanism spends more of
its time in the "overshoot, scatter-prune, self-heal" cycle than the prior
ADR anticipated.

Verified at this run's original fork point (`origin/main` @ `0cea78813`): 53
canonical `<run_id>.json` summaries, 2 pinned via
`iterate_retention_pins`, 51 unpinned against the old cap of 50 — the "+1"
steady state the prior ADR modeled, not the more dramatic overshoot the
2026-09-11 investigation measured a day earlier. Self-heal is visibly doing
its job between merges; the residual risk is headroom, not today's count.

**Re-measured after rebasing onto `origin/main` @ `89c4a39a9`** (two PRs
landed on this run's original base in the interim: `#727`, and `#736`, which
deliberately pruned the entry backlog): 35 canonical summaries, 2 pinned, 33
unpinned — lower than the original 51, not higher, because `#736` is a
one-time manual cleanup, not a mechanism change; it buys roughly 17 more
appends before the old cap of 50 would start firing again, which is exactly
the kind of temporary breathing room this ADR is not relying on. The decision
below is unchanged; it is re-measured, not re-argued.

## Decision

Raise `ITERATE_RETENTION` from 50 to 200. No change to the pruning
mechanism, the self-heal behavior, or `iterate_retention_pins` semantics —
only the threshold. 200 is chosen as well above the current working set (53
canonical entries) and well above realistic concurrent-branch fan-out, so
under normal load no branch prunes at all and the scatter-prune symptom
stops firing. Full iterate history remains available regardless of the cap
in `shipwright_events.jsonl`, as the tool's own docstring already states.

**Revisit trigger, stated so the deferral is visible rather than silent**
(external review flagged the earlier draft for omitting this): if the
unpinned count on `origin/main` is observed approaching ~150, or the
cross-run scatter-pruning symptom recurs at the new cap, the alternative the
2026-08-15 ADR already declined — moving retention out of the per-branch
append path entirely, to a main-only post-merge step or a dedicated
maintenance command — should be re-evaluated rather than raising the cap
again. A third bump of the same knob would be evidence the per-branch model
itself, not its sizing, is the problem.

That re-evaluation should ask a cheaper question first: whether the
directory needs a count bound at all. `read_all_entries` has zero
non-test callers, and the only directory-level consumer,
`verifiers/iterate_checks.check_iterate_history_has_run_id`, needs exactly
one file — the current run's. Nothing in this investigation established that
anything reads the entries retention evicts; this ADR does not widen scope to
test that premise, but the next person to hit the revisit trigger should
check it before reaching for a bigger bound, since "does eviction need to
happen at all" is strictly cheaper to answer than "what should the new bound
be."

## Rejected alternatives (same investigation, ranked lower by its own
## leverage ordering)

- **Move retention to a main-only post-merge step or maintenance command.**
  This is exactly the "new merge-time or periodic-sweep machinery" the
  2026-08-15 ADR already weighed and declined, on the grounds this framework
  has no merge-time hook and a periodic sweep would be a new scheduled
  surface. Nothing in this investigation changes that cost side of the
  trade — it only shows the existing self-heal has less headroom than
  assumed, which the cap bump addresses directly. Left as the revisit-
  trigger escalation above rather than built now.
- **F6/pre-commit guard refusing to stage a deletion of another run's entry
  file under `.shipwright/agent_docs/iterates/`.** Retention's only job is
  to evict the oldest *unpinned* entries, which by construction belong to
  other runs — that is the feature working as designed, not a distinguishable
  fault. A guard shaped this way would either always fire (defeating
  retention outright) or need the same "is this deletion within the
  mechanism's accepted overshoot bound" judgment `test_retention_merge_overshoot.py`
  already encodes as a test, making the guard a duplicate of existing
  coverage rather than new protection. No such guard was built.

## Consequences

- `.shipwright/agent_docs/iterates/` can now hold up to ~200 unpinned
  summary files before pruning resumes, versus ~50 before. This is a larger
  but still bounded window; `shipwright_events.jsonl` remains the durable
  full history regardless.
- The six prose/code locations that state the cap
  (`append_iterate_entry.py`'s docstring and inline comment,
  `plugins/shipwright-iterate/skills/iterate/references/F5c.md`,
  `docs/hooks-and-pipeline.md`, two spots in `docs/guide.md`, and
  `verifiers/iterate_checks.py`'s `_no_entry_detail()` operator diagnostic
  — the last three surfaced by Internal Plan Review and Stage-3 doubt
  review, not the initial grep) now all say 200 (the last one reads
  `ITERATE_RETENTION` symbolically so it can't drift again);
  `shared/tests/test_retention_cap_headroom.py` guards all six from
  drifting back out of sync.
- Two pre-existing tests in `test_append_iterate_entry.py`
  (`test_retention_trims_to_keep_last`,
  `test_retention_does_not_prune_during_migration`) hardcoded fixture entry
  counts (52, 60) sized for the old cap of 50; both were updated to build
  `ITERATE_RETENTION + N` entries instead, so they continue exercising the
  trim regardless of the constant's value.
- If a future change ever removes or weakens `_apply_retention`'s
  "re-read the full directory on every call" behavior, the self-heal claim
  underlying both this ADR and the one it amends would need to be revisited
  — `test_retention_merge_overshoot.py` would catch that regression
  directly.
- `_apply_retention` re-reads and parses the full iterates directory on
  every `append_iterate_entry` call; raising the cap 4x means this per-call
  I/O now scans up to ~200 small JSON files at steady state instead of ~50.
  Negligible at this file count on local disk; noted here so a future
  investigation into F5c latency doesn't have to rediscover it (internal
  plan review, below).

## Review

Reviewed via `external_review.py --mode iterate` (mini-plan vs. iterate
spec) and `--mode architecture` (brief vs. spec): architecture pass approved
2-of-2 (GLM, GPT via Codex CLI); iterate-mode plan review returned
approve (GLM) / revise (GPT), not a contradiction requiring operator
resolution. The GPT revise asked for (1) the capacity basis and a concrete
revisit threshold in the ADR, and (2) a repository-wide check for other
references to the old cap value. Both addressed: the revisit trigger above,
and a repo-wide grep for `ITERATE_RETENTION`/`~50`/"cap of 50" confirming no
other production doc or code states the cap value (matches only historical,
append-only, or unrelated hits — e.g. `CHANGELOG.md`'s past entries, which
are not edited retroactively, and an unrelated "~50 iterates" FR-prose
count in `docs/hooks-and-pipeline.md`).

**Internal Plan Review** (`shipwright-plan:opus-plan-reviewer`, medium+
gate before Branch A/B/C — run here against the spec + mini-plan):
`severity: medium`. That first grep pattern (`ITERATE_RETENTION`/`~50`/"cap
of 50") missed two real stale mentions phrased differently —
`docs/hooks-and-pipeline.md:4466` ("applies 50-entry retention") and
`docs/guide.md:1889,2374` ("last 50 entries retained" / "F5c, 50-entry
retention") — both describing this exact tool, both fixed in this diff to
say 200, both now guarded by
`test_retention_cap_headroom.py::test_hooks_and_pipeline_doc_states_current_cap`
and `::test_guide_doc_states_current_cap`. `append_phase_history.py`'s
separate, genuinely-unrelated 50-entries-per-phase mentions
(`hooks-and-pipeline.md:4501,4536`, `guide.md:2717`) were correctly left
untouched — different constant, different mechanism. Second finding (low,
the per-call directory-scan cost) is recorded in Consequences above.
Status: 2 findings, both fixed.

**Stage-2 code review** (internal `code-reviewer`): 5 findings, all fixed —
a medium-severity performance one (two tests looped the full
`append_iterate_entry` transaction 200+ times each; rewritten to seed
fixtures directly on disk via a new `_write_entries_directly()` helper,
cutting the retention suite's runtime from 22.4s to 7.0s) plus 4 low-severity
readability/correctness ones (stale "three locations" wording in two places,
dead-code date reassignment, and a count-only assertion strengthened to an
exact survivor-set check). `external_code` recorded `not_run` — the internal
cascade completed, so it wasn't mandatory (F11's `>=1 of code/external_code`
floor is satisfied by `code`).

**Stage-3 doubt review** (adversarial, biased to disprove): confirmed the
core mechanics — `_write_entries_directly()` produces entries indistinguishable
from the real transaction's output to `_apply_retention`'s sort/eviction
logic, and the strengthened survivor-set assertion has no off-by-one error.
One medium finding: `verifiers/iterate_checks.py`'s `_no_entry_detail()`
still hardcoded "50-entry retention window" in operator-facing diagnostic
text — a sixth stale location none of the prior three review passes caught.
Fixed (now reads `ITERATE_RETENTION` symbolically) and added as a sixth
guarded location in the regression test. One low finding (the revisit
trigger is manual/observational, not an automated alert) accepted as-is —
already substantively addressed and out of this run's scope to automate.
