# Step E — Artifact Generation

Run:

```bash
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/tools/generate_adoption_artifacts.py" \
  --project-root <cwd> \
  [--no-sync] [--no-backfill-events] \
  [--scope <full_app|library|cli>] \
  [--profile <name>] \
  [--split-name <name>]
```

Writes — **in order**:

1. `CLAUDE.md`
2. `.shipwright/agent_docs/{architecture,conventions,decision_log,build_dashboard}.md`
3. `.shipwright/planning/<split>/spec.md`
4. The six required configs (project / plan / build / iterate /
   compliance / + optional sync — `--no-sync` skips it), and
   **`shipwright_run_config.json` LAST**. The iterate config carries
   the documented opt-out fields (`external_review.feedback_iterations`
   for plan/iterate-mode review, `external_code_review.enabled` for the
   code-review cascade); both are independent gates and the cascade
   defaults to enabled.
5. `shipwright_events.jsonl` with one `adopted` event + optional
   backfill.
6. (No project-level hook write.) The `suggest_iterate` UserPromptSubmit
   hook is plugin-owned, registered in
   `plugins/shipwright-iterate/hooks/hooks.json`. If the target project
   carries a legacy `${CLAUDE_PLUGIN_ROOT}` entry from a pre-2026-05-05
   adopt run, the user must remove it manually from
   `.claude/settings.json` to silence the Claude Code "hook is not
   associated with a plugin" red-banner error. The plugin-registered
   hook fires regardless.
7. `e2e/flows/adopted-baseline.spec.ts` if routes.json exists.
8. **Visual frontend documentation (Tier 5).** Three artifacts at
   canonical paths so /shipwright-design / /shipwright-iterate consume
   them without manual fix-up:

   - **`.shipwright/designs/visual-guidelines.md`** — design-system
     view in the canonical schema (typography / colors / spacing /
     radius / shadows / component patterns). Slot-filled from extracted
     tokens; unfilled slots stay `_TBD_` rather than inventing values.
     This is the path /shipwright-design reads, so adopted projects
     can run /shipwright-design without re-authoring the file.
   - **`.shipwright/agent_docs/design_tokens.md`** — raw audit trail of
     Tailwind colors / spacing / fontSize (parsed from
     `tailwind.config.{ts,js,mjs,cjs}` via regex — no Node runtime in
     adopt) plus `:root { --var: ... }` CSS variables from
     `src/**/*.css`. Configs that build their theme dynamically yield
     empty maps; the operator can fill via /shipwright-iterate.
   - **`.shipwright/agent_docs/component_inventory.md`** — architecture
     doc: components table (name, path, props count, usage count)
     sorted by usages descending, plus a screenshot link block. Renamed
     from the legacy `guideline.md`. Adopt automatically backs the
     legacy filename up to `.shipwright/adopt/backups/` if it's present
     from a pre-Fix-1 adopt run.
   - **`.shipwright/agent_docs/visual/screenshots/`** — copies of
     `.shipwright/adopt/screenshots/` (the gitignored crawl workdir)
     so the docs reference a stable, committed location. Re-running
     adopt refreshes them.

   Opt-in: written only when the project has a frontend signal
   (multi-service frontend, components under
   src/components/src/ui/src/app, tailwind.config.*, or `:root` CSS
   variables). Backend-only profiles produce `wrote_docs: false` in
   `results.visual_docs` and write nothing under `.shipwright/`.

9. **Prior-art harvest** (Fix 2). Before writing thin auto-generated
   `decision_log.md` / `conventions.md`, adopt runs
   `prior_art_harvester` to copy any maintainer-written knowledge
   forward. Recognized sources (first hit wins, deterministic, no LLM):

   - **Decision logs:** `docs/adr/`, `docs/architecture/decisions/`,
     `docs/decisions/`, `<root>/ADRs/`, `<root>/decision_log.md`,
     `<root>/agent_docs/decision_log.md`, README "Architecture" /
     "Design decisions" sections.
   - **Conventions:** `CONTRIBUTING.md`, `STYLEGUIDE.md`,
     `docs/conventions.md`, README "Conventions" / "Code style"
     sections, AGENTS.md / CLAUDE.md "Conventions" sections.

   When found, the harvested content is appended verbatim with an
   attribution header documenting the source path. When no source
   matches, adopt falls back to today's auto-generated content. No
   merging, no NLP — operators see exactly what was there.

10. **Sibling-test acceptance criteria** (Fix 5). For every FR with
    a non-test `source_file`, adopt scans conventional sibling test
    paths (`<stem>.test.{ts,tsx,js,jsx,py}`, `<stem>.spec.*`,
    `__tests__/<stem>.test.*`, `tests/<stem>.test.*`,
    `tests/test_<stem>.py`) and harvests `describe(...)` / `it(...)` /
    `test(...)` strings (Jest / Vitest / Mocha) plus `def test_*`
    functions with their docstrings (pytest). Up to 10 ACs per FR;
    enrichment-supplied `acceptance_draft` always wins when present.
    Test files themselves are filtered out of the FR list (Fix 3a).

    **FR `Layers` column (surface-inferred).** Each reverse-engineered FR
    row in the planning `spec.md` carries a `Layers` column declaring the
    test layers it must be covered at, inferred from its detected surface by
    `render_helpers.infer_required_layers`: a route / page / UI-framework
    source ⇒ `e2e`; a migration / schema / table / RLS-policy source ⇒
    `integration`; every FR ⇒ `unit`. Multiple surfaces union. The default is
    deliberately conservative — an unknown surface ⇒ `unit` only — so an
    adopted brownfield repo is not instantly drowned in "MISSING e2e"
    findings (Spec §9). The emitted values are annotated `(inferred)`, which
    the compliance requirement-model parser reads as **advisory**
    (`inferred_legacy` provenance) rather than the author-declared `explicit`
    hard-gate regime. Authors confirm or override via `/shipwright-iterate`.

11. **TODO / FIXME inventory** (Fix 6). After artifact generation,
    adopt ripgreps `\b(TODO|FIXME|HACK|XXX|DEPRECATED)\b:?` over source
    files, respecting `.gitignore` (`git check-ignore -z --stdin`)
    and skipping universal artifact dirs (node_modules, dist, build,
    vendor, etc.). Output: `.shipwright/agent_docs/known_issues.md`
    with a per-marker summary table, sections per marker type, and
    `file:line — text` bullets (per-bullet 200-char cap). Cap of 200
    total entries (top 50 listed, rest summarized as counts). Empty-
    state file is written when zero markers are found — operators
    expect the file to exist either way.

12. **See-also cross-links** (Fix 4). When discoverable, adopt appends
    a `## See also` block to `architecture.md` linking
    `<root>/README.md` (always when present), and
    `<root>/docs/{guide,manual,usage,getting-started,handbook}.md`
    (only when >100 lines). `build_dashboard.md` similarly links
    `<root>/CHANGELOG.md` when present. No broken links — sections are
    omitted entirely when nothing matches.

13. **Security CI scaffold.** Adopt copies the dormant scanner-chain
    workflow into `<root>/.github/workflows/security.yml` so brownfield
    repos start with a Phase-B-ready security baseline. Behavior:
    - **Absent** → write the template verbatim. Workflow ships with
      only `workflow_dispatch:` active; `pull_request:` and `schedule:`
      triggers stay commented until the user activates them at Phase B.
    - **Present** → preserve the existing file untouched, regardless
      of contents. Pre-existing CodeQL workflows, hand-rolled scanner
      configs, and earlier shipwright templates all win.

    The convention lock at `shared/scripts/lib/security_workflow.py`
    is the single source of truth for the deployed-file path, the
    critical-gate step id (`shipwright-critical-gate`), the
    minimum-required permissions, and the SARIF category. The drift
    test at `shared/tests/test_security_workflow_convention.py` pins
    the template at `shared/templates/github-actions/security.yml.template`
    against those constants — the scaffolder cannot drift from what
    `/shipwright-compliance` Group A5 audits.

    Activation guidance — including the GitHub Actions
    permission-implicit-`none` footgun, fork-PR semantics, and
    Phase-B prerequisites — lives at `docs/security-ci-setup.md`.
    The scaffolder result lands in `results.security_ci` as
    `{wrote, path, reason}` so the Step H handoff banner can show
    "installed (dormant)" vs "preserved" without re-stat'ing the file.

    **Companion `.gitleaks.toml` scaffold (Step E.13b).** The deployed
    `security.yml` runs `gitleaks detect --no-git` with **no** `--config`,
    so gitleaks auto-loads a `.gitleaks.toml` from the repo root when
    present. Adopt therefore also copies
    `shared/templates/github-actions/gitleaks.toml.template` to
    `<root>/.gitleaks.toml` (same never-overwrite contract). Without it,
    gitleaks' built-in `sidekiq-secret` rule false-matches the magic-hex
    placeholder `cafebabe:deadbeef` and the hardened critical-gate (which
    blocks on **any** gitleaks result) turns every freshly-adopted repo's
    **first** Security Scan red — a misleading "secret leak" that is no
    leak (empirically proven on leadwright 2026-06-07: run 27086046885 red
    → 27086178138 green after the file was added). The allowlist extends
    the full default ruleset (`useDefault = true`) and suppresses only that
    one self-evident placeholder. The same convention lock declares
    `GITLEAKS_CONFIG_TEMPLATE_PATH` + `GITLEAKS_CONFIG_PATH`; the drift test
    at `shared/tests/test_gitleaks_config_convention.py` pins the template's
    shape. The scaffolder result lands in `results.gitleaks_config` as
    `{wrote, path, reason}`.

    The template also carries the same supply-chain hardening as the
    monorepo's own `security.yml`: the gitleaks install is SHA256-verified
    (download-to-disk + `sha256sum -c` before extract, not an unverified
    `wget | tar` pipe) and `peter-evans/create-or-update-comment` is pinned
    to a full commit SHA rather than the mutable `@v4` tag. Both are pinned
    by `shared/tests/test_security_workflow_convention.py`
    (`TestSupplyChainHardening`).

    **Append-log union merge driver scaffold (Step E.13c).** Adopt also
    lands a root `.gitattributes` declaring `merge=union` for the tracked
    append-log artifacts (`shipwright_events.jsonl`,
    `.shipwright/triage.jsonl`), sourced from
    `shared/templates/gitattributes-union.template` (SSoT
    `shared/scripts/lib/gitattributes_union.py`). `merge=union` is git's
    built-in line-union driver: when two iterates each append, both sides'
    lines are kept automatically (no conflict markers, honored by GitHub's
    server-side PR merge too) — the protection that kept the monorepo
    merge-theater-free but had never reached managed repos (WebUI #96–#100
    hand-resolved exactly these files). **Unlike** the `.gitleaks.toml`
    scaffold this is a **merge, not never-overwrite**: an existing user
    `.gitattributes` is preserved bit-for-bit and only the missing union
    lines are appended (idempotent — a second adopt run is a no-op). The
    same fragment is self-healed into already-adopted repos by the iterate
    flow (`setup_iterate_worktree` → `self_heal_gitattributes`). The
    scaffolder result lands in `results.gitattributes_union` as
    `{wrote, path, reason}` (`scaffolded` / `merged` / `already_present`);
    the drift test `shared/tests/test_gitattributes_union.py` pins
    `UNION_PATHS` to the churn resolver's append-log allowlist.

14. **CI workflow scaffold (profile-aware).** Adopt picks the CI
    template that matches the stack profile detected earlier in the
    pipeline (`snapshot.profile.matched`) and writes it to
    `<root>/.github/workflows/ci.yml`. Three profiles ship templates
    today:
    - `supabase-nextjs` → `ci-supabase-nextjs.yml.template` (single
      `test` job, security + deploy chained, Node 22.x)
    - `vite-hono` → `ci-vite-hono.yml.template` (two-workspace:
      `client-checks` + `server-checks`, both matrixed)
    - `python-plugin-monorepo` → `ci-python-plugin-monorepo.yml.template`
      (uv-driven, ruff + pyright + plugin-tests + integration-tests)

    Every template ships with the **cross-platform OS matrix**
    (`ubuntu-latest` + `windows-latest`, `fail-fast: false`) so
    OS-coupled portability bugs surface at PR time instead of leaking
    through to runtime. Originating regression: `shipwright-webui`
    v0.8.5 — 4 path-self-heal tests silently passed on the Windows dev
    machine and silently failed on Linux CI for 9 push-runs because
    the hand-written `ci.yml` only ran on `ubuntu-latest`.

    Same idempotency contract as Security CI: dormant default
    (`workflow_dispatch:` only), pre-existing `ci.yml` files are
    preserved bit-for-bit. Distinct reason codes
    (`profile_unresolved` vs `no_template_for_profile`) surface
    snapshot-parsing failures upstream rather than masking them as
    "no template available".

    The convention lock at `shared/scripts/lib/ci_workflow.py` is the
    SSoT for the profile→template map, deployed paths, and the
    cross-platform-matrix invariant. Drift test at
    `shared/tests/test_ci_workflow_convention.py` pins every template
    against those constants. The scaffolder result lands in
    `results.ci_workflow` as `{wrote, path, reason}`.

14b. **CodeQL workflow scaffold (profile-aware).** Adopt writes a dormant
    `<root>/.github/workflows/codeql.yml` whose `language:` matrix is
    **rendered** from the detected profile, so a brownfield repo gains the
    `Analyze (<language>)` Required-Check job names B4.5-style automerge
    needs. Unlike the pure-copy CI scaffolder, this one substitutes the
    `${SHIPWRIGHT_CODEQL_LANGUAGES}` placeholder before writing:
    - `python-plugin-monorepo` → `[python]` → check `Analyze (python)`
    - `supabase-nextjs` / `vite-hono` → `[javascript-typescript]` →
      check `Analyze (javascript-typescript)`

    Dormant default (`workflow_dispatch:` only) + never-overwrite, same as
    CI/Security. The analyze step carries `continue-on-error: true` so the
    job stays GREEN on a private repo without GitHub Advanced Security (the
    SARIF upload fails there; the QL analysis still runs) — a Required Check
    that errors would block every PR. Distinct reason codes
    (`profile_unresolved` vs `no_codeql_for_profile`). SSoT:
    `shared/scripts/lib/codeql_workflow.py`; drift test
    `shared/tests/test_codeql_workflow_convention.py`. Result lands in
    `results.codeql_workflow` as `{wrote, path, reason, languages}`.

15. **Claude-Review workflow scaffold.** Adopt writes the independent
    Claude-Code-review workflow to `<root>/.github/workflows/claude-review.yml`.
    Profile-agnostic — single template, no profile branching.

    Unlike CI + Security, this workflow is **NOT dormant by default**:
    `on: pull_request` is the active trigger because firing on PR
    events is the workflow's entire purpose. Same byte-equal idempotency
    contract (pre-existing files preserved). Result lands in
    `results.claude_review_workflow`.

    Origin: commit `8aac61d` (Anthropic Architect Certification best
    practice — "write in one session, review in a different one").

16. **Automerge-readiness doc (`AUTOMERGE_SETUP.md`).** Written **LAST**,
    after every workflow scaffold above, because it derives the
    Required-Check job names by **parsing the deployed**
    `.github/workflows/*.yml` (matrix-expanded) rather than guessing — a
    wrong name in branch protection silently never matches (the "armed but
    waiting" automerge killer). The profile-aware doc lands at the repo root
    and walks the adopter through: which Required-Check names this repo
    actually produces, the "activate the dormant `pull_request:` trigger
    **before** requiring the check" rule, the branch-protection UI steps
    (0 approvals; signing deliberately NOT required for headless iterate
    PRs), `Allow auto-merge`, and the `gh pr merge --auto --squash` pattern.
    It also documents that CodeQL is the paid-on-private GHAS path (vs the
    free `security.yml` scanner chain) and that anti-ratchet `bloat-check`
    is a deferred manual opt-in. Never-overwrite. SSoT/render:
    `shared/scripts/lib/automerge_readiness.py`; template
    `shared/templates/AUTOMERGE_SETUP.md.template`. Result lands in
    `results.automerge_setup` as `{wrote, path, reason, required_checks}`.

**Vite DX templates (offer-only, NEVER auto-applied).** If
`package.json` lists `vite` as a dependency (any Vite-based stack), the
adoption handoff includes a one-line opt-in note pointing to:

- `shared/templates/vite.config.ts.template` — mode-gated dev plugin
  slot, allowedHosts wildcard, sensible defaults. Useful only if the
  user wants to start over from a clean baseline.
- `shared/templates/dev-error-overlay.tsx.template` +
  `dev-banner.tsx.template` — drop-in dev-mode React components for
  runtime-error modals and a visible dev-mode pill. Both are
  `import.meta.env.DEV`-gated so they no-op in prod.
- `shared/templates/path-helpers.ts.template` +
  `path-helpers.test.ts.template` — `pickPathModule(input)` heuristic
  for cross-platform path classification (returns `path.win32` or
  `path.posix` based on input shape). Drop into any Node project that
  needs to parse path strings whose platform-origin differs from the
  runner's native `path` module. The empirical Vitest suite covers
  Windows + POSIX + UNC + edge cases; passes identically on both OSes.
  Origin: `shipwright-webui` v0.8.5 cross-platform regression.

**Existing `vite.config.ts` is NEVER overwritten.** The handoff lists
the templates so the user can copy/adapt them at their own pace; adopt
itself touches no Vite files.

**Features merge (4.2)**. Layer-1 AST features and Layer-1.5 crawl routes
are unioned by route key — neither side is silently dropped when the
other is non-empty. Each merged feature carries an `origin` of
`ast | crawl | ast+crawl`. spec.md therefore lists both API FRs (from
AST scan of route handlers) and UI FRs (from the crawl), giving a
complete picture for downstream consumers.

**Canonical gitignore propagation (Step E.6 — MANDATORY).** Immediately
after the artifact generator returns, adopt MUST merge the canonical
`.shipwright/` artifact-ignore block into the project's `.gitignore` so
framework-managed ignore rules propagate to this brownfield repo. Run:

```bash
uv run "{shared_root}/scripts/lib/gitignore_canon.py" --project-root "{project_root}"
```

The SSoT is `shared/templates/shipwright-gitignore.template`; the merge is
**idempotent + additive** (line-level: adds only missing rules inside a
managed BEGIN/END block, never duplicates), so re-running adopt back-fills
only rules a later template revision introduces — this self-heals an
already-adopted repo. It closes the gap where framework-added ignore rules
(e.g. `/.shipwright/agent_docs/runtime/`, ADR-089) never reached consuming
projects: transient artifacts get ignored while the canonical SDLC-doc
homes stay tracked. The JSON output carries
`{action, path, added, already_present, total_canonical}` (`action` ∈
`created`/`updated`/`unchanged`) for the Step H banner. Drift between the
template and the framework's own `.gitignore` block is caught by
`shared/tests/test_gitignore_template_congruent.py`. (It runs as a separate
CLI rather than inside `generate_adoption_artifacts.py` to keep that
already-grandfathered file under its bloat baseline —
iterate-2026-05-30-gitignore-canon-propagation.)

The canon block also scaffolds the ignore for the per-tree background-triage
**outbox** `.shipwright/triage.outbox.jsonl` (campaign
`2026-06-08-triage-outbox-delivery`): the `/.shipwright/*` whitelist wildcard
ignores it, and an explicit `/.shipwright/triage.outbox.jsonl` line pins the
intent (no `!`-re-include) so a future template edit can't silently start
tracking the buffer. Idle-main background producers append there (never the
tracked `triage.jsonl`); `setup_iterate_worktree` sweeps it into the iterate
PR branch. An already-adopted repo whose plugin cache predates this campaign
gets the block back-filled automatically on its next iterate by
`shared/scripts/lib/gitignore_selfheal.self_heal_gitignore`
(`setup_iterate_worktree` step 4.6 — sibling of the `.gitattributes` self-heal).

**Gitignore awareness (4.1)**. Inside `generate_adoption_artifacts.py`,
after all artifact writes, the tool runs `git check-ignore` against every
output path. The result lands in `results.gitignore_report` as
`{total, gitignored: [...], majority_gitignored: bool}`. This runs **before**
the E.6 merge above, so the report is a *pre-merge, advisory* snapshot; the
E.6 merge is what actually guarantees the canonical ignore rules are in
place. If the report still warns after E.6 has run, surface it — but the
canonical `.shipwright/` homes are tracked by design once E.6 completes.

If `majority_gitignored` is true (≥50% of artifacts excluded), surface
a `**GITIGNORED OUTPUTS**` block in the handoff and ask the user via
`AskUserQuestion`:

> "N of M adopt-generated artifacts are excluded by .gitignore (e.g.
> .shipwright/agent_docs/, .shipwright/planning/, shipwright_*_config.json). They will not be
> committed unless you adjust .gitignore. Continue without changes,
> stop and review .gitignore, or proceed and adjust manually after?"

See [artifact-templates.md](artifact-templates.md) for template slot
mapping.
