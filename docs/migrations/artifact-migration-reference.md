# Shipwright `.shipwright/<artifact>/` Migration Reference

This document is the SSoT for every future top-level artifact directory
that gets relocated under `.shipwright/`. It was written **after** the
planning relocation (Sub-Iterates A-G, 2026-04-26 -> 2026-04-27) and
extended with each subsequent migration: designs (2026-04-27),
agent_docs (2026-04-28). It is based on what actually happened, not on
the original plan's speculation.

Read this BEFORE starting a new migration (e.g. `compliance/`, `e2e/`,
`CHANGELOG-unreleased.d/`). Keep the structure unless you have a
specific reason to deviate.

---

## 0. Kickoff Prompt Template (copy-paste)

Send this to a fresh Claude Code session to start the next artifact
migration. Replace the three placeholders, then paste:

> I want to relocate the top-level `{LEGACY_DIR}` directory to
> `{CANONICAL_PATH}` following the validated pattern from the planning
> migration.
>
> **Before doing anything else, read these in order:**
> 1. `~/.claude/projects/c--Users-you-My-Projects-shipwright/memory/feedback_artifact_migration_pattern.md`
>    -- the always-read-first pattern memory
> 2. `docs/migrations/artifact-migration-reference.md` -- full SSoT
>    (12 sections incl. Architecture, Touchpoint Discovery, Sub-Iterate
>    Structure, Test Layer Schema, Allowlist, Verification Checklist,
>    External-Review template, Rejected Alternatives, Lessons,
>    Reference Commits, Quick-Start)
> 3. `docs/migrations/.shipwright-relocation.md` -- planning-migration's
>    user-facing migration doc; reuse the structure for `{ARTIFACT_NAME}`
>
> Then run:
>
>     uv run shared/scripts/tools/print_next_migration_prompt.py
>
> to confirm `{ARTIFACT_NAME}` is the next pending entry, and follow the
> 12-step quick-start in section 12 of the reference doc.
>
> **Plan boundaries (mandatory):**
> - One plan-file per sub-iterate in `~/.claude/plans/iterate-shipwright-relocation-{ARTIFACT_NAME}-{A..G}-*.md`
>   -- do NOT collapse into one mega-plan.
> - Hard cutover only -- no Grace-Period reads.
> - External review (`external_review.py --mode plan`) before
>   `ExitPlanMode` of the main plan.
> - Sub-Iterate G is mandatory and gated by **my** review before merge.
>
> Show me the touchpoint inventory first (3 Explore agents in parallel
> per § 2 of the reference doc), then the per-sub-iterate plan files,
> then the dual-LLM external review trace, then ask for approval.

Placeholders:
- `{LEGACY_DIR}` -- top-level dir name with trailing slash. Discover
  the next pending entry via
  `uv run shared/scripts/tools/print_next_migration_prompt.py` rather
  than guessing from a hardcoded list.
- `{CANONICAL_PATH}` -- target POSIX path under `.shipwright/`, e.g.
  `.shipwright/<artifact_name>`.
- `{ARTIFACT_NAME}` -- bare artifact name (no slash), used as the
  manifest key, plan-file slug, and in commit/PR titles.

### Rejected migration candidates (do NOT re-evaluate)

The following artefacts were considered as migration candidates and
**explicitly rejected**. Do not re-propose without first reading the
linked memo:

- **`e2e/`** -- `project_e2e_migration_rejected.md`. Playwright
  convention; external tooling (playwright.config.ts testDir, IDE test
  discovery, npm scripts, CI workflows) hard-codes root-level layout.
  Cost/benefit profile fundamentally different from
  Shipwright-internal artefacts.
- **`CHANGELOG-unreleased.d/`** -- `project_changelog_unreleased_migration_rejected.md`.
  Sibling-to-CHANGELOG.md by Keep-a-Changelog convention; human-authored
  release-doc family, not pipeline-state. Adjacent fragment-directory
  tools (towncrier, scriv, changelog-d, reno) all expect root-level
  discovery.

### Deferred migration candidates (do NOT re-evaluate without trigger)

The following artefacts were considered as migration candidates and
**explicitly deferred** — not rejected, but cost-without-benefit until
a named trigger fires. Do not re-propose without first reading the
linked memo and confirming a trigger has fired:

- **`shipwright_*_config.json`** files at project root
  (run/project/plan/build/test/security/compliance/design/deploy/changelog/sync)
  + `shipwright_events.jsonl` —
  `project_config_jsons_migration_deferred.md`. (Outlier
  `.shipwright_toolcall_count` was renamed to `.shipwright/toolcall_count`
  drive-by 2026-04-29; no separate migration.) Industry pattern
  actually *favors* root for per-tool configs with namespace prefix
  (`tsconfig.json`, `pyproject.toml`, `Cargo.toml`,
  `playwright.config.ts` etc.). Audited 2026-04-29: zero CI / S3 /
  audit-system / IDE-extension coupling. Largest migration to date
  (~582 Python hits / ~132 files), first *flat-file* migration so
  `ARTIFACT_MIGRATIONS` framework would need extension, plus
  highest-stakes bootstrap dependency (`_CONFIG_MARKER` in
  `project_root.py`). Reactivation triggers: (1) `resolve_project_root()`
  refactor needed for unrelated reason, (2) external coupling
  materializes (audit-upload / log-collector with fixed canonical
  path requirement), (3) WebUI builds a Shipwright-artefact
  Datei-Browser. If none have fired, the deferral stands.

---

## 1. Architecture Pattern (validated)

**Hard cutover + drift detector** -- not a Grace Period.

- Reads use only `.shipwright/<artifact>/`. No fallback path.
- Writes go only to `.shipwright/<artifact>/`. No double-write.
- A SessionStart hook scans for legacy top-level directories every
  time a Shipwright skill is invoked (full mechanics in § 1a below).
- Per-plugin local constants (`PLANNING_DIR`, `LEGACY_PLANNING_DIRNAME`)
  in each module that touches the path. **No central `paths.py` module**
  -- evaluated and rejected (see `project_paths_refactor_evaluated.md`).
  The artifact-migrations manifest is the SSoT for tests, the local
  constants are convenience.

**Why hard-cutover beats Grace-Period (validated):**

| | Grace-Period | Hard cutover + drift detector |
|---|---|---|
| Vergessener Writer entdeckbar | (verschwiegen) | sichtbar in stale-folders.md + JSON |
| Code-Komplexität in jedem Reader | two-path lookup | einzeilig |
| User-Pain wenn Drift | nicht sichtbar | direkt mit `git mv`-Anleitung |
| Bestehende Projekte | "läuft weiter" | bricht laut, mit Anleitung |

The planning migration confirmed this -- zero silent drift across
B-F because the lint catches it BEFORE commit, and the detector
catches it AT session start.

---

## 1a. Drift Detector -- complete mechanics

The detector is the *runtime* safety net. The Layer-1 lint catches
drift in source code before it ships; the detector catches drift in
*existing user projects* the first time they run a Shipwright skill
after upgrading. This subsection documents how it actually works, so
future migrations can reason about it without reading the source.

### Where it lives

- **Hook script:** `shared/scripts/hooks/check_artifact_drift.py`.
  Wired in every plugin's `hooks/hooks.json` as the third SessionStart
  hook, after `capture_session_id.py` and `phase_session_start.py`.
- **Scanner module:** `shared/scripts/lib/stale_artifact_detector.py`.
  Library code -- `scan_for_stale_legacy_dirs(project_root)` and
  `write_drift_report_or_clear(project_root, findings)`.
- **Manifest:** `shared/scripts/lib/artifact_migrations.py`. The hook
  iterates `ARTIFACT_MIGRATIONS` and considers only entries with
  `status in ("in_progress", "migrated")`.
- **Project root resolution:** `shared/scripts/lib/project_root.py`'s
  `resolve_project_root()`. Priority chain: `SHIPWRIGHT_PROJECT_ROOT`
  env var > cwd if it has a Shipwright config marker > the unique
  immediate subdir of cwd that has a marker > cwd as last fallback.
  The env var is *only* honored if the path is recognized as a
  Shipwright project (has `shipwright_run_config.json` or one of the
  secondary markers) -- this is intentional, to prevent the hook from
  scanning random directories.

### What it does on every SessionStart

1. Resolve the project root (chain above).
2. For each migration in `ARTIFACT_MIGRATIONS`:
   - If `status == "pending"`, skip entirely (no-op).
   - Otherwise, check whether `<project_root>/<legacy_dirname>` is a
     directory containing at least one file. The walk is **streaming**
     and capped at 50 files per migration (Gemini #5 perf fix); we
     don't materialize the full file list.
   - If found, record a finding with: artifact name, status,
     legacy_path, canonical_path, canonical_exists flag, sample_count
     (with "50" meaning "at least 50"), severity (`warn` for
     `in_progress`, `block` for `migrated`).
3. Write or delete `.shipwright/stale-folders.md`:
   - **Has findings:** render Markdown report, escape `[]()` and
     backticks in path names (Markdown-injection guard, GPT #15),
     write the file.
   - **No findings:** `unlink(missing_ok=True)` -- the file's absence
     is the canonical "drift-free" signal (Gemini #3 self-heal). No
     timestamp churn, no diff spam.
4. Decide exit code based on the worst severity in the findings:
   - **No findings** -> exit 0, no stderr noise.
   - **Only `warn` findings (in_progress)** -> stderr notice
     ("X legacy dir(s) seen during in-progress migration; see
     `.shipwright/stale-folders.md`"), exit 0. The migration can
     continue without the hook blocking it.
   - **Any `block` finding (migrated)** -> **warn-only** (a SessionStart
     hook cannot block a session, so exit codes are non-blocking). Emit a
     schema-valid `additionalContext` payload on stdout — the channel
     SessionStart delivers to the model — carrying the drift + `git mv`
     remediation, plus a stderr notice, exit 0. The user sees both
     `stale-folders.md` and the model-facing context. (WP4 corrected an
     earlier inert `exit 1` "hard-gate" claim; see the mode matrix below.)

### Self-healing behavior

The detector treats *file presence* as state and never edits Markdown
in place. The progression is:

- Drift exists -> write `.shipwright/stale-folders.md` (overwrite if
  it already existed -- new content always replaces stale content,
  but the file's mere existence is informative even on repeat runs).
- Drift resolved (legacy dir is gone) -> next SessionStart deletes
  the report. The deletion is silent; the next thing the user sees
  about the artifact is whatever Shipwright is doing at that moment.

This means: **if `.shipwright/stale-folders.md` is present in your
project, you have unresolved drift right now**. If it's absent, you
don't.

### Failure mode: detector itself crashes

The hook is **fail-open** (GPT #6). An outer try/except in
`hook_main` swallows any exception, prints a single-line stderr
notice ("[shipwright] drift detector skipped: <reason>") and exits
0. The session start does not fail because the detector itself is
broken. This trades one specific risk (false-negatives during a
detector bug) against a much larger one (bricking every Shipwright
session if the detector misbehaves).

### Migration-CLI workflow for a stale project

When the detector flags drift (warn-only) in an existing project:

```bash
# Inspect what was found
cat .shipwright/stale-folders.md

# Preview the move
uv run shared/scripts/tools/migrate_artifact_dir.py \
  --artifact <name> --project-root . --dry-run

# Execute -- prefers `git mv` if the legacy dir is git-tracked,
# otherwise falls back to shutil.move. Refuses non-destructively if
# the canonical destination already has content.
uv run shared/scripts/tools/migrate_artifact_dir.py \
  --artifact <name> --project-root .

# Commit the move
git add -A
git commit -m "refactor: relocate <name>/ to .shipwright/<name>/"
```

The next SessionStart will see no legacy dir and silently delete
`.shipwright/stale-folders.md`.

### What it deliberately does NOT do

- It does not move files. The CLI does that, on user invocation.
- It does not write anything to the legacy directory.
- It does not modify the manifest, the gitignore, or any tracked
  source.
- It does not phone home, log to disk outside `.shipwright/`, or
  read project content beyond directory names.
- It does not respect the `# artifact-path-canon: legacy` inline
  marker -- that's a Layer-1 lint construct for source files, not a
  runtime concept. The detector judges by directory presence alone.

### Mode matrix at a glance

| Status | Layer-1 lint | SessionStart hook | Migration CLI |
|---|---|---|---|
| `pending` | no-op | no-op | refuses (`unknown_artifact` if not in manifest yet) |
| `in_progress` | enforces (with allowlist) | warn-only, exit 0 | usable, recommended for early adopters |
| `migrated` | enforces (allowlist near-empty) | warn-only (additionalContext on stdout + stderr), exit 0 | the documented user-facing remediation |

---

## 2. Touchpoint Discovery (Explore-Agent Prompts)

For a new artifact `{ARTIFACT_NAME}` (e.g. `agent_docs`) with legacy
location `{LEGACY_DIR}` (e.g. `agent_docs/`) and canonical location
`{CANONICAL_PATH}` (e.g. `.shipwright/agent_docs/`), launch three
Explore agents in parallel. Total time: ~5 min for the planning
migration; expect similar.

### Agent 1: Python touchpoints

```
Search the shipwright monorepo for all Python references to the legacy
artifact path "{LEGACY_DIR}" (without the leading ./). Report:
- File path + line number for each hit
- Categorize: Path("{LEGACY_DIR}"), os.path.join, "{LEGACY_DIR}" string
  literal, or argparse default
- Group by plugin (shipwright-{name}/) vs shared/ vs integration-tests/
- Distinguish ENV-VARS from string literals from CLI args

Skip: any file already inside .shipwright/, .git/, node_modules/, .venv/.
Output: a Markdown table with columns File | Line | Construction | Notes.
```

### Agent 2: Prose + template touchpoints

```
Search the shipwright monorepo for prose and template references to
"{LEGACY_DIR}" (anywhere -- markdown, JSON, YAML, .gitignore). Report:
- All SKILL.md / agents/*.md / references/*.md hits
- All shared/templates/*.md / .json / .template hits
- All docs/*.md hits with section anchor
- All test fixture .json hits
- Distinguish bare "{LEGACY_DIR}" path from {variable_name}/-style
  templates (which usually don't migrate)

Skip: this reference doc itself, CHANGELOG.md, docs/migrations/, tests
that intentionally exercise the legacy path by name.

Output: hits grouped by file with surrounding context (1 line before,
1 after).
```

### Agent 3: Configuration + workflow touchpoints

```
Audit non-code configuration touchpoints for "{LEGACY_DIR}":
- All hooks.json files (matcher patterns, env injection)
- .gitignore (current entry + need for canonical entry)
- pyproject.toml + plugin.json keywords (descriptive vs path)
- .github/workflows/ + scripts/*.sh
- Any sample_*_config.json fixtures
- shipwright_*_config.json files at the repo root

Output: per-file findings, plus a short verdict on what needs to change
vs. what stays (e.g. plugin.json keyword "planning" is descriptive, not
a path).
```

After all three return, consolidate into a touchpoint table
(see § 4 for the structure that worked for planning).

---

## 3. Sub-Iterate Structure (A-G, validated)

The planning migration ran 7 sub-iterates over ~36h calendar time. For
the next migrations, expect the *test framework already exists* (A is a
no-op for them) but the touchpoint count drives B-E sizing.

| Sub-Iterate | Scope | Planning estimate (B-F per artifact) | Actual planning result |
|---|---|---|---|
| **A** | Test framework skeleton | one-time (already done) | done in planning iterate |
| **B** | Python migration in `shared/` | ~30 files | matched estimate |
| **C** | Python migration in `plugins/` + Layer-2 contract tests | ~25 files | matched estimate; surfaced 1 sub-iterate-C bug (double `.shipwright/` in test_integration.py) caught in D |
| **D** | Prose migration (SKILL.md, agents/, references/) | ~15 files / ~120 hits | matched. Honest assessment: many "{planning_dir}" template references that DO NOT need migration -- about 2/3 of grep hits were false-positives. Disambiguate up front. |
| **E** | Templates + docs + integration-tests + Layer-3 negative-assertion | ~10 files | matched. Found a pre-existing .gitignore bug (template was also gitignored) -- fixed in same commit. |
| **F** | `.gitignore` cleanup, status flip to migrated, Migrations-Doc, CHANGELOG, CLI, next-prompt helper | 6 files | matched. The CLI + tests ate the most time (~half of F). |
| **G** | Reference doc | 1 file + memory updates | this file |

**Sizing tip:** if a future artifact is *small* (e.g. CHANGELOG-unreleased.d),
B and C may collapse into a single sub-iterate -- but D-G should stay
discrete because the test/doc/CLI layers are about the same regardless
of artifact size.

**Branch layout used for planning:**
- `iterate/relocation-A-...` through `iterate/relocation-F-cleanup`
- Each branched off `main`, FF-merged when green.
- `iterate/relocation-G-reference` is the only one held for review
  before merge.

---

## 4. Touchpoint Table (template, with planning + designs + agent_docs + compliance numbers as examples)

Fill this in during the Explore phase. Use the prior migration numbers
as a sanity check -- if your artifact has fewer touchpoints, B-E will
be faster; if more, expect proportional growth. Four reference data
sets now (planning + designs + agent_docs + compliance) so you can
sanity-check magnitude across an order-of-magnitude range.

| Category | planning hits | designs hits | agent_docs hits | compliance hits | Reality check |
|---|---|---|---|---|---|
| Python `.py` PATH_LITERAL | ~231 in 55 files | ~17 in 8 files | ~523 in 98 files | **~79 in ~25 files** | compliance mid-tier — smaller than agent_docs (~6×) and planning (~3×), only ~1.4× designs Python+Prose-Sum. Heaviest single plugin: shipwright-compliance (~32 hits / 11 files; self-referential migration). |
| SKILL.md / agents.md / references.md prose | ~120 (~2/3 false-positive `{planning_dir}` template) | ~115 in 17 files (zero template-vars) | ~110 in 26 files (zero template-vars) | **~6 in 4 files (zero template-vars; compliance's own SKILL added during A's lint baseline)** | Smallest D-scope yet. Initial Inventory missed compliance plugin's own SKILL.md (3 hits at lines 50/110/113) — Layer-1-lint baseline at A surfaced it. Always grep `plugins/<artifact>/skills/<artifact>/SKILL.md` for self-referential migrations. |
| `shared/templates/shipwright_sync_config.json` | 6 hardcoded paths | 0 | 1 | **0** | -- |
| `shared/templates/claude-md-template.md` | 1 (`@planning/`) | 0 | 5 (`@agent_docs/<file>.md`) | **0** | -- |
| `shared/templates/agent-docs/conventions.md.template` | 0 | 1 | 0 | **0** | -- |
| `docs/guide.md` | 5 PATH_REFs + new convention para | ~10 PATH_REFs + paragraph update | 53 PATH_REFs + tail-sentence update | **12 PATH_REFs + tail-sentence rephrase (line 524: 2-item -> 1-item list)** | Mid-tier. Lesson 17 recurs every migration: tail-sentence "remaining top-level dirs are X, Y, Z" rots with each. |
| `docs/hooks-and-pipeline.md` | 9 PATH_REFs | 3 PATH_REFs | 23 PATH_REFs | **~18 PATH_REFs** | compliance has heavy phase-validator Mtime-tables + RTM/SBOM/test-evidence/change-history references. Plus 1 PLUGIN-PATH that stays (`skills/compliance/SKILL.md` line 1268 is plugin-skill path, not artifact). |
| `.gitignore` | 1 line edit | 1 line edit | 1 line edit | **3 lines added (NEW Lesson 26: pre-existing legacy entry without comment block)** | compliance had `compliance/` at line 70 with NO comment block (prior migrations added theirs in F). Sub-Iterate F **adds the missing block** instead of just extending one. Pre-F-Sanity-Check pattern. |
| Plugin agents/* + project references/* | NOT searched in planning | 4 files / 10 hits | 2 agents + 14 references / ~22 hits | **0** | -- |
| `plugin.json` / `marketplace.json` keywords | 4 hits | descriptive (no path) | descriptive (1 hit, STAYS) | **6 hits, all descriptive (plugin name `shipwright-compliance` + keywords arrays)** | permanent allowlist. compliance has plugin-name overlap (shipwright-compliance plugin vs compliance/ artifact) — disambiguation explicit in Explore prompts. |
| `pyproject.toml` keywords | -- | -- | -- | **3 hits (descriptive, stay)** | NEW data point. Plugin-name + concept overlap surfaces here. Permanent allowlist via `**/pyproject.toml` glob. |
| Test fixture `sample_*_config.json` | 4 path entries | 0 | 0 | **0** | -- |
| `bug_report.yml` | 0 | 0 | 1 | **0 (KEYWORD only — `shipwright-compliance` plugin name in dropdown)** | -- |
| `run_config.v2.schema.json` description | 0 | 0 | 1 | **0 PATH-REF (1 KEYWORD: `last_compliance_update` field-name not path)** | NEW datapoint: Lesson 16 doesn't apply when "compliance" is a field-name component, not an artifact path. |
| Shell scripts (`.sh`) | 0 | 0 | 2 | **0** | Lesson 15 doesn't apply this round. |
| CI workflows | 0 | 0 | 0 | **0** (only Dependabot plugin-dir, KEYWORD) | -- |
| `hooks.json` | 0 | 0 | 0 | **0** | hooks call generic shared scripts; pathless |
| Hook docstrings/comments (NEW touchpoint sub-type) | -- | -- | -- | **3 (audit_report.py:5, audit_staleness.py:37, run_audit.py:63 + check_rtm_coverage.py:4)** | NEW Lesson 28: hook + audit module DOCSTRINGS routinely contain path-refs that Layer-1 lint catches but Inventory often misses. Always grep module-level + first-paragraph docstrings of audit/ + hooks/ files explicitly. |
| Plugin-config-file `shipwright_<plugin>_config.json` (separate artifact) | -- | -- | -- | **14+ refs, all stay** | NEW boundary case: not every `<artifact>` keyword is a path-ref. shipwright_compliance_config.json is a SEPARATE artifact at project root (gitignored), not the `compliance/` directory. Layer-1 regex's negative-lookbehind (`_` ∈ `\w`) correctly excludes it; document the boundary explicitly. |

---

## 5. Test-Suite Layer Schema (final 7 layers)

| Layer | File | What it catches | Validated edge cases |
|---|---|---|---|
| 1 -- Static canon lint | `shared/tests/test_artifact_path_canon.py` | Text-regex + Python-AST scan for legacy literals | Caught bare `Path("planning")`, `os.path.join`, `tmp_path / "planning"`. AST mode was essential -- pure regex would have missed ~30% of Python touchpoints. |
| 2 -- Setup-contract tests | `shared/tests/test_setup_writes_canonical.py` | Per-plugin: setup-{plugin}-session.py writes ONLY under .shipwright/ | Surfaced 1 regression where a test fixture used `tmp_path / ".shipwright" / ".shipwright" / "planning"` (double prefix). |
| 3 -- Integration negative assertion | `integration-tests/test_core_trilogy_flow.py` + `test_state_recovery.py` | E2E trilogy must not produce any legacy top-level dir | Important: load `lib.artifact_migrations` via `importlib.util.spec_from_file_location` to avoid `sys.modules['lib']` poisoning the compliance plugin's separate `lib/` package. |
| 4 -- Drift detector unit tests | `shared/tests/test_stale_artifact_detector.py` | Hook returns correct exit code, JSON, severity, self-heal | Already in place from Sub-Iterate A; reused unchanged. |
| 5 -- gitignore canon | `shared/tests/test_gitignore_canon.py` | Legacy entry kept with "legacy path" comment within `[idx-1, idx+2]` | Trap: gitignore does NOT support trailing comments. Pattern + comment must be on different lines. |
| 6 -- Constants vs manifest cross-validation | `shared/tests/test_constants_match_manifest.py` | Local `<NAME>_DIR` / `LEGACY_<NAME>_DIRNAME` constants must equal the manifest values | Built post-agent_docs (2026-04-28) once 14 constants across 11 modules existed. Recognized name patterns: `<NAME>_DIR`, `<NAME>_DIRNAME`, `<NAME>_PATH`, plus `LEGACY_<NAME>_*`. Catches typos (e.g. `PLANNING_DIRNAME = ".shipwright/planing"`) that Layer-1 lint cannot see -- Layer 1 only forbids legacy literals in source, not malformed canonical literals. Verified on a deliberate typo: failure message gives file:line + expected value + 3 fix options. |
| 7 -- Cross-platform path tests | `shared/tests/test_path_canon_windows.py` | Windows backslash vs POSIX, symlink handling | Already in place from A; reused. |

**Note on Layer 6 history:** Sub-Iterate A scoped this layer but it was deliberately
deferred for the planning migration -- planning didn't introduce per-module local
constants, so there was nothing to cross-validate. The designs migration also
skipped local constants. The agent_docs migration was the threshold: it
introduced `AGENT_DOCS_DIR` and `LEGACY_AGENT_DOCS_DIRNAME` in
`plugins/shipwright-adopt/scripts/lib/{artifact_writer,visual_docs_generator}.py`
plus a sprinkle of `PLANNING_DIRNAME` in shared verifiers, and the gap became
real. Layer 6 was built as a follow-up after the agent_docs G commit.

**Future migrations:** Layer 6 already covers any new `<NAME>_*` constant that
follows the recognized naming convention -- no work needed in Sub-Iterate A
when adding a new artifact, just append to `ARTIFACT_MIGRATIONS`.

---

## 6. Allowlist Bootstrapping (real example)

Sub-Iterate A seeded the allowlist with a deliberately-wide glob set
covering every legacy hit. Sub-Iterates B-E each removed a slice. The
end-state allowlist (after F's status flip) is small and stable:

```python
ALLOWLIST = {
    "planning": [
        # Migration framework itself -- references both paths by design
        "shared/scripts/lib/artifact_migrations.py",
        "shared/scripts/lib/stale_artifact_detector.py",
        "shared/scripts/hooks/check_artifact_drift.py",
        "shared/tests/test_artifact_path_canon.py",
        "shared/tests/test_stale_artifact_detector.py",
        "shared/tests/test_gitignore_canon.py",
        "shared/tests/test_path_canon_windows.py",
        "shared/tests/test_setup_writes_canonical.py",  # Layer-2 asserts legacy NOT created
        # Plan files (this migration's own design docs)
        "C:/Users/you/.claude/plans/iterate-shipwright-relocation-*.md",
        "C:/Users/you/.claude/plans/ich-bin-am-berarbeiten-glittery-sun.md",
        # Historical docs that must not be rewritten
        "CHANGELOG.md",
        "CHANGELOG-unreleased.d/**",
        "docs/migrations/**",
        # Files where literal legacy ref is intentional
        "shared/scripts/lib/drift_parsers.py",
        "shared/scripts/lib/iterate_entry.py",
        "shared/scripts/lib/external_review_config.py",
        # plugin.json keywords + pyproject.toml metadata: descriptive word, not paths
        "plugins/**/.claude-plugin/plugin.json",
        "**/pyproject.toml",
        # .gitignore retains the legacy entry under # legacy comment
        ".gitignore",
        ".claude-plugin/**",
        # Memo describing the rejected alternative
        "**/project_paths_refactor_evaluated.md",
    ],
}
```

For inline opt-outs in a single line, use the marker
`# artifact-path-canon: legacy` (works in `#`-comments and HTML
`<!-- ... -->`). Used in `docs/guide.md` and
`docs/hooks-and-pipeline.md` for paragraphs that intentionally
describe the OLD path.

---

## 7. Pre-`ExitPlanMode` Verification Checklist

Before approving the plan for a new artifact migration, walk this
5-item checklist. Each item caused a real correction in the planning
session:

1. **argparse defaults** -- grep every script for `default=...` against
   the legacy path. The planning plan listed this as "verified" but
   it's still worth a 30-second re-grep per migration.
2. **ENV-VARS** -- which ENV-VARs name the artifact? Are they values
   that change with the migration, or path-agnostic? `SHIPWRIGHT_PLANNING_DIR`
   was path-agnostic (user sets externally), so it stayed.
3. **Hook wiring** -- which `hooks.json` files reference the legacy
   path? For planning: zero (hooks call generic shared scripts). For
   `compliance/`, expect *some* hooks because that plugin's hooks read
   compliance docs directly.
4. **Test fixtures** -- grep `tests/fixtures/**/*.json` and
   `tests/fixtures/**/*.md` for the legacy literal. These are subtle
   because they pass the lint (the fixture file *is* the test data, so
   it looks like real content).
5. **Root configs** -- check what `shipwright_*_config.json` files at
   the repo root might still reference the legacy path. For planning,
   these were gitignored so they were out of scope -- but always
   verify.

---

## 8. External-Review Trace Template

Copy this table verbatim into each new migration's plan. Fill rows as
the dual-LLM review (Gemini + GPT via OpenRouter) returns findings.

| # | Reviewer | Severity | Category | Finding (short) | Status | Where addressed |
|---|---|---|---|---|---|---|
| G1 | Gemini | HIGH/MED/LOW | Migration/Test/Arch/Sec/Perf | one-liner | Fixed/Partial/Verified/Rejected | section ref |
| 1 | GPT | ... | ... | ... | ... | ... |

For planning, the matrix had 23 rows (5 Gemini + 18 GPT). 2 rows were
"Verified" (already addressed in the plan), 1 was "Rejected"
(scope-creep that the user explicitly wanted), all others were "Fixed"
or "Partial."

Run command:

```bash
uv run shared/scripts/tools/external_review.py \
  --mode plan \
  --plan-file C:/Users/you/.claude/plans/<plan>.md \
  --spec-file CLAUDE.md \
  --plugin-root plugins/shipwright-plan
```

---

## 9. Rejected Alternatives (with reasons)

These alternatives were considered and explicitly rejected. Do not
re-propose without consulting the linked memo.

- **Central `paths.py` module** -- `project_paths_refactor_evaluated.md`
  (2026-04-25). Dual-LLM-reviewed and rejected: too much coupling, no
  benefit over local constants + lint.
- **Grace-Period reads (try canonical, fall back to legacy)** -- user
  rejected directly. Hides drift instead of surfacing it.
- **Mega-plan-file with all 7 sub-iterates inline** -- rejected for the
  planning migration. One plan file per sub-iterate worked better:
  each is ~50-100 lines, scoped, and survives mid-session compaction.
- **Stop-hook (after every Stop) instead of SessionStart-hook for the
  drift detector** -- considered but rejected. SessionStart catches
  drift the moment a user opens the project; Stop only catches it
  after work has been done in the wrong place.
- **CHANGELOG-unreleased.d/ entry per sub-iterate** -- rejected per
  pre-Early-Access rule (`feedback_early_access_push.md`). Resume
  per-sub-iterate CHANGELOG entries when Early Access starts.

---

## 10. What I'd Do Differently Next Time

Honest list from the planning migration. Treat as advice, not gospel.

1. **Disambiguate `{template_var}` from real path references in D
   upfront.** ~2/3 of plugin SKILL.md "planning" hits were
   `{planning_dir}` template variables that should NOT migrate. The
   plan estimated "~120 hits" but only ~40 needed editing.
2. **Run the gitignore_canon test SOON after writing the comment.**
   The trailing-comment trap (gitignore doesn't support inline
   comments) only surfaced after F was committed; needed a follow-up
   commit to fix. Run the canon test immediately after editing
   `.gitignore` -- it's <2 seconds.
3. **Always include a Layer-3 negative-assertion when adding the
   trilogy fixture changes (E).** It catches drift that escapes
   per-script unit tests (mocks/stubs hide the real path constructed).
   Add to BOTH `test_core_trilogy_flow.py` AND `test_state_recovery.py`
   -- they exercise different paths.
4. **Sub-Iterate-C test bug carry-over to D is real -- run a sanity
   pass at start of D.** Sub-Iterate C left a `.shipwright/.shipwright/`
   typo in `test_integration.py` that D had to fix. Always start a
   prose sub-iterate with a quick `grep -rn "<legacy>" plugins/` to
   catch these.
5. **Don't bundle the .gitignore template-tracking fix into the
   migration sub-iterate.** Sub-Iterate E inherited an unrelated
   .gitignore bug (`shipwright_*_config.json` was matching the
   template). Fixed in same commit, but it muddied the diff. Land
   such drive-by fixes in their own commit.
6. **The migration CLI should require `--confirm` for live writes.**
   The `--dry-run` flag is good but not surfaced enough; new users
   may forget. Consider making `--confirm` mandatory for the
   destructive path.
7. **Em-dashes in script docstrings break Windows cp1252 console.**
   Stick to ASCII (`--` instead of `—`) in any script that prints
   to stdout.

### Additional lessons from the `designs` migration (2026-04-27)

8. **Always grep `plugins/*/agents/*.md` AND `skills/project/references/*.md`,
   not just `skills/*/SKILL.md`.** Explore-Agent #2 missed 4 files
   here (10 hits total). Layer-1 caught them in Sub-Iterate A but it
   would've been faster to find them upfront. Update the agent prompt
   in § 2 to explicitly enumerate `agents/`, `skills/<name>/references/`,
   AND `skills/<name>/SKILL.md`.

9. **Bulk Edit replace_all beats Edit-pro-Hit on files with 10+ hits.**
   Designs SKILL.md had ~65 hits — doing them sequentially would've
   been error-prone. Pattern that worked: Pre-Grep + Disambiguation
   audit + 10 unambiguous `replace_all` patterns + Post-Grep verify.
   For files with < 5 hits, inline still wins.

10. **Latent bugs from previous migration's path-shape change can
    surface during the next.** generate-batch-tasks.py used
    `planning_dir.parent` (correct pre-planning-migration, broken
    after — `.parent` resolved to `.shipwright/planning` instead of
    project root). The bug was silent because `designs/` didn't exist
    in test fixtures. Found while migrating designs. **Lesson**:
    when migrating an artifact, also re-validate any `_dir.parent`
    or `_dir.parent.parent` chains in code that touches DIFFERENT
    artifacts which were previously migrated.

11. **Add defensive shape validation when climbing parents.**
    Hardcoded `.parent.parent.parent` is brittle if a future caller
    passes a non-canonical path. Pattern: check `path.parts[-N]` against
    the expected segment names (e.g. `.shipwright`, `planning`) before
    climbing. Skip-with-fallback rather than crash.

12. **Layer-2 setup-contract test must explicitly assert no
    `.shipwright/.shipwright/` and no `<artifact>/<artifact>/`
    double-prefixes.** The carry-over bug pattern from planning
    Sub-Iterate C->D doesn't reproduce automatically; it only
    surfaces if you assert against it. Add to every new artifact's
    Layer-2 contract test.

13. **External code review can flag "valid concerns" that are
    actually structurally enforced elsewhere.** OpenAI's review of
    designs F flagged "canonical reads not asserted in both-dirs
    test" as MED — but Layer-1 lint already prevents legacy reads
    in code, and Layer-2 prevents legacy writes. The structural
    invariant covers the case. Note these in the review-trace as
    "verified addressed" rather than implementing redundant tests.

14. **Configure inline `# artifact-path-canon: legacy` markers
    on the SAME line as the offending literal, not the line
    above.** The Layer-1 lint's text-regex mode is per-line; markers
    on adjacent lines do not propagate. Tested in F when adding the
    drift_parsers marker and in the Pre-G hotfix's defensive
    `parts[-2] == "planning"` check.

15. **Shell-hook scripts (`*.sh`) are production touchpoints, not
    prose.** Hooks like `check_secrets.sh` and `check_file_size.sh`
    emit user-facing JSON with path strings (`"log the override to
    .shipwright/agent_docs/compliance_overrides.log"`). When such a
    string appears, the file belongs in Sub-Iterate B with the Python
    production code, not in Sub-Iterate D with the prose. agent_docs
    migration surfaced this — 2 such files. Always grep `*.sh` files
    in the B-scope inventory.

16. **JSON Schema `description` fields cannot be inline-marked.**
    JSON has no comment syntax, so `# artifact-path-canon: legacy`
    is not legal in a `.json` description. Solution: rephrase the
    description to use the canonical path. agent_docs migration hit
    this at `shared/schemas/run_config.v2.schema.json:82` ("Legacy
    field; new entries live under .shipwright/agent_docs/iterates/.").

17. **Tail-sentences in `docs/guide.md` rot with each migration.**
    Time-locked statements like "remaining top-level dirs are X, Y,
    Z" become factually wrong after each subsequent migration. Pre-G
    discovery step: grep `docs/guide.md` for "remaining" + the prior
    artifact-list pattern, update the count and items. agent_docs
    migration found this at line 524 (3-item list -> 2-item list).

18. **`.github/ISSUE_TEMPLATE/*.yml` is a touchpoint type.**
    Bug-report templates can carry path references in their
    description fields. Always grep `.github/ISSUE_TEMPLATE/**/*.yml`
    in Touchpoint Discovery, separate from prose-files. agent_docs
    migration surfaced 1 hit at `bug_report.yml:107`.

19. **Heavy single-plugin scope in C may justify a sub-section
    Commit-body, not a split.** When one plugin contributes >50 hits
    in a single Sub-Iterate-scope (agent_docs C: ~70 hits in
    shipwright-adopt), C-Plan Step 10 mandates a Decision-Gate at
    the 800-line-diff mark. agent_docs C stayed under (~478 lines
    diff), so single-commit was correct. If your scope crosses the
    threshold, split per Plan-Step 10. Either way, sub-section the
    commit body explicitly so reviewers can scope-narrow.

20. **Stray Explore-agent artifacts must be cleaned before A.**
    Explore-subagents can dump large markdown reports into the
    repo-root (`agent_docs_refs.md` ~70 KB, untracked). These are
    Discovery artifacts, not project files. Pre-A check: `git
    status -uall` for untracked Discovery output; remove or relocate
    to `~/.claude/plans/` before Sub-Iterate A starts.

21. **Scanner-Exclusion Contract** (resolved in Sub-Iterate H,
    v0.10+). The original blanket `.shipwright`-exclude was lifted:
    `plugins/shipwright-security/scripts/lib/oss_backend.py` now
    keeps per-scanner lists (`_SEMGREP_EXCLUDES = ()`,
    `_TRIVY_EXCLUDES`, `_GITLEAKS_EXCLUDES`) and `.shipwright/` is
    intentionally absent from all of them. Effective behavior:
    Semgrep skips whatever the project `.gitignore` ignores (the
    SSoT for tracked-vs-untracked); Trivy and Gitleaks scan
    `.shipwright/` since they do not honor `.gitignore`, but
    Trivy finds nothing in markdown (no manifests) and
    Gitleaks `detect`-mode skips uncommitted files. Projects that
    want `.shipwright/` skipped explicitly set
    `SHIPWRIGHT_SCAN_EXCLUDES=.shipwright`. See
    `plugins/shipwright-security/skills/security/references/oss-scanners.md`
    for the full per-scanner truth table.

### Additional lessons from the `compliance` migration (2026-04-29)

22. **Plugin-name + artifact-name overlap requires explicit disambiguation
    in Touchpoint-Discovery prompts.** compliance was the first migration
    where the artifact name (`compliance/`) shares a name with a plugin
    (`shipwright-compliance`). Without explicit guidance to the Explore
    agents to filter PLUGIN-NAME / PHASE-NAME / FUNCTION-NAME hits as
    KEYWORD (not PATH-REF), ~60% of raw grep hits would have polluted
    the inventory. Pattern that worked: explicit verdict categories
    (PATH-REF / PLUGIN-NAME / PHASE-NAME / TEMPLATE-VAR / KEYWORD /
    AMBIGUOUS) in Agent prompts + a top-of-report sample of false-
    positives so the disambiguation can be verified.

23. **Manifest pattern negative-lookbehind needs verification when
    artifact name is a substring of plugin/concept names.** Pattern
    `(?<![\w/.\\])compliance/` correctly excludes `shipwright-compliance/`
    in practice ONLY because the codebase consistently uses
    `Path(__file__).parent...` for plugin-internal paths (verified via
    `grep -rnE '"shipwright-compliance[/\\]"' shared/ plugins/ --include='*.py'`
    -> 0 hits). Layer-1 regex would otherwise match `-compliance/` because
    `-` is not in `[\w/.\\]`. **Test it explicitly during Sub-Iterate A**
    with a Layer-1 lint run + grep for plugin-name string literals. If a
    future artifact name has broader linguistic overlap, the lookbehind
    might need extension (e.g. `(?<!shipwright-)`).

24. **Self-referential migrations (artifact written by its own plugin)
    need an extra prose grep.** The shipwright-compliance plugin's own
    SKILL.md (`plugins/shipwright-compliance/skills/compliance/SKILL.md`)
    had 3 PATH-REFs that the Inventory Prose agent missed because the
    agent's prompt focused on cross-plugin references and didn't enumerate
    `plugins/<artifact>/skills/<artifact>/SKILL.md` as a self-referential
    case. **Pattern**: when the artifact name matches a plugin's skill
    dir, ALWAYS grep `plugins/shipwright-<artifact>/skills/<artifact>/SKILL.md`
    explicitly. Layer-1-lint at A surfaced this in compliance migration
    via 3 hits in lines 50/110/113.

25. **Cross-plugin write-coupling via bridge modules requires lockstep
    commits.** shipwright-adopt -> shipwright-compliance coupling lives
    in `compliance_bridge.py` (5-tuple of generator_name -> output_path)
    + `dry_run_reporter.py` (5 ProposedWrite mirror). If only one is
    migrated, dry-run output and live runs diverge. Lockstep-rule:
    bridge + mirror in same commit. compliance migration validated this
    pattern; expect similar coupling in future migrations whose adopt
    plugin scaffolds the artifact.

26. **`.gitignore` Lücke pre-Migration ist häufiger als erwartet.**
    Pre-compliance-migration hatte `compliance/` keinen Legacy-
    Kommentar-Block (anders als planning/designs/agent_docs). Vermutlich
    historisch früher hinzugefügt vor Migration-Pattern-Etablierung.
    Sub-Iterate F muss daher den Block neu schreiben (3 Zeilen vor dem
    Pattern), nicht nur erweitern. **Pre-F-Sanity-Check**: für jedes
    `migrated`-Artifact prüfen ob Legacy-Kommentar-Block existiert; wenn
    nicht: in F nachholen.

27. **Real-Scanner-Smoke jetzt assertion-based (per External-Review O-1.2).**
    Verbesserung gegenüber agent_docs-Migration: nicht nur grep-on-output
    (kann false confidence geben), sondern synthetisches Secret-Fixture
    mit non-allowlisted Pattern (z.B. github-pat `ghp_...`) das gitleaks
    DETEKTIEREN MUSS. Wenn gitleaks 0 Hits: Scanner-Exclusion-Bug ->
    Hot-Fix vor Status-Flip. **AKIAIOSFODNN7EXAMPLE ist gitleaks
    stopword** (Test-Allowlist) — verwendet keine "Beispiel"-Patterns.
    Compliance migration verified gitleaks-inclusion empirisch (2 leaks
    detected: generic-api-key + github-pat in `.shipwright/compliance/test-secret-fixture.md`).

28. **Hook + audit module DOCSTRINGS routinely contain path-refs.** Initial
    Inventory Python agent classified docstring/comment hits as KEYWORD or
    skipped them, but Layer-1-lint catches them as text-regex matches.
    compliance migration surfaced 4 such hits (audit_report.py:5,
    audit_staleness.py:37, run_audit.py:63, check_rtm_coverage.py:4) —
    all docstrings/comments mentioning `compliance/<file>.md`. **Pattern**:
    in Sub-Iterate A's pre-flight, explicitly grep module-level + function
    docstrings of `plugins/<artifact>/scripts/audit/*.py` and
    `plugins/<artifact>/scripts/hooks/*.py` for the artifact-name path
    pattern. Update C-Plan to list them as explicit touchpoints rather
    than relying on Layer-1-lint to catch them reactively.

29. **Plugin-config-file boundary clarity.** `shipwright_<plugin>_config.json`
    (e.g. `shipwright_compliance_config.json`) is a SEPARATE artifact from
    `<artifact>/` directory. It lives at project root (gitignored), is
    referenced by 14+ files in compliance migration, and is correctly
    excluded by Layer-1 regex (`_` ∈ `\w` -> negative-lookbehind matches).
    **Always document this boundary explicitly** in MAIN's "Was NICHT
    migriert wird" section so reviewers don't conflate the two artifacts.

30. **Generator-Relative-Link-Resolution: runtime test, not just
    static-grep.** When the migration changes the depth of generated
    output files (e.g. `compliance/<file>.md` 1-deep -> `.shipwright/compliance/<file>.md`
    2-deep), all hardcoded `../<file>` Markdown links inside generator
    OUTPUT break. Lesson 30: the C-Step-11 fix table is necessary but
    NOT sufficient — Pre-G belt-and-suspenders MUST include a real
    runtime invocation of the affected generators in a tmp project +
    parse output Markdown links + assert each resolves. Static grep
    of `../<X>` -> `../../<X>` is fragile against f-string template
    edge cases (e.g. `f"({req.spec_path})"` where spec_path itself
    starts with `.shipwright/`). compliance migration verified: real
    `compliance_report.generate_file()` produces 8 links all resolving
    + `rtm_generator.generate()` f-string output produces 2 link
    patterns both resolving correctly. **Pattern**: write this runtime
    test as part of Sub-Iterate C, not just as Pre-G belt-and-suspenders.

---

## 11. Reference Commits

For grep / blame / re-orientation:

- `b8fc243` -- security report dir relocation, established the
  `.shipwright/` convention.
- `ad62e15` -- Sub-Iterate A: drift safety net (artifact_migrations
  manifest + Layer-1 lint + Layer-4 detector + gitignore canon).
- `a056d41` -- Sub-Iterate B: shared/ Python migration.
- `3c64a71` -- Sub-Iterate C: plugins/ Python migration + Layer-2
  setup-contract tests.
- `7b33dc2` -- Sub-Iterate D: plugin prose migration.
- `6b1418b` -- Sub-Iterate E: templates + docs + integration-tests +
  Layer-3 negative-assertion.
- `cf193f9` -- Sub-Iterate F: hard cutover (status flip), migration
  CLI, next-migration prompt, user-facing migration doc.
- `2466b00` -- Sub-Iterate G: reference doc + pattern memory (this file's first version).

### designs migration (2026-04-27)

Second artifact migration validating the pattern. ~17 production touchpoints
+ ~115 prose touchpoints across 7 sub-iterates B-F + Pre-G hotfix + G:

- `01b493a` -- Sub-Iterate A: manifest activation (`pending` -> `in_progress`),
  ALLOWLIST seed, .gitignore legacy entry. Layer-1 surfaced 4 plugin
  agents/references files Explore-discovery had missed (ground truth for
  pattern-memory § 2 "always grep agents/* in addition to skills/*").
- `80e40be` -- Sub-Iterate B: shared/ Python migration (3 verifiers +
  get_phase_context + 2 shared tests + Layer-6 candidate constant
  `DESIGNS_DIR` in design_checks.py).
- `b39407f` -- Sub-Iterate C: plugins/ Python migration (5 plugin scripts
  + 4 plugin test files) + Layer-2 setup-contract additions:
  `test_design_setup_session_writes_canonical_designs` and
  `test_no_legacy_designs_path_construction_in_plugin_source`.
  **Bonus**: latent bug fix in generate-batch-tasks.py (planning_dir.parent
  was correct pre-planning-migration, broken post-migration; corrected
  to .parent.parent.parent + later hardened with shape validation).
- `32388fd` -- Sub-Iterate D: plugin prose migration (17 .md files,
  ~115 edits via bulk Edit replace_all on 10 unambiguous patterns,
  not Edit-pro-Hit which the planning lessons warned against).
- `bbd56d4` -- Sub-Iterate E: templates + docs + Layer-3 already
  iterates manifest so designs is auto-covered + 2 NEW edge case
  tests in `shared/tests/test_artifact_drift_edge_cases.py`
  (both-dirs-present + canonical-only self-heal + generated-output
  content scan, addressing External-Review GPT-9 + GPT-10).
- `af64a26` -- Sub-Iterate F: hard cutover. Status flip, .gitignore
  retention comment in window, drift_parsers.py:108 line split with
  per-artifact `# artifact-path-canon: legacy` markers, user-facing
  `docs/migrations/.shipwright-designs-relocation.md` (with `git rm
  --cached` guidance per External-Review GPT-7), idempotency test
  `test_10_design_setup_re_run_idempotency` per External-Review GPT-8.
- `3421434` -- Pre-G hotfix: defensive shape validation on planning_dir
  in generate-batch-tasks.py per External-Review HIGH finding (OpenAI).
- `2854718` -- Sub-Iterate G: reference doc + pattern memory updates.

### agent_docs migration (2026-04-28)

Third artifact migration validating the pattern. ~523 Python
touchpoints + ~195 prose touchpoints across ~36 .md files. Largest
migration so far — ~2.3× planning, ~5.5× designs. Spans all 6 SDLC
plugins, with shipwright-adopt as the dominant single plugin (~70 hits
/ 9 files) due to wholesale agent_docs/ scaffolding for adopted projects.

- `81cef64` -- Sub-Iterate A: manifest activation (`pending` -> `in_progress`),
  ALLOWLIST seed (~80 entries), .gitignore stays untouched (legacy
  entry already present from prior pre-migration .gitignore). Layer-1
  + Layer-4 + Layer-5 + Layer-6 baseline green.
- `ca0fd19` -- Sub-Iterate B: shared/ Python migration (16 production
  + 22 test files) + 2 shell hooks (`check_secrets.sh`, `check_file_size.sh`)
  + Layer-6 candidate constants in spec_parser.py,
  generate_handoff_on_stop.py, verifiers/common.py,
  verifiers/design_compliance.py.
- `c009a0a` -- Sub-Iterate C: plugins/ Python migration (heavy:
  shipwright-adopt 9 files / 70 hits, with constants in
  artifact_writer.py + visual_docs_generator.py)
  + Layer-2 setup-contract additions:
  `test_adopt_write_agent_docs_writes_under_dot_shipwright` and
  `test_no_legacy_agent_docs_path_construction_in_plugin_source`
  parametrized over 6 plugins. shipwright-{build,compliance,iterate,
  project,run} also covered. Fixture `nested-shipwright/webui/`
  rename to canonical layout.
- `9dc880d` -- Sub-Iterate D: plugin prose migration (30 .md files,
  ~195 edits via bulk Edit replace_all on 7 unambiguous patterns).
  README.md + CLAUDE.md (repo-root) + constitution.md also migrated.
  ZERO template-vars to disambiguate (cleaner than planning's ~2/3
  false-positive trap; same as designs).
- `e0dd9bc` -- Sub-Iterate E: templates (claude-md-template,
  migrations.md.template, shipwright_sync_config.json) +
  docs/guide.md (53 hits, including line 524 sentence rephrase from
  3-item to 2-item list of remaining top-level dirs) +
  docs/hooks-and-pipeline.md (23 hits) + bug_report.yml +
  run_config.v2.schema.json description rephrase. 3 NEW touchpoint
  types surfaced (Lessons 15, 16, 18). Layer-3 trilogy temp E-stage
  no-legacy assertion added (removed in F when status flips).
- `95d2c5c` -- Sub-Iterate F Step 1: .gitignore legacy comment
  (separate-line, [idx-1, idx+2] window per Lesson 6).
- `10e1f65` -- Sub-Iterate F Step 3: drift_parsers.py:108
  HIDDEN_DIR_DEFAULTS line extended to 3-entry inline marker per
  artifact.
- `1744bff` -- Sub-Iterate F Step 4: user-facing
  `docs/migrations/.shipwright-agent_docs-relocation.md` with
  CI/CD-update + concurrent-session-warning + drift-detector-JSON-
  example + recovery-anleitung sections (per External Review G3 + O7
  + O10 + O11).
- `1bf4af6` -- Sub-Iterate F Step 2 (final atomic): status flip
  `in_progress` -> `migrated` + remove temporary E-stage trilogy
  assertion (universal `_assert_no_legacy_artifact_dirs` helper now
  covers agent_docs as `migrated`). Manual smoke trace in commit
  body: migrate_artifact_dir.py dry-run + live + spaces-in-path +
  both-dirs-refusal + drift-detector legacy/clean.
- `8ad450a` -- Sub-Iterate G: reference doc + pattern memory
  updates (this file's third data column + agent_docs section in §
  11 + new lessons 15-20 in § 10).

### compliance migration (2026-04-29)

Fourth artifact migration validating the pattern. ~79 Python touchpoints
+ ~35 prose touchpoints across ~30 files. Mid-tier — smaller than
agent_docs (~6×) and planning (~3×), only ~1.4× designs Python+Prose-Sum.

**Special characteristics:**
- First migration where artifact name (`compliance/`) overlaps with plugin
  name (`shipwright-compliance`) and phase name (`compliance` in
  pipeline-step lists). Disambiguation explicit in Explore-agent prompts;
  manifest regex negative-lookbehind verified empirically at Sub-Iterate A.
- Self-referential migration: shipwright-compliance plugin owns the
  compliance/ artifact AND writes it via 6 generators (compliance_report,
  sbom_generator, rtm_generator, test_evidence, change_history,
  audit_report) sharing a common output_dir pattern.
- Cross-plugin write-coupling: shipwright-adopt's compliance_bridge.py
  invokes the compliance generators with hardcoded output paths (5-tuple);
  dry_run_reporter.py mirrors with 5 ProposedWrite entries. Lockstep-commit
  required (validated in Sub-Iterate C).

- `61728f0` -- Sub-Iterate A: manifest activation (`pending` -> `in_progress`),
  ALLOWLIST seed (~30 entries), .gitignore stays untouched (legacy
  entry already on line 70 from pre-migration era; Sub-Iterate F adds
  the missing legacy comment block). Layer-1 + Layer-4 + Layer-5 +
  Layer-6 + Layer-7 baseline green. **Bundled hot-fix:** added
  `oss-scanners.md` to agent_docs ALLOWLIST (security Sub-Iterate H
  introduced 2 legacy `agent_docs/` references without allowlisting them).
  Sub-Iterate A's lint baseline also surfaced 3 missed PATH-REFs in
  `plugins/shipwright-compliance/skills/compliance/SKILL.md` (lines
  50/110/113) and 1 in `plugins/shipwright-adopt/scripts/lib/artifact_writer.py:204`
  decision-log template — both temporarily allowlisted, migrated in D and C.
- `f6be006` -- Sub-Iterate B: shared/ Python migration (10 production
  files + 5 test files). Layer-6 constants `COMPLIANCE_DIR` +
  `LEGACY_COMPLIANCE_DIRNAME` introduced in `phase_quality.py` (3
  module-level paths derived), `security_compliance.py`,
  `infrastructure_checks.py`, `compliance_compliance.py`. Helper
  `_compliance_path(proj, name)` introduced in heavy-hit test files.
- `5a9ba0e` -- Sub-Iterate C: plugins/ Python migration (heavy on
  shipwright-compliance: 32 hits / 11 files; lockstep in
  shipwright-adopt: 7 hits / 2 files; light in shipwright-run: 4 hits /
  2 files). **NEW Step 11 (per External-Review G-1A): Generator-Output
  Relative-Link Fix** — 13 hardcoded `../<file>` Markdown links in 3
  generators broke after migration (compliance/ was 1-deep,
  .shipwright/compliance/ is 2-deep). Per-line mapping:
  `../<project_root_file>` -> `../../<file>`;
  `../.shipwright/<other_artifact>/...` -> `../<other_artifact>/...`.
  Affected: compliance_report.py:47-60, rtm_generator.py:62/71/186/265/305/428,
  test_evidence.py:286. Layer-2 setup-contract additions:
  `test_compliance_generators_write_under_dot_shipwright` and
  `test_no_legacy_compliance_path_construction_in_plugin_source`
  parametrized over shipwright-{adopt,compliance,run}.
- `335b1d9` -- Sub-Iterate D: plugin prose migration (smallest D-scope
  yet: 6 hits in 4 SKILL.md files via inline edits, no bulk replace_all
  needed). Zero template-vars to disambiguate. **D-scope grew from 3 to 4**
  during A's lint baseline (compliance plugin's own SKILL.md added).
- `8e85961` -- Sub-Iterate E: docs/guide.md (12 PATH-REF +
  line 524 tail-sentence rephrase from 2-item to 1-item per Lesson 17)
  + docs/hooks-and-pipeline.md (~18 PATH-REF). Zero template touchpoints.
  No Layer-3 temp E-stage assertion (universal `_assert_no_legacy_artifact_dirs`
  helper handles status=migrated automatically; in_progress is warn-only).
- `b209566` -- Sub-Iterate F Step 1: .gitignore legacy comment block
  added (NEW pattern — pre-migration entry had no block, see Lesson 26).
- `57c1180` -- Sub-Iterate F Step 3: drift_parsers.py
  HIDDEN_DIR_DEFAULTS `compliance` entry extended with inline marker
  `# artifact-path-canon: legacy (post-migration tolerance)`.
- `6398642` -- Sub-Iterate F Step 4: user-facing
  `docs/migrations/.shipwright-compliance-relocation.md` with all
  post-agent_docs sections + audit-relevance section (compliance reports
  as audit evidence, override-log preservation, skill-compliance subdir
  layout) + audit-system path-update warning in CI/CD section.
- `f5372f3` -- Sub-Iterate F Step 2 (final atomic): status flip
  `in_progress` -> `migrated`. Manual smoke trace in commit body:
  migrate_artifact_dir.py dry-run + live + spaces-in-path +
  both-dirs-refusal + drift-detector legacy/clean. **Real-Scanner-Smoke
  (assertion-based per External-Review O-1.2):** gitleaks empirically
  detects 2 leaks (generic-api-key + github-pat) in
  `.shipwright/compliance/test-secret-fixture.md` -> canonical scanned,
  not silently skipped.
- `50d1d86` -- Pre-G fixup: migrated 2 mock-fixture lines in
  `plugins/shipwright-run/tests/test_orchestrator.py` to canonical path
  (surfaced by Pre-G repo-wide sanity grep).
- **Pre-G Belt-and-Suspenders Generator-Relative-Link-Resolution test
  (per Lesson 30):** real-runtime invocation of
  `compliance_report.generate_file()` + `rtm_generator.generate()` in tmp
  project + parse output Markdown links + assert each resolves.
  **Result: 8/8 dashboard.md links resolve + 2/2 RTM f-string-templated
  links resolve correctly.** Confirms the C-Step-11 mapping
  (../<root_file> -> ../../<file>; ../.shipwright/<artifact>/... ->
  ../<artifact>/...) is correct end-to-end at runtime, not just
  statically per-line.
- `ffaa0b4` -- Sub-Iterate G: reference doc + pattern memory
  updates (this file's fourth data column + compliance section in
  § 11 + new lessons 22-30 in § 10).
- `3595786` -- Sub-Iterate G follow-up: Lesson 30 added retroactively
  + Pre-G belt-and-suspenders trace appended (post-rewrite addendum).

---

## 12. Quick Start: Migrating the Next Artifact

**Before starting**, verify the candidate is not already rejected — see
§ 0 "Rejected migration candidates" subsection. As of 2026-04-29 the
four pipeline-internal artefacts (planning, designs, agent_docs,
compliance) are all `migrated`; `print_next_migration_prompt.py` reports
"All 4 artifact migration(s) complete." Future candidates require
upfront analysis (cost/benefit vs external-tool coupling, see e2e/ and
CHANGELOG-unreleased.d/ rejection memos for the disqualifying patterns).

1. Run `uv run shared/scripts/tools/print_next_migration_prompt.py` --
   it tells you what's next and seeds the kickoff prompt. If the output
   says "All N artifact migration(s) complete." and you still want to
   migrate something, FIRST check `~/.claude/projects/.../memory/` for
   a `project_<artifact>_migration_rejected.md` memo before appending
   to the manifest.
2. Read this doc end-to-end (you're doing it).
3. Append a `pending` entry to `ARTIFACT_MIGRATIONS` in
   `shared/scripts/lib/artifact_migrations.py`.
4. Launch the 3 Explore-agent prompts (§ 2) in parallel.
5. Draft sub-iterate plan files A-G in `~/.claude/plans/` using the
   `iterate-shipwright-relocation-*.md` files as templates.
6. External-review the main plan (§ 8).
7. Flip status to `in_progress` and start Sub-Iterate B.
8. Run B-F, each with the same TDD + Layer-1-lint-green discipline.
9. F flips status to `migrated`. The drift detector now warns (warn-only;
   SessionStart cannot block — see § 1 mode matrix).
10. G updates THIS reference doc with the new artifact's lessons,
    appends to § 11 reference commits, updates `MEMORY.md` index.
