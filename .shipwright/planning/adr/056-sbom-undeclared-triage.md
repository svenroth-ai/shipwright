# ADR-056 — SBOM undeclared-license triage (B.2)

> Long-form spec backing the iterate-2026-05-21-b2-sbom-polish ADR drop.
> The drop's `--spec-ref` points here so future readers don't have to
> reconstruct the design rationale from commits.

## Audience principle

Same as ADR-054 / ADR-055: solo dev today, leadwright Phase 3 tomorrow.
Quiet inbox by default; loud only when an operator action exists. For
SBOM that means: **one card per workspace, not one per package**. A
monorepo with 500 deps and no `node_modules` produces one card with a
top-20 + `+N more` body, not 500 cards.

## What landed in B.2 vs forward-looking

| Decision | Realized in this iterate? | Realized where |
|----------|---------------------------|----------------|
| D1 Per-workspace triage emit            | **Yes** | B.2 (this PR)            |
| D2 Top-20 + `+N more` body              | **Yes** | B.2                      |
| D3 `launchPayload` install + regen      | **Yes** | B.2                      |
| D4 Auto-resolve when workspace clean    | **Yes** | B.2                      |
| D5 Promoted-item retention              | **Yes** | B.2                      |
| D6 Severity default = `low`             | **Yes** | B.2                      |
| D7 Source = `sbom` (open vocab)         | **Yes** | B.2                      |
| 7-day stale-dismiss (ADR-054 D4)        | No — out of scope | Reviewed; deferred (see below) |

## Decisions (B.2)

### D1. One triage item per workspace/manifest

Closes ADR-054 D1. Each manifest with ≥1 undeclared package emits a
single `source="sbom"`, `kind="compliance"`, `severity="low"` item. The
dedup-key encodes the manifest's repo-relative POSIX path:

    sbom:undeclared:<manifest_rel_path>

Examples:

    sbom:undeclared:package.json
    sbom:undeclared:client/package.json
    sbom:undeclared:server/pyproject.toml

Rejected alternatives — same as ADR-054 D1:

- *1 global item* — a JS workspace's fix command (`npm install`) differs
  from a Python workspace's (`uv sync`); a single payload muddies both.
- *1 item per package* — drowning noise; solo dev fixes in batches.

### D2. Body shows top-20 packages + `+N more` footer

Mirrors the cap used by phase-quality (top-10) and audit producers. The
detail line:

> N package(s) without a resolvable license. Top 20: pkg-a@v, pkg-b@v, … (+M more)

Sorted by name for deterministic output (review-friendly diffs).

20 is enough that the operator usually sees the full set (most
workspaces in the wild have <20 undeclared after lockfile resolution),
but capped tightly enough that a pathological 500-dep monorepo doesn't
bloat the inbox.

### D3. `launchPayload` carries the fix block

The aggregator already fences a payload in a copy-pasteable `text`
block (ADR-053 / iterate-2026-05-20-triage-launch-surface). For SBOM:

```
cd <workspace>
npm install            # or `uv sync` for python
cd -
# regenerate SBOM so the triage item auto-resolves:
uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py --project-root . --phase iterate
```

For root-level manifests (`manifest_rel_path == "package.json"` or
`"pyproject.toml"`) the `cd` step is omitted — the operator is already
at the right place.

### D4. Auto-resolve when workspace runs clean

Symmetric with `audit_detector.mirror_findings_to_triage`. After each
`emit_undeclared_triage` run, every currently-`triage` item whose
`dedupKey` starts with `sbom:undeclared:` and is **not** in this run's
set of dirty workspaces is marked:

- `status = dismissed`
- `by = "sbomGenerator"`
- `reason = "sbomResolved"`

Operator never has to manually flip the card when they finally run
`uv sync` — re-running the compliance update clears it automatically.

### D5. Promoted / dismissed items stay terminal

Audit-detector HIGH-2 contract: auto-dismiss applies **only** to items
still in `triage`. If the operator promoted the SBOM card to the
backlog or manually dismissed it, the next clean run leaves the
terminal status untouched. The card came back via a new ID if the
workspace dirties again.

### D6. Severity default = `low`

Visible on the inbox top section (per ADR-054 D6 / ADR-055 D5, only
`info` collapses into the `<details>` block) but not loud. Unknown
licenses are a pre-launch polish concern, not a release blocker. The
existing `Copyleft risk` indicator on the dashboard remains the
escalation surface for actual copyleft hits.

### D7. Source = `sbom` (open vocabulary)

`shared/scripts/triage.py:KNOWN_SOURCES` documents the well-known set
but explicitly states `source` is free-form. SBOM uses a new value;
`suggest_domain_from_source` falls through to `engineering` (default)
which is correct for SBOM hygiene — the operator triages it like any
other engineering polish item.

## What this iterate does NOT do

- **7-day stale-dismiss** (ADR-054 D4) — the contract is set, but the
  generic implementation lives one level up: an aggregator-side sweep,
  not a per-producer feature. Producers shouldn't all re-implement
  stale-checking. Deferred until a generic stale-sweeper lands (likely
  a separate iterate after C.3).

- **`no-venv` special-case item** — the plan mentioned a separate
  `sbom:no-venv:<manifest>` triage for Python projects where
  `importlib.metadata` returns `unknown` because the venv isn't
  populated. Conflated with regular `undeclared`: same launchPayload
  (`uv sync`), same dedup-key shape, would double-count the same
  operator action. One card per workspace covers both cases.

- **Status column on the SBOM table** (`declared` /
  `resolved-from-lockfile` / `resolved-from-installed` /
  `undeclared`) — would touch every SBOM consumer (mermaid pie,
  copyleft check, unknown-section render). The new triage card +
  existing Unknown-Licenses section already surface the operator action.
  Skipped per the audience principle (quieter wins).

## Consequences

- The compliance run on the shipwright monorepo (and any project) emits
  one `source="sbom"` card per dirty workspace after each `iterate`
  phase. Existing Compliance dashboard's `Copyleft risk` indicator is
  unchanged (it tracks real copyleft licenses, not undeclared).

- ADR-054 D1 / D5 are now realized end-to-end on the producer side.
  RTM-side rendering of FAIL → triage links (D5 consumer) lands in B.4.

- The `update_compliance.py` JSON output now includes a `sbom_triage`
  key when the phase touches SBOM. Existing callers that ignore unknown
  keys (the orchestrator + the audit adapter) are unaffected.

## Rejected (kept for future me)

- **Per-package items** — drowning noise; ADR-054 D1 already rejected.
- **Severity `info`** — would collapse into the `<details>` block;
  defeats the launch-surface purpose.
- **Embed install command inline in the SBOM table** — every row would
  carry a redundant `Run uv sync` cell; bloated and undiff-able.
- **Cap at 10 instead of 20** — too aggressive given a real monorepo
  routinely has 15+ undeclared on first scan.

## External-Review-Findings

OpenRouter cascade ran 2026-05-21 (Gemini + OpenAI on the iterate spec).
12 findings total (Gemini 4 / OpenAI 8). High/medium findings addressed
inline before commit:

| # | Source | Severity | Finding | Disposition |
|---|--------|----------|---------|-------------|
| 1 | Gemini | HIGH   | `launchPayload` used unchained `cd\nnpm install` — a failing `cd` would silently install in repo root. | accepted-and-fixed — chained with `&&` in `_launch_payload`; test `test_one_item_per_workspace` asserts `&&` is present. |
| 2 | Gemini | MEDIUM | Auto-dismiss could leave orphan items if a workspace was deleted. | rejected-with-reason — current `read_all_items + filter dedupKey ∉ current_keys` flow already catches deletion (deleted workspace produces no group → key not in `current_keys` → item dismissed). Existing `test_auto_resolve_when_workspace_clean` exercises the path. |
| 3 | Gemini | MEDIUM | Shell-metacharacter injection via workspace path. | accepted-and-fixed — `_shell_quote_workspace` single-quotes the path; `test_launch_payload_quotes_paths_with_spaces` covers `my app`. |
| 4 | Gemini | LOW    | Drift risk between two manifest-walk routines. | rejected-with-reason — both use the same `_find_manifests` helper; the new collector adds only license-resolution + per-manifest grouping. Shared traversal eliminates the duplicate-walk concern. |
| 5 | OpenAI | MEDIUM | Spec contradiction: collector said `data_collector` in AC-1 but `sbom_generator` in notes. | accepted-and-fixed — spec note rewritten; implementation matches AC-1 (collector in `data_collector.py`). |
| 6 | OpenAI | MEDIUM | Drift risk; share `_find_manifests`. | accepted-and-already-correct — `collect_undeclared_by_workspace` reuses `_find_manifests` (same path that `collect_dependencies` uses). |
| 7 | OpenAI | MEDIUM | Windows path-separator normalization for dedup keys. | accepted-and-already-correct — `manifest_rel_path` goes through `.as_posix()` at the single boundary in the collector; `test_uses_forward_slash_paths_on_all_platforms` asserts no `\`. |
| 8 | OpenAI | MEDIUM | Shell-quote payload paths (duplicate of Gemini #3). | accepted-and-fixed — same fix. |
| 9 | OpenAI | MEDIUM | Same as #8 (security framing). | accepted-and-fixed — same fix. |
| 10 | OpenAI | MEDIUM | Sort tie-break for same name + different versions. | accepted-and-fixed — sort key is `(name, version)`; `test_detail_sort_stable_for_duplicate_names` covers it. |
| 11 | OpenAI | MEDIUM | Auto-dismiss must filter to `source="sbom"` only. | accepted-and-already-correct — emit_undeclared_triage skips non-sbom items + checks the `sbom:undeclared:` prefix; `test_emit_does_not_touch_non_sbom_items` covers it. |
| 12 | OpenAI | LOW    | `cd -` ordering before regenerate. | accepted-and-already-correct — `_launch_payload` returns `cd workspace && install && cd - && regen`; `test_launch_payload_for_python_workspace` asserts `cd -` precedes `update_compliance.py`. |
| 13 | OpenAI | MEDIUM | Wire emit at the single post-SBOM hook (cover non-iterate phases). | accepted-and-already-correct — emit lives in `update_compliance.py` inside the `if report_name == "sbom"` branch, which is the shared post-SBOM hook for every phase whose `PHASE_REPORTS` entry includes `sbom` (`build`, `changelog`, `iterate`). |
| 14 | OpenAI | LOW    | Lazy-import fallback masks regression. | accepted-and-fixed — fallback now returns `{"error": "triage_api_unavailable"}`; test `test_one_item_per_workspace` asserts no `error` key in normal runs. |
| 15 | OpenAI | MEDIUM | Python no-venv may yield empty deps → no triage. | accepted-and-already-correct — `_parse_pyproject_deps` reads the manifest, not the venv; license resolution via `importlib.metadata` returns `unknown` for non-installed packages, which is exactly the undeclared case. `test_python_no_venv_still_emits` covers it. |
| 16 | OpenAI | LOW    | `data_collector` vs `sbom_generator` boundary. | accepted-and-fixed — same as #5. |

## External-Code-Review-Findings

OpenRouter cascade ran 2026-05-21 on the staged diff. 3 findings (OpenAI;
Gemini's response was truncated). High/medium addressed inline.

| # | Source | Severity | Finding | Disposition |
|---|--------|----------|---------|-------------|
| 1 | OpenAI | MEDIUM | `collect_undeclared_by_workspace` calls `.items()` on `pkg.get(section)` without verifying it's a dict — a malformed `package.json` would `AttributeError` and abort the sweep. | accepted-and-fixed — added `isinstance(section_deps, dict)` guard at the section boundary; `test_non_dict_dependencies_section_is_skipped` covers it. |
| 2 | OpenAI | MEDIUM | `emit_undeclared_triage` swallowed append/dismiss exceptions but didn't surface them via the `error` key — violated AC-10's "errors must be reported" contract. | accepted-and-fixed — both `except` branches now accumulate `{phase}:{rel-or-id}:{exc_type}` entries; the result dict gets an `error` key joining them; `test_emit_reports_append_errors` covers it. |
| 3 | OpenAI | LOW    | `triage_api` fixture uses `parents[3]` while production uses `parents[4]` — different counts. | rejected-with-reason — both expressions resolve to the same `repo_root/shared/scripts` directory because they start from different `__file__` ancestry (`test_sbom_generator.py` is one level deeper than `sbom_generator.py`). Tests pass deterministically; no functional gap. |
| 4 | Gemini | (truncated) | Response cut mid-sentence about `Path("")` vs `Path(".")` equality. | rejected-with-reason — the existing comparison works (`Path("") == Path(".")` in CPython, so `parent != Path("")` is True iff parent is a real subdir); `test_root_manifest_omits_cd` + `test_launch_payload_for_python_workspace` cover both branches. Response inconclusive enough that no action is implied. |

## See also

- Iterate spec: `.shipwright/planning/iterate/2026-05-21-b2-sbom-polish.md`
- Triage producer contract: `.shipwright/planning/adr/054-triage-producer-contract.md` (D1, D5, D6)
- Compliance dashboard mode-aware: `.shipwright/planning/adr/055-compliance-dashboard-mode-aware.md` (D5 — Triage open indicator)
- Generator: `plugins/shipwright-compliance/scripts/lib/sbom_generator.py` (`emit_undeclared_triage`)
- Collector: `plugins/shipwright-compliance/scripts/lib/data_collector.py` (`collect_undeclared_by_workspace`)
- Orchestrator: `plugins/shipwright-compliance/scripts/tools/update_compliance.py`
- Triage API: `shared/scripts/triage.py` (`append_triage_item_idempotent`)
- Earlier ADRs: ADR-046 (Triage Inbox), ADR-052 (action-units), ADR-053 (launch-surface), ADR-054 (B0), ADR-055 (B.1).
