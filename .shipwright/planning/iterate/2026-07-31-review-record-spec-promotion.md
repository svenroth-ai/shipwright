# Iterate: promote `spec` into `REVIEW_TYPES`, and keep 65 old records readable

- **Run ID:** `iterate-2026-07-31-review-record-spec-promotion`
- **Date:** 2026-07-31
- **Type:** CHANGE
- **Complexity:** medium (Stage 1 said `small`; the Stage-2 Repo Scout raised it — see below)
- **Spec Impact:** MODIFY — the on-disk review-record contract changes shape
- **Branch:** `iterate/review-record-spec-promotion`

## Why now

`review_record_schema.py:74` named its own release condition: *"Promotion into
`REVIEW_TYPES` — one line here, one there — becomes safe as soon as the webui
ships a reader that tolerates unknown review types."*

That reader shipped in `shipwright-webui` `ce21323e` (PR #339, 2026-07-31) —
the commit that *introduced* it, not the branch tip, which has since moved on
(`origin/main` was `01b25b17` when this was written; `ce21323e` is still an
ancestor and the reader is present at the tip — both re-verified). Verified
directly against the merged source, not the PR title:

- the version check is now a FLOOR (`version < MIN_RECORD_SCHEMA_VERSION`),
  not the old `!==` pin;
- `strangers = keys.filter(k => !REVIEW_TYPES.includes(k))` are mapped through
  `toRow` and **rendered as extra rows**, not rejected.

So the stated condition is met. **The promotion is still not the one line that
comment implies**, for four reasons — three named in the brief, one found here.

## The four obstacles

### 1. The producer is strict in exactly the way the consumer was

`validate_record` (`review_record_schema.py:218-223`) requires every
`REVIEW_TYPES` key to be **present** in `reviews`. Measured on disk today:

| Record shape | Count | `reviews.spec`? |
|---|---:|---|
| pre-`gates` (no `gates` key at all) | 53 | no |
| `gates`-era (`gates.spec` present) | 12 | no |
| **total** | **65** | **0** |

The moment `spec` joins `REVIEW_TYPES`, **all 65** report `reviews is missing:
spec` to this repo's own F11 gate (`check_review_record`), which fails CLOSED
and tells the operator to "repair or delete" an immutable, git-tracked review
history that is perfectly fine. There is no `gates`→`reviews` fallback in
`review_record_core.py`. Hence a transitional READ path, not a constant edit.

### 2. `SCHEMA_VERSION` must NOT be bumped

The consumer reads `>=` now, so a bump buys it nothing — and it costs twice:
`validate_record` rejects a version newer than its own constant (old plugin
caches become casualties), and the new reader appends a user-visible caveat
("written by a newer Shipwright") for a record that is not actually newer in any
way that matters. Promotion-only. Pinned by a test.

### 3. The gate is a DEPLOYED webui, not a merged PR — and it is not deployed

Merge-order is not install-order: this plugin auto-updates through the
marketplace cache, `shipwright-webui` is hand-deployed. Probed empirically
rather than assumed:

- `server\dist` last built **2026-07-21**, `client\dist` **2026-07-26**;
  PR #339 merged **2026-07-31**.
- the marker string from #339 (`"somewhere this version does not read"`) appears
  in **0 of 536** built JS files.

**The running webui does not have the tolerant reader.** Against the old reader
a record carrying `reviews.spec` is invalid, and `review-state.ts` deliberately
does NOT degrade to the marker view — all five rows render *"This run's review
record exists but could not be read. That is a data problem, not a clean
result."*, which is false under version skew and repeats every run.

There is no way to engineer around this: the old reader rejects on `reviews`
carrying any stranger key, so keeping a parallel copy under `gates` does not
help. The promotion is inherently coupled to the redeploy.

**Operator decision (2026-07-31):** build the full change, open the PR, do
**not** arm auto-merge; the webui rebuild+redeploy is a hard merge precondition
stated in the PR body. → AC10.

### 4. FOUND HERE: the Stage-1 ordering rule would silently stop firing

`stage_one_precedes_stage_two` (`review_record_floor.py:216`) opens with:

```python
if "gates" not in record:
    return None
```

That guard means "a record written before `gates` existed cannot answer this
question". Retire the `gates` **write** path and *every new record* also has no
`gates` key — so the rule that a completed `code` pass implies a completed
`spec` pass would return `None` for every run from then on. The HARD-GATE
ordering check dies quietly, with every test still green and no message
anywhere. This is the failure the brief predicted, at a line the brief does not
name.

The guard must ask the real question — *can this record answer at all?* — i.e.
is `spec` absent from **both** sections.

## The Chesterton call on `GATE_TYPES`

The fence's own stated purpose: *"Review passes this repo's F11 gate requires
that the pinned `reviews` contract has no slot for."* The pin is gone — the
consumer renders unknown review types as rows. **The reason for the fence no
longer exists, so it comes down as a write destination:** a future gate stage
now goes straight into `REVIEW_TYPES`.

What must survive forever is *reading* `gates`, because 12 git-tracked,
never-evicted records carry `gates.spec`. So `GATE_TYPES` is not kept as an
empty tuple pretending to be a seam — it is replaced by `LEGACY_GATE_TYPES`,
which names what it actually is: history we still read, never a place we write.
One concept, correctly named, instead of two constants where one is permanently
empty and invites "what is the difference?" forever.

## The strictness we kept, and what it costs

`validate_record` still rejects any `reviews` key outside `REVIEW_TYPES`. That
rule was justified by *"strictness protects the mirror"* — and this change
repeals the premise, because the mirror stopped rejecting strangers. Keeping the
conclusion while deleting its reason would be exactly the kind of unexamined
fence this iterate is otherwise dismantling, so it gets re-derived rather than
inherited (Stage-3 doubt, objection 4).

**Why it stays:** the consumer only *displays*, so a key it cannot name costs it
one wrong row. This gate *blocks delivery*, so a key it cannot name costs a
wrong verdict on whether a change may ship. A producer that launders unknown
keys cannot tell "a pass written by a newer writer" from corruption.

**What that costs, stated plainly:** every future growth of `REVIEW_TYPES` will
need the same transitional read path this change built, because old and new
plugin caches coexist by design. `LEGACY_GATE_TYPES` is a name-keyed exemption
for one key — it is not a mechanism, and it does not generalise.

**The alternative, and why it is not bundled here:** relax `unknown` so a
*well-formed* stranger key is accepted and only a malformed one is rejected —
the consumer's own `unreadableStranger` posture. Under that rule this promotion
would have needed no exemption, and neither would the next one. It is a change
to a fail-closed validator arriving after three review stages had passed on the
current design, so it belongs in its own iterate with its own review round, not
appended to this one. Filed rather than done.

## Acceptance Criteria

| # | Criterion |
|---|---|
| AC1 | `spec` is in `REVIEW_TYPES`; a newly created record carries `reviews.spec` and **no** `gates` key |
| AC2 | `SCHEMA_VERSION` stays `1` |
| AC3 | All 65 existing on-disk records still pass `validate_record` |
| AC4 | A legacy `gates.spec` entry is still found by `entry_for` and honoured by `pending_types` |
| AC5 | `stage_one_precedes_stage_two` fires for a new-shape record (the §4 regression) |
| AC6 | It still returns `None` for a record that genuinely cannot answer |
| AC7 | Immutability holds across the move: a terminal legacy `gates.spec` cannot be silently overwritten in `reviews` |
| AC8 | `GATE_TYPES` retired deliberately and documented; the write path never emits a `gates` key |
| AC9 | Prose that is now false is corrected in the same diff (`SKILL.md`, `iteration-reviews.md`, module docstrings) |
| AC10 | **Both** rollout preconditions are named in the PR body, and auto-merge is NOT armed: the `shipwright-webui` rebuild+redeploy, **and** the plugin-cache re-sync (`bash scripts/update-marketplace.sh`, verified with `check_plugin_cache_sync.py --strict`) |

### AC10 is an ORDER, not a set

The two preconditions are not interchangeable, and listing them as a checklist
invites doing them in the wrong order (Stage-3 doubt, objection 5):

| # | Step | Why it must be here | Verified by |
|---|---|---|---|
| 1 | rebuild + redeploy `shipwright-webui` | makes the consumer tolerant **before** any new-shape record can be rendered | re-run the marker grep: `"somewhere this version does not read"` must appear in the built JS (it appeared in 0 of 536 files on 2026-07-31) |
| 2 | merge this PR | — | PR state |
| 3 | `bash scripts/update-marketplace.sh` | turns the **producer** on; must follow the merge, never precede it | — |
| 4 | `uv run scripts/check_plugin_cache_sync.py --strict` | proves step 3 actually landed | paste the output in the PR |

Auto-merge is **not armed**, so step 2 cannot overtake step 1.

**One caveat that is honest rather than reassuring:** the first new-shape record
already exists *before* the merge — this run's own `reviews.json` is in the
worktree now, and the webui resolves live-run artifacts from the registered
worktree. Checked on 2026-07-31: this worktree does not appear in the webui's
`projects.json` or `sdk-sessions.json`, so the exposure is not observable here.
It would be for a run the webui *is* tracking, which makes step 1 worth doing
before the next iterate, not merely before this merge.

### AC10 has two readers, not one

The webui is the obvious one. The second was missed on the first pass and found
by the Stage-2 review: **this repo's own runtime** reads
`~/.claude/plugins/cache/shipwright/`, which per `CLAUDE.md` does not
auto-sync. A record carrying `reviews.spec` is valid only under the *new*
`validate_record`; the old one rejects it with `reviews has unknown type(s):
spec`, and `check_review_record` fails CLOSED telling the operator to repair or
delete it. This run's own committed record already carries the new shape, so the
exposure is immediate rather than theoretical. Same class of skew as the webui,
same fix shape: refresh the reader before the producer reaches it.

## Affected Boundaries

- **On-disk record shape** — `.shipwright/planning/iterate/<run_id>/reviews.json`
- **Cross-repo contract** — consumed by `shipwright-webui` `review-record.ts`
- **This repo's F11 gate** — `check_review_record`, fails closed
- **Deployment skew** — auto-updating plugin cache vs. hand-deployed webui

## Confidence Calibration

- **Boundaries touched:** on-disk review record; cross-repo reader contract;
  F11 gate machinery; plugin-cache/webui deployment skew.
- **Empirical probes run:**
  - counted the real corpus → 65 records, 12 with `gates.spec`, 53 without,
    0 with `reviews.spec` (so the break is total, not partial);
  - read the merged consumer source → floor `>=`, strangers rendered;
  - grepped 536 built JS files for the #339 marker → 0 hits, build predates the
    merge by 10 days (so obstacle 3 is live, not theoretical);
  - traced `stage_one_precedes_stage_two`'s guard → found the silent-death
    regression that no test covers today.
- **Test Completeness Ledger:** every behaviour this diff introduces or changes.
  18 behaviours, 18 `tested`, 0 testable-but-untested, 0 `untestable`.
  Rows 16-18 were added after the Stage-2 code review; see the note under the
  table for what they close.

| # | Behaviour | Disposition | Evidence |
|---|---|---|---|
| 1 | `spec` is a first-class review type | tested | `test_spec_is_a_first_class_review_type` |
| 2 | a new record carries `reviews.spec` and **no** `gates` key | tested | `test_a_new_record_carries_spec_under_reviews_and_no_gates_key` |
| 3 | `SCHEMA_VERSION` stays `1` | tested | `test_schema_version_is_not_bumped`; `test_the_on_disk_shape_matches_the_pinned_consumer_contract` |
| 4 | the on-disk shape satisfies the *new* consumer contract (version floor, pinned five present, stranger key is a valid identifier, ≤32 keys) | tested | `test_the_new_shape_satisfies_the_new_consumer_contract` — a MIRROR, see the pattern check |
| 5 | a pre-`gates` record (53-shape) still validates | tested | `test_a_pre_gates_record_still_validates` |
| 6 | a `gates`-era record (12-shape) still validates | tested | `test_a_gates_era_record_still_validates` |
| 7 | `entry_for` finds a legacy `gates.spec` | tested | `test_a_gates_era_spec_row_is_still_found` |
| 8 | `pending_types` reports `spec` unanswered when absent from both sections | tested | `test_a_pre_gates_record_reports_spec_unanswered` |
| 9 | **all 65 real on-disk records still validate** | tested | `test_every_record_on_disk_still_validates` (walks the corpus; asserts non-empty first) |
| 10 | the Stage-1 ordering rule fires for a new-shape record | tested | `test_it_fires_for_a_new_shape_record_with_no_gates_key` — **was RED before the fix** |
| 11 | it accepts a new-shape record whose `spec` is completed | tested | `test_it_accepts_a_new_shape_record_whose_spec_is_completed` |
| 12 | a completed `spec` still needs evidence | tested | `test_a_completed_spec_still_needs_evidence` |
| 13 | it skips a record that genuinely cannot answer | tested | `test_it_skips_a_pre_gates_record`; `test_it_skips_when_the_code_pass_did_not_run` |
| 14 | a legacy `gates.spec` still satisfies / still fires the rule | tested | `test_a_gates_era_spec_still_satisfies_the_rule`; `test_a_gates_era_spec_that_did_not_run_still_fires` |
| 15 | immutability holds across the section move; record round-trips unchanged | tested | `test_a_terminal_gates_era_spec_cannot_be_silently_rewritten`; `test_round_trips_through_disk_unchanged` |
| 16 | **a `reviews` row is authoritative over a legacy `gates` row** when both are present | tested | `test_a_reviews_row_wins_over_a_legacy_gates_row` |
| 17 | a terminal `reviews.spec` is immutable on the ordinary (non-legacy) path | tested | `test_a_terminal_reviews_spec_is_immutable_on_the_ordinary_path` |
| 18 | an unanswered `spec` still blocks at the gate | tested | `test_an_unanswered_spec_row_blocks_like_any_other_type` (repaired — see below) |

  **Rows 16-18 close holes the Stage-2 review found, and two of them were holes
  this change itself opened:**

  - Row 16: `_read_sections` returns an *ordered* tuple, and that order is the
    answer to "which section wins when both carry the type" — reachable via
    `--force` and via a record in flight at rollout. Every other fixture put
    `spec` in exactly one section, so inverting the tuple left the whole suite
    green. Verified by mutation: with the order flipped, exactly this test fails
    and the other 12 still pass; restored, all 13 pass.
  - Row 18: `test_an_unanswered_spec_row_blocks_like_any_other_type` went
    **vacuous** the moment `spec` joined `REVIEW_TYPES` — its blanket
    `for review_type in REVIEW_TYPES` loop started closing the very row it
    leaves open, and its `"spec" in detail` assertion was then satisfied by
    `spec-reviewer` appearing in a *different* failure message. Since
    `validate_record` now permanently tolerates an absent `reviews.spec`,
    `pending_types` is the SOLE enforcement that a live run cannot dodge the
    Stage-1 row — and this was its only gate-level pin. It now skips `spec` in
    the loop and asserts on the pending branch's own wording.

  AC9 (prose) and AC10 (merge precondition) are not behaviours and carry no
  ledger row: AC9 was verified by the Stage-1 reviewer, which is what caught the
  two files this run first missed; AC10 is discharged at PR-open time.

- **Confidence-pattern check:**
  - **Asymptote (depth).** The deepest risk was not the promotion but what it
    silently disables. Tracing `stage_one_precedes_stage_two` found a guard that
    would have returned `None` for every future record with all tests green —
    row 10 exists because of that trace and was RED before the fix. Probing
    stopped when the remaining questions were about prose rather than behaviour.
  - **Coverage (breadth).** Both directions, and against the real corpus rather
    than reconstructions: the 65 on-disk records are the population the F11 gate
    actually meets. The new shape is additionally verified in production, not
    only in tests — this run's own `reviews.json` was written by the changed
    code and carries six `reviews` keys with no `gates` key.
  - **Integration composition.** `cross_component` does not fire for this diff
    (`risk_detectors.CROSS_COMPONENT_FILE_PATTERNS` matches none of these paths),
    so no `category:"integration"` behaviour is required.
  - **Stated residual — the mirror.** Row 4 asserts our side of a contract whose
    other side is TypeScript in another repo; no cross-repo suite runs from this
    commit, so mirror-versus-consumer drift stays possible. Mitigated by reading
    the merged consumer source directly (`ce21323e`) rather than trusting the PR
    description, and by AC10 gating the merge on the redeploy.
  - **Stated residual — the deployment.** The running webui is built from
    2026-07-21 and does **not** contain the tolerant reader (0 hits for the #339
    marker across 536 built JS files). Until it is rebuilt, this change would
    make every Review row render a false "could not be read". That is why the PR
    does not arm auto-merge.
