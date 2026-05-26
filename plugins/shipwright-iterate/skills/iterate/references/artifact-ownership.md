# Artifact Ownership

| Artifact | Owns | Do NOT duplicate here |
|---|---|---|
| **Iterate spec** (`.shipwright/planning/iterate/`) | Intent, ACs, scope, out-of-scope, Spec-Impact classification | Rationale (→ ADR), structure (→ architecture) |
| **spec.md** (FR table + `## Removed Requirements`) | Normative FR changes — ADD/MODIFY in the FR table, REMOVE into the Removed Requirements section | Why (→ ADR), approach (→ mini-plan) |
| **`shipwright_events.jsonl`** (F7 event) | Machine-of-record `spec_impact` classification (enforced by `check_spec_impact_recorded`) | Narrative (→ ADR), FR text (→ spec) |
| **ADR** (`decision_log.md`) | Rationale, alternatives, consequences | Full ACs (→ spec), structure (→ architecture) |
| **architecture.md** | Current structural state | Decisions (→ ADR), requirements (→ spec) |
| **Mini-plan** (`.shipwright/planning/iterate/`) | Approach, files, test strategy | Requirements (→ spec), decisions (→ ADR) |
