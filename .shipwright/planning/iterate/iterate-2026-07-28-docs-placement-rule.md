# Iterate ADR — docs/ holds what someone wrote for someone to read

- **Run-ID:** iterate-2026-07-28-docs-placement-rule
- **Standalone iterate** (NOT a campaign).
- **Complexity:** medium · **spec_impact:** none · **affected_frs:** [] ·
  **change_type:** docs
- **Owns:** the written convention for where a repository document lives, and
  the location of the gate-catalog render.

---

## Problem statement

`docs/` currently holds three different kinds of file, and no written rule
separates them:

1. **Hand-written instructions that get read** — `guide.md`,
   `hooks-and-pipeline.md`, `security-ci-setup.md`,
   `setup-guide-jelastic-infomaniak.md`. These belong.
2. **A generated artifact** — `gate-catalog.md`, rendered from
   `shared/config/gate_catalog.json` by `resolve_gate_policy.py --render-doc`.
   It is never linked from `guide.md`, so nobody arrives at it, and it needs a
   dedicated drift test to stay honest about being a copy.
3. **Records of finished work** — `docs/migrations/` mixes two audiences under
   one folder name. Two files are genuine instructions for a *user* whose
   project predates a change (`multi-session-to-single-session.md`,
   `requirements-catalog-merge.md`). Five are records of migrations *this
   monorepo* completed between April and June 2026 and will not repeat.

The cost is not disk. It is that a reader cannot tell, from the location, which
kind of file they have opened — and that the absence of a rule invites the next
stray file to land in the same place. The concrete evidence that the folder has
stopped meaning anything: `shared/templates/claude-md-template.md` ships a
sentence into **end-user projects** pointing them at `docs/migrations/` for
per-artefact migration guides they can never use.

## The decision this needed

A placement rule with three clauses, written down where the next contributor
will hit it (`CLAUDE.md`), because two clauses are obvious and the third is the
one that was actually missing.

> **`docs/` holds hand-written instructions** — for users and for developers
> alike. The test is not who reads it, but that someone *wrote* it and someone
> *reads* it. `guide.md` and `hooks-and-pipeline.md` sit there as equals.
>
> **`.shipwright/` holds the artifacts Shipwright itself keeps** — specs under
> `planning/`, evidence under `compliance/`, architecture and decision memory
> under `agent_docs/`. They come out of runs; they are not composed by hand.
>
> **A file that is neither belongs nowhere.** A record of finished work is
> deleted — git history keeps it. A generated file is not filed among the
> hand-written ones: if it is committed at all, it lives **next to the source it
> is generated from**, so that source and render are read together and the
> drift test has an obvious subject.
>
> For neither case is the answer "then put it under `.shipwright/`".
> `agent_docs/`, `planning/` and `compliance/` are read as well — they are not a
> parking lot for files nobody reads.

The third clause is the load-bearing one. Without it, the correct-looking move
is to relocate `gate-catalog.md` into `.shipwright/agent_docs/` — which is
filing, not deciding, and puts an unread file in a read place.

## Alternatives considered

1. **Move the strays into `.shipwright/agent_docs/`.** Rejected. It answers
   "where else?" instead of "should this exist here at all?", and `agent_docs/`
   is itself a read directory.

2. **Delete `gate-catalog.md` together with its drift test**, keeping
   `--render-doc` as an on-demand command. This was the planned route and was
   **rejected mid-flight** during context loading: `shared/constitution.md`
   (§Programmatic Enforcement, "This table is a seed, not the register") and
   `.shipwright/planning/campaigns/2026-07-24-req3-constitution-enforcement-register-DESIGN.md`
   §"Pattern to copy" both name *machine-readable catalogue + generated doc +
   drift test* as the three-part template a planned REQ-3 Phase 3 register is to
   copy — "Copy all three." Deleting two of the three parts would quietly
   reshape a campaign that was not under discussion. A fence with a visible
   reason; left standing.

   The technical claim behind the original proposal still holds and is worth
   recording: `test_gate_catalog.py` (schema, unique ids, no constitution-locked
   gate auto-answers) is what guards the catalogue's *integrity*, and it does
   not reference the markdown at all. `test_gate_catalog_doc_sync.py` guards
   only that the committed render is not stale. Deleting the render would have
   lost no integrity coverage — it would have lost a cited template.

3. **Link `gate-catalog.md` from `guide.md` and leave it in place.** Rejected as
   insufficient: it makes the file reachable but leaves a generated artifact
   among hand-written ones, which is the thing the rule exists to prevent. The
   useful half of this idea is kept — see AC4.

## Design

### D1 — The rule is written before anything moves

`CLAUDE.md` gains a "Wo Dokumente hingehören" section carrying the three clauses
above. It goes in **first**, so every deletion in this diff has a stated reason
in the repository rather than only in a commit message.

### D2 — The gate-catalog render moves next to its source

`docs/gate-catalog.md` → `shared/config/gate_catalog.md`, adjacent to the
`gate_catalog.json` it renders. All three parts of the cited pattern survive;
only the address changes, and it becomes a better template — source and render
in one place, which is the shape REQ-3 will copy.

`test_gate_catalog_doc_sync.py` is **retargeted, not deleted**. Its regeneration
hint changes with it.

### D3 — Five records of finished work are deleted

| File | Evidence it is finished |
|---|---|
| `.shipwright-relocation.md` | `ARTIFACT_MIGRATIONS["planning"].status == "migrated"` |
| `.shipwright-designs-relocation.md` | `…["designs"].status == "migrated"` |
| `.shipwright-agent_docs-relocation.md` | `…["agent_docs"].status == "migrated"` |
| `.shipwright-compliance-relocation.md` | `…["compliance"].status == "migrated"` |
| `artifact-migration-reference.md` | all four above; the doc says so itself at line 1021 |

Git history keeps all five.

### D4 — One dormant tool goes with the reference doc

`print_next_migration_prompt.py` is wired into no hook and no skill. With all
four migrations `migrated`, `render_prompt` returns `_all_done_message()`; the
branch that names the reference doc (line 82) is unreachable. Deleting the doc
without the tool would leave a script whose only content-bearing output is a
path to a file that no longer exists.

**This is knowingly outside a docs change.** Constitution Pre-Phase Principle 3
says a docs change that edits source code is mis-scoped and should be split. It
is kept in scope because the operator authorised it explicitly and the coupling
is real — the tool's output *is* the deleted document. Recorded here rather than
passed over silently.

### D5 — The path-canon exemption is measured, not assumed

`shared/scripts/lib/artifact_migrations.py` carries `"docs/migrations/**"` as a
path-canon exemption in four places (once per migration) because the deleted
documents deliberately contained legacy path strings. After the deletions the
exemption is **removed and the check re-run**. Green → it stays removed. Red →
the two surviving user guides contain legacy paths themselves, the pattern goes
back with that as its stated reason. The outcome is recorded in AC7 either way;
guessing is not an option here because a wrong guess turns a documentation
cleanup into a red gate that names innocent files.

### D6 — What a reader actually wanted from the gate catalog

`gate-catalog.md` was never linked from `guide.md`, so the question it answers —
*"which decisions does the pipeline make without asking me?"* — is currently
unanswered in the user-facing documentation. `guide.md` gains a short section
naming the three policies (`auto-default`, `orchestrator-approve`, `hard-stop`)
and pointing at `shared/config/gate_catalog.json` for the full list. The
instruction lands where instructions live; the generated table stays next to its
source.

### D7 — A maintainer's name comes out of a public catalogue

`shared/config/gate_catalog.json` carries three annotations naming an individual
(`SENSITIVE (Sven)` ×2, and a deferral attributed by name and date). The repo is
public. The substance of each annotation — that a human must eyeball the visual
direction, that plan review is deferred — is preserved; the name is removed.

## Acceptance criteria

- **AC1** — `CLAUDE.md` contains the placement rule with all three clauses,
  including the explicit statement that `.shipwright/` is not the answer for a
  file nobody reads.
- **AC2** — `shared/config/gate_catalog.md` exists and its text equals
  `render_catalog_markdown(load_catalog())` **modulo line endings**;
  `docs/gate-catalog.md` does not exist. Not byte-equality: `core.autocrlf=true`
  with no `.gitattributes` rule for `.md` means a Windows checkout holds CRLF
  while the renderer emits LF, so a byte comparison would fail for every Windows
  contributor. The drift test's `read_text()` normalisation is deliberate.
- **AC3** — `test_gate_catalog_doc_sync.py` passes against the new path, and
  fails if the render is stale (verified by mutating the catalogue in a scratch
  copy, not by assertion-reading).
- **AC4** — `docs/guide.md` contains a section naming the three gate policies
  and pointing at `shared/config/gate_catalog.json`.
- **AC5** — `shared/config/gate_catalog.json` contains no personal name; the
  three annotations keep their substance.
- **AC6** — The five documents in D3 are gone, and no live reference to them
  remains: `.gitignore` comments, `shared/templates/claude-md-template.md`,
  `artifact_migrations.py`, `stale_artifact_detector.py`,
  `docs/hooks-and-pipeline.md`. `CHANGELOG.md` and `CHANGELOG-unreleased.d/`
  are historical and stay untouched.
- **AC7** — The path-canon check is run with the `docs/migrations/**` exemption
  removed, and the result is recorded. Exemption removed on green; restored with
  a stated reason on red.
- **AC8** — `print_next_migration_prompt.py` and its test are gone; the eight
  allowlist entries naming them in `artifact_migrations.py` are gone;
  `ARTIFACT_MIGRATIONS` and every path-canon check still pass.
- **AC9** — `docs/` afterwards contains only hand-written instructions:
  `guide.md`, `hooks-and-pipeline.md`, `security-ci-setup.md`,
  `setup-guide-jelastic-infomaniak.md`, `images/`, and `migrations/` holding
  exactly the two user-facing guides.
- **AC10** — The two surviving guides keep every code reference that points at
  them: `orchestrator_pkg/constants.py` (`MIGRATION_DOC`), `master_stop_check.py`,
  `run/SKILL.md`, ADR-109, `test_requirements_catalog_parsers.py`.
- **AC11** — `2026-07-24-req3-constitution-enforcement-register-DESIGN.md` names
  the render's new path, so the template it tells a future campaign to copy is
  the one that exists.
- **AC12** — Full test suite green per test root; `uvx ruff@0.15.15 check .`
  clean.

## Scope

**In:** `CLAUDE.md`, `docs/guide.md`, `docs/hooks-and-pipeline.md`,
`docs/gate-catalog.md` (moved), `docs/migrations/` (5 deletions),
`shared/config/gate_catalog.json` + `.md`, `shared/tests/test_gate_catalog_doc_sync.py`,
`shared/scripts/lib/gate_policy.py`, `shared/scripts/tools/resolve_gate_policy.py`,
`shared/prompts/single-session-gate-discipline.md`,
`shared/scripts/lib/artifact_migrations.py`,
`shared/scripts/lib/stale_artifact_detector.py`,
`shared/scripts/tools/print_next_migration_prompt.py` + test,
`shared/templates/claude-md-template.md`, `.gitignore`, REQ-3 DESIGN doc.

**Out:** `docs/hooks-and-pipeline.md` stays in `docs/` — it is hand-written and
read, which is the whole test. `CHANGELOG.md` / `CHANGELOG-unreleased.d/`
historical entries. `ARTIFACT_MIGRATIONS` itself and the path-canon machinery.
The REQ-3 register's own design (only its path reference is corrected).

## External-Plan-Review-Findings (Step 3.5 — GPT-5.6 + Gemini 3.1 Pro via OpenRouter, both succeeded)

Both returned `revise`. Every finding was answered with a probe, not a judgement.

| # | Src | Sev | Finding | Disposition |
|---|---|---|---|---|
| 1 | GPT | med | Deleted tool may have callers beyond hooks/skills (CI, Makefile, packaging) | **Probed, clean.** No hits in `.github/`, `Makefile*`, any `pyproject.toml`, `scripts/`. |
| 2 | GPT | med | No repo-wide check for the old render path | **Done.** Repo-wide grep for `docs/gate-catalog`: zero live hits. |
| 3 | GPT | med | AC7 names no durable location for the measurement record | **Accepted, resolved by outcome.** Exemption came out green, so the record is its absence plus a passing suite — which is GPT's own preferred form. |
| 4 | GPT | low | Regeneration may work by coincidence, not via the documented command | **Probed.** Deleted the render, ran the documented command from the repo root: recreated at the new path, `docs/gate-catalog.md` not resurrected, drift test green. |
| 5 | GPT | low | Name removal is narrower than the stated concern | **Accepted, partly acted on.** Repo-wide scan separated authorship metadata (LICENSE / `plugin.json` / `pyproject.toml` — correct, kept) from prose use. Fixed the second occurrence in a file already touched; the four in other subsystems filed as `trg-1a215186` rather than widened into this change. |
| 6 | GPT | low | `update-marketplace.sh` in the risk table but not in scope/ACs | **Accepted, clarified.** It syncs the local plugin cache (whole `shared/`, deletions included) and touches no tracked artifact, so it cannot be an AC. Already mandated by CLAUDE.md; runs after push. |
| 7 | Gem | med | Step order regenerates before retargeting the generator | **Correct about the written plan, not the execution.** Generator and drift test were retargeted first; the render's own header proves it. |
| 8 | Gem | **high** | `ARTIFACT_MIGRATIONS` may hold hardcoded paths to the deleted records | **Refuted.** Its fields are `name / canonical / legacy_dirname / old_path_patterns / ast_check_string / status / started / completed` — no field holds a doc path. |
| 9 | Gem | low | grep CI configs for the old render path | **Covered by #2**; re-checked `.github/` explicitly. |

## External-Code-Review-Findings (Step 3.7 — GPT-5.6 succeeded; Gemini returned degraded/truncated)

| # | Src | Sev | Finding | Disposition |
|---|---|---|---|---|
| 1 | Gem | **high** | `--output` is not a real flag; the embedded regeneration command will error | **Refuted with evidence.** `--help` documents `--output OUTPUT` ("shell-agnostic — avoids a PowerShell `>` re-encoding the doc to UTF-16"); it pre-dates this change and was invoked successfully three times here. Gemini's fix — revert to `>` — would reintroduce the exact UTF-16 corruption the flag exists to prevent. The response was flagged degraded/truncated. |
| 2 | GPT | med | New iterate documents carry legacy paths and are not allowlisted, so path-canon likely fails; AC7 unrecorded | **Refuted, and the second half acted on.** All four allowlist blocks already carry `.shipwright/planning/iterate/**.md`. Path-canon re-run after every change: 4 passed. That run **is** the AC7 record. |
| 3 | GPT | low | `read_text()` normalises CRLF, so AC2's "byte-identical" is not enforced | **Real defect — in the acceptance criterion, not the test.** `core.autocrlf=true` with no `.gitattributes` rule for `.md`: the index holds LF, a Windows checkout holds CRLF. The suggested byte comparison would fail for every Windows contributor; the normalisation is deliberate. AC2 was reworded to state the invariant actually verified. |

## Confidence Calibration

- **Boundaries touched:** a shipped runtime prompt (`single-session-gate-discipline.md`), a template written into user projects (`claude-md-template.md`), the path-canon allowlist, the gate-catalogue render contract, `.gitignore`. No serialisation format, no schema, no network or DB boundary — `touches_io_boundary` does not apply.
- **Empirical probes run:**
  1. *Does the deleted tool still do anything?* Ran it: `All 4 artifact migration(s) complete. Nothing pending.` — and it points readers at `artifact_migrations.py`, the same place the replacement docstring does.
  2. *Is the path-canon exemption still needed?* Removed it and ran the check: **green**. It existed only for the deleted documents. (AC7 record.)
  3. *Does the documented regeneration command actually target the new path?* Deleted the render, ran it verbatim from the repo root: recreated correctly, old path not resurrected, drift test green.
  4. *Would a byte comparison be stricter or just broken?* `core.autocrlf=true`, index holds LF, checkout holds CRLF → broken on Windows. Declined the suggestion, fixed the criterion.
  5. *Does `ARTIFACT_MIGRATIONS` reference the deleted docs?* Enumerated every field of every entry: no doc path anywhere.
  6. *Is the maintainer's name gone from live prose?* Repo-wide scan; authorship metadata separated from prose use; remainder filed as `trg-1a215186`.
- **Test Completeness Ledger:**

| # | Behavior introduced / changed | Status | Evidence |
|---|---|---|---|
| 1 | The render lives at `shared/config/gate_catalog.md` and matches the catalogue | `tested` | `test_gate_catalog_doc_sync.py::test_doc_exists` + `::test_doc_matches_generated_catalog` — 3 passed |
| 2 | The render may not drift back under `docs/` | `tested` | **New** `test_doc_lives_beside_its_source` — asserts the parent directory and the absence of `docs/gate-catalog.md`. Without it, a move back would still satisfy byte-equality and silently undo the rule. |
| 3 | Catalogue integrity survives the name removal | `tested` | `test_gate_catalog.py` — 15 passed, incl. the pinned sensitive-gate policies |
| 4 | No legacy artifact path is reintroduced once the exemption is dropped | `tested` | `test_artifact_path_canon.py` — 4 passed (caught two real violations in the new `CLAUDE.md` prose and forced the canonical spelling) |
| 5 | Deleting the dormant tool breaks no consumer | `tested` | Its own test deleted with it; three full test roots green (6880 passed); repo-wide grep for callers clean |
| 6 | `.gitignore` semantics unchanged by comment removal | `tested` | `test_gitignore_canon.py` (in `shared/tests`, green) — only comment lines were removed, no rule |
| 7 | The two surviving guides keep every code reference | `tested` | 6 reference sites enumerated and each target verified to exist |
| 8 | The regeneration command a maintainer copies works | `tested` | Probe 3 above (executed, not read) |
| 9 | `guide.md` gate-policy section reads correctly to a user | `untestable` — `requires-manual-visual-judgment` | Prose. Content correctness is pinned by `test_gate_catalog.py`'s policy assertions; readability is a human call. |
| 10 | `CLAUDE.md` placement rule is followed by future contributors | `untestable` — `requires-manual-visual-judgment` | An instruction to humans. Its one mechanisable half **is** enforced — see behavior 2. |

0 testable-but-untested.

- **Confidence-pattern check:**
  - *Asymptote (depth):* the riskiest claim was "this exemption is only there for the deleted files". It was measured, not argued — and measuring first also caught two violations I had introduced myself.
  - *Coverage (breadth):* three test roots (6880 passed), ruff clean, plus targeted greps for each deleted artefact's name.
  - *Integration composition:* `cross_component` does not apply — no merge/churn resolver, hook fan-out, phase validator or campaign-drain machinery is touched.
  - *Known limit, stated:* historical records that name the deleted playbook — `decision_log.md`, `adopt/enrichment.json`, two archived iterate specs, `CHANGELOG.md` — were **left alone**. They record what was true when written; rewriting append-only history to tidy a reference would be the larger error. AC6 covers live references only, which is what it says.
