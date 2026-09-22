# Bloat exception — `shared/scripts/lib/review_attribution.py` raised above the 300-LOC limit (current: see `shipwright_bloat_baseline.json`)

<!-- Named by run_id per `_template-bloat-exception.md` — this heading does
     NOT claim a numeric ADR-NNN; that identity is assigned later, at
     release, by decision_log.md. `shipwright_bloat_baseline.json`'s entry
     for this file is set to `"state": "exception", "adr": "ADR-pending:
     .shipwright/planning/adr/iterate-2026-09-22-r3-review-diff-fix-review-attribution-bloat-exception.md"`. -->

- **Status:** accepted
- **Date:** 2026-09-22
- **Re-Review-Date:** 2026-12-22
- **Incident Reference:** `iterate-2026-09-22-r3-review-diff-fix`
  (campaign-dag-scheduler R3). A fresh independent code-reviewer (round 7
  verify) found this file crossed the 300-LOC limit with no baseline entry
  at all, while three OTHER files this same PR grew (`campaign-mode.md`,
  `test_campaign_step_3f_bis.py`, `conftest.py`) already had proper
  `state: "exception"` entries — an internal inconsistency filed here, in
  round 8, to close it.

## Context

`review_attribution.py` is the new module R3 introduces: three CLI modes
(`pin`/`ship`/`verify`) over one JSON pin file, replacing the unpinned
"whatever branch/worktree the merge step happens to resolve independently"
hazard the whole sub-iterate exists to close. It started small and grew
across 8 review rounds (spec/code/doubt cascades, both internal and one
external Tier-3 pass on the live PR), each addition closing a genuine,
independently-found correctness gap: `_single_parent()` replacing a bare
`git rev-parse {sha}^` that mis-resolved merge commits; `_safe_segment()`
blocking path-traversal and Windows drive-relative escapes on
`--expect-file`; `refs/heads/{branch}` full qualification closing a
tag-collision and option-injection route; `ship()`'s tip → already-shipped
→ ancestry ordering and its STRICT-STOP on a non-`reviewed_head` parent;
`verify --against shipped_head` refusing to ALLOW on a `null` value instead
of silently falling back to a content-blind parent check. None of this is
incidental growth — every line traces to a finding a reviewer could
reproduce.

## Ousterhout Argument

One deep module: a single external interface (three CLI modes reading and
writing one pin-file shape) hides substantial internal complexity (git
ref resolution, path-safety, ancestry verification, JSON schema
validation) that every caller — `campaign-mode.md`'s 3f-bis/3g steps — is
better off not reimplementing. Splitting `pin`/`ship`/`verify` into
separate files would multiply the shared git-plumbing and validation
helpers (`_run_git`, `_safe_segment`, `_single_parent`, `_find_unit`)
across three modules instead of one, trading LOC-per-file for real
duplication.

## YAGNI Check

Nothing here is speculative. Every function and branch is exercised by
`shared/tests/test_review_attribution.py` and traces to either the R3
spec's own three-mode contract or a specific reviewer finding recorded in
this campaign's review-cascade payloads. No unused modes, no
not-yet-needed CLI flags, no abstraction built ahead of a second caller.

## Chesterton's Fence

There is no removed guard here to account for — this is a wholly new
module. The one fence worth naming: the file does NOT try to make `pin`
idempotent-and-silent on a re-run with identical inputs (a tempting
simplification) — `pin` always re-resolves and re-validates, because a
loop_state.json row can change (a lease can move a unit's worktree)
between two pin calls on the same unit, and silently trusting a cached
result would reintroduce exactly the divergent-resolution hazard R3
exists to close.

## Decision

`current` raised from unfiled to 458, `limit` 300, `state: "exception"`.
Further growth is expected to be modest going forward — R4/R5b's own specs
already name specific new call sites (`verify --against shipped_head`) but
those are consumers of this module's existing CLI surface, not new modes.

### Round 14 growth (458 -> 477)

External Tier-3 PR review on the live PR found `_resolve()` — the shared
`pin`/`ship`/`verify` preamble — let `json.JSONDecodeError`, `OSError`
(from a missing state file) and structural errors from
`resolve_unit_identity()` (`AttributeError`/`TypeError` on a malformed
`state`/unit entry, e.g. a list instead of an object) escape uncaught; the
CLI's `except ReviewAttributionError` does not catch any of those, so a
missing or malformed `loop_state.json` produced a raw Python traceback
instead of the documented `check_review_attribution <mode>: BLOCK`
message. Fixed by wrapping `_resolve()`'s body in `try`/`except` and
re-raising each failure as `ReviewAttributionError` with a clear message.
Diagnostic-quality gap, not a fail-open: the exit code was already 1
either way, so no `|| STRICT-STOP` caller was ever fooled into treating
this as success.

### Round 14c growth (477 -> 500)

The external Tier-3 reviewer re-ran on the round-14 push and raised three
findings: two repeats of already-rebutted items (shell-interpolation of
`{branch}`/`{id}`/`{loop_id}` in `campaign-mode.md`, and `fires=<1 or 0>`)
— see the master ADR's "External Tier-3 PR Review" section, now extended
with a round-2 note — plus one new, genuine finding: `verify()`/`ship()`
re-resolve `worktree` fresh from `loop_state.json` on every call but never
cross-checked it against the value `pin()` already recorded in the pin
file, even though that data was already sitting right there. Added
`_check_pinned_worktree()`, called from both `verify()` and `ship()`
immediately after `_load_pin()`, raising `ReviewAttributionError` when the
row's current `worktree` disagrees with the pinned one.

### Round 3 growth (500 -> 509)

A third external Tier-3 pass found two more genuine, independently-real
gaps: `_load_pin()` still caught only `(json.JSONDecodeError, KeyError)`,
missing `(OSError, UnicodeError)` for the same reason `_resolve()`'s own
fix closed it a round ago — widened to match. And
`resolve_unit_identity()` validated `worktree`/`branch` by truthiness
only, so a malformed loop_state row (e.g. a numeric `worktree`) passed
straight through to `_run_git`, which stringifies it into `git -C
<worktree> ...` — git then fails with an opaque exit-code error naming a
bad path, not the real cause; added an explicit `isinstance(..., str)`
check for both fields, raised before any git call, giving a specific,
documented `ReviewAttributionError` instead. Confirmed both red-before
(temporarily reverting each fix) / green-after.

**Correction (code-review round 3 verify):** the paragraph above
originally claimed this closed an "uncaught `TypeError`" — a fresh
reviewer traced `_run_git`'s actual argv construction (`str(cwd)`
stringifies before use) and found no `TypeError` was ever reachable;
pre-fix, the malformed row already failed with a clean
`ReviewAttributionError` from git's own non-zero exit code, just naming
the wrong thing (a bad path) instead of the real cause (a malformed
loop_state row). The fix is still worthwhile — an earlier, more specific
failure — corrected here rather than left standing as an inaccurate
record, per this file's own "no hindsight-inaccurate record" standard.

### Round 3c growth (509 -> 518 -> 522)

Two catch-up items land together here since neither got its own entry when
it landed:

- The "Correction" paragraph above (code-review round 3 verify) itself
  edited this file's rationale text, growing it 509 -> 518 with no matching
  growth entry — a fresh code-reviewer pass on round 3's diff flagged this
  file's own inconsistency (the sibling test ADR got its "Round 3b" entry,
  this one didn't).
- A second fresh code-reviewer pass (round 3b verify) found the branch
  message split introduced by round 3's fix (`_check pinned worktree`'s
  sibling change in `resolve_unit_identity`) had itself regressed: checking
  `isinstance(branch, str)` before checking for an absent/empty branch made
  a genuinely missing `branch` key report the wrong diagnostic
  ("non-string branch (None)" instead of "has no branch recorded").
  Reordered to check `branch is None or branch == ""` first, `isinstance`
  second — 518 -> 522. Confirmed red-before (temporarily reverting to the
  pre-fix ordering, `test_resolve_unit_identity_reports_a_missing_branch_key_as_absent_not_non_string`
  failed with exactly the predicted wrong message) / green-after.

## Consequences

`review_attribution.py` remains the single source of truth for pin/ship/
verify logic; `campaign-mode.md`'s 3f-bis/3g steps and any future
sub-iterate (R4, R5a, R5b) that needs to resolve or verify a unit's
reviewed/shipped state call into this module rather than reimplementing
git-plumbing inline in a runtime prompt.

## Rejected alternatives

- **Split into `review_pin.py` / `review_ship.py` / `review_verify.py`**:
  rejected — each mode shares `_run_git`, `_safe_segment`,
  `_single_parent`, `_find_unit`/`resolve_unit_identity`, and the pin-file
  JSON schema; three files would either duplicate ~150 LOC of shared
  plumbing or introduce a fourth shared-helpers module, net LOC-neutral at
  best while fragmenting one coherent CLI's implementation across three
  files a caller has to cross-reference.
- **Defer filing until a later "Group H" bloat audit** (the ADR's own
  original disposition, per the code-reviewer's finding): rejected in this
  round — leaving 928 combined LOC (this file + its test) unfiled while
  three much smaller crossings in the same PR were properly filed is the
  inconsistency this ADR exists to close, not a reason to keep deferring it.
