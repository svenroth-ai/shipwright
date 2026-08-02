# Mini-Plan: the compliance refresh is driven through its real producer

- **Run ID:** iterate-2026-08-01-compliance-refresh-real-converge
- **Spec:** `.shipwright/planning/iterate/2026-08-01-compliance-refresh-real-converge.md`
- **Complexity:** medium

## Files to create/modify

| File | Change | Why |
|---|---|---|
| `shared/tests/test_compliance_refresh_real_producer.py` | **new** (273 LOC) | The whole deliverable: one real `converge()` over a rich fixture, nine assertions on the single captured result |
| `shared/tests/_compliance_refresh_fixtures.py` | **edited** (89 → 233 LOC) | Carries the rich project seeder (`seed_project`, `assert_seed_is_sound`, `read_lines`) and the constants the new module names |

> **Deviation from the plan as first written, recorded rather than quietly made.**
> This plan said the fixtures module would stay unchanged and the rich seeder
> would live in the new test module — one caller, so no shared structure
> (Simplicity First). Written that way, the test module came to **381 lines**,
> over the constitution's 300-line cap for tests. The cap forced a split, and
> `_compliance_refresh_fixtures.py` is the established home for exactly this
> subject ("the constants and the seeding function live here"). Inventing a
> second `_*_fixtures` module beside it would have been the worse answer. Both
> files now sit under the cap (273 / 233) and neither carries a baseline entry,
> so nothing is ratcheted.

No production file is touched. That is a property of the change, not an
accident: if this test needed a production edit to become drivable, the edit
would be the finding.

## Work breakdown

1. **Module scaffold + path inserts.** Copy the ADR-045 pattern verbatim from
   `test_compliance_refresh_produce.py` (unconditional inserts, tests dir first,
   `shared/scripts` second). Import `seed_repo` / `RUN` / `git` from
   `_compliance_refresh_fixtures`.
   *Test expectation:* module imports cleanly under `pytest shared/tests`.
2. **`seed_project(root)`** (landed in `_compliance_refresh_fixtures.py`, see the deviation note) — layer the rich `.shipwright` tree on top of
   `seed_repo`: `01-core/spec.md` with FR-01.01 + FR-01.02, an `@FR`-tagged test
   module, `shipwright_events.jsonl` (one `work_completed`, one failing-layer
   `test_run`), `.shipwright/triage.jsonl` (one item), a
   `shipwright_compliance_config.json` missing `iterate`, run/test-results
   configs, a `pyproject.toml` for the SBOM leg, a decision log; then one commit.
   *Test expectation:* the seed commits clean; `git status --porcelain` empty.
3. **Module-scoped `real_run` fixture** — snapshot documents + `PRODUCER_STATE`,
   run `converge` **once** through a recording wrapper that delegates to the real
   `produce_mod.regenerate` and captures `PRODUCER_STATE` after each pass, then
   snapshot again. Returns one frozen result object every test reads.
   *Test expectation:* ~14 s once, not once per test.
4. **The assertions**, one test each (ledger rows 1–9; row 10 turned out to be
   already covered by `test_compliance_refresh.py` and row 11 is the fixture
   gate, so the module ships **nine** test functions).
   *Test expectation:* all pass; each fails with a message naming the cause.
5. **Actionable failure on a degraded producer** — if any outcome is `error`,
   say so with the two real causes (the 30 s `_update_compliance` timeout on a
   slow runner; an unreachable compliance plugin) rather than letting a
   downstream assertion fail confusingly.
6. **Triage card** for the `inputs_left_alone` reporting mismatch (Out of Scope
   item 1), filed against the **main** root at F12.

## Test strategy

- Layer: integration (subprocess boundary), living in `shared/tests` — the root
  that already reaches the compliance plugin by path constant.
- **No marker.** `slow` would exclude it from CI (`-m "not slow and not
  cross_plugin"`, `ci.yml:176`), which defeats the point; `cross_plugin` does not
  apply because the chain crosses a *subprocess*, not `sys.path`.
- One `converge` run shared module-wide keeps the cost at ~14 s.
- E2E: the F0.5 `cli` runner is this module itself.

## Alternative approach considered — and why rejected

**Import `update_compliance` and its `scripts.lib.*` collectors directly, and
call the generators in-process** (the shape `test_compliance_audit_triage_emit.py`
uses via `importlib.util.spec_from_file_location`).

Rejected. It would be *faster* — no three subprocess round-trips — and it would
give tidier failure messages. But it tests a different thing. The defect class
this run exists for lives in `_update_compliance`'s **error swallowing**: it
catches a non-zero exit, its own 30 s timeout and every exception and returns
`[]`, which `regenerate_tracked_snapshots` then converts into "error" outcomes
*without writing anything*. In-process generator calls bypass exactly that layer,
so the chain the card names — `regenerate_tracked_snapshots` → `_update_compliance`
— would still be undriven while the test looked comprehensive. Worse, importing
the compliance plugin's `scripts.lib` into a `shared/tests` session is the
ADR-044 namespace collision the repo hard-fails on, so it would need a
`cross_plugin` marker and would then be **excluded from CI** — a test that never
runs where it matters.

Keeping the subprocess is not a cost here; it is the reason the test is worth
writing.
