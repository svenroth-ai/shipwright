# Design Review Loop

**Goal:** Wait for the user's review, then process feedback or finalize.

Present an `AskUserQuestion` dialog that stays open while the user reviews in the browser:

```
AskUserQuestion:
  question: |
    Take your time reviewing in the browser. When you're done, choose:
  options:
    A) All screens approved — finalize design phase
       → Updates specs & decisions, writes session handoff, ready for /shipwright-plan
    B) Feedback ready — I've reviewed and exported the feedback file
       → Reads .shipwright/designs/design-feedback-roundN.md, revises flagged screens, then asks again
    C) Pause for now
       → State is saved, continue later with /shipwright-design
```

## Option A — Finalize

**FR-Coverage Gate** (verify before finalizing):
- Read the spec's Functional Requirements that have UI relevance
- Verify each UI-relevant FR has at least one screen in `.shipwright/designs/design-manifest.md`
- Verify `.shipwright/designs/visual-guidelines.md` exists and contains: Colors, Typography, Spacing
- If uncovered FRs or missing guidelines → fix before proceeding to Spec Backflow

1. **Spec Backflow (full)**:

   | Artifact | What to update |
   |----------|---------------|
   | `.shipwright/designs/visual-guidelines.md` | Final color values, token changes |
   | `.shipwright/designs/design-manifest.md` | Final screen titles, statuses |
   | `.shipwright/designs/index.html` | Regenerate screens array |
   | `.shipwright/planning/*/spec.md` Section 7 (UI Requirements) | Add screen references per FR: "FR-01.09 → screens/03-dashboard.html" |
   | `.shipwright/planning/*/spec.md` Section 5 (Functional Requirements) | Add `[UI: Screen #NN]` cross-reference tags to FRs that have mockups |
   | `.shipwright/agent_docs/decision_log.md` | All final design decisions (DR-NNN format, see below) |
   | `shipwright_project_config.json` | Set `design_phase: "complete"` |

2. **Write session handoff** to `.shipwright/designs/design-handoff.md`:

   ```markdown
   # Design Phase — Session Handoff

   > Completed: {date}
   > Rounds: {N}
   > Screens: {total} ({approved} approved, {revised} revised)

   ## Status
   All screens approved. Ready for implementation planning.

   ## Key Design Decisions
   {List of DR-NNN decisions made during design phase}

   ## Files for Implementation
   - Visual system: `.shipwright/designs/visual-guidelines.md`
   - Screen registry: `.shipwright/designs/design-manifest.md`
   - Screen mockups: `.shipwright/designs/screens/*.html`
   - User flows: `.shipwright/designs/flows/*.html`

   ## Notes for /shipwright-plan
   {Any implementation-relevant notes from feedback, e.g.
   "Sidebar CTA must be purchase-aware — hide when user has active Masterclass"}
   ```

3. **Phase complete — update pipeline state:**
```bash
# Mark design phase complete (triggers compliance update automatically)
uv run {plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py \
  update-step --project-root "$(pwd)" --step design --status complete

# Update delivery dashboard
uv run {shared_root}/scripts/tools/update_build_dashboard.py \
  --project-root "$(pwd)" --phase design --session-id "{SHIPWRIGHT_SESSION_ID}"

# Record phase completion event (idempotent — skips if already recorded)
uv run {shared_root}/scripts/tools/record_event.py \
  --project-root "$(pwd)" --type phase_completed --phase design \
  --detail "{N} screens, {M} flows"
```
Where `{shared_root}` = `{plugin_root}/../../shared`.

4. Print completion message with next step (`/shipwright-plan`)

## Option B — Process Feedback

1. Find the latest `.shipwright/designs/design-feedback-round*.md` file (highest round number)
2. Parse it: identify screens with status **CHANGES** or **REJECTED**
3. Identify **global changes** (changes that affect multiple screens — e.g. color shifts, icon style changes, nav label renames). Apply these to ALL screens, not just flagged ones.
4. Revise only flagged screens — use the snippet assembly process from Step 4
5. **Spec Backflow (partial)**:

   | Artifact | What to update | Condition |
   |----------|---------------|-----------|
   | `.shipwright/designs/visual-guidelines.md` | Color values, token changes | If global design changes were made |
   | `.shipwright/designs/design-manifest.md` | Screen titles (if renamed), status → `revised-rN` | Always |
   | `.shipwright/designs/index.html` | Regenerate screens array with updated data | Always |
   | `.shipwright/agent_docs/decision_log.md` | New design decisions (DR-NNN format) | If non-trivial decisions |

6. Print review instructions again (same banner as Step 8)
7. → **Loop back** to the AskUserQuestion (same 3 options)

## Option C — Pause

1. Print current state summary (N screens, N approved, guidelines saved)
2. End — user can resume later with `/shipwright-design`

## Decision Log Format

Design decisions are logged to `.shipwright/agent_docs/decision_log.md` using this format:

```markdown
### DR-{NNN}: {Title}

**Date:** {date}
**Source:** Design Round {N} feedback
**Decision:** {What was decided}
**Rationale:** {Why — user feedback, UX reason, brand requirement}
**Impact:** {What changed — screens, colors, patterns}
```

## Complete Flow Diagram

```
/shipwright-design
  │
  ├── Generate/revise screens + index.html
  ├── Print review instructions
  ├── AskUserQuestion (A/B/C) ← dialog stays open
  │
  │   [User reviews in browser meanwhile]
  │   [User exports feedback to .shipwright/designs/]
  │
  ├─[B]─→ Read feedback file
  │        Revise CHANGES/REJECTED screens
  │        Spec Backflow (partial)
  │        Regenerate index.html
  │        Print review instructions
  │        → AskUserQuestion again (loop)
  │
  ├─[A]─→ Spec Backflow (full)
  │        Write session handoff
  │        → Done, ready for /shipwright-plan
  │
  └─[C]─→ Print state summary → End
```
