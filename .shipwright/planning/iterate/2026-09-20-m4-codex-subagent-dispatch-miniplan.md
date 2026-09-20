# Mini-Plan: m4-codex-subagent-dispatch

- **Run ID:** iterate-2026-09-20-m4-codex-subagent-dispatch

**Scope note:** an earlier draft of this plan also built a
`.codex/agents/*.toml` generator (Option A below). It was built, internally
reviewed and fixed, then cut after the dedicated Architecture Review (both
legs, unanimous) and the user's own confirmation — see the iterate spec's
"External Review" section. This plan now reflects only the shipped scope
(Option B).

## Files created/modified

1. `shared/scripts/lib/codex_review_roles.py` — **edit**. Added
   `REASONING_EFFORT_ROLES` (a `frozenset[str]`, `{"spec", "code", "doubt"}`)
   and `CODEX_REVIEW_REASONING_EFFORT`/`CODEX_REVIEW_SANDBOX_MODE`
   constants. `plan_review` keeps its existing behavior untouched (out of
   scope, see spec).
2. `shared/scripts/lib/codex_review_transport.py` — **edit**. `argv` gains
   `"-c", f"model_reasoning_effort={CODEX_REVIEW_REASONING_EFFORT}"`, only
   for roles in `REASONING_EFFORT_ROLES` (guards `plan_review`, unaffected).
   `run_codex_review` also now returns a `transport_note` naming the
   effective model plus effort/sandbox for those roles (bare model for
   others), and `--sandbox` is sourced from the same `CODEX_REVIEW_
   SANDBOX_MODE` constant rather than a duplicated string literal.
3. `shared/tests/test_codex_review_transport_reasoning_effort.py` — **new**
   (split out of `test_codex_review_transport.py` to stay under its 300-line
   cap, mirroring that file's own `_model_override.py` precedent). Covers
   the reasoning-effort flag (present for the cascade, absent for
   `plan_review`), and that it still applies under an explicit `model=`
   override — with `transport_note` reflecting the resolved model, not the
   hardcoded default.
4. `shared/tests/test_codex_review_cascade_distinctness_fixture.py` —
   **new**. The AC2 fixture: monkeypatches `subprocess.run` to return three
   distinct canned payloads across three sequential `run_codex_review`
   calls (`spec`, `code`, `doubt`), records each via `record_review_pass.py
   record` (the real CLI, driven as a subprocess — matches
   `test_record_review_pass_cli.py`'s own AC8 pattern), then reads back
   `reviews.json` and asserts three distinct rows keyed by review type, each
   carrying its own distinct payload content. The `subprocess.run` monkeypatch
   is scoped per-role via `monkeypatch.context()`, since `transport.subprocess`
   and the harness's own `record_review_pass.py` launch share the same module
   object. The fixture also sets `PYTHONIOENCODING=utf-8` on the child
   process — a pre-existing Windows cp1252-vs-UTF-8 gotcha surfaced once the
   doubt payload's em-dash reached `record_review_pass.py show`'s own stdout
   decode (see the fixture's own inline comment; no shared-code change, fixed
   entirely inside this test).
5. `.shipwright/planning/01-adopted/spec.md` — **edit** (FR-01.11 AC37).
6. `AGENTS.md` — untouched in the shipped scope (a contributor-workflow
   note for the generator was added, then removed with the cut).

## Work Breakdown

1. Add `REASONING_EFFORT_ROLES` + constants to `codex_review_roles.py`.
   Test: import-time `assert` that the set is a subset of `ROLE_SCHEMAS`.
2. Wire `model_reasoning_effort` (and the shared `--sandbox` constant) into
   `codex_review_transport.run_codex_review`'s argv, sourced from
   `REASONING_EFFORT_ROLES`; `plan_review` (not a member) keeps today's argv
   unchanged. Test: `test_codex_review_transport_reasoning_effort.py`.
3. Compute and return `transport_note` from `run_codex_review`. Test: same
   file, plus the AC2 fixture's own assertion on the recorded row.
4. Write the AC2 distinctness fixture. Test: itself IS the test — asserts
   on `reviews.json` content after three simulated passes.
5. Update FR-01.11 (AC37) and prep ADR content for F3.

## Test Strategy

- Unit tests for the transport's argv/`transport_note` change — pure/mocked,
  no live `codex exec` calls (matches the existing test suite's own
  convention — `is_codex_available` is monkeypatched everywhere, never
  actually shelled out to in CI).
- One integration-shaped fixture test is the AC2 proof — runs against a
  real temp `reviews.json` via the real `record_review_pass.py` write path
  (not itself mocked), with only the outermost `subprocess.run` (the
  `codex exec` call) mocked. Same "mock at the process boundary, exercise
  the real internal wiring" shape the existing transport tests already use.
- No E2E / browser layer — this is backend/CLI tooling, no `dev_url`, no
  UI. F0.5 Backend-affects-Frontend rule does not fire.
- Single test root (`shared/tests`) for the shipped scope — no
  `shared/scripts/tools/tests` split needed once the generator was cut.
  `uv run pytest shared/tests/test_codex_review_transport*.py
  shared/tests/test_codex_review_cascade_distinctness_fixture.py -v`.

## Alternative Approach — Option A, built then cut (see spec's External Review)

**Option A: also build a `.codex/agents/*.toml` generator, three committed
profile files, and a drift test**, satisfying M4's literal text ("map
review roles to approved Codex subagent profiles... rendered as
Shipwright-managed project files under `.codex/agents/shipwright-*.toml`").
This was the FIRST choice made in this iterate — fully implemented (a
generator script, three committed TOML files, a `--check` drift gate, 25+
tests) and reviewed to a high standard by an opus-tier Internal Plan Review
(10 findings, all fixed).

**Cut, after being built, because:** the dedicated Architecture Review
(`external_review.py --mode architecture`, asking specifically "should this
exist at all" over a brief, not the plan) found — independently, on both
legs — that the generated files have no automated consumer: `codex exec`
cannot invoke a named custom agent from a non-interactive session (the
Design Notes' own verified upstream gap), so the generator's permanent
maintenance cost (contributor workflow rule, drift gate, collision-state
machine) bought documentation and speculative future value, not current
execution reliability. Presented directly to the user (who had named this
exact scope item in the original request), the user confirmed the cut and
asked how the model is then defined without it — it already was,
independently, in `codex_review_roles.py`; nothing about model/effort/
sandbox definition was lost. **What survives from Option A:** the shared
`CODEX_REVIEW_REASONING_EFFORT`/`CODEX_REVIEW_SANDBOX_MODE` constants
(already canonical, not generator-specific) and the `transport_note`
evidence field the same Architecture Review's sibling findings motivated.
