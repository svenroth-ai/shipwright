# Iterate Spec: triage-launch-surface

- **Run ID:** iterate-2026-05-20-triage-launch-surface
- **Type:** feature
- **Complexity:** medium
- **Status:** draft

## Goal

Convert the Triage Inbox from a finding-mirror (#39's 1:1 import — 32 GitHub
findings → 32 triage items) into a **launch-surface**: a small number of
operator-actionable items, each carrying a ready-to-paste `launchPayload`
that the operator copies into a new Claude session to start the matching
run. Ship CLI as the first-class operation surface; the WebUI in Iterate B
will be a thin wrapper over the same library.

## Acceptance Criteria

> All ACs are assertion-shaped — the F0.5 CLI runner verifies them
> mechanically via pytest against `.shipwright/triage.jsonl` round-trips
> and CLI subprocess invocations.

- [ ] **AC-1-agent** Given a project with open GitHub code-scanning +
  Dependabot + secret-scanning alerts and at least one failed default-branch
  CI workflow, when `import_findings(project_root)` runs, then
  `.shipwright/triage.jsonl` contains **action-unit** items keyed by
  `gh-security:{owner}/{repo}`, `gh-secrets:{owner}/{repo}`, and
  `gh-ci:{workflow_identity}` (one per failed workflow) — exactly one item
  per action-unit per repo, regardless of how many underlying findings
  exist. No per-finding `github:code-scanning:<n>` / `github:dependabot:<n>`
  / `github:secret-scanning:<n>` items are emitted by this producer.

- [ ] **AC-2-agent** Given a producer run that emits an action-unit, when
  the wire JSON is inspected, then the appended event carries a non-empty
  `launchPayload` string with **deterministic** content (sorted/normalized
  inputs so the same finding set yields byte-identical payloads across
  runs). For `gh-security` the payload starts with `/shipwright-security`
  and contains the GitHub security-tab URL; for `gh-ci` it starts with
  `/shipwright-iterate --type bug` and contains the **workflow page** URL
  (stable across runs — NOT a single-run URL, since the dedup key drops
  the head_sha); for `gh-secrets` it contains a whitelist-only plain-text
  rotation checklist + the GitHub secret-scanning **tab** URL — no slash
  command, no alert titles, no `secret_type` display, no locations or
  commit SHAs from individual alerts (review finding #9: hard hygiene
  boundary, tested with a fixture-leak assertion).

- [ ] **AC-3-agent** Given action-unit items exist in `triage.jsonl`, when
  `aggregate_triage.py` regenerates `.shipwright/agent_docs/triage_inbox.md`,
  then each open action-unit item renders its `launchPayload` inside a
  fenced markdown code block (triple-backtick fence) immediately under the
  item's title/severity line, ready for the operator to copy into a new
  Claude session.

- [ ] **AC-4-agent** Given an existing `triage.jsonl` containing only the
  header line, when `uv run shared/scripts/tools/triage_cli.py list` runs
  against that project, then it prints a human-readable list of open
  triage items (one block per item: id, source, severity, title, then the
  `launchPayload` fenced block) and exits 0. With no open items it prints
  a single line ("No open triage items.") and exits 0.

- [ ] **AC-5-agent** Given an open triage item `trg-XXXXXXXX`, when
  `uv run shared/scripts/tools/triage_cli.py promote trg-XXXXXXXX
  --task-ref EXT:foo` runs, then `triage.jsonl` gains a status event
  flipping the item to `promoted` with `by=cli` and
  `promotedTaskId=EXT:foo`; the CLI exits 0 and prints a confirmation.
  Behavior matches the existing `triage_promote.py` tool (which the CLI
  delegates to under the hood) — no semantic divergence.

- [ ] **AC-6-agent** Given an open triage item `trg-XXXXXXXX`, when
  `uv run shared/scripts/tools/triage_cli.py dismiss trg-XXXXXXXX
  --reason notRelevant` runs, then `triage.jsonl` gains a status event
  flipping the item to `dismissed` with `by=cli` and
  `reason=notRelevant`; the CLI exits 0.

- [ ] **AC-7-agent** Given a `triage.jsonl` that pre-dates this iterate
  and contains legacy per-finding items with dedup keys
  `github:code-scanning:*`, `github:dependabot:*`,
  `github:secret-scanning:*`, or `github-ci:{wf}:{sha}` (with sha
  suffix), when `import_findings` next runs, then every still-open
  legacy item is dismissed with `reason=schemaMigration` exactly once
  **— gated PER ORIGINAL SOURCE, not per new-prefix**. Mapping is
  one-to-one: `github:code-scanning:*` migrates only if
  `fetch_code_scanning_alerts()` succeeded; `github:dependabot:*` only
  if `fetch_dependabot_alerts()` succeeded; `github:secret-scanning:*`
  only if `fetch_secret_scanning_alerts()` succeeded; `github-ci:*`
  only if `fetch_workflow_runs(default_branch())` succeeded.  A failed
  fetch for a given source MUST NEVER trigger migration for that
  source's legacy items (preserves the ADR-052 fail-soft invariant
  — review finding #3). The sweep operates on the `read_all_items`
  resolved view and ignores items whose current status is not
  `triage` (review finding #12: idempotent re-run never appends a
  second `schemaMigration` status event for the same item).

- [ ] **AC-8-agent** Given the producer's launch payload generation,
  when the same finding set is imported twice (idempotent path), then
  the second run does NOT emit a duplicate append event for the
  unchanged action-unit and the persisted `launchPayload` from the first
  append is unchanged. Live count + severity-breakdown in the `detail`
  field is best-effort and frozen at first-append (operators click
  through the GitHub URL in `launchPayload` for live state).

- [ ] **AC-9-agent** Given the schema extension, when the existing
  Phase-Quality / Compliance / Security / Performance / F0.5 / Drift
  producers (legacy producers — finding-granular, unchanged scope) emit
  items, then they MAY emit `launch_payload=None` (or omit the kwarg);
  the storage layer must persist the field as `null` on the wire when
  absent. No legacy producer is required to populate it in this iterate
  — only the GitHub producer wires payloads. Drift protection: a
  parametrized test asserts the persisted schema is identical for items
  with and without `launchPayload`.

- [ ] **AC-10-agent** Given a project where `git remote get-url origin`
  returns a recognised GitHub URL (HTTPS `https://github.com/{owner}/
  {repo}[.git]` OR SSH `git@github.com:{owner}/{repo}[.git]` OR
  enterprise `https://github.example.com/{owner}/{repo}[.git]`), when
  `owner_repo()` runs, then it returns `"{owner}/{repo}"` with the
  `.git` suffix stripped and no host segment. When the remote is
  missing, malformed, or non-GitHub, `owner_repo()` returns `None` and
  the producer SKIPS emission of any `gh-security:*` or `gh-secrets:*`
  action-unit (logging a single stderr warning, exit-0) rather than
  emitting a malformed key like `gh-security:` (review finding #4).
  `gh-ci:*` items remain unaffected since they key off
  `_workflow_identity`, not owner/repo.

- [ ] **AC-11-agent** Given the new CLI's `promote` subcommand, when it
  is invoked with the same args as the existing `triage_promote.py`,
  then the appended status event is byte-identical between the two
  tools (same `newStatus`, same `promotedTaskId`, same audit fields)
  except for the `by` value (`"cli"` vs `triage_promote.py`'s
  current value). The implementations MUST share a single helper —
  `triage_promote.promote_item(...)` (extracted) — to guarantee parity
  (review finding #2). A parity test runs both tools against an
  identical seeded `triage.jsonl` fixture and diffs the resulting
  status events with `by` field excluded.

- [ ] **AC-12-user** (optional UAT — does not gate finalization) On the
  operator's machine after the iterate ships, the operator runs
  `uv run shared/scripts/tools/triage_cli.py list`, copies one
  `launchPayload` fence into a new Claude session, observes the matching
  slash command auto-fire, and confirms the run starts against the
  referenced finding. The agent cannot verify Claude-session
  copy-paste behavior end-to-end; this AC documents the intended user
  flow but is checked manually post-merge.

## Spec Impact

- **Classification:** modify
- **ADD:** none
- **MODIFY:** **FR-01.14** (Triage Inbox) — the GitHub producer's emission
  shape changes from per-finding to action-unit; a new `launchPayload`
  field is added to the wire schema; a CLI surface is established as
  first-class alongside the future WebUI Triage tab. Append a new
  "Refined by `iterate-2026-05-20-triage-launch-surface`" block to
  FR-01.14 with E-form ACs covering action-unit emission,
  `launchPayload` round-trip through the inbox view, CLI subcommands,
  and the one-shot legacy auto-migration.
- **REMOVE:** none
- **NONE justification:** n/a (modify applies)

## Out of Scope

- WebUI Triage-tab UI changes — that is **Iterate B**, separate, on the
  `shipwright-webui` repo. This iterate ships only the monorepo-side
  primitives.
- A `fix` CLI verb that auto-spawns a Claude session subprocess — the
  v1 flow is read-payload-from-inbox + manual copy-paste. A future
  iterate may add `--autonomous` once the launcher pattern is proven.
- Refactoring `triage_promote.py` into the new CLI — it stays as-is for
  back-compat; the new CLI's `promote` subcommand delegates to its
  `mark_status` call. Removing the old tool is a separate housekeeping
  task.
- Live-count refresh of action-unit `detail` fields. Producer-time
  freeze accepted; operators use the GitHub URL in `launchPayload` for
  live state.
- Per-finding false-positive dismissal — operators continue to do this
  on GitHub (SARIF-level dismissal), not in the triage inbox.
- Changing `github_api.py`, `import_github_findings.py` (SessionStart
  hook), or the 6h throttle — all keep their #39 behavior.

## Design Notes

n/a — no UI in this iterate. The user-erlebbare surface is the CLI and
the markdown inbox view; verified via F0.5 `cli` surface.

## Affected Boundaries

`triage.jsonl` is a serialized format crossed by multiple
producer/consumer pairs. Adding the `launchPayload` field changes the
wire schema; producers MUST emit it consistently, consumers MUST tolerate
its absence (legacy items + non-github producers that don't populate).

| Producer (writes)                                              | Consumer (reads)                                                                                       | Format        |
|---|---|---|
| `shared/scripts/github_triage.py::import_findings` (action-units + payloads) | `shared/scripts/tools/aggregate_triage.py` (renders `triage_inbox.md`)                                | JSONL (triage)|
| `shared/scripts/triage.py::append_triage_item[_idempotent]` (schema extension: `launchPayload` field) | `shared/scripts/triage.py::read_all_items` (resolved view; passes `launchPayload` through)            | JSONL (triage)|
| `shared/scripts/tools/triage_cli.py` (`promote`/`dismiss` write status events) | `shared/scripts/triage.py::read_all_items` + existing aggregator                                       | JSONL (triage)|
| `shared/scripts/triage.py::append_triage_item[_idempotent]` (legacy producers — phase-quality/compliance/security/perf/F0.5/drift, unchanged) | `shared/scripts/triage.py::read_all_items` (must accept items where `launchPayload` is `null`/absent) | JSONL (triage)|

Round-trip test required (producer→file→consumer) in the Build's
Boundary Probe sub-step. Drift protection: parametrized test across
all 7 producer call-sites asserting that an item with
`launch_payload=None` (or omitted kwarg) round-trips identically to
today, and an item with a non-null payload survives the resolver.

## Confidence Calibration

Mandatory at medium. Pre-F0 empirical probes (drawn from the 8
boundary-probe categories — `references/boundary-probes.md`):

- **Boundaries touched:** 4 producer→consumer pairs across
  `triage.jsonl` (see "Affected Boundaries" table above).
- **Empirical probes run:**
  1. **Producer→file→consumer round-trip with payload set**
     (`test_round_trip_*`, `test_append_persists_launch_payload`,
     `test_wire_event_carries_supplied_payload_verbatim`) — PASS:
     `launchPayload` survives serialization byte-identical (incl.
     leading whitespace, embedded newlines, embedded backticks).
  2. **Round-trip with payload omitted/null**
     (`test_append_omitted_kwarg_persists_null`,
     `test_wire_event_carries_launch_payload_key_always`) — PASS:
     consumers see `launchPayload: null` on the wire even when the
     producer omitted the kwarg. Legacy producers stay no-op.
  3. **Parametrized null-safety across all 10 KNOWN_SOURCES**
     (`test_every_source_persists_null_when_payload_omitted`,
     `test_every_source_persists_payload_when_supplied`) — PASS:
     no source has a non-None default.
  4. **Idempotency / payload frozen at first append**
     (`test_idempotent_second_call_does_not_overwrite_payload`,
     `test_import_findings_idempotent_payload_frozen`) — PASS:
     second identical import does NOT mutate the persisted payload.
  5. **Determinism under reordering**
     (`test_security_action_unit_payload_deterministic`) — PASS:
     shuffled alert input → byte-identical payload + title.
  6. **Legacy-key migration sweep — happy path**
     (`test_legacy_items_migrated_when_all_fetches_succeed`) — PASS:
     four legacy items dismissed in one run.
  7. **Legacy-key migration — per-source-gated** (4 parametrized
     cases, `test_legacy_migration_per_source_gated[...]`) — PASS:
     `None` fetch leaves THAT source's legacy items untouched while
     siblings migrate. Confirms ADR-052 fail-soft invariant.
  8. **Legacy migration idempotency**
     (`test_legacy_migration_is_idempotent`) — PASS: re-run does not
     append redundant `schemaMigration` status events.
  9. **Cross-producer isolation**
     (`test_legacy_migration_leaves_non_github_items_untouched`,
     `test_resolve_leaves_other_sources_untouched`) — PASS: drift +
     phaseQuality items survive the github resolve pass.
  10. **CLI subprocess against fixture jsonl** (`test_triage_cli.py`,
      14 tests) — PASS: list / promote / dismiss + parity with
      `triage_promote.py` + control-char stripping.
  11. **Secret-hygiene** (`test_secret_value_never_written_to_triage_file`,
      `test_secrets_action_unit_payload_is_whitelist_only`,
      `test_secrets_action_unit_detail_does_not_leak_alert_content`)
      — PASS: raw `secret` value, alert display names, per-alert URLs
      all absent from persisted fields.
  12. **owner_repo resolution matrix** (`test_github_api.py`, 26
      tests) — PASS: 12 recognised remote shapes (HTTPS/SSH/enterprise/
      token-bearing) resolve correctly; 8 invalid shapes return
      `None`; `_gh_api` never invoked from the resolver.
  13. **owner_repo-unresolvable producer skip**
      (`test_import_findings_skips_repo_scoped_when_owner_repo_none`,
      `test_security_action_unit_returns_none_when_owner_repo_none`,
      `test_secrets_action_unit_returns_none_when_owner_repo_none`,
      `test_ci_action_unit_returns_none_when_owner_repo_none`) —
      PASS: no malformed dedup keys ever emitted.
  14. **Safe-fence rendering** (`test_payload_with_triple_backticks_uses_longer_fence`)
      — PASS: payload with embedded ` ``` ` uses a 4-backtick fence.

- **Edge cases NOT probed + why acceptable:**
  - **POSIX `export` prefix / inline `# comment` / quoted `#` in
    JSONL line** — N/A. `triage.jsonl` is a machine-only JSON-per-line
    format; lines are produced by `json.dumps` (no operator hand-edit
    path). Justified by the existing `test_triage_storage.py` corpus
    and ADR-024.
  - **Concurrent producer race on `launchPayload`** — already covered
    by the existing `test_idempotent_concurrency_under_lock`
    (8-thread race, 1 winner). Adding `launch_payload` does not
    change the locking semantics; it's part of the same `new_event`
    dict assembled before the lock.
  - **Cross-process file lock with `launch_payload`** — same
    reasoning as above. The kwarg threading is purely data, the lock
    discipline is unchanged.

- **Confidence-pattern check:** Code review surfaced 14 findings from
  GPT-5; all integrated into spec + mini-plan + tests before
  implementation. The "are you confident?" question has not appeared
  in this iterate — the externalized review replaced that loop with
  empirical findings. Asymptote heuristic: probes #1-#14 above plus
  the 218 green tests cover every named risk; the next probe would
  fall into the operator-input or hardware-failure categories which
  are N/A for a machine-written JSONL surface in a Python monorepo.

## Self-Review (7-point checklist)

Mandatory at every complexity. Format follows ADR-024 + the iterate
SKILL.md Step 7.

1. **Spec compliance.** 11 of 11 mechanically-verifiable ACs covered
   by tests (AC-1..AC-9, AC-10, AC-11). AC-12 is operator UAT
   (documented but explicitly does NOT gate finalization).
2. **Error handling.** Producer / mapper / CLI all fail-soft:
   `owner_repo` returns `None` and the producer skips emission;
   `_resolve_stale` / `_migrate_legacy_items` swallow per-item
   exceptions with a stderr line. CLI maps each library exception
   class to exit code 2 with a helpful stderr message.
3. **Security.** No new ASK-FIRST / NEVER violations. The
   secret-scanning hygiene boundary tightened — the action-unit
   `launchPayload` is whitelist-only, never carries alert content,
   `_SENTINEL` test fixture proves no leak.
4. **Test quality.** 218 tests green across the touched surface.
   No skips. No flaky timing tests (legacy-migration idempotency
   counts status events, not wall-clock). Round-trip + drift
   protection at every layer (schema, mapper, aggregator, CLI).
5. **Naming.** `launch_payload` (Python) ↔ `launchPayload` (wire,
   camelCase per ADR-046). Action-unit dedup keys
   `gh-security:` / `gh-secrets:` / `gh-ci:` are stable, namespaced,
   and visually distinct from the legacy `github:` / `github-ci:`
   prefixes — eyeballing a `triage.jsonl` makes the migration state
   obvious.
6. **Test wiring.** Every test asserts on persisted state
   (round-trip through `read_all_items` or raw file bytes), not on
   internal mock calls. The CLI tests invoke the script via
   `subprocess.run`, not by importing `main()`, so argparse / exit
   codes / stderr are exercised end-to-end.
7. **Affected Boundaries** (touches_io_boundary). The 4
   producer→consumer pairs (see "Affected Boundaries" table) are
   covered by probes #1, #3, #6, #9 in Confidence Calibration above.
   Drift protection layer present: `test_every_source_persists_*`
   parametrized across all 10 documented sources.

**Known acceptable diffs from convention:**

- `test_github_triage_action_units.py` (526 lines) exceeds the
  300-line guideline. Cleaner split is `mappers` vs `migration` (two
  ~260-line files); deferred to a follow-up iterate so this iterate's
  scope stays focused. Captured as a Self-Review follow-up.
- `test_triage_promote.py` (331) and `test_triage_aggregator.py`
  (309) marginally over the guideline (≤ 11 lines over). Acceptable
  inline.
- `shared/scripts/github_triage.py` grew from 419 → 706 lines
  (action-unit mappers + legacy migration sweep). The natural split
  is `github_triage_mappers.py` (pure functions) +
  `github_triage_orchestrator.py` (import_findings + state + throttle).
  Deferred — would re-import-graph every caller in the same iterate;
  see follow-up.

## Verification (medium+)

- **Surface:** cli
- **Runner command:**
  `uv run --extra dev pytest shared/tests/test_github_triage.py shared/tests/test_triage.py shared/tests/test_aggregate_triage.py shared/tests/test_triage_cli.py shared/tests/test_triage_launch_payload_roundtrip.py -v --color=no`
- **Evidence path:**
  `.shipwright/runs/iterate-2026-05-20-triage-launch-surface/surface_verification.log`
- **Justification:** n/a (cli surface applies — this is a library/CLI
  monorepo; the existing pattern matches iterate-2026-05-19's
  `surface_verification` block).

## Implementation Order (mini-plan summary)

Detailed mini-plan at
`.shipwright/planning/iterate/2026-05-20-triage-launch-surface-miniplan.md`.

1. Extend `triage.py` schema: add `launch_payload` kwarg to both
   `append_triage_item` and `append_triage_item_idempotent`; persist as
   wire-name `launchPayload`; default `None`; preserve through
   `read_all_items`. Update existing tests to assert `launchPayload`
   round-trips as `null` for items that don't pass it.
2. Rebuild `github_triage.py` mapping:
   - Add three new mapper helpers: `security_action_unit(alerts:
     {"code_scanning": list, "dependabot": list}, owner_repo: str)`,
     `secrets_action_unit(alerts: list, owner_repo: str)`,
     `ci_action_unit(run: dict)`. Each returns either a single dict
     (action-unit item kwargs incl. `launch_payload`) or `None`.
   - Replace the per-finding emit loop with action-unit emission.
     Keep `triage_severity`, `_kind_for`, `_workflow_identity` helpers.
     Delete the four legacy item-mapper functions (`code_scanning_item`,
     `dependabot_item`, `secret_scanning_item`, `ci_item`).
   - Update `_OWNED_PREFIXES` to the new three (`gh-security:`,
     `gh-secrets:`, `gh-ci:`) for the ADR-052 auto-resolve scoping.
   - Add a one-shot `_migrate_legacy_items(project_root,
     resolvable_prefixes)` sweep that runs at the top of
     `import_findings` immediately after the resolvable-prefix set is
     computed: every still-open `source=github` item whose dedup key
     carries a legacy prefix AND whose corresponding new-prefix fetch
     succeeded is marked dismissed with `reason=schemaMigration`.
   - The `latest_failed_ci_runs` helper stays unchanged — still groups
     by workflow identity and keeps only the latest concluded run.
     The new `ci_action_unit` mapper consumes ITS output, but the
     dedup key drops the sha suffix.
3. Extend `aggregate_triage.py` to render `launchPayload` as a fenced
   markdown code block per open item in `triage_inbox.md`. Idempotent
   re-render preserves the existing inbox-doc layout otherwise.
4. New CLI: `shared/scripts/tools/triage_cli.py` with three
   subcommands (`list`, `promote`, `dismiss`). `promote` delegates to
   `triage_promote.py`'s underlying `mark_status` (or imports
   `triage_promote.main`); `dismiss` calls `mark_status` directly;
   `list` reads `read_all_items` and prints. Argparse-driven, exit 0
   on success / 1 on validation error / 2 on missing item.
5. Tests at every layer (see mini-plan).
6. Doc updates (mandatory): `docs/guide.md` Chapter 4 (Triage Inbox
   phase) + new sub-section "Triage as Launch-Surface"; `docs/hooks-
   and-pipeline.md` artifact-write + context-loading matrices.

## Linked memory

- [[triage-launch-surface-redesign]] (design memory — agreed 2026-05-19)
- ADR-046 (triage storage SSoT + idempotent under-lock dedup)
- ADR-049 (worktree isolation — base for this iterate)
- ADR-050 (worktree-aware event-log resolution)
- ADR-052 (auto-resolve key-shape-scoped)
- FR-01.14 (Triage Inbox)
- iterate-2026-05-19-github-triage-importer (PR #39 — superseded mapping)
