# Iterate Spec — Canonical Shipwright-project predicate

- **Run ID:** `iterate-2026-06-12-canonical-project-predicate`
- **Intent:** CHANGE (refactor / consolidation)
- **Complexity:** medium (shared infra; full review + full test suite)
- **Spec Impact:** MODIFY (internal contract — no FR change)

## Problem

Multiple project-detection predicates decide the greenfield/foreign boundary
(*"is this directory a Shipwright-managed project?"*) and they use **different
marker sets**, so a tree carrying only one marker is classified inconsistently
across hooks:

| Site | Marker set | Verdict for `agent_docs/`-only tree | for `project_config`-only tree |
|---|---|---|---|
| `project_root._is_shipwright_project` (resolver gate) | 5 config files (run/project/plan/build/events) | NO | YES |
| `phase_quality._resolution.is_shipwright_project` | 5 config files **+ `.shipwright/agent_docs/`** | YES | YES |
| `track_tool_calls._is_shipwright_project` | 2 files (run, build) | NO | NO |
| `aggregate_triage_on_stop._is_shipwright_project` | 1 file (run) | NO | NO |
| `generate_handoff_on_stop` inline gate | 5 config files **+ `.shipwright/agent_docs/`** | YES | NO¹ |

¹ handoff ORs run_config / agent_docs / any-other-config, so a `project_config`-only
tree IS detected; table simplified.

**Scope note (origin/main reality):** the task's "a1-2 F7 drift guard"
(`lib/drift_anchor.py`, imported by `check_drift`) exists only as *uncommitted
WIP in the main working tree* — it is **not on origin/main**, this iterate's
base (verified: `git ls-tree`, `git ls-files`, `Glob` all find no
`drift_anchor.py`; `check_drift` imports from `lib/drift_parsers.py` and has no
project guard). So drift_anchor is **out of scope** here — there are exactly
**five** real sites on origin/main. To avoid breaking that WIP (which imports
`project_root._is_shipwright_project`), the historical private name is preserved
as a back-compat alias of the new canonical predicate.

## Goal

One canonical predicate so **every** hook agrees on the boundary. Net divergent
definitions collapse from 4 (project_root narrow / phase_quality broad /
track_tool_calls 2-marker / aggregate_triage 1-marker / handoff inline-broad) to
**one**.

## Decision — canonical = the *broad* (superset) marker set

`is_shipwright_project(path)` ⇔ `any(CONFIG_MARKERS exist) OR (.shipwright/agent_docs/ is a dir)`
where `CONFIG_MARKERS = (run, project, plan, build, events)` config files.

**Why broad, not narrow:** the agent_docs arm is a *deliberate* part of the
phase_quality + handoff gates — it covers the window between `/shipwright-project`
init and the first config write so fresh projects aren't skipped (documented in
`_resolution.is_shipwright_project`). Unifying *down* to a narrow set would
silently regress fresh-project auditing/handoff. Unifying *up* only ever makes
the narrowest consumers (`track_tool_calls` counter, `aggregate_triage` inbox
regen) fire in *more* legitimately-Shipwright trees — harmless and more correct.
All markers are `shipwright_*`-prefixed / `.shipwright/agent_docs/`, so the
foreign-tree false-positive surface is unchanged (and now identical everywhere).

**SSoT home:** `shared/scripts/lib/project_root.py` — the lowest-level resolver
module (no Shipwright deps), already the canonical root resolver and the one the
F7 guard delegates to.

### Mini-plan
1. `project_root.py`: promote a **public** `is_shipwright_project(path)` (broad)
   + a `CONFIG_MARKERS` tuple as the single marker definition. Keep
   `_is_shipwright_project` as a thin private alias (drift_anchor imports it; do
   not break the import). `resolve_project_root` calls the canonical one.
2. `phase_quality._resolution.is_shipwright_project` → **re-export** the canonical
   (drop the local impl). Remove the now-duplicate `CONFIG_MARKERS` from
   `phase_quality._constants` (internal-only; not in the package `__all__`).
3. `track_tool_calls._is_shipwright_project` → delegate to canonical (fallback
   keeps the hook import-robust).
4. `aggregate_triage_on_stop._is_shipwright_project` → delegate to canonical.
5. `generate_handoff_on_stop` inline gate → module helper delegating to canonical
   (lazy import + a fallback that mirrors the *old inline gate exactly*).
6. `project_root.py` keeps `_is_shipwright_project` as a thin alias of the public
   `is_shipwright_project` (back-compat for the WIP drift-anchor import).
7. **Resolver tie-break (added per external review):** `resolve_project_root`
   now prefers a config-bearing subdir over an `agent_docs`-only one, so a stray
   `agent_docs/` sibling can't turn a clean single-project resolution into a
   multi-candidate `ValueError`. The gate predicate stays single; only the
   resolver's candidate ranking gains a tier.
8. Tests: a **consensus matrix** proving all five predicates (+ the alias) return
   the identical verdict across the marker-combination space; fail-closed edge
   tests (agent_docs-as-file, missing path); resolver tie-break tests.

### External review disposition (OpenAI + Gemini via OpenRouter, iterate mode)
- **HIGH "widening crashes narrow consumers"** (both) → *empirically refuted*:
  `aggregate_triage` reads no config (ran clean on an agent_docs-only tree, 0
  items / exit 0); `track_tool_calls` only writes a counter; `generate_handoff`
  already fired on agent_docs-only trees. No post-gate config assumption exists.
- **MEDIUM resolver `ValueError` expansion / stray agent_docs** (both) → fixed
  via the config-preference tie-break (step 7) + regression tests.
- **MEDIUM "CONFIG_MARKERS may have hidden importers"** → grepped repo-wide;
  only `_resolution.py` imported it (now removed). Not in the package `__all__`.
- **edge cases** (fail-closed: missing path / agent_docs-as-file) → tests added.
- **REJECTED `@lru_cache`** (Gemini, low): project-root state changes mid-session
  (init writes config); caching would stale the predicate. Correctness > a few
  `stat()` calls the hooks already dwarf.

### Alternative considered (rejected)
*Keep per-site predicates but add a meta-test asserting their marker sets are
equal.* Rejected: leaves N copies of the marker logic, so the SSoT is a test
rather than the code — drift can still ship between test runs, and the
phase_quality `agent_docs` arm vs. resolver's config-only arm are genuinely
*different code*, not just different constants. Re-export/delegate removes the
divergence at the source.

## Affected Boundaries
- Internal predicate contract (no env/JSON parsing change; not `touches_io_boundary`).
- Shared infra used by every plugin's Stop/PostTool/SessionStart hook chain →
  full review + full test suite.
- `resolve_project_root` subdir-scan now also matches an `agent_docs/`-only
  immediate subdir (was config-only). Safe: agent_docs is Shipwright-specific;
  multi-candidate stays a loud `ValueError`.

## Confidence Calibration
- **Boundaries touched:** the project-detection predicate at 5 hook sites + the
  `resolve_project_root` gate. No FR, no I/O-boundary parsing change.
- **Empirical probes run:**
  - Consensus matrix (8 marker shapes × 6 predicates incl. alias): all agree →
    `test_all_predicates_agree` (16 params) PASS.
  - `aggregate_triage` on an `agent_docs`-only tree: `exit 0, 0 items` (no
    post-gate config crash — refutes the reviewers' HIGH finding empirically).
  - Forced-ImportError degraded fallbacks pinned per hook (run+build for
    track_tool_calls; broad for generate_handoff) → 2 PASS.
  - Full `shared/tests`: **3203 passed / 12 skipped**; `shared/scripts/tests`:
    **175 passed**; `ruff@0.15.15 check .`: clean; artifact-path-canon: green.
- **Test Completeness Ledger:** every behavior is `tested` (0 testable-but-untested):
  | Behavior | Disposition |
  |---|---|
  | Canonical detects each of 5 config markers | tested (matrix params run/project/plan/build/events) |
  | Canonical detects `.shipwright/agent_docs/` dir | tested (agent_docs_dir param + unit) |
  | Canonical False on empty / foreign-only tree | tested (empty, foreign_only) |
  | Fail-closed: agent_docs as a FILE → False | tested |
  | Fail-closed: missing path → False | tested |
  | Returns a genuine `bool` | tested (identity) |
  | All 5 hook sites + `_` alias agree | tested (consensus matrix) |
  | `_is_shipwright_project` alias IS the canonical fn | tested (identity) |
  | Resolver detects `agent_docs`-only subdir | tested |
  | Resolver prefers config sibling (no false ValueError) | tested |
  | Resolver: 2 config subdirs still raises | tested |
  | track_tool_calls degraded fallback = run+build | tested |
  | generate_handoff degraded fallback = broad | tested |
- **Confidence-pattern check:** *asymptote (depth)* — predicate is a pure
  function of filesystem markers, exercised across the full marker-combination
  space, fail-closed edges, AND the degraded import path. *Coverage (breadth)* —
  every consumer site is enumerated in the consensus matrix; resolver semantics
  (3 cases) covered. No "I should still test X" items remain.
