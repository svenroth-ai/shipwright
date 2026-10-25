# Wizard brief keeps the stack profile it names

Run: iterate-2026-10-25-b2b-wizard-brief-explicit-profile (campaign brief-driven-run-b-intake-design-e2e, unit B2b).

## Brief contract finding (verified, not guessed)
- **Producer:** shipwright-webui `client/src/components/wizard/IntentWizard/contract.ts`, `composeNewBrief`. It writes ONE prose line, `<idea> (Intake - Users: ..; Saves data: ..; Runs: ..; Stack profile: <name>; ...)`, as the launch description. The profile is the WebUI's own mapping (`supabase-nextjs` when it saves data, else `vite-hono`); adopt launches carry no profile item.
- **Consumer before this change:** `shared/scripts/lib/brief_intake.py` parsed no key from that line (description only) and never read a `profile` field; the profile came only from `persistence`, so a named profile was lost. The documented "JSON object shape" in `references/brief-intake.md` is what a future or hand-written brief may send; the WebUI does not write it today.
- **Version:** the file/wizard route has no brief version (the package route carries `brief.json` `version`, `brief_package.py`). Nothing to bump; the change is additive.
- **Field:** optional `profile` (alias `stack_profile`) in a JSON / fenced / `key: value` brief; else the `Stack profile:` item inside the `(Intake ...)` trailer. `profile` wins over the alias; a blank field means no choice and the trailer is not consulted.
- **WebUI change:** none required for the current output (the trailer is read as is). To let users pick a project or user profile, the WebUI should write the name in that same `Stack profile:` item (or, better, a structured `profile` field in an inline JSON brief); the name must match `^[a-z0-9][a-z0-9-]*$`. The trailer wording `Stack profile:` is now a compatibility commitment.

## Decision
`brief_profile.py` (sibling, loaded by file path, ADR-045) finds the name and asks `profile_resolver.resolve_profile`; `map_brief(brief, explicit)` lets the choice beat inference and recomputes env questions from it. An unusable name leaves `profile` null with `profile_requested`, `profile_error`, `warnings` and the package refusal shape; the CLI exits 3. Nothing else is substituted. `write-config --profile` already stores the profile in the run config; `get-next-step` and later phases read it there.

## Fix round 1 (orchestrator review)
- **`detecting` is not choosable** (refused as `invalid`): it is the resolver's placeholder for "detect later", so a brief that names it has not chosen a stack. `generic` stays accepted (a real, built-in choice).
- A text-brief `profile:` value counts as a name only in the shape `^[a-z0-9][a-z0-9-]*$`; free text such as `Profile: a SaaS for dentists` stays in the description. The resolver still validates the name.
- Unusable name (`profile_error`): the agent stops and asks, never infers (brief-intake.md Step 2). Control, C1 and bidi characters are stripped from resolver messages.

## Architecture Review
Both reviewers: approve (glm, openai). glm (low): prefer a structured field over prose parsing if the WebUI changes anyway; openai: the trailer syntax becomes a compatibility commitment (recorded above).

## External-Plan-Review-Findings
| Finding | Disposition |
|---|---|
| Parse anchored to the trailer; conflicting fields undefined (glm, openai) | accepted-and-fixed: anchored on `(Intake`, `profile` wins over `stack_profile`, blank rule, tests |
| Env questions change with the chosen profile (glm) | rejected-with-reason: intended, the env belongs to the chosen stack; tests cover both directions |
| Exit 3 for callers (glm, openai) | accepted-and-fixed: refusal shape added, documented, e2e test that nothing is written and no fallback is chosen |
| ADR must record the contract (glm, openai) | accepted-and-fixed: this file |
| Refactor of synonym tables (glm) | rejected-with-reason: needed to keep brief_intake.py below its size at no growth |
| Warning text should carry the operator-only rule (glm) | rejected-with-reason: unrelated to profiles; the NEVER rule sits in the fixture refusal, brief-intake.md and SKILL.md |

## External-Code-Review-Findings
| Finding | Disposition |
|---|---|
| ADR record missing (both) | accepted-and-fixed: this file |
| Text parse let the alias overwrite `profile` (openai) | accepted-and-fixed: both keys kept, precedence in `requested_name`, tests in both orders |
| Trailer item cut at the first word (openai) | accepted-and-fixed: the whole item is validated; test |
| Exit 3 overloaded without `refused` shape (glm) | accepted-and-fixed: `refused`/`code`/`message`/`issues` added |
| Test accepted several codes (glm) | accepted-and-fixed: pinned to `invalid` |
| E2E inherited SHIPWRIGHT_* env (glm) | accepted-and-fixed: scrubbed env, own user-profiles dir |
| Blank `profile` hid a populated alias (glm) | accepted-and-fixed: skipped; blank only suppresses the trailer; test |
| Echoed `brief` lacks `profile` (glm) | rejected-with-reason: `profile_requested` carries it; no consumer reads `brief.profile` |
