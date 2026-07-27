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

## The feedback file — transient scratch, two ways it arrives

`design-feedback-round{N}.md` is **transient review scratch**: the human's
per-round critique, consumed by Option B and superseded by the next round. It is
**gitignored** (canonical `.shipwright/` ignore block →
`/.shipwright/designs/design-feedback-round*.md`), so it never ships in a PR. The
*durable* design artifacts are the mockups (`screens/*.html`, `flows/*.html`), the
manifest, and `visual-guidelines.md` — those stay tracked.

The file always has the same per-screen / per-split shape (the review viewer's
`index.html` generates it — see [step-6a-review-viewer.md](step-6a-review-viewer.md)),
so Option B parses it identically regardless of how it was produced:

- **Standalone (`/shipwright-design` in a terminal):** the human opens `index.html`
  in a browser and exports the round file from the viewer's feedback panel (File
  System Access save dialog / download), then picks Option B.
- **Single-session pipeline (`mode: single_session`):** the design gate is
  `orchestrator-approve` — the phase-runner emits the mockups + the `index.html`
  review viewer and **stops** (the phase pauses). The Command Center WebUI hosts
  that emitted viewer in an isolated full-fidelity surface and, on submit, writes
  `design-feedback-round{N}.md` **straight into the worktree** (no manual export);
  a Resume action then clears the gate and this same Option-B reader applies the
  feedback. (WebUI behavior is tracked in `shipwright-webui`; the monorepo side is
  just this reader + the file convention.)

## Option A — Finalize

**FR-Coverage Gate** (verify before finalizing):
- Read the spec's Functional Requirements that have UI relevance
- Verify each UI-relevant FR has at least one screen in `.shipwright/designs/design-manifest.md`
- Verify `.shipwright/designs/visual-guidelines.md` exists and contains: Colors, Typography, Spacing
- If uncovered FRs or missing guidelines → fix before proceeding to Spec Backflow

**Requirement Write-Back Gate** (blocks Option A — non-zero exit means STOP):

```bash
uv run "{shared_root}/scripts/tools/check_design_round_declarations.py"   --project-root "$(pwd)" --run-id "{SHIPWRIGHT_SESSION_ID}"
```

Every feedback round processed in this run MUST have a requirement-impact
declaration. The checker discovers the rounds from the
`design-feedback-round{N}.md` files this phase consumed (or pass `--round` per
scope explicitly) and looks each one up by **this** run id — a declaration
recorded under a different run does **not** count, so a `round-1` from an earlier
design run can never satisfy this one.

| Exit | Meaning |
|---|---|
| `0` | every round declared (or there were no feedback rounds at all) |
| `1` | `undeclared` lists the silent rounds — go back and run Option B step 7 for each |
| `2` | a declaration file is damaged — repair it; this is NOT the same as missing |

Deciding a round was appearance-only is a fine answer; saying nothing is not. A
design phase is not complete while a round is silent about what it did to the
requirements.

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
uv run "{plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py" \
  update-step --project-root "$(pwd)" --step design --status complete

# Update delivery dashboard
uv run "{shared_root}/scripts/tools/update_build_dashboard.py" \
  --project-root "$(pwd)" --phase design --session-id "{SHIPWRIGHT_SESSION_ID}"

# Record phase completion event (idempotent — skips if already recorded)
uv run "{shared_root}/scripts/tools/record_event.py" \
  --project-root "$(pwd)" --type phase_completed --phase design \
  --detail "{N} screens, {M} flows"
```
Where `{shared_root}` = `{plugin_root}/../../shared`.

4. Print completion message with next step (`/shipwright-plan`)

## Option B — Process Feedback

1. Find the latest `.shipwright/designs/design-feedback-round*.md` file (highest round number)

   **Snapshot this round's requirement baseline FIRST — before revising anything:**

   ```bash
   uv run "{shared_root}/scripts/tools/record_requirement_impact.py"      --project-root "$(pwd)" --run-id "{SHIPWRIGHT_SESSION_ID}"      --phase design --scope "round-{N}" --snapshot-baseline
   ```

   This is what makes "the requirement was corrected **by this round**"
   checkable. A build section gets that boundary from its commit; a design round
   has none, so it captures one. It is also the round registry the Option-A gate
   reads — a round that snapshots cannot then be invisible to finalization.

2. Parse it: identify screens with status **CHANGES** or **REJECTED**
3. Identify **global changes** (changes that affect multiple screens — e.g. color shifts, icon style changes, nav label renames). Apply these to ALL screens, not just flagged ones.
4. Revise only flagged screens — use the snippet assembly process from Step 4
5. **Behaviour-vs-appearance read (per round — REQUIRED).** Before backflow, go
   through this round's feedback and decide, item by item, whether it changed
   **what a screen or flow does** or only **how it looks**. Behaviour is: a step
   added or removed, an option introduced, a path through the product reordered,
   a rule about when something appears or is allowed. Appearance is: colour,
   spacing, type, iconography, copy tone, layout that leaves the same steps in
   the same order.

   > This judgement is a **human read** and has no deterministic check — that is
   > why it is stated as a rule rather than a script. What *is* checked is that
   > you declared an answer (Step 7) and that a behaviour answer actually reached
   > the requirement.

6. **Spec Backflow (partial)**:

   | Artifact | What to update | Condition |
   |----------|---------------|-----------|
   | `.shipwright/planning/*/spec.md` Section 5 (Functional Requirements) | **Substance** — correct the FR's description and acceptance criteria to say what the flow now does. Append `- (E) Given … when … then …` lines for behaviour this round introduced, and correct any AC the round contradicted | **If Step 5 found behaviour changes** |
   | `.shipwright/designs/visual-guidelines.md` | Color values, token changes | If global design changes were made |
   | `.shipwright/designs/design-manifest.md` | Screen titles (if renamed), status → `revised-rN` | Always |
   | `.shipwright/designs/index.html` | Regenerate screens array with updated data | Always |
   | `.shipwright/agent_docs/decision_log.md` | New design decisions (DR-NNN format) | If non-trivial decisions |

   > **This is the row that did not exist.** Backflow historically wrote back
   > *pointers* only — which screen stands for which requirement, and
   > cross-reference tags. Nothing wrote back substance, so a round that added an
   > option or reordered a path left the requirement describing the older intent.
   > Design is where flows are rightly rethought; what is learned here has to
   > reach the requirements instead of living only in the mockup.

7. **Declare the round's requirement impact (REQUIRED — blocks Option A):**

   ```bash
   # behaviour changed → the requirement was corrected in step 6
   uv run "{shared_root}/scripts/tools/record_requirement_impact.py" \
     --project-root "$(pwd)" --run-id "{SHIPWRIGHT_SESSION_ID}" \
     --phase design --scope "round-{N}" \
     --impact modify --fr FR-XX.YY --worktree

   # appearance only → one line saying so
   uv run "{shared_root}/scripts/tools/record_requirement_impact.py" \
     --project-root "$(pwd)" --run-id "{SHIPWRIGHT_SESSION_ID}" \
     --phase design --scope "round-{N}" \
     --impact none --reason "{one line: what the round changed, and why it is appearance}" \
     --worktree
   ```

   The command compares against **this round's baseline** (step 1), so an
   `add`/`modify`/`remove` declaration is refused unless a
   `.shipwright/planning/**/spec.md` genuinely differs from what it said when
   the round started; `none` is refused without a reason. **Read the printed
   `error` key** rather than assuming what a non-zero exit means:

   | `error` | What to do |
   |---|---|
   | `requirement_impact_no_spec_touched` | The write-back in step 6 did not actually happen. Correct the requirement — do not re-word the declaration. |
   | `requirement_impact_none_requires_reason` | Add a one-line `--reason`. |
   | `requirement_impact_requires_fr` / `_malformed_fr` | Name the real FR id(s). |
   | `requirement_impact_evidence_unusable` | The comparison boundary was wrong (bad ref, or `--worktree` combined with a range). |
   | `requirement_impact_no_baseline` | Step 1's snapshot was skipped — take it, then re-declare. |

   > **Why the baseline matters.** Without it the check was satisfiable for free.
   > Nothing in the pipeline commits before the build phase, so every `spec.md`
   > the project phase wrote is untracked — a plain "what is uncommitted?" diff
   > lists them all, and *any* `modify` passed on a spec nobody had edited.

8. Print review instructions again (same banner as Step 8)
9. → **Loop back** to the AskUserQuestion (same 3 options)

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
  │        Snapshot this round's requirement baseline
  │        Revise CHANGES/REJECTED screens
  │        Behaviour-vs-appearance read
  │        Spec Backflow (partial) — incl. FR SUBSTANCE when behaviour changed
  │        Declare the round's requirement impact
  │        Regenerate index.html
  │        Print review instructions
  │        → AskUserQuestion again (loop)
  │
  ├─[A]─→ FR-Coverage Gate + Requirement Write-Back Gate
  │        Spec Backflow (full)
  │        Write session handoff
  │        → Done, ready for /shipwright-plan
  │
  └─[C]─→ Print state summary → End
```
