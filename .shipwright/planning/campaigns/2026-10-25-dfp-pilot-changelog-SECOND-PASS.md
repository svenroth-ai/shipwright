# Changelog pilot: second inventory pass (draft, 2026-11-22)

Question per prose spot: (A) can code DO it at the start? (B) where the model still acts, can code CHECK afterwards that it was done (check, hook)? (C) other determinism levers.
Source: SKILL.md (440 lines) and its references, read in full; BRIEF §1 inventory, P3-P8, §3a. Status: planned = already in the BRIEF; NEW = not in it.

## A. Into code at the start

| # | Spot | Today | Proposal | Status |
|---|---|---|---|---|
| A1 | Mode, banner, plugin root, setup, steps 0-3 | model runs and reads | `prepare` | planned (P3) |
| A2 | Gate answers (version, preview, out-of-sequence) | model reads `autonomy` and two prose places that disagree (Step 3 vs "Step 4") | `prepare` returns `gates: {version: auto\|ask, preview: auto\|ask, out_of_sequence: ask}` from the gate catalog; prose says "do what `gates` says" | NEW (fixes prose points 1 and 2) |
| A3 | Upgrade-notes check (release-workflow.md, 4 steps) | model lists `docs/migrations` changes, reads each "Do you have to do anything?" line, writes a drop, says "no page changed" | code lists pages, classifies each page (plain "no" vs action), writes the drop with the page's own line plus the link, and returns the sentence "no migration page changed" itself; the model only reviews an action drop | NEW (BRIEF D20 pins it, does not move it) |
| A4 | Step 4 dry run then real run, flag rules ("never `--fail-if-empty` with `--dry-run`", "always with the real run") | prose rules about flags | `aggregate` owns the flags; rules vanish by construction | planned (P3) |
| A5 | `update-step` rule (D1: forbidden in Step C, called in Step 7) | prose prohibition | `close-phase` decides from the mode; the model cannot call it wrongly | planned (P4), D1 stays an operator decision |
| A6 | Release date | passed by the model, "same date on re-run" is a prose rule | `prepare` stores the date once in a run-state file; every later call reads it | NEW |
| A7 | Where am I after an interruption | model compares prose table `rerunning-a-release.md` with the repo | `release.py status` returns the next step | NEW |
| A8 | PR title and body | inline `\n` bug (D15) | `--body-file`, built by code from the section plus compare link | planned (P8) |
| A9 | Closing summary and the "one line" per step status | model fills the template; every field is a fact code already holds | `close-phase` prints it | NEW |
| A10 | Commit block, pathspecs, tag chain | shell in prose | `commit-and-tag` | planned (P4) |
| A11 | Steps 5.3-5.5, event record, canon C1-C3 | shell in prose | `sync`, `record-event`, `close-phase` | planned (P4) |

## B. Prevent before, check after (rule: a hook wherever the precondition is knowable before the action and a repair costs tokens, time or cannot be undone; an end check only for outcomes and as a net)

Where the CLI owns a step it refuses to continue itself (no hook needed). Hooks cover what the model still does outside the CLI: push (tag, main), PR merge, release page.

| # | Item | Mechanism | Status |
|---|---|---|---|
| B1 | Release state record written by `commit-and-tag` (version, release commit, checks passed) | `.shipwright/runtime/release_state.json` | NEW, build |
| B2 | Hook before `git push --tags`/`git push origin main`, `gh pr merge`, `gh release create`: requires the record for the current HEAD; active only while a release is in progress (no false blocks on ordinary pushes; tested) | PreToolUse hook in the changelog plugin, hooks-doc rows | NEW, build |
| B4 | Post-release `verify` (read only): tag local and on origin names the release commit, CHANGELOG matches the tag, `phase_completed` event committed, no decision drops left, PR state fits the mode, release page present or skipped with reason; run automatically at the end of `close-phase` | one command | NEW, build (net under B2) |
| B3 | Approval bound to a content hash | prevents nothing, proves nothing (a model that skips the question can compute the hash) | DROPPED |
| B5 | Stop guard for an unclosed release | an end-of-turn correction; B2 prevents the cause | DROPPED |
| B6 | `update-step` hook | covered by A5 | DROPPED |

Limit: nothing here proves the model asked the operator; A2 narrows this (ask only where the gate says `ask`).

## C. Further levers

- C1 One source for gate policy (catalog and resolver); the two prose copies are deleted, not synchronised. Build.
- C2 Placeholders resolved by the CLI. Build (falls out of P3/P4).
- C5 The P6 ratchet also flags new shell commands in SKILL.md. Build.
- Dropped: C3 (store condensed text), C4 (step timestamps), A7 `status` command (deferred until a run fails on it).

## D. Where it lands

- P3: A2, A3, A6. P4: A9, B1, B4. New small unit P4b (after P4, before P5): B2 and the hooks-doc rows; touches hooks.json, so `cross_component` integration coverage applies.
- P6: C5. P7 conversion check: asserts the A-items are gone from prose and the B-items exist.
- Stop 2 is unaffected: the lock freezes today's behaviour; a trace change (A2, A3, A9) goes through `approved_deltas.json`; B1, B2, B4 add files and checks, no trace change expected.
