# Shipwright's own project profile

Run: iterate-2026-11-16-u5-shipwright-profile (campaign profile-architecture-rules, unit U5). No FR is minted; the criterion is AC33 under FR-01.01.

## Decision
`.shipwright/profiles/shipwright-monorepo.json` is a copy of the bundled `claude-plugin` profile under its own name, plus rules that name mechanisms found only in this repository. The `profile` key of the run, project and build configs now names it, so the resolver gives `source=project`. `render_architecture_rules.py` wrote the block into this repo's `conventions.md`.

## Repo-only rules and their honest classes
- One pytest root per process: validator, mechanism the root `conftest.py` session guard (loaded only when the repository root is pytest's rootdir).
- Pre-commit anti-ratchet: hook, mechanism the pre-commit script and the anti-ratchet check; runs only in a clone that installed it, `--no-verify` skips it, and it reads the baseline from the working tree, so a commit that also edits the recorded size passes.
- Bloat check in CI: validator, mechanism the Bloat Check workflow; it also reads the committed baseline, so raising an entry passes and shows only in the PR comment. The "list new crossings, never raise `current`" half is a separate `prompt-only (mechanisable)` rule (the internal plan review caught that one rule claimed both halves).
- Stop hook for new crossings: hook, mechanisms the file-size detector (PostToolUse Write and Edit) and the bloat Stop gate; covers only files edited with Write or Edit in the last hour, not Bash or subagent changes; session-only, fail-open, not at merge; added after the doubt review showed the first draft claimed nothing blocks a new crossing.
- Baseline discipline (never raise `current`, list new crossings, no `--no-verify`): prompt-only (mechanisable), no mechanism.
- hooks.json quoting: test class, mechanism a shared test run by CI; added so this repo's extra enforcement is visible while the bundled rule stays instruction only.

## Name-keyed consumers
CI and CodeQL template tables (`ci_workflow.TEMPLATE_BY_PROFILE`, `codeql_workflow.CODEQL_LANGUAGES_BY_PROFILE`) are keyed by bundled names: a project-source profile gets no template default on re-adopt (accepted by the campaign brief; this repo's CI files are already committed). Test, lint, dev-server, services, deploy and env data are pinned equal to the generic profile this repo used before.

## Drift control
A test pins deep equality of the copy with the bundled profile on every key except name, description and architecture_rules, and that the bundled rules are the first rules of the copy, unchanged. Editing a bundled rule makes it fail until the copy is updated: that is the intended forcing function.

## Reviews and dispositions
Code review: the --no-verify clause moved out of the hook rule (a hook cannot enforce it is not skipped). Architecture review (external, both approve; internal approve with two medium notes, both taken: name-keyed lookups listed above, enforcement labelled by what is invoked). External plan review approve (deep-equality containment already pinned). Internal plan review high (CI rule overclaim) fixed by splitting the rule; medium note on the hook's baseline read added to the rule note; cheap invocation string checks added to the test.

## Not done here
- `check_plugin_cache_sync.py --strict` is a post-merge check against the main checkout's cache; the orchestrator runs it after `update-marketplace.sh`.
- Re-adopting this repo loses bundled CI and CodeQL defaults (accepted in the campaign brief).

## Follow-ups and notes
- A seventh added rule, a note rule, says the copied notes for `no-bare-python-stdin` and `hooks-resolve-plugin-root` do not apply in this repository; the bundled rule text stays byte-pinned.
- `risk_recheck.json` records the computed small; the run is recorded medium in the F5c entry, as the campaign brief declares. F11 requires the entry to be at least the computed value and is green; the computed record is left as the tool wrote it.
- The 'five repo-only rules' wording in the F5 ledger and the immutable test-results sibling predates the sixth rule; those records are immutable and left as written (the final profile has seven added rules including the note rule).
- Not verified from this repository: how the WebUI reads the `profile` key when the name is a project profile. A follow-up for the campaign report; no code change here. U6's reader should refuse a stale block (`render --check`).
