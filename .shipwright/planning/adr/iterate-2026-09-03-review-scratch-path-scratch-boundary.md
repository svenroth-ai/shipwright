# Resolve the bash/Python temp-file boundary instead of trusting a bare `/tmp/` path

## Context

Git-Bash/MSYS mounts `/tmp` onto `%TEMP%`; native Python resolves a leading
`/` against the current drive's root (e.g. `C:\tmp\<name>`). Any skill step
that writes a file from bash and reads it from a `uv run` Python process via
a bare `/tmp/<name>` path silently operates on two different physical files
on Windows — the write succeeds, the read sees stale or absent content, and
nothing raises an error. This broke the code-review pipeline's diff-file
handoff (`code-review.md` Step 6b/6c) and the campaign loop's units-list
handoff (`campaign-mode.md`).

## Decision

Two different fixes for two different boundary shapes, chosen after an
Architecture Review (GLM + OpenAI via OpenRouter) recommended a smaller
design than the original "scratch file for every boundary" plan:

1. **`campaign_units.json` (campaign-mode.md → `autonomous_loop.py init`):**
   both sides are same-shell `uv run` Python CLIs invoked back-to-back, so
   the units list is piped straight through (`list-units | ... init
   --units-from -`). No file, no path to diverge on. `autonomous_loop.py`
   gained an `isatty()`-guarded stdin read and a clean `JSONDecodeError`
   error path.
2. **The 4 diff-file boundaries** (frozen-snapshot review artifacts feeding
   the external LLM review cascade) keep a scratch file, because the
   snapshot must survive across several sequential subagent/CLI steps and a
   pipe cannot do that. `shared/scripts/lib/review_scratch.py` provides
   `resolve(run_id, name)` / `cleanup(run_id)`: both the bash write site and
   the Python read site call `resolve()` independently and land on the
   identical path (a private, ACL-hardened root under
   `host_resource_lease.py`'s existing `%LOCALAPPDATA%\Shipwright` /
   `$XDG_RUNTIME_DIR/shipwright` hardening — not a plain `tempfile.gettempdir()`).
   `cleanup()` is explicit-only, called once terminally by whichever step's
   flow is longest-lived for that boundary.

A regression guard (`test_review_scratch_guard.py`) scans every
`plugins/*/{skills,agents}/**/*.md` + `shared/prompts/**/*.md` file (217
files) for a bare `/tmp/<root>` literal, so a future skill edit cannot
reintroduce the bug undetected.

## A real bug the review cascade caught: cleanup ownership

`code-review-protocol.md` (build's Step 6b, the code-reviewer subagent step)
originally owned its own `cleanup()` call on the diff file it wrote. But
`code-review.md`'s Step 6c (the optional external review cascade) runs
immediately after 6b and reuses that exact diff file. Whenever the cascade
was enabled, 6b's cleanup deleted the file out from under 6c before it could
read it — a bug that would have silently broken the external cascade on
every build session with the cascade on, never caught by an isolated review
of either file alone. Fixed by removing 6b's own cleanup entirely; 6c's own
terminal step is now the sole, unconditional cleanup owner (it runs whether
or not the cascade itself fires, since 6b already wrote the file either way).

## Hardening (from Stage-2 code-review + external review + doubt-review)

- `_validate_component` canonicalizes `run_id`/`name` to lowercase (a
  case-insensitive filesystem could otherwise let `Foo`/`foo` collide) and
  rejects Windows reserved device names (`CON`, `NUL`, `COM1`, …).
- `resolve()` calls `_safe_file(allow_missing=True)` before returning,
  rejecting a pre-planted reparse point at the target path.
- `cleanup()` uses `os.path.lexists()` (not `Path.exists()`/`is_symlink()`)
  to detect a directory **junction** at the run root — `is_symlink()` only
  catches `IO_REPARSE_TAG_SYMLINK`, never `IO_REPARSE_TAG_MOUNT_POINT`
  (junctions), and junctions need no elevated privilege on Windows (verified
  empirically via `mklink /J`), making them the realistic vector.
  `_reject_linked_components` (checks `FILE_ATTRIBUTE_REPARSE_POINT`, either
  tag) is the actual junction guard and runs before `rmtree`.
- Doubt-reviewer's ACL-cross-tool-write concern (a file written by the bash
  tool might carry different effective ACLs than one written by Python) was
  disproved empirically on this host: `resolve` → bash `>` write → `resolve`
  again all exit 0, because both processes inherit the same Windows user
  token.

## Rejected alternatives

- **Scratch file for every boundary** (the original plan): rejected by
  Architecture Review as more machinery than the units-list boundary needs —
  it has no frozen-snapshot requirement, so a pipe is strictly simpler and
  removes a cleanup call entirely.
- **Self-healing stale-directory sweep in `resolve()`:** rejected — cleanup
  is explicit-only at every call site, so a sweep would only mask a call
  site that forgot to clean up rather than surfacing it.
- **A `# test-hygiene: allow-silent-skip` marker** on the reparse-point
  regression tests (to silence the privilege-gated `pytest.skip`): rejected
  in favor of planting a Windows directory junction (no privilege needed)
  instead of a symlink — this also more faithfully exercises the exact gap
  the tests exist to catch, since symlinks were already caught by the
  pre-existing `is_symlink()` check and only junctions bypass it.

## Consequences

- Two shared library modules gain a permanent, narrow responsibility:
  `review_scratch.py` (diff-file scratch paths) and the piping convention in
  `autonomous_loop.py init --units-from -` (stdin ingestion).
- The regression guard's 217-file glob is intentionally broad (every
  skill/agent doc, not just the files this run touched) — narrowing it to a
  fixed list would defeat its purpose of catching a *future* skill edit that
  reintroduces the bug.
- Cleanup is best-effort only against a same-user TOCTOU race between the
  reparse-point checks and `rmtree` — out of scope, since nothing untrusted
  runs as this user inside that window.
