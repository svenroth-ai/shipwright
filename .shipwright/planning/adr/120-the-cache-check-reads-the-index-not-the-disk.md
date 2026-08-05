# ADR-120 — The plugin-cache check reads the index, not the disk

**Run:** `iterate-2026-08-01-cache-sync-shared-tree`

## Context

`scripts/check_plugin_cache_sync.py` is the monorepo's detective gate for
"did my plugin-side edit reach the Claude Code runtime cache". Its docstring
claimed it covered `plugins/*` **and** `shared/scripts/`, but the comparison
loop walked only `plugins/shipwright-*`. The cache's `shared/` tree — 1005
files, including the 55 modules under `shared/scripts/tools/verifiers/` that
the F11 finalization verifier imports, and which every parallel iterate runs
from — was never compared. `--strict` printed *"all 14 plugin(s) in sync"*
while saying nothing about it.

Measured on the live cache, 2026-08-01:

| cache state | F11 verifier | SessionStart self-heal | old `--strict` |
|---|---|---|---|
| intact | runs | — | `0` "all 14 plugin(s) in sync" |
| partial reap of the 55 verifier modules | `ModuleNotFoundError: No module named 'tools.verifiers'` | **does not fire** | `0` "all 14 plugin(s) in sync" |
| full reap of `shared/scripts/` | entrypoint gone | fires next SessionStart | `0` "all 14 plugin(s) in sync" |

The partial reap is the unrecovered case: `ensure_shared_cache._shared_healthy`
judges the whole tree from one sentinel (`shared/scripts/lib/project_root.py`)
which a partial reap leaves standing, so nothing repairs it.

`.orphaned_at` markers turned out **not** to be a reap prediction. All 8
top-level `shared/` subdirs carry one on a fully intact cache, re-written by a
recurring sweep, because the marker means "not recognised as an installed
plugin" — permanently true of `shared/` by construction.

## Decision

Compare the cached `shared/` tree, and define "the tree" from the index rather
than from a heuristic:

- **repo side — `git ls-files`.** The cache is copied from
  `~/.claude/plugins/marketplaces/shipwright`, a `git reset --hard origin/main`
  clone holding exactly the tracked files. "What git tracks" is therefore
  precisely "what can ever reach the cache".
- **cache side — a filesystem walk** minus `__pycache__` / `.git` / `.venv` /
  `.pytest_cache` / `node_modules` / `.in_use` and `*.pyc`, because the cache
  is not a git tree and has no index to ask.

Primitives live in `scripts/cache_tree_compare.py`, rendering in
`scripts/cache_sync_report.py`. The verdict reports `verified` (trees this
result covers), `ungated` (trees it knowingly does not), and per record a
`basis` of `git` or `walk (<why not git>)`.

**A zero is never read as agreement**, at either entrance: an empty
`ls-files` listing over a non-empty directory, and a listing none of whose
files can be read, are both refusals to establish a basis.

## Consequences

- A reap, a stale `shared/` file and a `skills/build/` edit all exit 1 where
  they previously exited 0.
- Coverage rose by 110 files (plugin trees 1060 → 1125, shared 961 → 1005)
  with **no verdict change** on the live cache.
- The `.orphaned_at` advisory prints only alongside drift, because on a healthy
  machine it is permanently on and a warning at 100% duty cycle is
  indistinguishable from an incident. `orphan_markers` stays in `--json`.
- `cache_only_count` and `unhashable_count` are reported without failing the
  gate — an unpropagated deletion stays importable at runtime, and a tracked
  file that cannot be read must not shrink `tracked_count` to fit.
- The cross-plugin mirror `cache/plugins/<name>/` stays **ungated by
  decision** (`trg-7d1d8437`). **Update (2026-08-05, iterate-2026-08-05-mirror-tree-drift-basis,
  P2.29):** the blocker below is resolved (the healer now compares each
  mirror's file set against its repair source) and the mirror is gated —
  see `scripts/cache_mirror_compare.py`, which gives it its own basis
  (`"cache"`, never `git`/`walk`) rather than reusing `compare_tree`'s.
- Because the two sides now apply different rules, a meta-test
  (`test_skip_dirs_hide_nothing_git_tracks`) asserts nothing git tracks lives
  under a skipped component.

## Rationale

Across five adversarial review rounds every defect had one of two shapes.

**A blanket rule standing between the gate and the tree:**

- a seven-suffix allowlist that hid 44 of 1005 cached `shared/` files —
  `shared/templates/` 3/37 verified, `shared/prompts/` 3/9 — both read from
  the cache at runtime, both able to vanish entirely under a green;
- a bare `build` component in the skip set that hid all 29 tracked files of
  `plugins/shipwright-build/skills/build/`, `SKILL.md` included, from **both**
  sides, so the most-edited plugin-side file could never drift;
- a filesystem walk over a worked-in checkout, which made six gitignored
  generated files permanent phantom "missing from cache" and would have turned
  the mandatory `--strict` run permanently red.

**A zero standing in for agreement:** at the listing step, at the hashing step,
and in the key that reports what a verdict covers.

Deriving the tree from what is actually copied removes the first class
structurally; guarding both zero-entrances removes the second.

## Rejected

- **Reword the success line, keep the allowlist.** Cheapest, and it removes the
  overclaim — but `shared/prompts/code_reviewer/` could still vanish entirely
  under a green, and `external_review_prompts._load` degrades to `("", "")`
  silently.
- **Gate the cross-plugin mirror too.** Its repair is gated behind
  `_plugins_healthy`, a single sentinel file (shipwright-run's), so a mirror
  missing while that file survives is never healed. A gate built on top would
  restate this bug one tree over. Sequenced behind `trg-7d1d8437` instead.
  **Done as of P2.29** once that sequencing blocker cleared (see the
  Consequences update above).
- **Walk the filesystem on both sides.** Symmetric and simple, but it is what
  made the six gitignored files phantom drift, and no exclusion list stays
  correct as directories are added.
- **Fail on `cache_only` / `.orphaned_at`.** Both are legitimately non-empty on
  a healthy machine; failing on them trains the operator to ignore the gate.
