# Iterate Spec: the compliance refresh is driven through its real producer

- **Run ID:** iterate-2026-08-01-compliance-refresh-real-converge
- **Type:** feature
- **Complexity:** medium
- **Status:** draft

## Goal

Close the one gap `iterate-2026-07-31-derived-docs-at-release` named rather than
hid: *"the real `regenerate_tracked_snapshots` → `_update_compliance` producer is
driven nowhere in this diff — every refusal, rewind and floor test injects
`regenerate` or stubs `converge`."* Add a fixture project carrying a full
`.shipwright` tree and drive **one** real `converge()` through it, so the
producer's actual side effects are observed instead of reasoned about.

Not theoretical. The Stage-3 doubt review of that iterate found D6 — the
compliance config was never rewound, because the append-only prefix guard could
not apply to a file the producer *rewrites* — and it was invisible for exactly
this reason: no test exercised the real producer's side effects.

## Acceptance Criteria

- [ ] **AC-1** A fixture project with a full `.shipwright` tree (a spec carrying
  two FRs, an `@FR`-tagged test module, an event log with a `work_completed` and
  a failing-layer `test_run`, one triage backlog line, and a
  `shipwright_compliance_config.json` whose `phases_covered` does not yet contain
  `iterate`) drives **one** real `converge()` — no `regenerate` stub, no
  `converge` monkeypatch — and every one of the seven `REFRESH_SET` paths reports
  an outcome in `SUCCESS_OUTCOMES`.
- [ ] **AC-2** After that run the **six `TREE_DERIVED`** documents differ
  byte-wise from their committed seed and carry real derived content:
  `traceability-matrix.md` names both seeded FR ids, `change-history.md` counts
  the seed's two commits, `sbom.md` names the seeded dependency, and
  `test-traceability.json` parses as a schema-v3 manifest with a node per FR and
  no `untagged_tests`.

  > **The card asked for "the seven documents actually change". That premise is
  > wrong, and this run is what found it.** `ci-security.json` is
  > `DERIVES_FROM_CI_HISTORY`: its only writer is `refresh_ci_security`, gated on
  > an authenticated `gh` CLI. CI's `shared/tests` step exports no token, so on
  > CI the leg is `skipped` and the committed copy stands — measured, `210 → 210`
  > bytes with `gh` logged out versus a rewrite with it logged in. A test
  > asserting all seven change would have been green on a developer machine and
  > red in CI. So AC-2 covers six, and **AC-8 below covers the seventh properly**
  > — as a frozen-copy-stands case, which is the behaviour the classification
  > actually promises.
- [ ] **AC-3** `converge` returns `reached is True` with `passes == 3`, strictly
  under `MAX_PASSES` — the RTM ← `test-traceability.json` generator-ordering
  coupling the loop exists for, measured on a real project rather than quoted
  from the docstring.
- [ ] **AC-4** `shipwright_compliance_config.json` is byte-identical before and
  after the run, **and** the per-pass recording shows it was really rewritten
  mid-run (`phases_covered` gained `iterate`), so the assertion cannot pass
  vacuously. This is D6, pinned.
- [ ] **AC-5** Both append-only inputs keep every line they started with, each
  grew during the run, and `converge.left_alone` names exactly
  `[".shipwright/triage.jsonl", "shipwright_events.jsonl"]`.
- [ ] **AC-6** The fixpoint is reached *despite* those inputs moving: the event
  log gains exactly one `grade_snapshot` per pass, and after three passes the
  triage log carries exactly one `test-fail:unit` row — the dedupKey-idempotence
  claim in `APPEND_ONLY_INPUTS`' docstring, driven rather than argued.
- [ ] **AC-7** `converge`'s `regenerate` parameter still defaults to the real
  `compliance_refresh_produce.regenerate`, so the injection point this test uses
  for *observation* cannot silently become the thing under test.
- [ ] **AC-8** With its source unreachable, `ci-security.json` keeps its
  committed bytes, its producer leg still reports success, and the run still
  converges — "a release is never held for a scan", driven rather than asserted
  from the docstring.
- [ ] **AC-9** The run is **hermetic**: it produces the same result on a machine
  with an authenticated `gh` and one without. `_update_compliance` shells out
  with no `cwd=`, so the child inherits the test process's working directory and
  `gh api` resolves `{owner}/{repo}` from *the shipwright repo's own remote* —
  the fixture must neutralise `gh` for the subprocess, which the in-process
  `conftest` stub structurally cannot do.

## Spec Impact

- **Classification:** none
- **ADD** (new FR appended): none
- **MODIFY** (existing FR changed): none
- **REMOVE** (FR retired): none
- **NONE justification:** This diff adds a test module and touches no production
  code. FR-01.10 (`/shipwright-compliance` — produce audit-ready evidence) already
  specifies the behavior being driven; nothing about its observable behavior
  changes. The change buys evidence, not capability, so the No-FR branch
  (`change_type: tooling`) is the honest classification at F5b.

## Out of Scope

- **Fixing the `inputs_left_alone` reporting mismatch this run surfaces.** The
  producer appends a `grade_snapshot` to `shipwright_events.jsonl` on every pass
  by documented contract, so on any real project that field will *always* name
  the event log — while `produce()`'s comment reads it as "somebody else wrote to
  it while the producer ran". The signal therefore cannot distinguish a
  concurrent writer from the producer's own append. Real, but it is a design
  decision about an operator-facing field, not a test gap. Filed as a triage card;
  this run only pins the behavior as it is.
- Changing the generator ordering in `PHASE_REPORTS["iterate"]` that makes the
  third pass necessary. The loop is deliberately kept even once ordering is fixed
  (`converge` docstring); this run measures the ordering, it does not repair it.
- Widening `REFRESH_SET`, `CLASSIFICATION` or `PRODUCER_STATE`.
- Any change to `update_compliance.py` or the compliance plugin.

## Design Notes

n/a — no UI surface. The change is a single new pytest module under
`shared/tests/`.

## Affected Boundaries

The test does not *change* a serialized format, but it reads three of them, so
they are named rather than left implicit:

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `update_compliance.py` (subprocess) | `compliance_refresh_produce.digest` / `capture` | 7 files: 5 markdown + 2 JSON |
| `update_compliance.py:main` | `compliance_input_state.rewind` | `shipwright_compliance_config.json` (rewritten whole) |
| `_grade_snapshot.emit_grade_snapshot` | `compliance_input_state.rewind` (append-only) | `shipwright_events.jsonl` (JSONL) |
| `test_evidence.emit_test_failure_triage` | `compliance_input_state.rewind` (append-only) | `.shipwright/triage.jsonl` (JSONL) |

The `touches_io_boundary` risk flag is **not** raised: it is diff-driven on file
paths, and this diff carries no `*_config.json` / `.env` / `hooks.json` /
`settings.json` / `*_state.json`. The Boundary Probe is nonetheless effectively
what this whole change *is* — a round-trip probe of the producer's own inputs.

## Confidence Calibration

- **Boundaries touched:** the subprocess boundary into
  `plugins/shipwright-compliance/scripts/tools/update_compliance.py`; the two
  append-only JSONL logs; the whole-file-rewritten
  `shipwright_compliance_config.json`; the seven-document refresh set.

- **Empirical probes run:** (all before writing a line of the test)
  - *Can the real chain be driven from a tmp fixture at all?* Executed
    `converge(seed_repo(tmp), RUN)` with the default `regenerate`. **Yes** —
    `reached=True`, `passes=2`, all seven `regenerated`. So `_update_compliance`
    resolves the compliance plugin by path constant from the repo and shells out
    with `sys.executable`; no cross-plugin import, so **ADR-044 never bites** and
    no `cross_plugin` marker is needed.
  - *Does a bare seed reproduce the documented 3-pass ordering coupling?* **No —
    2 passes.** With no FRs and no tagged tests the RTM's layer cells are empty
    either way, so the coupling cannot show. This is why the fixture has to be
    rich; a thin one would have silently proved less than it appeared to.
  - *Does a rich fixture reproduce it?* **Yes — `passes == 3`, three consecutive
    runs, byte-identical document sizes each time.** So the docstring's "pass 1 ≠
    pass 2, pass 2 == pass 3" is real, and the cap of 4 leaves exactly one spare
    pass.
  - *Is the config-rewind assertion non-vacuous?* The producer really rewrites
    `shipwright_compliance_config.json` (appends `iterate` to `phases_covered`),
    and it came back byte-identical (95 → 95 bytes). Measured, not assumed.
  - *Do the append-only logs actually move?* `shipwright_events.jsonl` 555 →
    1305 bytes with **three** `grade_snapshot` events (one per pass), reported in
    `left_alone`. With a failing test layer seeded, `.shipwright/triage.jsonl`
    also moves (186 → 970) and joins `left_alone`. Both retain every original
    line — **but the triage store prepends a `{"v":1,"schema":"triage"}` header
    when the seed lacks one, so `after.startswith(before)` is the WRONG
    assertion.** Found by looking at the bytes; the test asserts line-retention
    instead.
  - *Does the fixpoint survive those moving inputs?* Yes — still 3 passes with
    both logs growing, and exactly one `test-fail:unit` triage row after three
    passes. The dedupKey-idempotence claim holds against the real producer.
  - *Cost, for the CI-timeout question?* ~14 s wall for seed + three passes,
    i.e. ~4 s per `_update_compliance` call against its own 30 s timeout. Enough
    headroom; the test is deliberately ONE converge run shared by all cases.
  - *Are the stray `*.jsonl.lock` files a leak?* No — `.gitignore:83` and the
    `.shipwright/*` wildcard already cover both in the real repo; they showed as
    `??` only because the tmp fixture has no `.gitignore`.
  - **Does the test actually catch D6 — the defect it was written for?** Not
    argued: **mutated and measured.** Adding
    `shipwright_compliance_config.json` to `APPEND_ONLY_INPUTS` (which *is* D6 —
    the config is never rewound) turned the suite red at exactly two cases,
    `::test_the_rewritten_config_ends_exactly_where_it_started` and
    `::test_the_inputs_left_alone_are_exactly_the_two_logs_that_moved`, with the
    other eight still green. Correct locality as well as correct detection.
    Reverted.
  - **Does it catch the all-error trap against the REAL producer?** Second
    mutation: pointed `_update_compliance` at a non-existent script, so it
    returns `[]` exactly as it does on a timeout or a crash. `converge` returned
    `reached=True, passes=2` — it **converged immediately**, which is the
    documented trap verbatim — and 8 of 10 cases went red. The failure message
    printed the outcomes plus `this run took 0.0s over 2 passes`, so the elapsed
    time distinguishes "the producer was unreachable" from "the 30 s timeout
    fired" instead of leaving the reader to guess. Reverted; `git status`
    confirmed clean.
  - *Does it pass on the interpreter CI judges the push with?* The first green
    run was Python **3.13.13** — the ambient one, not CI's. Re-run under
    `uv run --python 3.11 --extra dev` with `CI=true`: **3.11.15, 10 passed in
    14.17s.** (The naive `uv run --python 3.11 pytest` silently resolved the
    system 3.13 pytest; `--extra dev` is what makes the pin real in a fresh
    worktree.)
  - *Does the diff introduce a silent skip or a focused test?*
    `scan_test_hygiene.py --diff` → `no findings`, exit 0.
  - **Was the "green" run actually hermetic?** No — and this is the run's most
    important finding, raised by Stage-2 review and then measured.
    `_update_compliance` shells out with **no `cwd=`**, so the child inherits the
    pytest process's working directory — the shipwright worktree — and `gh api`
    resolves `{owner}/{repo}` from *that* remote. With `gh` logged in the
    ci-security leg was fetching the REAL repository three times per run;
    with `GH_CONFIG_DIR` pointed at an empty directory `ci-security.json` went
    `210 → 210` bytes, unchanged. So the original AC-2 ("all seven change") was
    **green on this machine and would have been red in CI**, where the
    `shared/tests` step exports no token. The conftest's in-process `gh` stub
    cannot help: it does not cross a subprocess boundary. Fixed by neutralising
    `gh` for the child; **runtime fell from ~14 s to ~2.3 s**, which is the
    measure of how much of it was network.
  - *Do the two content markers the review proposed actually work?* **Neither
    did, as proposed — running them is what showed it.** `change-history.md`
    renders git **commits**, not events, so the suggested `"widget list"` (an
    event description) is absent; it now asserts `| Total commits | 2 |`, which
    the seed's two commits determine. And `sbom.md` rendered *"No dependency
    manifests found"* despite a seeded `pyproject.toml`, because
    `parse_pyproject_dep_specs` is a **line** parser that opens only on a line
    equal to `dependencies = [` — the equally valid single-line array form
    parses to zero dependencies. The fixture now writes the multi-line form.

- **Test Completeness Ledger:** 13 behaviours, **0 testable-but-untested**.

  | # | Testable behavior | Category | Disposition | Evidence / reason_code |
  |---|---|---|---|---|
  | 1 | The real `regenerate_tracked_snapshots` → `_update_compliance` chain runs and every one of the seven paths reports a success outcome | integration | tested | `test_compliance_refresh_real_producer.py::test_the_real_producer_reports_success_for_all_seven` PASSED |
  | 2 | The six tree-derived documents change against their committed seed, and none is deleted | integration | tested | `::test_the_real_producer_rewrites_every_tree_derived_document` PASSED |
  | 2b | `ci-security.json` keeps its committed bytes when its source is unreachable, still reports success, and does not break the run | integration | tested | `::test_ci_security_is_left_frozen_when_its_source_is_unreachable` PASSED |
  | 3 | The tree-derived documents carry real derived content (both FR ids in the RTM; the seed's two commits in change-history; the seeded dependency in the SBOM; a v3 manifest with 2 nodes and no `untagged_tests`) | integration | tested | `::test_the_regenerated_documents_carry_real_derived_content` PASSED |
  | 4 | A fixpoint is reached, in 3 passes, strictly under the cap | integration | tested | `::test_the_real_producer_needs_three_passes_to_settle` PASSED |
  | 5 | The rewritten producer config ends byte-identical — and was really rewritten mid-run | integration | tested | `::test_the_rewritten_config_ends_exactly_where_it_started` PASSED |
  | 6 | Every line the append-only logs started with is still there afterwards, in order | integration | tested | `::test_the_append_only_logs_keep_every_line_they_started_with` PASSED |
  | 7 | An append-only input that moved is reported to the operator — and a rewritten one is not | integration | tested | `::test_the_inputs_left_alone_are_exactly_the_two_logs_that_moved` PASSED |
  | 8 | The producer's own appends (one `grade_snapshot` per pass, one dedup'd triage row) do not break the fixpoint | integration | tested | `::test_the_producers_own_appends_do_not_break_the_fixpoint` PASSED |
  | 9 | `converge`'s `regenerate` default is still the real producer | unit | tested | `::test_converge_still_defaults_to_the_real_producer` PASSED |
  | 10 | The `ci-security.json` content-narrowing stays a stated boundary rather than becoming a gap | unit | untestable | `covered-by-existing-test` — `test_compliance_refresh.py::test_ci_security_is_outside_the_fixpoint_claim` already asserts `TREE_DERIVED == REFRESH_SET - {CI_SECURITY_SUMMARY}`, the identical assertion |
  | 11 | An unsound seed, or a run whose `gh` was not neutralised, fails as a FIXTURE fault before the producer runs | integration | tested | `assert_seed_is_sound` runs inside the `real_run` fixture; its three checks gate rows 1–8, the cases that consume the fixture |
  | 12 | The run is hermetic — same result with `gh` authenticated and logged out | integration | tested | measured both ways: `10 passed` each, byte-identical documents; `assert_seed_is_sound` refuses to proceed without `GH_CONFIG_DIR` set |

  **Untestable in this diff:** one row, and it is a duplicate rather than a gap.
  Row 10 was originally written as a tenth test in this module; Stage-1 review
  (N1) showed it restated `test_compliance_refresh.py:145-146` **verbatim**, so
  it was deleted and the row now cites the existing test. Marginal coverage was
  zero either way; carrying two copies of one assertion is how a suite starts
  looking bigger than it is.

  The one behavior deliberately *not* asserted is `ci-security.json`'s
  **content** — it is `DERIVES_FROM_CI_HISTORY` by its own classification, so
  pinning its rendered bytes would assert a property the module explicitly
  disclaims. Its *outcome* and the fact that it was rewritten are asserted
  (rows 1–2). This is a scoped assertion, not an untested behavior.

- **Confidence-pattern check:**
  - *Asymptote (depth):* the pattern this run was most exposed to is
    **a green test that proves nothing** — which is the very failure it exists to
    repair, so "the tests pass" was never going to be an answer here. It showed up
    three times and each time the first yes was wrong:
    (1) "can the real chain be driven?" → yes, and the very next probe showed that
    yes proved almost nothing, because the thin fixture settled in 2 passes and
    hid the coupling; (2) the `@FR` tags read fine and did not parse — the
    manifest carried two `untagged_tests` while the fixture *looked* like it
    exercised the tag→FR join; (3) the append-only logs "kept their content", but
    reading the bytes showed the triage store prepends a schema header, so the
    obvious `startswith` assertion would have been wrong. So the run did not stop
    at green: it **mutated the production code twice** and confirmed the suite
    goes red, at the right cases, for both the D6 rewind defect and the all-error
    trap. That is the depth reached — not "the tests pass" but "the tests fail
    when they should".
  - *Coverage (breadth):* 11 rows, 11 `tested`, 0 `untestable`, 0
    untested-but-testable.
  - *Integration composition:* the `cross_component` flag is **not** raised (no
    pattern-matching path in the diff), so no `category:"integration"` behavior is
    owed on that account. Rows 1–8 and 11 are integration-shaped regardless,
    because composing `converge` → `regenerate_tracked_snapshots` →
    `_update_compliance` → `update_compliance.py` across a subprocess boundary is
    precisely what they exercise.

## Verification (medium+)

- **Surface:** cli
- **Runner command:**
  `uv run pytest shared/tests/test_compliance_refresh_real_producer.py -v`
- **Evidence path:**
  `.shipwright/runs/iterate-2026-08-01-compliance-refresh-real-converge/surface_verification.json`
- **Justification (only if surface=none):** n/a — the surface of a test-only
  change is the test run itself, which F0.5 explicitly admits as `cli`
  ("scripted CLI / skill / pytest invocation against fixture").

## Self-Review

{filled at Step 7}
