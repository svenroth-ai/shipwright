# B3 — Phase-aware UserPromptSubmit dispatcher

- **Type:** change (topology refactor)
- **Complexity:** small → medium
- **Depends on:** B0 (and the B1/B2 dispatcher pattern)

## Goal

Collapse `phase_user_prompt_validate.py` (registered in 9 plugins → fires
9× per user prompt) into **one** UserPromptSubmit validator owned by
`shipwright-iterate`. iterate-only `suggest_iterate.py` stays.

## Acceptance Criteria

- [ ] **AC-1.** One user prompt → the phase validator runs once, scoped to
      the engaged phase via `resolve_engaged_phase` (B0).
- [ ] **AC-2 (fail-open).** UNKNOWN phase → validate (do not silently
      pass). A prompt-blocking validator must never *block* on a wrong
      guess — fail-open here means "allow + warn", not "hard block".
- [ ] **AC-3.** `phase_user_prompt_validate.py` de-registered from the 8
      non-iterate phase plugins.
- [ ] **AC-4.** Consumer back-compat preserved.

## Tests

- One prompt → one validation; engaged-phase scoping; UNKNOWN path;
  de-registration regression.

## Note

UserPromptSubmit can block/modify the prompt — be conservative: the
dispatcher must not turn a previously-9×-redundant-but-harmless validation
into a single point that *blocks* legitimate prompts on an ambiguous phase.
