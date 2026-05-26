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

If `.shipwright/adopt/preservation_log.json` exists, also surface a
"Preserved files" section in the handoff: count of files preserved, list
of `.preserved` backup paths, and a special call-out if any
`action: skipped_loadbearing` entry is present (the user must review
`.shipwright/adopt/CLAUDE.md.adopt-suggested` and merge manually).

2. If validation passes, build the commit message via the SSoT helper
   (per iterate-2026-05-23-security-adopt-compliance-snapshots — the
   trailing `Run-ID: adopt-<YYYY-MM-DD>-<repo>` line is what makes the
   commit a snapshot baseline for `audit_staleness.find_snapshot_commit`):

   ```python
   from lib.adopt_commit_template import build_adopt_commit_message
   msg = build_adopt_commit_message(
       project_root=Path(cwd),
       profile=<matched_profile>,
       scope=<matched_scope>,
       inferred_fr_count=<N>,
   )
   subprocess.run(["git", "commit", "-m", msg], check=True)
   ```

   Resulting message shape:

   ```
   chore(shipwright): adopt repository into Shipwright SDLC

   Adopted via /shipwright-adopt using profile=<profile>, scope=<scope>.
   Inferred <N> functional requirements from existing codebase.
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
Crawl:         <enabled|skipped: <reason>>
Review:        <completed|skipped: <reason>>
Security CI:   <installed (dormant) | preserved (existing file untouched)>
Env scaffold:  <created|updated|unchanged|skipped: <reason>>  → <abs path to .env.local>
Commit:        <sha>

Next steps:
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
