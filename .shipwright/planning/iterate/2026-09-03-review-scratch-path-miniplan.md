# Mini-Plan: review-scratch-path

- **Run ID:** iterate-2026-09-03-review-scratch-path

**Status: superseded by `## Internal Plan Review` in the iterate spec.** The
work breakdown below is the ORIGINAL plan, kept for provenance; the shell-var
handoff (step 4), `tempfile.gettempdir()` base (step 1), and unvalidated
`rmtree` (step 1) it describes were all revised after the internal plan
review found them unsafe/broken. What actually shipped: independent
deterministic `resolve()` calls at every write/read site (no shell var
crosses a Bash tool call), a hardened private root reused from
`host_resource_lease.py`, and validated/containment-checked `cleanup`. See
the iterate spec's `## Internal Plan Review` section for the authoritative
finding-by-finding disposition, and `## Acceptance Criteria` / `##
Confidence Calibration` for what was actually built and tested.

## Files to create/modify

| File | Change |
|---|---|
| `shared/scripts/lib/review_scratch.py` | new — `resolve()` / `cleanup()` |
| `shared/scripts/tools/review_scratch.py` | new — CLI wrapping the lib (`resolve`, `cleanup` subcommands) |
| `shared/scripts/tools/tests/test_review_scratch.py` | new — unit + cross-process contract tests (single root; see revised design) |
| `shared/scripts/tools/tests/test_review_scratch_guard.py` | new — regression guard: no bare `/tmp/` literal in `plugins/*/skills+agents/**/*.md` or `shared/prompts/**/*.md` (same root as the file above) |
| `plugins/shipwright-build/skills/build/references/code-review.md` | edit — resolve path once, reuse for write+read, cleanup step |
| `plugins/shipwright-build/skills/build/references/code-review-protocol.md` | edit — same pattern |
| `plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md` | edit — same pattern |
| `plugins/shipwright-iterate/agents/sub-iterate-runner.md` | edit — same pattern |
| `plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md` | edit — same pattern, `campaign_units.json` |
| `docs/guide.md` | edit — line ~1524, describe resolved-path mechanism instead of the bare `/tmp` path |

## Work breakdown

1. Write `review_scratch.py` lib: `resolve(run_id, name) -> Path` (creates
   `<tempfile.gettempdir()>/shipwright-review/<run_id>/`, joins `name`,
   ensures parent dir exists), `cleanup(run_id) -> None` (`shutil.rmtree`,
   `ignore_errors=True` semantics but explicit existence check first so a
   double-cleanup is a documented no-op, not a silently swallowed error).
   Test: round-trip write-via-open/read-via-open in the same process
   (sanity), determinism (same run_id+name → same path across calls),
   cleanup removes the dir, cleanup on a non-existent run_id is a no-op.
2. Write the CLI (`shared/scripts/tools/review_scratch.py`): `resolve
   --run-id ID --name NAME` prints the absolute path with forward slashes
   (`.as_posix()`-equivalent on the drive-letter form, e.g.
   `C:/Users/.../Temp/shipwright-review/<run_id>/diff.txt`) so Git-Bash
   accepts it unmodified in a `>` redirect and a `uv run ... --diff-file`
   argument alike; `cleanup --run-id ID` calls `cleanup()`.
3. **Integration test** (satisfies both the `touches_io_boundary` round-trip
   requirement and the `cross_component` integration-coverage requirement,
   since `campaign-mode.md` is in the diff): a real subprocess-level test
   that (a) shells out to `uv run review_scratch.py resolve ...` to get a
   path, (b) writes to it via a Bash-tool-equivalent mechanism (a real
   `subprocess.run(["bash", "-c", f'echo test > "{path}"'])` where available,
   else a plain file write standing in for the bash side — CI is Linux so
   the actual cross-resolution bug cannot reproduce there; the test instead
   pins the *contract* that both steps receive and use the identical
   resolved string), (c) reads it back via a second `uv run` Python process,
   (d) asserts content matches, (e) calls `cleanup` and asserts the file is
   gone. This is the regression test for the root cause: the write and the
   read never independently interpret `/tmp/...`.
4. Update the 5 skill/agent `.md` files: replace the `/tmp/shipwright-review-diff.txt`
   / `/tmp/campaign_units.json` literals with the resolve-into-shell-var
   pattern (see proposal), and add the `cleanup` call as the flow's last
   step, called out as "always run, even on failure."
5. Update `docs/guide.md`'s diff-exposure-warning line.
6. Guard test: grep every `plugins/**/*.md` for a bare `/tmp/` path literal,
   fail if found (mirrors existing anti-ratchet-style guard tests in this
   repo).

## Component hierarchy
n/a — no UI.

## Data model changes
n/a.

## Test strategy
- Unit tests for `review_scratch.py` (lib-level, fast, no subprocess).
- One integration test proving the write/read/cleanup contract composes
  across two separate `uv run` invocations (the actual regression pin).
- Guard/regression test asserting no skill file regresses to a bare `/tmp/`
  literal.
- No E2E / browser surface — this is a CLI-only pipeline mechanism
  (`Verification.Surface: cli` in the iterate spec).

## Alternative approach — rejected
**Considered:** put the scratch directory inside the repo, under
`.shipwright/tmp/`, gitignored. **Rejected** per the user's explicit
instruction: a diff file can contain secrets/proprietary code, and a
project-local location — even gitignored — has a nonzero chance of getting
swept in by a broad `git add -A` or a misconfigured `.gitignore`, which the
OS temp directory (structurally outside any repo) cannot. The project-local
option was also not actually necessary to fix the divergence bug itself
(the fix is "resolve once, reuse the same string" — that works regardless of
which directory is chosen), so there was no correctness reason to accept the
extra risk.
