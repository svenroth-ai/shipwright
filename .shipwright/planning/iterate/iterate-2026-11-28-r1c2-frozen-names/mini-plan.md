# Mini-plan: R1c-2 (route frozen names of moving files through path())

1. AST codemod: every `<root> / CONST` where CONST = `<sp>.rel("<moving key>")` (defining module + `from m import CONST` importers) becomes `_sp.path("<key>", <root>)`; print every rewrite; hand-fix modules without a resolver binding (add the package's resolver import).
2. Lists of root names joined in loops become registry-key lists resolved with `path()` (adopt REQUIRED_CONFIGS x2, _HONESTY_ARTIFACTS, setup_adopt config candidates, lib.config / compliance collectors CONFIG_KEYS). Event-log entries stay root joins (the log stays).
3. Stale-cache fallbacks: `root / ("<lit>" if _sp is None else _sp.rel(k))` -> `root / "<lit>" if _sp is None else _sp.path(k, root)`; inline the three fallback constants; extend the fallback scan to the join shape (same root both sides, literal == legacy_rel).
4. Indirect joins: test-gate escape helper gets `path(...).relative_to(root)`; merge_boundary_coverage default `_sp.path("test_results", ".")`.
5. Registry: flip audit_config (D2, .shipwright/config) and dev_server (D1, .shipwright/runtime) to moving rows.
6. Guards: new constant-join guard (positive controls); class-8 rule ignores path() (working-tree leg); prune rel-join-fallback allowlist; shrink constants inventory 80 -> 73 and its cap.
7. Tests: moved-layout end-to-end test (file only in the new place) with a negative control on the pre-change tree; full F0.
Out: pathspecs/sets/messages, rel()-moved test, carriers -> R1c-3; LayoutError per hook -> R1e.
