# iterate-2026-07-28-f11-verifies-own-run

**Anchor:** `trg-e3ca4314` (IT-3) — consolidates `trg-81fbf8ed`, `trg-51a57370`,
`trg-64372769`, `trg-ffddd6b9`.
**Brief:** `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
**Type:** bug · **Complexity:** medium (classifier said `small`; overridden — see §0)
**Spec Impact:** NONE · **Affected FRs:** FR-01.11

---

## 0. Scope, and the two things measured before building

**Complexity override.** `classify_complexity` returned `small` with a
`touches_migrations` risk flag. Both are prose artefacts: the message contains
"schema_version bump", and no migration is touched. `risk_detectors` on the real
diff is authoritative (memory: classifier keyword false-positives). The change
alters a gate contract across four checks, adds a recordable gate row, and
touches `churn_merge` — medium.

**The IT-0 precondition is already satisfied.** The brief says IT-3 is blocked
until `record_review_pass.py` (395 lines) is baselined. Measured on
`origin/main` @ `8b7b6eb7` (IT-0 landed as #492):

```
{"path": "shared/scripts/tools/record_review_pass.py",
 "limit": 300, "current": 395, "state": "grandfathered"}
```

Present — but sitting **exactly on its ceiling**, so this run must not add a
line to it. It does not: every change there is a symbol swap
(`REVIEW_TYPES` → `RECORDABLE_TYPES`), net zero lines.

**`cross_component` fires, deliberately.** AC-5 puts the "what is derived"
predicate in `shared/scripts/lib/churn_merge.py`, which matches
`CROSS_COMPONENT_FILE_PATTERNS`. That is the correct home — the whole point of
AC-5 is that the verifier and the churn resolver must not hold two definitions —
so the run takes the flag and pays for it with a real integration test
(`category:"integration"` in the ledger).

---

## 1. Root causes (one per item — the Iron Law, four times)

### 1.1 `trg-81fbf8ed` — the gate reads a file the gate's own procedure rewound

`shipwright_test_results.json` is in `DERIVED_SNAPSHOTS`
(`lib/derived_snapshots.py:48` — via `churn_merge.TEST_RESULTS`). At F11,
`ensure_current` → `integrate_main` calls `restore_derived_to_head`
(`tools/integrate_main.py:129`), which `git checkout HEAD --`s that path. The
iterate no longer commits it, so `HEAD`'s copy is **main's** — the previous
run's evidence.

Measured on this worktree at fork point: `iterate_latest.run_id` reads
`iterate-2026-07-28-docs-placement-rule`. Any F11 running here today would
validate that run's ledger.

**Three readers share the defect**, not one:

| Reader | Compares `run_id`? | Consequence |
|---|---|---|
| `check_test_completeness_ledger` (`iterate_checks.py:598`) | no | passes on another run's ledger |
| `check_surface_verification` (`iterate_checks.py:504`) | no | passes on another run's E2E evidence |
| `declared_removals` (`silent_revert.py:269`) | no | another run's declarations **excuse this run's removals** |

The third is the worst direction and is not in the card: it does not merely
fail to catch, it actively licenses.

The ledger check already *prefers* a per-run F5c entry — but no producer writes
`test_completeness` into that entry today (checked: real entries carry
`adr · branch · complexity · date · run_id · spec · tests_passed · type`), so
the shared-file fallback is the live path.

The sibling `check_session_handoff_fresh` (`handoff_freshness.py:71`) has the
same root cause and gets it right: exact-value comparison against a named
marker, and *"never a silent SKIP"*. That is the pattern to copy.

### 1.2 `trg-51a57370` — "completed" is not the same claim as "happened"

`_code_review_floor` (`review_record_check.py:180`) accepts
`status == "completed"` on `code` or `external_code`. Nothing on that row must
be evidence: `record --status completed` with `--from` omitted defaults to the
`none` adapter, `build_findings` returns `[]`, and the row lands as
`findings_count 0 / provider null / raw_excerpt null / recorded_by "none"` —
byte-indistinguishable from a fabricated line.

Second path, same function's neighbourhood: `check_review_record:89-95` reads
the complexity from `find_entry_by_run_id` and returns **SKIPPED** when the
entry is absent. `check_test_completeness_ledger:630` does the same.

### 1.3 `trg-64372769` — the HARD-GATE that cannot testify

`REVIEW_TYPES` (`review_record_schema.py:45`) has five entries and no `spec`.
Stage 1 (`spec-reviewer`) is the *first and blocking* gate of the cascade, and a
`code` row sourced `code-reviewer` is byte-identical whether Stage 1 passed
first or was never spawned.

The card's prescribed fix — sixth `REVIEW_TYPES` entry + `schema_version` bump —
**is empirically disqualified.** Read in the consumer repo at
`C:/01_Development/shipwright-webui`:

```ts
// server/src/core/mission-context/review-record.ts:261
if (record.schema_version !== RECORD_SCHEMA_VERSION) return invalid(...)   // strict ==, not <=
// server/src/core/mission-context/review-record.ts:276
const unknown = Object.keys(byType).filter((k) => !REVIEW_TYPES.includes(...));
if (unknown.length > 0) return invalid(...)                                 // 5-type list
```

and, decisively, `review-state.ts:240-250`:

> *"A record that is present but INVALID does not fall through."*

An invalid record renders **all five rows as unreadable with a data-integrity
note** — it does not degrade to the marker fallback. So either half of the naive
change (the bump, or the sixth `reviews` key) would make every new run's Mission
Review artifact report a corruption fault on a record that is perfectly fine.
That is the artifact's own failure mode, inflicted on every run, from a repo
this iterate may not change (the brief: *"anderes Repo — kann kein Teil eines
Monorepo-Iterates sein"*).

**Decision (deviation from the card, recorded):** deliver Stage-1 provability in
a shape the pinned consumer cannot see. `reviews` stays exactly the five pinned
types at `schema_version 1`; the gate stages this repo enforces live in a
sibling top-level `gates` object. The consumer inspects only `schema_version`,
`run_id` and `reviews`, so it is untouched. Promotion of `gates.spec` into
`reviews` becomes a one-line change **once the webui ships a tolerant reader** —
that is the cross-repo decision the card asked for, and it is now a follow-up
with a measured reason rather than a blocked prerequisite.

`schema_version` deliberately stays `1`: the addition is optional and additive,
older records remain valid unchanged, and a bump would communicate nothing to
the one consumer while breaking it. See §5 for why that is not a dodge.

### 1.4 `trg-ffddd6b9` — three narrowings deferred from #488

1. **Derived-definition drift.** `silent_revert.py:151` asks
   `path in CHURN_ALLOWLIST`; the resolver's own `churn_merge.classify:124` asks
   `rel in CHURN_ALLOWLIST or is_campaign_status(rel)`. A campaign
   `status.json` is regenerated churn to one and authored content to the other.
2. **A checkable comparison skipped.** `resolve_default_ref`
   (`silent_revert_reading.py:84`) has three outcomes, not the four its
   docstring claims: when `origin/<default>` resolves but the local ref does
   not, `merge-base --is-ancestor` fails and it returns the *unresolvable local*
   ref, so `check_no_silent_revert`'s pre-flight SKIPs a comparison that was
   available.
3. **Two notions of "the same line".** Lines are compared after `.strip()`
   (leading/trailing only); `replacement_hunks` diffs with `-w`
   (whitespace-insensitive throughout). A line whose *internal* whitespace
   changed is therefore a finding that no hunk can pair with, so it reports.
   Safe direction, but the two must mean one thing.

---

## 2. Acceptance Criteria

**AC-1 — an `iterate_latest` block that names another run is not evidence.**
One shared reader returning a **typed state** — `current` · `foreign` ·
`unattributed` · `malformed` · `missing` — and every caller fails closed on
every non-`current` state, naming both run ids and the repair. Applies to
`check_test_completeness_ledger`, `check_surface_verification`, and the
silent-revert `declared_removals`.

**AC-1b — the evidence has a home the restore cannot reach.**
`check_surface_verification` prefers the per-run F5c entry exactly as the ledger
check already does, and F5c documents both blocks as entry fields. Without this,
AC-1 converts a false green into a permanent red (external review, gemini/high).

**AC-2 — the medium+ code-review floor requires evidence, not a status.**
The satisfying row must carry at least one of: a non-empty `findings` list, a
**non-blank** `provider`, a **non-blank** `raw_excerpt`, or a **non-blank**
`recorded_by` that is not the `none` adapter. Whitespace is not evidence
(external review, openai #6).

**AC-3 — a missing F5c entry fails, it does not skip.**
`check_review_record` and `check_test_completeness_ledger` report the absent
entry and name F5c, instead of returning SKIPPED with `complexity=unknown`.

**AC-4 — Stage 1 can prove it ran.**
A `spec` row is recordable and must be answered like every other pass — an
**absent** `gates` section counts as unanswered for the current run, so
optionality buys back-compat for old records and nothing for a live gate
(external review, openai #1). And a `code` row recorded `completed` while `spec`
is not `completed` fails the gate: Stage 2 cannot legitimately have run without
its own HARD-GATE preceding it.

`external_code` is **deliberately outside** this invariant (external review,
openai #4 asked for the explicit definition). Per `iteration-reviews.md` the
spec-compliance and doubt roles are not cascaded to external providers, so a run
carried by `external_code` alone correctly has `spec` closed `not_run` with a
disposition. Requiring `spec` there would block the documented external route.
The existing `_substitution_note` already reports that cost on the passing
result; AC-4 does not turn it into a block.

**AC-5 — one definition of "derived".**
`churn_merge` owns the predicate; `classify` and the silent-revert filter both
call it, and a campaign `status.json` is derived to both.

**AC-6 — a resolvable remote wins over an unresolvable local ref.**
`resolve_default_ref` returns `origin/<default>` when the local ref does not
resolve, so the comparison runs instead of being skipped.

**AC-7 — "the same line" means one thing.**
**One** equivalence relation on both sides: `normalize_line` (`str.split()`
semantics) for the finder, and `git diff -b` for the hunk pairer. They agree on
every whitespace shape but one, and the survivor errs harmlessly (a hunk with
nothing to pair, never a finding with no hunk) — measured table in the
`normalize_line` docstring.

*Corrected during code review.* The first draft said "matching the `-w` the hunk
pairer already relies on", and `-w` was measured NOT to match: it ignores
whitespace entirely, so it reads a token merge (`a b` → `ab`) as no change while
the finder reads it as one — leaving exactly the unanswerable finding the AC
exists to remove. Two options were offered (collapse the finder to `-w`
semantics, or change both to one rule); a third was measured and taken. `-b`
means "ignore changes in the *amount* of whitespace", which is `" ".join(split())`
almost exactly, and it preserves the anti-collapse property `-w` was chosen for
(a pure re-indent still yields no hunk). Collapsing the finder instead was
rejected: it would suppress a real content change, and it would destroy the
whitespace tokenisation `tokens_in_order` depends on.

---

## 2b. External plan review — every finding, and what it changed

Providers: openrouter → `gemini` (**degraded**: reply truncated at
`finish_reason=length`, verdict unavailable) + `openai` (**`revise`**).
Only one reviewer answered, so the contradiction check reports
`requires_resolution` — resolved here by acting on both, including the partial.

| # | Finding | Sev | Response |
|---|---|---|---|
| gemini | AC-1 fails closed but the root cause (`restore_derived_to_head` rewinding the file) stays — this would break F11 **permanently for all runs** | high | **ACCEPTED — plan changed.** New **AC-1b**. `derived_snapshots.py` belongs to IT-11 and `integrate_main` is not this run's blast radius, but `f5c_argv` passes the entry dict through verbatim and `validate_iterate_entry` tolerates extra keys, so the per-run entry (explicitly NOT a derived snapshot) is already a viable durable home. The ledger check already prefers it; `check_surface_verification` now does too, and F5c documents both blocks. |
| openai 1 | absent `gates` could satisfy the schema and bypass AC-4 | med | **ACCEPTED.** AC-4 amended: absent section = unanswered for a live run. |
| openai 2 | inventory every `REVIEW_TYPES` use before splitting the vocabulary | med | **ACCEPTED.** Done in §6 probe P4; regression test pins `reviews` at exactly the five pinned keys while `spec` persists only under `gates`. |
| openai 3 | the webui compatibility claim is source inspection, not an executable check | med | **PARTLY ACCEPTED.** A cross-repo TypeScript suite cannot run from this commit's CI. Instead a test **mirrors the consumer's two guards** as executable assertions over a real record (`schema_version == 1`; `set(reviews)` == the five pinned types), plus a legacy record with no `gates`. The residual — that the mirror could drift from the consumer — is stated, not hidden. |
| openai 4 | does the Stage-1 prerequisite apply to `external_code` too? | med | **ACCEPTED as a definition.** No — and AC-4 now says so and why. |
| openai 5 | the attributed reader needs a typed failure contract | med | **ACCEPTED.** AC-1 amended to name the five states. |
| openai 6 | `provider: ""` would count as evidence | med | **ACCEPTED.** AC-2 amended to non-blank. |
| openai 7 | scope the hard failure to a resolved active run | med | **ACCEPTED, and the probe corrected my own assumption.** I expected one non-test caller; P5 found **two**. `verify_iterate_finalization.main` (`--run-id` is `required=True`) and `verify_phase.dispatch_iterate`, which returns a hard failure *before* dispatching when `run_id` is falsy, and which `dispatch_all` skips outright without one. No `hooks.json` wires `verify_phase --phase iterate`, so no automated caller can arrive with the `""`/`"unknown"` sentinels that `_iterate_run_id.py` exists for — those reach `spec_checks`, not `iterate_checks`. Fail-closed is safe on both paths. The failure is worded "F5c did not run", never "not applicable". |
| openai 8 | keep `is_derived_churn` pure; watch import direction | low | **ACCEPTED.** It lands in `churn_merge` next to `classify`, whose only imports are stdlib; `silent_revert` already imports from that module, so no new direction. |
| openai 9 | pin one whitespace normalisation | low | **ACCEPTED.** AC-7 amended. |

---

## 2c. External CODE review — six rounds, twelve findings

Providers: openrouter → `gemini` + `openai`. Gemini returned **approve** in
rounds 1, 2, 3 and 6 (degraded/truncated in 4 and 5). OpenAI drove the rounds.
**Ten of twelve findings accepted**; the two declined are argued below rather
than waved off.

The internal cascade could not run (see §2d), so this is the pass that carried
the review — which is why it was run to convergence instead of once.

| # | Finding | Sev | Outcome |
|---|---|---|---|
| 1.1 | `check_silent_revert_for_run` gained `run_id` but `run_all_checks` still called it without one — every declaration would resolve foreign and legitimate removals would be reported as reverts | **high** | **REAL, mine.** Fixed. My tests exercised the function and not the call site, which is exactly how it got through; added `test_run_all_checks_hands_the_run_id_to_the_silent_revert_check`. |
| 1.2 | the unattributed `declared_removals` stayed public | med | Accepted — made private, `__all__` trimmed. Measured: zero importers repo-wide. |
| 1.3 | "no tests added" | med | **Not a defect** — I had scoped the reviewer's diff to `shared/scripts` + skills, so it could not see the five new test files. Re-run on the full diff from round 2 on. |
| 2.1 | `normalize_line` is not `-w` equivalent | med | **Accepted, with a better fix than either option offered** — see AC-7. `git diff -b` *is* `" ".join(split())` semantics; the pairer moved to it. Rejected collapsing the finder to `-w`: it would suppress real content changes and destroy the tokenisation `tokens_in_order` needs. |
| 2.2 | the wrapper only disclosed an attribution problem when the check already failed | med | Accepted — a disregarded declaration now reports on a clean run too, as a WARNING. |
| 3.1 | AC-7 text said "match `-w`" while the code deliberately did not | med | Accepted — the AC was corrected to what was decided, and why. |
| 3.2 | the Stage-1 remediation advertised `--from spec-reviewer`, which `argparse` rejects | med | **REAL, mine.** The gate told the operator to run a command that fails — the exact "blocks with no way forward" trap this run is about. Fixed, and pinned by a test that parses the message against the real `ADAPTERS`. |
| 4.1 | F5c documented `test_completeness` + `surface_verification` but the reader also prefers `declared_removals` there | med | Accepted — F5c template and prose updated, end-to-end test added. |
| 4.2 | removing `declared_removals` from `__all__` breaks importers | low | **Measured away** — zero importers; internal verifier module, not a published surface. |
| 5.1 | `{"iterate_latest": ["stale"]}` crashes with `AttributeError` (`or {}` guards None, not a truthy list) | med | **REAL, mine.** Fixed + test. |
| 5.2 | `run_id=""` default lets an unconverted caller silently change behaviour | med | Accepted — now required and keyword-only. |
| 5.3 | the AC-7 tests could not tell `-b` from `-w` | med | **REAL, and worse than reported.** I had believed I added a discriminating test; flipping production back to `-w` showed the suite still green. The patch that "added" it had silently no-op'd (a bash heredoc mangled the escapes). Rewritten via the editor, **verified red under `-w` and green under `-b`** before being kept. |
| 6.1 | every non-current state should block, even with no declarations anywhere | med | **HALF accepted.** `malformed` now reports unconditionally — it is the one state where "none declared" cannot be told from "could not read". **Declined** for missing/unattributed/foreign-with-nothing: see below. |
| 6.2 | the test codifying that fail-open should be replaced | med | **Declined, and rewritten to say why** rather than deleted. |

**The one substantive disagreement (6.1 / 6.2).** The reviewer reads AC-1's
"fail closed on every non-`current` state" as: block whenever the shared block
is non-current and the F5c entry carries no `declared_removals`. Every iterate
would hit that — the entry does not carry the field by default and the restore
makes the shared file foreign — so the fix is a mandatory
`declared_removals: []` on 100% of runs to prove a negative.

It buys nothing. AC-1's purpose is that a foreign block is never USED as
evidence, and that already holds: the caller receives `[]`, nothing is exempt,
and every dropped line still blocks. The asymmetry with the ledger and F0.5
gates is real and intended — those demand evidence in order to PASS, so absence
must block them; declarations are an *exception* mechanism, whose absence is the
normal state of a healthy run. A gate red on every run is the failure mode this
repo keeps having to un-teach. The half that was a genuine hole — malformed,
where silence is a guess — is now closed.

---

## 3. Mini-Plan

**Chosen: fix the readers, and give the record a sibling section.**

| Step | Files |
|---|---|
| 1 | new `tools/verifiers/_iterate_latest.py` — the attributed reader |
| 2 | `iterate_checks.py` — ledger + surface_verification use it; missing entry fails |
| 3 | `silent_revert.py` — `declared_removals` uses it; shared derived predicate |
| 4 | `review_record_schema.py` — `GATE_TYPES`, `RECORDABLE_TYPES`, `gates` validation |
| 5 | `review_record_core.py` — construct / route / pend the gate section |
| 6 | `record_review_pass.py` — symbol swap only (net 0 lines) |
| 7 | `review_record_check.py` — evidence floor, missing entry, Stage-1 invariant |
| 8 | `churn_merge.py` — `is_derived_churn`; `silent_revert_reading.py` — AC-6, AC-7 |
| 9 | docs: `iteration-reviews.md`, `SKILL.md` Step 8, `hooks-and-pipeline.md`, `guide.md` |

**Alternative considered and rejected — carry the Stage-1 verdict in the `code`
row.** Already built and withdrawn on
`iterate-2026-07-28-cascade-delegated-to-nobody` after three independent
reviewers disproved it (a Stage-1-only row satisfied the medium+ floor although
Stage 2 provably had not run; `not_run` discards findings; write ordering is
unknowable because a REJECT you intend to fix is not terminal). The card says
*"do not re-attempt that shape"*, and it is not re-attempted.

**Alternative considered and rejected — bump `schema_version` and add the sixth
`reviews` key.** §1.3: measured to break the only consumer, in the direction of
reporting healthy records as corrupt.

---

## 4. Affected Boundaries

- `shipwright_test_results.json` → three F11 checks (**the boundary this run is about**)
- `.shipwright/planning/iterate/<run_id>/reviews.json` → F11 gate **and** the
  cross-repo webui Mission consumer (`touches_io_boundary` — round-trip probe required)
- `.shipwright/agent_docs/iterates/<run_id>.json` (F5c) → complexity resolution
- git refs → `resolve_default_ref`
- `CHURN_ALLOWLIST` / campaign status glob → churn resolver **and** silent-revert

## 5. Why `schema_version` stays 1

A version exists so a reader can tell whether it understands the file. Three
facts decide it here:

1. Every field added is **optional**. A record without `gates` is valid, reads
   identically, and means what it always meant.
2. The one external reader compares `schema_version` with `!==` and refuses on
   any other value, so a bump makes it *stop* understanding a file it
   understands fine.
3. Our own `validate_record` already refuses a version **newer** than it knows
   — the guard the bump exists to arm is already armed, and nothing in this
   change makes an old reader misread a new file.

Bumping would therefore buy no reader anything and cost the only reader
everything. The bump belongs in the same change that teaches the webui about
`gates` — recorded as a follow-up, not skipped silently.

## 2d. Self-Review (Step 7 — 7-point checklist)

| # | Item | Verdict | Note |
|---|---|---|---|
| 1 | Spec Compliance | pass | All 8 ACs implemented; AC-7 was **corrected mid-run** to what was actually decided rather than left disagreeing with the code (§2c/3.1). |
| 2 | Error Handling | pass | Every non-`current` read is a named state, not an exception. Two crash paths found and closed: a truthy non-mapping `iterate_latest` (§2c/5.1) and the unreadable-file branch. Malformed never presents as "none declared". |
| 3 | Security Basics | pass | No new input surface. `record_dir` still rejects an unsafe `run_id`; `gates` is validated by the same `validate_entry` as `reviews`, so no unvalidated shape reaches disk. |
| 4 | Test Quality | pass | 51 tests over 5 new files. One weak test was found by review and **verified weak by flipping production** (§2c/5.3) rather than argued about. Fixture updates changed shapes to what real producers emit; no assertion was weakened to pass. |
| 5 | Performance Basics | pass | One extra JSON read per gate, on a file already read. `-b` vs `-w` is the same git invocation. |
| 6 | Naming & Structure | pass | Three extractions, all at the 300-line cap and on real seams (`_iterate_latest`, `silent_revert_declarations`, `review_record_floor` = "does this answer mean what it says"). `record_review_pass.py` held at exactly 395/395 by symbol swap. |
| 7 | **Affected Boundaries** | pass | §4. `reviews.json` is the cross-repo one; its consumer was READ (not assumed) and its two guards are mirrored as executable assertions. Round-trip probe covers the record; the `iterate_latest` boundary has typed-state tests for all five states. |

## 2e. Confidence Calibration

- **Boundaries touched:** §4 — `shipwright_test_results.json` → 3 F11 gates ·
  `reviews.json` → F11 **and** the webui Mission consumer ·
  `iterates/<run_id>.json` (F5c) · git refs · the churn allowlist.

- **Empirical probes run** (nine; each changed something or closed a question):

  | # | Probe | Finding |
  |---|---|---|
  | P1 | Read `shipwright_bloat_baseline.json` for `record_review_pass.py` | Baselined at 395 — the brief's blocker was already cleared by IT-0 (#492), but the file sits **exactly** on its ceiling. Drove the net-zero-line constraint. |
  | P2 | Read `iterate_latest.run_id` at this worktree's fork point | `iterate-2026-07-28-docs-placement-rule` — the defect is live here, not hypothetical. |
  | P3 | Read the webui consumer source | **Changed the design.** Two guards (`schema_version !==`, unknown `reviews` key) + no marker fallback on invalid ⇒ the card's prescribed fix would report every healthy record as corrupt. |
  | P4 | Inventory every `REVIEW_TYPES` reference | 7 sites needed the split; `review_marker.ALLOWED_REVIEW_TYPES` is a different vocabulary and was left alone. |
  | P5 | Callers of `iterate_checks.run_all_checks` | **Corrected my own assumption** — two, not one. Both guarantee a non-empty run_id, so AC-3 is safe. |
  | P6 | Old vs new derived predicate on a campaign `status.json` | `False` → `True`: the integration test's first assertion genuinely fails pre-fix. |
  | P7 | Evidence floor against all 45 real `reviews.json` | 45/45 carry evidence — AC-2 blocks nothing that already happened. |
  | P8 | `-b` vs `-w` vs `" ".join(split())` over 6 whitespace shapes | **Changed the fix.** `-b` agrees with the finder on 5/6 and diverges harmlessly on the 6th; `-w` diverged dangerously. |
  | P9 | Flip production to `-w` and run the AC-7 suite | **Still green** ⇒ the test was not discriminating, and the patch that "added" it had silently no-op'd. Rewritten and re-verified red-then-green. |

- **Test Completeness Ledger:** the machine-readable block is written at F5 and
  carried in the F5c entry (this run eats its own AC-1b).

- **Confidence-pattern check.**
  *Asymptote (depth):* the last three review rounds returned 3, 3 and 2
  findings, of which 3 were real defects of mine — the rate did not decay to
  zero, but the final round's surviving disagreement is a design question
  answered in prose, not a defect. Two consecutive rounds where Gemini approved
  and OpenAI's remaining findings were declines-with-reasons is the stopping
  signal.
  *Coverage (breadth):* all five reader states × three callers; six whitespace
  shapes × both halves of the detector; four evidence traces × blank-vs-present;
  `code`×`spec` status crossings; legacy-record-without-`gates` and
  record-with-`gates`.
  *Integration composition:* `cross_component` fires (recomputed from the real
  diff, `churn_merge.py`), and `test_derived_definition_integration.py` proves
  the merge resolver and the F11 gate agree on "derived" on real git — with a
  control asserting a genuine loss in the same integration, so an
  exempt-everything regression could not pass it.
