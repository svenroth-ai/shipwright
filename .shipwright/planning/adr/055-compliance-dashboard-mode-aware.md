# ADR-055 — Compliance Dashboard mode-aware indicators (B.1)

> Long-form spec backing the iterate-2026-05-21-b1-compliance-dashboard
> ADR drop.

## Audience principle

Same as B0 ADR-054: solo dev today, leadwright Phase 3. The dashboard
should answer "is anything wrong, and if so where do I look?" — in one
glance. Misleading WARN rows (the `1/7 WARN` for an adopted project
that will *never* run a 7-phase pipeline) actively erode trust in the
indicator. Every WARN must be either actionable or unequivocally
correct.

## Decisions (B.1)

### D1. Adopted-mode detection via `run_config.adoption` (not `scope`)

The artifact-polish plan's original wording — "lese `run_config.scope`
(adopt vs greenfield)" — was wrong. Empirically `scope` carries values
like `"library"` / `"full_app"`, orthogonal to adoption status. The
authoritative signal is the presence of the `adoption` object written
by `/shipwright-adopt`.

The check lives in `_is_adopted(run_config)` and is intentionally tiny
(`return isinstance(run_config.get("adoption"), dict) and bool(...)`)
so future adoption-marker fields (a v2 of the adoption object, say)
don't break it.

### D2. Pipeline-phases row → `n/a (adopted)` (not hidden)

For adopted projects the `Pipeline phases completed` row stays in the
dashboard but renders as `n/a (adopted)` with INFO status. Rationale:

- The reader (human or leadwright) sees that the dashboard understands
  the project's lineage. A missing row is ambiguous ("did the
  indicator break?"); an explicit `n/a` is informative.
- INFO (not PASS) because the project genuinely never ran the
  pipeline — claiming PASS would imply phases were completed.

### D3. Hide `Work events (build)` and `All sections reviewed` for adopted

These two rows ARE removed entirely. Different reasoning from D2:

- They report counts (`0 sections`, `0/0 reviewed`) that are
  structurally `0` for adopted projects — the project was onboarded
  with existing code, not built section by section.
- An `0 sections WARN` is more confusing than the absent row.
- The Iterate-specific rows (`Work events (iterate)`, `Iterate tests
  passing`) stay because they're meaningful in both modes.

### D4. Why-warn column — static one-line pointers, no dynamic analysis

The new 4th column carries a per-indicator pointer string on WARN
rows. The strings are inline-templated in `_quality_indicators_events`,
e.g.:

- Unit tests WARN → `"{failing}/{total} failing — see test-evidence.md"`
- Pipeline phases WARN → `"{n} phase(s) pending — see shipwright_events.jsonl"`
- Iterate tests WARN → `"{n} iterate(s) without tests — see test-evidence.md"`
- Copyleft risk WARN → `"{n} copyleft license(s) detected — see sbom.md"`
- Sections-reviewed WARN → `"{n} section(s) unreviewed — see change-history.md"`
- Triage open WARN → `"{signal} actionable item(s) — see ../agent_docs/triage_inbox.md"`

Rejected: dynamic analysis (e.g. "iterates 4, 7, 9 regressed"). The
dashboard is a launchpad, not a triage tool. Deep diagnosis lives
in the Triage Inbox (B0). Solo-dev pragmatism: simple templates win.

### D5. Triage open — split signal vs info; only signal triggers WARN

Mirrors the inbox's signal-first render from B0 ADR-054 D6. Value
formats:

| Open state | Rendered value | Status |
|------------|----------------|--------|
| 0 signal, 0 info | `0 open` | PASS |
| N signal, 0 info | `N open` | WARN |
| 0 signal, M info | `0 open (M info)` | PASS |
| N signal, M info | `N open (M info)` | WARN |

Dismissed / promoted / snoozed items don't contribute. Items with
malformed severity are skipped silently (tolerant reader matches
`triage.read_all_items`).

### D6. Only the event-based path is touched

`_quality_indicators_legacy` (the pre-event-log path) is left
unchanged. Adopted projects always have events (their iterates
emit them), so the legacy path is greenfield-only. Less to verify.

## What landed in B.1 vs forward-looking

| Decision | Realized in this iterate? |
|----------|--------------------------|
| D1 Adopted-mode detection      | **Yes** |
| D2 Pipeline-phases n/a row     | **Yes** |
| D3 Hide build-section rows     | **Yes** |
| D4 Why-warn column             | **Yes** |
| D5 Triage open indicator       | **Yes** |
| D6 Legacy path unchanged       | **Yes (intentional non-change)** |

## Consequences

- Adopted-project dashboards (shipwright monorepo itself, webui) no
  longer carry the misleading `1/7 WARN` row.
- Operators see "where to look next" inline on every WARN row.
- The Triage Inbox gets a permanent surface on the compliance home
  page — operators don't have to remember to check it.

## Rejected (recorded for future me)

- **Hide pipeline row entirely for adopted** — ambiguous (could look
  like a bug). Explicit `n/a` is clearer.
- **Generate Why-warn dynamically** — over-engineering for solo dev;
  static pointers are sufficient.
- **Make the dashboard a HTML page with hyperlinks** — out of scope;
  markdown plays nice with VS Code preview and CI artifacts.

## See also

- Iterate spec: `.shipwright/planning/iterate/2026-05-21-b1-compliance-dashboard-mode-aware.md`
- Compliance report: `plugins/shipwright-compliance/scripts/lib/compliance_report.py`
- Triage schema: `shared/schemas/triage_item.schema.json` (B0 / ADR-054)
- Earlier ADRs: ADR-046 (Triage Inbox), ADR-054 (Triage Producer Contract — B0).
