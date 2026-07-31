# Self-Review — iterate-2026-07-31-it5-classification-calibration

Seven-point checklist per `references/iteration-reviews.md`.

## 1. Does it do what the spec says?

Yes, and it does one thing the anchor did not ask for. AC-1..AC-3 (ceiling) and
AC-4..AC-6 (Python build inputs) are each pinned by a test that was verified to
fail without the fix. **AC-6 is the addition:** the anchor named only
`TOUCHES_BUILD_FILE_PATTERNS`, but `detect_risk_flags` — the surface that
actually runs at SKILL.md Step E — matches `RISK_TAXONOMY` patterns against the
*message*, not the diff. Widening only the file patterns would have shipped a
detector that fires in a unit test and never in a session. Mutation 2 confirms
it: reverting only the message patterns fails 15 tests.

## 2. Is anything out of scope?

`pyproject.toml`, `setup.py`, `setup.cfg` and `Pipfile` are added beyond the
four names the card lists (`uv.lock`, `poetry.lock`, `requirements*.txt`,
`Pipfile.lock`). Justification: `pyproject.toml` is the exact counterpart of
`package.json`, which the list already carries; omitting it would reproduce the
same blindness one level up, which is the defect being fixed. Recorded as a
decision in the spec, not slipped in.

Deliberately NOT done, each recorded rather than silently skipped:
- Rust / Go / Ruby / PHP build inputs — unmeasured here; a wrong entry costs a
  false risk flag on every future iterate that touches the file.
- Recording `prior_source` in the F5c entry (which would allow the anchor's
  other option, "median over keyword-classified runs only"). It needs a field in
  `shared/scripts/tools/append_iterate_entry.py`, which is **425/425
  grandfathered** — adding one ratchets the baseline and is blocked until the
  split `trg-1346abbd` owns.
- Removing or widening the `trivial` tier. Decided explicitly (kept, reachable
  via cold start and a trivial-dominated history) because the anchor asked for a
  decision, and an undecided tier would come back as an oversight.

## 3. Tests: do they test outcomes, and would they fail?

Verified by mutation, not assumed — the repo's own 2026-07-28 learning:

| Mutation | Result |
|---|---|
| `_PRIOR_CEILING` back to `medium` | **13 failed** |
| Python message patterns removed from `RISK_TAXONOMY` | **15 failed** |
| `requirements*.txt` glob removed | **3 failed** |

The first attempt at mutation 2 was a **false pass** — a bash heredoc mangled
the regex escapes (`SyntaxWarning: invalid escape sequence`), so the edit never
applied and 82 tests "passed" against unmutated code. Re-applied with the
editor; it then failed as it should. A green mutation run is only evidence if
the mutation is confirmed present.

Two existing tests were repaired because the change made them **vacuous**, which
is a stronger reason than making them fail:
- `test_jumbled_writes_sorted_window_median` used `medium`/`small`. Under the
  cap both a correct window and a window built from the *oldest* 20 entries read
  back `small` — the sort assertion could no longer fail. Recomposed to
  `trivial`/`small` so correct → `small` and broken → `trivial`.
- `test_risk_floor_does_not_cap_history_prior` asserted "prior above floor" on
  the history branch. That state is now unreachable by construction. The
  property still holds on the keyword branch, so the assertion moved there
  rather than being deleted.

## 4. Error paths

`load_history_prior` is unchanged in its failure behaviour (all skip criteria,
the cold-start `None`, the malformed-entry paths). Only the final clamp index
moved; every existing skip test still passes and still discriminates via `n`.

`fnmatchcase`, not `fnmatch`: plain `fnmatch` calls `os.path.normcase`, so on
Windows `REQUIREMENTS.TXT` would fire and on Linux it would not. A risk gate
whose verdict depends on the OS is a defect; the exact-basename half of the
detector is case-sensitive already.

## 5. Does it match repo conventions?

Yes. Ruff clean (gating). New constant follows the module's existing
`*_PATTERNS` naming and is re-exported through `classify_complexity` and
`shared/contracts/iterate.py` — the contract already exports every *other*
pattern constant, so omitting this one would be the kind of asymmetry that
hides. No file crosses its bloat limit; no baseline entry is ratcheted.

## 6. Docs updated in the same diff?

- SKILL.md Risk Taxonomy row + Step E prose (both NORMATIVE)
- `docs/guide.md` — the taxonomy row *and* line 1677, which independently stated
  "capped at medium" and would otherwise have contradicted the code
- `docs/hooks-and-pipeline.md` — **checked, no update owed**: no hook, phase,
  validator, between-phase action or startup-read changes
- `CHANGELOG.md:310` — **deliberately not edited.** It records what a past
  release did; the new behaviour belongs in an F4 drop, not in a rewrite of
  shipped history.
- A drift test (`test_touches_build_python_inputs_sync.py`) now pins the
  SKILL.md row against the detector in **both** directions, per the
  registry-driven SSoT meta-test rule.

## 7. Affected Boundaries

- `classify_complexity` → `shared/contracts/iterate.py` — additive export,
  `__all__` updated; the consumer integration test passes (429 green).
- `complexity_history` ← `.shipwright/agent_docs/iterates/*.json` — read-only;
  the round-trip through the **real** shared writer still passes.
- `RISK_TAXONOMY` → SKILL.md + `docs/guide.md` — now drift-pinned.

**Not a boundary this run writes:** the F5c entry schema. That is exactly why
the anchor's alternative fix was unavailable.

## Residual risk, stated plainly

In *this* repo the prior now returns `small` for every no-keyword run, because
the median is `medium` and the cap catches it. `complexity_history.py` therefore
no longer discriminates here; its remaining job is choosing between `trivial`
and `small` as the floor, which matters for adopters whose runs genuinely
finalize trivial. That is a real reduction in what the module does and is stated
in its docstring and the spec rather than left for a reader to discover.

The change moves gates for every following iterate. It lands with no REQ-3
campaign in flight and no open PRs (verified at B1b), which is the "clearly
before REQ-3" condition the anchor set.
