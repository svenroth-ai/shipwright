# Iterate Spec: arch-doc-refresh-harden

- **Run ID:** iterate-2026-07-17-arch-doc-refresh-harden
- **Type:** change
- **Complexity:** medium (overridden from keyword `large`; force-continue, full rigor)
- **Status:** draft

## Goal
Refresh `.shipwright/agent_docs/architecture.md` to current state (portable
System-Overview mermaid; a Data-Flow section restructured into Plugins + GitHub
subsections) and **harden the "Architecture Updates" entry format so it stays
consistent by construction** — the release aggregator stops blind-appending a
duplicate `ADR-NNN` bullet, a new forward-only shape-gate enforces the canonical
run_id bullet grammar, and the active tail (≥ 2026-06-28) is normalized.

## Acceptance Criteria
- [ ] **AC1 (mermaid portability):** the System-Overview block parses under
  Mermaid v11 AND contains no `&nbsp;` entity, no glued `subgraph id["…"]`
  header, and no subgraph-internal `direction`; it includes a GitHub node.
- [ ] **AC2 (Data Flow structure):** `## Data Flow` contains exactly the two
  subsections `### Plugins` and `### GitHub`; every fact is current (14 plugins,
  `single_session` sole mode, the 6 real workflow files, no `scorecard.yml`); the
  8 live component/data-flow run_id tokens remain present in `architecture.md`.
- [ ] **AC3 (kill the iterate dup — surgically):** the `aggregate_decisions`
  fold path no longer appends a second `ADR-NNN` bullet for a drop whose run_id
  is already documented in the target section (the iterate flow's F2 bullet is
  guaranteed present by F11's `check_architecture_documented`). The **direct**
  path (`write_decision_log.append_decision`, used by build/plan/project/test/
  deploy) is UNTOUCHED — it is the sole, non-dup appender for those phases. Unit
  test: a folded iterate drop yields the `decision_log.md` ADR + `Run-ID:` line
  but adds **zero** new lines to the two curated append docs; `append_decision`
  still appends exactly one bullet.
- [ ] **AC3b (canonicalize the machine bullet):** `_append_architecture_update`
  emits the full canonical form `- **ADR-NNN** (date): <Impact> — <summary>. →
  decision_log (ADR-NNN)` (was `- **ADR-NNN** (date): <summary>` — no Impact, no
  arrow), so direct-path bullets in adopted repos pass the shape-gate. Update
  `test_arch_update_writer_format.py` (Test-Update-Klausel).
- [ ] **AC4 (shape-gate):** a new SSoT lib (reusing `agent_doc_budget`'s
  `iter_entries`/`entry_anchor`/`entry_date`) enforces, for **dated** bullets
  with date ≥ `enforced_from = 2026-06-28` in the **two** `…Updates` sections
  (Architecture Updates + Convention Updates — **NOT `## Learnings`**, which is a
  date-first non-anchored grammar): a well-formed canonical bullet — anchor is a
  bold `**<run_id>**` OR `**ADR-NNN**` (Campaign/sub_iterate/free-text REJECTED),
  a `(YYYY-MM-DD)` date, and a `→` pointer. Undated / pre-cutoff grandfathered.
  Forward-only variant for F11 + CI; full-corpus variant for the monorepo pytest.
  Wired into `run_all_checks` + a membership drift-guard test; repo-agnostic;
  UTF-8-safe stdout (Windows cp1252).
- [ ] **AC5 (normalize active tail — both docs):** ≥ 2026-06-28,
  `architecture.md ## Architecture Updates` loses its **31** redundant `ADR-NNN`
  dup lines (run_id twin kept) and **converts** the 1 orphan `ADR-327` →
  `iterate-2026-07-15-execution-evidence` form; `conventions.md ## Convention
  Updates` loses its **21** dup `ADR-NNN` lines (all have twins). Deep-historical
  `→ archive` / pre-cutoff lines untouched; the new gate is GREEN full-corpus on
  BOTH docs; every dated bullet ≤ 600 chars; all 8 live tokens preserved.
- [ ] **AC6 (docs/spec of record):** `references/F2.md`, the `architecture.md`
  + `conventions.md` inline headers, and `docs/hooks-and-pipeline.md` state the
  single-well-formed-bullet-per-change rule (iterate → run_id, no ADR dup;
  direct → ADR-NNN) and register the new gate. F2's 4 routing substrings kept.

## Spec Impact
- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** No user-visible FR changes. This is framework
  tooling + documentation: a curated agent-doc refresh, a release-aggregator
  behavior fix, and a new internal doc-hygiene lint gate. Finalize `change_type`
  = `tooling` (passes the ADR-059 FR-or-change-type gate without an FR link).

## Out of Scope
- No backfill/normalization of deep-historical (< 2026-06-28) bare `ADR-NNN`,
  `Campaign …`, or `sub_iterate-…` lines — grandfathered.
- No change to `aggregate_decisions.py`'s ADR numbering, `decision_log.md` body,
  the `Run-ID:` linkage, or the drop-`unlink` compaction contract.
- No change to the ≤600-char budget gate or the drift/F5/F11 presence checks
  (the new gate is additive, orthogonal).
- No WebUI changes (the WebUI consumes triage/grade contracts, not this doc).

## Design Notes
n/a (no UI).

## Affected Boundaries
The new shape-gate is a consumer of the curated agent-doc markdown (a
producer→file→consumer round-trip over `architecture.md` / `conventions.md`).

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| iterate F2 (agent) + `write_decision_log._append_architecture_update` | `lib.agent_doc_shape` (new gate), `lib.agent_doc_budget` | curated markdown bullets |
| `aggregate_decisions.aggregate` | `decision_log.md` (ADR + `Run-ID:` line) | markdown ADR entries |

## Confidence Calibration
- **Boundaries touched:** the curated agent-doc bullet format (architecture.md /
  conventions.md append sections) + the release-aggregator's doc-append path.
- **Empirical probes run:** (filled before F0)
  - Mermaid: `mermaid.parse()` v11 on original (PASS — not a syntax error) and on
    the portable rewrite (PASS); confirms breakage is renderer-fragility, fixed.
  - Aggregator: fixture drop → assert decision_log gains the ADR + `Run-ID:` line
    and the two curated append docs gain 0 lines.
  - Shape-gate: canonical bullet PASS, each malformation (bad anchor, missing
    date/arrow/Impact, ADR-NNN dup) FAIL; pre-cutoff/undated grandfathered.
  - Whole-file: run the gate on the normalized architecture.md → GREEN; grep the
    8 live run_id tokens still present.
- **Test Completeness Ledger:** (see table; mirrored to F5)

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Portable mermaid parses + no fragile constructs | tested | shape/parse test |
  | 2 | Data Flow = Plugins + GitHub, 8 tokens preserved | tested | meta-test grep |
  | 3 | Aggregator adds 0 lines to curated append docs | tested | aggregator unit test |
  | 4 | Aggregator still writes ADR + Run-ID to decision_log | tested | aggregator unit test |
  | 5 | Shape-gate FAILs each non-canonical dated bullet | tested | gate unit tests |
  | 6 | Shape-gate PASSes canonical + grandfathers pre-cutoff/undated | tested | gate unit tests |
  | 7 | Gate wired into F11 run_all_checks (both-direction registry) | tested | verifier registry meta-test |
  | 8 | Whole normalized architecture.md GREEN on gate + budget | tested | full-corpus test |
  | 9 | Gate composes into F11 finalization (integration) | tested | integration test (if cross_component) |
  | 10 | Renders visually correct in the user's viewer | untestable | requires-manual-visual-judgment |

- **Confidence-pattern check:** depth — the mermaid "is it valid?" question
  already produced a surprising finding (parses fine → not syntax → renderer), so
  a second probe (the portable rewrite parse) was run. Breadth — every row is
  `tested` except the one honest `requires-manual-visual-judgment`.

## Verification (medium+)
- **Surface:** none
- **Runner command:** n/a (framework tooling + docs; no startable web/cli/api app)
- **Evidence path:** `shipwright_test_results.json` (full pytest suite: new gate +
  aggregator unit tests + drift/budget meta-tests + integration test)
- **Justification (surface=none):** This monorepo is a Claude-Code plugin
  library. The change touches curated docs + Python release-tooling + a new lint
  gate — there is no runtime user surface to drive; empirical verification is the
  pytest suite exercising the producer→file→consumer round-trip end-to-end.
