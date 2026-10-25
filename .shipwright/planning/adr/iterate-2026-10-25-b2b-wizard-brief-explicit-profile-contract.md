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
- A bare `profile:` line of a text brief is only a HINT (superseded round 1 rule, see round 2).
- Unusable name (`profile_error`): the agent stops and asks, never infers (brief-intake.md Step 2). Control, C1 and bidi characters are stripped from resolver messages.

## Fix round 2 (trade-offs)
- **Trailer anchoring:** the WebUI puts the user's free idea BEFORE the trailer, so the idea must not be able to name a profile. The trailer is the last `(Intake` and must end the text; two trailers or two `Stack profile:` items are refused as ambiguous (exit 3) instead of guessing.
- **Text-brief keys:** `Stack profile:` / `stack_profile:` is unambiguous, so its value always goes to the resolver (a misspelled `Vite-Hono` exits 3, never falls back to inference). A bare `profile:` is ordinary English ("Profile: none", "- profile: avatar" in a feature list), so it is only a hint: unbulleted, name-shaped and known to the resolver, else it stays prose. Trade-off accepted (round 3, after spec review): an unused bare `profile: vite-hon` is never silent - the line stays in the description, the profile is inferred, exit stays 0, and `warnings` names the ignored value and points to `Stack profile: <name>` (sanitised, length-capped). It is a warning and not a refusal because the same word is ordinary prose ("Profile: none"); the strict key and the JSON field are the ways to make a choice that is used or refused.
- **Blast radius:** `brief_profile.py` and the resolver are touched only for a brief that can name a profile; if they cannot be loaded or fail unexpectedly, that is `resolver_unavailable` (exit 3), never a silent inference. A brief that names none works without them.
- The bidi/zero-width class is written as escapes, so no invisible character sits in the source.

## Precedence of the profile sources (fix round 4, the single rule)
Strict sources always beat the bare hint, in this order: (1) JSON field `profile` / alias `stack_profile`; (2) text `Stack profile:` / `stack_profile:` key; (3) the last `(Intake ...)` trailer item (must end the text; two trailers or items are refused); (4) only if none of 1-3 exists, the bare unbulleted `profile:` hint. A strict source that cannot be used exits 3; a blank strict field means no choice (trailer and hint not consulted); a hint is considered only when no strict source exists, so it cannot mask one (a wizard one-liner whose idea starts with "Profile:" keeps its trailer name) and a present strict source means the hint is not even warned about. Pinned by a table-driven test over the combinations.

## Final fix round (trailer reading)
A one-line wizard brief whose idea starts with a brief key (`Location:`, `Users:` ...) was swallowed whole into that key's value, so `description` was empty and the trailer's profile was silently dropped: the text parser now also hands the whole brief to the profile check (`_text`, a side channel that never becomes a brief answer), and the trailer is looked up in `description` then `_text`. Only the trailer's own `Stack profile:` items count (an idea saying "(Intake forms)" or "stack profile: x" no longer refuses); an earlier `(Intake ... Stack profile: ...)`, two items in the trailer or two `Stack profile:` lines stay ambiguous with a message that names that cause. A hint turns every resolver ValueError kind (not only not_found) into a warning; the lazy-load gate is case-insensitive; a failed sibling load returns the full sanitised refusal shape; resolver text is echoed as `resolver said (untrusted): ...`.

## Round 6 (review of the final round)
`_trailer_item` now checks "does the last `(Intake` end the text" BEFORE it counts items, so prose that is not a trailer cannot be refused (it is reported as `misplaced`, a warning); the earlier-trailer pattern is `\(Intake[^()]*Stack profile:` (linear, a 200 KB test pins it) and `(Intake` is matched case-insensitively. A text `Stack profile:` key and a differing trailer item are ambiguous (the WebUI `composeNewBrief` only `trim()`s the idea and the server flattens newlines, so this only happens in hand-written briefs). The profile-check load failure refuses only a brief that names a profile; a generic resolver failure on a hint warns; JSON keys like `stackProfile` warn and are never aliases; the private parser keys are dropped from JSON briefs (`_TextBrief` marks the text parser's output).

## Round 7 (last round: simplest rule per item)
(1) `_text` exists only for a one-physical-line text brief, and an item value never spans a newline: a valid multi-line brief naming one profile is no longer refused. In a one-liner the trailer wins over a key swallowed at the line start; in a multi-line brief a text key and a differing trailer stay ambiguous. (2) A fenced JSON block is the brief only when its opening fence starts a line (a lead-in sentence stays allowed, existing behaviour); a fence inside an idea is prose. (3) The `Stack profile:` text line is kept in the description (like the hint), so adopt's `product_description` is identical to before B2b. (4) A misplaced trailer warns beside a bare hint too; it only warns (never refuses) because the same words occur in ordinary prose. (5) `_NAMES_PROFILE` is narrowed to a line-start/`;`-led key or a JSON key. `_KV_RE` and `_FENCE_RE` own each space once (linear). Accepted change: a text brief whose key line is `Stack profile:` now keeps that line in `description` (previously B2b removed it). Follow-up, not done: the WebUI should send a structured `profile` field so none of this prose parsing is needed.

## Round 8 (one principle replaces the round 4-7 special cases)
The rounds kept reopening because the trailer was searched in derived text (joined prose, a one-line `_text`, fences). One rule now: THE WIZARD TRAILER IS READ ONLY FROM THE LAST PHYSICAL LINE OF THE RAW TEXT (`_text` is kept for every text brief; a JSON brief uses its description). Everything else never produces a trailer. This deletes: the single-line `_text` special case, the description/`_text` double lookup, the anchored fence and the "key at the line start is the idea" early return (a key that swallowed the last line is simply compared with the trailer read from that same line). The original unanchored `_FENCE_RE` is restored (briefs without a profile parse exactly as before B2b; adopt unchanged); the one exception is a text whose last line is a wizard trailer line, whose fence is idea prose. The trailer's item must sit in the `(Intake` group before any inner bracket, so "(Intake forms) ... stack profile: x (later)" is prose (no refusal, no warning). An earlier `(Intake` counts as a second trailer only when it closes with a name-shaped item followed by `)` or `;`. Text `Stack profile:` line and trailer disagree: ambiguous; agree: fine. The fallback gate also accepts `(Intake[^()]*Stack profile:`. Doc claim narrowed: "no new keys" except a non-blocking `warnings` entry for a profile-looking key or a misplaced trailer.

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
