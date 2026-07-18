# Step B.8 — Semantic Enrichment (Layer 2, inline)

Read `.shipwright/adopt/snapshot.json` and (if present)
`.shipwright/adopt/routes.json`. Read **sample files** for context:

- `README.md` at the project root
- 3–5 top-level route files (sorted by LOC; from `features[].source_file`)
- 2–3 key domain files (from `folder_layers` with name `domain` or `core`)
- Top-5 commit bodies for `git.major_refactor_commits[].sha` via
  `git show --stat <sha>`
- A handful of screenshots from `.shipwright/adopt/screenshots/` if Step
  B.5 produced any

Write a **strict JSON object** to `.shipwright/adopt/enrichment.json`:

```json
{
  "product_description": "2–3 paragraphs explaining the product functionally.",
  "features": [
    {
      "route": "/dashboard",
      "label": "Active-project dashboard",
      "description": "User views current active Shipwright projects...",
      "acceptance_draft": "Given the user is logged in, when they land on /dashboard, then..."
    }
  ],
  "architecture_prose": "Data-flow narrative — Layers -> interactions -> external systems.",
  "architecture_diagram": "```\n  <ASCII box drawing>\n```",
  "conventions_prose": "Human-readable rules distilled from linter configs + code sampling.",
  "adrs": [
    {
      "commit_sha": "abc123",
      "context": "...",
      "decision": "...",
      "consequences": "..."
    }
  ]
}
```

**Quality leitplanken** (respect these in the inline enrichment):

- **`label` + `description` follow `shared/fr-authoring.md`** — they become the
  Name and Description of an FR, so they are **plain business language**: what
  the capability does and what it guarantees, in words a product owner
  understands. No file paths, ADR numbers, HTTP verbs, or code symbols in
  either field — the route belongs in the `route` field and the file in
  `Source`, not in the prose. Read that document before writing enrichment.
  - ❌ `"label": "Pending tool_use list (GET)"`,
    `"description": "Walks unmatched tool_use ids in the JSONL."`
  - ✅ `"label": "Pending questions"`,
    `"description": "Shows every question the assistant is waiting on, so no session sits blocked unnoticed."`
- **Code > Prose**: if README contradicts the actual folder structure, the code
  wins. Derive the capability from what the code actually *does* — then state
  that capability in business language, not as a description of the code.
- **Don't invent.** If unclear, write `"TBD"` — the Layer-3 review and
  `/shipwright-iterate` will refine.
- **No marketing copy, and no implementation dump either.** Sober and concrete,
  IREB-compatible — but readable by a non-engineer. Never drop a behavioural
  guarantee to sound plainer.
- **ASCII box diagram style**: match the existing convention used in
  `webui/.shipwright/agent_docs/architecture.md` — plain ASCII box-drawing characters
  (`┌`, `─`, `│`, `└`), no Mermaid. Size: roughly 40–60 lines.

**Validation + fallback** (4.4). `generate_adoption_artifacts.py` validates
`enrichment.json` against a strict schema before consuming it. If the file
exists but is malformed (missing required keys, wrong types, missing
`route` on a feature, missing `decision`/`consequences` on an ADR), Step E
fails loud with a clear error — adopt does NOT silently fall back to
"snapshot+routes only" when Layer-2 was attempted.

If `enrichment.json` does not exist at all, a deterministic minimal
fallback is generated from the snapshot + routes. Every text field is
clearly labeled as a placeholder ("TBD — Layer-2 enrichment skipped..."),
the file carries `_fallback: true`, and the SKILL.md handoff surfaces a
loud "Layer-2 was skipped" notice. No invented prose, no plausible-sounding
lies.
