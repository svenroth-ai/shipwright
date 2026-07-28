# Mini-Plan — ask before the cascade lapses

Run: `iterate-2026-07-28-cascade-ask-before-lapse` · CHANGE · medium

## S1 — Failing guards (`shared/tests/test_cascade_ask_before_lapse.py`, new)

Same prose-assertion pattern as `test_review_cascade_owner.py` (#482), whose
`_norm` preserves underscores so CLI flags can be asserted.

1. Step 8 tells the session to request the go-ahead **as its first action**
   when a policy gates spawning. **RED**
2. Step 8 names the `--autonomous` exception (cannot block → record + surface).
   **RED**
3. `iteration-reviews.md`'s escalation section defines what counts as a real
   blocker (no `Agent` tool / tool failure / autonomous). **RED**
4. It states that a conditional policy is not a blocker until asked and
   declined. **RED**
5. The disposition requirement names which of the three applied. **RED**
6. The escalation ladder still ends where it did — external carries the pass,
   `code` is never `completed` by substitution (regression guard on #476/#482
   wording; expected **GREEN** before and after).

## S2 — Prose (AC1–AC4)

- `plugins/shipwright-iterate/skills/iterate/SKILL.md` Step 8: prepend the
  ask-first sentence + the autonomous exception. Runtime-prompt, 400-LOC cap —
  the file is currently well under it, but keep the addition to ~3 lines.
- `plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md`
  → "When the internal reviewer cannot run": insert step 0 (what a blocker is,
  what it is not), and extend the step-2 disposition requirement to name the
  blocker class.

## S3 — Docs

`docs/guide.md` Ch. 8 already describes the three review layers (updated in
#482). Check whether the ask-first rule belongs there; add one clause if so.
No `docs/hooks-and-pipeline.md` change — no hook, phase or validator moves.

## S4 — Verify

`shared/tests` full suite · `plugins/shipwright-iterate/tests` (the
`test_sub_iterate_runner_contract.py` structural set must survive) ·
`uvx ruff@0.15.15 check .` · F0.5 `surface=cli`.

## Risk

No `cross_component` (campaign-mode.md untouched → integration coverage not
triggered; will confirm against `risk_detectors` on the real diff). No schema,
no migration, no enum change. Prose + guards only.
