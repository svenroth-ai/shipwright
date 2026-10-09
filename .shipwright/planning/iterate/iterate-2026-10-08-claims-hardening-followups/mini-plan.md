# Mini-plan: claims-hardening follow-ups

Built as four independent edits, each with tests in `shared/tests/test_claims_hardening_followups.py`.

1. `change_type_paths._REQUIREMENT_SPECS` checked first in `_covered`.
2. `finalize_iterate._record_event`: compute `prior_id`; return it early only when the call carries no extras; otherwise build + gate the event, then return `prior_id` instead of appending.
3. `change_type_diff._stack_base` + `iterate_diff(stack_base=)`; read `event["stack_base_ref"]`.
4. `_surface_revision._resolutions` (merge-tree replay, newest-first by first-parent age) merged into `_last_writes`; `_evidence_drop_guard._deleted_after`.

## Alternative considered
Option B (derive stack base from loop state): rejected, loop state has no fixed location the gate can find, and plumbing it adds a cross-module dependency for a deprecated strategy.

## Risks
- Old git (< 2.38) cannot replay merges: surfaced with a distinct message, not the gc message.
- `stack_base_ref` is runner-stated: bounded by iterate/* + ancestor + on-trunk + not-own-branch checks.
- Deletion dating by directory mtime errs toward refusing.

## External review reconciliation (GLM + GPT, both `revise`)
- "No extras" vs "no claims" (both): the predicate is `not event_extras` on purpose: a caller that supplies ANY extras is asserting a record and is gated; the Stop-hook repair pass supplies none. Metadata-only extras are therefore gated too (accepted; no caller does it).
- Re-run with diverging claims keeps the originally recorded event (GLM): accepted. The gate refuses an invalid re-run; it does not rewrite history (events are append-only).
- Stack base with trunk merges between base and HEAD (GLM): over-flags (fails closed), never under-flags. Accepted and documented.
- Conflict resolved by keeping trunk bytes (GPT): covered by design, the replay names conflicted PATHS, not content; evidence staged before the merge then differs from the merge result and is stale. Old git is a distinct message, not a gc message.
- Directory mtime (GLM): a deletion itself bumps the parent directory mtime; only a tool resetting mtimes could hide it. Accepted, errs toward refusing otherwise.
- Injection (GLM): every git call is an argv list (no shell); the ref is regex-checked and resolved with `rev-parse --verify`.

## Internal Plan Review reconciliation (opus-plan-reviewer)
Fixed: evil merges (the merge is replayed and the recorded tree diffed against git's auto-merge, so hand edits in cleanly merged files count too); shape read from the trunk fork point even with a stack base; branch refs resolved in `refs/heads`/`refs/remotes` only (no tag shadowing); the "sits on the trunk" check removed (it refused after trunk was merged into the unit; now only over-flags); catalog predicate delegated to `lib.requirement_impact.is_requirement_spec` plus `.shipwright/agent_docs/spec.md`; distinct message for any merge-tree replay failure; stack-base refusals carry their own repair text; runner doc says to omit the field for the first stacked unit; `%ct` limits documented. Tests added for each. Accepted: an alias branch at HEAD still shrinks a caller's own diff (the name is runner-stated); a re-run with diverging claims keeps the stored event.
