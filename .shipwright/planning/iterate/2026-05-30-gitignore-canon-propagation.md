# Iterate: Canonical `.shipwright/` gitignore block propagation

- **Run ID:** `iterate-2026-05-30-gitignore-canon-propagation`
- **Intent:** feature / change (systemic infra fix)
- **Complexity:** medium (cross-plugin: shared + adopt + project + tests + docs; new shared module; SSoT template; drift test)
- **Spec Impact:** ADD (new shared module + drift test) + MODIFY (template, framework `.gitignore` markers, adopt/project integration)

## Problem

Framework-added `.gitignore` rules for `.shipwright/` artifacts do **not**
propagate to consuming projects (neither existing nor newly-adopted).

- `shared/templates/shipwright-gitignore.template` is a 3-line orphan
  (`loop.lock` + `runs/`), applied by nobody.
- `/shipwright-adopt` only **checks** coverage (`gitignore_check.py`
  `majority_gitignored` + a handoff report) and hard-enforces only
  `.env.local`. It never **writes** the canonical `.shipwright/` artifact
  block (the `!/.shipwright/agent_docs/` whitelist + re-excludes).
- `/shipwright-project` writes no `.gitignore` entries at all.
- The framework's own `.gitignore` is hand-maintained; the `runtime/`
  re-exclude (ADR-089, 2026-05-27) is drift-guarded by
  `test_runtime_dir_gitignored.py` — but only for the FRAMEWORK repo, not
  for any template or consuming project.

**Symptom (2026-05-29):** shipwright-webui missed
`/.shipwright/agent_docs/runtime/` → the 3 Stop-hook runtime files showed
as untracked clutter. Patched manually in webui (commit f6e34a6). That was
a symptom-fix; this iterate is the systemic fix.

## Decision (Think-Before-Coding)

**Chosen approach — template-as-SSoT + idempotent line-level merge:**

1. `shared/templates/shipwright-gitignore.template` becomes the single
   source of truth: the full canonical `.shipwright/` artifact-ignore
   block, wrapped in stable BEGIN/END markers.
2. A new shared module `shared/scripts/lib/gitignore_canon.py` parses the
   template's marked rule-lines and **idempotently merges** the missing
   ones into a target `.gitignore` (line-level: add missing, never
   duplicate; newly-added lines live in a marked managed block).
3. `/shipwright-adopt` (Step E.6, a standalone `gitignore_canon.py` CLI
   step — NOT inside the grandfathered `generate_adoption_artifacts.py`, to
   respect the bloat anti-ratchet baseline) and `/shipwright-project`
   (in-code in `write-project-config.py`, which is under the LOC limit)
   invoke the merge writer.
4. A drift test asserts the template's marked rules == the framework
   `.gitignore`'s marked rules — so a future ADR that adds a gitignored
   `.shipwright/` dir must edit the template, and the change auto-
   propagates to every consuming project.

**Alternative considered — marker-block whole-replace** (replace the
entire managed block with the template on every run): simpler, but
produces semantic duplicates when a consuming project already has the
canonical rules unmarked (the webui case). Rejected: line-level merge
matches the task's literal "add missing lines, no duplicates" and the
point-4 "back-fill missing rules into EXISTING projects" wording, and is
the cleaner self-heal.

**Scope boundary (YAGNI):** the canonical block is precisely the
`.shipwright/` whitelist + re-excludes (what broke, what ADRs extend).
`.worktrees/` and `*.lock` files are out of scope (separate concerns, not
part of "the canonical `.shipwright` artifact-ignore block"). Point-4
auto-backfill is realized by the merge being idempotent+additive when
adopt/project re-run; wiring it into the every-iterate hot path is a
deliberate non-goal here.

## Affected Boundaries

- `shared/templates/shipwright-gitignore.template` — SSoT file (read by writer + drift test)
- `.gitignore` (framework, this repo) — marker-wrapped block (read by drift test)
- `shared/scripts/lib/gitignore_canon.py` — NEW: template parse + `.gitignore` write (I/O round-trip boundary) + CLI
- `plugins/shipwright-adopt/skills/adopt/SKILL.md` + `references/step-e-artifact-generation.md` — NEW Step E.6 invokes the CLI (generate_adoption_artifacts.py left untouched — bloat baseline)
- `plugins/shipwright-project/scripts/checks/write-project-config.py` — calls writer in-code (`--status complete`)
- `shared/tests/test_gitignore_canon_merge.py`, `test_gitignore_template_congruent.py`, `test_gitignore_propagation_wiring.py` — NEW tests
- project `references/step-7-scaffolding.md` + `docs/hooks-and-pipeline.md` (artifact-write matrix)

## Confidence Calibration
- **Boundaries touched:** template SSoT, framework `.gitignore` (markers only, no rule change), new shared writer (file I/O round-trip), adopt + project integration, drift+writer tests.
- **Empirical probes run:**
  - *Fresh-repo round-trip* (`git init` + merge + `git check-ignore`): `runtime/session_handoff.md` and `decision-drops/d.json` ARE ignored; `agent_docs/architecture.md` and `planning/iterate/x.md` are TRACKED. → PASS.
  - *Webui-regression probe*: a `.gitignore` with the whitelist but missing `runtime/` → before merge `runtime/session_handoff.md` NOT ignored; after merge IS ignored (mirrors webui f6e34a6). → PASS.
  - *Idempotency*: second merge = `unchanged`, byte-for-byte stable. → PASS.
  - *No-duplicate / preserve-user-content*: pre-existing user lines preserved at top; each canonical rule appears exactly once. → PASS.
  - *Drift congruence*: template marked-rules == framework `.gitignore` marked-rules (ordered). → PASS.
  - *End-to-end project*: `write-project-config.py --status complete` created `.gitignore` (12 rules), stdout still pure config JSON; check-ignore confirms runtime ignored / architecture tracked. → PASS.
  - *End-to-end adopt*: `test_adopt_pipeline_subprocess` now asserts `gitignore_merge.action` + runtime rule in `added`; 6/6 pipeline + 296 adopt suite green.
- **Edge cases NOT probed + why acceptable:** (1) a project carrying the *unanchored* variant (`.shipwright/agent_docs/runtime` without leading slash / trailing slash) gets the anchored canonical form added too — harmless redundancy, both ignore the root dir; exact-stripped-match is predictable. (2) `.worktrees/` + `*.lock` files — deliberately out of scope (not part of the canonical `.shipwright` artifact block; separate concerns). (3) iterate-time auto-backfill into the every-iterate hot path — non-goal; self-heal is realized by re-running adopt/project or the new CLI (`uv run shared/scripts/lib/gitignore_canon.py --project-root <path>`).
- **Confidence-pattern check (asymptote):** the high-risk failure mode here is gitignore *negation/re-include ordering* (the classic "can't re-include under an excluded parent" trap). I did not stop at "the merge writes the lines" — I ran the real `git check-ignore` oracle on both fresh and partial-backfill repos and confirmed the tracked-vs-ignored split empirically. No yes-then-bug pattern surfaced. One pre-existing, unrelated red test on `main` (`test_no_legacy_artifact_paths[compliance-migrated]`, tripped by a prior iterate's committed JSON) is recorded as a degraded condition, not introduced here.
