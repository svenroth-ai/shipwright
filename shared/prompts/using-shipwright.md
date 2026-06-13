# Using Shipwright

> Injected at SessionStart by `session_start_using_shipwright.py` whenever
> `shipwright_run_config.json` is present in the project root. It orients a
> fresh session so the user does not have to prime it.
>
> Adapted from the obra/superpowers `using-superpowers` bootstrap pattern
> (MIT, © Jesse Vincent — https://github.com/obra/superpowers).

**You are working in a Shipwright SDLC project.** Shipwright is an AI-driven
software lifecycle built on Claude Code plugins (one per phase). Route work
through the phase skills below instead of ad-hoc editing — the skills enforce
TDD, review, compliance, and a clean git/PR workflow.

## Routing — pick the skill, don't freelance

| The user wants to… | Use |
|---|---|
| **Add a feature, change behavior, fix a bug, refactor, improve code** in this finished project | **`/shipwright-iterate`** |
| Start a brand-new project / decompose requirements (IREB) | `/shipwright-project` |
| Onboard an EXISTING repo into Shipwright (brownfield) | `/shipwright-adopt` |
| Plan implementation details for an existing spec | `/shipwright-plan` |
| Design UI mockups from a spec | `/shipwright-design` |
| Implement a planned section (TDD) | `/shipwright-build` |
| Run tests (unit / smoke / E2E) | `/shipwright-test` |
| Scan + remediate security findings | `/shipwright-security` |
| Deploy | `/shipwright-deploy` |
| Changelog / release / version tag / PR | `/shipwright-changelog` |
| Compliance audit, traceability, RTM, SBOM, drift check | `/shipwright-compliance` |
| See the app running locally | `/shipwright-preview` |

**Default for day-to-day change requests is `/shipwright-iterate`.** It is
complexity-adaptive (trivial → large) and auto-detects feature vs. change vs.
bug. So when asked *"how do I add a feature?"* or *"there's a bug"*, the answer
is **`/shipwright-iterate`** — not a raw edit.

## Before you change code

- **Governing rules:** `shared/constitution.md` (ALWAYS / ASK FIRST / NEVER) is
  binding. Highlights: tests must pass before commit; Conventional Commits;
  never `--no-verify`, `git reset --hard`, or `git push --force` to main; never
  weaken a test or RLS to make it pass; YAGNI (no features beyond spec); keep
  files ≤300 LOC (source/tests) / ≤400 LOC (runtime-prompts).
- **What fires when:** `docs/hooks-and-pipeline.md` is the single source of truth
  for hooks, the context-loading matrix, and the artifact-write matrix.
- **Vocabulary:** `shared/glossary.md` (Allowlist, Ratchet, Anti-Ratchet,
  Producer, Canon-Gate, …).

## If you are developing Shipwright ITSELF (this monorepo)

Editing files under `plugins/*`, `shared/*`, or any `SKILL.md` changes the
framework, not a target app. Those changes do **not** auto-reach the runtime
plugin cache. Read `shared/prompts/writing-plugin.md` and, when done, run
`bash scripts/update-marketplace.sh` + `uv run scripts/check_plugin_cache_sync.py
--strict`. A Stop hook will remind you once per session (it files no triage item
— the re-sync is current-run maintenance, not a deferred backlog item).

## Triage & follow-ups

Background producers append findings to `.shipwright/triage.jsonl` (drift,
compliance, security, performance). Surface them with
`/shipwright-compliance` or the Command Center WebUI. Don't silently ignore open
high/critical items.

## Iron Law

NO COMPLETION WHILE TESTS ARE RED OR FILES ARE GROWING UNCHECKED. If you are
tempted to skip a test layer, weaken an assertion, or commit through a failing
gate — stop and fix the cause. Spirit over letter.
