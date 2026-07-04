# Iterate Spec — G4: Authoritative wiring + URL support + plugin polish + standalone CLI

- **Run ID:** `iterate-2026-07-04-grade-g4-plugin-polish`
- **Campaign:** `2026-07-03-shipwright-grade` · sub-iterate `G4`
- **Intent:** FEATURE (new functionality) · **Complexity:** medium (override; classifier under-estimated `small`)
- **Sub-iterate spec:** `.shipwright/planning/iterate/campaigns/2026-07-03-shipwright-grade/sub-iterates/G4-plugin-polish.md`
- **Design:** `Spec/shipwright-grade-plan.md` §4 (C-R4 authoritative/heuristic), §14 C (URL), §14 D (network), §14 F (core/wrapper), §9 (G4 scope)

## Spec Impact
**NONE — framework/grader tooling; no existing FR touched** (FR-gate:
`spec_impact=none, change_type=tooling`, a satisfied no-FR change), matching the
G1–G3 precedent for this campaign. The change is *code-additive* (new
authoritative-ingestion path + URL clone-and-grade + plugin registration; the shared
engine is unchanged and existing `GradeInputs` behaviour is byte-identical), but it
touches no product requirement, so it is not behavior-affecting in the FR sense.

## Risk flags
- `touches_io_boundary` (real, diff-derived): `clone.py` runs `git clone` (subprocess) into a
  `tempfile.TemporaryDirectory`; authoritative ingestion reads a target's `.shipwright/` via
  `collect_all` (json). → **Boundary Probe** + **round-trip test** required.
- `touches_auth`, `touches_rls` (classifier prose FP from "authoritative"/"URL"): **OVERRIDDEN** —
  the diff touches no `**/auth/**`, `src/lib/supabase/`, or RLS files. Recorded in `degraded[]`.
- NOT `cross_component` (no merge/churn/event-log resolver, no hooks.json/`**/hooks/*.py`, no
  phase validators, no campaign drain touched) → no integration-coverage gate.

## Acceptance Criteria (from sub-iterate spec)
- [ ] **AC1** Authoritative vs heuristic wired + labeled; corrupt/partial/stale `.shipwright/`
      falls back to heuristic (tested).
- [ ] **AC2** URL support behind `resolve_target`: shallow clone, purged tempdir (crash-safe),
      scheme allowlist, size/time caps, submodule policy; invalid/inaccessible URL → clean error.
- [ ] **AC3** `grade.py <path|url>` standalone CLI: deterministic, non-interactive, read-only.
- [ ] **AC4** Interactive ≤2-question enrichment; standalone never blocks; answers provenance-stamped.
- [ ] **AC5** `SKILL.md` + `plugin.json` complete; **marketplace manifest entry added**; guide.md
      section; sync-check parity.
- [ ] **AC6** `update-marketplace.sh` + `check_plugin_cache_sync.py --strict` pass (post-merge).
- [ ] **AC7** ruff clean; modules ≤300 LOC.

## Approach (per phase)

### Phase 1 — Authoritative wiring (AC1)
- `routing.py`: add optional `head_sha` param to `decide_routing`; emit `STATE_STALE` via a
  minimal, honest, *positive* staleness rule (the log records ≥1 non-empty `commit` and none is
  HEAD → the log is behind HEAD). Never false-flags a commit-less (worktree-model) log.
- `reuse_bridge.py`: add `load_compliance_ingest()` → lazy `(collect_all, build_grade_inputs)`
  from the compliance plugin (mirrors `engine_bridge`; compliance root already put on `sys.path`).
- New `authoritative.py`: `try_authoritative_grade(context, engine) -> ReportModel | None`.
  `collect_all(root)` → if the data is empty/degenerate return `None` (→ heuristic); else
  `build_grade_inputs(data)` → `engine.compute_grade` (**same engine**) → `build_report_model`
  with `effective_mode="authoritative"` + authoritative provenance overrides. Any exception →
  `None` (fall back). This covers corrupt/partial/stale robustly.
- `grade_inputs_projector.grade_context`: when `decide_routing` detects authoritative, try
  `try_authoritative_grade`; on `None` fall through to the existing heuristic path (labeled).

### Phase 2 — URL clone-and-grade (AC2, AC3)
- New `clone.py`: `clone_url(url, dest) `— scheme allowlist (`https://`, `git@…:`, `owner/repo`
  shorthand → `https://github.com/owner/repo`); list-arg `git clone --depth 1 --no-tags
  --single-branch -c protocol.file.allow=never` (no submodule recursion) via the hardened runner;
  time cap (timeout) + post-clone byte-size cap (purge + error if exceeded).
- `resolve_target.py` (the seam): add `open_target(raw, *, allow_clone=True)` context manager —
  local path → yields `resolve_target(raw)` (no cleanup); URL → `TemporaryDirectory` +
  `clone_url` + yields `resolve_target(clone_dir)`, tempdir purged on exit **even on exception**.
  Keep `resolve_target` local-only (raises on URL) as the low-level validator.
- `grade.py`: use `with open_target(args.path) as target:`; a URL now grades. Deterministic,
  non-interactive (no `input()`), read-only wrt the user's tree (writes only its own tempdir).

### Phase 3 — Plugin surface + registration (AC4, AC5, AC6, AC7)
- `SKILL.md`: retitle scope G2→G4; document authoritative/heuristic, URL usage, and the
  **interactive enrichment protocol** (≤2 Qs, provenance-stamped, never changes the base grade
  unless a documented override; standalone never blocks).
- `plugin.json`: bump `version` to `0.29.1` (monorepo unified marketplace version).
- Register the plugin: `.claude-plugin/marketplace.json` entry (v0.29.1), `scripts/install.sh`,
  `scripts/update-marketplace.sh` PLUGINS array, `README.md` skills table, `CLAUDE.md` Structure
  (also clears the SessionStart drift warning). `docs/guide.md` command-reference section.
  `docs/hooks-and-pipeline.md`: note grade registers no hooks / reads nothing at startup.
- Run `shared/scripts/sync_check.py` → all green.

## Confidence Calibration
- **Boundaries touched:** URL parse + `git clone` subprocess + `TemporaryDirectory` (clone.py);
  target `.shipwright/` json ingestion via `collect_all` (authoritative.py); routing state machine
  (event-log head/tail bounded reads); marketplace/plugin registration JSON.
- **Empirical probes run (live, not just asserted):**
  1. **Authoritative round-trip** — graded THIS repo → `A 99.9`, `mode=authoritative`, verified_from
     `shipwright_events.jsonl (249 events…)`: grader-grade == the repo's dashboard grade (A). ✓
  2. **Real network clone-and-grade** — `grade.py octocat/Hello-World` cloned a live GitHub repo into
     a purged tempdir and graded it (`A`, heuristic) end-to-end. ✓
  3. **Staleness tail-read** — first dogfood mis-fired `stale` because the 64 KB HEAD read saw only
     legacy commit-bearing events; fixed with a bounded TAIL read → now `valid/authoritative`. Pinned
     by `test_large_log_reads_the_tail_not_the_head`. ✓
  4. **Fail-safe fallback** — corrupt (malformed), empty-records, and ingestion-exception targets all
     fall back to labelled heuristic; `--no-clone` URL → clean exit 2, no network. ✓
  5. **Injection-safe clone** — `normalize_url` rejects `http://`/`git://`/`file://`/`ext::…`; the
     clone disables the `ext`+`file` transports and recurses no submodules. ✓
  6. **Crash-safe purge** — a clone that raises mid-flight still purges its `TemporaryDirectory`. ✓
- **Test Completeness Ledger:** see the table below — every AC behaviour is `tested` except the
  interactive-enrichment protocol (a SKILL.md runtime behavior of the Claude Code session, not a CLI
  code path → `requires-interactive-tty`). 0 untested-testable behaviours.
- **Confidence-pattern check:** *depth* — the authoritative path is proven against the real repo AND
  the fallback proven on every degraded shape; *breadth* — 47 new tests across routing/authoritative/
  clone/CLI + a live network probe. No `cross_component` machinery touched → no integration-composition
  row required.

### Review cascade dispositions (GPT-5.4 + Gemini 3.1 Pro external; internal code-reviewer + adversarial doubt-reviewer)
Fixed (defects the cascade surfaced):
- **[MED] git clone could block on an interactive credential/host-key prompt** (private/404/SSH URL → hang to timeout, violating "never blocks"). Fixed in `git_exec.run_git`: `stdin=DEVNULL` + `GIT_TERMINAL_PROMPT=0` + `GIT_ASKPASS=echo` + `GIT_SSH_COMMAND=… -oBatchMode=yes`. **Verified: an auth-required clone now fails in ~1 s, not 60 s.**
- **[MED] authoritative path routed a hostile clone's event log into the unbounded cross-plugin `collect_all`** (500 MB → OOM). Fixed: `authoritative._eventlog_over_cap` refuses >10 MB logs → heuristic fallback (byte-bounded).
- **[MED→doc] post-checkout size cap over-claimed "cannot exhaust the disk"** (tree-bomb materialises during checkout). Docstring reworded; residual documented as an accepted, time-cap-bounded disk-DoS (sandboxing is a plan §6 fast-follow). Clone timeout aligned 120 s → 60 s.
- **[LOW] fail-safe didn't cover model assembly** → moved `build_report_model` inside the `try` (any exception → heuristic).
- **[LOW] symlink-escape guard missing** on routing's event-log/RTM reads → added `_within_root` (parity with `repo_context.read_text`).
- **[LOW] SCP/HTTPS regex allowed a leading-dash host** (ssh option-injection, CVE-2017-1000117 class) → host must start alphanumeric.
- **[LOW] weak stdin test** (source-scan) → replaced with a runtime guard that raises on any stdin read.
- **[LOW] `_SHORTHAND_RE` duplicated** → shared from `resolve_target`.
- **[LOW→doc] staleness depends on the legacy `commit` field** → documented in the module docstring.

Accepted with rationale (not defects):
- **Clone-by-default for URLs** (GPT) — the user-approved contract; cloning ≠ `--allow-network` enrichment; `--no-clone` opts out. Documented in SKILL.md + guide.md.
- **Arbitrary https host** (GPT) — grading any public repo (GitLab/Bitbucket/self-hosted), not GitHub-only, is intended; hardening bounds the surface.
- **`resolve_target` stays local-only** (GPT) — it is the low-level validator; `open_target` dispatches remote-vs-local by existence, so a relative path is never mis-cloned.
- **Over-cap feature sampling may vary** (doubt-reviewer) — honestly labelled `sampled/truncated` in the provenance; within the plan's sampled contract.

### Reflection (F3a)
- **Dogfooding caught two latent G1 bugs the unit tests couldn't:** (a) routing checked
  `.shipwright/events.jsonl` + `rtm.md`, but the REAL Shipwright layout is root
  `shipwright_events.jsonl` + `traceability-matrix.md` — so the authoritative path would
  *never* have fired on an actual Shipwright repo; (b) the 64 KB HEAD-only read made
  staleness mis-fire on this 253 KB log (it saw only the oldest, commit-bearing events).
  Lesson: for a "grade a real repo" feature, grade THE real repo early — the fixtures
  were all clean/synthetic and hid both.
- **The adversarial doubt-reviewer earned its cost:** the two most serious findings
  (checkout tree-bomb disk-DoS; hostile clone → unbounded cross-plugin `collect_all` →
  OOM) came from thinking "what if the cloned repo is hostile," which neither the unit
  tests nor the external review surfaced. Reusing a TRUSTED-context helper (`collect_all`)
  across a NEW trust boundary (an untrusted clone) silently inherits its unbounded contract
  — the bound must be re-imposed at the boundary.
- **Non-interactive git is load-bearing for the URL lead magnet:** without
  `GIT_TERMINAL_PROMPT=0`, a private/404 URL hangs on a credential prompt to the timeout.
  A "never blocks" CLI must close stdin + neutralise every prompt at the runner.

### Test Completeness Ledger
| # | Behaviour (AC) | Disposition | Evidence |
|---|----------------|-------------|----------|
| 1 | Canonical `.shipwright/` layout → authoritative (AC1) | tested | `test_routing::TestCanonicalLayout`, `test_authoritative::test_canonical_records_grade_authoritatively` |
| 2 | Staleness detected (newest work commit ≠ HEAD), commit-less never flagged (AC1) | tested | `test_routing::TestStaleness` (4) + tail-read regression |
| 3 | Corrupt/partial/mixed/empty/exception → heuristic fallback (AC1) | tested | `test_routing` (malformed/partial/mixed), `test_authoritative::{empty,corrupt,fail-safe}` |
| 4 | Grader-grade == dashboard-grade on a real Shipwright repo (AC1) | tested | live probe (`A 99.9` authoritative) |
| 5 | URL scheme allowlist accept/reject (AC2) | tested | `test_clone::TestNormalizeUrl` |
| 6 | Real shallow clone + size cap + crash-safe purge (AC2) | tested | `test_clone::{TestRealClone,TestOpenTarget}` + live network probe |
| 7 | `grade.py <url>` clones & grades; `--no-clone` rejects (AC3) | tested | `test_grade_cli::{test_url_is_cloned_and_graded,test_url_with_no_clone_exits_2}` |
| 8 | Standalone is non-interactive / never blocks (AC3, AC4) | tested | `test_grade_cli::test_standalone_never_blocks_on_input` |
| 9 | Interactive ≤2-Q enrichment, provenance-stamped, base grade unchanged (AC4) | untestable | `requires-interactive-tty` — a SKILL.md runtime protocol for the Claude Code session, not a CLI code path; documented in SKILL.md "Interactive vs standalone" |
| 10 | Plugin registered + version parity (AC5, AC6) | tested | `shared/scripts/sync_check.py` all-green (14 plugins) |
| 11 | ruff clean; modules ≤300 LOC (AC7) | tested | `uvx ruff@0.15.15 check .` green; `wc -l` all ≤214 |
