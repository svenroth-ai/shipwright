# Iterate Spec: claude-md-invariant-index

- **Run ID:** iterate-2026-07-10-claude-md-invariant-index
- **Type:** change
- **Complexity:** medium
- **Status:** implemented

## Goal
Stop adopted/generated repos from accreting bloated CLAUDE.md files (webui's is
~2.4x the monorepo's; its DO-NOT block alone is ~46% of the file): both CLAUDE.md
producers gain an explicit writing rule — CLAUDE.md is orientation plus a terse
invariant index (one line + ADR pointer; rationale lives in the ADR) — and the
repo-agnostic budget gate gains a forward-only net-growth check on CLAUDE.md so
the rule is enforced, not just stated.

## Acceptance Criteria
- [x] AC1: `shared/templates/claude-md-template.md` (greenfield producer) carries
      a "keep it lean" writing-rule section: one line per invariant + ADR pointer,
      rationale in the ADR/conventions entry, prefer editing an existing line over
      adding a new one.
- [x] AC2: `plugins/shipwright-adopt/scripts/lib/claude_md_renderer.py`
      (brownfield producer) renders the same writing-rule section, and
      `shared/tests/test_claude_md_template.py` pins new markers in BOTH producers
      (mirror-test extended).
- [x] AC3: `shared/scripts/lib/agent_doc_budget.py` gains a pure, repo-agnostic
      CLAUDE.md net-growth rule (`CLAUDE_MD_MAX_NEW_LINES = 30`; forward-only:
      net `splitlines()` growth vs the git base above the cap is a violation;
      shrink or equal never flags; CRLF/trailing-newline differences don't
      change the count). The helper stays pure — git resolution, env override,
      and mode selection live in the CLI/verifier layer.
- [x] AC4: `shared/scripts/tools/check_agent_doc_budget.py` (CLI) and the F11
      verifier `check_agent_doc_budget` report CLAUDE.md growth violations through
      the existing `(filename, header, message)` channel — forward-only mode only,
      and only when CLAUDE.md exists BOTH at the git base and in the worktree
      (creation/deletion is not accretion; `git show` failure ⇒ skip). Fail-soft
      SKIP stays when no git base resolves; `--all` prints an explicit note that
      the growth check only runs forward-only.
- [x] AC5: Deliberate large additions have a visible escape hatch:
      `SHIPWRIGHT_CLAUDE_MD_GROWTH_OK=1` skips ONLY the growth rule (entry-budget
      checks unaffected). The skip is surfaced as an informational note — CLI
      info line + appended to the verifier's SUCCESS message — never through the
      violations channel (a skip must not fail the gate).
- [x] AC6: Docs updated: `docs/hooks-and-pipeline.md` (F11 verifier behavior
      change) and `docs/guide.md` Chapter 8 (quality gates) mention the CLAUDE.md
      growth gate + escape hatch.

## Spec Impact
- **Classification:** none
- **ADD**: none
- **MODIFY**: none
- **REMOVE**: none
- **NONE justification:** Framework-internal quality-gate + template change; the
  monorepo's FR specs describe pipeline features for target projects, and no
  FR covers agent-doc budget internals (the existing 600-char entry gate has no
  FR either — same class of change).

## Out of Scope
- Slimming webui's existing CLAUDE.md (paired item, Session
  f9afc62b-98e5-49f1-82e9-2b2ba5e16564 — the gate here protects that cleanup
  from regressing).
- Retrofitting existing repos' CLAUDE.md content (the gate is forward-only by
  design; legacy bloat never blocks an untouched iterate).
- A per-SECTION char budget inside CLAUDE.md (CLAUDE.md has no stable entry
  grammar to parse; net-file growth is the enforceable proxy — revisit only if
  the growth gate proves too coarse).

## Design Notes
n/a — no UI surface (markdown templates + Python lib/CLI/verifier + tests).

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `claude_md_renderer.py:_render_claude_md` | Claude Code session (target repo CLAUDE.md) | Markdown |
| `check_agent_doc_budget.py:find_violations` | `verifiers/agent_doc_budget_check.py:check_agent_doc_budget` | tuple list (filename, header, message) |

No serialized config/JSON format changes → no `touches_io_boundary` flag; the
tuple channel is exercised end-to-end by the wiring tests.

## Confidence Calibration
- **Boundaries touched:** template↔renderer mirror (pinned by
  test_claude_md_template.py); find_violations→verifier tuple channel.
- **Empirical probes run:**
  - Live CLI + verifier against THIS worktree (real repo, real origin/main
    base): both green — `agent-doc entry budget: OK` / `True | all new
    entries <= 600 chars; CLAUDE.md growth ok` (proves no self-block at F11).
  - Live negative probe: appended 35 lines to the real CLAUDE.md → CLI exit 1
    with `CLAUDE.md '(net growth)': +35 lines net growth (> 30)`; with
    `SHIPWRIGHT_CLAUDE_MD_GROWTH_OK=1` → exit 0 + visible skip note; file
    restored (git status clean).
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Lib: growth over cap flags (+N in message) | tested | test_claude_md_growth_over_cap_flags PASSED |
  | 2 | Lib: at-cap / under / shrink / equal clean | tested | test_claude_md_growth_exactly_at_cap_clean, test_claude_md_growth_shrink_and_equal_clean PASSED |
  | 3 | Lib: CRLF + trailing-newline parity (no phantom growth) | tested | test_claude_md_growth_crlf_parity, test_claude_md_growth_trailing_newline_only_clean PASSED |
  | 4 | Lib: custom cap respected | tested | test_claude_md_growth_custom_cap PASSED |
  | 5 | CLI: forward-only over-cap growth → ("CLAUDE.md", "(net growth)", …) violation | tested | test_claude_md_growth_over_cap_flagged PASSED |
  | 6 | CLI: within-cap growth clean | tested | test_claude_md_growth_within_cap_clean PASSED |
  | 7 | CLI: CLAUDE.md absent at base (creation) → skip | tested | test_claude_md_new_file_at_worktree_skipped PASSED |
  | 8 | CLI: CLAUDE.md deleted / replaced-by-directory in worktree → skip, never crash | tested | test_claude_md_deleted_in_worktree_skipped, test_claude_md_replaced_by_directory_skipped PASSED |
  | 9 | CLI: check_claude_md=False skips ONLY growth (entry budget still enforced) | tested | test_claude_md_growth_opt_out_param PASSED |
  | 10 | CLI: full-corpus --all never evaluates growth | tested | test_full_corpus_mode_never_checks_claude_md_growth PASSED |
  | 11 | CLI stdout: --all prints "not evaluated" note | tested | test_cli_all_mode_prints_growth_not_evaluated_note PASSED |
  | 12 | CLI stdout: env override prints skip note | tested | test_cli_env_override_prints_skip_note PASSED |
  | 13 | Verifier: blocks over-growth end-to-end (ok=False, CLAUDE.md in detail) | tested | test_verifier_blocks_claude_md_over_growth PASSED |
  | 14 | Verifier: env override stays green + note in SUCCESS detail | tested | test_verifier_env_override_skips_growth_but_stays_green PASSED |
  | 15 | Verifier: fail-soft SKIP without git base | untestable | covered-by-existing-test (test_check_fail_soft_skips_without_git_base) |
  | 16 | Greenfield template carries keep-it-lean markers (incl. "Growth is gated", env var) | tested | test_template_carries_keep_it_lean_rule PASSED |
  | 17 | Brownfield renderer mirrors the same markers | tested | test_adopt_rendered_claude_md_mirrors_template_iterate_bullets PASSED |
  | 18 | Docs prose accuracy (guide.md §CLAUDE.md, hooks-and-pipeline.md §agent-docs) | untestable | requires-manual-visual-judgment |

- **Confidence-pattern check:** asymptote (depth): both review passes produced
  findings that were fixed (mirror-marker strength, CLI stdout coverage,
  non-regular-file guard) and the follow-up probe after each fix ran green —
  no "confident-yes followed by a finding" left unprobed. Coverage (breadth):
  18 ledger rows ≥ 6 ACs, every row tested or closed-vocab untestable,
  0 untested-testable.
