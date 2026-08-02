# Mini-Plan — iterate-2026-08-01-cache-heal-per-plugin

Spec: `iterate-2026-08-01-cache-heal-per-plugin.md`

## Chosen approach — delivered-file-set completeness check

One helper walks a tree the way `shutil.copytree` would, driven by the **same**
`_IGNORE` callable, and returns the set of relative paths the copy would
deliver. A tree is healthy iff `delivered(src) - delivered(dst)` is empty.

```
_IGNORE_NAMES = ("__pycache__", "*.pyc", "*.pyo", ".venv", ".pytest_cache",
                 ".git", "node_modules", ".in_use", ".orphaned_at")
_IGNORE       = shutil.ignore_patterns(*_IGNORE_NAMES)

_delivered(root)      -> set[str] | None   # copytree-equivalent walk; None = unknown
_incomplete(src, dst) -> bool | None       # None = either side unreadable
_version_key(name)    -> tuple             # 0.10.0 > 0.2.0  (added at self-review)
_plugin_mirrors(cache_root, plugins_target) -> [(newest_version_dir, dst), ...]
_heal_plugins(cache_root, plugins_target)   -> bool   # self-no-op'ing
_shared_healthy(target)                     -> sentinel (cheap liveness, kept)
_same_name_shared(cache_root)               -> our clone (added at self-review)
_find_marketplace_shared(cache_root)        -> any clone — RESTORE ONLY
```

**Two helpers were added after this plan was reviewed** (`_same_name_shared`,
`_version_key`); both are recorded with their reasoning in the spec's "Design
changes after the plan" section, and each is pinned by its own test. The short
version: only *our own* clone may answer "is the cached tree complete?", and the
repair source must be the numerically newest installed version.

`_plugins_healthy` is **deleted**. It existed only as the gate that this card is
about; keeping a second walker in parallel with `_heal_plugins` would double the
cost and re-open the chance for the two to disagree.

### `main()` control flow after the fix

The combined early return is gone. `_heal_plugins` is called unconditionally and
returns `False` when every mirror is already whole.

| condition | today | after |
|---|---|---|
| both sentinels present, plugins mirror partial | `return 0` at line 113 | gaps detected → that plugin re-mirrored |
| both sentinels present, shared partial | `return 0` at line 113 | clone compared → shared overlay-copied |
| shared partial, plugins sentinel present | line 124 short-circuits | both repaired |
| plugin dir exists but partial | `dst.exists(): continue` | gaps detected → overlay copy |
| everything whole | no-op | no-op (unchanged) |
| dev `--plugin-dir` | no-op | no-op (no top-level `shipwright-*`, no clone) |
| no marketplace clone | advisory | advisory; sentinel trusted, **no** false alarm |
| either side unreadable | — | unknown → no claim, no copy, exit 0 |

The "no clone" row is deliberate: with no clone there is no repair source, so
declaring `shared/` incomplete would only print the scary advisory on every
session in the dev model. Completeness for `shared/` is asserted **only** when a
comparison basis exists.

```python
if not _shared_healthy(shared_target):
    source = _find_marketplace_shared(cache_root)   # RESTORE: any clone beats none
else:
    own = _same_name_shared(cache_root)             # TOP-UP: only our own clone
    source = own if own is not None and _incomplete(own, shared_target) is True else None
if source is not None:
    try:
        copytree(source, shared_target, ignore=_IGNORE, dirs_exist_ok=True)
    except OSError:
        pass                                        # must not skip the plugins repair
```

Two source-selection rules, not one — restore is broad, top-up is strict. An
install carrying only a *foreign* clone therefore gets restore-but-never-top-up.

### Steps

1. **RED** — add the partial-reap scenarios (AC1–AC4) + an ignore-set SSoT pin
   (AC5). Confirm they fail against today's hook. *(As executed, these landed in
   a new `test_ensure_shared_cache_partial_reap.py` plus a `…_walk.py` unit
   module, with layout builders extracted to `ensure_shared_cache_fixtures.py`,
   rather than all inside the existing integration module — it crossed the
   300-line guideline once the surviving-sentinel cases were added.)*
2. **GREEN** — edit the canonical
   `shared/templates/hooks/ensure_shared_cache.py` only.
3. **VENDOR** — copy canonical → 12 `plugins/*/scripts/hooks/`; verify with
   `test_ensure_shared_cache_vendored.py` (byte-identical + first-SessionStart).
4. **DOCS** — `docs/hooks-and-pipeline.md` §"Shared Hook: ensure_shared_cache.py"
   and `.shipwright/agent_docs/architecture.md` (the "knowingly ungated"
   paragraph, which cites this very triage item as its reason).
5. **VERIFY** — `shared/tests` root, ruff, then the F-phases.

### Out of scope (deliberate)

Joining `cache/plugins/` to `check_plugin_cache_sync.py`. The card offers it as
a *follow-on* ("**Once** the mirror tree is soundly healed, it can also join the
drift gate"). It is a separate producer with its own basis/verdict semantics
(ADR-120), and bundling it would put a new gate and the fix it depends on in one
PR. Filed as follow-up instead; `architecture.md` is updated to say the healer
is now sound and the gate is the open item.

## Alternative — per-plugin sentinel (`plugin.json`)

Rejected. Cheaper, same class of bug: a partial reap that leaves `plugin.json`
standing still reads healthy. Full reasoning in the spec.

## Risks

| risk | mitigation |
|---|---|
| walk/copy ignore-set mismatch → **re-copy every session** | one shared `_IGNORE` callable, queried per-directory as copytree does; AC3 asserts the no-op with `.in_use` present |
| `.in_use` PID churn | in the ignore set; probe 3 is the evidence |
| SessionStart latency | measured **189-229 ms** on the live cache (four walks, both sides of both trees); fail-open; accepted — see the spec's Cost section |
| 13-copy drift | existing bidirectional vendoring gate |
| unreadable dir on Windows | walk returns `None` (tri-state) — it does **not** swallow per-dir and continue, which would under-count the source into a false "complete". Unknown ⇒ no claim, no copy; the hook still exits 0 |
| symlink / junction loop hangs a SessionStart hook | measured on a real `mklink /J` loop: `iterdir` raises at depth 18 (MAX_PATH) → `None` → no claim, no copy, 42 ms. Pinned by `test_delivered_is_none_when_a_subdirectory_fails_mid_walk` |
