# Mini-Plan: hooks-uv-run-project-pin

- **Run ID:** iterate-2026-09-28-hooks-uv-run-project-pin

## 1. Files to create/modify

- `plugins/shipwright-adopt/hooks/hooks.json` — edit (insert `--no-project`)
- `plugins/shipwright-build/hooks/hooks.json` — edit
- `plugins/shipwright-changelog/hooks/hooks.json` — edit (incl. the
  `--with pyyaml` line for `audit_compliance_on_stop.py`)
- `plugins/shipwright-compliance/hooks/hooks.json` — edit (2 lines already
  correct, remaining lines get the flag)
- `plugins/shipwright-deploy/hooks/hooks.json` — edit
- `plugins/shipwright-design/hooks/hooks.json` — edit
- `plugins/shipwright-iterate/hooks-codex/hooks.json` — no edit needed. Its
  only 2 `uv run` lines are already pinned (pre-existing exemplars named in
  the spec's Goal section: `codex_activation_mint.py`,
  `codex_pretooluse_gate.py`) — it has no other lines to fix. **Correction:**
  an earlier draft of this bullet wrongly said "remaining lines get the
  flag", copy-pasted from the sibling `hooks/hooks.json` entry without
  adjusting it for this file's actual (fully-compliant) content — that stale
  sentence caused both external code-review passes to independently flag
  this file as a high-severity omission. Verified false:
  `test_every_uv_run_hook_command_has_no_project[shipwright-iterate/hooks-codex]`
  passes unmodified; the file's diff is empty because there is nothing to
  change.
- `plugins/shipwright-iterate/hooks/hooks.json` — edit (1 line already
  correct; 1 `--with pyyaml` line needs the flag added; remaining lines get
  the flag)
- `plugins/shipwright-plan/hooks/hooks.json` — edit
- `plugins/shipwright-project/hooks/hooks.json` — edit
- `plugins/shipwright-run/hooks/hooks.json` — edit
- `plugins/shipwright-security/hooks/hooks.json` — edit
- `plugins/shipwright-test/hooks/hooks.json` — edit
- `shared/tests/test_hooks_uv_run_pinned.py` — new (static meta-test, AC-1/2)
- `shared/tests/test_hooks_uv_run_project_isolation.py` — new (integration
  test, AC-3/4 — the `category:"integration"` behavior for `cross_component`)
- `docs/hooks-and-pipeline.md` — edit (document the `--no-project` convention)

## 2. Work breakdown

**Updated post-Internal-Plan-Review and post-external-review** to reflect
what was actually built (both reviews flagged that this section had fallen
behind the spec's own Confidence Calibration content — corrected here).

1. Write the static meta-test first (`test_hooks_uv_run_pinned.py`) against
   the CURRENT (unfixed) `hooks.json` files — confirm it FAILS red, proving
   it actually detects the bug's absence-of-flag shape (TDD red step). Two
   assertions: (a) every `uv run` command starts with `--no-project`
   (exact-prefix, not "contains somewhere"), (b) a script invoked from more
   than one plugin uses an identical flag prefix everywhere — required
   because `codex_hooks_sync.py`'s bundle merge dedups by exact command
   shape and hard-fails on a mismatch.
2. Write the integration test (`test_hooks_uv_run_project_isolation.py`) with
   both the positive (`--no-project` succeeds against a poisoned CWD) and
   negative (plain `uv run` fails against the same poisoned CWD) cases. The
   command under test is derived from a REAL, currently-shipped hooks.json
   entry (not a hand-written approximation) so the test proves composition
   with the actual command shape hooks fire. The poison is an
   offline-deterministic unresolvable local `file://` dependency (not an
   unregistered-but-plausible PyPI name, which would depend on network
   behavior); both subprocess calls run with `VIRTUAL_ENV`/`UV_*` stripped
   from the environment so this test's own venv can't mask either result;
   the negative case additionally asserts its failure output mentions
   resolution/project (proving it failed for the right reason).
3. Mechanically edit all 13 `hooks.json` files: insert `--no-project`
   immediately after every `"uv run` token that does not already have it.
   One pass, regex-safe substitution reviewed file-by-file (13 files, not a
   blind sed sweep — some already have `--no-project` or `--with pyyaml` and
   must not get a duplicate/misordered flag).
4. Re-run the static meta-test — confirm GREEN.
5. Update `docs/hooks-and-pipeline.md` with the `--no-project` convention
   (per CLAUDE.md's rule: a `hooks.json` change requires this doc updated in
   the same diff), including the concrete per-machine resync commands
   (marketplace + Codex) an operator runs to actually pick up the fix, and
   `shared/prompts/writing-plugin.md`'s hook-authoring convention line.
6. Run the full existing hooks-related test suite (`shared/tests/`), plus
   the Codex hook merge/sync/launcher suites
   (`shared/scripts/tools/tests/test_codex_hook*.py`), plus every plugin
   test root flagged during review as parsing hook command strings, to
   confirm no regression to existing hook-invocation tests. This step found
   and fixed a real regression:
   `plugins/shipwright-build/tests/test_review_payload_hook_wiring_integration.py`
   naively took `command.split()[0]` as the script path, which broke once a
   flag was inserted before it — fixed by skipping leading `--flag` tokens
   before locating the quoted script path.

## 5. Test strategy

- **Static meta-test** (`test_hooks_uv_run_pinned.py`): parses every
  `plugins/*/hooks*/hooks.json` with `json.load`, regex-extracts each
  `"command"` value, and asserts every one starting with `uv run` contains
  `--no-project`. Fails loudly (file + line-ish context via the command
  string itself) if a future hook omits it.
- **Integration test** (`test_hooks_uv_run_project_isolation.py`): builds a
  temp directory with a deliberately unsatisfiable `pyproject.toml`
  (`dependencies = ["this-package-does-not-exist-xyz123"]`), `cd`s into it,
  and runs a real, trivial stdlib-only hook script via subprocess:
  - `uv run --no-project <script>` → asserts exit 0 (mechanism proven).
  - `uv run <script>` (no flag) → asserts non-zero exit (negative control;
    proves the test would have caught the original bug).
  This is the `category:"integration"` Test Completeness Ledger row required
  by the `cross_component` risk flag — it proves composition (hooks.json's
  command shape + `uv`'s actual resolution behavior), not just that a string
  literal is present in a JSON file.
- No E2E/UAT-shaped ACs — this is a pure infra/tooling fix, not a
  user-visible product surface. AC-N-user rows are not applicable.

## 6. Alternative approach considered (medium only)

**Alternative:** add `--project "${CLAUDE_PLUGIN_ROOT}/.."` (or similar,
pointing at the specific plugin's own `pyproject.toml`) instead of
`--no-project`, so `uv run` still resolves *a* project — just always the
right one instead of whatever the CWD happens to be.

**Rejected because (corrected per Internal Plan Review — every plugin DOES
have its own `pyproject.toml`, e.g. `plugins/shipwright-changelog/pyproject.toml`,
so the original "nothing to point at" rationale below was factually wrong):**
`--project <plugin>` would re-couple every hook invocation to that plugin's
own venv under the plugin cache — bringing back exactly the sync-before-run
cost (and, on a machine where that venv's own entry-point happens to be
locked, the same class of file-lock failure this iterate exists to
eliminate) for a set of scripts that are plain stdlib-only utilities (per
the AST-based import audit — zero third-party deps beyond the one already
`--with`-declared `pyyaml` case) with nothing to gain from a project sync in
the first place. `--no-project` does lose each plugin's `requires-python`
guard as a side effect (see the spec's "Known residual" note), but
`--project` does not actually close that gap either — it only points `uv`
at a project to sync, it does not pin an interpreter version by itself.
`--no-project` is also the pattern this repo has already shipped 5 times
over — consistency with existing precedent outweighs a theoretical benefit
of per-plugin project scoping that nothing here currently needs.
