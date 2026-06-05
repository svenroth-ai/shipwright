# Sub-iterate C1 — make `triage.jsonl` trackable (gitignore + scaffolder self-heal)

- **Campaign:** 2026-06-05-track-triage-jsonl (sub-iterate C1 of A→E; C split into C1+C2)
- **run_id:** `iterate-2026-06-05-triage-track-c1-gitignore`
- **Type:** change (framework infra) · **Complexity:** small ·
  **Branch:** `iterate/triage-track-c1` · **Anchor:** `expands_triage: trg-2fb7d3bc`

## Scope decision (post Codex review — see campaign notes)

C was de-scoped: the systemic per-tree producer reroute (old "C3") was **over-engineering**.
`events.jsonl` itself doesn't reroute background writers — the leak-guard simply **exempts**
it (`_MAIN_TREE_WRITE_EXEMPT`). So "mirror events" = track + churn-resolver + the same
leak-guard exemption (C2), **not** a systemic resolver. C1 is just the gitignore enablement.

## Changes

1. **SSoT template** `shared/templates/shipwright-gitignore.template` — add
   `!/.shipwright/triage.jsonl` after the doc-home re-includes (managed block).
2. **Monorepo `.gitignore`** — identical line at the identical rule-position
   (the congruence test compares the two managed blocks as an **ordered list**).
3. **`scaffold_triage_inbox.py`** — `GITIGNORE_LINES` drops the bare
   `.shipwright/triage.jsonl` (keeps `.lock` **and the GC `.bak`** — Codex LOW:
   belt-and-braces for repos lacking the canonical block); `_scaffold_gitignore`
   gains a **self-heal** that strips any stale bare/`/`-prefixed
   `.shipwright/triage.jsonl` ignore line (a pre-tracking adopter appended it
   AFTER the managed block, where gitignore last-match-wins would override the
   negation). The `!` negation is never stripped, and the heal **preserves the
   file's existing content + line endings** (external-review GPT-5.4 HIGH —
   `keepends=True`, append-only path leaves bytes verbatim).

`.lock` + the GC's `.bak` stay ignored by the `/.shipwright/*` wildcard (the
negation matches only the exact `.jsonl`); the scaffolder also lists them as a
fallback for non-canonical `.gitignore` files.

## Acceptance criteria

- [x] **C1-AC1.** Canonical managed block TRACKS `triage.jsonl`; `.lock` + `.bak` stay ignored
      (end-to-end `git check-ignore` on the real SSoT template via `gitignore_canon`).
- [x] **C1-AC2.** Template ↔ monorepo `.gitignore` managed blocks remain ordered-list congruent.
- [x] **C1-AC3.** Scaffolder no longer manages the bare `.jsonl` line; self-heal strips a stale
      bare/`/`-variant line; the `!` negation is never stripped; idempotent.

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| template + scaffolder write the managed `.gitignore` block | git (tracking decision) + adopt/project (`gitignore_canon` merge) | `.gitignore` lines |

## Confidence Calibration

- **Boundaries touched:** the `.gitignore` tracking decision for `.shipwright/triage.jsonl`
  (template SSoT + monorepo block + the adopt-time scaffolder). No runtime data path.
- **Empirical probes run:**
  1. *Negation probe* — `git check-ignore` on the real template block: `triage.jsonl`
     TRACKED, `.lock` + `.bak` IGNORED (now a pinned regression test).
  2. *Congruence probe* — ordered-list equality template ↔ monorepo block (4 tests green).
  3. *Self-heal probe* — stale bare line + `/`-variant stripped; negation preserved; idempotent.
- **Test Completeness Ledger:**

  | Behavior | Disposition | Evidence |
  |---|---|---|
  | canonical negation tracks jsonl, ignores lock+bak | `tested` | `test_canonical_negation_tracks_jsonl_but_ignores_lock_and_bak` |
  | template ↔ monorepo ordered-list congruent | `tested` | `test_gitignore_template_congruent.py` (4) |
  | bare jsonl no longer a managed ignore line | `tested` | `test_jsonl_is_no_longer_a_managed_ignore_line` |
  | self-heal strips stale bare line | `tested` | `test_self_heals_stale_bare_jsonl_ignore` |
  | self-heal strips `/`-prefixed variant | `tested` | `test_self_heal_strips_slash_prefixed_variant` |
  | self-heal never strips the `!` negation | `tested` | `test_self_heal_never_strips_the_negation` |
  | `.lock` still ignored/appended; idempotent | `tested` | `test_creates_gitignore_when_absent`, `test_appends_to_existing_gitignore`, `test_full_idempotency` |

  0 testable-but-untested. Committing the actual monorepo backlog jsonl = sub-iterate E (one-time migration).
- **Confidence-pattern check:** *depth* — the load-bearing gitignore behavior is pinned
  end-to-end on the real SSoT, not just reasoned; *breadth* — track/ignore/congruence/
  self-heal(both variants)/negation-preservation/idempotency all covered.
