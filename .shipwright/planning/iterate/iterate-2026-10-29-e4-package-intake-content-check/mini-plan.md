# Mini-plan: E4 package intake content check and kit-token warning

1. shared/scripts/tools/brief_project_mode.py: factor the content check into `content_issues(text)` (used by `apply`) and add a read-only `check` command.
2. shared/scripts/lib/brief_intake_checks.py (new): `content_issues` runs `brief_project_mode.py check` in its own interpreter (ADR-045 namespace isolation); `token_warnings` loads the design plugin's check_brand_tokens.py from where it sits next to shared and reports missing kit tokens and failing declared contrast pairs.
3. shared/scripts/lib/brief_dir_intake.py `_intake_dir`: refuse `invalid_content` before mapping; add `warnings` to the result.
4. Docs: hooks-and-pipeline.md Brief intake row, run brief-intake.md, project brief-mode.md.
5. Tests: shared/tests/test_brief_intake_checks.py, project plugin write_run_config brief test (fixture md made valid).

## Architecture Review
GLM and OpenAI (external) and the internal architecture-internal-reviewer: approve option A. Internal findings accepted-and-fixed: token check fails open on any checker error; kit rules judged through the kit's own check() over a warm-set base (no restated rules); refusal message says fix and re-approve.

## Internal Plan Review
opus-plan-reviewer: accepted-and-fixed: fail-open token check (high); installed version wins over the cache plugins/ mirror; UTF-8 child decoding (errors=replace, PYTHONUTF8); guide check (hooks-and-pipeline updated, guide has no Brief-intake section); pinned kit attributes in a test. Rejected-with-reason: stdin-fed check text (swap window already deferred to U3, same read pattern as apply); re-raising the tool's refusal code (the package is verified before the check; a refusal there is infrastructure, kept io_error).

## External-Plan-Review-Findings
| Finding | Disposition |
|---|---|
| GLM: subprocess heavier than needed | rejected-with-reason: ADR-045 namespace conflict is real (the tool binds lib/tools), documented in the module docstring |
| GLM: two homes for content_issues | accepted-and-fixed: wrapper renamed check_content |
| GLM/OpenAI: callers handle the new refusal and show warnings | accepted-and-fixed: write_run_config prints warnings; brief_intake prints the result; docs |
| OpenAI: sibling plugin may be absent; timeouts | accepted-and-fixed: skipped warning; timeout becomes io_error; tests |

## External-Code-Review-Findings
| Finding | Disposition |
|---|---|
| OpenAI: missing font sizes never warned | accepted-and-fixed (e4e8b52e2) |
| GLM: RuntimeError escapes as traceback | rejected-with-reason: intake_dir converts RuntimeError to BriefRefused io_error; a test asserts it |
| GLM: missing visual-guidelines.md only advisory | rejected-with-reason: REQUIRED_FILES layout check refuses a package without it |
| GLM: mirror-only fallback may be stale | rejected-with-reason: advisory only; repo checkout has no other copy |
