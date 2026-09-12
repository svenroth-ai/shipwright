# mark_status reports its outbox-vs-tracked write target

## Context

`mark_status()` derives whether a status-flip write lands in the gitignored
outbox (`.shipwright/triage.outbox.jsonl`) or the tracked store
(`.shipwright/triage.jsonl`), based on git state
(`should_route_to_outbox`: origin remote + HEAD==default branch + not-CI).
Its sibling `amend_triage_item()` reports which target it picked; `mark_status`
did not. Three same-session status flips (trg-ff6ea5f0, trg-5ae23b62,
trg-4fac93bf) landed tracked-on-a-freshly-created-branch instead of the
outbox an idle-main flip would have used, each needing its own PR before the
operator noticed — one of them sat invisible on the board for hours.

## Decision

`mark_status(..., return_item=True)` now returns a `(previous, item,
to_outbox)` triple — additive; `return_item=False` still returns the bare
`previous` scalar, unchanged. `shared/scripts/lib/triage_route.py` centralizes
`route_label`/`route_note` (the human-readable stderr note, or `None` when
neither branch applies). All four CLI writers in
`triage_cli_commands.py` — `dismiss` (json + non-json), `snooze`, `amend`,
`promote`/`defer`/`unpark` — now print/emit the route in both `--json` and
human-stderr modes; `_emit_result`'s JSON payload gained an additive `route`
key. `should_route_to_outbox` was deliberately NOT turned into a
caller-supplied parameter — only the already-derived decision is reported.

## Consequences

An operator on any branch now sees, at the moment of the write, whether a
status flip landed in the outbox (delivered by the next iterate's worktree
setup) or the tracked store (needs a PR to reach `main`). Scope grew beyond
the two direct `mark_status` call sites (`dismiss --json`, `snooze`) to also
cover `triage_promote.py`'s `promote()`/`_transition()` and the CLI's
`cmd_promote`/`_status_flip` dispatcher (shared by `dismiss`-non-json,
`defer`, `unpark`), after two independent external reviewers (GLM, OpenAI/
Codex) both flagged that `dismiss`'s non-json path stayed silent — the same
"silence should never be the report" rationale the original card states.
Extending the fix required `promote()`/`_transition()` to always call
`mark_status(..., return_item=True)` regardless of the caller's own
`include_item` flag, so a `route` key is always present in their result
dict; a Stage-1 spec-reviewer pass on that extended diff caught a real
regression this introduced — 4 pre-existing exact-dict-equality tests
(`test_triage_promote.py`, `test_triage_defer.py`) broke on the new key —
fixed in the same run by updating those assertions.

## Rationale

The derivation is deliberately never overridable (`triage.py`'s own
docstring already states the data-loss reasoning for keeping it
git-state-derived); this change only makes it self-report, per the card's
explicit constraint. Reporting through the shared `_status_flip`/`promote`
dispatch, not just the two directly-named call sites, closes the gap for
every CLI writer rather than leaving one silent by omission.

## Rejected alternatives

Turning the outbox/tracked target into a `--route` flag — rejected outright,
the card's explicit constraint; a caller-chosen route reintroduces the
data-loss risk the derivation exists to prevent. Limiting the fix to the two
literally-named call sites — rejected after two independent external
reviewers converged on the same silent-`dismiss` gap; shipping a "fixed"
CLI that still has one silent writer defeats the change's stated purpose.

## Full detail

Task brief and review cascade: `.shipwright/planning/iterate/iterate-2026-09-12-triage-route-report/` (`reviews.json`, `spec_review_reply.json`, `code_review_reply.json`, `self-review-payload.json`, `external-code-review-raw.json`, `full-diff.txt`).
