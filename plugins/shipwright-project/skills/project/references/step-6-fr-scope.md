# Step 6 gate: one requirement, one capability

**Binding.** Read `shared/fr-authoring.md` §3c before you finish any FR. This gate BLOCKS: you may not call a
requirement finished, move to the next one, or end Step 6 until it passes. A spec has no code or tests yet, so the
gate rests on the capability test below plus code form checks, not on cluster evidence (that runs later, in the audit
as advice).

## 1. The capability test (you, per requirement)

Group the requirement's acceptance criteria by what they are about. For **each group**, write one plain sentence
that says what the group lets the user do or guarantees. Then check:

- The sentence needs **"and"** → the group is two capabilities. Split the requirement: mint a new FR for the second
  part and move its criteria there. The number is the next free one in the split: the highest in use plus one,
  counting the rows under "Removed Requirements" too (no tool does this yet; check by hand).
- Two groups have different sentences AND each part keeps **at least 3 criteria** AND the parts are built or tested
  separately, or serve different readers → they are different capabilities. Split. A part that would keep fewer
  than 3 criteria stays folded into its neighbour (a requirement carved out of one or two criteria is too thin).
- A group's sentence can only be said by naming a mechanism (route, table, library) → rewrite it as what the user
  gets, then re-test.
- **Stop rule (do not over-split):** split only if every part gets a name a user understands, has at least 3 criteria,
  and is built or tested separately or serves different readers. Criteria that serve the same purpose stay together,
  however many there are. Same wording as `shared/fr-authoring.md` §3c.

Record nothing in the spec for this; the result is the shape of the table and the criteria lists.

## 2. The form checks (code)

Run on every `spec.md` you wrote:

```bash
uv run "{shared_root}/scripts/tools/fr_scope_check.py" --spec <split>/spec.md [<other splits>...]
```

It is deliberately conservative. Exit 1 (Step 6 not finished) only for: a spec with text but no requirement it can
read; a `Must` requirement (or one whose priority cannot be read as Should/May) with no acceptance criteria at all;
a file path or code symbol in a criterion. Fix each line, then re-run until it exits 0. `Should` / `May`
requirements may have no criteria yet, and product names such as LinkedIn are not code symbols.

Everything else is a printed `?` prompt that never changes the exit code: a criterion not in `Given … when … then …`
form (checkbox criteria and "confirm with the product owner" criteria are allowed), an HTTP verb / ADR number in a
criterion, and a name joining two capabilities with "and" ("Terms and conditions" is one capability). Take each prompt
as a reason to apply the capability test to that FR in section 1, and decide there.

## 3. Hand-off

When both pass, continue with the checkpoint in `step-6-spec-gen.md`. Later, the compliance audit check `I10` and
`fr_cluster_report.py` use real tests and files to list requirements that can still be split; that is advice for an
operator, not part of this gate.
