# Mini-plan: r1c1-layout-lookup (revised after the plan and architecture reviews)

1. **`shared/scripts/lib/shipwright_layout.py` (new, stdlib only):** `LayoutError(Exception)` with `code`, `key`, `paths` and a message naming the fix. `locate(key, root, new_rel, legacy_rel, *, stub_capable, classify) -> Path` implements the spec's state table in a fixed order: stub at the new path (every moving key), then the root stub verdict (`run_config` only), then both copies (identical copies included). Only regular files are read; an ordinary config's first line is judged on one 2 KiB read.
2. **`shipwright_paths.py`:** `_sibling(stem)` loads `shipwright_layout` and `shipwright_pointer` by file from the resolver's own directory. The module name carries a CRC of the directory (one per tree), the loader reuses a registered module and registers before exec, and a load failure becomes `ImportError`. `path()`, `main_path()` and `json_path_or_none()` call `locate()`. `lock_for()` is unchanged: the root lock is the one lock in both layouts. Prose is trimmed to stay at 300 lines.
3. **No dual lock** (operator decision after the reviews; BRIEF 12 item 11b). No writer changes.
4. **`check_file_size`:** remove the dead resolver fallback (unguarded import, `path("build_config", cwd)`). `bloat_baseline` stays strict. Drop the two strict xfails and the hook's allowlist entries.
5. **Stop hook:** the phase-completion `except Exception` reports a `LayoutError` (matched by class name, per tree) on stderr. The line count stays the same.
6. **Tests:**
   - `test_shipwright_layout.py`: every state-table row for every moving key, the shared pointer fixture set, error contract, round trip, the R1c-1-alone invariant, one module per tree, missing sibling.
   - `test_handoff_stop_reads_new_layout.py`: integration, real hook, no patching; the negative control fails on the old hook.
   - The seven tests that copy the resolver alone copy its siblings too.
7. **Verify:** resolver, guard and fallback tests, ruff, `verify_local`, full F0 suite.
