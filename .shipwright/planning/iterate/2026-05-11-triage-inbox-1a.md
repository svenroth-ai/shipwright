# Iterate Spec: triage-inbox-1a

- **Run ID:** iterate-2026-05-11-triage-inbox-1a
- **Type:** feature
- **Complexity:** medium
- **Status:** draft

## Goal

Add the foundation of the Triage Inbox pattern: a pre-backlog intake store
for findings from hooks/scans/audits. Triage and Backlog are kept as
separate stores; promote is the explicit bridge. Iterate 1a delivers the
storage layer, aggregator, two producers (PhaseQuality + Compliance), an
adopt-time scaffolding step, a manual promote CLI for non-webui repos,
plus the supporting tests + docs.

The shape MUST be mappable to the leadwright ExternalTask extension
(camelCase wire format, severity→priority + source→domain mapping) so
Iterate 1b (webui side) and Iterate 3 (Triage tab in webui) can land
without renames.

## Acceptance Criteria

- [ ] **AC-1 — Storage API**: `shared/scripts/triage.py` (see Deviation
  Note #1 below — placed at `shared/scripts/triage.py`, NOT
  `shared/scripts/lib/triage.py`) exposes:
  - `append_triage_item(project_root, *, source, severity, kind, title,
    detail, evidence_path=None, run_id=None, commit=None) -> str` (returns
    `id` of form `trg-<8hex>`).
  - `read_all_items(project_root) -> list[dict]` — collapses history
    (last-status-wins per id), returns the resolved view.
  - `mark_status(project_root, item_id, *, new_status, by, reason=None,
    promoted_task_id=None) -> None` — appends a history event line, never
    mutates prior lines. Idempotent: re-appending the same status+reason
    is a no-op on the resolved view.
  - `suggest_priority_from_severity(severity) -> str` — pure: critical→P0,
    high→P1, medium→P2, low→P3, info→P3.
  - `suggest_domain_from_source(source) -> str` — pure: `compliance`→
    `compliance`, anything else (`phaseQuality`, `security`, `performance`,
    `ci`, `iterate`)→`engineering`.
  - File-lock on JSONL append (mirror of `record_event.py`'s cross-platform
    `_FileLock`). Lock-file path: `.shipwright/triage.jsonl.lock`.
  - ISO-8601 timestamps with `Z` suffix (UTC), generated via
    `datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")`.

- [ ] **AC-2 — Aggregator**: `shared/scripts/tools/aggregate_triage.py`
  reads `.shipwright/triage.jsonl`, collapses history per `id`
  (last-status-wins), filters to `status == "triage"`, renders
  `.shipwright/agent_docs/triage_inbox.md` with:
  - Header line with counts (`total / triage / promoted / dismissed /
    snoozed`).
  - Top-50 items sorted by severity (critical → info) then ts (newest
    first).
  - Grouped by source (subheading per source).
  - Per-item line: suggested promote-action with `id`, `severity`, `kind`,
    `title`, `suggestedPriority`, `suggestedDomain`.
  - Argparse: `--project-root .` (default `.`).

- [ ] **AC-3 — Stop-Hook**: `shared/scripts/hooks/aggregate_triage_on_stop.py`
  invokes the aggregator at iterate-finalize Stop, registered in
  `plugins/shipwright-iterate/hooks/hooks.json` under the existing Stop
  hooks block. Schema-compliant stdout per ADR-042 (no
  `additionalContext` on Stop; diagnostics → stderr).

- [ ] **AC-4 — Phase-Quality Producer**: modify
  `shared/scripts/hooks/audit_phase_quality_on_stop.py` so every Tier-1
  FAIL (codes C1, C5, W3 per phase_quality.py — see Note #3) is appended
  as a triage item with `source="phaseQuality"`. Dedup: skip when an item
  with the same `source + detail + commit` already exists and was
  appended within the last 24h (best-effort dedup window).

- [ ] **AC-5 — Compliance-Audit Producer**: modify
  `plugins/shipwright-compliance/scripts/audit/audit_detector.py` so
  every `Finding` added to `AuditReport.findings` is appended with
  `source="compliance"`. Findings present in the previous run but
  absent in the current one are auto-dismissed via
  `mark_status(new_status="dismissed", reason="auditResolved",
  by="auditDetector")`.

- [ ] **AC-6 — Adopt Scaffolding**: at initial-adopt time only (not for
  re-runs of /shipwright-adopt on existing projects in this iterate):
  - Write `.shipwright/triage.jsonl` with header line
    `{"v":1,"schema":"triage","created":"<ISO>"}`.
  - Append `.shipwright/triage.jsonl` to project `.gitignore`.
  - Write empty-skeleton `.shipwright/agent_docs/triage_inbox.md`.
  - Add Step E.16 ("Triage Inbox Scaffold") to
    `plugins/shipwright-adopt/skills/adopt/SKILL.md` describing the
    above + linking to `docs/triage-inbox.md`.

- [ ] **AC-7 — Promote CLI**:
  `shared/scripts/tools/triage_promote.py --id trg-xxx --task-ref EXT:...`
  calls `mark_status(new_status="promoted", reason="manualPromote",
  promoted_task_id="EXT:...")`. Error if `id` doesn't exist or status is
  already `promoted`. Argparse: `--project-root .` (default `.`),
  `--id` (required), `--task-ref` (required).

- [ ] **AC-8 — Drift Tests**:
  - `shared/tests/test_triage_schema.py`: fixture-parametrized JSONL
    validator (required fields, enum values, camelCase keys).
  - `shared/tests/test_triage_storage.py`: append+read round-trip
    (Boundary Probe — see "Affected Boundaries" below), file-lock
    contention test (two concurrent appends), idempotent mark_status,
    no-mutate-prior-lines invariant.
  - `shared/tests/test_triage_aggregator.py`: status resolution
    (`promoted`/`dismissed` removed from rendered list), markdown
    snapshot, severity-sort ordering.
  - `shared/tests/test_triage_mapping.py`: parametrized matrix for
    `suggest_priority_from_severity` (5 cases) and
    `suggest_domain_from_source` (6+ cases including `unknown`).

- [ ] **AC-9 — Docs**:
  - `docs/triage-inbox.md`: 1-pager on pattern, promote flow,
    webui-vs-non-webui paths, mapping rules.
  - `docs/guide.md` Chapter 4: short reference link.
  - `docs/hooks-and-pipeline.md`: register
    `aggregate_triage_on_stop` Stop-hook with read/write matrix entry.

## Affected FRs

This is the self-monorepo (Shipwright framework itself); FRs are tracked
as `_iterate_migration_state: complete`. The repo's `spec.md` files
under `.shipwright/planning/` document the framework's own functional
requirements. Triage Inbox is a NEW capability — no existing FR covers it.

**Adopt scaffolding** (AC-6) extends an existing FR area
(adopt-scaffolds-runtime-files). The other ACs are new capability
additions documented via the iterate spec + ADR rather than via new FRs
in `spec.md` (matches the convention for cross-cutting plumbing — see
recent iterates `iterate-2026-05-10-adopt-ci-scaffolders`).

## Out of Scope

Explicit, NOT in this iterate:
- Security/CI/Performance/F0.5/Drift Producer wiring → Iterate 2.
- Leadwright Phase-1 ExternalTask-Extension → Iterate 1b (parallel,
  separate, in shipwright-webui repo).
- WebUI Triage-Tab + Promote-Button → Iterate 3 (needs 1a + 1b).
- `backlog.md` aggregate in adopted repo (only `triage_inbox.md` here).
- Migration of existing `known_issues.md` entries (no auto-import).
- Re-running `/shipwright-adopt` on the shipwright monorepo itself to
  populate the new scaffolding artifacts. AC-6 ships the *template*;
  the user/operator runs adopt when they want it applied.
- Fixing the existing C1/C5/W3 Phase-Quality FAILs from prior phases —
  AC-4 will START spiegeln those into triage.jsonl from this commit
  forward, but doesn't fix them.

## Deviations from Pre-Spec (flagged)

1. **Path: `shared/scripts/triage.py` (not `shared/scripts/lib/triage.py`).**
   ADR-045 (2026-05-11): cross-plugin importable helpers MUST live outside
   the `lib/` namespace because `shared/scripts/lib/` is a regular package
   (has `__init__.py`) while every `plugins/*/scripts/lib/` is a namespace
   package — pytest sessions importing across both collide on
   `sys.modules['lib']`. AC-5 imports `triage` from
   `plugins/shipwright-compliance/scripts/audit/audit_detector.py`, so
   the cross-plugin import is real. Following ADR-045: `shared/scripts/
   triage.py` imported as `from triage import ...` from any consumer
   that sets `sys.path` to include `shared/scripts/`.

2. **camelCase scope: wire format only.** User spec says "camelCase
   durchgehend" — interpreted as the JSON wire format (matches webui's
   ExternalTask + leadwright libs). Python identifiers (function names,
   keyword args, internal vars) follow PEP 8 (snake_case). Boundary
   adapter: `append_triage_item(*, evidence_path=None, run_id=None)`
   writes `{"evidencePath": ..., "runId": ...}` to JSONL.
   `read_all_items()` returns the camelCase-keyed dicts unchanged so
   downstream consumers (aggregator, promote CLI, webui-imports) see the
   wire form directly.

## Affected Boundaries

The triage feature defines a new producer/consumer pair on a serialized
format (`touches_io_boundary` fires). Round-Trip test mandatory.

| Producer (writes)                                | Consumer (reads)                                | Format |
|---|---|---|
| `shared/scripts/triage.py:append_triage_item`    | `shared/scripts/triage.py:read_all_items`       | JSONL (camelCase keys, `Z`-suffixed ISO ts) |
| `shared/scripts/triage.py:mark_status`           | `shared/scripts/triage.py:read_all_items`       | JSONL (history event) |
| `shared/scripts/hooks/audit_phase_quality_on_stop.py` (via API) | `shared/scripts/tools/aggregate_triage.py:main` | JSONL (file path: `.shipwright/triage.jsonl`) |
| `plugins/shipwright-compliance/scripts/audit/audit_detector.py` (via API) | `shared/scripts/tools/aggregate_triage.py:main` | JSONL |
| `shared/scripts/tools/triage_promote.py` (via API) | `read_all_items` (status filter) | JSONL (history event) |
| `shared/scripts/tools/aggregate_triage.py:main`  | (human reader; markdown viewer)                 | Markdown (`triage_inbox.md`) |

**Probes mandated** (per `references/boundary-probes.md`):
1. Round-trip: producer→file-on-disk→consumer reading and re-asserting
   every field (AC-8 `test_triage_storage.py`).
2. Empty-file probe: aggregator reads file with only schema-header line
   → produces empty markdown skeleton (no crash) (AC-8 `test_triage_aggregator.py`).
3. Mixed-status probe: items with various statuses → only `triage` shown.
4. Corrupt-line probe: malformed JSON line → reader skips with warning,
   doesn't poison subsequent reads (mirrors `read_events`' tolerance).
5. Concurrent-write probe: two producers append in parallel → both
   visible, no lost writes (file-lock test).
6. Lockfile-stale probe: stale `.lock` file from killed process → next
   writer recovers gracefully (mirrors `record_event.py` pattern).
7. Status-history-ordering probe: id with status sequence
   `triage→snoozed→promoted` resolves to `promoted`, not the most
   recent in chronological order (validates last-status-wins).
8. Unicode/path-with-spaces probe: project path with spaces (OneDrive
   case — `AI Backup - Documents`) — append + read works.

Machine-only-format opt-outs (justified): POSIX `export` prefix, inline
`#` comment, quoted `#` — n/a for JSONL (machine-only).

## Confidence Calibration

Mandatory at medium (per Phase Matrix). Run before F0.

- **Boundaries touched:** see "Affected Boundaries" table above (6 pairs
  across JSONL + Markdown).
- **Empirical probes run:** populate at Self-Review (Step 7.5). The 8
  probes above are the floor; format-specific probes added as needed.
- **Edge cases NOT probed + why acceptable:** operator-input probes
  (POSIX `export`, inline `# comment`, quoted `#`) skipped — JSONL is
  machine-only.
- **Confidence-pattern check:** populate at Self-Review.

## Verification (medium+ — F0.5)

- **Surface:** `cli` — this iterate ships no UI. The behavior surface
  is the CLI + library API.
- **Runner command:**
  ```
  uv run --directory .worktrees/triage-inbox-1a pytest shared/tests/test_triage_*.py -v
  uv run --directory .worktrees/triage-inbox-1a pytest plugins/shipwright-iterate/tests/ -v
  uv run --directory .worktrees/triage-inbox-1a pytest plugins/shipwright-compliance/tests/ -v
  ```
  Plus the end-to-end smoke:
  ```
  # 1. fixture project + manual scenario
  python -c "from triage import append_triage_item; \
             append_triage_item('<tmp>', source='manual', severity='high', \
                                kind='bug', title='probe', detail='F0.5 smoke')"
  uv run --directory .worktrees/triage-inbox-1a shared/scripts/tools/aggregate_triage.py --project-root <tmp>
  # assert .shipwright/agent_docs/triage_inbox.md exists and lists the probe item
  ```
- **Evidence path:** pytest output captured to
  `.shipwright/runs/iterate-2026-05-11-triage-inbox-1a/surface_verification.json`
  via `shared/scripts/surface_verification.py --surface cli`.

## Design Notes

n/a — no UI in this iterate. The Triage tab in webui is Iterate 3.

## Notes / Locked Decisions (incl. External Review responses)

External LLM review run 2026-05-11 (OpenRouter / Gemini + OpenAI).
Raw output: `iterate-2026-05-11-triage-inbox-1a-external-review.json`.
3 HIGH + 11 MED/LOW findings. Decisions below are the locked responses;
each is referenced by the issue number from the review JSON.

### Storage API contract

- **File-existence bootstrap** (HIGH-3): `append_triage_item` auto-creates
  `.shipwright/triage.jsonl` with the schema header line on first write
  (so producers are robust on adopt-not-yet-run repos). `mark_status`
  fails clear (`FileNotFoundError`) when the file is missing (can't
  change status of items that don't exist). `read_all_items` returns
  `[]` for missing file. The aggregator writes an empty skeleton
  `triage_inbox.md` when the JSONL is missing or has only the header.
- **Cross-context import bootstrap** (HIGH-1): every consumer (compliance
  audit_detector.py, hook scripts, CLIs, tests) does at top of file:
  ```python
  import sys
  from pathlib import Path
  _SHARED_SCRIPTS = Path(__file__).resolve().parents[N] / "shared" / "scripts"
  if str(_SHARED_SCRIPTS) not in sys.path:
      sys.path.insert(0, str(_SHARED_SCRIPTS))
  from triage import append_triage_item, ...
  ```
  N chosen per file depth. This is the same pattern existing tools use
  (`record_event.py`, `aggregate_changelog.py`). Documented in
  `docs/triage-inbox.md` consumer section.
- **Last-status-wins resolution** (MED-6): strictly **file-order**, not
  timestamp. The reader iterates lines in physical order; later valid
  lines win over earlier ones for the same `id`. This is deterministic
  even under clock skew (Windows TZ jumps, OneDrive sync clock).
- **Tolerant reader** (Gemini MED-1): `read_all_items` skips lines that
  fail `json.JSONDecodeError` and logs to stderr — mirrors
  `record_event.py:read_events` exactly.
- **Constants in `triage.py`** (MED-5): single source of truth for
  status enum, severity enum, kind enum, source list, severity→priority
  table, source→domain table, schema version. Tests assert against the
  imported constants, not duplicated literals.

### AC-4 Phase-Quality producer

- **Dedup key** (MED-4): `(source, finding_code, commit)` — NOT
  `(source, detail, commit)`. The Phase-Quality code (`C1`/`C5`/`W3`/...
  from `phase_quality.py:Tier1Codes`) is the stable identity; `detail`
  is descriptive text that varies. Window: items appended within last
  24h with the same triple → skip the new append.
- **Commit on dirty tree** (Gemini LOW-3): use `git rev-parse HEAD`
  (returns last-commit hash even on dirty tree). Never `None`. If git
  unavailable, fall back to empty string + log warning.

### AC-5 Compliance producer

- **Auto-dismiss correlation key** (HIGH-2): the key is
  `(source="compliance", finding_code)` where `finding_code` is the
  finding's unique identifier from `audit_detector.Finding`. Auto-dismiss
  applies only to currently-`triage` items matching that key — items
  previously promoted or dismissed stay in their terminal state.
- **Branch-switch race** (Gemini MED-2): explicitly accept the
  consequence. The triage JSONL is gitignored local store. Switching
  to a branch without a compliance finding will auto-dismiss it; back
  on the original branch the next audit will re-detect and re-append
  (new `id`, history shows the dismiss/re-add chain). Documented as
  expected behavior in `docs/triage-inbox.md`. Operators with strict
  audit-trail needs are expected to promote findings before branch
  switching. Out of scope for 1a: branch-aware dismiss.

### AC-2 Aggregator

- **Hook ordering** (MED-8): `aggregate_triage_on_stop` is registered
  as the LAST Stop-hook in `plugins/shipwright-iterate/hooks/hooks.json`
  Stop array, after `iterate_stop_finalize`, `audit_phase_quality_on_stop`,
  `write_terminal_marker`. Claude Code runs Stop hooks in array order;
  aggregator must observe the producers' writes.
- **Sort field** (MED-9): top-50 sort is `(severity_rank, original_append_ts
  DESC)`. `original_append_ts` is the timestamp of the **first** event
  for that id (the original append, not the latest status event). Stable
  ordering across status flips. Tracked on the resolved record as
  `originalTs` (separate from `ts` which is the latest event).
- **Markdown escaping** (MED-10, Gemini LOW-5): aggregator escapes
  Markdown-active characters in `title`, `detail`, `evidencePath`, `kind`
  before rendering. Escape table: `|` → `\|`, leading `#` → `\#`,
  triple-backtick stripped (collapse to one). Long fields (>120 chars)
  get truncated with `…` suffix.

### AC-6 Scaffolder

- **Idempotent `.gitignore`** (LOW-14, Gemini LOW-4): scaffolder reads
  existing `.gitignore`, checks for presence of `.shipwright/triage.jsonl`
  AND `.shipwright/triage.jsonl.lock`; appends only the missing ones.
  Creates `.gitignore` if absent. Test covers all 4 combinations.
- **Adopt wiring** (LOW-15): SKILL.md Step E.16 is the canonical wiring
  — adopt skill is markdown-driven (the agent runs the steps inline).
  The scaffolder helper (`scaffold_triage_inbox.py`) is the testable
  unit invoked by Step E.16. No additional Python-orchestration glue
  needed.

### AC-7 Promote CLI

- **Allowed source state** (LOW-12): only `triage` → `promoted`. Promoting
  from `dismissed`/`snoozed` rejected with exit-code 2 (transitions
  require explicit operator intervention out of scope for 1a).
- **task-ref sanitization** (MED-12): CLI rejects `--task-ref` containing
  newline, tab, or ASCII control characters. Length cap 200 chars.

### AC-8 Tests

- **Cross-process contention** (MED-7): in addition to ThreadPoolExecutor
  test, add subprocess-based contention test that spawns two `python -c
  "import triage; triage.append_triage_item(...)"` processes in parallel
  via `subprocess.Popen`. Asserts both writes visible, no lost lines.
- **Boundary probes** also include status-resolution-under-corrupt-lines
  (Probe 4 + 7 combined): one corrupt line between two valid status
  events for the same id → resolved status is the later valid one,
  corrupt line skipped.

### Out-of-scope (deferred)

- **Compaction strategy** (Gemini MED-3): note in `docs/triage-inbox.md`
  that the JSONL grows monotonically; manual prune via
  `triage_promote.py --reset-history` or a future compaction tool.
  Not implemented in 1a.
- **Branch-aware dismiss / reopen-from-terminal** (Gemini MED-2 cont):
  out of scope. Operators promote-before-switch.
- **Read-lock during `read_all_items`** (Gemini MED-1): tolerant reader
  (skip JSONDecodeError) is sufficient for 1a. A proper shared-read-lock
  is out of scope; the partial-line case is handled by file-order +
  skip-on-error semantics.

## External Review

- **Run:** 2026-05-11, provider=openrouter, gemini + openai both succeeded.
- **Raw output:**
  `.shipwright/planning/iterate/iterate-2026-05-11-triage-inbox-1a-external-review.json`
- **State marker:** `external_review_state.json` (Branch A — addressed).
- **Decisions:** see "Locked Decisions" section above; every HIGH +
  MED finding addressed inline or explicitly deferred with rationale.
