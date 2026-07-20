# Path B: CHANGE (modify existing behavior)

Same steps as FEATURE (`references/path-a-feature.md`), with these
differences:

- Step 2: see below — same ADD/MODIFY/REMOVE/NONE classification as
  FEATURE; the default for CHANGE is **MODIFY**.
- Step 6: Update existing tests to reflect new expected behavior, then
  implement.
- Step 6a: Boundary Probe applies identically — when `touches_io_boundary`
  fires, run the round-trip + 8-probe checklist before commit.
- Step 7.5: Confidence Calibration applies identically — mandatory at
  medium+, also at small with `touches_io_boundary` (see Path A
  Step 7.5).

## Step 2: Spec Update — classify the Spec Impact (always — CHANGE)

1. Identify which spec file(s) cover the affected area.
1a. **MINT-vs-FOLD gate** — identical to FEATURE Step 1a; read
   `shared/fr-authoring.md` (§3). For CHANGE the answer is almost always
   **FOLD**: modifying, completing, or polishing an existing capability is
   MODIFY on its FR, never a new row. Minting a row for a change is how a
   requirements table decays into a second changelog.
2. **Classify the spec impact** as one or more of ADD / MODIFY / REMOVE,
   or NONE — same four cases as FEATURE Step 2. For CHANGE the default
   is **MODIFY**.
   - **MODIFY** (default for CHANGE) — modifying behavior of an existing
     endpoint, page, or component: update the FR table-row description
     to reflect the new behavior + append new
     `- (E) Given … when … then …` acceptance-criteria lines covering
     the modified behavior + any backwards-compatibility / migration
     guarantees. The FR ID goes to F7 `--affected-frs`. Reference the
     run_id + ADR.
     - Keep the description **plain business language**
       (`shared/fr-authoring.md` §1) — an edit must not smuggle a file path,
       symbol, or ADR number into a row that was previously clean. The
       run_id/ADR provenance belongs in the AC line, not the description.
   - **ADD** (rare for CHANGE) — only when the modification carves out a
     genuinely new user-visible capability alongside the old one, and only
     after the gate above says MINT: append a new FR table row + an
     acceptance-criteria block; the new FR ID goes to F7 `--new-frs`.
     Number it deterministically (next free `FR-{split}.NN`, counting live
     **and** removed rows) and name it as a capability, per FEATURE Step 2.
     - **The row has seven cells:**
       `| ID | Area | Name | Priority | Description | Basis | Layers |`.
       `Basis` is ONE value from `interview` / `code` / `observed` / `tests`
       / `assumed` / `other: <reason>` — anything else, including a blank
       cell, is a hard audit failure.
     - **`Layers` can hard-abort this iterate.** A **bare** cell
       (`unit, e2e`) is a binding declaration: any named layer without an
       executed-passing `@FR`-tagged test becomes a HARD coverage failure
       and finalization exits non-zero, with no bypass. A newly added FR
       always counts as behaviour-changed in the iterate that adds it, so a
       bare cell on an FR whose tests do not exist yet **aborts the run**.
       Write the bare form only if the tests land in THIS iterate; otherwise
       write `unit, e2e (inferred)`, which is advisory and is the honest form
       when the layers have not been verified. See `shared/fr-authoring.md`
       §4a.
   - **REMOVE** — the change deletes a user-visible capability: move the
     FR row into a `### Removed Requirements` subsection with the run_id
     and the literal `status: deprecated` (never silently delete).
   - **NONE** — a behavior-preserving internal refactor: record a
     one-line justification, passed to F7 as `--spec-impact none
     --spec-impact-justification "..."`.
3. **NONE must be *justified*, not assumed.** The Phase Matrix marks this
   step `always` for CHANGE — that is load-bearing. Scope size is a
   reason the update is *small*, not a reason to skip it. The F11
   verifier (`check_spec_impact_recorded`) FAILS a feature/change
   iterate whose commit touched no `spec.md` without a recorded
   `spec_impact=none`.
4. If `shipwright_sync_config.json` exists, update mappings to reflect
   any file moves or renames.
