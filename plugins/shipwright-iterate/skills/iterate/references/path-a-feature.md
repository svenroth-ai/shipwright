# Path A: FEATURE (new functionality)

Follow the Phase Matrix in SKILL.md Section 6 to determine which steps run.
Step 7 / Step 7.5 / Step 8 / Step 11a / Step 11b headings are kept inline in
SKILL.md because they are anchors for several drift-protection tests.

> **The interview (SKILL.md Section G) follows the shared elicitation method.**
> Grilling to a shared understanding, one question at a time each with a
> recommended answer, looking facts up in the code instead of asking, challenging
> terms against the glossary, edge-case stress-tests, and the **coverage
> checklist that is not finished until every context dimension is answered or
> recorded `Basis: assumed`** are binding and live in
> `shared/requirement-elicitation.md`. The Goal and Acceptance Criteria written
> in Step 1 are the output of that method; for iterate the surface-specific
> question is the scope of *this* change plus the MINT-vs-FOLD gate (Step 2).
> Write the criteria under `shared/fr-authoring.md`.

## Step 1: Iterate Spec (medium+ only)

Create `.shipwright/planning/iterate/{date}-{short-description}.md` using
this template:

```markdown
# Iterate Spec: {short-description}

- **Run ID:** {run_id}
- **Type:** {feature | change | bug}
- **Complexity:** {level}
- **Status:** draft

## Goal
{1-2 sentences — populated from interview answers (Section G)}

## Acceptance Criteria
- [ ] {AC from interview — concrete, testable}
- [ ] {AC 2}

**Frozen pre-build record (Step 2a):** `AC frozen: sha256:{hash}` (copied from the plan stub) and the exact
AC text added or changed (old and new for a change), the outcome exemption, or the AC id a restore restores.

## Spec Impact
{Classify how this iterate changes the FR spec — see Step 2.}
- **Classification:** {add | modify | remove | none — one or more}
- **ADD** (new FR appended): {FR-XX.YY — short title, or `none`}
- **MODIFY** (existing FR changed): {FR-XX.YY — what changed, or `none`}
- **REMOVE** (FR retired → `## Removed Requirements`): {FR-XX.YY, or `none`}
- **NONE justification:** {required only when Classification is solely
  `none` — why this feature/change touches no FR}

## Out of Scope
- {from interview answer — what explicitly will NOT be done}

## Design Notes
{Filled during Design Check. Include affected mockup files,
 design tokens applied, new vs modified components, deviations
 from visual guidelines with justification}

## Affected Boundaries
{Producer/consumer pairs for any changed serialized format.
 Triggers Boundary Probe sub-step in Build TDD when `touches_io_boundary`
 risk flag fires.

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| {file:fn} | {file:fn} | {env / JSON / YAML / ...} |

If no boundaries touched: write `n/a` with one-line justification.}

## Confidence Calibration
{Mandatory at medium+; mandatory at small when `touches_io_boundary`
 fires. Empirical probes run before F0 Fresh Verification Gate.

- **Boundaries touched:** {list from "Affected Boundaries" above}
- **Empirical probes run:** {one-line per probe + finding — real
  round-trip / edge-case tests, not "I re-read the diff"}
- **Test Completeness Ledger:** {every testable behavior this diff
  introduces/changes — one row each, `tested` (evidence) or `untestable`
  (closed-vocab reason_code). The "could-test-but-didn't" disposition is
  forbidden. Mirror into the F5 `iterate_latest.test_completeness` block;
  the F11 verifier `check_test_completeness_ledger` enforces it.}

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | {behavior} | tested | {test_name::case PASSED} |
  | 2 | {behavior} | untestable | {requires-prod-credential ·
  requires-external-nondeterministic-service · requires-physical-device ·
  requires-manual-visual-judgment · requires-interactive-tty ·
  covered-by-existing-test} |

- **Confidence-pattern check:** {asymptote (depth): has any "are you
  confident?"-style question already produced "yes" + a subsequent finding
  this run? If yes, run one more probe before F0. AND coverage (breadth):
  every ledger row `tested`/`untestable`, 0 untested-testable?}}

## Verification (medium+)
{Mandatory at medium+. The runner that will produce the F0.5
 surface_verification block.

- **Surface:** web | cli | api | none
- **Runner command:** {exact command F0.5 will execute}
- **Evidence path:** {where output lands}
- **Justification (only if surface=none):** {one line — why no startable
  surface exists for this change}}
```

## Step 2: Spec Update — classify the Spec Impact (always)

1. Identify which spec file(s) cover the affected area.
1a. **MINT-vs-FOLD gate — run this BEFORE choosing ADD.** Read
   `shared/fr-authoring.md` (§3). Ask: *is this a capability the product
   did not have before?*
   - **FOLD → classify MODIFY, do not add a row.** The change *completes,
     polishes, fixes, extends,* or is *"Phase N of"* something that already
     exists. Append acceptance-criteria lines to the existing FR instead.
     Folding is the common case.
   - **MINT → classify ADD.** Only for a genuinely new, user- or
     system-observable capability.
   - A new endpoint, route, or component is **not** by itself a new
     capability — it is usually the plumbing of one that already has an FR.
   - Altitude self-check before writing the row: could a non-technical
     person read the FR *name* as something the product can do? If the name
     needs a verb like GET/POST, a `snake_case` symbol, an ADR number, or an
     iterate slug, it is a route or a change — FOLD, don't MINT.
2. **Classify the spec impact** as one or more of ADD / MODIFY / REMOVE, or
   NONE. Record it in the iterate spec's `## Spec Impact` section
   (medium+) and carry the same FR IDs into F7 (`--spec-impact`,
   `--affected-frs`, `--new-frs`).
   - **ADD** — a genuinely new user- or system-observable capability that
     survived the MINT-vs-FOLD gate: append a new FR table row + an
     acceptance-criteria block. The new FR ID goes to F7 `--new-frs` (and
     `--affected-frs`).
     - **Number it deterministically:** the new FR takes the **next free
       number in its split** — the highest `FR-{split}.NN` in use plus one,
       counting **both live and `### Removed Requirements` rows** so a
       retired number is never reused. Never guess a number. If a parallel
       iterate already took it, resolve the duplicate at merge — never keep
       two rows on one ID.
     - **Name + description follow `shared/fr-authoring.md`:** a capability
       phrase (~6 words, no verbs/symbols/paths/ADR numbers), and a plain
       business-language description a product owner can sign off. Put the
       implementation detail in `architecture.md`, not the row.
     - **The row has seven cells:**
       `| ID | Area | Name | Priority | Description | Basis | Layers |`.
       `Area` is the split's name (it must match the ID's group digit — if it
       does not, the FR belongs in a different split). `Basis` is ONE value
       from `interview` / `code` / `observed` / `tests` / `assumed` /
       `other: <reason>`; anything else is a hard audit failure, and a blank
       cell fails too — use `assumed` when nobody has confirmed it, and
       **name what would settle it** (who to ask, or what to try) as an
       acceptance criterion on that requirement. The settlement never goes in
       the cell itself: `assumed — ask the PO` is malformed and fails audit
       `I5`. With the operator present, an unanswered-but-answerable question
       is unasked rather than unknowable — see `shared/fr-authoring.md` §4a.
     - **`Layers` — read this before you type it. It can hard-abort this
       iterate.** Two forms, and the choice is binding:
       - `unit, e2e` **(bare) is a declaration.** Compliance treats it as
         authoritative: every named layer with no executed-passing
         `@FR`-tagged test becomes a HARD coverage failure and finalization
         **exits non-zero**. There is no bypass — no env var, no flag, no
         label. A newly added FR is always counted as behaviour-changed in
         the iterate that adds it, so **a bare cell on an FR whose tests do
         not exist yet aborts the run.**
       - `unit, e2e (inferred)` is advisory and never blocks.
       **So: write the bare form only if the tests land in THIS iterate**
       (which is the normal TDD case, and is the preferred one — declare what
       you are about to cover). **If the layers are a guess, write
       `(inferred)`** — the honest cell. Do NOT reach for `Basis: assumed`
       instead: they are different columns answering different questions
       (`Basis` = how we know the requirement, `Layers` = what it must be
       tested at), and a requirement can be `Basis: interview` with entirely
       unverified layers. Mind the space: `unit (inferred)` parses,
       `unit(inferred)` silently yields NO required layers.
       **Manual by construction, not a deferred gap:** a brand-new FR has no
       CI-confirmed test evidence yet, so there is nothing an automated writer
       could promote from — `shared/scripts/tools/promote_required_layers.py`
       (P3.5) only ever *widens* an EXISTING binding from evidence a later CI
       run confirms; it never mints the first cell on a row that did not exist
       when that evidence was produced. Typing this cell by hand on CREATE is
       therefore the whole mechanism for this path, not half of one — the
       automation exists for the widen-an-existing-FR case (see Path B's
       MODIFY section for where that runs).
   - **MODIFY** — an additive side-effect or changed behavior of an
     existing FR, **and every FOLD from the gate above**: update the FR
     table-row description + append new
     `- (E) Given … when … then …` acceptance-criteria lines covering
     the new behavior + any idempotency / no-op guarantees. The FR ID
     goes to F7 `--affected-frs`. Reference the run_id + ADR.
     - Keep the description **plain business language**
       (`shared/fr-authoring.md` §1) — do not let an edit smuggle a file
       path, symbol, or ADR number into a row that was previously clean.
       The run_id/ADR provenance belongs in the AC line, not the description.
   - **REMOVE** — the change deletes a user-visible capability: move the
     FR row out of `## 2. Functional Requirements` into a
     `### Removed Requirements` subsection — never silently delete it.
   - **NONE** — a behavior-preserving internal refactor with no
     user-visible change. Record a one-line justification.
3. **NONE is a classification that must be *justified*, not a default.**
   The Phase Matrix marks this step `always` for FEATURE — that is
   load-bearing. The F11 finalization verifier FAILS a feature/change
   iterate whose **work up to the recorded commit** touched no `spec.md`
   unless `spec_impact=none` + a justification was recorded at F7. It reads
   the merge-base range where a trunk base can be corroborated (the single
   commit otherwise), so an integration merge at HEAD normally does not hide
   the spec.md your own commit carried.
4. If `shipwright_sync_config.json` exists, add/update mappings for the
   affected files.

> **AC shape (medium+).** ACs MUST be assertion-shaped (mechanically
> verifiable by the F0.5 runner), not story-shaped. Story-shaped ACs
> cannot be empirically driven and silently degrade F0.5 to spec-only
> authorship.

## Step 2a: Pre-build AC — the promise, frozen BEFORE any code (FEATURE and CHANGE, every complexity)

Step 2 decides which requirement a change belongs to; this step writes down **what it promises**, before the
build, so the promise cannot drift to fit the code. It runs at trivial and small too. A bug fix is not asked here
(a fix that gives the product behaviour no AC states is a CHANGE).

1. **Declare one item per promise** in a JSON file written with the Write tool (free text never goes through a
   shell command line); the shape is in the docstring of `shared/scripts/tools/ac_decision.py`:
   - `add`: the exact AC text (WHAT/WHY, `shared/fr-authoring.md`; a business user can read it, no mechanism,
     file, flag or threshold) and `owner_fr`, the single FR the MINT-vs-FOLD gate chose (blank if none fits).
   - `change` / `remove`: `ac`, the current text copied exactly from the catalog (`old_text`; the tool compares it) and the new text (`new_text`).
   - `restore`: `restores_ac`, the id of the AC the work brings back. **It must exist in the catalog** — the tool
     checks. If no AC names the promise, it is a catalog gap: declare an `add`.
   - `exempt`: `exempt_kind` `no-observable-change` or `how-only`, and `exempt_reason` in words about the
     OUTCOME: "no user- or operator-observable behaviour changes, because ...". Ask yourself what a user or
     operator would see, do or rely on differently; if nothing, say so. **Never exempt by a path label, a
     complexity tier, or the words bug, trivial, tooling** — the tool refuses a reason that is only a label.
   - For an `add`/`change`/`remove` that may be asked about, also write `plain_new` / `plain_old`: one sentence
     about the outcome, no path, symbol, flag, number with a unit (the tool refuses a question that has one).
     Set `request_open: true` when the request leaves open what the user sees.
2. **Run it:** `uv run "{shared_root}/scripts/tools/ac_decision.py" --project-root "{project_root}" --from-json "{ac_json}" --out "{decided_json}"`
   (add `--autonomous` under `--autonomous`). **First matching row wins:** (1) an existing AC is changed or
   removed: ask · (2) no single FR owns it: ask · (3) the AC text trips the lexical HOW test (path, snake_case,
   flag, ADR number, slug, number with a unit, GET/POST — the Step 1a altitude self-check, as code): ask ·
   (4) the request leaves open what the user sees: ask · otherwise **auto**, and the PR body lists it (`references/F11.md`).
   A `how-only` exemption always asks (it is the operator's call); `no-observable-change` and a restore
   with an existing AC are decided alone and counted. Exit `0` decided · `10` ask · `2` fix the declaration.
3. **Ask (exit 10), interactively:** put each printed question to the operator in exactly its words —
   "This change gives the product a new promise: <one sentence>. Until now: <old promise or nothing>. Should it
   hold like this? 1 Yes, write it. 2 No, instead: <text>. 3 This is only how it is built, not a promise."
   (a removal says "Until now this held: <promise>. After this change it no longer holds."). Write the answer into
   the item (`"answer": {"choice": "yes|no|only-how", "text": "..."}`) and run the tool again. **Under
   `--autonomous` an ask never auto-approves:** a campaign unit writes the printed `escalation` to its
   `result.json` and returns `status:"escalated"`, `reason_code:"ac_question_requires_operator"` (commit and
   push nothing); a standalone run records `record_hard_blocker.py --reason-code operator-only-decision`.
4. **Freeze:** write the plan stub NOW, before the build: `write_plan_stub.py ... --ac-decision "{decided_json}"`
   (`references/F5b.md`). It holds `AC frozen: sha256:...`, the items and `AC decisions`. At medium+ copy the hash
   line into the iterate spec's Acceptance Criteria. A later edit of the text re-runs the tool and shows as a
   diff in the stub; the spec-reviewer reads it. Pass `"ac_decisions"` (the printed list) in the F5b extras.
   The exemption maps to `spec_impact: none` with `behavior-preserving` (no-observable-change); F11
   `check_pre_build_ac_recorded` warns (never blocks) when the record is missing or edited.

## Step 3: Mini-Plan (persisted at every tier that runs it)

See `references/iteration-planning.md` for protocol. Save as
`.shipwright/planning/iterate/{date}-{desc}-miniplan.md` at `small` and at
`medium+` alike — only the content depth (work breakdown, alternative
approach) is medium-only, not the file itself.

## Step 3b: User Approval Gate (medium+)

Present the iterate spec + mini-plan summary to the user:

> "Here is my plan:
> - **Scope:** {AC summary from iterate spec}
> - **Approach:** {mini-plan summary}
> - **Out of scope:** {boundaries from iterate spec}
>
> Shall I proceed, or would you like to adjust scope, ACs, or approach?"

**CRITICAL: Wait for user approval before proceeding to build.**

For trivial/small: skip (the confirmation question in Section G is sufficient).

## Step 4: External LLM Review (medium auto, or --review flag)

See `references/iteration-planning.md` for invocation.

## Step 5: Design Check (if UI)

See `references/design-and-testing.md` for 2-tier protocol.

## Step 6 — Build (full body)

The Step 6 / Step 7 / Step 7.5 / Step 8 / Step 9 / Step 10 / Step 11a /
Step 11b / Step 12 / Step 13 / Step 14 headings remain in SKILL.md so the
existing drift-protection tests anchor on them. SKILL.md carries the
governance-rule anchors (Test-Update-Klausel, Registry-driven SSoT,
Silent-skip CI-discipline) inline; this file is reference prose only.

### Tag each test with the requirement it proves

Write the tag together with the test, never afterwards: `@pytest.mark.covers("FR-XX.YY/ACnn")`
on the test function (or once on its `Test*` class), `{ tag: ['@FR-XX.YY'] }` or a preceding
`// @covers FR-XX.YY` on a Playwright/Vitest test (a `describe` tag covers the tests inside it).
Name the AC the test proves; a bare `FR-XX.YY` is allowed when no single AC fits. Write the id
as a string literal: `covers(AC)` with a module constant is a malformed tag (`non_string_arg`),
because the collector reads the source, not the running value. Tags should
point at this iterate's Spec-Impact FRs; a tag outside them WARNs. **Enforced at F11** by
`check_test_tag_binding`, at every complexity: an untagged added test, a stripped tag, an edited
legacy untagged test, or a tag that resolves to no live FR STOPs the run. The two legitimate
exceptions are recorded per test in the F5c `exemptions` block, never per diff:
`fixture-or-helper` (a function pytest does not collect as a test) and `mechanical-refactor`
(the body changed only by renamed identifiers, e.g. a fixture rename across legacy tests).

### Migration apply (if migration files were created during build)

Read `migrations` config from the stack profile (loaded in Step B2).

**Preflight + Apply:**
1. Run `{migrations.preflight_cmd}` — verify environment ready
2. If `safe_nonprod_only` is true, verify target is non-production
3. If preflight fails: Print diagnostic, instruct user to fix. **Stop.**
4. Run `{migrations.apply_cmd}`
5. If apply fails: **Stop immediately.** Do not run tests. Ask user.
6. Verify with `{migrations.list_cmd}`

**Post-migration manual steps:**
7. Check `post_apply_manual_steps` — match `trigger_tag` against changes
8. If matched: inform user, note blocked test areas, wait for confirmation

Apply immediately after creating the migration, before running tests.

### Test commands

```bash
npx vitest run
npx tsc --noEmit

# Integration tests (if CRUD/DB changes)
npx vitest run --config vitest.integration.config.ts

# pgTAP tests (if new RLS migrations)
supabase test db
```

## Step 13: Escalation Check

See `references/mid-flight-escalation.md`.

## Step 14: Finalize

Go to Finalization (F0 .. F12) in SKILL.md.
