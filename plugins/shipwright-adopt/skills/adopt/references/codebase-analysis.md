# Codebase Analysis — Detector Heuristics

## Detection chain (Layer 1)

All detectors live in `scripts/lib/` and are composed by
`scripts/tools/analyze_codebase.py` into a single JSON snapshot.

| Detector | Inputs | Output keys |
|---|---|---|
| `stack_detector` | `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `composer.json`, `Gemfile`, `tsconfig.json` | `stack.{primary_language,runtime,frontend,backend,database,auth,signals}` |
| `profile_matcher` | Stack signature + `shared/profiles/*.json` | `profile.{matched,confidence,candidates}` |
| `convention_detector` | `.eslintrc*`, flat `eslint.config.*`, `.prettierrc*`, `tsconfig.json`, `.editorconfig`, `pyproject.toml` `[tool.ruff]`/`[tool.black]` | `conventions.{linter,formatter,tsconfig_strict,editorconfig,python_style}` |
| `test_framework_detector` | `package.json` deps, `pytest.ini`, `pyproject.toml` `[tool.pytest]`, `go.mod`, `Cargo.toml`, `supabase/tests/database/` | `test_frameworks.{unit,integration,e2e,db,coverage_tool}` |
| `ci_detector` | `.github/workflows/`, `.gitlab-ci.yml`, `.circleci/config.yml`, `Jenkinsfile`, `.travis.yml` | `ci_pipeline.{provider,workflows}` |
| `folder_introspector` | Top-level directories + `src/` children | `folders.{layers,loc_by_layer}` |
| `nested_project_detector` | Sub-dirs with `.git/`, `shipwright_run_config.json`, `CLAUDE.md` + `.shipwright/agent_docs/`, or deep `package.json`/`pyproject.toml` | `nested_projects[]` |
| `feature_inferrer` (AST) | Next App/Pages router, Express/Fastify routes, FastAPI/Flask `@app.route` | `features[]` with `fr_id`, `route`, `source_file`, `framework`, `confidence` |
| `git_analyzer` | `git log --numstat` | `git.{commits_total,first_commit,contributors,major_refactor_commits}` |

## Profile matching

Scoring: simple Jaccard-like overlap between the detected stack's
dependency names and each profile's `stack.*` name set. A best-score
of ≥0.30 returns that profile; otherwise `generic` with confidence 0.

Override with `--profile-hint <name>`.

## Excludes

Nested projects can be excluded via `--exclude-path <rel-path>`. All
detectors respect the exclude list:
- `stack_detector` skips manifests under excluded paths
- `folder_introspector` skips layer counting
- `feature_inferrer` skips route files under excluded paths
- `git_analyzer` always runs on the repo root (history is shared)

## Known limitations (V1)

- Framework coverage for AST-based `feature_inferrer`:
  - ✅ Next.js App Router, Next.js Pages Router
  - ✅ Express / Fastify / generic `app.get/post/...`
  - ✅ FastAPI `@app.route` decorators
  - ✅ Flask `@app.route` / `@bp.route`
  - ⚠️ Rails, Django, Spring Boot, Laravel — V2 scope
- For any web-app with a dev-server, **Layer 1.5 (Playwright crawl)**
  replaces the AST inferrer and is framework-agnostic.
