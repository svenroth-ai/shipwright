# Mini-plan U1 (rev 2, after plan-review round 1)

Rule contract (frozen here, consumed by U2-U6):
- `architecture_rules`: absent or null = not declared; `[]` = explicitly none; list of objects (new) or strings (legacy).
- Rule object: `id` (unique, `^[a-z0-9][a-z0-9-]*$`), `text`, `why` (non-empty strings), `enforcement` (closed vocabulary), optional `lint` XOR `mechanism`, `note` (string).
- Allowed combinations (`ALLOWED`): `validator` -> `lint` or `mechanism`; `hook` / `test` -> `mechanism` only; `prompt-only (mechanisable)`, `prompt-only (judgement)`, `unimplemented` -> neither. `lint` is only valid with `validator`. `prompt-only (mechanisable)` and `unimplemented` require a `note`.
- `lint` = `{tool: "eslint"|"ruff", target: relative path, block: non-empty object}`; `mechanism` = non-empty list of relative paths.
- Paths (lint target, mechanism entries): shape check rejects absolute paths, drive letters, backslashes, empty and `..` segments. Filesystem check (`check_paths`) resolves against the root with realpath, requires containment (symlink/junction escape = error) and existence.
- Recovery: `load_rules` returns valid rules + `errors` + `warnings`; an invalid rule (incl. lint+mechanism) is excluded from `rules` and listed in errors; duplicates: first wins, later one is an error. Legacy strings are normalised to `legacy-string-<n>` rules (declared object id wins on collision) flagged `legacy=True`, enforcement undeclared (None), plus ONE warning.

Changes:
- New `shared/scripts/profile_architecture_rules.py`: ENFORCEMENT copy, ALLOWED table, `load_rules`, `check_paths`, `shadow_rules_warning`.
- `profile_model.ResolvedProfile.shadow_warnings()` replaces the two inline shadow-warning blocks in profile_resolver (net fewer lines; text of the existing warning unchanged) and appends the lacks-architecture_rules warning only when the shadowed bundled profile has a non-empty rules list. No raw consumer of `architecture_rules` exists in code (only prose in project-scaffolding.md, which keeps reading the strings because supabase-nextjs stays strings in U1).
- `resolve_profile.py validate`: prints rule errors and the legacy warning to stderr; `--json` gets `rule_errors` / `rule_warnings`; exit 0 whenever the profile itself is valid (rule diagnostics are NOT an exit-code concern; CI consumers read `rule_errors`). Path existence is checked for non-bundled profiles against `--project-root`; bundled profiles are covered by a repo test (the installed cache has a different layout).
- Schema: `architecture_rules` described but not typed (a wrong top-level type is reported phase-locally by the loader, never invalidates the profile).
- vite-hono, skill-companion-app: `"architecture_rules": []` + `_architecture_rules_note`.
- Module docstring records: the legacy string list is accepted through the end of the profile-architecture-rules campaign; U3a converts the last bundled user.
- Tests (shared/tests): module unit tests incl. mixed list with a lint+mechanism rule; drift vs constitution ENFORCEMENT; all bundled profiles validate; bundled mechanism-path test (vacuous in U1, no bundled mechanisms yet); validate CLI behaviour (legacy warning only in validate; exit 0 with rule error); path-escape tests; shadow warning (with and without bundled rules); existing resolver warning tests re-run.
- Docs: docs/stack-profiles.md section.

## Revisions after external plan review (round 2, 2026-11-15)
- Legacy ids are namespaced `legacy-string-<n>` (n = 1-based list position), mixed lists (objects + strings) are allowed, and an id collision with a declared object id is reported as an error naming which rule is the legacy one (the declared object wins, the legacy string is dropped).
- Frozen meaning of `enforcement is None` (legacy only): "instruction only, class undeclared"; U2 renders it as instruction-only. Documented in module docstring and docs/stack-profiles.md.
- `check_paths(rules, root)` returns `[(rule_id, message)]`; the loader result is shape-only. A rule with a path problem is reported but not removed from `load_rules` output; consumers that execute mechanisms must skip ids that appear in `check_paths`. Point-in-time check only (docstring says no containment guarantee afterwards).
- Contract documented: `validate` exits 0 with rule errors (CLI help + docs); no CI workflow or script invokes validate on profiles with rules (grep recorded in ADR).
- Tests added: ordinary `resolve` of the legacy bundled profile emits no legacy warning; exact warning order of the existing shadow warning is asserted; the bundled mechanism-path test asserts the expected empty set explicitly (not vacuous); the drift test imports `lib.constitution_register` the same way the existing constitution tests do.
- Rejected: defer shadow warning to U5 (BRIEF section 3 / U1 requires it).

## Revisions after internal plan review (opus-plan-reviewer, revise)
- Accepted: legacy id spelling fixed in the frozen block; required keys per class pinned by tests (validator/hook/test without mechanism or lint = error); eslint `block` must hold a non-empty `rules` object, ruff `block` = non-empty object (finer ruff shape deferred to U4, first ruff-backed rule - deliberate narrowing of "fragment shape per tool"); base dirs frozen (mechanism: repo root for bundled, project root otherwise; lint.target: target project, containment only); wrong top-level type = error + no rules + "not declared"; unknown non-underscore keys warn; bundled shadow file read inside try/except returning no warning; `rules_valid` added to validate --json; bundled-profile test asserts `rule_errors == []`; stderr lines go through `_plain`; project root named in path errors.
- Rejected with reason: reuse `profile_model.path_within` for containment (profile_model imports this module; circular) - the module does realpath + normcase + commonpath, the same core as path_within.
- Internal architecture review (approve): explicit empty list only for vite-hono / skill-companion-app (campaign decision 4.2); python-plugin-monorepo is rewritten in U4 and chat-first-json is a separate track. `lint` is class `validator` (brief 2.1), so the vocabulary copy stays equal to the constitution's.
