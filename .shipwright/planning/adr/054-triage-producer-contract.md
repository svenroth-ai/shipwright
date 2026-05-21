# ADR-054 — Triage Producer Contract (B0 design decisions)

> Long-form spec backing the iterate-2026-05-21-triage-producer-contract
> ADR drop. The drop's `--spec-ref` points here so future readers don't
> have to reconstruct the design rationale from commits.

## Audience principle

The triage inbox is a **launch-surface for one operator** (today the
human, Phase 3 leadwright autonomously). The right balance: less noise,
loud only where relevant; accept everything else as the cost for the
solo-dev / agentic-engineering audience. This principle drives every
decision below — when in doubt, drop a feature rather than add nuance.

## Decisions (B0)

### D1. SBOM-undeclared triage granularity — **1 item per workspace/manifest**

When the SBOM scanner finds packages without declared licenses, emit one
triage item *per workspace* (e.g. one per `package.json` /
`pyproject.toml` discovered under the project root, excluding the usual
`node_modules / .venv / dist / .worktrees / .shipwright / coverage`
exclude list).

Body lists the top-20 offending packages with a "+N more" footer.
`launchPayload` contains a workspace-specific fix command. Auto-resolve
when the workspace has zero undeclared packages.

Rejected alternatives:
- *1 global item* — muddies the launchPayload because client and server
  workspaces use different package managers and different fix steps.
- *1 item per package* — drowning noise; solo dev fixes in batches.

### D2. Test-failure triage granularity — **1 item per layer**

Layers are `unit | integration | e2e | pgtap` — the keys already present
in `record_event.layers`. One open triage item per failing layer.

`detail` field lists the top-10 failing test IDs (truncated with "+N
more" footer). `launchPayload` calls `/shipwright-iterate --type bug`
scoped to the whole layer. Auto-resolve when the layer goes back to
all-green.

Rejected alternatives:
- *1 item per (layer, suite)* — was my initial proposal. Engineering
  precision without operator UX value: solo dev fixes batched in a
  single Claude session anyway, and the launchPayload's top-10 IDs give
  enough context. Suite-level dedup would inflate the inbox during
  multi-suite outages.
- *1 global "Tests are red"* — too vague to triage; loses the
  layer-based severity default below.

### D3. Severity default-action mapping — **layer-based**

The default Fix-now affordance hinges on layer not severity, because
solo dev's "what should I do first" answer is rooted in surface area:

| Layer       | Default CTA  | Severity-floor |
|-------------|--------------|----------------|
| e2e         | Fix now      | major          |
| integration | Fix now      | major          |
| pgtap       | Fix now      | major          |
| unit        | Triage       | minor          |

The operator always overrides. This is presentation-side; the wire
`severity` enum stays critical/high/medium/low/info (D7).

### D4. Stale-item auto-dismiss — **7 days**

Items that haven't been touched (no producer re-emit, no manual status
flip) for 7 days are auto-dismissed with `reason="stale"`. Symmetric
window for both the test-rename case and the general "I forgot about
this card" case.

Rejected alternatives:
- *30 days* — was my initial proposal. Too long for a solo-dev cadence
  where iterations are daily. Stale rot accumulates.
- *Never auto-dismiss* — every forgotten card stays forever. Tested with
  6 months of project life: the inbox becomes a graveyard.

### D5. RTM ↔ Triage linkage — **first-class wire fields**

Three optional camelCase keys on every triage append event:

- `frId` — e.g. `"FR-01.05"`
- `suiteId` — e.g. `"client/src/auth.test.tsx"`
- `eventId` — e.g. `"evt-abc12345"` (back-ref to `shipwright_events.jsonl`)

The compliance RTM renderer (B.4) consumes these by querying
`read_all_items()` for any open triage item whose `frId` matches the
row's FR. Renders a markdown link `[FAIL → trg-XXX](triage_inbox.md#trg-XXX)`.

Plugin-only / WebUI-less operators get clickable navigation in VS Code's
markdown preview — no WebUI dependency. The Triage Inbox aggregator
emits stable HTML anchors `<a id="trg-XXX"></a>` above each card so the
link resolves correctly.

Producers populate these fields opportunistically. Today's producers
don't have FR context (Phase-Quality, drift, SBOM); the new test-evidence
producer (B.3) will. Null is the wire default.

### D6. Info-severity collapse — **`<details>` block at file end**

Solo-dev pragmatism dial. The aggregator partitions open items by
severity:

- critical / high / medium / low → top section, severity-sorted as today
- info → collapsed `<details>` block at the end of `triage_inbox.md`

Info items are mostly drift findings or observability noise — useful to
have around, useless to scan past every time. The block summary shows
the count so the operator knows there's something there.

### D7. Severity vocabulary — **unchanged**

Stays critical/high/medium/low/info. The plan's tentative
info/warn/major/minor rename was rejected — breaking change, no UX
benefit, every downstream consumer would have to migrate.

### D8. `resolve_condition` declarative field — **rejected for B0**

Plan suggested a declarative `resolve_condition` dict so producers could
state "this item should auto-resolve when X happens" in data rather
than code.

Rejected because:
- Producer set is small (~7) and stable.
- Hardcoded auto-resolve in each producer is easier to test (existing
  pattern, dozens of tests already).
- No third-party producers (yet) — no consumer of declarative resolve.

Worth revisiting only if (a) producer count grows >10 or (b) leadwright
ships a producer that doesn't fit the hardcoded pattern.

## Consequences

- B.2 (SBOM polish) implements D1 + D5.
- B.3 (test-evidence polish) implements D2 + D3 + D5.
- C.2 (drift detector) emits info-severity items by default → lands in
  the collapsed block.
- RTM generator (B.4) consumes D5 for the failing-row deep-link.
- Public-launch operators (and leadwright, Phase 3) see a quiet inbox
  by default and can drill into info-severity drift when they want to.

## Rejected (kept here so future me sees the explored space)

- **Snooze status flip** — present in today's `STATUSES` tuple but adds
  marginal UX value for solo dev. Likely deprecation candidate when the
  set of producers stabilizes; not addressed in B0.
- **Severity → priority mapping made data-driven** — today's
  `PRIORITY_FROM_SEVERITY` dict is 5 entries, stable, well-tested.
  Configurable mapping would add complexity for no operator benefit.

## See also

- Iterate spec: `.shipwright/planning/iterate/2026-05-21-triage-producer-contract.md`
- Schema: `shared/schemas/triage_item.schema.json`
- Producer API: `shared/scripts/triage.py`
- Aggregator: `shared/scripts/tools/aggregate_triage.py`
- Earlier ADRs: ADR-046 (Triage Inbox storage), ADR-047 (Producers-2),
  ADR-052 (action-unit migration), ADR-053 (launch-surface).
