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
