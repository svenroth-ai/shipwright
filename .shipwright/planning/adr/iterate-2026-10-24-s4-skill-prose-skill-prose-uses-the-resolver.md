# Skill prose uses the stack-profile resolver

Campaign stack-profile-resolver, unit S4. Runtime prose no longer builds a bundled stack-profile path.

## Decision

- Read-only sites (test first-actions, project step-7, security, build section-builder and migrations-apply) call `resolve_profile.py resolve --path-only`; empty output means built-in defaults, exit 2/3 means stop and show the message.
- Test-layer sites that run commands pass the profile NAME (`--profile`) and, for the performance check, `--project-root`; no bare `--profile-path` remains (D8f).
- Preview's gate is the resolver exit code (0 continue, 2 not found, 3 invalid).
- Sites that only described the location now describe the lookup order (project, user, bundled).
- The S2 hand-off sentence (profile problem: stop and show the message, do not retry) sits at every `dev_server.py start` call site in iterate, build, test, preview and adopt.
- Two tests: a markdown/hooks.json guard (planted path red then green, allowlist reverse, zero findings) and a snippet-runner that extracts each resolver command from a fixed list of edited files and runs it against a tmp project.

## Architecture Review

External: GLM approve, GPT approve (low: keep the snippet-runner scoped to a fixed file list; done). Internal arms not run (effective complexity small).

## External-Plan-Review-Findings

| Reviewer | Finding | Disposition |
|---|---|---|
| GPT (medium) | check exit status before consuming `--path-only` stdout; empty = defaults | accepted-and-fixed (each site states empty = defaults, exit 2/3 = stop) |
| GPT (medium) | iterate omitted from inventory; hand-off sentence incomplete | accepted-and-fixed (iterate x3 added; sentence carries exit 2/3, kind, do not retry) |
| GPT/GLM (medium) | guard scope: hooks.json, S5 deferral allowlist, stale entries | accepted-and-fixed (`docs/` allowlisted for S5, hooks.json plant case, reverse test) |
| GLM (medium) | guard must be in the default run | accepted (lives in shared/tests, which CI runs) |
| GLM (medium) | preview gate surfaces the resolver message | accepted-and-fixed (stop and show the message) |
| GLM (low) | snippet-runner coupling | accepted: fixed file list, test fails if fewer than 7 snippets found |
| GLM (low) | preview SKILL.md grows 9 lines | rejected-with-reason: not in the bloat baseline, well under 400 |

## Confidence Calibration

Boundary: resolve_profile.py output (stdout path, exit 0/2/3, empty for sentinels) consumed by skill prose. Probes run: (1) every resolver command in 7 edited files executed against a tmp project with a project-level profile: exit 0 and the project path printed; (2) same commands with an unknown name: exit 2; (3) same with `generic`: exit 0, empty stdout; (4) guard planted-path probes (md form, `{shared_root}` form, JSON-escaped Windows path, case/variant forms): all red, fixed form green. Probes with findings: 2 (code-review: guard false negatives and dead allowlist entries), both fixed and re-probed; two consecutive no-finding passes followed. Not probed: running the prose commands through a live Claude session (acceptable: the commands are plain shell).

## Guard allowlist beyond the brief

`shared/glossary.md` defines the Profile term; `.shipwright/planning/` and three named agent-doc files (conventions, decision_log, triage_inbox) are historical or descriptive records; `CHANGELOG*` is history; `docs/` stays until S5. Each entry must excuse a real finding (reverse test). Every `--path-only` snippet states "exit 0 with empty output = built-in defaults; any other non-zero exit = stop and show the message" (exit 4 usage and exit 1 also print nothing, so "empty" alone must never read as defaults); a test enforces it with a planted old-wording case and an empty-name exit-4 case. Inline `dev_server.py start` mentions in sub-iterate-runner.md and test SKILL.md carry the exit 2/3 stop note.
