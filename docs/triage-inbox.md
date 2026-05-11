# Triage Inbox Pattern

## What it is

The **triage inbox** is a per-project, append-only intake store for
findings emitted by Shipwright hooks, scans, and audits. It is the
pre-backlog buffer between "something noticed a problem" and "we have
decided to act on it."

Triage and the backlog are **separate stores by design**:

| Store | Where | What | Lifecycle |
|---|---|---|---|
| **Triage** | `.shipwright/triage.jsonl` (per adopted repo, gitignored) | Hook/scan/audit findings; raw producer output | append-only, history-event JSONL |
| **Backlog** | `sdk-sessions.json` (in [shipwright-webui](https://github.com/svenroth-ai/shipwright-webui)) | ExternalTask records for daemons/operators to claim | object-store with full lifecycle (`awaiting_external_start` → `active` → `done`) |

A finding in triage is not yet a task. The **promote** action is the
explicit bridge that turns a triage item into a backlog ExternalTask.

## Why split them

- **Noise floor.** Hooks emit on every Stop. The same Phase-Quality
  `C1` FAIL re-fires every session until it's fixed; the same
  Compliance audit finding persists across runs. Routing those raw
  signals straight into the backlog floods the operator's view. The
  triage inbox absorbs the noise; the backlog stays a curated list.
- **Dedup separation.** Triage owns dedup-by-finding-code (so the
  inbox doesn't have N copies of the same issue across sessions). The
  backlog (ExternalTask) is keyed by task id — duplicate tasks would
  be wrong there. Different keys, different stores.
- **Promote semantics are explicit.** The operator decides what's
  worth pulling onto the backlog. The triage inbox documents what was
  seen; the backlog documents what's being acted on. Auditors care
  about both.

## On-disk shape

`.shipwright/triage.jsonl` is a JSONL file with one header line plus an
event-sourced history.

```
{"v":1,"schema":"triage","created":"2026-05-11T13:45:00Z"}
{"event":"append","id":"trg-a1b2c3d4","ts":"2026-05-11T13:45:00Z","originalTs":"2026-05-11T13:45:00Z","source":"phaseQuality","severity":"high","kind":"bug","title":"iterate C1: phase_completed event missing","detail":"...","evidencePath":".shipwright/compliance/skill-compliance/...","runId":"iterate-2026-05-11-...","commit":"abcdef0","dedupKey":"iterate:C1","status":"triage","suggestedPriority":"P1","suggestedDomain":"engineering"}
{"event":"status","id":"trg-a1b2c3d4","ts":"2026-05-11T14:00:00Z","newStatus":"promoted","by":"manualPromote","reason":"...","promotedTaskId":"EXT:linear-ENG-7"}
```

Keys are **camelCase** because the wire format is shared with the
[shipwright-webui](https://github.com/svenroth-ai/shipwright-webui)
`ExternalTask` schema (and the `leadwright` daemon's task-extension —
see `leadwright/docs/specs/phase-1-external-task-extension.md`).

Status resolution is **last-status-wins by file order** (not
timestamp). The reader is tolerant: lines that fail `JSONDecodeError`
are skipped with a stderr warning, never crash the read.

## Status enum

```
triage     — new finding, awaiting decision
promoted   — turned into an ExternalTask via triage_promote (or webui)
dismissed  — operator/auditor decided not actionable
snoozed    — defer; reserved for future surfacing
```

The enum is intentionally simpler than `ExternalTask.state` (which has
`awaiting_external_start` / `active` / `done`). Triage doesn't track
execution — that's the backlog's job after promote.

## Producers (Iterate 1a)

| Producer | Trigger | Source | What it appends |
|---|---|---|---|
| `shared/scripts/hooks/audit_phase_quality_on_stop.py` | Stop hook, every session | `phaseQuality` | Tier-1 FAILs (C1/C5/W3/…), dedup by `(phase, code, commit)` within 24h |
| `plugins/shipwright-compliance/scripts/audit/audit_detector.py::mirror_findings_to_triage` | `run_all(emit_to_triage=True)` (default) | `compliance` | Every `Finding.status == "fail"`, dedup by `check_id` cross-commit. Findings absent from the current run → auto-dismissed with `reason="auditResolved"` |

Out-of-scope for Iterate 1a (deferred): Security/CI/Performance/F0.5/Drift
producers — see Iterate 2.

## Consumer (Iterate 1a)

The Stop hook `shared/scripts/hooks/aggregate_triage_on_stop.py` runs
**last** in the iterate plugin's Stop chain (after the producers) and
regenerates `.shipwright/agent_docs/triage_inbox.md` via
`shared/scripts/tools/aggregate_triage.py`. The markdown is the
human-facing view: status summary, top 50 items sorted by
`(severity, originalTs DESC)`, grouped by source, with per-item
promote-action hints.

You can also regenerate manually:

```bash
uv run shared/scripts/tools/aggregate_triage.py --project-root .
```

## Promote (the bridge to the backlog)

### From the WebUI (Iterate 3, future)

The shipwright-webui Triage tab will show pending items and offer a
one-click promote that opens a `Create Task` modal pre-filled with
`suggestedPriority` / `suggestedDomain` / origin tags. The webui will
also set `promotedFromTriageId` on the resulting ExternalTask so the
audit trail closes.

Tracked in `leadwright/docs/specs/phase-1-external-task-extension.md`
(Iterate 1b in webui) and Iterate 3 in this monorepo.

### From the CLI (Iterate 1a, available now)

For non-webui repos or operators who prefer the CLI:

```bash
uv run shared/scripts/tools/triage_promote.py \
  --id trg-a1b2c3d4 \
  --task-ref "EXT:linear-ENG-7" \
  [--reason "urgent — Q2 release"]
```

Exit codes:

- `0` — promoted; triage_inbox.md will re-render on next Stop hook
- `2` — invalid input (state already-promoted/dismissed/snoozed, or
  `task-ref` contains control chars / is too long)
- `3` — triage id not found
- `4` — triage store not initialised (run `/shipwright-adopt` or the
  scaffolder first)

`--task-ref` is sanitized: no newlines, tabs, or ASCII control
characters; max 200 chars. Free-form otherwise — `EXT:linear-ENG-7`,
`EXT:asana-12345`, `https://my-tracker/issues/42` — downstream consumers
expect a human-readable token. (When the webui Triage tab lands in
Iterate 3, it writes the actual `ExternalTask` record and sets
`promotedTaskId` on the triage side automatically.)

## Mapping rules (severity → priority, source → domain)

These mappings are mechanical and recorded in every triage item as
`suggestedPriority` and `suggestedDomain` so promote-time tooling
doesn't have to recompute them:

| Severity | suggestedPriority |
|---|---|
| critical | P0 |
| high | P1 |
| medium | P2 |
| low | P3 |
| info | P3 |

| Source | suggestedDomain |
|---|---|
| `compliance` | `compliance` |
| (anything else) | `engineering` |

The full table is in `shared/scripts/triage.py` (`PRIORITY_FROM_SEVERITY`,
`DOMAIN_FROM_SOURCE`) and exported as the SSoT — tests assert against
the imports, not duplicated literals.

The mapping matches `leadwright`'s expectation: severity `critical → P0`,
`info → P3-or-skip`, source `security/performance/ci/phaseQuality/iterate
→ engineering`, source `compliance → compliance`.

## Storage API

`shared/scripts/triage.py` (note: outside `shared/scripts/lib/` per
[ADR-045](../.shipwright/agent_docs/decision_log.md) — cross-plugin
imports collide on `sys.modules['lib']`).

```python
from triage import (
    append_triage_item,            # raw append, returns trg-<8hex>
    append_triage_item_idempotent, # dedup'd; returns id or None
    mark_status,                   # appends status event; idempotent
    read_all_items,                # collapsed view (last-status-wins)
    suggest_priority_from_severity,
    suggest_domain_from_source,
)
```

Locking mirrors `shared/scripts/tools/record_event.py:_FileLock` —
cross-platform via `msvcrt.locking` on Windows and `fcntl.flock` on
POSIX, with a dedicated `.lock` sidecar file. Both in-process and
cross-process contention are covered (see
`shared/tests/test_triage_storage.py`).

## Operating expectations

- **The triage file grows monotonically.** No compaction is done in
  Iterate 1a. For long-running projects, expect the JSONL to reach
  thousands of lines over months. The aggregator caps rendered output
  at 50; the underlying read is still O(N). Compaction strategy is
  tracked as future work (Gemini MED-3 from external review).
- **Branch switching is a known edge.** `.shipwright/triage.jsonl` is
  gitignored and local. Switching to a branch without a compliance
  finding auto-dismisses the corresponding triage item; switching back
  re-detects the finding and appends a NEW id (the previous id stays
  dismissed). Operators who want the audit trail tight should promote
  findings BEFORE switching branches.
- **Producer order matters** for what the aggregator sees in a single
  Stop chain. The iterate plugin's `hooks.json` registers producers
  first (`audit_phase_quality_on_stop`, `iterate_stop_finalize`) and
  the aggregator last (`aggregate_triage_on_stop`) — see
  [hooks-and-pipeline.md](hooks-and-pipeline.md).
- **No backwards-compatibility hacks for legacy known_issues.md.**
  The two files coexist: `.shipwright/agent_docs/known_issues.md`
  scans source files for TODO/FIXME markers at adopt time and stays
  static thereafter; `.shipwright/agent_docs/triage_inbox.md`
  regenerates from hook events every Stop. There is no migration of
  one into the other.

## References

- Spec: `.shipwright/planning/iterate/2026-05-11-triage-inbox-1a.md`
- ADR: see decision log for ADR-046 (Triage Inbox Pattern, Iterate 1a). The sibling ADR-045 landed first and covers the `lib/` namespace rule that motivates placing `triage.py` outside `shared/scripts/lib/`.
- Leadwright ExternalTask extension:
  `leadwright/docs/specs/phase-1-external-task-extension.md`
- ADR-045: cross-plugin import constraint behind the
  `shared/scripts/triage.py` (not `lib/`) placement
- ADR-042: Stop hook schema (NO `additionalContext`; aggregator
  diagnostics go to stderr)
- ADR-024: producer/consumer round-trip discipline (boundary probes
  in `test_triage_storage.py`)
