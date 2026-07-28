# Mini-Plan: the test phase's record tells the truth about the run

- **Run ID:** iterate-2026-07-27-test-phase-record-honesty
- **Spec:** `iterate-2026-07-27-test-phase-record-honesty.md`
- **Type:** change · **Complexity:** medium · **Risk flags:** none

## Chosen approach

Four defects, four narrow producers, one shared reader. Each item is delivered
as a small module with its own tests; nothing is bolted onto an existing
oversized file.

### Step 1 — `shared/scripts/known_failures.py` (NEW, ~120 LOC)

The single reader for `shipwright_known_failures.json` (AC5).

```python
@dataclass(frozen=True)
class AcceptedFailure:      # one declared entry
    test: str; description: str; ticket: str; added: str; count: int

@dataclass(frozen=True)
class AcceptedBaseline:
    entries: tuple[AcceptedFailure, ...]
    baseline_failure_count: int
    present: bool           # file exists
    malformed: bool         # exists but unreadable → treated as absent

def load_accepted_baseline(project_root) -> AcceptedBaseline
def split_accepted(failure_names, baseline) -> tuple[list[str], list[str]]
    #  → (known_and_accepted, genuine)   — AC4's "reported separately"
def within_baseline(passed, total, baseline_count) -> bool
    #  → gap = total - passed; gap <= 0 or (count > 0 and gap <= count)
    #    verbatim mirror of rtm_generator.py:475-478 (D2)
def is_adopted_project(project_root) -> bool
    #  → bool(run_config["adoption"]) — the empirical signal (D4)
```

Tolerant reader throughout: missing file → `present=False, count=0`; malformed
→ `malformed=True` and the same zero-baseline result compliance produces today,
so audit behaviour is byte-identical.

**Compliance delegates.** `collectors/test_evidence.collect_known_failures`
keeps its exact signature and `KnownFailure` return type, and becomes a thin
adapter over `load_accepted_baseline`. `sys.path` shape copied verbatim from
`compliance_report.py:14-16`; module lives at `shared/scripts/` top level (NOT
`shared/scripts/lib/`) per ADR-045, and imports stdlib only — no `from lib.X`,
so no plugin-local `lib` shadowing.

### Step 2 — `verifiers/test_checks.py` (EDIT, ~+35 LOC)

`check_test_results_file_fresh` gains the baseline branch (AC4):

- `gap = total - passed`; when `gap > 0` and `within_baseline(...)` →
  **PASS**, message `unit 828/830 passed (2 within declared baseline of 2)`.
- `gap > baseline` → the existing WARNING, message now splits the two:
  `unit.passed=820/830 (8 genuine, 2 within baseline)`.
- No file / malformed → today's behaviour exactly (baseline 0).

Import via the same `parents[N] / "shared" / "scripts"` sys.path shape; the
verifier already sits under `shared/scripts/tools/verifiers/`, so the reader is
two directories up — plain relative resolution, no cross-plugin import.

### Step 3 — `plugins/shipwright-test/scripts/lib/journey_coverage.py` (NEW, ~170 LOC)

Per-journey coverage (AC1, AC2, D6).

- `parse_journeys(plan_text) -> list[Journey]` — headings / numbered flow items
  in `claude-plan-e2e.md`; each journey gets a slug.
- `scan_specs(e2e_dir) -> list[SpecFile]` — `**/*.spec.ts`, slug from filename
  plus the `test.describe(...)` / `test(...)` titles inside.
- `check_journey_coverage(project_root) -> dict` — per journey `covered` /
  `uncovered`; `undetermined` when no journeys parse out of the plan.
- Routing: `is_adopted_project()` → brownfield ⇒ `blocking: False` + one triage
  item per uncovered journey (`source="journey-coverage"`, dedup key
  `journey:{slug}`, detail names `/shipwright-adopt` as the route);
  greenfield ⇒ `blocking: True`, exit 1.
- CLI: `--project-root`, `--json`. Exit 0 when nothing blocks.

### Step 4 — `plugins/shipwright-test/scripts/lib/warning_followups.py` (NEW, ~150 LOC)

Durability for the three orphaned warning layers (AC3).

- `emit_warning_followups(project_root, *, e2e=…, consistency=…, design_fidelity=…, run_id=…, commit=…) -> int`
- One item per failing layer, `append_triage_item_idempotent` with
  `match_commit=True`, `window_seconds=24h` — the exact call shape
  `_emit_failures_to_triage` already uses, so cadence and dedup semantics match
  the layer that already works.
- Dedup keys: `test-warning:e2e:{spec-file}` (per failing spec, so two broken
  specs are two follow-ups), `test-warning:consistency:{category}`,
  `test-warning:fidelity:{screen}`.
- Severity: `high` when the layer is wholly failing, else `medium`.
- Best-effort: every emission wrapped, failures to stderr, never changes an exit
  code — a warning layer must not become blocking through its bookkeeping.
- Flaky E2E emits too, at `low`: that is exactly the "needed a retry for weeks"
  visibility item (4) asks for.

### Step 5 — `playwright_runner.py` (EDIT, ~+55 LOC)

Test-level classification (AC6, AC7).

- `_classify_test(test) -> ("expected"|"unexpected"|"flaky"|"skipped", retries)`:
  prefer Playwright's own `test["status"]`; fall back to deriving from
  `results[]` when absent (our legacy fixtures, and older reporter output).
- Counters move from per-attempt to per-test: `total`, `passed`, `failed`,
  `skipped`, plus new `flaky` and `flaky_tests: [{title, file, retries}]`.
- `success = failed == 0` — unchanged, so flaky stays non-blocking (D3).
- `failures[]` keeps its existing shape (title/file/status/error) and now
  carries `retries`.

### Step 6 — Prose + catalog

| File | Change |
|---|---|
| `skills/test/references/step-2.5-e2e-spec-generation.md` | replace the wholesale skip with the per-journey check; keep generation on the no-specs path |
| `skills/test/references/step-3.5-e2e-verification.md` | reconciliation total becomes `expected + unexpected + flaky + skipped`; record `flaky` |
| `skills/test/references/step-3-playwright-e2e.md` | flaky reported, not blocking |
| `skills/test/references/results-enforcement.md` | new column: what each non-blocking layer leaves behind |
| `skills/test/references/completion-gate.md` | known-vs-genuine split in the required result |
| `skills/test/references/step-5-report-results.md` | summary lines for flaky, known-accepted, journey gaps |
| `skills/test/SKILL.md` | step index rows for 2.5 / 3.5 |
| `.shipwright/planning/01-adopted/spec.md` | mint FR-01.06 criteria (AC8) |
| campaign evidence ledger | rows 5/6 status, and the triage table's landed items |
| `docs/hooks-and-pipeline.md` | test phase now reads `shipwright_known_failures.json`; three new triage producers |
| `docs/guide.md` | check only — no command/flag change expected |

### Step 7 — Tests (TDD, written first per layer)

- `shared/tests/test_known_failures.py` — reader, tolerant paths, `within_baseline`
  boundary (gap == count passes, gap == count+1 does not), adoption signal.
- `shared/tests/test_known_failures_compliance_parity.py` — the delegation
  actually preserves compliance's output for present / absent / malformed
  (the AC5 integration probe).
- `shared/tests/test_test_checks_baseline.py` — validator branch.
- `plugins/shipwright-test/tests/test_journey_coverage.py` — parse, match,
  greenfield block, brownfield triage.
- `plugins/shipwright-test/tests/test_warning_followups.py` — one item per
  failing layer, dedup across two runs, never raises.
- `plugins/shipwright-test/tests/test_playwright_runner.py` — extend: flaky
  counted, retries not inflating total, real-reporter shape and legacy shape.

All new tests carry `@pytest.mark.covers("FR-01.06")`.

## Alternative considered — and rejected

**Copy the known-failures parse into the test plugin** (a ~30-line reader beside
`test_runner.py`) instead of extracting a shared module and touching compliance.

- *For:* smaller diff; no compliance file changes; zero risk to the audit path.
- *Against:* it delivers item (3)'s letter and misses its point. The recorded
  defect is *"two components hold different truths about it"*; a second parser
  is a second truth waiting to drift — the two would diverge the first time
  either side gained a field. The whole card is "the record should describe what
  actually happened", and two readers of one file cannot guarantee that.
- *Decision:* extract. The risk is contained by keeping
  `collect_known_failures`'s signature and return type frozen and pinning the
  delegation with a parity test that asserts present / absent / malformed all
  produce what compliance produced before.

**Also considered and rejected:** making flaky a fourth mutually-exclusive
bucket (`passed + failed + skipped + flaky == total`). Cleaner arithmetic, but
it silently changes `passed` for every existing consumer of the shape and
contradicts "it stays a pass". D3 keeps flaky as a subset.

## Verification

- `uv run pytest shared/tests/ -q` and `cd plugins/shipwright-test && uv run pytest tests/ -q`
- `uv run pytest plugins/shipwright-compliance/tests/ -q` — the delegation must
  not move a single compliance assertion.
- `uvx ruff@0.15.15 check .`
- F0 full gate, then F0.5 (surface `none` + justification — this is a
  Python/CLI monorepo change with no web surface; the CLI entry points are
  exercised by the surface runner instead).

## Risks

| Risk | Mitigation |
|---|---|
| Delegation changes compliance behaviour | parity test on present/absent/malformed; full compliance suite run |
| `lib` namespace collision (ADR-045) | module at `shared/scripts/` top level, stdlib-only imports |
| Journey parsing over-fits this repo's plan format | three-state output; `undetermined` when nothing parses, never a false "uncovered" |
| Triage flood from a persistently failing layer | idempotent append + stable dedup keys + `match_commit=False` + `window_seconds=None` (see R2) |
| Playwright shape assumptions | decision table (R6) + fixtures for every row |

---

## External plan review — dispositions

Reviewed by `external_review.py --mode iterate` (openrouter: gemini-3-pro +
gpt-5.6-terra), both legs succeeded, not degraded. Every finding was checked
against the code before being accepted or declined. **8 accepted, 4 declined.**

### R1 — operational wiring (both, HIGH) — **ACCEPTED, plan changed**

Correct and the most important finding: modules with CLIs that nothing invokes
are testable in isolation and dead in production. Gemini additionally asked
where the consistency / fidelity failure states would come from.

**Resolution — no new artifact is needed, because the record already is one.**
`shipwright_test_results.json` carries top-level `e2e`, `consistency`,
`design_fidelity` blocks (that is exactly what compliance's
`collectors/test_evidence._parse_test_results_file` reads today). So:

- `warning_followups.py` gains a CLI: `--results-file shipwright_test_results.json`.
  It reads the finished record and emits — the layer scripts stay untouched, and
  the emitter is driven by the same artifact the audit phase reads. This also
  makes it re-runnable over an existing record.
- `journey_coverage.py` runs from the project root against the plan + `e2e/` tree
  on disk; no upstream state needed.
- Both are invoked from named steps: journey coverage in **Step 2.5**, warning
  follow-ups in **Step 5** (after all layer results are final, before the phase is
  marked complete).
- An integration test drives *both* from a realistic project fixture, so the
  wired path — not just the units — is pinned.

### R2 — `match_commit=True` floods the board (both, HIGH) — **ACCEPTED, plan changed**

Verified in `triage.py:452-470`: match is `source` + `dedup_key` + *optionally*
`commit`. With `match_commit=True`, every commit re-fires the item — which is
precisely what AC3 forbids. The performance check was the wrong precedent to
copy here: a budget overrun is per-commit, a persistently broken suite is one
issue until someone fixes it.

**Resolution:** `match_commit=False` + `window_seconds=None`, the shape
`github_triage`, `check_drift` and `artifact_sync` already use ("a finding stays
exactly one open inbox item"). A test drives two runs at **different commits**
and asserts one item.

### R3 — skipped tests consume baseline (openai, MEDIUM) — **ACCEPTED, plan changed**

Real. `gap = total - passed` counts skips as failures. Compliance lives with
this deliberately (it reads the gap as skips), but the *test phase* has better
information: `test_runner.run_tests` already returns an explicit `failed` count.

**Resolution:** the validator prefers explicit signal and degrades honestly —
`unit.failed` when present, else `total - passed - skipped`, else `total - passed`
with the message naming that it is a gap, not a failure count. Fixtures:
skipped-only, skipped-plus-failed, failed-only, neither.

### R4 — AC4 needs failure *identities*, not just arithmetic (openai, MEDIUM) — **ACCEPTED, plan changed**

Right, and it is the same honesty defect this card exists to fix — an aggregate
allowance dressed up as "these specific failures are accepted" would be a new
false record.

**Resolution:** two clearly distinct outputs. Where identities exist (Playwright
`failures[]`), `split_accepted()` runs over them and the report names which
failures are known-and-accepted. Where only counts exist, the result is labelled
`aggregate baseline allowance` and explicitly does **not** claim any particular
failure is accepted. A test covers the divergent case (declared failure absent,
unrelated failure present).

### R5 — brownfield routing needs the structured field (openai, MEDIUM) — **ACCEPTED, plan changed**

Checked the schema: the established routing mechanism is `launchPayload` — a
ready-to-paste slash command + context block (`triage.py:373-376`;
`_triage_bundle._build_launch_payload` is the reference implementation).

**Resolution:** brownfield journey gaps set
`launch_payload="/shipwright-adopt\n\nContext: …"`, not free text in `detail`.
Asserted on the emitted item's field, not on its prose.

### R6 — Playwright fallback decision table (openai, MEDIUM; gemini #3, MEDIUM) — **ACCEPTED, plan changed**

Both flagged it; the table is now normative rather than "derive from results[]":

| Signal | Outcome | Retries |
|---|---|---|
| `test.status == "expected"` | passed | `max(result.retry)` |
| `test.status == "flaky"` | passed **and** flaky | `max(result.retry)` |
| `test.status == "unexpected"` | failed | `max(result.retry)` |
| `test.status == "skipped"` | skipped | 0 |
| status absent — last result `passed`, >1 attempt | passed **and** flaky | `len(results) - 1` |
| status absent — last result `passed`, 1 attempt | passed | 0 |
| status absent — last result `failed` / `timedOut` / `interrupted` | failed | `len(results) - 1` |
| status absent — every result `skipped` | skipped | 0 |
| `results` empty, or an unrecognised status | **failed**, error `no resolved result` | 0 |

The last row is the point: an unknown shape is never silently promoted to a
pass. Fixtures for every row.

### R7 — duplicate journey titles collapse (openai, LOW) — **ACCEPTED, plan changed**

Journey identity becomes `{index:02d}-{slug}` (position + slug), used in both
the report and the dedup key, so two journeys with the same title stay two
items. A missing / unreadable plan yields `undetermined` **with a diagnostic**,
never an empty success.

### R8 — bound the ingested strings (openai, LOW) — **ACCEPTED, cheap**

Titles capped at 160 chars (the cap `_emit_failures_to_triage` already uses),
details at 2000, control characters stripped. Serialization stays on
`append_triage_item_idempotent`; nothing hand-assembles JSONL.

### R9 — `is_adopted_project` does not belong in `known_failures.py` (gemini, LOW) — **ACCEPTED, plan changed**

Fair on cohesion. It goes to its own `shared/scripts/project_facts.py`
(stdlib-only, top-level per ADR-045 — *not* `shared/scripts/lib/config.py`,
which would collide with the test plugin's own `scripts/lib/` namespace).
Compliance's `_is_adopted` delegates there too, so the adoption signal also
stops having two definitions.

### Declined

- **gemini #1's suggested mechanism** (make the layer scripts drop
  `.consistency-status.json` sidecars). The *finding* is accepted (R1); the
  *remedy* is declined — inventing new per-layer state files when the phase
  already writes one authoritative record would add exactly the kind of
  second-source-of-truth this card is closing.
- **openai #4's fallback** ("or explicitly scope the requirement to one item per
  issue per commit and revise the acceptance language"). Declined: weakening AC3
  to match the flooding behaviour is the wrong direction. Fixed the behaviour
  instead.
- **openai #3's fallback** ("if audit's arithmetic must remain unchanged,
  document this limitation"). Declined for the test phase for the same reason —
  the phase has `failed` available, so it can be right rather than documented as
  wrong. Compliance's arithmetic *is* left unchanged (D2 / AC5 depend on it).
- **openai #8's suggestion to add sanitization infrastructure.** Declined as
  scoped; bounded lengths + the existing JSON writer are proportionate, and the
  reviewer said as much.
