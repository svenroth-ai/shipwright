# Mini-plan: R1a resolver foundation (no behaviour change)

Spec: `.shipwright/planning/iterate/2026-11-27-r1a-resolver-foundation.md`; BRIEF sections 12 (items 1-3, 7), 14 (items 1-2), operator split of R1 into R1a-R1e (2026-11-27). Revision 2: plan-review findings integrated (see the spec's review sections).

## Work breakdown
1. **One module object** (`shared/scripts/lib/shipwright_paths.py`, AC1). Replace the end-of-module `setdefault` with `_unify()`, a decision table:
   - alias names = `shipwright_paths` or any name ending `.shipwright_paths` (`lib.`, `_shipwright_shared_review_lib.`, `_shipwright_shared_lib.`, future packages); flat probe names stay separate;
   - act only if `sys.modules.get(__name__)` IS this module (`.__dict__ is globals()`), else do nothing (exec-without-register and hand loaders);
   - bare entry absent → register this module under `shipwright_paths`;
   - bare entry is a module with `SPECS` whose resolved `__file__` equals ours and is not us → `sys.modules[__name__] = bare` (importlib returns it and binds it on the parent package);
   - anything else (`None` from a test hiding the resolver, a fake without `SPECS`, a resolver from another tree / cache version) → do nothing.
   Docstring: correct "Two module objects are harmless" and the 12.1 claim "R1/R3/R4 are an edit in this file"; note that a hand loader under an alias name must re-read `sys.modules` after exec, and that the swapped object keeps `__name__ == "shipwright_paths"`.
2. **Known locations** (same file, AC4): registry gains a `target` column (default `.shipwright/config`; `dev_server` → `.shipwright/runtime`, D1 — still `moves=False` until R1c/R3). `new_rel(key)` (`None` unless moving), `known_rels(key)` (`(new, legacy)` or `(legacy,)`), `all_known_rels(kinds=None, *, moves=None, marker=None, include_retired=False)` (the set-level helper for the frozen sets, 12.1). Docstring: R1c owns the final contract. Resolver stays ≤ 300 lines.
3. **Pointer recogniser** (new `shared/scripts/lib/shipwright_pointer.py`, stdlib only, AC2/AC3). `classify(data: bytes) -> Verdict` is total (never raises) and runs these steps in order, documented in the module docstring:
   1. `size = len(data.replace(b"\r", b""))` (BOM counted);
   2. decode `utf-8-sig`; failure → `not_stub`;
   3. any line (split on `\n` only) starting `<<<<<<<`, `=======` or `>>>>>>>` → `not_stub`;
   4. first line = `text.split("\n", 1)[0].strip()`; `re.fullmatch(r"SHIPWRIGHT-POINTER/([1-9][0-9]{0,8})", line, re.ASCII)`; no match (incl. `/0`, `/01`, non-ASCII digits, over-long digits, a ` ` inside the line) → `not_stub`;
   5. `size > 512` → `edited` (before the version check);
   6. version > 1 → `too_new`; version 1 → `stub`.
   Content after a valid first line (e.g. JSON) is NOT inspected: the rule is signature + cap (14.1); the row is pinned `stub` with that reason. `Verdict` is a NamedTuple `(kind: str, version: int | None)` with string constants, so copies loaded under several names compare equal. `render(min_plugin_version)` validates a SemVer string (ASCII, no whitespace/control chars, else `ValueError`) and asserts the 11.5 shape and ≤ 512 bytes. No function returns a path.
   **Shared fixtures** live in `shared/testkit/pointer_stub_cases.json` (one row per case: `id`, `text` or `hex`, `location` root|new, `expect`, `why`), so R1c/R2/R3 and CI reuse the same table. The `location: new` row is recorded now, asserted by R1c.
4. **Handoff listing** (`shared/scripts/tools/generate_session_handoff.py:430`, AC7): print `CONFIG_FILES[skill]` (the repo-relative path; byte-identical today, correct after the move); the dead fallback goes. Test through the existing entry point asserts the exact lines.
5. **Tests** (`shared/tests`, tagged `FR-01.11`):
   - `test_shipwright_pointer.py`: every fixture row, totality on random bytes, render round-trip and validation.
   - `test_shipwright_paths_identity.py` (subprocesses, clean interpreter): all load orders over `shipwright_paths`, `lib.shipwright_paths`, `from lib import shipwright_paths`, `_shipwright_shared_review_lib`, `_shipwright_shared_lib` (via `shared_lib_loader`); parent-package attributes are the same object; `rel()` agrees across aliases; hidden bare (`None`) untouched; fake without `SPECS` untouched; a copy of the resolver at another path stays separate; probe name stays separate. Plus a toy-package contract test of importlib self-replacement (`import pkg.mod`, `from pkg import mod`) so a future interpreter fails on the mechanism.
   - `test_shipwright_paths_fallbacks.py`: (a) AST scan of production Python for registry basenames inside an `_sp is None` conditional or an `except ImportError` handler: each literal is a registry basename and, where paired with a key, equals `legacy_rel(key)` (identical today; R1c decides the post-move value, 12.7a); (b) "resolver-hidden branch" subprocess test per shared hook with a fallback: imports with `_sp is None` and its module-level fallback constant equals the literal.
   - `test_shipwright_paths_basenames.py` (AC6): subprocess per consumer with the whole layout moved (`rel`, `names_of`/`rels_of_kind`, `snapshot_paths` patched to the new form before loading): `ac_surface`, `suite_worktree_diff`, `pr_review_generated`, `event_seeder` keep their bare-name sets, and `lib.config.CONFIG_FILES["run"]` DOES follow the move. Static AST rule over production Python (empty allowlist, 0 hits today, proven by a synthetic positive case): `.name` / `basename_of()` / `os.path.basename()` / `.parts[-1]` compared or `endswith`-matched against a path-returning resolver call or a module constant built from one. Limits recorded in its docstring: constants imported from another module, `fnmatch`.
6. **Brief**: section 5 records the R1a-R1e split; 11.5 gains the `_migration_check.py` row (done).

## Alternative approach
Make every caller import one canonical name and let the guard enforce it; put the recogniser inside the resolver. Rejected because plugins cannot import `lib.*` from shared without shadowing their own `lib` package (ADR-045), which is why several names exist; and the resolver is at its size cap while the recogniser judges content, not location.

## Risks
- importlib swap semantics — pinned by the toy contract test (CI runs 3.11; 3.12/3.13 run locally once, recorded at Step 7.5).
- Resolver line cap (300): docstring prose is trimmed to make room.

## Tests
`shared/tests` root green; F0 full suite.
