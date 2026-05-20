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

## Producers (Iterate 1a + Iterate 2)

| Producer | Trigger | Source | What it appends |
|---|---|---|---|
| `shared/scripts/hooks/audit_phase_quality_on_stop.py` | Stop hook, every session | `phaseQuality` | Tier-1 FAILs (C1/C5/W3/…), dedup by `(phase, code, commit)` within 24h |
| `plugins/shipwright-compliance/scripts/audit/audit_detector.py::mirror_findings_to_triage` | `run_all(emit_to_triage=True)` (default) | `compliance` | Every `Finding.status == "fail"`, dedup by `check_id` cross-commit. Findings absent from the current run → auto-dismissed with `reason="auditResolved"` |
| `plugins/shipwright-security/scripts/tools/generate_security_report.py::_emit_findings_to_triage` | Every security-report run (after scan + prompt-injection consolidation) | `security` | One item per finding, severity inherited from scanner, dedup by `(tool, check_id, file, line)` within 24h |
| `plugins/shipwright-test/scripts/lib/performance_check.py::_emit_failures_to_triage` | Every perf-gate run (after `evaluate_gate`) | `performance` | One item per failed sub-check (Lighthouse score, LCP, bundle), severity `high` if >10% over budget else `medium`, dedup by `(metric, page)` within 24h |
| `shared/scripts/surface_verification.py::_emit_failure_to_triage` | F0.5 fail-closed exits (3 of 4 — see below) | `f0.5` | One item per non-zero exit, severity `critical`, dedup by `(run_id, surface, condition)` within 24h. Items for the same `(run_id, surface)` whose condition cleared on a green re-run → auto-dismissed with `reason="f05Resolved"` |
| `shared/scripts/hooks/check_drift.py::_emit_drift_to_triage` | SessionStart hook on any timestamp / content drift in CLAUDE.md | `drift` | One item per file:kind (`timestamp` or `content`), severity `medium`, dedup by `(canonical file path, kind)` cross-session indefinite — the `content` path is `normcase`+`realpath`-canonicalized so Windows drive-letter casing can't split one drift across two items. Findings absent from the current run → auto-dismissed with `reason="driftResolved"` (this detector's own `timestamp`/`content` keys only — `artifact_sync.py`'s `:artifact` keys are left alone) |
| `shared/scripts/artifact_sync.py::_emit_drift_to_triage` | F1 (post-commit) drift check on changed_files vs sync_config | `drift` | One item per affected mapping pattern (`kind=artifact`), severity `medium`, dedup by `(pattern, kind)` cross-session indefinite |
| `shared/scripts/hooks/import_github_findings.py` | SessionStart hook, throttled (default 6h, configurable) | `github` | GitHub code-scanning / Dependabot / secret-scanning alerts + the latest failed default-branch CI run per workflow, pulled via `gh api`. As of iterate-2026-05-20 (`triage-launch-surface`), emits **action-units** (one per repo / per workflow) rather than per-finding items — see § "Action-units (iterate-2026-05-20)" below. Dedup keys `gh-security:{owner}/{repo}`, `gh-secrets:{owner}/{repo}`, `gh-ci:{workflow_id}`; `match_commit=False`, `window=None`. Each unit carries a `launchPayload` field (frozen at first append). Auto-resolve scoped to those three key prefixes (`reason="githubResolved"`), only for sources whose fetch succeeded. One-shot legacy migration sweeps pre-iterate-2026-05-20 per-finding items into `dismissed` with `reason="schemaMigration"`, also per-source-gated. Throttle state in `.shipwright/github_import_state.json`; fail-soft (never blocks SessionStart). A secret-scanning alert's raw `secret` value is never persisted, AND the `gh-secrets` action-unit `launchPayload` is whitelist-only (static rotation checklist + secret-scanning tab URL only — no alert content, no display names, no per-alert URLs). |

### Action-units (iterate-2026-05-20)

The GitHub producer collapses upstream findings into **action-units** —
one operator-actionable item per repo (security, secrets) or per
failing workflow (CI) — rather than mirroring per-finding state. GitHub
itself is the per-finding database; the triage inbox is a *launch
surface*.

| Action-unit              | Dedup key                       | Launch behavior                                                              |
|--------------------------|---------------------------------|------------------------------------------------------------------------------|
| security                 | `gh-security:{owner}/{repo}`    | `launchPayload` starts with `/shipwright-security` + GitHub security tab URL |
| secrets                  | `gh-secrets:{owner}/{repo}`     | `launchPayload` is a whitelist-only rotation checklist (no slash command)    |
| failed CI per workflow   | `gh-ci:{workflow_id}`           | `launchPayload` starts with `/shipwright-iterate --type bug` + workflow PAGE URL (stable across runs — the `head_sha` is intentionally NOT in the dedup key) |

`launchPayload` is **frozen at first append** — idempotent dedup
suppresses re-emission of the same key, so the payload persisted on the
first emission survives subsequent imports unchanged. Live counts in
`detail` are best-effort; operators click the GitHub URL in the payload
for current state.

`owner_repo` resolution is local-first (`git remote get-url origin`,
parsed by `github_api.parse_github_remote`). When the remote is
missing, malformed, or non-GitHub, the producer SKIPS repo-scoped
action-units rather than emitting malformed keys like `gh-security:`.

### Deferred producers

> The CI-failure producer — deferred under ADR-047 because a webhook
> receiver was out of scope — shipped in 2026-05 as part of the
> `github` producer above (`import_github_findings.py`). It is
> pull-based via `gh api`, not a webhook receiver, so the original
> "no autonomous local data source" objection no longer applies.

- **F0.5 `missing_block` producer** — the condition `"missing_block"`
  in the F0.5 dedup-key enum is reserved for a future audit-side
  producer in `shared/scripts/tools/verifiers/iterate_checks.py`. That
  detection happens post-commit (the file IS the writer of the block,
  so it cannot detect its own absence). The 3 runtime-fail producers
  ship in Iterate 2; the 4th audit-side producer ships in a later
  iterate.

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

### From the CLI

The launch-surface CLI (iterate-2026-05-20) is the canonical operator
interface, parallel to the future WebUI Triage tab. The pre-existing
`triage_promote.py` tool stays for back-compat — both invoke the same
library helper.

```bash
# List open items + their launchPayload (the "Fix now" surface)
uv run shared/scripts/tools/triage_cli.py list

# Promote to backlog (positional id)
uv run shared/scripts/tools/triage_cli.py promote trg-a1b2c3d4 \
  --task-ref "EXT:linear-ENG-7" \
  [--reason "urgent — Q2 release"]

# Dismiss (false-positive / won't-fix; positional id)
uv run shared/scripts/tools/triage_cli.py dismiss trg-a1b2c3d4 \
  --reason notRelevant

# Legacy promote tool (back-compat — unchanged from iterate-2026-05-11)
uv run shared/scripts/tools/triage_promote.py \
  --id trg-a1b2c3d4 --task-ref "EXT:linear-ENG-7"
```

Exit codes (`triage_cli.py promote|dismiss`):

- `0` — status flipped; triage_inbox.md will re-render on next Stop hook
- `2` — invalid input (missing required option, item id not found,
  state already-promoted/dismissed/snoozed, or `--task-ref`/`--reason`
  contains control chars / is too long)

(The legacy `triage_promote.py` retains its richer exit-code surface:
`2` for invalid input, `3` for unknown id, `4` for uninitialised store.
The new CLI collapses 3/4 into 2 for simpler scripting.)

**Fix-now flow.** Open `.shipwright/agent_docs/triage_inbox.md` (or run
`triage_cli.py list`), find the item, copy the `launchPayload` fence
into a new Claude session. The matching slash command auto-fires there.
The existing lifecycle hooks flip the item once the run completes.

`--task-ref` is sanitized: no newlines, tabs, or ASCII control
characters; max 200 chars. `--reason` follows the same rules (max
500 chars). Free-form otherwise — `EXT:linear-ENG-7`,
`EXT:asana-12345`, `https://my-tracker/issues/42` — downstream consumers
expect a human-readable token. (When the WebUI Triage tab lands in
shipwright-webui Iterate B, it writes the actual `ExternalTask` record
and sets `promotedTaskId` on the triage side automatically; it
delegates to the same library helpers as the CLI so audit-trail shape
is byte-identical.)

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
`info → P3-or-skip`, source `security/performance/ci/github/phaseQuality/iterate
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
