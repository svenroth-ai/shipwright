# Mini-plan: Q2 phase 1, post-build per-AC check (warning only)

Goal: after the build, the spec-reviewer judges each promise (AC) the run froze before the build against the diff (matches or diverges, with the line), and the iterate's own F11 reports the result as a warning. Nothing blocks.

Work:
1. `lib/ac_claims.py` + `tools/ac_claims.py`: build `ac-claims.json` from the committed `ac-record.jsonl` and the base catalog (code only); `judge()` turns claims + verdicts into warnings; `grade` reject for operator/code items, warn for unconfirmed auto.
2. `agents/spec-reviewer.md`: optional third input (claims file) and a per-AC output block; unchanged without the input (shared with /shipwright-build); stays under 400 lines.
3. `lib/ac_verdicts.py`: clean and bound `ac_verdicts`; `record_review_pass.py` carries them onto the completed `spec` row (net-zero lines in the 408-line file).
4. `verifiers/post_build_ac_check.py`: F11 warning check registered in `CLAIM_CHECKS`; says visibly when no AC review ran.
5. Docs (hooks-and-pipeline, iteration-reviews, F11, SKILL.md sentence), changelog, decision drop; `ac-claims.json` is gitignored.
6. Seeded measurement before merge (5 correct, 5 altered), saved under campaigns.

Tests first, hermetic, `shared/tests` root only. Phase 2 (refusing a spec row on reject-grade items) is not part of this change.
