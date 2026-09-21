# Iterate Spec: codex-plugin-bundle-root-contract

- **Run ID:** iterate-2026-09-20-codex-plugin-bundle-root-contract
- **Type:** feature
- **Complexity:** medium
- **Status:** implemented
- **Campaign:** codex-plugin-execution-reliability, sub-iterate R1 (see
  `.shipwright/planning/iterate/campaigns/codex-plugin-execution-reliability/sub-iterates/R1-m1-m2-plugin-bundle-and-root-contract.md`)

## Goal

Pull forward M1 + M2 from `Spec/codex-runtime-integration-spec.md` §7, as
scoped by `Spec/codex-plugin-execution-reliability.md` Phase 1: build a real,
deterministic, installable Codex plugin bundle containing every Shipwright
skill (not a prose pointer into `~/.claude/plugins/cache`, which Codex has no
business reading), and establish `SHIPWRIGHT_PLUGIN_ROOT` as the one
canonical variable that resolves identically whether a script is invoked from
the monorepo, Claude's plugin cache, or the Codex plugin cache. Infrastructure
only — no enforcement/behavior change (that is R2/M3).

## Acceptance Criteria

- [x] AC1: A clean Codex installation, with the Shipwright bundle added from a
  local file-based marketplace and installed, discovers every intended
  Shipwright skill by name in a live Codex session (proven live, not just by
  fixture — see Verification).
- [x] AC2: A single shared resolver function returns the identical
  `SHIPWRIGHT_PLUGIN_ROOT` value under three simulated directory shapes: the
  monorepo working tree, a Claude plugin-cache install
  (`.../cache/shipwright/<plugin>/<version>/`), and a Codex plugin-cache
  install (`~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/` — shape
  confirmed live during Repo Scout, see Design Notes). **This is a
  value-level contract only:** the resolver returns whatever the active
  env var was set to, verbatim, and does not parse or guess cache topology.
  It does NOT prove that logic which DOES parse the plugin-root path — e.g.
  `phase_from_plugin_root()`'s `shipwright-<phase>` name matching, used by
  the two audit hooks — recognizes a phase under the real Codex bundle: that
  bundle installs as ONE umbrella plugin (`.../cache/shipwright/shipwright/<version>/`,
  confirmed live), which has no per-plugin name component to match against.
  Phase-aware hook behavior under the Codex-installed bundle is unsolved and
  out of scope for this iterate (doubt-review, 2026-09-20 — see Out of
  Scope).
- [x] AC3: Every real `CLAUDE_PLUGIN_ROOT`-reading call site is migrated to the
  new precedence and its own existing tests still pass unchanged (regression,
  not behavior change). Repo Scout's "6" estimate (from the pre-build interview,
  before the codebase was searched exhaustively) turned out to be 4 real
  candidates once grepped for: `capture_session_id.py`,
  `audit_phase_quality_on_stop.py`, and `audit_compliance_on_stop.py` import
  the shared resolver directly; `cleanup-review-scratch-on-code-reviewer-failure.py`
  inlines the same three-variable precedence instead (ADR-044 self-containment
  constraint — no cross-plugin `shared/` import from this hook, see Out of
  Scope). All 4 now resolve `CLAUDE_PLUGIN_ROOT` in addition to
  `SHIPWRIGHT_PLUGIN_ROOT`/`PLUGIN_ROOT` — an earlier version of this note
  excluded the 4th site on the false premise that
  `capture_session_id.py` had already exported `SHIPWRIGHT_PLUGIN_ROOT` by
  the time it runs (`additionalContext` is model-visible text, not an OS
  environment export — doubt-review, 2026-09-20, also see docs/hooks-and-pipeline.md).
  Without the `CLAUDE_PLUGIN_ROOT` fallback this hook was permanently dark in
  production, a pre-existing defect this iterate's own migration now fixes.
  `generate_session_handoff.py`'s only reference is a docstring usage
  example, not a live read.
- [x] AC4: A builder script deterministically produces the Codex plugin bundle
  (`.codex-plugin/plugin.json` + copied skills/scripts/`shared/`) from the 14
  Claude plugin manifests and `shared/`; a second, no-source-change rebuild is
  byte-for-byte identical to the first.
- [x] AC5: A drift/verifier script fails when the bundle is stale relative to
  source (source changed, bundle not rebuilt), and fails when the bundle
  contains a file not traceable to a declared source (undeclared generated
  content / path escape).
- [x] AC6: `.claude-plugin/marketplace.json` and all 14 Claude per-plugin
  manifests are unchanged by this iterate (byte-identical diff check).

## Spec Impact

- **Classification:** add
- **ADD** (new FR appended): FR-01.21 — Codex Plugin Distribution
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** n/a (classification is ADD)

## Out of Scope

- Hook **execution/enforcement** semantics (M3) — the bundle's
  `.codex-plugin/plugin.json` carries a best-effort hook manifest translated
  from the 14 Claude manifests, but this iterate does not prove hooks fire,
  block, or aggregate under Codex. Proving that requires an interactive,
  human-mediated Codex hook-trust review (`codex /hooks`) that this session
  cannot automate (`--dangerously-bypass-hook-trust` is a real safety bypass
  and was correctly refused when attempted during Repo Scout) — this is the
  same gap `Spec/codex-plugin-execution-reliability.md` §2 already names as
  the accepted M9 gap, and it is R2's job (gated on that spec's own
  precondition: "ordinary, non-bypassed hook-trust denial via `codex
  /hooks`"). **This is an observational gap, not a known-defect gap:**
  doubt-review (2026-09-20) caught that the rewrite target originally used
  here (`${SHIPWRIGHT_PLUGIN_ROOT}`) is never set at shell-expansion time by
  either runtime — a statically-knowable HIGH-severity bug that would have
  made every bundled hook command fail regardless of the trust question.
  Fixed: the rewrite now targets `${CLAUDE_PLUGIN_ROOT}`, the variable Codex
  does set (alongside its native `PLUGIN_ROOT`) for a plugin-bundled hook
  (`Spec/codex-runtime-integration-spec.md` lines 73-77, 107). The remaining
  gap is genuinely just "unobserved because trust-gated," not "known broken."
- Phase recognition under the Codex-installed bundle. `phase_from_plugin_root()`
  (used by `audit_phase_quality_on_stop.py` and `audit_compliance_on_stop.py`)
  matches a `shipwright-<phase>` directory-name component; the real Codex
  bundle installs as ONE umbrella plugin (`.../cache/shipwright/shipwright/<version>/`,
  confirmed live), which has no such component. Under the real bundle these
  two hooks will resolve a plugin root successfully (AC2/AC3) but still no-op
  on phase detection (same as today's greenfield/foreign-plugin path) — this
  iterate proves the *root-resolution* contract only, not phase-aware hook
  behavior under Codex, which is unsolved and belongs to a later milestone
  (doubt-review, 2026-09-20).
- Subagent/role mapping (M4), `AGENTS.md`/`.codex/agents/*.toml` generation
  (M5), attribution (M6), campaign durability (M8), cache-health reporting
  (M9), the documentation sweep (M11), managed app-server mode (W4), and all
  of W1–W7 — per the campaign's own non-goals, unchanged here.
- An `npx`-based installer for the Codex bundle. The build-output directory
  is shaped so one could be added later, but none is built now (parent spec
  §3 non-goals: no `npx` adapter work absent a proven runtime defect).
- Rewriting the 12 hook-registered `hooks.json` files themselves. This
  iterate only *reads* them to generate the bundle's hook manifest.
- Rewriting the path templates embedded in each of the 14 `SKILL.md` files'
  own prose and linked reference trees (e.g. "Base directory for this
  skill: {plugin_root}", or a reference doc's own relative links). Those are
  agent-interpreted instructional text, not a machine-executed integration
  point the way a hook command is — this iterate rewrites bundled **hook
  command** paths only (mechanical, testable — mini-plan step 6), because
  that is what M1's own acceptance bar ("no skill depends on
  `~/.claude/plugins/cache`") is about. Making every skill's own internal
  prose fully self-consistent under the umbrella bundle's directory layout
  is real behavior-execution correctness and belongs with the M3/Slice-2
  work that actually exercises Codex running a skill end-to-end, not with
  this infra-only pass.

## Design Notes

n/a — no UI.

### AC1 live proof: real bundle, real Codex install (2026-09-20)

Post-build (after `build_codex_plugin.py` + `codex_hook_merge.py` landed and
the real 14-plugin bundle was rebuilt clean): `codex plugin marketplace add
<worktree>/dist`, then `codex plugin add shipwright@shipwright` — installed
at `~/.codex/plugins/cache/shipwright/shipwright/0.33.1` (version taken from
`.claude-plugin/marketplace.json`, confirming AC2's versioned-cache-shape
fixture matches a real install). `codex exec --json` (stdin explicitly
closed with `< /dev/null` — a bare `codex exec "<prompt>"` run in a
backgrounded shell hangs forever waiting on stdin EOF for its `<stdin>`
block, since a piped-but-empty stdin is still "stdin is piped" per the CLI's
own docs) asked the session to enumerate every available skill. Result: all
14 real Shipwright skills appeared under the `shipwright:` prefix
(`shipwright:grade`, `shipwright:shipwright-adopt`, `-build`, `-changelog`,
`-compliance`, `-deploy`, `-design`, `-iterate`, `-plan`, `-preview`,
`-project`, `-run`, `-security`, `-test`) — one name per bundled skill, each
matching that skill's own `SKILL.md` frontmatter `name:` field (e.g.
`skills/adopt/SKILL.md` → `name: shipwright-adopt`; `skills/grade/SKILL.md`
→ `name: grade`), 14/14, none missing or extra. Full JSON transcript
captured at
`ac1-live-skill-discovery-probe.jsonl` in this directory. Cleaned up
afterward (`codex plugin remove` + `codex plugin marketplace remove`), same
as the Repo Scout probe below.

This supersedes the Repo Scout probe as AC1's evidence: that earlier probe
(next subsection) proved the general Codex skill-discovery mechanism against
a hand-built one-skill toy plugin, built *before* `build_codex_plugin.py`
existed — it never proved that the real builder's real output exposes every
real skill. This probe is against the actual bundle produced by the actual
builder, which is what AC1's "proven live, not just by fixture" bar requires.

### Repo Scout findings (live Codex CLI probe, 2026-09-20)

A minimal probe plugin (`probe-plugin`, one `SessionStart` command hook, one
trivial skill) was built, registered via `codex plugin marketplace add`
against a local scratch directory, and installed via `codex plugin add
probe-plugin@probe-marketplace`. Findings, all reproducible and cleaned up
afterward (`codex plugin remove` + `codex plugin marketplace remove`):

1. **Codex marketplace manifest location:** `<marketplace-root>/.agents/plugins/marketplace.json`
   (NOT `.codex-plugin/marketplace.json` — that path was tried first and
   rejected by `codex plugin marketplace add` with "marketplace root does not
   contain a supported manifest"). Confirmed against the real, public
   `github.com/openai/plugins` marketplace (already configured on this
   machine as `openai-curated`), which carries its manifest at the same path
   under git.
2. **Plugin manifest location:** `<plugin-root>/.codex-plugin/plugin.json` —
   matches the parent spec's own naming and every real installed plugin
   inspected (`browser`, `chrome`, `computer-use`, `superpowers`, etc.).
3. **Codex plugin cache shape (confirmed live):**
   `~/.codex/plugins/cache/<marketplace-name>/<plugin-name>/<version>/` —
   directly analogous to Claude's own
   `~/.claude/plugins/cache/<marketplace-name>/<plugin-name>/<version>/`.
   This is the shape AC2's fixture reproduces.
4. **Skill discovery: PROVEN live.** Asking the installed Codex session to
   list its available skills returned `probe-plugin:probe-skill` alongside
   every other installed plugin's skills — this is the direct evidence for
   AC1's mechanism (Codex reads `skills` from `.codex-plugin/plugin.json`
   correctly for a locally-installed, file-based plugin).
5. **Hook execution: gated behind interactive trust, not directly
   observable from this session.** `codex exec` (headless) did not execute
   the probe's `SessionStart` command hook — no observable side effect, no
   error, no trust prompt in the JSON event stream. `codex exec --dangerously-bypass-hook-trust`
   would force it, but that flag is a genuine safety bypass and this
   session's own auto-mode classifier correctly declined to run it. This
   means: (a) the exact runtime shape of `PLUGIN_ROOT`/`CLAUDE_PLUGIN_ROOT`
   as set *by a live Codex hook invocation* is not empirically confirmed by
   this iterate — AC2 is proved by a fixture reproducing the directory shape
   above, not by a live hook firing; (b) no real, uncommitted plugin among
   the 181 in the public `openai/plugins` marketplace, nor any bundled
   OpenAI-authored plugin already installed on this machine, uses a
   `"type": "command"` hook anywhere — every observed hook is `"type":
   "mcp_tool"`. This is a materially useful finding for R2 (M3), which this
   iterate does not otherwise touch: the parent spec's assumption that
   "existing hook commands can therefore be tested before they are
   rewritten" has zero corroborating real-world precedent in this
   environment, and R2 should treat command-hook support as unproven until
   it does its own interactive trust-review probe, not as inherited fact
   from this iterate.
6. **No canonical `hooks.json`-file-path example found either** — the
   `plugin-json-spec.md` reference (from Codex's own bundled
   `plugin-creator` skill, `~/.codex/.tmp/plugins/.agents/skills/plugin-creator/`)
   documents `"hooks": "./hooks.json"` as a path-string option, but the
   `browser` plugin instead inlines the hook object directly under a
   `"hooks"` key shaped exactly like Claude's own `hooks.json` (nested
   `hooks.hooks.<EventName>`). Both forms appear to be accepted; this
   iterate's builder targets the inline form, since it is what the one
   real example with actual hook content uses.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `shared/scripts/tools/build_codex_plugin.py` | Codex CLI (`.codex-plugin/plugin.json`, skills, bundled `shared/`) | JSON manifest + copied directory tree |
| `shared/scripts/tools/build_codex_plugin.py` | `shared/scripts/tools/verify_codex_plugin_bundle.py` (drift/manifest check) | `BUILD_MANIFEST.json`: bundled-relative-path→sha256 map only (source path is NOT recorded per entry — the verifier re-derives source provenance by a fresh rebuild-and-diff instead of trusting a stored mapping, per this file's own docstring: "never trusts the live bundle's own BUILD_MANIFEST.json ... the fresh rebuild IS the ground truth" — corrected wording, external code review, 2026-09-20) |
| `shared/scripts/lib/plugin_root.py` (new resolver) | the 3 real `CLAUDE_PLUGIN_ROOT`-reading call sites migrated in this iterate (`capture_session_id.py`, `audit_phase_quality_on_stop.py`, `audit_compliance_on_stop.py` — see AC3) | environment variables (`SHIPWRIGHT_PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT`, `PLUGIN_ROOT`) |

## External Plan Review (Step 3.5, `external_review.py --mode iterate`)

- **Ran:** yes — LATE, same process gap as Internal Plan Review above (should
  run before Branch A/B/C, ran retroactively over the finished mini-plan/spec
  instead). `--driver claude`.
- **Verdicts:** glm=approve, openai=revise. No contradiction requiring
  resolution (adjacent verdicts).
- **Two `high`-severity findings from openai, both verified FALSE against
  the live tree and declined with rebuttal:**
  1. Claimed `resolve_plugin_root()` returns `Path` and violates AC2's
     string-preservation contract. **False**: `plugin_root.py` already
     defines `resolve_plugin_root_str() -> str` (verbatim, no `Path`
     round-trip) as the canonical resolver, with `resolve_plugin_root() ->
     Path` as a separate convenience wrapper for filesystem-operation
     callers. Confirmed by reading the live file
     (`shared/scripts/lib/plugin_root.py:50-72`).
  2. Claimed the mini-plan names only `capture_session_id.py` and omits the
     cleanup-hook call site. **False**: the mini-plan already lists all 4
     real call sites (lines 15-19), including the cleanup hook's inline
     ADR-044 fallback and the doubt-review correction of the original false
     "already exported" claim. Confirmed by reading the live file.
- **Remaining findings (medium/low), triaged:**
  - security/medium (both legs) — raw-filesystem copy in `build_bundle`, not
    a git-tracked snapshot. **Disclose** — same finding as Internal Plan
    Review's finding 2; already recorded there as a publish-milestone
    precondition.
  - risk/medium (both legs) — hook-merge ordering machinery and the
    `${CLAUDE_PLUGIN_ROOT}` rewrite target are unvalidated against Codex's
    real (unobserved) hook-execution semantics. **Disclose** — same as
    Internal Plan Review's finding 1; R2's hook-trust probe is the
    validation point.
  - risk/low (glm) — the cleanup hook's inlined precedence copy could drift
    from `plugin_root.py`'s if one is reordered without the other.
    **Disclose** — a real but low-value-to-fix-now gap: any robust check
    would need to read the hook script's source as text (it cannot import
    `shared/` per ADR-044, and neither can a test in its own plugin's test
    root without risking the same `lib` package collision) rather than a
    normal import-and-compare test, which is fragile for a 3-tuple that
    changes about once a doubt-review cycle. Left as a documented gap
    rather than a rote fix.
  - edge-case/low (glm) — bundle version vs. marketplace version sync isn't
    independently checked. **Disclose** — no real drift observed; would
    duplicate AC4/AC5's existing hash-based drift detection for marginal
    benefit.
  - edge-case/medium (openai) — determinism edge cases beyond file content
    (JSON key ordering already fixed via `sort_keys=True`; loose `.pyc`
    outside `__pycache__`, symlinks, permissions, timestamps not
    independently normalized/rejected). **Disclose** — no instance in the
    real 14-plugin tree; hypothetical hardening, not a present defect.
  - risk/low (glm) — inventory how many bundled `SKILL.md` files reference
    `{plugin_root}`/`{root}` template tokens that would resolve wrong under
    the flattened bundle layout. **Disclose, with a plain read-only check
    performed on the spot** (no code change): `grep -rl '{plugin_root}\|{root}'
    dist/codex-plugin/skills/*/SKILL.md` finds 10 of the 14 bundled
    SKILL.md files. This is a real, non-trivial number, sizing (not
    resolving) the deferred M3/M4 prose-path work this iterate's own Out of
    Scope section already defers — recorded here as the concrete count for
    whoever picks that work up.
- **Status:** 0 fixed (both real-code findings already correct on
  inspection), 6 disclosed, 2 declined (with rebuttal evidence above)

## Internal Plan Review (opus-plan-reviewer)

- **Ran:** yes — LATE (process gap: this pass is specified to run before
  Branch A/B/C, before build; it was missed in the driving session and only
  run retroactively, over the finished mini-plan/spec/diff, after the full
  code/doubt/spec review cascade had already passed). Noted here for
  honesty, not as a template to repeat.
- **Severity:** medium
- **Summary:** Architecturally sound for the stated infra-only scope; two
  medium findings worth carrying forward rather than fixing now, one low
  finding fixed on the spot, one low finding confirmed as already-correct
  scope.
- **Findings:**
  1. architecture/medium — the hook-merge ordering machinery
     (`codex_hook_merge.py` + `codex_hook_inventory.py`) is more general
     than the mini-plan's own stated boundary, built before any evidence
     Codex's command-hook execution model needs or will honor it (the
     iterate's own Repo Scout found real installed Codex plugins use only
     `mcp_tool` hooks). Disposition: **disclose**.
  2. security/medium — `build_bundle()` copies from the raw working tree
     (filtered by directory name only), not a git-tracked snapshot; harmless
     today (`dist/` is gitignored, local-only) but a latent secret-leak
     vector once a publish milestone exists. Disposition: **disclose**.
  3. architecture/low — no collision guard on skill-name flattening across
     plugins; `_copy_tree`'s rmtree would silently discard one plugin's
     skill in favor of another's same-named one. Disposition: **fix** —
     added a `BundleCollisionError` guard in `build_bundle` (mirrors the
     hook-merge module's own collision-refusal philosophy) plus
     `test_refuses_a_same_named_skill_declared_by_two_plugins`.
  4. completeness/low — `agents/` (subagent definitions) is not bundled.
     Disposition: **decline** — already explicitly out of scope (M4,
     subagent/role mapping), confirmed correct rather than accidental.
- **Known limitations:**
  - Hook-ordering algorithm (finding 1) is unvalidated against Codex's real
    hook-execution semantics; R2's hook-trust probe should re-verify or the
    algorithm may need redesign once real behavior is observed.
  - Bundle builder reads the raw filesystem, not git-tracked content
    (finding 2); must be closed as a named precondition before any future
    publish-oriented milestone (`Spec/codex-runtime-integration-spec.md` §7
    Slice 5).
  - Skill-discovery succeeding (AC1) does not prove subagent-dependent
    skills work end-to-end under Codex (finding 4) — a real gap for M4, not
    this iterate.
- **Status:** 1 fixed, 2 disclosed, 1 declined

## External Code Review (Step 3.7 cascade, `external_review.py --mode code`)

- **Ran:** yes, over the full diff (`git diff HEAD`, 3397 lines) against this
  spec, `--driver claude`.
- **Verdicts:** glm=revise, openai=revise. No contradiction requiring
  resolution (both agree).
- **Findings, triaged:**
  1. bug/medium (both legs, independently) — the cleanup hook's
     `resolve_shared_root()` computed only the Claude-cache shape
     (`plugin_root/../../shared`), which points outside the bundle entirely
     under the Codex umbrella layout (`plugin_root/shared`), silently
     no-opping the hook under Codex — recurring the exact "permanently dark
     hook" defect this iterate's own AC3 fixes on the Claude side.
     **Fix** — try `plugin_root/shared` first, fall back to
     `plugin_root/../../shared`; new test
     `test_resolve_shared_root_prefers_the_codex_bundle_shape`.
  2. spec/low-medium (both legs) — `BUILD_MANIFEST.json` is a
     bundled-path→hash map, not the "source→bundled-file map" the mini-plan
     and this spec's Affected Boundaries table claimed. **Fix (wording, not
     code)** — corrected both documents; the verifier's actual
     fresh-rebuild-and-diff design already delivers AC5's guarantee without
     a stored source mapping.
  3. bug/low (glm) — `verify_codex_plugin_bundle.py`'s `main()` caught only
     `BundleCollisionError`, not `UnsafeOutputPathError`, unlike the
     builder's own `main()`. **Fix** — added the second exception type for
     symmetry. No dedicated test: `verify_bundle`'s own call to
     `build_bundle` always targets a guaranteed-fresh temp directory, so
     `UnsafeOutputPathError` is not reachable through this call site today;
     recorded here rather than fabricating a test for an unreachable branch.
  4. test/low (glm) — 3 new "codex native" tests (`test_capture_session_id.py`,
     `test_audit_compliance_on_stop.py`, `test_audit_phase_quality_stop_hook_direct.py`)
     `delenv`'d `CLAUDE_PLUGIN_ROOT` but not `SHIPWRIGHT_PLUGIN_ROOT`, unlike
     `test_plugin_root.py`'s own autouse fixture — a theoretical false-pass
     risk if `SHIPWRIGHT_PLUGIN_ROOT` were ever ambient in a test process
     (never true today per AC3's own finding that nothing exports it into a
     hook subprocess's OS environment). **Fix** — added the missing
     `delenv` to all 3.
  5. spec/low (glm) — mini-plan §2 step 2 still undercounted the migrated
     call sites to just `capture_session_id.py`, contradicting its own §1
     (which lists all 3). **Fix** — corrected the line with a
     "SUPERSEDED" note, same pattern as the doc's other corrections.
  6. security/medium (openai) — `_copy_tree`/`_hash_tree` follow symlinks by
     default and neither rejects nor flags them; a symlink could copy
     content from outside a declared source root, undetected by the
     hash-based verifier. **Disclose** — no symlink exists anywhere in the
     real `plugins/`/`shared/` trees today (confirmed: `find plugins shared
     -type l` returns nothing); same broader category as Internal Plan
     Review's finding 2 (raw-filesystem-copy trust boundary), carried
     forward together as a publish-milestone precondition rather than fixed
     for a hypothetical shape absent from the real tree.
  7. regression/medium (openai) — command hooks are merged by path/tokens
     only, never comparing same-relative-path script CONTENT across
     origins; a genuinely divergent same-path script would be silently
     dropped. **Already disclosed** — this is exactly
     `codex_hook_inventory.py`'s own documented "Known unchecked
     assumptions" bullet 2, not a new finding.
  8. edge-case/medium (openai) — determinism beyond file content (JSON
     ordering already fixed via `sort_keys=True`; permissions, timestamps,
     loose `.pyc` outside `__pycache__` not independently normalized).
     **Disclose** — no instance in the real tree; hypothetical hardening.
  9. edge-case/medium (glm, secondary point inside finding 1) — speculated
     the Claude-cache `../../shared` shape might also be wrong "at a real
     cache install." **Verified false**: the real Claude cache shape is
     `cache/shipwright/<plugin>/<version>/`, exactly 2 directory levels
     under the vendor dir where `shared/` lives as a sibling (confirmed by
     listing `~/.claude/plugins/cache/shipwright/`) — the same 2-level
     depth as the monorepo's own `plugins/<name>/` shape the existing test
     already covers, so no additional fixture was needed.
- **Status:** 4 fixed (1 real bug + 3 hygiene/wording), 3 disclosed
  (2 already-known, 1 new), 1 verified-false and declined (with rebuttal),
  1 confirmed-correct-as-tested (no action)

## Confidence Calibration

- **Boundaries touched:** the three Affected Boundaries rows above.
- **Empirical probes run, with results:**
  1. Live Codex marketplace-add + plugin-add + skill-discovery probe against
     the REAL `dist/codex-plugin` bundle (built by the real
     `build_codex_plugin.py`, not a toy fixture) — installed at
     `~/.codex/plugins/cache/shipwright/shipwright/0.33.1`; `codex exec`
     enumerated all 14 real Shipwright skills under the `shipwright:`
     prefix, one per bundled skill (each matching that skill's own
     `SKILL.md` frontmatter `name:` field), 14/14, none missing or extra.
     Transcript: `ac1-live-skill-discovery-probe.jsonl` in this iterate's
     evidence directory. This is AC1's evidence (see Design Notes — this
     supersedes the earlier Repo Scout probe against a one-skill toy
     plugin, which only proved the general discovery mechanism, not that
     the real bundle exposes every real skill). PASS.
  2. `shared/tests/test_plugin_root.py` (10 tests) — precedence order
     (`SHIPWRIGHT_PLUGIN_ROOT` > `CLAUDE_PLUGIN_ROOT` > `PLUGIN_ROOT` >
     raise — reordered under doubt-review, 2026-09-20: the original
     `SHIPWRIGHT > PLUGIN_ROOT > CLAUDE` order let a generic, ambient
     `PLUGIN_ROOT` silently outrank the variable Claude itself sets for
     every hook invocation, for zero benefit under Codex, which sets both to
     the same value for a plugin-bundled hook), the 3 real directory shapes
     (monorepo, Claude cache, Codex cache — the Codex shape corrected to the
     live-confirmed umbrella install path, `.../cache/shipwright/shipwright/<version>/`,
     also under doubt-review), and the no-Path-round-trip
     string-preservation guarantee. 10/10 PASS.
  3. `shared/scripts/tools/tests/test_build_codex_plugin.py` (9 tests) +
     `test_build_codex_plugin_safety.py` (6 tests) + `test_codex_hook_merge.py`
     (6 tests) + `test_codex_hook_merge_ordering.py` (3 tests) — skill
     discovery, shared-tree bundling, per-origin script namespacing,
     byte-identical clean rebuild (AC4), output-path/marketplace safety
     guards including interrupted-build recovery, exact-duplicate dedup,
     genuine-collision refusal, matcher distinction, dispatcher-style
     trailing-argument union (order-preserving + a genuine order conflict),
     cross-plugin ordering of distinct hook entries within one bucket
     (doubt-review round 2), one plugin's own order preserved across two
     hooks.json group objects sharing one bucket (doubt-review round 3), and
     a passthrough-only bucket (e.g. `mcp_tool`) building without raising
     (doubt-review round 4, 2026-09-20). `codex_hook_merge.py` split into
     itself (rewrite/order-merge primitives) + `codex_hook_inventory.py`
     (dedup/ordering policy) to stay under the 300-LOC guideline. 24/24 PASS.
  4. `shared/scripts/tools/tests/test_verify_codex_plugin_bundle.py`
     (4 tests) — clean bundle passes; a source change without a rebuild is
     reported `stale`; a hand-inserted file is reported `undeclared`; a new
     source file without a rebuild is reported `missing` (AC5). 4/4 PASS.
  5. Real-tree build: `uv run build_codex_plugin.py --project-root . --out
     dist/codex-plugin` against the actual 14 plugins — 0 collisions after
     fixing 4 real merge bugs found only by running against real data: (i)
     early return in `_rewrite_command` masking own-plugin paths; (ii) dedup
     key ignoring `matcher`; (iii) no union for the legitimate
     `run_if_cache_ready.py` dispatcher case; (iv) the union appended
     newly-seen tokens to the tail instead of preserving each origin's own
     declared relative order — caught by code-review, since
     `run_if_cache_ready.py` runs its sub-scripts sequentially via
     `subprocess.run`, so order is observable behavior. Verified the merged
     `run_if_cache_ready.py` command (6 trailing sub-scripts, unioned across
     origins — 7 quoted script paths total once the invoked dispatcher itself
     is counted)
     is byte-identical to `shipwright-iterate`'s own full declared order —
     the superset among the 14 plugins — and `write-review-payload-on-stop.py`
     correctly keeps its 3 matcher-distinguished variants. PASS.
  6. Real-tree verify: `uv run verify_codex_plugin_bundle.py` against the
     freshly rebuilt real bundle — `OK: bundle matches a fresh rebuild from
     source.` PASS.
  7. AC6: `git status`/`git diff --stat` on `.claude-plugin/marketplace.json`
     + all 14 `plugins/*/.claude-plugin/plugin.json` — zero touched lines.
     PASS.
  8. AC3 exhaustive grep (`os.environ.get\(.*CLAUDE_PLUGIN_ROOT`) found 4 real
     call sites, not the interview-stage estimate of 6 — see AC3's own note.
     3 import the shared resolver (`capture_session_id.py`,
     `audit_phase_quality_on_stop.py`, `audit_compliance_on_stop.py`); the
     4th (`cleanup-review-scratch-on-code-reviewer-failure.py`) inlines the
     same precedence per ADR-044. Each site has its own regression tests plus
     a new Codex-native test. All green — see Test Completeness Ledger.
  9. **Not run (documented gap, not a failure):** live Codex hook execution
     (the trust-review question — see Out of Scope). What IS proven
     statically: the bundled hook commands' rewrite target is consistent
     with what Codex actually sets for a plugin-bundled hook (fixed under
     doubt-review — see item 10).
  10. **Doubt-review round (2026-09-20), 1 HIGH + 4 medium + 3 low, all
      addressed:**
      - HIGH: `_rewrite_command`'s target was `${SHIPWRIGHT_PLUGIN_ROOT}` —
        a name neither Claude nor Codex sets at shell-expansion time (only
        resolvable from inside already-running Python, a different
        mechanism) — so every bundled hook command would have expanded to a
        rootless path and failed outright, independent of the trust
        question. Fixed: retargeted to `${CLAUDE_PLUGIN_ROOT}`, which Codex
        does set for a plugin-bundled hook. Fixing this surfaced a second,
        self-inflicted bug (both rewrite targets now shared one variable
        name, so the second `.replace()` pass re-matched the first's own
        output) — fixed via a sentinel; both discovered by re-running the
        full test suite (2 failures), not by re-reasoning.
      - Medium: `PLUGIN_ROOT` outranked `CLAUDE_PLUGIN_ROOT`, a silent
        wrong-root hijack path under Claude (an unrelated ambient
        `PLUGIN_ROOT`) for zero Codex-side benefit. Fixed: reordered (AC2
        note, item 2).
      - Medium: unguarded `rmtree`/marketplace overwrite. Fixed:
        `UnsafeOutputPathError` guards (project-root/ancestor refusal,
        non-bundle-directory refusal, foreign-marketplace refusal) — 5 new
        tests in `test_build_codex_plugin_safety.py`.
      - Medium: AC2's fixture modeled a per-plugin cache shape the real
        Codex umbrella bundle never produces. Fixed: corrected to the
        live-confirmed shape; AC2/AC3 wording corrected to state phase
        recognition under the umbrella bundle is unsolved (Out of Scope).
      - Medium: docs asserted `SHIPWRIGHT_PLUGIN_ROOT` was already exported
        by the time the excluded 4th call site runs — false
        (`additionalContext` is not an OS export). Fixed: that site now
        inlines the same fallback precedence (item 8); the false claim
        removed from docs/hooks-and-pipeline.md and this spec.
      - Low (documented, not code-changed): `_merge_preserving_order`'s
        head-insertion policy can produce an order-dependent, spurious
        refusal for a not-yet-real 3+ origin shape (no silent wrong order —
        independently re-verified by the doubt-reviewer); the trailing-
        argument union is not restricted to path-like tokens; skill-name
        collision across plugins is unenforced. All three are pre-existing-
        shape gaps with no instance in the real 14-plugin tree today;
        deferred rather than fixed blind, to avoid the same "correctness
        code written by rote per a review comment" pattern the module's own
        docstring already warns against.
  11. **Doubt-review round 2 + code-review round (2026-09-20), verifying the
      round-1 fix set, found and fixed 2 more real defects:**
      - Medium (doubt-review round 2): `build_hook_inventory` order-preserved
        trailing arguments WITHIN one dispatcher entry (item 10's HIGH fix)
        but not the order of DISTINCT hook entries across plugins within one
        `(event, matcher)` bucket — those came out in "whichever
        alphabetically-first plugin declared this script" order. Real
        impact: `shipwright-adopt` (alphabetically first) registers only
        `audit_phase_quality_on_stop.py`/`audit_compliance_on_stop.py` on
        Stop; `shipwright-iterate` additionally requires
        `iterate_stop_finalize.py` before both and
        `aggregate_triage_on_stop.py` after — a real cross-plugin order
        requirement pinned by `shared/tests/test_audit_compliance_on_stop_wiring.py`.
        The merged bundle silently inverted it. Fixed by applying the SAME
        `_merge_preserving_order` algorithm to hook-entry order per bucket
        (`bucket_order`), not just trailing args within one entry — new test
        `test_hook_entries_preserve_a_fuller_origins_declared_order`
        reproduces the exact scenario; verified against the real rebuilt
        bundle that the Stop chain now matches: `iterate_stop_finalize.py`
        (0) < `audit_phase_quality_on_stop.py` (1) < `audit_compliance_on_stop.py`
        (2) < ... < `aggregate_triage_on_stop.py` (7).
      - Medium (code-review): the new output-path safety guard (item 10) had
        a self-inflicted false positive — `build_bundle` wrote the
        `.codex-plugin/plugin.json` marker LAST, after copying skills/origin/
        shared, so a build interrupted partway through left a non-empty,
        marker-less directory that the guard then refused to touch on retry
        ("did not create" — wrong on the facts). Fixed: the marker is now
        written FIRST, right after `out_dir.mkdir()` (both `version` and
        `hook_inventory` are already known by then) — new test
        `test_recovers_from_an_interrupted_build` pins it. The marketplace-
        ownership check was also tightened to verify the marker's `"name"`
        field, not just its presence (a foreign installed Codex plugin also
        has `.codex-plugin/plugin.json`). `main()` now also catches
        `UnsafeOutputPathError` (previously only `BundleCollisionError`, so
        this refusal surfaced as a raw traceback from the CLI).
      - Low: two stale precedence docstrings (`plugin_root.resolve_plugin_root()`,
        `capture_session_id.py`'s module docstring) still stated the OLD
        `SHIPWRIGHT > PLUGIN_ROOT > CLAUDE` order after item 10's reorder —
        both corrected. `build_codex_plugin.py` split into it and a new
        `codex_bundle_safety.py` (crossed the 300-line guideline). Stale
        diagnostic message and test counts in this spec also corrected.
- **Test Completeness Ledger:**

  | AC | Behavior | Test(s) | Type |
  |---|---|---|---|
  | AC1 | Skill discovery from one bundle | `test_skills_from_every_plugin_are_discoverable` + live probe against the real built bundle (`ac1-live-skill-discovery-probe.jsonl`) | unit + e2e (manual) |
  | AC2 | Resolver returns identical raw value under 3 real shapes (value-level only — not phase recognition, see AC2's own note) | `test_resolves_identically_under_claude_and_codex_cache_shapes` (×2 params, Codex param now the live-confirmed umbrella shape), `test_monorepo_working_tree_shape_via_shipwright_plugin_root` | unit |
  | AC3 | Every real call site resolves via the corrected precedence, regression-safe | `test_plugin_root.py` (10), `test_capture_session_id.py` (+1 new), `test_audit_phase_quality_stop_hook_direct.py` (+1 new), `test_audit_compliance_on_stop.py` (+1 new), `test_cleanup_review_scratch_on_code_reviewer_failure.py` (+1 new: CLAUDE_PLUGIN_ROOT fallback) | unit |
  | AC4 | Deterministic byte-identical rebuild; output-path safety | `test_clean_rebuild_is_byte_identical`, `test_pycache_is_excluded_from_every_copied_tree` (×3 params), real-tree rebuild (probe 5), `test_build_codex_plugin_safety.py` (6: project-root/ancestor/non-bundle/foreign-marketplace refusal, safe rebuild-in-place, interrupted-build recovery) | unit + integration |
  | AC5 | Drift/verifier: stale, missing, undeclared | `test_clean_bundle_passes`, `test_stale_bundle_source_changed_not_rebuilt_fails`, `test_undeclared_file_in_bundle_fails`, `test_missing_file_source_added_bundle_not_rebuilt_fails` | unit |
  | AC6 | Claude manifests byte-unchanged | `git diff --stat` (probe 7) | manual/CI-equivalent |
  | — | Hook-merge dedup/collision/matcher/trailing-union/order semantics | `test_identical_shared_referencing_hook_dedupes_across_plugins`, `test_conflicting_command_for_same_target_is_a_collision`, `test_matcher_distinguishes_same_script_different_flags`, `test_dispatcher_style_hook_unions_differing_trailing_shared_args`, `test_dispatcher_union_inserts_a_missing_middle_script_at_its_declared_position`, `test_dispatcher_union_conflicting_declared_order_is_a_collision`, `test_hook_entries_preserve_a_fuller_origins_declared_order` (cross-plugin entry ordering, doubt-review round 2) | unit |

  No gaps identified against AC1–AC6 within the (now corrected) scope each
  actually claims.
- **Confidence-pattern check:** no over-confidence pattern detected in the
  final state — every claim above is backed by a named test or a captured
  command's real output, not by "should work" reasoning. Two claims WERE
  over-confident in an earlier draft and were caught by doubt-review rather
  than self-caught: AC1's hook-execution gap was framed as "merely
  unobserved" when the emitted commands were in fact statically broken, and
  AC2 implied phase-recognition coverage it does not have. Both are now
  stated accurately rather than quietly dropped. The one deliberately
  unverified surface (live hook execution, now on a corrected rewrite
  target) remains documented as a gap, not asserted.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run shared/scripts/tools/build_codex_plugin.py --project-root . --out dist/codex-plugin` followed by the pytest suites for the new builder/resolver/drift-check modules, plus (where the operator has Codex CLI available, as this environment does) a scripted `codex plugin marketplace add`/`codex plugin add`/skill-list probe against the freshly built bundle, mirroring the Repo Scout probe above.
- **Evidence path:** `.shipwright/agent_docs/iterates/iterate-2026-09-20-codex-plugin-bundle-root-contract.test-results.json` (F5c) plus a captured transcript of the live Codex probe under `.shipwright/planning/iterate/iterate-2026-09-20-codex-plugin-bundle-root-contract/`.
