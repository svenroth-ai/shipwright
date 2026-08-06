# Mini-Plan: architecture-review-pass

- **Run ID:** iterate-2026-08-06-architecture-review-pass
- **Complexity:** medium

## 1. Files to create / modify

| File | Change |
|---|---|
| `shared/prompts/architecture_reviewer/system` | **new** — the one question, the withholding stated, the parseable finding labels |
| `shared/prompts/architecture_reviewer/user` | **new** — `{SPEC}` + `{BRIEF}`, nothing else |
| `shared/templates/architecture_brief.md` | **new** — anti-anchoring rule + the three-line shape when nothing permanent is added |
| `shared/scripts/lib/external_review_prompts.py` | edit — `load_architecture_review_prompts` + inline defaults |
| `shared/scripts/tools/external_review.py` | edit — `--mode architecture`, `--brief-file`, `{BRIEF}`, one-flag-per-mode validation |
| `plugins/shipwright-iterate/skills/iterate/references/iteration-planning.md` | edit — Step 3.5 step 4a |
| `plugins/shipwright-iterate/skills/iterate/SKILL.md` | edit — two one-liners |
| `plugins/shipwright-plan/skills/plan/references/step-5-external-review.md` | edit — Step 5a |
| `plugins/shipwright-plan/skills/plan/SKILL.md` | edit — one bullet |
| `docs/guide.md`, `docs/hooks-and-pipeline.md` | edit — mode table, the pass, the brief artifact |
| `shared/tests/test_architecture_review_mode.py` | **new** |
| `integration-tests/test_architecture_review_composition.py` | **new** |

Not touched, deliberately: the review-record contract, its 118 tracked records,
the campaign runner, `shared/glossary.md`.

## 2. Work breakdown

1. **Prompts + brief template.** The substance; everything else is plumbing.
   Test: the loader finds them, the verdict instruction and the parseable
   finding labels are present.
2. **CLI mode.** `--mode architecture` + `--brief-file` + `{BRIEF}` + one input
   flag per mode. Test: usage errors, substitution, no spurious warning.
3. **Wiring.** Step 3.5 step 4a (iterate) and Step 5a (plan): run the call,
   `reject` → ask the operator, findings into the existing records.
4. **Docs.**

## 3. Component hierarchy

n/a — no UI.

## 4. Data model changes

None. The pass writes no artifact of its own except the brief it is handed, and
its findings ride in the `plan` review row that step already writes.

## 5. Test strategy

- Unit (`shared/tests/`): CLI arg validation, placeholder rendering, prompt
  loading, the shipped prompt's own content rules.
- Integration (`integration-tests/`): brief → CLI → envelope → recorder → row,
  in-process with the provider replaced. Pins the one property everything rests
  on — the brief, not the plan, is what reached the model.
- Live: run the pass on this change itself, twice.

## 6. Alternative approach considered

**One paragraph appended to the existing `iterate_reviewer` / `plan_reviewer`
prompts, no second call.** One file changed, no new mode. Rejected: same input,
so the reviewer still reads `rejected because X` and tends to confirm it.

*(This section is deliberately NOT carried into the architecture brief — see
`shared/templates/architecture_brief.md`.)*
