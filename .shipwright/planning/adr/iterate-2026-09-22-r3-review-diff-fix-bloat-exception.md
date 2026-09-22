# Bloat exception — `plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md` raised to 522-LOC

<!-- Named by run_id per `_template-bloat-exception.md` — this heading does
     NOT claim a numeric ADR-NNN; that identity is assigned later, at
     release, by decision_log.md. `shipwright_bloat_baseline.json`'s entry
     for this file is set to `"state": "exception", "adr": "ADR-pending:
     .shipwright/planning/adr/iterate-2026-09-22-r3-review-diff-fix-bloat-exception.md"`. -->

- **Status:** accepted
- **Date:** 2026-09-22
- **Re-Review-Date:** 2026-12-22
- **Incident Reference:** `iterate-2026-09-22-r3-review-diff-fix`
  (campaign-dag-scheduler R3). The limit was crossed at exactly 400 lines
  (no prior baseline entry — this is the FIRST crossing for this file),
  wiring the new unit-scoped review-attribution pin into step 3f-bis.

## Context

R3's whole purpose is to stop `campaign-mode.md`'s pre-merge review step
(3f-bis) from silently attributing a review to the wrong unit's diff once
R5a gives every unit its own worktree (today, pre-R5a, one shared worktree
makes the bug latent, not absent — see the sub-iterate's own spec, "Why this
comes before scheduler concurrency"). `campaign-mode.md` is the orchestrator's
own runtime reference — the same category of "guaranteed-loaded prompt" text
ADR-119 and this campaign's own R2 bloat-exception (`sub-iterate-runner.md`,
400 -> 497 -> 512) already established the precedent for: a mandatory step's
*existence and exact trigger conditions* must be inline where the orchestrator
reads them, not behind a pointer it might not follow before merging a PR.

The added text is: an explicit `git -C "{project_root}"` scoping note (every
call site the spec names — the diff, the reviews.json commit/push, the
reviewed_head write — made explicit rather than relying on an unstated cwd
assumption); the new unconditional `check_review_attribution.py pin` call,
its trigger-dependent `--review-skipped` flag, its `--pr-node-id`/
`--pr-head-ref`/`--pr-base-ref` identity arguments (sourced from one `gh pr
view` call already gated by 3f-bis's own PR-existence STRICT-STOP, so these
are never null in practice), and why it dual-writes the legacy
`reviewed_head` file immediately (closing the previously-unpinned window
between diff computation and the later commit/push); a corrected comment
at 3g (the pin is now unconditional, not conditional on the cascade having
fired); and a clarifying note on which `--against` mode applies to a
reviewed vs. a below-threshold unit. +47 lines (400 -> 447).

**+4 more lines (447 -> 451), from the delegated Stage-1 spec-reviewer's
REJECT at 3f-bis (same run):** the spec-reviewer found a genuine
self-contradiction in this same passage — it defined `{project_root}` two
incompatible ways in the same step (as "THIS unit's own worktree ... a
per-unit worktree once R5a flips it" here, versus the campaign worktree
everywhere else the doc uses that placeholder, including the pin call
itself). Left standing, a post-R5a reader could read the pin as verifying
one worktree while the reviewed diff is still computed at another — the
exact misattribution bug this sub-iterate exists to close, reappearing
through the doc's own prose rather than the code. Fixed by stating plainly
that R3 scopes every named call site to `{project_root}` as it resolves
today (the shared campaign worktree), and that resolving `{project_root}`
to a genuine per-unit path is R5a's job, not this sub-iterate's — removing
the contradiction without pre-empting R5a's own scope.

**+4 more lines (451 -> 455), from the delegated Stage-2 code-reviewer's
REJECT at 3f-bis (same run):** the 3g comment documenting `head_pin`'s
source did not say that, by merge time, `$run_dir/reviewed_head` holds the
review-record's SHIPPED head, not the original pin's `reviewed_head` — the
same file is overwritten in between by 3f-bis's own post-record-commit
write. Left unstated, a future reader of 3g's `--match-head-commit` line
could reasonably (and wrongly) assume it pins against the pre-record SHA.
Fixed by naming the divergence explicitly at the 3g read site.

**+29 more lines (455 -> 484), from the delegated Stage-3 doubt-reviewer's
advisory-must-address findings at 3f-bis (same run, 2 high, 1 medium):**
(1) `shipped_head` was written `null` at pin time and never updated after —
`verify --against shipped_head` fell back to a content-blind check for
every reviewed unit, silently weaker than the `--match-head-commit` it
exists to replace. Fixed by adding a `--mode ship --shipped-head` call
right after the `reviews.json` push, `|| STRICT-STOP`, and its own
paragraph explaining why. (2) The spec's own "no PR merges unpinned"
acceptance criterion was unenforced: 3g tolerated an absent pin file. Fixed
by changing 3g's `[ -f "$run_dir/reviewed_head" ]` tolerance to
`|| STRICT-STOP`, with a corrected comment explaining why absence is no
longer tolerated. (3) The diff 3f-bis reviews and the tree the pin
certifies were resolved independently, with no equality check between
them. Fixed by capturing `diff_head` at the point the diff is computed and
asserting the pin's `reviewed_head` equals it, inline, `|| STRICT-STOP`.

**+3 more lines (484 -> 487), from the delegated Stage-2 code-reviewer's
REJECT (round 3, low):** `diff_head` was resolved AFTER the diff it was
meant to certify, so the equality check one paragraph above certified "HEAD
at pin time == HEAD at rev-parse time" rather than "HEAD at pin time == the
SHA the diff was actually computed from." Fixed by resolving `diff_head`
first and diffing against it explicitly.

**+28 more lines (487 -> 515), from the delegated Stage-3 doubt-reviewer's
round-2 advisory-must-address findings at 3f-bis (same run, 0 high, 3
medium accepted):** (1) `run_dir`/`pr_url` were assigned BEFORE the a/b/c
review-cascade spawns and read AFTER them — the only two values in this
step that genuinely cross a spawn boundary, and shell variables do not
survive across separate tool calls. Fixed by re-deriving both explicitly at
the top of the post-cascade block instead of trusting the earlier
assignment. (2) The `--mode ship` call ran AFTER the legacy `reviewed_head`
file was already written, so a STRICT-STOPped ship (e.g. an unreviewed
extra commit landing between pin and record) could leave the legacy file
holding a SHA the guard had just refused — exactly the SHA a human resuming
at 3g would `--match-head-commit` on. Fixed by reordering: `ship` now runs,
checked, before the legacy write. (3) The STRICT-STOP paragraph did not say
what "addressing" a Stage-2 finding means in practice, and the answer is
non-obvious: a new fix commit on top of the pinned tree is not a repair
path, because `ship`'s own ancestry check (added in round 3, below) refuses
it by construction. Fixed by naming the actual repair path — restart
3f-bis from the top, not commit a fix in place.

**+1 more line (515 -> 516), from a round-5 code-reviewer low finding, fixed
opportunistically:** the new repair-path sentence's hardcoded line number
("line 243's `rm -f`") would silently drift as this file keeps growing
across review rounds; reworded to describe the command instead.

## Ousterhout Argument

`campaign-mode.md` is deep by the same measure R2's precedent used: a short,
narrow set of numbered steps (3a-3h) hiding the full campaign loop's state
machine, git plumbing, and review-cascade promotion rules behind them. The
new pin call is exactly a step's *existence and exact trigger* — under what
condition `--review-skipped` is passed, and that it runs unconditionally —
which belongs inline for the same reason the trigger conditions for the
review cascade itself already do. The underlying mechanism (worktree/branch
resolution, the pin/verify field semantics, the fallback rule) is fully
delegated to `shared/scripts/lib/review_attribution.py`'s own docstring and
`R3-review-diff-fix.md`'s spec — this diff does not re-explain either.

## YAGNI Check

- The pin call is load-bearing today, not merely preparatory: without it,
  R4's "built -> merging" state and R5b's merge lane (both depend_on R3)
  would have nothing to verify against at merge time, and this sub-iterate's
  own acceptance criterion ("no campaign PR merges without
  `--match-head-commit` at any point during or after this sub-iterate")
  would be unmet the moment R5a's flip lands.
- The explicit `-C "{project_root}"` scoping is load-bearing today: it is
  the ONLY thing standing between "correct by accident because there is
  only one worktree" (today) and "correct by construction" (post-R5a) —
  removing it would silently reopen exactly the misattribution bug this
  sub-iterate exists to close, the moment R5a ships.
- No speculative generality was added: the pin call's `--project-root` and
  `--campaign-worktree` are both `{project_root}` today (pre-R5a they are
  identical); R5a is expected to change ONLY those two values at the call
  site, not this doc's prose.

## Chesterton's Fence

The 3g comment this diff corrects ("the pin is conditional, never
unconditional") was true before R3 and is false after — a bloat-avoidant
edit that left it standing would have shipped a self-contradicting doc
(3f-bis says unconditional, 3g's comment says conditional) for the sake of
a few saved lines. Correcting it in place, in the same diff that makes it
false, was preferred over leaving a footgun for the next reader.

## Consequences

`campaign-mode.md` may grow again for R4 (state-mechanics) or R5a
(wave-build-flip) — both depend_on this file's own review-lane logic and
are likely to touch 3f-bis/3g again. That is not a licence to keep growing
past this point without review: the next crossing needs its own ADR, exactly
as this one does for R2's precedent.

## Post-merge-cycle growth (516 → 522)

The PR's own CI (`gh pr checks`) runs a Tier-3 external review
(`openai/gpt-5.6-luna`, sensitive-path gate) on every push, independent of
this sub-iterate's own delegated internal cascade. That external review
caught two real defects the internal cascade's earlier rounds had not:

- **3f-bis's and 3g's bounded wait loops (`for i in $(seq 1 60); do ...
  break; sleep 5; done`) had no executable check after the loop** — only a
  trailing prose comment claiming "still not matching/MERGED after the cap
  → STRICT-STOP". Exhausting the cap without ever `break`ing fell through
  to the next step (3g, then 3h) with a stale head or an unmerged PR,
  silently treating "timed out" the same as "succeeded". Fixed by adding an
  explicit re-check statement (`[ ... ] || STRICT-STOP`) right after each
  loop — 6 lines added.
- `review_attribution.verify()`'s caller-supplied `--expect-file` was
  joined to the pin directory with no validation, permitting a crafted
  `../../...` to read outside the unit's pin directory. Fixed by routing it
  through the same `_safe_segment()` guard already used for `unit_id` — no
  line growth in this file (the fix is in `review_attribution.py`).

516 → 522 is a second crossing on top of the FIRST crossing this ADR
already covers; the `shipwright_bloat_baseline.json` entry's `current` is
bumped in the same commit as this note, per this file's own convention.

## Post-merge-cycle growth (522 → 564)

A FRESH spec-reviewer (independent of this sub-iterate's own internal
cascade, spawned by the orchestrator specifically to catch what a
self-review loop structurally cannot) REJECTed this file's 3f-bis/3g prose
on the same grounds the 516→522 entry above already names as the exact
failure mode this sub-iterate exists to close: every NAMED call site
(`git -C`, `record --payload-file`, `gh pr view`) still read `{project_root}`
as-is, with the doc's own prose explicitly deferring genuine per-unit
resolution to R5a — contradicting the pin call's own `--campaign-worktree
"{project_root}"` argument in the same passage. +42 lines (522 -> 564):

- Reworked the L253-262 passage to resolve and dual-write `$unit_wt` — THIS
  unit's own worktree, as pin's own `--json` output reports it
  (`.worktree`) — right after the pin call, to `$run_dir/unit_worktree`, so
  every later call site in 3f-bis/3g reads the SAME resolution pin already
  certified instead of re-deriving (or never deriving) its own. `{project_root}`
  itself is untouched: it remains reserved for pin/ship/verify's own
  `--project-root`/`--state`/`--campaign-worktree` arguments, resolving the
  contradiction without redefining the placeholder's existing meaning.
- The diff computation itself is the one call site that must still run
  BEFORE pin (its result feeds pin's own `--review-skipped` argument), so it
  stays at `{project_root}` — today identical to `$unit_wt` — with the
  equality check right after the pin call strengthened to also assert
  `$unit_wt`'s actual current HEAD matches, not merely pin's self-reported
  SHA.
- Converted the reviews.json add/commit/push, the REJECT-path's own
  add/commit/push, `record`'s `--payload-file` root, and 3g's `gh pr view`
  branch resolution to `git -C "$unit_wt"` / `cd "$unit_wt"`, each re-reading
  `$unit_wt` from `$run_dir/unit_worktree` at the top of its own block —
  the same file-based crossing this doc's `run_dir`/`pr_url` already use,
  since none of these blocks share a shell with the pin call that resolved
  it.

This is a THIRD crossing on top of the two this ADR already covers; the
`shipwright_bloat_baseline.json` entry's `current` is bumped to 564 in the
same commit as this note, per this file's own convention.

## Post-merge-cycle growth (564 → 583)

A SECOND fresh, independent spec-reviewer (a new fork, not the same session
that wrote the 522→564 fix) REJECTed again on a narrower version of the exact
failure mode the 522→564 entry describes: two named call sites the previous
fix had NOT actually converted still read `{project_root}`, plus a test that
now actively asserted the wrong (spec-contradicting) behavior for one of them.
+19 lines (564 -> 583):

- **The diff itself (`diff_head`/`$diff`) was still computed at
  `{project_root}`,** with this ADR's own 522→564 entry claiming it "must
  still run BEFORE pin" and therefore "stays at `{project_root}`" — a false
  necessity: `worktree` is independently readable from `loop_state.json`'s
  row for this unit, the same field `resolve_unit_identity()` reads, before
  pin ever runs. Fixed by resolving `$unit_wt` via a `jq` lookup into
  `loop_state.json` (falling back to `{project_root}` when the row carries no
  `worktree` field yet, matching pin's own fallback) immediately after the
  run_dir line, BEFORE both the pre-pin `gh pr view` and the diff
  computation, and scoping both to it.
- **3f-bis's own pre-pin `gh pr view` (computing `pr_json`) and its
  post-cascade re-derivation (computing `pr_url`) were still `{project_root}`-
  scoped** even though the spec names "the `gh pr view` branch resolution"
  as a 3f-bis call site, not only 3g's. Fixed by scoping the pre-pin call to
  the newly-resolved `$unit_wt`, and reordering the post-cascade block so
  `unit_wt=$(cat "$run_dir/unit_worktree")` runs before `pr_url=$(cd
  "$unit_wt" && gh pr view ...)` instead of after it.
- **Added a genuine path-equality check, not a HEAD-sha proxy for it:**
  comparing only `$unit_wt`'s HEAD sha against `diff_head` (the existing
  check) would let a pin that resolved a DIFFERENT worktree path landing on
  the same HEAD sha slip through unnoticed. Added `pin_wt=$(jq -r .worktree
  <<<"$pin_json"); [ "$pin_wt" = "$unit_wt" ] || STRICT-STOP` right after the
  pin call, asserting pin's own self-reported worktree agrees with the
  pre-pin resolution already used for the diff and the `gh pr view` call.
- `shared/tests/test_campaign_step_3f_bis.py` had a test
  (`test_run_dir_and_gh_pr_view_are_unit_scoped_in_3f_bis_and_3g`) that
  explicitly asserted the post-cascade `gh pr view` "is not a named
  unit-scoped call site and must stay anchored at `{project_root}`" —
  directly contradicting the spec's own text. Flipped to require `$unit_wt`
  for both 3f-bis `gh pr view` call sites; added a new test covering the
  pre-pin `$unit_wt` resolution and the pin-agreement equality check.
- Fixed a stale "Two modes:" heading (three bullets — pin/ship/verify — have
  existed since the `--mode ship` amendment) in both this sub-iterate's own
  spec and the master campaign plan document — no line growth in this file.

This is a FOURTH crossing on top of the three this ADR already covers; the
`shipwright_bloat_baseline.json` entry's `current` is bumped to 583 in the
same commit as this note, per this file's own convention.
