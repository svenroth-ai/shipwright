# Iterate Spec: B.2 — SBOM polish (per-workspace undeclared triage)

- **Run ID:** iterate-2026-05-21-b2-sbom-polish
- **Type:** feature
- **Complexity:** small
- **Status:** draft

## Goal

Close the artifact-polish plan's Iterate B.2 by implementing the
producer-side of ADR-054 D1: one `source="sbom"` triage item per
workspace whose manifest has packages with unresolved licenses
(`license == "unknown"`), auto-resolved when the workspace re-runs
clean.

Phase 0f (PR-merged earlier in this plan) already shipped the
workspace-aware traversal + lockfile-first JS license resolution +
`importlib.metadata` Python resolution. What's left is the operator
launch-surface: a triage card per offending workspace with a
copy-pasteable fix command. Without it, undeclared rows in `sbom.md`
have no path to action — the operator has to remember the legacy
`uv sync` / `npm install` ritual on their own.

## Acceptance Criteria

- [ ] **AC-1** `data_collector.collect_undeclared_by_workspace(project_root)`
  returns one dict per manifest with ≥1 undeclared package, shaped as
  `{"manifest_rel_path": str, "manifest_type": "npm"|"python",
  "undeclared": [{"name", "version"}, ...]}`. POSIX-style paths on all
  platforms (no `\` in `manifest_rel_path`).

- [ ] **AC-2** Manifests whose every dep resolves to a real license are
  omitted from the returned list (no work for the operator → no triage
  noise).

- [ ] **AC-3** The workspace exclude list (`node_modules`, `.venv`,
  `dist`, `build`, `.shipwright`, …) used by `collect_dependencies` is
  honored by the new collector — no false-positive groups from manifests
  inside excluded dirs.

- [ ] **AC-4** `sbom_generator.emit_undeclared_triage(project_root)` calls
  `append_triage_item_idempotent` once per group, using
  `source="sbom"`, `kind="compliance"`, `severity="low"`,
  `dedup_key="sbom:undeclared:<manifest-rel-path>"`,
  `window_seconds=None`, `match_commit=False`.

- [ ] **AC-5** The triage `detail` lists the top-20 undeclared packages
  (sorted by name for deterministic diffs) plus a `+N more` footer when
  the manifest has >20 undeclared entries.

- [ ] **AC-6** The `launchPayload` carries a shell-style fix block:
  `cd <workspace>` (omitted when the manifest is at the repo root) →
  `npm install` (npm) or `uv sync` (python) → `cd -` → regenerate-SBOM
  command. The aggregator already fences the payload in a `text` block
  for copy-paste.

- [ ] **AC-7** A second `emit_undeclared_triage(...)` call against the
  same disk state appends zero new items (idempotent dedup via
  `window_seconds=None`).

- [ ] **AC-8** When a previously-triaged workspace no longer has
  undeclared packages, the matching `source="sbom"` item is marked
  `dismissed` with `reason="sbomResolved"` and `by="sbomGenerator"`.

- [ ] **AC-9** Operator-promoted items (`status=="promoted"`) are NOT
  auto-dismissed even when the workspace is clean (mirrors
  `audit_detector.mirror_findings_to_triage` HIGH-2 contract).

- [ ] **AC-10** `update_compliance.py --phase iterate` (and any phase
  that triggers `sbom` regeneration) calls `emit_undeclared_triage`
  after the SBOM is written. The result is echoed under
  `output["sbom_triage"]` as `{"appended": N, "dismissed": N}`. Errors
  inside the emit are caught and reported via
  `output["sbom_triage"]["error"]`, never aborting compliance updates.

## Out of scope

- **`no-venv` special-case** (Python without `uv sync` → empty deps list).
  This iterate emits the same "undeclared" group when packages resolve
  to `unknown` regardless of cause; the launchPayload already prescribes
  `uv sync` first. A separate `sbom:no-venv:<manifest>` producer is
  unnecessary — would double-count the same operator action.

- **Severity vocabulary tweaks** — fixed at `"low"` per the audience
  principle. Visible on the inbox top section but not loud. Solo dev
  pragmatism (ADR-054 audience principle).

- **Status column on the SBOM table** (`declared` /
  `resolved-from-lockfile` / …) — out of scope for B.2; the existing
  Unknown-Licenses section + the new triage card surface the operator
  action. Re-evaluating row-level annotation would touch every SBOM
  consumer (mermaid pie, copyleft check); not worth the churn.

- **Architecture-drift detector** for new manifests showing up
  unannounced — lives in C.2.

## Implementation Notes

- New helper `collect_undeclared_by_workspace` re-walks manifests
  rather than reusing the deduped `collect_dependencies` output, because
  the SBOM dedup collapses cross-workspace duplicates (right for the
  SBOM table, wrong for triage which is per-manifest).

- Triage emit uses the audit-detector lazy-import pattern
  (`_import_triage_api`) so a minimal CI without `shared/scripts/` on
  `sys.path` falls through to `{"appended": 0, "dismissed": 0}` instead
  of crashing.

- `_launch_payload` joins commands with `\n`; the aggregator handles
  fencing. Tests assert the canonical install commands
  (`npm install` / `uv sync`) are present without overspecifying
  whitespace.

- Module split: data-shaping (`collect_undeclared_by_workspace`) lives
  in `data_collector.py` next to the existing manifest walk; triage
  emission (`emit_undeclared_triage`, `_launch_payload`, `_render_detail`)
  lives in `sbom_generator.py`. Reviewer-flagged spec contradiction —
  earlier drafts mixed the boundaries; the implementation follows the
  collector-vs-emitter split.

- `_launch_payload` chains commands with `&&` (failing `cd`
  short-circuits the install) and single-quotes the workspace path
  via `_shell_quote_workspace` (defends against spaces / shell
  metacharacters in repo paths).

- The lazy-import fallback returns `{"appended": 0, "dismissed": 0,
  "error": "triage_api_unavailable"}` when `shared/scripts/` isn't on
  `sys.path` (so the regression is observable in `update_compliance.py`
  output, not silently masked).

## Verification

- `uv run --extra dev pytest plugins/shipwright-compliance/tests/test_data_collector.py
  -v` — 7 new tests on `TestCollectUndeclaredByWorkspace` cover AC-1
  through AC-3.

- `uv run --extra dev pytest plugins/shipwright-compliance/tests/test_sbom_generator.py
  -v` — 8 new tests on `TestEmitUndeclaredTriage` cover AC-4 through
  AC-9 (AC-10 covered by the existing update_compliance integration —
  smoke-verified by hand against the monorepo and is exercised end-to-
  end every time `/shipwright-iterate` runs).

- Full compliance suite: `uv run --extra dev pytest plugins/shipwright-compliance/tests/`
  — expect 366 passed (baseline 351 + 15 new).

- Full shared suite: `uv run --extra dev pytest shared/tests/` — expect
  2101 passed (baseline restored after the canon-lint allowlist fix for
  campaign files).
