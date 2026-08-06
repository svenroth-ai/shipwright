# Step H — Validate, Commit, Handoff

1. Validate:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/checks/validate_adoption.py" \
  --project-root <cwd>
```

The output now carries `errors` AND `warnings`. Hard-stop on
`errors[]`. **Surface `warnings[]`** in the handoff (currently includes
the "few ADRs for repo size" plausibility check) — they're informational,
not blocking.

`errors[]` includes the two **honesty artifacts** (trg-1aa5a8ab):
`.shipwright/adopt/derived-catalogue.json` (Step E) and
`shipwright_known_failures.json` (Step E.18). Missing either means the handover
would present a derived catalogue as if someone had confirmed it, or an
inherited red suite as this project's own failure — so it blocks, and the error
names the step to re-run.

If `.shipwright/adopt/preservation_log.json` exists, also surface a
"Preserved files" section in the handoff: count of files preserved, list
of `.preserved` backup paths, and a special call-out if any
`action: skipped_loadbearing` entry is present (the user must review
`.shipwright/adopt/CLAUDE.md.adopt-suggested` and merge manually).

1a. **Stamp the seeded evidence with the commit onboarding read.** Run this
   **immediately before the commit in step 2** — not back in Step F. Step G sits
   between them, and any phase-completion regeneration in that window would
   substitute unstamped bytes while the run still reported success.

   ```bash
   uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/tools/refresh_compliance_docs.py" \
     --stamp-adopted --project-root <cwd> --base "<commit_at_adoption>"
   ```

   `--base` is the `commit_at_adoption` field of the single `adopted` event in
   `shipwright_events.jsonl` (written by Step E). **Pass it explicitly** — the
   mode never resolves `HEAD` for you, because at this point `HEAD` equals the
   recorded commit only if nothing has committed since, which resume, retry and
   operator intervention all break.

   Act on `status` — this list is exhaustive; anything not named here is a bug
   and should stop the adoption rather than be guessed at:

   - `ok` — all five markdown evidence documents now name the state they describe.
     Continue to step 2. (`ok` always means the **whole** set: the completeness
     refusals below come first, so there is no qualifier to remember to check.)
   - `no_base` — the recorded commit was absent, malformed or does not resolve (a
     repository with no commits yet). **This is not an error.** The set is
     complete, the documents carry their run id only, adoption continues, and
     step 2a is **skipped** — verification demands a `base=` and would reject a
     commit that is correct.
   - `no_documents` (non-zero exit) — none of the evidence documents exist at all,
     so Step F produced nothing. **Do not commit.** Re-run Step F.
   - `incomplete_set` (non-zero exit) — some exist and the ones in `absent` do
     not. **Do not commit.** `--verify-commit` presence-filters, so it would call
     what remains `verified`; this report is the only place the gap is visible.
     Re-run Step F.
   - `partial` (non-zero exit) — a document is present but carries no
     `Source-State:` banner to rewrite, so the set cannot be stamped completely.
     Nothing was written. **Do not commit.** Re-run Step F and try again; a
     half-stamped evidence set is worse than an unstamped one because it looks
     finished.
   - `write_failed` (non-zero exit) — the stamped bytes could not be written (a
     file held open, a permissions fault). The originals were put back; check
     `unrestored` for any that could not be. **Do not commit.** Fix the cause and
     re-run step 1a.

2. If validation passes, build the commit message via the SSoT helper
   (per iterate-2026-05-23-security-adopt-compliance-snapshots — the
   trailing `Run-ID: adopt-<YYYY-MM-DD>-<repo>` line is what makes the
   commit a snapshot baseline for `audit_staleness.find_snapshot_commit`):

   **Read the counts first.** `unconfirmed_fr_count` comes from
   `.shipwright/adopt/derived-catalogue.json` (`unconfirmed`), written by Step E.
   It is a **required** keyword — a caller that has not looked the number up
   cannot build the message at all, which is deliberate: the adoption commit is
   the most-read record of what onboarding produced, and this is the fact that
   went missing from it for years.

   **Read it through `read_summary`, never with a bare `json.loads`.** That
   helper runs the fail-closed checks (`confirmed` must be a real boolean AND
   must equal `basis in CONFIRMED_BASES`; stated totals must match the entries).
   Pulling `doc["unconfirmed"]` out directly would skip every one of them at the
   single place the count is published, so a forged catalogue could put a false
   number in the adoption commit.

   **Stage AFTER step 1a, never before it.** Step 1a writes the stamped bytes to
   the **working tree**, and `git commit` records the **index** — so staging that
   ran before the stamp puts the pre-stamp blobs in the adoption commit, and 2a
   then has to repair with its one permitted amend. Ordering was previously left
   to improvisation because nothing in this skill staged anything at all; with a
   stamp in the flow that is no longer harmless.

   **Look at what you are about to stage first.** This is a repository somebody
   else has been working in, and an untracked file there was never forced into
   `.gitignore` — a `.env`, a database dump, a scratch key. `git add -A` would put
   every one of them in a commit titled *"adopt repository into Shipwright SDLC"*.
   Adopt's own gitignore check classifies only adopt's OWN outputs, so nothing
   else is looking:

   ```bash
   git status --porcelain
   ```

   Every listed path should be one onboarding produced (`.shipwright/`,
   `CLAUDE.md`, `shipwright_*.json`, `CHANGELOG-unreleased.d/`, the CI scaffolds).
   **If anything else appears, stop and ask the operator** — do not stage it, and
   do not quietly narrow the commit either; a file they did not expect to see is
   a question, not an obstacle.

   ```python
   from lib.adopt_commit_template import build_adopt_commit_message
   from lib.derived_catalogue_doc import read_summary

   catalogue = read_summary(Path(cwd))          # raises CatalogueDocumentError
   msg = build_adopt_commit_message(
       project_root=Path(cwd),
       profile=<matched_profile>,
       scope=<matched_scope>,
       inferred_fr_count=catalogue.total,
       unconfirmed_fr_count=catalogue.unconfirmed,
   )
   subprocess.run(["git", "add", "-A"], cwd=cwd, check=True)   # AFTER 1a
   subprocess.run(["git", "commit", "-m", msg], check=True)
   ```

   Resulting message shape:

   ```
   chore(shipwright): adopt repository into Shipwright SDLC

   Adopted via /shipwright-adopt using profile=<profile>, scope=<scope>.
   Inferred <N> functional requirements from existing codebase.
   <U> of them are DERIVED AND UNCONFIRMED — no person has
   agreed they describe this product. Follow-up filed in the Triage Inbox
   (adopt-derived-catalogue-confirmation); counts in
   .shipwright/adopt/derived-catalogue.json.
   Inherited test failures and coverage gaps recorded in
   shipwright_known_failures.json, not counted as this project's own.
   Seeded compliance artifacts (SBOM, change-history, RTM skeleton).
   Test evidence starts collecting from next /shipwright-test run.

   See .shipwright/agent_docs/decision_log.md for the adoption ADR
   (id is `max(existing) + 1`, 3-digit zero-padded — ADR-001 on greenfield).

   Run-ID: adopt-<YYYY-MM-DD>-<repo-name>
   ```

   **Do not assemble the message by hand** — the helper enforces the
   Run-ID regex (`^adopt-\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*$`) and
   the date-deterministic semantics covered by the helper's unit tests.

2a. **Verify the commit actually carries the stamp** — unless step 1a reported
   `no_base`, in which case skip this entirely.

   ```bash
   uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/tools/refresh_compliance_docs.py" \
     --verify-commit <sha> --project-root <cwd>
   ```

   This reads the blobs **out of the commit**, which is the only check that proves
   anything: `git commit` records the working tree, so a writer touching
   `.shipwright/compliance/*.md` between 1a and 2 substitutes unstamped bytes
   while 1a's JSON still says `stamped: [...]`.

   On `unstamped_in_commit`: re-run 1a and amend **once**, path-limited to the
   five evidence documents so unrelated work cannot ride along —

   ```bash
   git commit --amend --no-edit -- .shipwright/compliance/
   ```

   then re-verify. If it still does not match, **stop and report the paths**: a
   deterministic writer (a commit hook, a second session) is rewriting them, and
   amending in a loop would rewrite the adoption commit indefinitely.

3. Print a handoff message. The `Env scaffold:` line and the optional
   "Edit .env.local" block are populated from `results["env_local"]`
   (see Step E.5). Render the "Edit .env.local" block whenever
   `missing_keys` is non-empty — independently of `action`, so an
   `unchanged` outcome with placeholder-only entries STILL prompts the
   user. The list of keys MUST be derived from
   `results["env_local"]["missing_keys"]` (which already merges the
   profile's `required_env_vars` with the framework keys), NOT
   hardcoded:

```
================================================================================
ADOPTION COMPLETE
================================================================================
Profile:       <matched>
Scope:         <full_app|library|cli>
Features:      <N> FR(s) in .shipwright/planning/<split>/spec.md
               ⚠  <U> of them are DERIVED AND UNCONFIRMED — read from the code,
                  agreed by nobody. Traceability, coverage and drift all measure
                  against this catalogue, so those numbers describe the
                  catalogue until someone confirms it.
Inherited:     <F> pre-existing test failure(s) <observed|not measured>,
               <R> requirement(s) with no test, <D> test(s) switched off
               → shipwright_known_failures.json (recorded as INHERITED, not as
                 this project's own failures)
Crawl:         <enabled|skipped: <reason>>
Review:        <completed|skipped: <reason>>
Security CI:   <installed (dormant) | preserved (existing file untouched)>
Env scaffold:  <created|updated|unchanged|skipped: <reason>>  → <abs path to .env.local>
Evidence:      current as of <short base sha>, the commit onboarding read
               <| not stamped: repository had no commit to name>. It is refreshed
               at releases and on demand — NOT continuously — so it will age
               until you refresh it.
Commit:        <sha>

Next steps:
  •  Confirm the derived requirements with someone who knows the product —
     follow shared/requirement-elicitation.md. Onboarding filed the follow-up
     in the Triage Inbox as `adopt-derived-catalogue-confirmation`.
     Reading the code is a start; it is not enough on its own.
  •  Edit .env.local — fill in the keys still flagged as missing:
       <one bullet per key in results["env_local"]["missing_keys"]>
  •  /shipwright-iterate       — for all future feature/bug/refactor work
  •  /shipwright-test          — to collect first real test-evidence
  •  /shipwright-compliance    — on-demand detective audit of artifacts
  •  /shipwright-design        — to add UI mockups (optional)

  Keeping the audit evidence current — it does NOT update itself:
  •  /shipwright-changelog            — a release recomputes the evidence and
                                        checks it in, stamped with that release
  •  /shipwright-compliance --refresh-pr  — in between, opens an ordinary
                                        documents-only pull request under your
                                        own GitHub login. Needs a clean checkout
                                        of an up-to-date default branch.
  Day-to-day work deliberately does NOT carry these documents: a branch computes
  them from its own history and gets them wrong for the default branch.

Do NOT use /shipwright-project on this repo — adoption replaces it.
Do NOT use /shipwright-plan or /shipwright-build directly — /shipwright-iterate
handles both for adopted projects.
================================================================================
```

If `results["env_local"]["action"] == "skipped"` AND
`reason == "gitignore_enforcement_failed"`, surface a loud line in
the banner instead of the "Edit .env.local" block:

```
  ⚠  Env scaffold skipped — fix .gitignore permissions and re-run /shipwright-adopt
     ({results["env_local"]["error"]}). No .env.local was written.
```

The `Features:` values come from the same validated `read_summary` object as the
commit body — never recomputed by hand, and never re-read raw:

| Banner slot | Source |
|---|---|
| `<N>` / `<U>` | `read_summary(project_root).total` / `.unconfirmed` |
| `<F>` + `observed` \| `not measured` | `shipwright_known_failures.json` → `baseline_failure_count` + `baseline_observed` |
| `<R>` / `<D>` | same file → `inherited_coverage_gaps.counts` |

`baseline_observed: false` renders **"not measured"**, never "0 failures":
onboarding does not run an arbitrary repository's test suite, and a run that
never happened is a different fact from a run that found nothing — nor from the
shared reader's `present`, which only says a declaration exists.

Step 1's `validate_adoption.py` already parsed the file through that same reader,
so by the time the banner renders a contradictory catalogue has been rejected.
