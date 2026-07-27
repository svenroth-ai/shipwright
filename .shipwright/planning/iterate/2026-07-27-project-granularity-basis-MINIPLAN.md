# Mini-Plan — `iterate-2026-07-27-project-granularity-basis`

Concrete step list. Rationale, probes and the rejected alternative live in the
iterate spec (`2026-07-27-project-granularity-basis.md`).

## Step 1 — `group_i_rows.py` (pure move, no logic change)

Move out of `plugins/shipwright-compliance/scripts/audit/group_i.py`:
`FrRow`, `_scan_one_spec`, `scan_specs`, `scan_fr_rows` (lines 54–151).
Re-export all four from `group_i.py` so existing callers/tests are untouched.

*Why:* `group_i.py` is at 298 of a 300-line cap; I6 does not fit. The file
already delegates to `group_i_detectors` and `group_i_scan`, so this is the
established pattern rather than a new one.

*Verify:* `test_audit_group_i.py`, `_basis.py`, `_states.py` pass unchanged.

## Step 2 — `group_i_criteria.py` (new, pure)

```
ids_with_criteria(content: str) -> set[str]
frs_without_criteria(project_root: Path, rows) -> list[str]
```

Anchor forms recognised (both are shapes a Shipwright producer actually emits):

| Form | Producer |
|---|---|
| `### FR-XX.YY — Title` + `-`/`*` bullets | `adopt/artifact_writer.py`, this repo's catalogue |
| `**FR-XX.YY: Name**` + `- [ ]` boxes | `spec-generation.md` template |

Rules:
- an anchor must start with `#` or `**` — a `\| FR-XX.YY \|` **table row is not an
  anchor**, else every FR would trivially "have criteria" from the FR table itself;
- a block collects until the next anchor or the next `##` section;
- a block whose only non-empty content is a `TBD` placeholder → **zero** criteria;
- ids are matched canonically (`FR-\d+\.\d+`).

*Verify:* new `test_group_i_criteria.py` — ledger rows 1–5, 9, 10.

## Step 3 — wire `I6` into `group_i.py`

- `_CHECKS` += `("I6", "FR without acceptance criteria", "LOW")`
- `_ADVISORY_CHECKS` += `"I6"` — never `fail`, so `AuditReport.any_fail` and the
  `run_audit` exit code are unchanged
- `run()` appends `_report("I6", …, frs_without_criteria(project_root, rows), …)`
- module docstring gains the `- I6 — …` line

*Verify:* new `test_audit_group_i_criteria.py` — ledger rows 6–8.

## Step 4 — granularity guidance

- `shared/fr-authoring.md`: new **§3a "How big is one requirement?"** after §3.
  States the decided rule (criteria a single delivery would satisfy; inability
  to enumerate what would settle it = several capabilities), keeps the judgement
  human, names I6 as the observable signal.
- `spec-generation.md`: cite §3a where it already cites §3.
- `split-heuristics.md`: one pointer distinguishing planning-unit granularity
  (that file) from requirement granularity (§3a).

*Verify:* new `test_granularity_guidance_refs.py` — both directions, so neither
the section nor its citations can be deleted silently (registry-driven SSoT rule).

## Step 5 — the `assumed` wording, one sentence in four places

| File | Change |
|---|---|
| `spec-generation.md` template rows | `assumed` → `interview`; one qualified `assumed` example retained |
| `spec-generation.md` Basis table | + "…and what would settle it is named" |
| `fr-authoring.md` §4a | same qualified wording |
| `requirement-elicitation.md` §8 | greenfield row: flat "No." → qualified form |

Brownfield (`/shipwright-adopt`) behaviour is deliberately untouched.

*Verify:* new `test_basis_wording_consistency.py` — ledger row 12.

## Step 6 — finalization

F0 full suite → F0.5 (`surface = none`, justified: no runtime surface, docs +
one detective-only audit check) → F1–F12.

## Risks

1. **False warnings across every adopted repo** — I6 reads a shape it does not
   emit. Mitigated by round-trip tests against the *literal* template and the
   *literal* adopt emission (ledger rows 9, 10), not hand-written fixtures.
2. **The pure move silently changes behaviour** — mitigated by running the three
   existing group_i test files unchanged.
3. **Docs drift apart again** — mitigated by the two drift tests (rows 12, 13);
   that recurrence is exactly the defect being fixed.
