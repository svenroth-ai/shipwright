# Shipwright `.shipwright/<artifact>/` Migration Reference

This document is the SSoT for every future top-level artifact directory
that gets relocated under `.shipwright/`. It was written **after** the
planning relocation (Sub-Iterates A-G, 2026-04-26 -> 2026-04-27) and is
based on what actually happened, not on the original plan's
speculation.

Read this BEFORE starting a new migration (e.g. `agent_docs/`,
`compliance/`, `designs/`, `e2e/`, `CHANGELOG-unreleased.d/`). Keep
the structure unless you have a specific reason to deviate.

---

## 0. Kickoff Prompt Template (copy-paste)

Send this to a fresh Claude Code session to start the next artifact
migration. Replace the three placeholders, then paste:

> I want to relocate the top-level `{LEGACY_DIR}` directory to
> `{CANONICAL_PATH}` following the validated pattern from the planning
> migration.
>
> **Before doing anything else, read these in order:**
> 1. `~/.claude/projects/c--Users-SvenRoth-dinovo-GmbH-AI-Backup---Documents-03-Development-shipwright/memory/feedback_artifact_migration_pattern.md`
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
- `{LEGACY_DIR}` -- top-level dir name with trailing slash, e.g.
  `agent_docs/`, `compliance/`, `designs/`, `e2e/`,
  `CHANGELOG-unreleased.d/`.
- `{CANONICAL_PATH}` -- target POSIX path under `.shipwright/`, e.g.
  `.shipwright/agent_docs`, `.shipwright/compliance`.
- `{ARTIFACT_NAME}` -- bare artifact name (no slash), used as the
  manifest key, plan-file slug, and in commit/PR titles, e.g.
  `agent_docs`, `compliance`, `designs`.

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
   - **Any `block` finding (migrated)** -> emit structured JSON to
     stdout (parsed by AI orchestrators per Gemini #1 -- stderr alone
     is overlooked) AND exit 1. The session start fails. The user
     sees both `stale-folders.md` and the JSON output.

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

When the detector hard-gates an existing project:

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
| `migrated` | enforces (allowlist near-empty) | hard-gate, exit 1 | the documented user-facing remediation |

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

## 4. Touchpoint Table (template, with the planning numbers as example)

Fill this in during the Explore phase. Use the planning numbers as a
sanity check -- if your artifact has fewer touchpoints, B-E will be
faster; if more, expect proportional growth.

| Category | Planning hits | Critical share | Reality check |
|---|---|---|---|
| Python `.py` PATH_LITERAL | ~231 in 55 files | 11 plugins + shared + integration-tests | Matched |
| SKILL.md / agents.md / references.md prose | ~120 | shipwright-plan + iterate + project | ~2/3 were `{planning_dir}` template (false positives). True prose targets: ~40 |
| `shared/templates/shipwright_sync_config.json` | 6 hardcoded paths | high (template copied into every project) | Found .gitignore bug -- template was ignored |
| `shared/templates/claude-md-template.md` | 1 (`@planning/`) | high (lands in every CLAUDE.md) | Single-line replace |
| `docs/guide.md` | 5 PATH_REFs + 1 new explanation paragraph | high | E expanded to add convention paragraph |
| `docs/hooks-and-pipeline.md` | 9 PATH_REFs | high | Mostly verifier evidence-source descriptions |
| `.gitignore` | 1 line edit | medium | Inline-comment trap: gitignore does NOT support trailing comments. Always put comment on a separate line. |
| `plugin.json` / `marketplace.json` keywords | 4 hits | NONE (descriptive word "planning", not a path) | Skip; allowlist permanently |
| Test fixture `sample_plan_config.json` | 4 path entries | medium | Easy rewrite |
| CI workflows | 0 | -- | None for planning |
| Shell scripts | 0 | -- | None for planning |
| `hooks.json` | 0 | -- | Hooks call shared scripts; pathless |

---

## 5. Test-Suite Layer Schema (final 7 layers)

| Layer | File | What it catches | Validated edge cases |
|---|---|---|---|
| 1 -- Static canon lint | `shared/tests/test_artifact_path_canon.py` | Text-regex + Python-AST scan for legacy literals | Caught bare `Path("planning")`, `os.path.join`, `tmp_path / "planning"`. AST mode was essential -- pure regex would have missed ~30% of Python touchpoints. |
| 2 -- Setup-contract tests | `shared/tests/test_setup_writes_canonical.py` | Per-plugin: setup-{plugin}-session.py writes ONLY under .shipwright/ | Surfaced 1 regression where a test fixture used `tmp_path / ".shipwright" / ".shipwright" / "planning"` (double prefix). |
| 3 -- Integration negative assertion | `integration-tests/test_core_trilogy_flow.py` + `test_state_recovery.py` | E2E trilogy must not produce any legacy top-level dir | Important: load `lib.artifact_migrations` via `importlib.util.spec_from_file_location` to avoid `sys.modules['lib']` poisoning the compliance plugin's separate `lib/` package. |
| 4 -- Drift detector unit tests | `shared/tests/test_stale_artifact_detector.py` | Hook returns correct exit code, JSON, severity, self-heal | Already in place from Sub-Iterate A; reused unchanged. |
| 5 -- gitignore canon | `shared/tests/test_gitignore_canon.py` | Legacy entry kept with "legacy path" comment within `[idx-1, idx+2]` | Trap: gitignore does NOT support trailing comments. Pattern + comment must be on different lines. |
| 6 -- Constants vs manifest cross-validation | not yet in place | Local PLANNING_DIR constant must match manifest | Scoped in Sub-Iterate-A plan but not implemented. Add before next migration if local constants proliferate. |
| 7 -- Cross-platform path tests | `shared/tests/test_path_canon_windows.py` | Windows backslash vs POSIX, symlink handling | Already in place from A; reused. |

**Note on Layer 6:** the planning migration did NOT create local
`PLANNING_DIR` constants in every Python module (we used the literal
`.shipwright/planning` directly because it appeared only a handful of
times per file). If a future artifact is referenced 5+ times in the
same module, introduce a module-local constant *and* implement Layer 6.

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
        "C:/Users/SvenRoth/.claude/plans/iterate-shipwright-relocation-*.md",
        "C:/Users/SvenRoth/.claude/plans/ich-bin-am-berarbeiten-glittery-sun.md",
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
  --plan-file C:/Users/SvenRoth/.claude/plans/<plan>.md \
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

---

## 11. Reference Commits

For grep / blame / re-orientation:

- `7cfa628` -- security report dir relocation, established the
  `.shipwright/` convention.
- `ba0eebe` -- Sub-Iterate A: drift safety net (artifact_migrations
  manifest + Layer-1 lint + Layer-4 detector + gitignore canon).
- `0021a23` -- Sub-Iterate B: shared/ Python migration.
- `2919ccf` -- Sub-Iterate C: plugins/ Python migration + Layer-2
  setup-contract tests.
- `407081d` -- Sub-Iterate D: plugin prose migration.
- `ca1efb8` -- Sub-Iterate E: templates + docs + integration-tests +
  Layer-3 negative-assertion.
- `864420c` -- Sub-Iterate F: hard cutover (status flip), migration
  CLI, next-migration prompt, user-facing migration doc.
- *(this commit)* -- Sub-Iterate G: reference doc + pattern memory.

---

## 12. Quick Start: Migrating the Next Artifact

1. Run `uv run shared/scripts/tools/print_next_migration_prompt.py` --
   it tells you what's next and seeds the kickoff prompt.
2. Read this doc end-to-end (you're doing it).
3. Append a `pending` entry to `ARTIFACT_MIGRATIONS` in
   `shared/scripts/lib/artifact_migrations.py`.
4. Launch the 3 Explore-agent prompts (§ 2) in parallel.
5. Draft sub-iterate plan files A-G in `~/.claude/plans/` using the
   `iterate-shipwright-relocation-*.md` files as templates.
6. External-review the main plan (§ 8).
7. Flip status to `in_progress` and start Sub-Iterate B.
8. Run B-F, each with the same TDD + Layer-1-lint-green discipline.
9. F flips status to `migrated`. The drift detector now hard-gates.
10. G updates THIS reference doc with the new artifact's lessons,
    appends to § 11 reference commits, updates `MEMORY.md` index.
