# Iterate — IT-5: classification & risk detection

run_id: `iterate-2026-07-31-it5-classification-calibration`
type: change · complexity: medium (keyword `consolidate`; `prior_source: keyword`)
anchor: `trg-ffbf13de` (absorbs `trg-ee7b83e5`, `trg-496e63a7`)
brief: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`

Both halves change **which phases fire**, so they share a blast radius and ship
together. The lever applies to every following iterate.

---

## §0 — Two of the anchor's premises were stale; measured before building

| Anchor / args claim | Measured 2026-07-31 |
|---|---|
| "VORAUSSETZUNG: IT-0 muss `tests/test_classify_complexity.py` (317 Zeilen, **keine Baseline**) zuerst baselinen" | The entry **exists** (`current: 317`, `state: grandfathered`) — it has since `66ec453d`. Round 3 of the brief already corrected this; the anchor card text was never updated. |
| …and IT-5 therefore needs a baseline bump | **No.** This run does not touch that file: it holds no history/prior assertions and none of its `detect_risk_flags` messages name a Python build input. Nothing in this diff ratchets any baseline entry. |
| trg-ee7b83e5: 79 % medium over 67 runs | Reproduced and **worse**: the store retains 50 entries → 84 % medium, 14 % small, 2 % trivial. Window (last 20) = 17 medium / 3 small. |

Probes (verbatim, `--project-root .` against the real store):

```
"add a missing docstring"    → medium  prior_source=history  history_prior=medium  n=20  flags=[]
"add a docstring to touches_build_files" → medium  prior_source=history  ...
"fix a typo in the guide"    → small   prior_source=keyword
"rename a local variable"    → small   prior_source=keyword
```

```
touches_build_files(["uv.lock"])         → False      touches_build_files(["package.json"]) → True
touches_build_files(["poetry.lock"])     → False
touches_build_files(["requirements.txt"])→ False
touches_build_files(["Pipfile.lock"])    → False
touches_build_files(["pyproject.toml"])  → False
```

---

## §1 — Root cause (half 1): the prior is a fixed point, not a prediction

`load_history_prior` returns the median **final** complexity of the last 20
runs. For a run with no scope keyword the final complexity *is* the prior. So:

```
prior = median(finals)     finals ⊇ {prior, prior, prior, …}  (every no-keyword run)
```

The relation is self-consistent at **any** level — it carries no information
about the change being classified. It happened to settle on `medium`, and each
new no-keyword run re-deposits `medium` into the window that produced it.

**What the prior was for** (its own docstring): "64 % of Stage-1 outputs were
trivial while only 14 % of runs finalized trivial — the Stage-2 scout had to
bump nearly every run." It was built to reduce Stage-2 bump work, and
over-corrected into a fixed point.

**The asymmetry that decides the fix direction.** Under-classification is
recoverable *in-session*: Stage 2 (Repo Scout) confirms/upgrades, and the skill
ships a Mid-Flight Escalation path. Over-classification is not — SKILL.md §E
locks complexity after Stage 2 and nothing de-escalates. The prior optimises
the cheap direction and pays in the expensive one.

### Decision — the fall-through may inform how LOW to go, never how HIGH

`_PRIOR_CEILING` moves from `medium` to `small`.

`medium` is the first tier that buys an iterate spec, a mini-plan, an approval
gate and an external LLM plan review. Those are bought with **positive
evidence** — a scope keyword, a risk flag, a cross-split, or the Stage-2 scout.
The *absence* of evidence must not buy them.

**Why not "median over keyword-classified runs only"** (the anchor's other
option) — **corrected after the doubt review; the first answer was wrong.**

This spec originally said the option was *blocked*, because recording a
`prior_source` field would mean editing
`shared/scripts/tools/append_iterate_entry.py`, "425/425 grandfathered" in the
bloat baseline. **Both halves of that were false**, and I had imported the
figure from the anchor instead of measuring it — the exact failure §0 above
congratulates itself for catching. Measured:

- the baseline entry is `limit: 300, current: 436`, and the file is 436 lines;
  no figure in the claim was right;
- the writer needs **no edit at all** — its CLI does `entry = {..., **extra}`
  over `--entry-json` with no allowlist, colliding only on
  `run_id`/`date`/`event_at`. Recording a new key costs zero lines there.

**The real and sufficient reason is the backfill blackout.** No entry written
before today carries `prior_source`, so a filter on it finds zero qualifying
entries, falls under `HISTORY_MIN_ENTRIES`, returns `None`, and drops the
fall-through to bare `trivial` — a *larger* process cut than this cap — until
~20 new runs accumulate. The cap needs no new data and bounds the loop
immediately.

**So the option is deferred, not rejected, and this run pays its setup cost:**
F5c now records `prior_source` (`references/F5c.md`). That makes the better
calibration implementable once the window fills, and — answering the doubt
review's third objection — makes this change's own flip-rate measurable, which
it otherwise would not have been in either direction.

**What the clamp preserves.** The lower half stays adaptive and stays meaningful
for adopters: a repo whose runs genuinely finalize trivial still gets `trivial`.
Only the route *up* to `medium` is closed.

### What a run gives up when it lands `small` instead of `medium`

Enumerated because the subject of this change *is* how much process runs, and a
spec that lists only what it preserves is arguing one side. Every row below goes
**green**, not warning, at `small` (doubt review, objection 6 — verified in the
named files):

| Given up | Where | At `small` |
|---|---|---|
| F0.5 surface verification | `iterate_checks.py` | green SKIP |
| integration coverage (cross-component) | `integration_coverage.py:70-72` | green SKIP — **before** its "non-dodgeable" recompute |
| cross-layer coverage | `layer_coverage.py:171-173` | green SKIP |
| removal-coverage **infra failures** | `layer_coverage.py:99-106` | ERROR → green SKIP |
| code-review floor ("a review actually ran") | `review_record_floor.py` | not applied |
| iterate spec / mini-plan checks | `spec_checks.py` | not applied |
| iterate spec · mini-plan · approval gate · external LLM plan review | Phase Matrix | not run |
| Confidence Calibration | Phase Matrix | skip unless `touches_io_boundary` |
| Full Code Review | Phase Matrix | "only if risk flags" |
| unit / integration suite | Phase Matrix | `--related` / if CRUD, not full |
| E2E author + execute | Phase Matrix | conditional, not "always" |

Two of these are load-bearing enough to change the design rather than just be
listed:

1. **`check_integration_coverage` is advertised NON-dodgeable but gates on the
   recorded complexity first.** Its recompute-from-diff cannot be dodged; the
   complexity gate above it can. Stage 1 raises `cross_component` from *message*
   keywords only, so a diff touching `hooks.json` or `churn_merge.py` that does
   not name them was previously rescued by the prior returning `medium`. This
   change removes that accidental rescue.
2. **Quick Scout — the recovery mechanism the whole asymmetry argument rests
   on — was itself weaker than Thorough Scout at exactly the two steps that now
   matter** (cross-split; shared components). Relying on Stage 2 while
   downgrading Stage 2 is circular.

**Both are answered in this diff, not deferred:** `references/iteration-planning.md`
Quick Scout gains a **mandatory diff-driven detector step** (running
`is_cross_component_change`, `is_ci_supplychain_change`, `is_io_boundary_change`,
`touches_build_files` over the file list step 2 already produces) plus the
cross-split check. `cross_component` floors at `medium`, so a genuine
cross-component diff now reaches medium from the **diff** at Stage 2 — a
stronger route than the message-keyword accident it replaces, and one that also
closes the pre-existing hole for `trivial`.

**The limit of that mitigation, stated rather than glossed** (external plan
review, `revise`, high): the Quick Scout detector step is an *instruction the
agent follows*, not an enforced classification path. A skipped or sloppy Quick
Scout lets a cross-component change stay `small` — where the old behaviour
reached `medium` automatically, if accidentally. The enforceable version is to
drop the complexity gate above `check_integration_coverage`'s recompute, which
is a change to a **shared F11 verifier**: it belongs to IT-3 (*"F11 tells the
truth about the run it checks"*, four fail-open paths in that same gate), and
the anchor's own risk note forbids riding gate changes along with a calibration
change. Filed as triage, not silently accepted, and named here so the mitigation
is not read as stronger than it is.

Two other plan-review findings were **checked and did not hold** against the
implementation (the review reads the spec as a plan, so it reasons about what
was proposed): the Windows-separator concern assumes `os.path.basename`, but
the detector normalizes `\`→`/` via `_normalize_diff_path` *before* splitting
and is tested with backslash paths on this platform; and the unbounded-regex
concern was already closed by the token guards. Gemini's high — "AC-4..6 force
assertions into the 317-line `test_classify_complexity.py` and will trip the
bloat hook" — is a misreading: the new assertions live in
`test_classify_complexity_perf.py`, which is the pre-existing home of the
`touches_build` tests, and `test_classify_complexity.py` is untouched. Verified,
not argued: the anti-ratchet pre-commit hook exits 0 against the staged tree.

**Said plainly, because it is a real reduction:** in *this* repo the module now
returns `small` for every no-keyword run, since the median is `medium` and the
clamp catches it. Its job shrinks from "predict the tier" to "decide whether
this repo's floor is `trivial` or `small`". That is a smaller job than it was
built for, and this spec records it rather than implying the module still
discriminates here.

### Decision — the `trivial` tier is kept, not widened and not removed

The anchor asks to decide (`2 of 67 is a dead tier`). It stays reachable — via
cold start (`prior_source: default`) and via a genuinely trivial-dominated
history — and is neither widened nor deleted. Removing a tier rewrites the Phase
Matrix, Override Classes and every complexity-gated reference for no measured
benefit; widening it would hand the *least* evidence to changes chosen by the
same fall-through this run is narrowing. Recorded as a decision so it is not
re-opened as an oversight.

---

## §2 — Root cause (half 2): the build detector cannot see Python, on two surfaces

`TOUCHES_BUILD_FILE_PATTERNS` lists JS build inputs only, matched by exact
basename. In a Python monorepo `uv.lock`, `poetry.lock`, `requirements*.txt`,
`Pipfile.lock` and `pyproject.toml` raise nothing.

**The card names one surface; there are two.** `detect_risk_flags` — what
actually runs at Step E — matches `RISK_TAXONOMY["touches_build"]["patterns"]`
against the *message*, not the diff. `touches_build_files` is the separate
diff-driven detector. Widening only the file patterns would leave the surface
that fires at Step E blind. (conventions.md, 2026-07-28: *detection that changes
no decision is not detection*.)

Both are widened with the canonical Python set: `uv.lock`, `poetry.lock`,
`Pipfile`, `Pipfile.lock`, `pyproject.toml`, `setup.py`, `setup.cfg`, and the
`requirements*.txt` family.

`requirements*.txt` cannot be an exact-basename literal
(`requirements-dev.txt`, `requirements_prod.txt`, …), and the tuple's
exact-basename contract is pinned by
`test_touches_build_files_does_not_match_partial_basename`
(`my-package.json` → False). So the family gets its own named constant,
`TOUCHES_BUILD_BASENAME_GLOBS`, matched with `fnmatch` on the basename — which
anchors the whole name, so `my-requirements.txt` still does not fire. The
literal tuple keeps its type and its meta-test keeps meaning what it says.

**False-positive guard (load-bearing).** The *message* pattern must require the
`.txt` suffix (`requirements[\w.-]*\.txt`). This is an IREB
requirements-engineering framework; a bare `requirements` would fire
`touches_build` on ordinary prose about requirement catalogues.

**Scope boundary — Python only.** Rust / Go / Ruby / PHP build inputs are
deliberately not added. The measured finding is Python, this is a Python
monorepo, and widening to unmeasured ecosystems is guessing. Recorded as a
decision, not an omission.

**What the flag actually buys for a Python change, stated so nobody reads a
promise into it.** `touches_build` enforces `performance_test_layer` (Lighthouse
+ bundle). For a Python diff both skip by their own rules — no `dev_url` → skip
Lighthouse, no build artifacts → skip bundle. The load-bearing effects are the
`small` minimum and the risk flag itself, which at trivial/small turns
"Full Code Review — *only if risk flags*" on. That is the honest value.

---

## Acceptance Criteria

- **AC-1** The fall-through prior can never exceed `small`, whatever the history
  contains (incl. an all-`large` history).
- **AC-2** The lower half stays adaptive: a trivial-dominated history still
  yields `trivial`, and cold start (< 3 entries) still yields `trivial` with
  `prior_source: default`.
- **AC-3** Against this repo's real store, a message with no scope keyword
  ("add a missing docstring") classifies **small** with `prior_source: history`
  — not `medium`. A keyword match still wins (`prior_source: keyword`), and a
  risk floor still applies on top.
- **AC-4** `uv.lock`, `poetry.lock`, `Pipfile`, `Pipfile.lock`, `pyproject.toml`,
  `setup.py`, `setup.cfg` raise `touches_build` from a **diff**, at any path
  depth and with Windows separators.
- **AC-5** `requirements.txt`, `requirements-dev.txt`, `requirements_prod.txt`
  raise `touches_build` from a diff; `my-requirements.txt` and
  `requirements.txt.bak` do **not** (no partial-basename regression).
- **AC-6** The same inputs raise `touches_build` from a **message** via
  `detect_risk_flags`; prose naming requirements without a `.txt` filename
  (e.g. "update the requirements catalog for FR-01.02") does **not**.
- **AC-7** SKILL.md and `docs/guide.md` name the Python build inputs in the
  `touches_build` trigger column, SKILL.md §E states the capped fall-through,
  and a drift test pins the SKILL.md row against `TOUCHES_BUILD_FILE_PATTERNS`
  in both directions.

## Spec Impact

**NONE** — no `FR-*` behaviour is added, removed or modified. This recalibrates
*how much process* an iterate runs, not what the framework produces. `affected_frs`
carries FR-01.11 (the risk-taxonomy/phase-selection requirement the changed
tests are marked `covers`); per the F11 contract a `spec_impact: none` alongside
`affected_frs` requires a `spec_impact_justification`, supplied at F5c.

## Affected Boundaries

- `classify_complexity` → `shared/contracts/iterate.py` (pinned cross-plugin
  re-export surface; a new constant is additive, `__all__` updated)
- `complexity_history` ← `.shipwright/agent_docs/iterates/*.json` (read-only;
  written by the shared F5c writer — round-trip pinned by
  `test_complexity_history_roundtrip.py`)
- `RISK_TAXONOMY` → SKILL.md (Risk Taxonomy table, Phase Matrix) + `docs/guide.md`

## Confidence Calibration

- **Boundaries touched:**
  `classify_complexity` → `shared/contracts/iterate.py` (pinned cross-plugin
  re-export; additive constant + `__all__`) · `complexity_history` ←
  `.shipwright/agent_docs/iterates/*.json` (read-only; written by the shared
  F5c writer) · `RISK_TAXONOMY` → SKILL.md + `docs/guide.md` · **new this
  round:** the F5c entry contract gains `prior_source`, and
  `references/iteration-planning.md` (Quick Scout) gains a detector step that
  feeds the Stage-1 → Stage-2 → complexity-lock boundary.

- **Empirical probes run** (each re-run *after* the change, against the real
  store — the pre-change readings are in §0):

  | Probe | Before | After |
  |---|---|---|
  | `"add a missing docstring"` | medium (`prior_source=history`, n=20) | **small** (`prior_source=history`, `history_prior=small`, n=20) |
  | `"add a docstring to touches_build_files"` | medium | **small** |
  | `"fix a typo in the guide"` | small (`keyword`) | small (`keyword`) — unchanged |
  | `"consolidate the two detectors"` | — | **medium** (`keyword`) — positive evidence still reaches medium |
  | `touches_build_files(["uv.lock"])` … `["pyproject.toml"]` | all **False** | all **True** |
  | `touches_build_files(["my-requirements.txt"])` | False | **False** (no over-match) |
  | `detect_risk_flags("restore my-requirements.txt")` | — | **False** — external review found this **True** with a bare `\b`; fixed with token guards |
  | `detect_risk_flags("pipfile.locked backup")` | — | **False** |
  | store distribution (50 retained entries) | 84% medium / 14% small / 2% trivial | unchanged (input data) |

  **Mutation checks** — every pin was verified to fail without its fix, not
  assumed to: ceiling → `medium` = **13 failures**; Python message patterns
  removed = **15 failures**; `requirements*.txt` glob removed = **3**;
  `fnmatchcase` → `fnmatch` = **2** (Windows only); quote-strip removed =
  **2**; `Cargo.toml` added to the detector = **1** (forward drift bites);
  detector step deleted from Quick Scout = **1**.

  One mutation run was a **false pass**: a bash heredoc mangled the regex
  escapes (`SyntaxWarning: invalid escape sequence`) so the edit never applied
  and 82 tests "passed" against unmutated code. Re-applied with the editor, it
  failed as it should. The same heredoc trap then produced two real defects in
  the test file itself (`\p`/`\{` invalid escapes, and `\303` silently decoded
  from git's literal quote-text to an octal character) — both caught and fixed
  with raw strings. A green mutation run is evidence only once the mutation is
  confirmed present.

- **Test Completeness Ledger:** 33 behaviors — **32 `tested`, 1 `untestable`
  (`covered-by-existing-test`), 0 untested-testable.** Enumeration basis: 7 ACs,
  all covered. Full table in the F5 block of
  `shipwright_test_results.json` / the F5c entry.

- **Confidence-pattern check:**
  - *Asymptote (depth):* the ceiling is exercised across five history
    compositions plus the two tie-break paths; two pre-existing tests were
    repaired because the cap made them **vacuous** (both middles clamped to the
    same value), and two more vacuous ones were found by the code reviewer
    after I had already caught two — the failure mode recurred four times, so
    every remaining assertion in that file was re-derived by hand rather than
    trusted.
  - *Coverage (breadth):* both `touches_build` surfaces (diff + message), both
    drift directions (detector→docs, docs→detector), both platforms
    (case-sensitivity), and the git-quoting path shape.
  - *Integration composition:* `cross_component` is **not** in this diff's path
    set — no merge/churn/event-log resolver, hook, phase validator or campaign
    file is touched — so the F11 recompute finds nothing and no
    `category:"integration"` behavior is owed. The change *does* alter when
    that gate fires; that is analysed in the give-up table above and mitigated
    in Quick Scout rather than left implicit.
  - *Residual watched, not closed:* `pyproject.toml` / `setup.py` / `setup.cfg`
    on the **message** surface can fire on prose that merely quotes the
    filename — CLAUDE.md itself tells agents the ruff config lives in the root
    `pyproject.toml`. Measured impact today is nil (1 of 26 real corpus prompts
    names it; its estimate is unchanged), so it is recorded rather than
    pre-emptively narrowed — narrowing would trade a false positive for a false
    negative on the surface that actually fires in-session.
