# E2E run findings: fixes and a second end-to-end run

**Stand:** 2026-10-28, rev 1 (draft for the operator) · **Input:** `2026-10-26-e2e-run-findings-REPORT.md` (findings F1-F8; the operator direction of sections 7 and 8 replaces its guesses) · **Kit:** merged in #936 (`plugins/shipwright-design/skills/design/kit/untitled-ui/`)
**Execution:** autonomous campaign, `branch_strategy: serial` with `depends_on` edges, no parallel units. Two operator stops: after E2 (profile decision) and after E8 (the run report). Progress lives in the campaign's `status.json`. No per-finding triage cards; one bundle triage item starts the campaign.

## 0. Goal

Make the operator end-to-end run (`integration-tests/e2e-webui/`, WebUI to finished app) test the **right product** and fix what a guided user also hits. The right product is a **skill-backed app**: the Claude app is the chat; the app is a skill (better: a plugin) with a companion of a served HTML board plus a Python backend and a JSON data folder. Look and feel comes from the Untitled UI kit; the brand supplies tokens only (`kit/untitled-ui/tokens-contract.md`). Then run the end-to-end run again and report.

Every unit helps a person running the pipeline guided as well as an unattended run, unless marked "auto only".

## 1. Start conditions (operator checks before starting)

1. Kit merged and the plugin cache synced (`check_plugin_cache_sync.py --strict`). Done 2026-10-28.
2. BP (baseline protection) briefs read; the coordination rules of §6 are accepted.
3. **Scope (BP):** `scope_frs` (§2) is on `main` before the first unit runs, because BP reads it from `main`, not from a worktree. E2 may propose changes to it and the operator extends it at stop 1. A unit touching an FR outside it is held by BP's `Baseline` check and needs the operator's label. BP only observes until it is armed (BL6), so nothing blocks yet.
4. Plugin changes under `plugins/*/skills/` make the Tier-3 PR Review ask for a maintainer. The operator decides before starting whether a campaign-scoped admin merge applies (as for earlier campaigns); without it every unit stops at its PR.
5. BP has been asked about conflicts; its answer and conditions are in §6.

## 2. `scope_frs` (existing FRs this campaign intentionally changes)

**Campaign-wide:** `scope_frs: FR-01.01, FR-01.02, FR-01.03, FR-01.04, FR-01.05, FR-01.06, FR-01.08, FR-01.12`

The list holds every existing FR whose text, tests or code this campaign changes on purpose. New FRs the campaign mints are not listed. It is complete rather than short: a missing FR makes BP hold a PR until the operator releases it by label. FR-01.03 and FR-01.08 are listed because E2 changes the shared stack-profile schema that Plan and Deploy read, so their tests or text may move with it; if E2 finds they do not, it says so at stop 1 and they come off the list.

**Per unit:**

| Unit | `scope_frs` | Why |
|---|---|---|
| E1 | FR-01.04 | boundary gate in the design phase (F1) |
| E2 | FR-01.02, FR-01.03, FR-01.05, FR-01.06, FR-01.08, FR-01.12 | the profile schema and resolver are read by every phase that builds, tests, previews or deploys; E2 records what each does with a plugin-shaped app |
| E3 | FR-01.04, FR-01.01 | kit-composed mockups in Brief-package mode, no chat layout for this app class; the run phase's gate wording where it names the layout |
| E4 | FR-01.02 | package intake content check (F6) and the kit-token warning |
| E5 | FR-01.06 | screenshot check for a served board, CSP-safe capture (F2, F3) |
| E6 | FR-01.06, FR-01.01 | the harness and fixture; answering gates by meaning (F7) |
| E8 | none | a run and its report only |

Not touched on purpose: FR-01.09 to FR-01.11 and FR-01.14 to FR-01.18. A unit that needs one of them stops and asks. A unit never edits `scope_frs` itself; the operator extends it at stop 1.

## 3. Units

| id | Unit | Finding | Real touch set | depends_on | Cx |
|---|---|---|---|---|---|
| **E1** | Boundary gate ignores uncommitted output of the previous phase, so Design stops asking "commit earlier output first?" in every brief run | F1 | `plugins/shipwright-design/scripts/checks/` (boundary gate), its tests, `design/SKILL.md` wording | - | small |
| **E2** | Stack profile for the skill-backed app: fields `host` (desktop app / terminal), `delivery` (skill / plugin), `companion` (ui + backend, started and stopped by the skill), data folder location; copied in spirit from the social-engagement skill; what Build, Test, Preview and Deploy do with a plugin-shaped app. Replaces `chat-first-json` for this app class. **STOP 1** | report §7, §8 | `shared/profiles/`, the stack-profile resolver and its schema, `docs/stack-profiles.md`, tests | - | large |
| **E3** | Design in Brief-package mode composes from the kit and the package's tokens instead of adopting mockups unchanged or building a chat layout; chat-first path (`chat-first.md`, Layout D, `ux_shape: chat-first`) retired for this app class; kit pointers in Step 4 and iteration mode already merged | report §3, §7 | `plugins/shipwright-design/skills/design/` (SKILL.md, `references/chat-first.md`, `step-4`, `snippets-layout.md`), `apply-brief-package.py`, `check-design-gates.py` and tests | E2 | medium |
| **E4** | Package intake runs the same content check as the Project phase (F6) and warns when the visual guidelines lack kit tokens (checked against `tokens-contract.md`) | F6, report §4.3 | `plugins/shipwright-project/` intake path, a token-contract checker reusing the kit's contrast logic, tests | E2 | medium |
| **E5** | Screenshot check for a served board (routes and states) and capture that survives the app's own CSP | F2, F3 | `plugins/shipwright-test/` screenshot check and capture tool, tests | E2 | medium |
| **E6** | Harness and fixture for the new app class: fixture Brief package (skill, board, backend, JSON data), harness checks test backend API and board HTML instead of chat commands (H06-H11 replaced), soft items S01, S02, S04-S08 become checks, run resume | F8, report §7 | `integration-tests/e2e-webui/`, fixture, report template | E3, E4, E5 | large |
| **E7** | Card in the **WebUI repo**: the inbox lists questions asked in the embedded terminal | F4 | `svenroth-ai/shipwright-webui` (one card, not a unit here) | - | - |
| **E8** | Operator procedure (§4): second end-to-end run on the plugins loaded from the E6 commit, with the report | all | report only | E1, E3-E6 | - |

F5 (Claude Code "dangerous rm" dialog) and F7 (gate wording) need no unit: plugins avoid the `rm` pattern, and gate answering stays meaning-based (kept as a rule in every unit's review).

## 4. Operator stops

1. **After E2:** the profile. In plain words: what does a skill-backed app consist of, where does its data live, who starts and stops the board and the backend, and what do Build, Test, Preview and Deploy do with it? Decision recorded in the ADR; `scope_frs` extended if E2 found more.
2. **After E8:** the second end-to-end run. Plugins loaded from the E6 commit (hash recorded), not from the cache. The report names what passed, what is still "not evaluated", and whether the built app now looks like the kit's board. Open findings become the next campaign's input.

## 5. Unit rules

Docs in the same diff; edits local and rebased on `main`; new files at most 300 lines; one pytest root per process; `uv run scripts/verify_local.py` and `uvx ruff@0.15.15 check .` before push; tests tagged with the FR/AC they prove; review cascade per CLAUDE.md (`model=opus` explicitly); a unit red twice is released with its dependents; anything needing an operator answer between stops is a STRICT-STOP. After every unit that edits plugin-side files: `bash scripts/update-marketplace.sh` and `check_plugin_cache_sync.py --strict` before the next unit starts.

## 6. Coordination with BP (baseline protection)

- **No entry in `.github/workflows/ci.yml`, `pyproject.toml` or `scripts/verify_local.py`.** They belong to BP. If a unit needs one, it stops and asks first.
- `scope_frs` is in this brief (§2); BP reads it from `main` at the merge base and holds PRs touching FRs outside it.
- `docs/hooks-and-pipeline.md`, `docs/guide.md` chapter 8 and the glossary are also edited by BP, at its end. Merge conflicts there are expected and harmless; units keep edits in those files to the rows they own.
- BP reported no file conflict with this campaign (operator message of 2026-10-28), subject to the three rules above.
- BP's own touch set, as it stated it: `shared/scripts/lib/fr_classification.py` (one rule) and the new `shared/scripts/lib/assertion_weakening_args.py`. It does not touch `fr_gates`, the requirement write-back files, `shared/profiles/` (resolver included) or `shared/prompts/`. E2 works in `shared/profiles/` and the resolver, so the two do not overlap. A unit that needs `fr_classification.py` stops and asks.

## 7. Open points for the operator

- Does Deploy need a plugin-shaped target (E2 records what deploy does today; FR-01.08 is outside `scope_frs`)?
- Is the second run's target "the Social Engagement board's look from a Brief package" (kit plus brand tokens) or only "kit look with default tokens"?
- Which soft items become hard checks in E6 beyond S01, S02 and S04?
