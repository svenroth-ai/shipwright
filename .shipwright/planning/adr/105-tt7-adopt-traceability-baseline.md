# ADR 105 — TT7 adopt establishes the traceability baseline

- Run-ID: `iterate-2026-07-15-adopt-traceability-baseline`
- Campaign: `2026-07-15-test-traceability-layers` (sub-iterate TT7, serial #7 of 8)
- Spec: `.shipwright/planning/iterate/campaigns/2026-07-15-test-traceability-layers/sub-iterates/TT7-adopt-traceability-baseline.md`
  (+ `Spec/test-traceability-across-layers.md` §6, §7, §8, §11 — gitignored)

## Decision

Add adopt **Step E.17 — Traceability Baseline** (after Step E spec write, before Step F
compliance seeding), driven by one orchestrator tool
(`plugins/shipwright-adopt/scripts/tools/seed_traceability_baseline.py`) + two adopt-local
pure libs (`traceability_baseline.py`, `traceability_layers.py`), plus a one-line
compliance wiring (`test_links` added to `update_compliance.py`'s `adopt` phase). At
onboarding it: (1) scaffolds the `@FR` tag convention into `.claude/rules/` (write-if-absent
/ append-section-if-present / skip-if-already-there); (2) subprocesses the TT6 backfill
engine VERBATIM to tag existing tests (never `--repo-follows-split-convention` — brownfield
`NN-` is execution order, so split matches stay advisory); (3) takes a **repo-wide** (not
diff-scoped) skip/quarantine inventory reusing the TT4 scanners; (4) resolves
`required_layers` ambiguity against P1's predeclared-decision fixture (unattended → never
stalls) and writes the decided layers back into the spec BEFORE Step F; (5) files
orphan/unmapped/proposal + every pre-existing skip as tracked triage carrying the TT6 orphan
category; and (6) writes `.shipwright/adopt/traceability-baseline.json` for the Step H
banner. Step F's collector then emits the baseline manifest from the just-written tags. A
zero-test repo backfills clean (empty manifest, no triage, no gate).

## ADR-045 discipline

The orchestrator imports NEITHER the shared `lib` package NOR the compliance `scripts.lib`
package in its interpreter: backfill (shared `lib`) runs in a subprocess; the manifest
collector (compliance `scripts.lib`) runs in Step F's own interpreter. This interpreter
imports only top-level `shared/scripts` modules (`triage` + the TT4 hygiene scanners) and
the adopt pure-libs. Reuse-not-fork: TT6 engine subprocessed verbatim; TT1 collector owns
`required_layers` inference (the tool only classifies cell authorship to find ambiguous
FRs); TT4 scanners reused in repo-wide (not diff-scoped) mode; TT1 `tests.md.template`
scaffolded verbatim.

## No false gate

Every adopted FR is `inferred_legacy` / `defaulted_legacy`, which the compliance `D-layer`
detective (`_LEGACY_SOURCES`) routes to ADVISORY (WARN, no `any_fail`) — so a MISSING layer
at onboarding never turns the gate red (Spec §9 landmine). `snapshot.json` is untouched
(the baseline lives in a separate compliance manifest + adopt summary), so the WebUI
snapshot contract test stays green (AC3); no `schema_version` bump.

## External-Plan-Review-Findings (GPT-5.4 + Gemini 3.1 Pro, OpenRouter — succeeded, not degraded)

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| O1 | High | Where are resolved decisions PERSISTED? A predeclared decision must reach the authoritative spec before Step F, not be held only in the summary. | accepted-and-fixed: `apply_layer_decisions_to_spec` rewrites the `Layers` cell (`<layers> (inferred)`) for predeclared-resolved FRs before Step F; E2E asserts the decision reaches the manifest (`FR-03.02 → ["e2e"]`). |
| O2 | High | Interactive path must ask; unattended consumes fixtures; "fall back to inference" could discard a user choice. | accepted-with-reason: the resolver is pure + returns explicit records (`inference_default` is an explicit deferral, not a silent discard); the SKILL assigns the interactive `AskUserQuestion` branch to the agent. `AskUserQuestion` is an agent tool, not a script capability. |
| O3 | High | Is TT6's report a stable machine-readable schema with category/path/test-id/confidence? | accepted-verified: TT6 `backfill-report.json` (`run_backfill`) is canonically-sorted JSON with `orphans.{confirmed,possible,unmapped}` + `proposals` carrying `test`/`tagged_fr`/`reason`/`candidate_fr`/`confidence`; consumed as JSON, never reparsed prose. |
| O4 | Med | `test_links` on the adopt phase may change ordering; Step F could run before tags are written. | accepted-and-fixed: Step E.17 (backfill) runs BEFORE Step F in the SKILL; a round-trip E2E asserts the Step F manifest carries the E.17 tags; the phase-contract test was updated. |
| O5 | Med | Scaffold underspecified for existing files; is there an `integration-tests` template? | accepted-and-fixed: append-a-managed-section-if-the-file-exists-without-`@FR`; `integration-tests.md.template` verified to exist. |
| O6 | Med | Skip inventory needs stable triage identity + dedup + rerun behavior. | accepted-and-fixed: `dedup_key = adopt-skip::<file>:<line>::<pattern>` + `append_triage_item_idempotent(window=None)` → stable, deduped, idempotent (rerun test). Auto-reconciling a removed skip on re-adopt is out of scope (adopt = once-per-repo). |
| O7 | Med | Need a with-orphans/unmapped E2E asserting persisted triage + category, esp. unmapped-not-stale. | accepted-and-fixed: E2E adds an unmapped test + asserts the persisted item's `dedupKey` category prefix, title has no "stale", detail says "never". |
| O8 | Med | "No false gate" is an integration contract; test a missing layer's severity + zero-test manifest presence. | accepted-and-fixed: E2E asserts adopted FRs are `inferred_legacy`/`defaulted_legacy` (→ advisory) and the zero-test manifest EXISTS (empty, not missing). |
| O9 | Med | Plan omits marketplace sync + strict cache; pin TT1/3/4/6 contracts. | accepted: marketplace sync + `check_plugin_cache_sync --strict` run at finalize; all four contracts were read + pinned before build. |
| O10 | Low | Subprocess hardening + validate report paths. | accepted-already-done: list-form `subprocess.run([sys.executable, …])`, no `shell=True`, resolved paths, JSON-only consumption. |
| O11 | Low | The two libs are adopt-specific — place under the adopt plugin. | reject-with-reason (misread): they ARE under `plugins/shipwright-adopt/scripts/lib/`, not shared. |
| G1 | High | File sprawl (3 files, >500 LOC) — collapse to one. | reject-with-reason: the 300-LOC source cap (hard, enforced by the bloat baseline anti-ratchet) forbids a single ~530-LOC file; the split is cohesive (layers vs. baseline-scaffold/inventory/triage) and the pure/orchestrator boundary is required for the ADR-045 subprocess discipline. |
| G2 | Med | Scaffold silently misses `@FR` if the rule file already exists. | accepted-and-fixed: same fix as O5 (append the convention section to a pre-existing file). |
| G3 | Med | Unattended fallback could stall if the collector prompts. | reject-with-reason: the "collector" is `parse_requirements`, a pure non-interactive parser (no prompts); the resolver itself never prompts. |
| G4 | Low | Subprocess path injection. | accepted-already-done: list-form, no shell. |

## External-Code-Review-Findings (GPT-5.4 + Gemini 3.1 Pro, OpenRouter — succeeded, not degraded)

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| C1 | High | Interactive path not implemented; fixture not auto-wired. | accepted-with-reason (same as plan-O2): the tool is pure by design; the SKILL assigns `AskUserQuestion` to the agent and `--decisions` to the campaign orchestrator — a script cannot call the agent's question tool. |
| C2 | Med | `--dry-run` still writes `.claude/rules/*` (scaffold ran unconditionally). | accepted-and-fixed: `scaffold_tag_convention(dry_run=…)` classifies without touching disk; new test asserts dry-run mutates nothing. |
| C3 | High | A failed backfill → empty report → adoption "succeeds" with a false baseline. | accepted-and-fixed: a backfill error now sets `backfill_ok:false` + a loud top-level `warnings[]` (stderr + summary) so the operator/orchestrator remediates instead of trusting a false-green. |
| C4 | Med | Orphan `category` not persisted into the triage item. | accepted-and-fixed: the category is carried structurally in the persisted `dedupKey` prefix (`adopt-orphan-confirmed`/`adopt-orphan-possible`/`adopt-unmapped`/`adopt-skip`); the E2E now asserts on `dedupKey`, not prose. (No triage-schema change — a shared cross-repo contract — was warranted.) |
| C5 | Med | Python scanner only flags un-CI-guarded skips, not every skip. | reject-with-reason: the brief designates `scan_for_silent_skip_without_ci_guard` as "the Python skip scanner"; a CI-guarded conditional skip is the *sanctioned* pattern (its justification), not standing rot — flagging it would be noise. TS/JS's justification is the quarantine block; Python's is the CI-guard. |
| C6 | Med | The with-tests E2E doesn't prove a tagged test reaches the manifest as a link (only that the FR parsed). | accepted-and-fixed: the fixture now carries a `@pytest.mark.covers("FR-01.01")` unit test; the E2E asserts it lands under `FR-01.01.tests.unit` in the Step F manifest (real tag→FR→manifest round-trip). |

## Adversarial Doubt-Review Findings (coordinator cascade — bite adopt's real target)

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| D1 | Med | `enumerate_test_files` used `rglob('*')` then filtered `_PRUNE_DIRS` — recurses INTO a large/committed `node_modules` and materializes+sorts every vendored path before filtering → O(all-files) hang on the brownfield-JS repo adopt exists for. | accepted-and-fixed: rewritten with `os.walk` + in-place `dirnames[:]` prune, so a vendored subtree is NEVER descended into (moved to `traceability_skip_inventory.py`). New test: a `node_modules/` subtree is not enumerated. |
| D2 | Med | `apply_layer_decisions_to_spec` / `find_ambiguous_frs` split on `.strip('|').split('|')` — not escaped-pipe aware, no cell-count guard, `splitlines()`+`'\n'.join()` CRLF→LF churn, `written+=1` on an unchanged cell (non-idempotent). The operator-supplied-decisions path DOES write a real repo's spec.md. | accepted-and-fixed: `_split_row` splits on UNESCAPED pipes only + a cell-count-vs-header guard skips a mis-columned row; the write reads/writes RAW bytes with `splitlines(keepends=True)` (per-line ending preserved, no `read_text(newline=)` — 3.13-only); a cell equal to the target is skipped (idempotent). New tests: piped Description not mis-columned, un-escaped-pipe row guarded, CRLF preserved + re-run writes 0. |
| D3 | Low | The Python scanner flags `skipif` + `pytest.skip()` but NOT `@pytest.mark.skip` — the commonest disable idiom + the classic standing rot §11-R5 targets. | accepted-and-fixed: added a local AST `_scan_pytest_mark_skip` (adopt-scoped, so the shared cross-consumer scanner's contract is untouched — a comment/string mention never matches). New test. |
| D4 | Low | `build_skip_triage_items` emits one card per finding — a skipif-heavy cross-platform lib floods the Inbox with hundreds of cards on first adopt. | accepted-and-fixed: above `_SKIP_ROLLUP_THRESHOLD` (10) findings, one rolled-up summary card (per-pattern count, max severity); at/below, granular. New test. |
| D5 | Low (code L1) | `--dry-run` still wrote `.shipwright/backfill/backfill-report.{json,md}` (TT6 `write_report` is unconditional) — contradicting "touches nothing". | accepted-and-fixed: the dry-run backfill report is routed to a `tempfile.mkdtemp` dir (`--report-dir`) and removed; `test_dry_run_mutates_nothing` now asserts `.shipwright/backfill/` is absent. |
| D6 | Low (docs) | ADR-045 docstrings claimed "imports NEITHER the shared lib package" — FALSE (`triage` lazily binds `sys.modules['lib']=shared/scripts/lib`); "for the Step H banner" over-claimed (H never reads it); the `(inferred)`-collapse was undocumented. | accepted-and-fixed: docstrings now state the real argument ("the only lib that binds is shared/scripts/lib via triage; the compliance + backfill libs are subprocessed, so no two lib packages coexist"), soften the summary to "durable run summary", and note the deliberate `(inferred)` collapse (provenance survives in `layer_resolutions`). |
| D7 | Low (code L4) | The subprocess round-trip proving AC1/AC4 is `pytest.mark.slow`. | confirmed-runs-in-CI + fixed: adopt's `addopts` carry NO `-m "not slow"` (verified via `--collect-only`), so the slow lane runs in the adopt CI (`pytest tests/ -v`). Belt-and-suspenders: added a NON-slow `test_collector_links_a_tagged_test_to_its_fr` that subprocesses only the collector over a tiny fixture, so the wiring is gated by the DEFAULT lane even if slow is later excluded. |

_Bloat note:_ the D1/D3/D4 additions crossed `traceability_baseline.py` past the 300-LOC cap, so the repo-wide skip inventory was extracted to a cohesive sibling `traceability_skip_inventory.py` (re-exported); the layer-resolution tests were split into `test_traceability_layers.py`. All source + test files ≤300 LOC; the bloat baseline is NOT ratcheted.

## Self-Review (7-item checklist)

1. **Spec Compliance** — pass: implements §6 adopt row + §11-R5 (repo-wide skip inventory,
   predeclared-decision never-stall) + §7 backfill-at-onboarding; reuses TT1/3/4/6 without
   forking; AC1–AC5 covered by tests.
2. **Error Handling** — pass: backfill failure → loud warning (not silent success);
   missing/malformed decisions → `{}` (defaults, never crash); missing spec → empty
   resolution; zero-test → clean empty baseline.
3. **Security Basics** — pass: list-form subprocess (no `shell=True`), `sys.executable`,
   resolved paths; triage titles/details are neutral test-hygiene text (constitution NEVER
   respected — no secrets/file:line/exploit detail).
4. **Test Quality** — pass: 20 unit (baseline + layers) + 5 subprocess E2E incl. tag→FR→
   manifest round-trip, a fast non-slow collector-link guard, dry-run-no-mutation (incl.
   no backfill report), predeclared-decision→manifest, unmapped-not-stale, zero-test
   manifest-present, idempotency, vendored-dir prune-during-descent, `@pytest.mark.skip`
   detection, skip rollup, escaped-pipe/mis-column/CRLF/idempotent spec write-back.
5. **Performance Basics** — pass: O(files) single repo walk; backfill/collector are
   subprocessed once each; triage append is idempotent (no re-flood on re-adopt).
6. **Naming & Structure** — pass: 4 cohesive modules ≤300 LOC (232/201/116 lib +
   210 tool), ruff-clean, no dead code, adopt-local placement; the repo-wide inventory was
   extracted to `traceability_skip_inventory.py` to hold the cap after the doubt fixes.
7. **Affected Boundaries (ADR-024)** — pass: the two changed serialized boundaries — the
   spec `Layers` cell (producer = `apply_layer_decisions_to_spec`, consumer = TT1
   `parse_requirements`) and the `@FR` tag (producer = TT6 backfill, consumer = TT1
   collector) — each has a REAL round-trip probe: a predeclared decision written to the
   cell is read back as `["e2e"]` in the Step F manifest, and a `@pytest.mark.covers` tag
   is read back as a `FR-01.01` unit coverage link. The TT6 report JSON boundary is
   consumed as structured JSON (never reparsed prose).

## Confidence Calibration (empirical probes)

- **Boundaries touched** (per ADR-024): (a) the adopt spec `Layers` cell ⇄ collector; (b)
  the `@FR` test tag ⇄ collector coverage link; (c) the TT6 `backfill-report.json` ⇄ adopt
  triage; (d) the tracked `triage.jsonl` ⇄ the persisted item.
- **Probes run (real, not asserted-confidence):** (1) round-trip: predeclared decision →
  spec cell → Step F manifest `required_layers == ["e2e"]`; (2) round-trip:
  `@pytest.mark.covers("FR-01.01")` → Step F manifest `FR-01.01.tests.unit` link; (3)
  dry-run mutates nothing on disk; (4) re-run idempotency (triage `appended == 0`, rules
  already present); (5) zero-test repo → manifest EXISTS + empty + advisory provenance; (6)
  vendored `node_modules` pruned from the skip inventory; (7) persisted `dedupKey` carries
  the orphan category.
- **Findings → fixes → re-probe:** the external code review found dry-run mutation (C2),
  silent backfill failure (C3), and a manifest-link gap (C6); the adversarial doubt review
  then found the two acute brownfield probes below. Each fixed; the re-run suite (a further
  probe) found no new defect → asymptote reached.
- **Doubt-review empirical probes (adopt's real target — large/Windows brownfield repos):**
  (8) a `node_modules/` subtree with a test file is NOT enumerated (os.walk prune, D1);
  (9) an escaped-pipe Description does not shift the decided layers into the Source column
  and the `\|` survives (D2); (10) a CRLF-authored spec is byte-preserved on write and a
  re-adopt writes 0 (D2 idempotency); (11) an un-escaped-pipe row is guarded (cell-count ≠
  header → left untouched); (12) `@pytest.mark.skip` is detected (D3); (13) >10 findings
  roll up to one card (D4); (14) `--dry-run` leaves `.shipwright/backfill/` absent (D5).
- **Edge cases not probed (acceptable):** an extreme repo where `os.walk` itself is slow
  on a non-pruned tree (the prune covers the known vendored dirs; an exotic vendored dir
  name is a config the operator can add); a spec.md with a genuinely malformed (unclosed)
  table (the cell-count guard leaves it untouched rather than guessing).
- **Edge cases not probed (acceptable):** a genuinely-mappable-but-untagged test that
  backfill AUTO-WRITES (requires the deterministic split/commit signal, which is advisory
  on a brownfield repo by design — the `honoured` existing-tag path is probed instead);
  auto-reconciliation of a skip removed on re-adopt (adopt is once-per-repo; the stable
  `dedup_key` prevents duplicates); a multi-split adopt (default single `01-adopted` split).
