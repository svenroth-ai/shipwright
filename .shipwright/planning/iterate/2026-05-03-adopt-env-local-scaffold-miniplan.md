# Mini-Plan: adopt-env-local-scaffold

- **Run ID:** iterate-2026-05-03-adopt-env-local-scaffold
- **Branch:** iterate/adopt-env-local-scaffold
- **Spec:** `.shipwright/planning/iterate/2026-05-03-adopt-env-local-scaffold.md`

## Approach (one paragraph)

Six-file change (5 edits + 1 new test). (1) `shared/scripts/validate_env.py`
learns a `_SHIPWRIGHT_FRAMEWORK_VARS` module-level constant for
OPENROUTER_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY (mirroring the
fallback order in `external_review_config.py:72-76`). `init_env_file`
gains `include_framework: bool = False` kwarg — when True, framework
vars are appended after profile vars and deduped by name (first-
occurrence wins, profile description preserved). `parse_env_file`
gains `export ` prefix tolerance. `_ensure_gitignore` failure
(OSError) is caught at the `init_env_file` boundary and turned into
`{action: "skipped", reason: "gitignore_enforcement_failed"}` —
NO `.env.local` write on `.gitignore` failure. `init_env_file`
returns the rich shape with `missing_keys` and `framework_keys`,
where `missing_keys` is computed from the final file state.
(2) The adopt artifact generator (`generate_adoption_artifacts.py`)
wires the call after `write_all` returns and surfaces the result
under `results["env_local"]`. (3) Adopt SKILL.md gains Step E.5
plus the conditional Step H banner block. (4) Tests across three
test files lock in unit, snapshot, and integration coverage.

## Files to change

| File | Action | Detail |
|------|--------|--------|
| `shared/scripts/validate_env.py` | edit | add `_SHIPWRIGHT_FRAMEWORK_VARS`, add framework-section logic to `_collect_phase_vars`, add dedup by name to `init_env_file` |
| `shared/scripts/tests/test_validate_env.py` | edit | new tests: framework-vars rendered when profile is empty; dedup when profile already has the key; phase=all renders all three sections; idempotent re-run with framework keys; placeholder-detection covers blank values |
| `plugins/shipwright-adopt/scripts/tools/generate_adoption_artifacts.py` | edit | call `init_env_file` after `write_all`, before `seed_adopted_event`; populate `results["env_local"]` |
| `plugins/shipwright-adopt/skills/adopt/SKILL.md` | edit | add Step E.5 block (between Step E and Step F); extend Step H banner with conditional "Edit .env.local" lines + key list |
| `plugins/shipwright-adopt/tests/test_adopt_pipeline_subprocess.py` | edit | add assertions to `test_full_pipeline_e2e_via_subprocess`: `.env.local` exists, contains the framework keys, `payload["env_local"]["action"] == "created"`, `.gitignore` contains `.env.local` |
| `plugins/shipwright-adopt/tests/test_skill_md_env_scaffold.py` | new | snapshot/substring asserts on SKILL.md: Step E.5 heading + body wording, Step H banner gains "Edit .env.local" line |

## Test strategy

- **Framework-vars logic** — pure unit tests on `validate_env.py` with
  in-memory profiles (existing test pattern): empty profile, profile
  with OPENROUTER_API_KEY already listed (dedup), profile with
  OPENROUTER_API_KEY listed twice (build+plugin), `phase=all` ordering.
- **SKILL.md snapshot** — a small new test file that just reads the
  `.md` and asserts: (a) the literal substring `### Step E.5 — Env
  Scaffold` exists, (b) the substring `validate_env.py --init` is
  invoked in a fenced code block, (c) the Step H banner template
  contains `Edit .env.local`. Snapshot-by-substring rather than
  full-file equality so unrelated edits don't trigger false negatives.
- **Adopt pipeline e2e** — extend the existing
  `test_full_pipeline_e2e_via_subprocess` slow test (already wired
  up, marked `slow`). After the subprocess returns, additionally:
  ```python
  assert (tmp_path / ".env.local").exists()
  env_text = (tmp_path / ".env.local").read_text(encoding="utf-8")
  for key in ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
      assert f"# {key}=" in env_text
  assert payload["env_local"]["action"] == "created"
  gi = (tmp_path / ".gitignore").read_text(encoding="utf-8")
  assert ".env.local" in gi
  ```
- **Idempotence** — a second adopt subprocess on the same `tmp_path`
  must report `action == "unchanged"` and leave the file byte-equal.
  Add this as a new test in the same file
  (`test_pipeline_idempotent_env_local`).

## Build order (TDD red → green)

1. RED: add SKILL.md snapshot tests; they fail (the new wording
   isn't there yet).
2. RED: add `validate_env.py` framework-vars unit tests; they fail
   (constant doesn't exist).
3. GREEN: implement `_SHIPWRIGHT_FRAMEWORK_VARS` + `_collect_phase_vars`
   merge + `init_env_file` dedup; unit tests go green.
4. GREEN: edit SKILL.md to add Step E.5 + Step H banner; snapshot
   tests go green.
5. RED: add adopt pipeline assertions; they fail (no scaffold call yet).
6. GREEN: wire `init_env_file` call into `generate_adoption_artifacts.py`;
   subprocess test goes green.
7. RED: add idempotence test; should fail only if step 6 over-writes.
8. GREEN: implementation already idempotent — should pass without
   further changes.

## Alternative considered (rejected)

- **Add the LLM keys to every profile JSON** instead of a
  framework-level constant. Rejected: scatters the same three entries
  across N profile files (current 3, more later) with the same
  description prose, creating a drift hotspot. The framework-keys-as-
  constant approach matches how `external_review_config.py` already
  centralizes the same fallback chain.
- **Run validate_env via subprocess from the SKILL.md instead of the
  artifact generator.** Rejected: would mean the LLM running adopt
  has to remember to invoke it, and snapshot tests can't easily
  prove it ran. Wiring it into the deterministic Python script makes
  the integration test directly assert behavior.
