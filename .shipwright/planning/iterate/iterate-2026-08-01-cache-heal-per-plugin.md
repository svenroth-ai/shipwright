# iterate-2026-08-01-cache-heal-per-plugin

**Type:** CHANGE · **Complexity:** medium (safety floor: `cross_component`)
**Risk flags:** `cross_component`
**Spec Impact:** NONE — no FR covers the runtime plugin cache; this is a
soundness fix to a framework-internal self-heal hook.
**Supersedes:** trg-7d1d8437 (same content, placed in the phase scheme).
**Origin:** fallout from P1.02 (`iterate-2026-08-01-cache-sync-shared-tree`,
ADR-120, #518), found by the Stage-1 spec-reviewer.

## Problem

`ensure_shared_cache.py` is the SessionStart safety net that repairs the runtime
plugin cache. It judges each of the two trees it repairs from **one sentinel
file**, so a *partial* reap — the failure it exists to catch — reads as healthy
and is never repaired.

### The plugins half (the card's headline)

```python
_PLUGINS_SENTINEL = ("shipwright-run", "scripts", "lib", "phase_task_lifecycle.py")

if _shared_healthy(shared_target) and _plugins_healthy(plugins_target):
    return 0                                                    # line 113
...
if not _plugins_healthy(plugins_target) and _heal_plugins(...):  # line 124
```

One file out of **14 mirrors** gates the whole repair. If any other plugin's
mirror is missing or partial while `shipwright-run`'s sentinel survives, the
repair is unreachable by **two** independent routes:

1. line 113 returns `0` before `_heal_plugins` is ever called; and
2. even if `shared/` is unhealthy so line 113 falls through, line 124
   short-circuits on `not _plugins_healthy(...)` being `False`.

So the per-plugin `if dst.exists(): continue` loop never runs. Runtime effect:
`{plugin_root}/../../plugins/shipwright-X` 404s for that plugin, with nothing
repairing it.

There is a **third** defect one level down: even when `_heal_plugins` *is*
reached, `if dst.exists(): continue` skips any plugin whose directory exists at
all. A partially-reaped mirror has a directory, so it is skipped. Fixing only
the gate would leave this live.

### The shared half (same defect, and the measured trigger)

`_shared_healthy` judges 1013 files from `shared/scripts/lib/project_root.py`.
This is not a symmetry argument — it is the case that was actually **measured**,
and ADR-120 (merged yesterday as #518) already records it:

> The partial reap is the unrecovered case: `ensure_shared_cache._shared_healthy`
> judges the whole tree from one sentinel (`shared/scripts/lib/project_root.py`)
> which a partial reap leaves standing, so nothing repairs it.

ADR-120 measured a partial reap of the 55 `shared/scripts/tools/verifiers/`
modules that every iterate's F11 imports: `ModuleNotFoundError`, self-heal
**does not fire**. The card's own P1 justification rests on this event.

**Scope note (widened beyond the card's literal headline, deliberately).** The
card names `_plugins_healthy`. Its stated reason for P1 priority is the
shared/scripts reap. These are one defect with two heads, in one function pair,
in one file, repaired by one mechanism. Fixing only the head the card names
would leave the failure that motivated it unrepaired. Both are in scope; the
extra cost is ~10 lines reusing the same helper.

## Root cause

A **sentinel is a liveness check being used as a completeness check.** One file
can only answer "was this tree ever created?", never "is this tree whole?". The
reap that motivates the hook removes files from an existing tree, so it is
invisible to every sentinel that survives it.

## Fix

Replace both sentinels with a **delivered-file-set comparison**: a tree is
healthy iff every file a `copytree(src, dst, ignore=_IGNORE)` would deliver is
present in `dst`.

The load-bearing invariant: **the health check must ignore exactly what the copy
ignores.** If the walk counts a file the copy never writes, that file is a
permanent gap and the hook re-copies on every session start forever. This is
guaranteed structurally by driving both from the *same* `_IGNORE` callable,
queried per-directory the way `shutil.copytree` itself queries it.

### Empirically-derived ignore set

A naive path-set check was probed against the live cache **before** writing any
code. It reported a false gap on **all 14 plugins**: `.in_use/<pid>`, the Claude
Code cache manager's volatile per-PID refcount, present in the source plugin
dirs. Three distinct PIDs (`8408`, `20592`, `2544`) were live during the probe.
Left unignored, this fix would have converted a no-op into a full 1464-file
re-copy every single session, and would have written stale PID locks into the
mirror.

`.orphaned_at` (cache-manager reap marker) appears in `dst` only, so it is
harmless in the src→dst direction, but is ignored for symmetry with the copy.

This independently rediscovered the set ADR-120 already established in
`scripts/cache_tree_compare.py::SKIP_DIRS`. Because the hook is **stdlib-only
and cannot import from `shared/`** (it exists to repair a missing `shared/`),
the set must be duplicated in the hook — so drift tests pin it (Registry-driven
SSoT rule).

**Pin the PRODUCER, not just the checker.** The first version pinned only
against `SKIP_DIRS`, which belongs to the tool that *compares* these trees. The
tool that *writes* them is `scripts/update-marketplace.sh`, and its exclusions
are strictly larger — notably `.python-version`, which all 14 plugins gained the
same day (iterate-2026-08-01-pin-python-311). A name the writer withholds can
never reach the destination, so counting it is a permanent gap. The pin now
parses the script's own `-not -name` tokens, so the hook is held to the writer.
Found by the review cascade; it was invisible to the live-cache probe because no
install had delivered a `.python-version` yet.

### Presence, not content — and why that is the *correct* scope

The check compares **which files exist**, never their bytes. This is a measured
decision, not an omission.

Probed on the live cache: comparing sizes between the marketplace clone and the
cached `shared/` reports **24 of 1015 files as differing** — e.g.
`scripts/lib/__init__.py` clone=29 / cache=28, a single CRLF-vs-LF byte. This is
exactly the line-ending hazard `cache_tree_compare.file_hash` documents ("a
Windows checkout (CRLF) compared against a Linux-synced cache (LF) would produce
false drift on every text file"). The plugins mirror, being a plain byte copy,
showed **0** size mismatches — so the hazard is real for one tree and absent
from the other, and a single content rule cannot serve both.

A content-aware check in this hook would therefore re-copy 24 shared files on
every session forever. Content equality is the **drift gate's** job
(`check_plugin_cache_sync.py`), which already CRLF-normalizes before hashing.
The healer answers "is anything *gone*?"; the gate answers "is anything *stale*?"

**Consequence, stated honestly:** a file that is present but truncated is NOT
detected. It is repaired only incidentally, when some adjacent file is also
missing and the overlay copy fires.

### Repair

Per tree with gaps: `copytree(src, dst, ignore=_IGNORE, dirs_exist_ok=True)`.
Overlay, not delete-and-recreate — it matches what the `shared/` half already
did and never destroys a file the source no longer has. Each mirror copies
inside its own `try`, so one unwritable plugin cannot block the other 13.

### Scanning is tri-state

A walk that swallows `OSError` and returns a *partial* set would under-count the
**source** and so manufacture a false "complete" verdict — the very bug being
fixed, reintroduced through the error path. `_delivered()` therefore returns
`None` (not a short set) on any enumeration failure, and an unknown verdict
means **neither** claim health **nor** copy: stay silent, exit 0.

## External plan review — findings and resolutions

Run `--mode iterate` (openrouter; gemini truncated, openai `revise`). Both
reviewers independently flagged the same high-severity control-flow gap.

| # | Sev | Finding | Resolution |
|---|---|---|---|
| GPT-1 | high | `delivered(src) - delivered(dst)` cannot detect a **truncated** file, yet the plan claimed truncation repair | **Accepted, scoped out with evidence.** Probed: content comparison is provably wrong here (24 CRLF false gaps). Claim removed; the limitation is now stated explicitly above and carried into the ledger as a `covered-by-existing-test` boundary owned by the drift gate |
| GPT-4 + Gemini-1 | high | The early return must use shared **completeness**, not the sentinel, or a surviving shared sentinel still short-circuits | **Accepted.** `_plugins_healthy` is deleted as a gate; `main()` no longer has a combined early return. `_heal_plugins` is always called and is self-no-op'ing. Test `test_neither_short_circuit_survives` pins both routes with both sentinels alive |
| GPT-2 | med | `rglob()` descends **into** `.in_use` before excluding; walk must be copytree-equivalent (per-dir `_IGNORE`, prune before descent) | **Accepted.** Explicit top-down stack traversal calling `_IGNORE(dir, names)` on each directory's own child names and pruning directories before descending |
| GPT-3 | med | Swallowing `OSError` turns an incomplete scan into a false-healthy | **Accepted.** Tri-state `_delivered() -> set | None`; unknown ⇒ no claim, no copy |
| GPT-5 | med | `exists()` is type-blind — a directory or broken symlink where a file belongs reads as present | **Accepted, and free.** Both sides are built by the *same file-only* walk and compared as sets, so a directory/broken-symlink at a file's path is simply absent from the dst set ⇒ counts as a gap. No `exists()` call remains |
| GPT-6 | low | Traversal should stay rooted; do not follow destination links to establish health | **Accepted.** Paths are always derived via `relative_to(root)`; non-file entries are never recorded |

### Cost

Steady-state (healthy) cost is one `stat` walk of **both sides of both trees**
— four walks, ~4 400 entries. First estimated at ~150 ms from one-sided probes;
the finished code was then run against the live cache and measured at
**189-229 ms** across runs (89 ms shared + 141 ms plugins on the first). The higher number is the honest one
and is recorded here rather than the estimate.

Accepted for a fail-open hook that runs once per session start: it buys the
difference between a safety net that inspects 1 file and one that inspects
4 400. If it ever needs to come down, the lever is a stamped "verified at
<mtime>" sidecar, not a cheaper health question.

**Same probe validated AC3 on real data**, which no synthetic fixture can: all
14 mirrors and `shared/` returned *complete*, so the hook is a clean no-op
against the live cache — zero phantom gaps. That is the direct empirical
confirmation that the `.in_use` / `.orphaned_at` ignore entries are correct;
without them this probe would have reported 14 incomplete mirrors.

## Alternative considered — per-plugin sentinel

Check `dst/.claude-plugin/plugin.json` per plugin instead of one global
sentinel. **Rejected:** 14× cheaper but the *same class* of bug — a partial reap
leaving `plugin.json` standing still reads healthy. It converts "1 file gates 14
mirrors" into "1 file gates 1 mirror", which is an improvement in blast radius
and no improvement in soundness. The card asks for a health check; a cheaper
wrong answer is still wrong, and the whole point is that this is the net under a
reap that has already been measured once.

## Affected Boundaries

- `shutil.copytree(ignore=...)` — the callable's per-directory contract
  `(dirname, names) -> ignored_names`, reused verbatim by the walk.
- The Claude Code cache manager's private files (`.in_use/<pid>`,
  `.orphaned_at`) — written into trees we read but never owned by this repo.
- The vendoring boundary: 13 byte-identical copies, drift-gated.
- Filesystem walk on Windows (case, junctions, unreadable dirs → fail-open).

## Acceptance Criteria

- **AC1** A partial plugins mirror (some plugin's files removed) with the
  `shipwright-run` sentinel intact IS repaired on the next SessionStart.
- **AC2** A partial `shared/` tree with `scripts/lib/project_root.py` intact IS
  repaired when **our own** marketplace clone (`marketplaces/<cache name>/shared`)
  is available. A *foreign* clone may restore an absent `shared/` but must never
  judge whether ours is complete — see AC7.
- **AC3** A fully healthy cache remains a **no-op** — no copy, no "self-healed"
  output — with `.in_use/<pid>` present in sources and `.orphaned_at` in mirrors.
- **AC4** The dev `--plugin-dir` model stays a silent no-op.
- **AC5** All 13 vendored copies stay byte-identical; the hook's ignore set is
  pinned against `cache_tree_compare.SKIP_DIRS`.
- **AC6** Fail-open preserved: every failure path still exits 0, and the two
  trees repair **independently** — a failed `shared/` copy still runs the plugins
  repair, and one unwritable mirror does not block the other thirteen.
- **AC7** Only the same-name clone decides completeness (added at self-review —
  see "Design changes after the plan" below).
- **AC8** The repair source is the **numerically** newest installed version, so
  `0.10.0` beats `0.2.0`.

## Design changes after the plan

Two changes were made during Step 7 self-review, after the external plan review
had signed off on the control flow. Recording them here rather than only in a
code comment, because they change the contract the reviewers approved.

**1. Only our own clone may judge completeness (AC7).** The plan's snippet used
`_find_marketplace_shared` — which, failing a same-name clone, scans
`marketplaces/*/shared` for *any* tree carrying the sentinel. That breadth is
right for restoring an **absent** `shared/`: a stranger's copy beats nothing.
It is wrong as a completeness authority — a foreign clone's extra files would
read as our gaps and its code would be copied into this cache on every session.
Split into `_same_name_shared` (completeness) vs `_find_marketplace_shared`
(restore). Consequence, stated plainly: an install that has *only* a foreign
clone gets restore-but-never-top-up. That is the intended trade — declining to
act beats acting on the wrong authority. Pinned by two tests, and verified by
mutation (reverting the split fails
`test_a_foreign_marketplace_clone_never_decides_completeness`).

**2. Numeric version ordering (AC8).** `_plugin_mirrors` sorted versions
lexically, so `0.10.0` sorted before `0.2.0`. Harmless before — the loop skipped
on `dst.exists()` and never read the pick — but the pick is now the *authority*
on completeness, so an older source would compare against stale content and copy
it over a good mirror. Mirrors `cache_tree_compare.version_key`, which cannot be
imported here (stdlib-only).

## Review cascade — findings and resolutions

`spec-reviewer` (HARD-GATE) → `code-reviewer` → `doubt-reviewer`. Stage 1
REJECTED the first pass on three citations (all fixed; re-review PASS). Stage 2
APPROVED conditionally. Stage 3 is adversarial and advisory-must-address: it
attacked six claims and **five did not survive**.

**The two that changed the shipped code most.** Both reviewers independently
found the same defect from opposite directions, and it is the one that would
have bitten first:

| # | Sev | Finding | Resolution |
|---|---|---|---|
| CODE-1 + DOUBT-5 | med | The ignore set was pinned against `cache_tree_compare.SKIP_DIRS` — the **checker**. The **producer**, `update-marketplace.sh`, excludes strictly more, including `.python-version`, which all 14 plugins gained *today* (iterate-2026-08-01-pin-python-311). The moment an install delivers one, every mirror reads incomplete and re-copies 1464 files **every session** — the exact failure this design calls fatal. Latent, so the live-cache probe could not see it | **Fixed.** `.python-version` added; the pin now parses `update-marketplace.sh`'s own `-not -name` tokens, so the hook is held to the WRITER, not just the checker. New `test_ignore_set_covers_every_name_the_PRODUCER_withholds` + a `SKIP_SUFFIXES` pin |
| DOUBT-1 + CODE-5 | high | On POSIX `update-marketplace.sh` makes the mirror a **symlink** to the installed version dir. A stale link plus a newer installed version routes `copytree` **through** the link into the OLDER version's directory — a tree the hook neither owns nor can restore, and self-concealing (the next run reads it complete). The old `dst.exists()` skip made this unreachable; a completeness check reaches it. No fixture modelled the symlinked layout at all | **Fixed.** `_heal_plugins` skips a mirror that `is_symlink()`. Two tests: a cross-platform unit pin driving the real `_heal_plugins`, and an end-to-end POSIX test (skipped on Windows — creating a symlink there needs a privilege this host lacks, verified `OSError 1314`; CI is Linux and runs it) |
| DOUBT-3 | med | The docs claimed "~200 ms **paid once per session**" three lines after acknowledging 12 vendored SessionStart registrations. Claude Code fires SessionStart from every hook-bearing plugin, so the real cost is **12×**, and when a heal is needed all 12 copy onto the same destination concurrently while sibling hooks import from that tree | **Doc corrected to 12×** (the old claim was simply false). Serialization NOT done here: the fan-out is an existing, separately-tracked concern, and fixing it inside one of 12 vendored copies of one hook is the wrong layer. Filed as `trg-0c5af217` with the `event_once.claim_once` pattern named |
| CODE-9 + DOUBT-8 | low | `want - have` was a case-SENSITIVE set difference over a case-INSENSITIVE filesystem; a case-only divergence is a gap `copytree` can never close | **Fixed**, and the first attempt was wrong in a way the tests caught: `os.path.normcase` also rewrites separators to backslashes on Windows, breaking the posix keys. Now folds case only, and only on `nt` |
| CODE-2 | med | `architecture.md` handed the follow-up off as "filed as trg-5005bf57" — an id in no tracked store | **Fixed.** Card filed against the MAIN root (a worktree filing is invisible) and swept into this branch |
| CODE-3 + CODE-4 | med/low | `check_plugin_cache_sync.py`'s docstring, `test_plugin_cache_sync_verdict.py`, and the `UNGATED` verdict string all still asserted that `_plugins_healthy` exists and blocks the drift gate — a function this diff deletes | **Fixed** in all three; `UNGATED` now points at the open follow-up instead of a dismissed card |
| CODE-6 + CODE-7 | low | Two tests were weaker than their docstrings: the "share one ignore callable" test was a tautology, and the prune-before-descent test passed for a descend-then-filter walk too | **Fixed.** The callable is now observed being queried per directory; the prune test records `iterdir` receivers and asserts the walk never *enters* an ignored dir |
| CODE-8 | low | `_version_key` claimed to mirror `cache_tree_compare.version_key` with no pin | **Fixed** — parametrized equality test over 11 names |

**Doubts addressed but deliberately NOT fixed** (each is now stated rather than
implied):

- **DOUBT-4 — the plugins source is itself reap-eligible.** The mirror's
  completeness basis is `cache/<name>/shipwright-X/<version>`, which lives in the
  same reap-eligible tree as the destination. A partially reaped *source*
  enumerates fine and yields a short want-set, so the mirror is declared complete
  against a damaged basis. This is real, and it means the two halves do **not**
  share one trust model: `shared/` is judged against a git clone *outside* the
  cache, the mirrors against a sibling *inside* it. Recorded as an assumption
  below; no in-cache basis is available to do better, and the drift gate
  (`trg-5005bf57`) is the right place to catch it.
- **DOUBT-7 — nobody checks mirror content, ever.** Ledger row 23 hands truncation
  to `check_plugin_cache_sync.py`, but that check does not cover the mirror tree
  and is monorepo-only, so end users have no content check on either tree. Row 23
  is restated as an accepted uncovered gap rather than a delegation.
- **DOUBT-9 — heal-vs-reap standoff.** Ignoring `.orphaned_at` means the healer
  will refill a tree the platform has marked for reaping, and the marker is
  currently on all 14 mirrors. Precedence is deliberate: the marker means "not
  referenced by `installed_plugins.json`", which ADR-120 measured as permanently
  true of these trees by construction — it is not a reap prediction. Treating it
  as one would disable the healer permanently.
- **DOUBT-10 — AC6 isolation is `OSError`-scoped.** A non-`OSError` from
  `copytree` still exits 0 (fail-open holds) but aborts the remaining mirrors.
  AC6 is scoped to `OSError` rather than widened to bare `Exception`, which would
  also swallow programming errors in the hook itself.

## External CODE review — findings and resolutions

Run `--mode code` after the cascade (openrouter; gemini truncated, openai
`revise`).

| # | Sev | Finding | Resolution |
|---|---|---|---|
| GPT-1 | high | "None of the 13 vendored copies are updated in this diff" | **False — an artifact of the input.** The diff supplied to the reviewer deliberately excluded `plugins/*` (12 byte-identical copies, ~3 600 lines of noise). All 12 are re-vendored and `test_ensure_shared_cache_vendored.py` passes forward and reverse. Noted rather than dismissed, because a reviewer given a partial diff reaching a wrong conclusion is a fact about how the review was run |
| GPT-3 | low | The AC3 no-op test asserts only that stderr lacks "self-healed"; an implementation that copies both healthy trees and suppresses the message would pass | **Accepted, fixed.** New `test_a_whole_cache_calls_copytree_ZERO_times` monkeypatches `copytree` and asserts zero calls on a whole cache with `.in_use`/`.orphaned_at` present. The subprocess test genuinely cannot see this — it only has stderr |
| GPT-2 | med | `_version_key` sorts `1.0.0-rc1` AFTER `1.0.0` (`"-rc1" > ""`), so a prerelease would be chosen as the repair authority | **Real, latent, deliberately not fixed here.** Every installed plugin in the live cache carries a plain `MAJOR.MINOR.PATCH` and one version each, so it is unreachable today. More importantly the defect belongs to `cache_tree_compare.version_key`, which this hook's key is pinned **equal** to — fixing one side only would break the pin and split the convention. Filed as `trg-18da39b0` covering both implementations and the pin together |
| Gemini | high (truncated) | A sentinel-less cached `shared/` falls back to a foreign clone, restoring foreign code | **Pre-existing and unchanged.** `if not _shared_healthy(...): source = _find_marketplace_shared(...)` is byte-identical to the old code; this diff narrows the *completeness* path to the same-name clone only, it does not widen the restore path. Not a regression introduced here |

## Test Completeness Ledger

Every behavior this diff introduces or changes. **testable ⇒ tested**;
0 untested-testable.

| # | Behavior | Status | Evidence / `reason_code` |
|---|---|---|---|
| 1 | Partial plugin mirror behind a surviving sentinel is repaired | `tested` | `test_heals_partial_plugin_mirror_behind_surviving_sentinel` |
| 2 | Partial `shared/` behind a surviving sentinel is repaired | `tested` | `test_heals_partial_shared_tree_behind_surviving_sentinel` |
| 3 | Neither former short-circuit survives (both trees, both sentinels alive) | `tested` | `test_neither_short_circuit_survives` |
| 4 | A whole cache stays a no-op despite `.in_use` / `.orphaned_at` litter | `tested` | `test_noop_when_cache_manager_markers_are_present` |
| 5 | `.in_use` is never mirrored into the cross-plugin tree | `tested` | same test, second assertion |
| 6 | A foreign clone never decides completeness | `tested` | `test_a_foreign_marketplace_clone_never_decides_completeness` (mutation-verified) |
| 7 | A foreign clone still restores an absent `shared/` | `tested` | `test_a_foreign_marketplace_clone_still_restores_an_absent_shared` |
| 8 | One unwritable mirror does not block the others | `tested` | `test_one_unwritable_mirror_does_not_block_the_others` |
| 9 | A failed `shared/` copy does not skip the plugins repair | `tested` | `test_a_failed_shared_copy_does_not_skip_the_plugins_repair` |
| 10 | Walk is copytree-equivalent: ignored dirs pruned before descent | `tested` | `test_delivered_prunes_ignored_dirs_without_descending` |
| 11 | Walk drops ignored files by pattern (`*.pyc`, `*.pyo`, `.orphaned_at`) | `tested` | `test_delivered_drops_ignored_files_by_pattern` |
| 12 | Tri-state: unreadable tree ⇒ `None`, empty tree ⇒ `set()` | `tested` | `test_delivered_is_none_for_a_tree_that_is_not_there`, `test_delivered_returns_empty_set_for_an_empty_tree` |
| 13 | Unknown source ⇒ verdict `None` (never a false "complete") | `tested` | `test_incomplete_is_none_when_the_source_cannot_be_read` |
| 13b | A **mid-walk** OSError abandons the verdict rather than shortening the file set — covers the symlink/junction-loop case | `tested` | `test_delivered_is_none_when_a_subdirectory_fails_mid_walk` (loop behaviour measured on a real `mklink /J` junction) |
| 14 | Extra files in the destination are not gaps | `tested` | `test_incomplete_ignores_extra_files_in_the_destination` |
| 15 | A directory where a file belongs counts as missing | `tested` | `test_incomplete_true_when_a_directory_stands_where_a_file_belongs` |
| 16 | Absent destination tree ⇒ incomplete | `tested` | `test_incomplete_true_when_the_destination_tree_is_absent` |
| 17 | Numeric version ordering picks the newest source | `tested` | `test_version_key_orders_numerically_not_lexically`, `test_plugin_mirrors_picks_the_numerically_newest_version` |
| 18 | Dev `--plugin-dir` model yields no mirror pairs | `tested` | `test_plugin_mirrors_yields_nothing_in_the_dev_repo_model`, `test_dev_plugin_dir_model_is_noop` |
| 19 | Ignore set stays a superset of `SKIP_DIRS ∪ {ORPHAN_MARKER}` | `tested` | `test_ignore_set_covers_every_cache_tree_compare_skip_dir`, `test_ignore_set_covers_the_orphan_marker` |
| 20 | Walk and copy share one ignore callable | `tested` | `test_walk_and_copy_share_one_ignore_callable` |
| 21 | Fresh-install delivery + fail-open unchanged | `tested` | `test_heals_shared_and_plugins_on_fresh_install`, `test_heals_plugins_without_marketplace_clone`, `test_fail_open_when_no_clone_and_no_run` |
| 22 | All 13 vendored copies byte-identical, registered first at SessionStart | `tested` | `test_ensure_shared_cache_vendored.py` (forward + reverse) |
| 25 | The ignore set covers every name the PRODUCER (`update-marketplace.sh`) withholds — incl. `.python-version` | `tested` | `test_ensure_shared_cache_ssot_pins.py::test_ignore_set_covers_every_name_the_PRODUCER_withholds` (parses the script's own `-not -name` tokens) |
| 26 | The ignore set covers `cache_tree_compare.SKIP_SUFFIXES` | `tested` | `…_ssot_pins.py::test_ignore_set_covers_the_cache_tree_compare_skip_suffixes` |
| 27 | `_version_key` is equivalent to `cache_tree_compare.version_key` | `tested` | `…_ssot_pins.py::test_version_key_is_equivalent_to_the_shared_implementation` (11 names) |
| 28 | Every `copytree` call site passes `ignore=_IGNORE` | `tested` | `…_ssot_pins.py::test_every_copy_site_passes_the_shared_ignore_callable` |
| 29 | The walk actually consults the shared ignore callable, per directory | `tested` | `…_walk.py::test_the_walk_actually_consults_the_shared_ignore_callable` |
| 30 | The walk never ENTERS an ignored directory (prune before descent) | `tested` | `…_walk.py::test_delivered_never_enters_an_ignored_directory` (records `iterdir` receivers) |
| 31 | A mirror that is a SYMLINK is never written through (guard) | `tested` | `…_repair_isolation.py::test_heal_plugins_skips_a_mirror_that_is_a_symlink` — cross-platform, drives the real `_heal_plugins`; its sanity assertion proves the mirror would otherwise be copied |
| 32 | End-to-end: a stale symlinked mirror does not corrupt the older installed version dir | `tested` | `…_repair_isolation.py::test_a_symlinked_mirror_is_never_written_through` — **runs on Linux CI only**; skipped on Windows, where creating a symlink needs a privilege this host lacks (verified `OSError 1314`). Row 31 is the cross-platform pin |
| 33 | Path keys are case-folded on Windows only, and separators stay posix | `tested` | `…_walk.py::test_delivered_lists_plain_files_relative_and_posix` + `::test_delivered_prunes_ignored_dirs_without_descending` — both failed against an `os.path.normcase` implementation that rewrote separators |
| 34 | A whole cache calls `copytree` **zero** times (AC3 at the operation, not the log line) | `tested` | `…_repair_isolation.py::test_a_whole_cache_calls_copytree_ZERO_times` — the subprocess test can only see stderr, so a copy-then-suppress implementation would have passed it |
| 23 | A **truncated** (present but short) file is not detected | `untestable` | `covered-by-existing-test` — presence-only is a measured decision: a content rule here re-copies 24 shared files every session (CRLF). **Accepted uncovered gap, not a delegation** (DOUBT-7): `check_plugin_cache_sync.py` covers the *shared* tree's content only, does not cover the mirror tree at all, and is monorepo-only — so end users have no content check on either tree. Closing it is `trg-5005bf57`'s job |
| 24 | Real-cache walk latency (~53 ms plugins / ~33 ms shared) | `untestable` | `requires-external-nondeterministic-service` — depends on the host filesystem and the live cache's size; measured by probe, not assertable in CI |

## Confidence Calibration

- **Boundaries touched:** `copytree(ignore=)` per-directory callable contract;
  cache-manager private files (`.in_use`, `.orphaned_at`); the 13-copy vendoring
  boundary; Windows filesystem walk (unreadable dirs, case).
- **Empirical probes run:**
  1. Walked the live cache — 14 mirrors, 1464 files, all carrying `.orphaned_at`;
     the whole mirror tree is reap-eligible. *Confirms the finding's premise.*
  2. Path-set compare, clone `shared/` vs cached `shared/` — **0 gaps**, 8
     extras (all `.orphaned_at`). *A completeness check is stable here.*
  3. Path-set compare, each plugin source vs its mirror — **false gap on all
     14**: `.in_use/<pid>`. *Landmine; drove the ignore set. Without this probe
     the fix would have re-copied 1464 files every session.*
  4. Timed both walks one-sided: 53 ms / 33 ms.
  5. Bloat baseline queried — file absent, no anti-ratchet exposure.
  6. **Ran the finished logic against the live cache, read-only:** `shared/`
     complete, all 14 mirrors complete, decision latency **189-229 ms** across two runs. *Confirms
     AC3 on real data (a clean no-op, zero phantom gaps) and corrects probe 4's
     one-sided estimate — the real cost is four walks, not two.*
  7. **Mutation-verified** the foreign-clone test: reverting `_same_name_shared`
     to the broad search makes it fail. *The test has teeth.*
  8. **Built a real directory junction loop** (`mklink /J`, cache-shaped) and
     walked it. *The walk is unbounded by design, so this was the one way it
     could HANG a session — the worst outcome for a fail-open hook, since
     SessionStart has no timeout. It does not hang: `iterdir` raises
     `FileNotFoundError` at loop-depth 18 once the path passes MAX_PATH, the
     tri-state turns that into `None`, and the hook makes no claim and no copy
     (42 ms, exit 0). POSIX terminates the same way via ELOOP/PATH_MAX.
     Generalised into a mid-walk-failure test rather than left to luck.*
- **Test Completeness Ledger:** the 24-row table in the "Test Completeness
  Ledger" section above — every behavior `tested` or `untestable` with a
  closed-vocabulary `reason_code`; 0 untested-testable.
- **Confidence-pattern check:**
  - *Asymptote (depth):* the failing mechanism is pinned by a test that
    reproduces the exact surviving-sentinel state, not by a test that merely
    deletes a whole tree (which the old code already handled).
  - *Coverage (breadth):* both trees, both short-circuit routes, the
    `dst.exists()` skip, the no-op path, and the dev model.
  - *Integration composition (`cross_component`):* the bootstrap is executed as
    a **real subprocess** against a faithful cache+marketplace layout, so the
    `Path(__file__)` walk, the copy, and the health check are proven to compose
    — recorded as a `category:"integration"` behavior.
