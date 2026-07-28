# IT-0b — the C3 event anchor, and a name out of the prose

**Run:** `iterate-2026-07-28-it0-followup-anchor-prose`
**Type:** CHANGE · **Complexity:** medium · **Spec Impact:** NONE
**Anchor:** `trg-fad2571c` (consolidates `trg-1346abbd` + `trg-1a215186`)
**Brief:** `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md` § "Nicht in IT-0 enthalten → Follow-up"

Two decision-free items that were folded into IT-0 *after* that run had already
started, so `iterate-2026-07-28-hygiene-sweep` could not see them. Both are small
and file-disjoint from every wave of the consolidation plan.

---

## Part 1 — Stamp the C3 event anchor in the iterate ledger writer

### What is wrong today

Canon C3 asks "did THIS phase leave the handover note". Where a completion
carries an **event anchor** (`event_at`), it also asks the sharper question:
*was the note written for THIS completion, or for an earlier one?* That second
question is the only thing that catches a phase which completed again without
re-writing the note.

`shared/scripts/tools/append_iterate_entry.py` (F5c) stamps no `event_at`, so
for the `iterate` phase the clock question is never asked at all. The bound is
recorded verbatim in four places:

| Place | Shape |
|---|---|
| `shared/scripts/lib/phase_history.py` above `COMPLETION_PRODUCER` | `#: KNOWN BOUND — …` comment |
| `shared/scripts/tools/verifiers/handoff_phase_canon.py` | **Known bounds** bullet 2 |
| `shared/scripts/tools/append_iterate_entry.py` module docstring | "``event_at`` is reserved … this tool deliberately does not" |
| `shared/tests/test_completion_writers.py` | `assert "event_at" not in entry` |
| *(also)* `docs/hooks-and-pipeline.md` | **Known bounds** numbered item 2 |

The brief named four; the repo has **five** — `docs/hooks-and-pipeline.md`
carries the same bound as numbered item 2 of its own *Known bounds* list. It is
the declared single source of truth for what fires when, so it moves in this
diff by the CLAUDE.md rule, not as an extra.

### Why it was safe, and what is left uncovered

The iterate ledger is **one file per run id**. A stale marker therefore names a
*different* run, and the run-id branch of `_same_phase_verdict` catches it
without ever consulting a clock. What escapes is exactly the case the run-id
branch cannot see: an **in-place F5c re-run under the same run id** — the ledger
entry is rewritten, the marker is not, and C3 calls it a pass.

### The change

Stamp `event_at` the way the sibling producer does — same function
(`lib.events_log.latest_event_dt`), same omit-when-absent rule:

```python
event_dt = latest_event_dt(project_root)
entry = {
    "run_id": args.run_id,
    "date": now_utc_iso(),
    **({"event_at": event_dt.isoformat()} if event_dt is not None else {}),
    **extra,
}
```

Omitted rather than nulled when the project has no events yet: an absent key is
a *stated unknown*, and `PhaseCompletion.claims_anchor` already distinguishes
"no key" (pre-anchor entry, run id answers alone) from "unreadable key"
(malformed record, must not get the benefit of the doubt).

### Why this cannot make C3 noisier in the normal flow

`finalize_bundle` runs **F5c before F5b** (`docs/hooks-and-pipeline.md`,
*Ordering*). So at F5c time the run's own `work_completed` event does not exist
yet; F5b records it and *then* regenerates the marker. The marker's timestamp is
therefore `>=` the ledger's anchor, and `RecordedTime.after` is STRICT — equality
is the shape of a correct run, not of a missing write. Both sides read the same
worktree-local `shipwright_events.jsonl` (`resolve_events_path` is a literal
join, deliberately not redirected to the main repo), so they are on one clock.

### Bloat: why the baseline entry is raised, and not the file split

`append_iterate_entry.py` is 425 lines against a baseline of
`current: 425, state: grandfathered` — it sits **exactly on its ceiling**, so
any growth ratchets an existing entry and the pre-commit hook blocks it. The
card offered two ways out: do the split the file is slated for, or raise the
entry in the same commit and justify it.

**Raised, not split.** The separable mass in that file is the one-shot legacy
`iterate_history` → file-per-run migration (~110 lines). Extracting it is a real
improvement, but it is a *decision*: where the module lives, whether the
recovery path stays CLI-reachable, and it ripples into
`shared/tests/test_append_iterate_entry.py` — itself 509 lines and *also* sitting
on its grandfathered ceiling, so the split would need a second bump anyway. This
run is scoped decision-free. An H2 `current` is a low-water mark, not a chosen
ceiling; raising it for a correctness fix with the reason written down is the
sanctioned path, and the split stays available to the run that takes it
deliberately.

Measured after the fact: **436**, so the entry moves 425 → 436. Eleven lines for
a five-line change, because the *why* is written down the way
`append_phase_history.py` writes down the same decision — eight lines explaining
which clock is being read and why an absent key beats a null one. That comment is
the reason the bound was legible enough to close at all.

**`shared/tests/test_completion_writers.py` needed no bump.** It sits at 302/302,
so the new coverage could not go there without raising a second ceiling *and*
pushing a test file 22% past the constitution's 300-line rule — a failure my own
Self-Review item 6 would have to record. The five new writer-driven tests live in
`shared/tests/test_iterate_ledger_anchor.py` (222 lines, no entry needed), split
along the seam that suite's own section comment already draws: `append_phase_history`
(the seven pipeline phases) versus `append_iterate_entry` (the file-per-run
ledger). The shared discipline — no hand-built dicts, every producer invoked as a
subprocess — is restated in the new file's docstring and enforced by the same
fixture-symmetry assertion. `test_completion_writers.py` keeps its two existing
iterate tests and its bound assertion is flipped line-for-line.

### Fixture symmetry

`shared/tests/_c3_fixtures.py::write_iterate_entry` claims to write "one entry in
the file-per-run ledger `append_iterate_entry.py` writes". After this change that
claim is false unless the fixture also models `event_at`. That is the precise
failure mode this fixture family was built for — `history_entries` already models
it for `phase_history`, with a docstring explaining why collapsing the anchor and
the wall clock would make every dependent suite return the same verdict either
way. The iterate fixture gets the same treatment, and the writer-vs-fixture
symmetry assertion is extended to cover it.

---

## Part 2 — The maintainer's name out of live prose

Four live files name an individual maintainer in prose rather than in authorship
metadata. Authorship metadata (`LICENSE`, `plugin.json` ×13, `pyproject.toml`)
is **correct and untouched** — this is only about the name used as an authority
marker or as fixture data.

| File | Today | After |
|---|---|---|
| `shared/prompts/pr_reviewer/system:50` | instructs the LLM to say "a maintainer (Sven) must review" | "a maintainer must review" — matching rule 3, which already says it namelessly |
| `plugins/shipwright-security/scripts/tools/pr_review.py:6` | "iterate branches + Sven's manual PRs" | "iterate branches + maintainer-authored PRs" |
| `plugins/shipwright-iterate/skills/iterate/references/round-trip-tests.md:105` | "Sven's BOM fix landed in one but not the other" | "a BOM fix landed in one but not the other" |
| `plugins/shipwright-compliance/tests/test_change_history.py:50` | `CommitEntry(…, "Sven")` | `CommitEntry(…, "Ada")` — any non-`Claude` author, the classifier only tests for `"claude"` |

**One file beyond the four, stated rather than smuggled.**
`shared/tests/test_ts_test_hygiene.py` carries `// owner: @svroch` four times
inside synthetic TS fixtures. Same class as the `CommitEntry` fixture — a
personal identity used as sample data — and leaving it means the repo-wide scan
that filed this card comes back dirty and refiles it. Replaced with
`@example-owner`; the parser only needs an `@handle`-shaped token.

**Deliberately NOT touched:** `.github/workflows/pr-review-run.yml:146`
(`[ "$author" != "svroch" ]`) and the two assertions in
`plugins/shipwright-security/tests/test_pr_review_workflow_shape.py` that pin it.
That is a *functional* author check, not prose, and the tier decision that owns
it is `trg-51f69c7d` → **IT-9**, which holds `.github/workflows/**` exclusively.

---

## Acceptance criteria

- **AC1** — `append_iterate_entry.py` stamps `event_at` from
  `lib.events_log.latest_event_dt`, and omits the key (never nulls it) when the
  project's event log is absent or empty.
- **AC2** — A completion written by the real F5c tool on a project that has
  events reads back through `lib.phase_history.latest_completion` with a usable
  `anchor` pinning an **instant**, not a day.
- **AC3** — The marker and the ledger entry land on **one clock**: a real
  `record_event` → `generate_session_handoff --canon-marker` → `append_iterate_entry`
  sequence leaves `entry["event_at"] == marker["timestamp"]`.
- **AC4** — The bound is closed in behaviour, not only in prose: an in-place F5c
  re-run under the same run id, after a newer event landed, makes C3 **warn**
  ("predates that run's last recorded completion") where it previously passed.
- **AC5** — The `KNOWN BOUND` / `Known bounds` paragraph naming this bound is gone
  from all five places, and the assertion in `test_completion_writers.py` is
  flipped to assert the anchor is now present. In `docs/hooks-and-pipeline.md`
  the iterate-specific item is **removed**, not reworded: what remained after the
  fix was already stated by numbered item 3 (the strengthening is inert until a
  phase completes once), so the two were folded into one and the list is now
  Two. The retired bound is recorded below the list as history, where a closed
  bound belongs.
- **AC6** — `_c3_fixtures.write_iterate_entry` models `event_at`, with the wall
  clock stamped strictly later (parsed and re-serialised, not string-spliced),
  and a symmetry assertion pins the fixture to the real writer's key set by
  **equality** — a subset would let a fixture invent a key production never
  emits, which is the same drift in the other direction. The **pre-anchor** shape
  stays reachable (`anchored=False`) and a C3 test drives it, because every
  ledger entry written before this change has it and must keep taking the run-id
  branch.
- **AC7** — Exactly one bloat baseline entry is raised —
  `append_iterate_entry.py`, 425 → 436 — in the same commit, and no non-baselined
  file crosses 300 because of this diff. `test_completion_writers.py` keeps its
  302 (the flip is line-for-line) and no new test file needs an entry.
- **AC8** — The maintainer's personal name/handle is gone from the four named
  files plus `test_ts_test_hygiene.py`; `LICENSE`, every `plugin.json` and every
  `pyproject.toml` are byte-unchanged; the functional `svroch` author check in
  `pr-review-run.yml` and its two pinning assertions are untouched.

---

## Affected boundaries

| Boundary | Producer | Consumer | Change |
|---|---|---|---|
| iterate ledger entry JSON | `append_iterate_entry.py` (F5c) | `lib/phase_history.latest_completion`, `lib/iterate_entry.read_iterate_entries`, plugin-side `complexity_history.py` | **additive key** — `validate_iterate_entry` permits unknown keys; no reader enumerates keys |
| canon marker ↔ completion | `generate_session_handoff --canon-marker` | `verifiers/handoff_phase_canon` (C3) | the `iterate` phase joins the clock branch it previously never reached |
| bloat baseline | this commit | `lib/anti_ratchet` pre-commit hook, Group H audit | two `current` values raised |

---

## Confidence Calibration

- **Boundaries touched:** iterate ledger entry JSON (additive key); the C3
  marker↔completion join for one phase; the bloat baseline.
- **Empirical probes run:**
  - **P1** — `git grep event_at` across `shared/ plugins/ docs/ integration-tests/`:
    the only readers are `lib/phase_history.entry_anchor` / `claims_anchor` and
    the C3 suites. No consumer of the iterate ledger enumerates or rejects keys.
    *Finding: additive is safe.*
  - **P2** — `validate_iterate_entry` read end to end: required-field loop +
    optional-field type checks, **no unknown-key rejection**.
    *Finding: the new key passes validation unchanged.*
  - **P3** — `risk_detectors.CROSS_COMPONENT_FILE_PATTERNS` matched against the
    planned file list: `events_log.py` matches the pattern but is only
    *imported*, never edited; nothing else matches. `CI_SUPPLYCHAIN` and
    `IO_BOUNDARY` likewise clean. *Finding: no risk flag, so no
    integration-coverage or ack requirement — recomputed the way F11 recomputes it.*
  - **P4** — `lib/anti_ratchet.classify_entries` read: the pre-commit hook blocks
    only on `measured > entry.current` for a **baselined** path; non-baselined
    oversize is advisory. *Finding: two entries must be raised; touching the
    300-line non-baselined files is safe as long as they do not cross.*
  - **P5** — ordering probe: `finalize_bundle` F5c-before-F5b confirmed in
    `docs/hooks-and-pipeline.md` *Ordering* and in the `handoff_phase_canon`
    comment that narrows the owner lookup. *Finding: the normal flow leaves
    marker ≥ anchor, so the activated branch cannot fire on a correct run.*
  - **P6** — this run's own F5c executes the patched writer from the worktree,
    so the change is exercised end to end by the run that ships it.
- **Test Completeness Ledger:** see below.
- **Confidence-pattern check:**
  - *Asymptote (depth)* — the true positive (AC4) is driven, not asserted about,
    so the activation cannot have been bought by blinding the check; and the
    no-events companion (AC1) pins the other side.
  - *Coverage (breadth)* — writer, reader, fixture and the C3 verdict are each
    exercised; the prose deletions are text-only and carry no behaviour.
  - *Integration composition* — `cross_component` recomputed **false** from the
    diff (P3), so no `category:"integration"` behaviour is required.

### Test Completeness Ledger

| # | Behaviour | Status | Evidence |
|---|---|---|---|
| 1 | F5c stamps `event_at` from `latest_event_dt` when events exist | `tested` | `test_iterate_ledger_anchor.py::test_the_ledger_writer_stamps_the_anchor_c3_reads` |
| 2 | F5c omits `event_at` (never nulls) when there is nothing to anchor to | `tested` | `test_iterate_ledger_anchor.py::test_a_ledger_entry_with_nothing_to_anchor_to_carries_no_anchor` — parametrized over absent · empty · blank-lines · unparseable |
| 3 | The written anchor reads back as an **instant** through `latest_completion` | `tested` | `…::test_the_ledger_writer_stamps_the_anchor_c3_reads` |
| 4 | Marker and ledger entry land on one clock (equal timestamps) | `tested` | `…::test_the_marker_and_the_ledger_entry_land_on_one_clock` |
| 5 | An in-place F5c re-run after a newer event is now CAUGHT by C3 | `tested` | `…::test_an_in_place_f5c_rerun_after_a_new_event_is_now_caught` |
| 5b | The real F5c-before-F5b ordering still PASSES — no false positive | `tested` | `…::test_the_real_f5c_before_f5b_ordering_still_passes` |
| 6 | A correct single-pass iterate still PASSES against a fixture marker | `tested` | `test_completion_writers.py::test_an_iterate_that_wrote_its_note_passes_end_to_end` (pre-existing, still green) |
| 7 | A **pre-anchor** (legacy) ledger entry still passes on the run id alone — the clock is not consulted | `tested` | `test_c3_applicability.py::test_a_pre_anchor_iterate_ledger_entry_still_passes_on_the_run_id_alone` |
| 8 | The hand-built iterate fixture carries exactly the writer's keys | `tested` | `test_iterate_ledger_anchor.py::test_the_hand_built_ledger_fixture_matches_the_writer` |
| 9 | `--entry-json` refuses a caller-supplied `event_at` (the guard that now protects a REAL anchor) | `tested` | `test_iterate_ledger_anchor.py::test_the_writer_refuses_to_let_a_caller_forge_the_anchor` |
| 10 | `finalize_bundle` pre-rejects a bundled `event_at` before F1/F3/F4 write | `tested` | `test_finalize_bundle_cli.py` (existing `iterate_entry must not set` assertion, now covering the third canonical key) |
| 11 | Prose deletions in three modules + one doc | `untestable` — `covered-by-existing-test` | no behaviour; the behavioural claim they described is pinned by rows 1–7 |
| 12 | Maintainer name removed from five files | `untestable` — `covered-by-existing-test` | text-only; the suites owning those files (`test_pr_review_workflow_shape`, `test_change_history`, `test_ts_test_hygiene`) stay green, which is what proves nothing load-bearing moved |

0 testable-but-untested.

**Row 9 exists because of a review finding that was wrong on the code and right
about the coverage.** Gemini R1 claimed `--entry-json` could forge `event_at`
because `**extra` unpacks last. It cannot: `main()` rejects the collision and
returns 1 before the dict is built. But checking that claim showed the guard has
**no test** — `test_append_iterate_entry.py` drives only the Python API, never
`main()` — and the guard now protects a real anchor rather than a merely reserved
key. An earlier draft of this ledger cited a pre-existing test for it that did
not exist.

---

## Review Record

`.shipwright/planning/iterate/iterate-2026-07-28-it0-followup-anchor-prose/reviews.json`
