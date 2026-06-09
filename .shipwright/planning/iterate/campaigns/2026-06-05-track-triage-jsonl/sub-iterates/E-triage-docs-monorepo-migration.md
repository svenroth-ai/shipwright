# Sub-iterate E — docs + monorepo migration (FINAL; ready to start in a fresh session)

- **Campaign:** 2026-06-05-track-triage-jsonl (sub-iterate E of A→E — the LAST one)
- **Suggested run_id:** `iterate-2026-06-06-triage-docs-monorepo-migration`
- **Type:** change · **Complexity:** small (docs) + a one-time DESTRUCTIVE data step
- **Anchor:** `expands_triage: trg-2fb7d3bc` (campaign) — closing this completes the campaign
- **Prereqs:** A/B/C1/C2/D ALL MERGED to main (PRs #153/#154/#155/#156/#158). ✅ Done.

> **START HERE (fresh session):** read memory `project_track_triage_jsonl` (full
> review trail + scope), `proposed-track-triage-jsonl.md` (§ E), and this file.
> Then `/shipwright-iterate` for E. The campaign is `active`; E is the only
> remaining sub-iterate (see `status.json`).

## What E does

### Part 1 — Docs (safe, the bulk of E)
1. `docs/guide.md` — document that `.shipwright/triage.jsonl` is the **tracked**
   SSoT triage backlog (committed, per-tree like `events.jsonl`); the `.md` is a
   derived view. Check the triage/compliance chapters + Appendix.
2. `shared/glossary.md` — add/refine the triage-tracking terminology (tracked SSoT
   backlog; the derived `triage_inbox.md` view).
3. `docs/hooks-and-pipeline.md` — **artifact-write matrix**: `triage.jsonl` is now
   tracked + who writes it (producers per-tree; F6 stages it); **context-loading
   matrix** if relevant. (The churn-reconciliation table row already landed in C2.)
4. **Stale-doc cleanup (Codex R1 finding):** `shared/scripts/hooks/plugin_sync_reminder_on_stop.py`
   `_emit_triage` docstring still says *"the worktree's triage.jsonl is gitignored +
   discarded on cleanup"* — now FALSE. Update it to: the redirect-to-main is
   intentional (durable main backlog, **leak-guard-exempt** since C2's
   `_MAIN_TREE_WRITE_EXEMPT`), NOT because it's gitignored. Update its test docstring
   (`shared/tests/test_plugin_sync_reminder_on_stop.py:7`). Grep for other
   "triage.jsonl is gitignored" stale references and fix.

### Part 1b — Tidy the campaign record (cosmetic, found 2026-06-06)
The tracked `campaign.md` is stale/malformed for the WebUI table parser: header is
`## Sub-iterates (A → E)` (parser wants exactly `## Sub-Iterates`), **no Slug
column**, rows say A=in_review / a single `C` row / all-pending. The WebUI works
**only** via its `status.json` fallback. Fix `campaign.md`: `## Sub-Iterates` header,
add a `Slug` column with the REAL slugs, split C→C1/C2, A–D=complete (+PRs),
E=pending. **Coupling gotcha (this bit us):** the WebUI derives each step's spec
filename as `sub-iterates/<id>-<slug>.md` and `existsSync`-checks it; a slug that
doesn't match the on-disk filename → `specPath=null` → dead Launch button. So slug
in status.json/campaign.md MUST equal the `<id>-<slug>.md` filename.

### Part 2 — The DESTRUCTIVE monorepo migration (GATED — show the user first)
The live `.shipwright/triage.jsonl` in the **main tree** (~175 items, machine-local,
uncommitted) is the real curated backlog. C1 made it trackable; E commits the
canonical (GC'd) pile so the committed snapshot finally matches the WebUI.

**Procedure (do NOT skip the gate):**
1. Settle A's one-time SBOM-key migration: run `update_compliance.py --phase iterate`
   once so A's signature-only cluster keys re-emit (old membership-keys auto-dismiss).
   These dismissals are machine-churn and will be GC'd in the next step.
2. **Dry-run** `uv run shared/scripts/tools/triage_gc.py --project-root .` → shows
   droppable (machine-churn) vs kept (human-curated). Was 53 droppable / 122 kept;
   re-check after step 1.
3. **SHOW THE USER:** the dry-run output + confirm. Then `--apply` (writes
   `.shipwright/triage.jsonl.bak` first, atomic rewrite, re-validates). Show the
   user the `.bak` + the resulting diff. **Commit only after the user's go-ahead.**
4. Commit the canonical `triage.jsonl` to main + regenerate `triage_inbox.md` from it
   (now matches the WebUI). This is the FIRST commit of the tracked jsonl — it
   establishes the canonical pile.

**HOW to commit it (gotcha — it's a MAIN-tree pile, not a worktree pile):**
An iterate worktree (off origin/main) does NOT contain main's working-tree pile
(main has no committed jsonl yet). So either: (a) do the GC + commit of the
canonical pile **directly on main** as a deliberate one-time migration commit (the
data lives in main's working tree), branch-first per the constitution; OR (b) in
E's iterate worktree, COPY main's GC'd `triage.jsonl` into the worktree, then F6
`git add .shipwright/triage.jsonl` (the F6.md rule C2 added) so it ships in E's PR
and merges to main. Option (b) keeps it in the normal PR flow; pick it unless there's
a reason not to. The leak-guard is **exempt** for `triage.jsonl` (C2), so GC-ing
main's pile during E's iterate does NOT trip f0/f11.

## After E lands
- Committed `triage.jsonl` (canonical ~122) + `triage_inbox.md` match the WebUI →
  the original divergence is CLOSED. Dismiss the campaign anchor `trg-2fb7d3bc`
  (campaign complete). Steady state: future iterates inherit the committed jsonl,
  producers append per-tree, F6 commits, the churn resolver (`_reconcile_triage`)
  unions concurrent appends.
- Follow-up still open: `trg-9403a648` (triage-store `amend` primitive — faithful
  SBOM cluster body re-render; separate from this campaign).

## Acceptance criteria
- [ ] **E-AC1.** guide.md + glossary.md + hooks-and-pipeline matrices document tracked triage.jsonl.
- [ ] **E-AC2.** plugin_sync_reminder docstring (+ test) + any "triage gitignored" stale refs corrected.
- [ ] **E-AC3.** Dry-run shown + user go-ahead; `--apply` run (backup + validate); canonical `triage.jsonl` committed + `triage_inbox.md` matches the WebUI.
- [ ] **E-AC4.** Campaign anchor `trg-2fb7d3bc` dismissed (campaign complete); `/shipwright-changelog` release prompt if pending drops.
