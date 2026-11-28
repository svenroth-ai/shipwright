# Capability column next to D7, and intent.md as the second human-owned file

Run-ID: iterate-2026-11-28-u0-terms-format (campaign intent-pyramid, unit U0)

## Decision
1. The FR table gets a stored `Capability` column (CAP id, AI-assigned) next to `Area` (D7). `Area` is rendered from the FR id's group digit and only groups the table by split; `Capability` is product-level, cannot be derived, and works across splits. U0 fixes the vocabulary and the format only; the column itself is U1a.
2. `.shipwright/planning/intent.md` is the second human-owned file under `.shipwright/` (after `.shipwright/profiles/`). Option D (a human section inside the AI-written spec.md) was rejected: ownership must be checkable per file path. Option C (JSON/YAML rendered to markdown) was rejected: a second representation to drift.
3. An FR is one function; a Capability groups FRs. Format: `shared/schemas/intent.schema.json`, no upper limits on counts or length.

## Known properties
- The FR -> CAP mapping is AI-owned: the AI can move an FR between confirmed capabilities without a human question. The human accepts capabilities, not FRs.
- Confirmation is tamper-evident, not tamper-proof (constitution NEVER, never-intent-self-confirm). Until U2a1 elements stay `assumption`.
- Operator decision 2026-11-28 (Stop-1 follow-up): the rule moved from ASK FIRST to NEVER, because a yes in chat must not license it; an agent may still draft `assumption` elements and apply an edit the human gave in the recorded flow.
- "Intent" now names two things (product intent vs. the iterate change kind); disambiguated in the glossary, raised for Stop 1.
- The scope-check tool still prints "capability test" (pinned by tests); prose names it as the FR-is-one-function test. Audit titles I3/I10 in group_i.py still say "capability": follow-up.

## Architecture Review
External (GLM, OpenAI): approve / approve. Internal (architecture-internal-reviewer, opus): approve with medium findings (parser-vs-schema contradiction: reference parser in the test only, real parser U1b; confirmation evidence named outside intent.md; id lifecycle; missing file = no intent). All worked in.

## Internal Plan Review (opus-plan-reviewer)
High: incomplete FR-is-capability sweep (fixed across fr-authoring, step-6, spec-generation, path-a/b, SKILL); Area wording vs Capability column (fixed); Intent term collision (disambiguation added, Stop-1 question). Medium: capability name added to the format, several INT elements allowed, element rules aligned with the brief, constitution wording names the agent as likely forger, FR-id regex widened. Deferred: group_i audit titles, normative format doc (U1b).

## External-Plan-Review-Findings
| Finding | Disposition |
|---|---|
| Define confirmed/assumption and what carries status (openai) | accepted-and-fixed (glossary Element) |
| How markdown fixture reaches the schema (openai) | accepted-and-fixed (test reference parser + schema description) |
| No FR ids in text unverified (openai) | rejected-with-reason: brief section 3 ownership rule |
| Register entry vs drift test (glm) | accepted-and-fixed (enforcement "unimplemented"; drift test green) |

## Self-Review
1. Spec compliance: pass, six scope items present. 2. Error handling: pass, schema rejects malformed input. 3. Security basics: pass, no secrets; constitution names residual risk. 4. Test quality: pass, sample plus malformed plus no-limit plus structural cases. 5. Performance: pass, nothing runtime. 6. Naming and structure: pass. 7. Affected boundaries: pass, the md-to-schema round trip is probed by test_intent_schema.py.

## Confidence Calibration
Boundary: intent.md -> parsed shape -> schema. Probes: sample validates; malformed rejected (status, id, FR id, missing name); 59 capabilities with 5000-char text validate (no upper limits). Not probed: CRLF and BOM in intent.md (parser is U1b; named there).

## External-Code-Review-Findings
| Finding | Disposition |
|---|---|
| No ADR drop in the diff (glm, openai) | rejected-with-reason: review diff excluded .shipwright; the drop exists |
| Capability name accepts colon and FR id (openai) | accepted-and-fixed (schema + tests) |
| FR-id pattern rejects `FR4` (openai, glm) | accepted-and-fixed: only FR-nn.nn matches |
| Capability column described as live in prose (openai) | accepted-and-fixed: marked as intent-pyramid U1a |
| Malformed test asserts loosely (glm) | accepted-and-fixed: per-path, per-rule assertions |
| Date 2026-11-28 vs 29 (glm) | rejected-with-reason: brief rev 9/10 dates it 2026-11-28 |

## Spec / Code / Doubt review (opus)
Spec: round 1 REJECT (leftover FR-is-capability wording in split-heuristics, adopt step-b8, brief-mode, design upload-mode), fixed; round 2 PASS. Code: no high; fixed requirement-elicitation.md sweep, regex dialect (newline, whitespace, ids of other elements), strict reference parser, CLAUDE.md citation. Doubt: fixed glossary present-tense claims, constitution wording ("a free-form yes is not a confirmation"), schema/brief section 3 link rule, product text rules, id uniqueness stated for U1b.
Deferred (tool strings keep the older word, named in fr-authoring section 2; follow-up): fr_scope_check prompt; brief_project_mode / brief_design_plan messages; record-non-ui-frs ADR title; audit titles I3/I10; chat-map.json key "capabilities"; spec.md AC wording (FR-01.02 AC02/AC03 and the other FR-level uses of "capability"), reworded in a later spec_impact:modify iterate; reference parser hardening (ValueError on missing front matter or unknown section, section order, duplicates, move into lib/intent_parser.py) in U1b; the stale section 5.4 quotation in shared/scripts/lib/fr_hygiene_detectors.py:24; residual "capability" wording in docs/building-skills-plugins-agents.md, fr_scope_check.py, group_i.py and fr_clusters.py.
