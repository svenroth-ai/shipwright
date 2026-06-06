# Sub-iterate D — adopt/project wiring for the now-tracked triage.jsonl

- **Campaign:** 2026-06-05-track-triage-jsonl (sub-iterate D of A→E)
- **run_id:** `iterate-2026-06-06-triage-adopt-project-wiring`
- **Type:** change (docs) · **Complexity:** trivial · **change_type:** docs
- **Branch:** `iterate/triage-adopt-wiring` · **Anchor:** `expands_triage: trg-2fb7d3bc`

## Scope (mostly already covered by C1)

The scaffolder **code** was fixed in C1 (`scaffold_triage_inbox.py` stops ignoring
`triage.jsonl`, self-heals, keeps `.lock`+`.bak`). The canonical gitignore negation
(merged C1) is propagated to adopted/created repos by `gitignore_canon.merge_canonical_block`
— which **adopt** already runs (Step E.6) and **project** already runs
(`write-project-config.py` on `--status complete`). So both adopt and project
already make `triage.jsonl` trackable; adopt's `git add`-everything Step H commit
auto-includes it. D is therefore the **doc cleanup**: the adopt skill text still
claimed the scaffolder "updates `.gitignore` to cover `.shipwright/triage.jsonl`",
which is now wrong (it's tracked, not ignored).

## Changes (docs-only)

1. `plugins/shipwright-adopt/skills/adopt/references/step-e16-triage-inbox.md` —
   step 3 now says the scaffolder ignores the `.lock` + GC `.bak` only and
   self-heals a stale bare `triage.jsonl` line; `triage.jsonl` is the **tracked**
   SSoT (re-included by the canonical negation) and ships in the Step H commit;
   added the `healed` action value + the `healed` result list.
2. `plugins/shipwright-adopt/skills/adopt/SKILL.md` (Step E.16 summary) — same
   correction.

## Deliberately NOT changed

- **project**: no scaffold call added (YAGNI). project already merges the canonical
  block (negation) + producers lazily bootstrap the header + F6 stages it. The
  optional header-seed in step-7 is symmetry-only and not required.
- **`plugin_sync_reminder_on_stop.py`** docstring ("triage.jsonl is gitignored +
  discarded") is stale but its redirect-to-main is now *intentional* (durable
  main backlog, leak-guard-exempt per C2). That shared-hook doc cleanup belongs to
  **E** ("update stale docs"), not adopt/project wiring.

## Acceptance criteria

- [x] **D-AC1.** Adopt skill no longer claims the scaffolder gitignores `triage.jsonl`;
      documents it as tracked + committed in Step H, `.lock`/`.bak` ignored, self-heal noted.
- [x] **D-AC2.** No test regression (link/reference tests + scaffolder tests green); no
      behavior change (code was C1).

## Test Completeness Ledger

`n/a` — docs-only change (adopt SKILL.md + reference prose). No new/changed runtime
behavior to test; the scaffolder code + its tests landed in C1 and remain green
(`test_triage_scaffold.py` 17 passed, `test_skill_references_link.py` 7 passed).
