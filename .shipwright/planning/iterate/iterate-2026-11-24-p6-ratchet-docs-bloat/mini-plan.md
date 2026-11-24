# Mini-plan: P6 prompt-mechanics ratchet

Goal: refuse mechanics creeping back into a converted skill's SKILL.md (programme P12, second-pass C5).

Steps: (1) shared/config/converted_skills.json registry (commands = key per command, escapes = exact blocks, escape_budget cap). (2) shared/scripts/tools/check_prompt_mechanics.py: fenced shell blocks only; fails on chain operators outside quotes, on multi-command blocks not named as an escape, on a command key not in the registry, on stale escapes, on exceeding the budget; exit 0/1/2. (3) In-process tests incl. the real registry against the real thin SKILL.md and a seeded chain. (4) One (gate) step in ci.yml python-checks and a LOCAL_GATES entry in scripts/verify_local.py (drift test keeps them equal). (5) Docs: guide chapter 9, hooks-and-pipeline gate table, glossary, architecture bullet. (6) shipwright_bloat_baseline.json SKILL.md current 443 -> 263, last.

Risks: ci.yml is a CI trust boundary (needs a human ack, not recorded here); glossary cap (540) forces compressing existing entries; SKILL.md and traces are frozen and untouched.

Alternative approach considered: an inline marker in the prose, rejected because the live prose is frozen (a delta per edit).
