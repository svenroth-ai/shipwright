# Iterate Spec: index-readers-adr-lock

- **Run ID:** iterate-2026-08-08-index-readers-adr-lock
- **Type:** bug (overridden from classify_intent.py's `feature` @0.6 — see
  Self-Review below)
- **Complexity:** medium (overridden from Stage-1 `small` @0.6 — see
  Self-Review below)
- **Status:** implemented (review cascade complete — spec PASS, code APPROVE,
  external code-review revise/approve resolved, doubt not_applicable;
  finalization F0-F0.5 green, F1-F12 in progress)

## Self-Review: two classifier overrides at First Actions

1. **Intent.** `classify_intent.py` returned `feature` (confidence 0.8) —
   the keyword `add` (from "add a duplicate-number detection test") tripped
   `FEATURE_KEYWORDS` ahead of the many literal occurrences of `fix`/`defect`.
   Overridden to `bug`: both items are framed by the operator as verified
   defects — defect 1 is an already-broken guarantee (a `Read` call caps at
   2,000 lines, the mandated file is 4,379), defect 2 explicitly demands
   root-cause analysis ("FIX THE CAUSE, NOT THE HISTORY").
2. **Complexity.** Stage 1 returned `small` (confidence 0.6, keyword-only —
   no diff exists yet to drive the cross-file/cross-plugin signal). Overridden
   to `medium`: the change spans 4 skill files across 4 plugins, requires
   designing a concurrency-safe allocation mechanism (not a local edit), adds
   a new test class, and produces an operator-facing collision report. The
   operator's own brief conditions the Opus + external plan-review gates on
   "medium or more," which is itself positive evidence for this tier.

Recorded per `plan.json`'s `complexity_override` field (same reasoning,
machine-readable copy for the WebUI Plan-Card).

## Goal

Two defects on the same "instruction promises more than the system delivers"
surface, both verified against `main` at PR #605 (`b7615e64`):

1. `decision_log_index.md` (331 lines, 13x compression vs `decision_log.md`'s
   4,379) has zero readers in `plugins/`, while four skill files across four
   plugins still instruct "read completely" a file that no single `Read` call
   can return in full — an already-broken guarantee, not a future risk.
2. ADR spec-folder filenames collide — **6 numbers, 15 files** as of this
   run's branch point (097, 120, 125, 126, 127, **128**; the operator's brief
   counted 5/13 before ADR-128 collided via the two most-recently-merged
   PRs, #604/#605 — see Plan Review below) — because the `<NNN>` prefix is
   chosen by unaided agent judgment at branch time, with no coordination
   across parallel iterates sharing a base.

## Repo Scout Evidence (AC2/AC3 — added per external-review finding 6)

- **AC2 (templates ship none of the four instructions):** `Grep "ALL.{0,30}architectural decisions|read completely|read the complete file"` (case-insensitive) across `**/*.md` returned exactly the four known call sites (`context-loading.md:11`, `first-actions.md:103` in shipwright-plan, `first-actions.md:63` in shipwright-build, `step-1-interview.md:16`) plus one incidental prose match in an already-merged ADR (`127-decision-log-drops-index.md:36`, itself describing this exact fix) and one unrelated match in an iterate note about transcripts. Separately, `Grep "decision_log"` scoped to `shared/templates/` returned 4 files (`claude-md-template.md`, `shipwright-gitignore.template`, `rules/migrations.md.template`, `agent-docs/architecture.md.template`) — none contain the "read completely" phrasing; the gitignore-template hit is the `/.shipwright/agent_docs/*.tmp` line from the already-merged decision-log-index producer work, unrelated to reading.
- **AC3 (section-builder.md + deploy/design/adopt mentions are writers):** Read `plugins/shipwright-build/agents/section-builder.md:353-380` directly — Step 14 "Update Decision Log" calls `write_decision_log.py`, a write, not a read instruction. Read the matched spans in `plugins/shipwright-deploy/skills/deploy/references/rollback-strategy.md`, `rollback-discipline.md` — both are "log every rollback in decision_log.md" (write). Read `plugins/shipwright-design/skills/design/references/review-loop.md:83-233` — three matches, all "add to decision_log.md" / "Decision Log Format" for the design skill's own writes. Read all four `plugins/shipwright-adopt/skills/adopt/references/*.md` matches — scaffold-generation mentions and a `prior_art_harvester` source list, none instruct a read-completely.

## Acceptance Criteria

- [x] AC1 — The four mandated-reader instructions (`shipwright-iterate`
      context-loading.md, `shipwright-build`/`shipwright-plan` first-actions.md,
      `shipwright-project` step-1-interview.md) read `decision_log_index.md`
      first and name a concrete trigger for reading a full `decision_log.md`
      entry (index title/supersession match, or an `ADR-NNN` citation already
      present in loaded context), plus a named fallback for "index has no
      matching entry" (grep the heading / offset-limit read) — never
      "read completely."
- [x] AC1b — A committed drift-guard test asserts each of the four files
      references `decision_log_index.md` and contains no "read...completely"
      / "ALL...decisions" phrasing bound to `decision_log.md`, so AC1 cannot
      silently regress after this run ends (opus-plan-reviewer finding —
      AC5 had a permanent guard and AC1 did not).
- [x] AC2 — `shared/templates/` confirmed to ship none of these four
      instructions to adopted projects (verified, not assumed).
- [x] AC3 — `section-builder.md:355` and the design/deploy/adopt
      `decision_log.md` mentions confirmed as writers, not readers (verified
      by reading each, not re-grepping).
- [x] AC4 — New ADR spec-folder files are named `<run_id_sanitized>-<slug>.md`
      (via `lib.iterate_entry.sanitize_run_id_for_filename`, the same
      sanitizer `write_decision_drop.py` already uses) instead of a
      hand-guessed `<NNN>-slug.md` — structurally collision-proof, since
      `run_id` is already globally unique, with **no allocator, lock, or
      watermark** (operator decision, superseding the Round-1 allocator
      design and Round-2 merge-time-check alternative — see Design Notes).
      `F3.md`'s naming instruction and worked example are updated to match,
      and the file's own `# ` heading must not claim a numeric `ADR-NNN` it
      does not have.
- [x] AC5 — A new drift-guard test fails on any *new* file under
      `.shipwright/planning/adr/` that reverts to the old `<NNN>-slug.md`
      shape and collides with an existing file's number (backsliding guard,
      not an allocator guard). Anti-ratchet baseline is **regenerated from
      the tree at build time** (never hand-transcribed — finding 1: the
      operator's 5/13 count was already stale by the time this run
      branched), rule = per pinned number `actual_files ⊆ pinned_files`
      (shrink/rename-away allowed) and any unpinned number has at most one
      file (finding 7) — both sides share one `parse_adr_number()` helper
      exported from `lib.adr_index` so the guard can't disagree with the
      real index renderer.
- [x] AC6 — A report enumerating the colliding files (count TBD by the
      build-time regeneration in AC5 — 15 files / 6 numbers measured at
      Repo Scout time, expect drift by build time given ~1 new pair per
      parallel-merge pair observed), citation counts for each colliding
      number elsewhere in the repo, and a proposed resolution left to the
      operator (no renaming in this run). Filed under
      `.shipwright/planning/iterate/`, not `.shipwright/planning/adr/`
      (finding 6 — the latter would render into the committed ADR INDEX.md
      as a pseudo-entry).

## Spec Impact

- **Classification:** none
- **NONE justification:** both defects are internal SDLC-framework mechanics
  (skill context-loading discipline; ADR-numbering concurrency safety) —
  implementation detail of already-declared capabilities (e.g. FR-01.10
  `/shipwright-compliance` evidence), not a new or changed user-observable
  product capability. No `spec.md` FR describes "how the iterate skill loads
  decision_log.md" or "how ADR spec files are numbered" at the FR altitude.

## Out of Scope

- Renaming any of the 15 existing colliding ADR spec files (explicit operator
  instruction — a wrong rename is worse than a known collision; report only).
- Reconciling `spec_ref` filenames against the `decision_log.md`-assigned
  `ADR-NNN` at release-fold time — a separate, pre-existing drift class
  (`adr_index.py`'s own "Known limit" docstring), still not touched: the
  final design (below) sidesteps it entirely rather than closing it.
- Any allocator, lock, or watermark mechanism. Considered at length (two
  design rounds, both internal and external review) and abandoned — see
  Design Notes: FINAL DESIGN.

## Design Notes

**Defect 1.** No design surface — prose edits to four skill reference files,
matching the existing `context-loading.md` item 4a style (already-merged
TC3.1/PR #605) for tone/format consistency.

**Defect 2 — design history (superseded, kept for the record).** Two earlier
designs were fully worked out and then abandoned; both are kept here rather
than deleted, because the reasoning for rejecting them is exactly what stops
this problem from being re-litigated the same way twice.

*Round 1 — a claim-time allocator.* Reserve a number exclusively at F3 time,
via a dedicated lock file plus a persisted, cross-worktree watermark
(resolved against the main repo root, self-healing from `git worktree list`,
idempotent per `(run_id, slug)`, fail-closed on missing state). Internal
Opus review found and this design fixed 11 real bugs in it (self-deadlock
from a shared lock, watermark loss being unrecoverable, silent degradation,
path-traversal via the slug — full table below). Then **both external
reviewers rejected the approach itself**, not its bugs: openai `reject`,
deepseek `revise`-toward-the-same-alternative. Their point, independently
reached: a lock + durable cross-worktree state is a standing mechanism
disproportionate to a rare, cheaply-fixed-at-merge-time problem, and every
future ADR author now has to route through it and reason about its failure
modes.

*Round 2 — a merge-time blocking check* (both external reviewers'
recommendation). Keep numbering exactly as today (an agent's best guess at
branch time), add a CI/F11 gate that blocks the merge if the guessed number
already exists on `origin/main` or collides within the same branch. No new
runtime mechanism — but presented to the operator (this is a `reject`
verdict from one of two reviewers, and this skill's own protocol requires
stopping for the operator on a `reject` rather than deciding alone), the
operator asked the sharper question neither design round had asked: **why
does the long-form spec file need a number *at all* at branch time**, given
`decision_log.md`'s own short entries already avoid exactly this problem by
not being numbered until release?

**FINAL DESIGN (operator decision) — remove the premature number, don't
allocate or detect one.** `.shipwright/planning/adr/<NNN>-slug.md` picked
`<NNN>` only because the file needed *some* unique name at branch time, when
the real `ADR-NNN` (assigned once, serialized, at `/shipwright-changelog`
release — the same mechanism that already makes `decision_log.md`'s own
numbering collision-proof) is not yet known. The number was never load-bearing
— confirmed by reading `aggregate_decisions.py`: it renders whatever
`spec_ref` string a drop carries, verbatim, and never reconciles it against
the number it assigns to the short entry. **New spec files are named
`<run_id_sanitized>-<slug>.md`** (`lib.iterate_entry.sanitize_run_id_for_filename`,
the exact sanitizer `write_decision_drop.py` already uses for the JSON drop's
own filename) — no number, so nothing to collide over, since `run_id` is
already globally unique by construction (date + description).

This needs **no new production code for the renderer or the fold**:
`lib/adr_index.py::_entries()` already has a freeform-name branch (the
`_template-*`/`_archive-*` files already exercise it today — see
`_archive-agent-doc-updates.md`'s existing INDEX.md row) that renders a
non-numeric filename using its own `#` heading, sorted after every numbered
entry. `write_decision_log._format_spec_ref_link` already renders whatever
filename `--spec-ref` is given, numeric or not. The only changes are: (1)
`F3.md`'s naming instruction and worked example switch from `<NNN>-<slug>.md`
to `<run_id_sanitized>-<slug>.md`, and the file's own `# ` heading must NOT
claim a numeric `ADR-NNN` it does not have (stating a false number is worse
than stating none); (2) a drift-guard test that only needs to catch
*backsliding* into the old numeric-collision pattern going forward — no
allocator to test, since there is nothing left to allocate.

This resolves the external reviewers' core objection more completely than
their own suggested alternative: proportionality was their word for it, and
zero new standing mechanism is more proportionate than either a lock or a
merge-time check. It also removes every one of the internal review's 11
findings by removing their subject — recorded below for provenance, not
because any of them still need fixing.

**Accepted consequence, unchanged from Round 1's analysis.** The spec-folder
filename and `decision_log.md`'s own fold-assigned `ADR-NNN` were already two
independent identities (confirmed via `_ADR_FILENAME_RE`/`aggregate_decisions.py`
reading above); this design makes that explicit rather than papering over it
with a look-alike number. Cross-references to a long-form spec should use the
filename/slug or `run_id`, never a bare number the file no longer claims to
have earned.

**Drift-guard test.** Catches backsliding, not allocation: after this run,
any *new* file under `.shipwright/planning/adr/` matching the old
`<NNN>-slug.md` shape whose number collides with an existing file's number is
a process violation (someone reverted to hand-guessing a number) and fails
the guard. The baseline of currently-colliding numbers (15 files / 6 numbers
measured at Repo Scout time — see AC5) is a **committed data file, regenerated
by a separate, explicitly-invoked maintainer command**, never hand-transcribed
and never regenerated live inside the guard test itself (external-review
finding 5 — a self-regenerating guard would silently absorb a same-run
collision as "baseline" and protect nothing). Rule: for every PINNED number,
`actual_files ⊆ pinned_files` (shrinking — e.g. renaming a grandfathered file
away — always allowed); for every number NOT in the baseline, at most one
file. Guard and `adr_index._entries()` share one exported
`parse_adr_number()` so they cannot disagree on what counts as numeric.

**Index-first fix's own growth ceiling, named (Plan Review finding, low
severity, still applies — orthogonal to defect 2's redesign).**
`decision_log_index.md` inherits the same unbounded-growth curve it repairs —
at the current ADR rate it will itself eventually cross the 2,000-line `Read`
cap. Out of scope to solve now (no evidence it is close), but the four reader
instructions name an explicit fallback for "the index has no matching entry"
(grep `decision_log.md` for the `### ADR-NNN` heading, or an offset/limit
read) so the trigger is not silently unusable in exactly the case — an ADR
recorded but not yet indexed, or a stale index — where it matters most.

## Affected Boundaries

n/a — the final design adds no new producer/consumer pair. `write_decision_drop.py`'s
existing `--spec-ref` link-rendering and `lib/adr_index.py`'s existing
freeform-filename rendering are both reused unchanged; only the *filename
convention* an agent follows (skill prose in `F3.md`) changes.

## Plan Review

### Internal (Opus, model=opus per operator instruction — mandatory at medium+)

**Verdict: high-severity findings, all folded in before external review** (see
Design Notes above for the resolution of each). Summary of the 11 findings:

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | high | Baseline stale: 15 files/6 numbers on disk, not 13/5 (ADR-128 collided via #604/#605 after the brief was written) | Baseline regenerated from the tree at build time, never hand-transcribed; AC5/AC6 reworded |
| 2 | high | Reusing `adr_index.lock` self-deadlocks (no reentrancy) and creates unrelated contention with release-time index renders | Dedicated `adr_spec_number.lock`, sub-millisecond critical section |
| 3 | high | Watermark floor invisible to in-flight sibling worktrees; gitignored dir is cleanable | Floor = max(watermark, main-root max, every linked worktree's max via `git worktree list`) |
| 4 | medium | `resolve_main_repo_root()` degrades to worktree-local silently on several real paths | CLI states resolved scope explicitly every call; degraded path is loud on stderr |
| 5 | medium | No idempotency; number and filename can diverge (recreates the original defect in miniature) | Idempotent per `run_id`; CLI prints/returns the exact target path |
| 6 | medium | Collision report under `.shipwright/planning/adr/` would render as a pseudo-ADR in the committed INDEX.md | Report moved to `.shipwright/planning/iterate/` |
| 7 | medium | Anti-ratchet rule ambiguous between count and membership — both readings exploitable | `actual ⊆ pinned` per number, shared `parse_adr_number()` helper |
| 8 | medium | AC1 (the primary defect) had no permanent regression guard, unlike AC5 | AC1b added: committed drift-guard test |
| 9 | medium | Missing same-diff obligations: marketplace sync (plugin-side files) + guide.md Appendix B check (new shipped command) | Added to mini-plan work breakdown |
| 10 | low | Allocator formally widens the pre-existing spec-folder-number vs. log-number divergence | Stated explicitly as an accepted consequence |
| 11 | low | Index-first fix inherits the same unbounded-growth curve; no fallback named for "no matching index entry" | Fallback named in the reader instruction |

Direct answers on the four questions the brief asked the reviewer to weigh:
same-machine scope is defensible once findings 3-4 are fixed (durability +
loud degradation, not the scope itself); resolving the watermark against the
main root is correct, resolving the *shared* lock there was the actual bug
(finding 2); the anti-ratchet design is enforceable only under the subset
rule (finding 7); Spec Impact NONE holds (neither defect is FR-altitude per
ADR-112's own boundary).

### External (medium+ auto) — deepseek + openai via OpenRouter

**Verdict: both `revise` (no contradiction — comparable, in agreement).**
First call: openai returned `status: degraded` ("provider returned an empty
reply") — retried once per this repo's own truncated/degraded-review
handling; second call both providers answered.

| # | Source | Sev | Finding | Resolution |
|---|---|---|---|---|
| 1 | openai | high | "Same-machine" scope is imprecise: two independent clones of the same repo on one machine do NOT coordinate (only linked worktrees of ONE main root do) | Design Notes reworded: scope is "linked worktrees sharing one main repository root," not "same machine" — a narrower, honest claim |
| 2 | openai | high | Timing window: state deleted AFTER a claim but BEFORE the agent writes the spec file leaves the number unrecoverable by folder-scan (no file exists yet to find) — a later allocation can reissue it | F3.md instructs writing the spec file at the returned path IMMEDIATELY, same step, no intervening actions; allocator FAILS CLOSED (does not silently reset to the folder-scan floor) when its state file is missing/corrupt while `git worktree list` shows other active iterate worktrees — that combination is a signal of state loss mid-flight, not a fresh clone, and must stop rather than guess |
| 3 | openai | medium | Degraded `WORKTREE-LOCAL` mode still completes an unsafe allocation by default | Reworded with finding 2: unresolvable main root is now a FAILURE by default, not a silent degrade; no separate opt-in flag added (YAGNI — no caller needs it) |
| 4 | openai (+ deepseek, 1st pass) | medium/security | Slug used raw in path construction (traversal risk); idempotent replay with a changed slug or a pre-existing unrelated target could overwrite | Slug validated against a safe-filename allowlist (`^[a-z0-9][a-z0-9-]{0,79}$`) before use; resolved target asserted to stay under `ADR_SPEC_FOLDER`; idempotency now keyed on `(run_id, slug)` — a replay with the same `run_id` but a DIFFERENT slug errors loudly instead of silently returning the old claim |
| 5 | openai | medium | Anti-ratchet regeneration ambiguity — if the guard test regenerates-then-compares, a same-run collision becomes "baseline" and the guard protects nothing | Design Notes corrected: guard reads only the COMMITTED baseline file; regeneration is a separate, explicit, human-invoked command; a meta-test pins that the guard imports nothing from the regen tool |
| 6 | openai | medium | AC2/AC3 have no recorded evidence of the verification work | Added `## Repo Scout Evidence` section below, citing the actual greps/reads performed |
| 7 | openai | medium | Stated verification command misses the new `test_mandated_reader_index_first.py` | `## Verification` runner command broadened to name all three new test modules explicitly |
| 8 | openai | low | Marketplace-sync timing concern ("stale PR" if sync changes tracked content) | **Reviewed, no change** — `update-marketplace.sh` refreshes the local `~/.claude/plugins/cache/` runtime cache, a directory outside this repo's git history; it does not modify or generate any file this PR commits, so there is no "stale PR" to re-push. Recorded as rejected-with-reason, not silently dropped. |
| 9 | deepseek | medium | Idempotent replay with a different slug creates a number/path mismatch | Same fix as #4 — `(run_id, slug)` keying, loud error on mismatch |
| 10 | deepseek | low | `.shipwright/locks/` may not exist (fresh clone / `git clean`) | Allocator `mkdir(parents=True, exist_ok=True)` before opening lock/watermark |
| 11 | deepseek | low | A pruned-but-listed worktree in `git worktree list --porcelain` could crash the scan with `FileNotFoundError` | Caught per-worktree (`FileNotFoundError`/`OSError`), skipped with a warning, scan continues |

### Architecture Review — Branch A second call (`--mode architecture`), over `architecture_brief.md`

**Verdict: openai `reject`, deepseek `revise`** — a `reject` from either
reviewer requires STOP-and-ask-the-operator per this skill's own protocol; no
build proceeded on the allocator design past this point.

Both reviewers converged on the same alternative to the brief's Option A (the
allocator): openai rejected on proportionality grounds — a standing lock +
durable cross-worktree state is disproportionate to a rare, cheaply-detected
problem, and recommended the brief's **Option D, hardened into a real gate**
(detect-and-block at merge time, i.e. Round 2 above) rather than allocate
pre-emptively. deepseek did not reject outright but `revise`d toward the same
place, additionally flagging that Option A's "one machine" scope was a
capability boundary the brief itself hadn't stress-tested (the finding folded
into external-review finding 1 above, before the architecture call was even
made — the same imprecision surfaced twice, independently).

Presented to the operator as three options (switch to the reviewers' Round-2
merge-time check / keep the Round-1 allocator over the reviewers' objection /
pause), the operator did not pick any of them. Instead: *"if we do it that
way, don't we just have the change-drop there? I currently don't understand
why the number is a problem, since it's only numbered in the changelog
anyway — please explain before we continue."* This was the right challenge:
neither reviewer, nor the brief's own four options, had asked why the
spec-folder file needs a number *at branch time* at all, when
`decision_log.md`'s own numbering already defers exactly this to release
time. After explaining the two-numbering-identities distinction (spec-folder
filename vs. `decision_log.md`'s fold-assigned `ADR-NNN` — see Design Notes),
the operator chose a fifth option, outside the brief's original A/B/C/D and
outside both reviewers' recommendation: **remove the number entirely, name by
`run_id`/slug.** This is not a compromise between the reviewers' positions —
it satisfies openai's proportionality objection more completely than openai's
own suggested fix (zero standing mechanism, not a lighter one), and it makes
deepseek's scope concern moot (nothing is being claimed, so there is nothing
to scope). The 15 existing colliding files are explicitly left unrenamed per
the operator's decision (see Out of Scope).

## External-Code-Review-Findings

`external_review.py --mode code`, run over the full diff (`git diff HEAD`
plus intent-to-added new files) at finalization. deepseek `approve` (no
findings — "no concrete defects were found in the diff... ship-as-is"),
openai `revise` (3 findings). Verdicts comparable, no contradiction
(`deepseek=approve, openai=revise` — one step apart).

| # | Source | Sev | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | medium | `_template-bloat-exception.md`'s heading still read `# ADR-XXX: ...`, contradicting AC4/F3's rule that a new run-id-named spec file must not claim a numeric ADR-NNN in its own heading | accepted-and-fixed — heading changed to `# Bloat exception — ...`; comment block reworded to state the heading must not claim a numeric ADR-NNN, and to call the release-assigned identity out explicitly |
| 2 | openai | low | `group_f.py`'s module docstring (F4, F7) still advertised `.shipwright/planning/adr/<run_id>-…` — the unsanitized form — instead of `<run_id_sanitized>-<slug>.md` | accepted-and-fixed — both docstring lines updated to name `sanitize_run_id_for_filename` explicitly, matching the runtime finding-message text fixed earlier in this run |
| 3 | openai | low | `test_mandated_reader_index_first.py`'s `_PROMISES_COMPLETE_READ` only matched complete/entire/whole/full-read phrasing; the historical "read ALL the decisions" wording (no such token) could regress undetected | accepted-and-fixed — added a second alternation (`_ALL_DECISIONS_PHRASE`) plus a mutation-style regression test (`test_the_all_decisions_phrasing_alone_is_still_caught`) proving the bare "ALL ... decisions" wording is now caught |

All three re-verified: `shared/tests/test_mandated_reader_index_first.py` (13
tests, was 12 — new mutation test), `plugins/shipwright-compliance` audit
group tests (78 tests) and `uvx ruff@0.15.15 check .` all green after the
fixes.

## Confidence Calibration

- **Boundaries touched:** none new (Affected Boundaries = n/a — this run
  changes skill/audit *prose* and adds pure-function test/tooling code that
  reuses existing producer/consumer pairs; no new file format, no new I/O
  boundary).
- **Empirical probes run:**
  - Ran `shared/tests/test_mandated_reader_index_first.py` RED before the
    Defect-1 edits (12/12 failed on the fallback-wording check; the
    index-reference and no-longer-promises-complete checks were also red),
    then GREEN after (12/12 passed) — proves the regression guard actually
    guards, not just passes trivially.
  - Ran `rebuild_adr_collision_baseline.py` against the real repo tree:
    regenerated 6 colliding numbers / 15 files, matching the Repo Scout
    count exactly (no drift between Scout time and build time, contrary to
    the "expect drift" note in AC6 — nothing merged in between).
  - Ran the new `test_adr_index_no_duplicate_numbers.py` against the real
    committed baseline (green) plus two synthetic probes proving the guard
    can actually fail (`test_guard_actually_fails_on_a_fresh_unpinned_collision`)
    and that shrinking a pinned pair is never punished
    (`test_shrinking_a_pinned_number_is_allowed`).
  - Repo-wide `git grep` sweep for `<NNN>-<slug>` / `<NNN>-…` after the
    planned file list was believed complete — found 6 additional LIVE
    (non-historical) files still instructing the retired convention
    (`F2.md`, `F6.md`, `F-finalize-bundle.md`, `_template-bloat-exception.md`,
    `docs/guide.md` ×3, `group_f.py` ×6) that the mini-plan had missed or
    pre-judged as "no change needed." Fixed. Historical iterate/campaign
    planning docs deliberately left untouched (they document what was true
    when written).
  - **This sweep was still incomplete** — `spec-reviewer` (Stage 1 review,
    below) caught 5 more live files the grep pass missed
    (`write_decision_log.py`, `write_decision_drop.py`,
    `decision_drop.schema.json`, `sub-iterate-runner.md`,
    `code-reviewer.md`) plus a real gap in AC5 (`_entries()` wasn't actually
    calling the shared `parse_adr_number()` helper it claimed to share).
    Both fixed post-review; see `## Plan Review` is NOT where this is
    recorded — this is a BUILD-time review finding, tracked here instead.
    The fix for the second one initially introduced its own regression
    (dropped zero-padding in the rendered label), caught by
    `test_adr_index_writing.py` failing before it was ever shown to a
    reviewer — the empirical-probe discipline above is what caught it, not
    a second review pass.
- **Test Completeness Ledger:**

  | Behavior | Status | Evidence |
  |---|---|---|
  | AC1: 4 readers reference the index | tested | `test_reader_names_the_index_first` ×4 |
  | AC1: no "read completely" promise survives | tested | `test_reader_no_longer_promises_a_complete_read` ×4 |
  | AC1: fallback for no-index-match is named | tested | `test_reader_names_a_fallback_for_no_index_match` ×4 |
  | AC2: templates ship none of the 4 instructions | tested | Repo Scout grep evidence (`## Repo Scout Evidence`) — no automated regression guard (a template *gaining* the phrase is caught by nothing mechanical); accepted as a one-time verification, consistent with how AC3 is handled |
  | AC3: section-builder/design/deploy/adopt are writers | tested | Repo Scout direct-read evidence |
  | AC4: new ADR files named by run_id, F3.md/docs updated | tested | `git grep` sweep (above) + manual read of every changed file |
  | AC5: drift guard fails on new numeric collision, passes on today's tree | tested | `test_adr_index_no_duplicate_numbers.py` (5 tests, incl. 2 synthetic fail-mode probes) |
  | AC6: collision report with citation counts + resolution options | tested | `.shipwright/planning/iterate/iterate-2026-08-08-index-readers-adr-lock-adr-collision-report.md`, counts reproduced via `git grep -c` |
  | `parse_adr_number()` extraction is behavior-preserving | tested | full `test_adr_index*.py` suite green post-refactor (37 tests) |
  | No regression across the rest of the monorepo | tested | full `shared/tests` run: 8852 passed, 32 skipped (pre-existing, unrelated), 0 failed |

  0 untested-testable.
- **Confidence-pattern check:** Asymptote (depth) — the Defect-1 guard test
  was proven to fail before the fix and pass after (not just "written and
  green"), and the Defect-2 guard was proven to fail on a synthetic fresh
  collision, not only to pass on the pinned baseline; both satisfy the
  "prove it can fail" bar. Coverage (breadth) — the repo-wide `git grep`
  sweep for the retired naming pattern went beyond the mini-plan's
  pre-enumerated file list and found real gaps (a live compliance-audit
  advisory message, a live template, three more skill references), which is
  exactly the failure mode a asymptote-only check (test the files I already
  planned to touch) would have missed.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run pytest shared/tests/test_adr_index_no_duplicate_numbers.py shared/tests/test_mandated_reader_index_first.py shared/tests/test_adr_index*.py shared/tests/test_write_decision_log.py shared/tests/test_decision_log_index_producers.py -v`
  (external-review finding 7 — broadened to explicitly name every new test
  module, not a `-k` filter that could silently miss one; allocator test
  module dropped along with the allocator design)
- **Evidence path:** `.shipwright/runs/iterate-2026-08-08-index-readers-adr-lock/f05-surface/`
