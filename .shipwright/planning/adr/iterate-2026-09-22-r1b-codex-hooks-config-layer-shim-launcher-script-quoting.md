# Codex hooks: config-layer sync via per-hook launcher scripts, platform-split quoting

Long-form decision text for the decision-drop at
`.shipwright/agent_docs/decision-drops/iterate-2026-09-22-r1b-codex-hooks-config-layer-shim_001.json`
(run_id `iterate-2026-09-22-r1b-codex-hooks-config-layer-shim`). The
sequential `ADR-NNN` number for this decision is assigned by
`/shipwright-changelog`'s `aggregate_decisions.py` at release time, not
here — do not cite a number for this decision until `decision_log.md`
actually carries it.

## Context

R1 (PR #781) inlined every Shipwright plugin's hooks into the Codex
bundle's own `.codex-plugin/plugin.json`. Live probing against installed
Codex CLI found it never executes a plugin-bundled `hooks` key at all
(openai/codex#16430, #39895) — the one confirmed-working path is a
**config-layer** hooks file, `~/.codex/hooks.json`, global and
trust-independent. Building the sync producer for that path surfaced a
second, load-bearing bug: Codex invokes a hook's `command` string via
`cmd.exe /C "<command_line>"` on Windows, which wraps the WHOLE string in
one extra, unconditional quote pair — `cmd.exe /C` only parses cleanly with
exactly one quote pair total, so any command embedding its own quoted paths
(every real Shipwright hook command does) breaks silently. Confirmed
empirically (8 live Codex invocations, zero fires) and traced to
`codex-rs/hooks/src/engine/command_runner.rs` directly.

## Decision — mechanism

Write one small launcher script per hook handler (`.cmd` on Windows, `.sh` +
owner-only executable bit on POSIX) holding the real, normally-quoted
invocation, and put only that launcher's path into `hooks.json`. A single
quoted token with no arguments satisfies `cmd.exe`'s documented "preserve as
executable name" special case even when the path itself contains spaces.

Ownership detection uses directory membership, not an exact
`(event, matcher, command)` triple match: an entry is Shipwright's
if-and-only-if its command resolves inside the launcher directory
(`codex_home/shipwright-hooks/`) — self-evident from the entry alone,
avoiding both the "operator's own identical entry gets removed" collision
and the "sidecar loss permanently orphans every entry" failure mode an
exact-triple match would have. A sidecar manifest
(`.shipwright-hooks-managed.json`) records what was written, but ownership
detection does not depend on it being present.

## Decision — the POSIX mirror-bug, found by external review after the Windows fix landed

A second, independently-discovered platform bug: on POSIX, Codex runs the
`command` field via `$SHELL -lc "<command_line>"`, which re-parses the
string as a shell command line and word-splits on whitespace — so a bare,
unquoted launcher path containing a space (plausible on macOS, e.g.
`/Users/Sven Roth/.codex/...`) breaks the exact opposite way from the
Windows bug this module was built to fix. Neither the internal doubt-reviewer
nor a fresh internal code-reviewer pass caught this (both implicitly
Windows-only reasoning on this dev machine) — only the external LLM review
cascade caught it, independently, on both legs.

Fixed with a platform split in what gets written into `hooks.json`'s
`command` field: bare on Windows (unchanged — `cmd.exe`'s special case needs
no quoting, and shell-quoting there would reintroduce the double-quote bug),
`shlex.quote()`-wrapped on POSIX (a single shell token even with embedded
spaces). The read side (`_is_shipwright_entry()`'s ownership check, and the
stale-launcher cleanup loop's `wanted_names` computation) mirrors the same
split to recover the real filesystem path from either shape.

## Decision — ownership-check path normalization

The external review's second convergent finding: `_is_shipwright_entry()`
did a purely lexical `Path(command).relative_to(launcher_dir)`, with no
`.resolve()`. This misclassifies a command like
`launcher_dir/../evil.sh` as inside `launcher_dir` (the component prefix
matches) when it actually resolves outside it — both a Windows
short-path/separator-variant false-negative risk and a POSIX
`../`-traversal/symlink-escape false-positive risk. Fixed: the candidate
path is `.resolve(strict=False)`d before the containment check;
`launcher_dir` was already absolute (`codex_home` is `.resolve()`d at the
top of `sync_codex_hooks()`), so the comparison basis is consistent.

## Decision — `is_codex_runtime()` shape validation

A third, lower-severity external-review finding (medium, both legs,
convergent on severity though not on exact form): presence of the two
marker files (`BUILD_MANIFEST.json`, `.codex-plugin/plugin.json`) alone was
sufficient to treat a directory as a genuine Codex bundle — two empty
placeholder files would pass, and whatever `plugin.json["hooks"]["hooks"]`
contains gets installed as globally-executing hooks for every Codex session
on the machine. Fixed by shape-checking `BUILD_MANIFEST.json` specifically
(must parse as JSON with a non-empty `"files"` dict, matching
`build_codex_plugin.py`'s own real output) — deliberately **not**
shape-checking `plugin.json` the same way, since that is
`_read_bundle_hooks()`'s job: it already raises `CodexHooksSyncError`
loudly on a genuinely-corrupted real bundle, and shape-checking it here too
would instead silently no-op that case, the opposite of this module's
"surface loudly" design commitment.

## External-Code-Review-Findings

Two rounds, both legs (`glm`, `openai`/`opus` per driver), against the full
diff each time.

| Round | Leg | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | glm + openai | HIGH | POSIX launcher path breaks under `$SHELL -lc` word-splitting when it contains a space | accepted-and-fixed — `shlex.quote()` platform split, see above |
| 1 | openai (opus leg) | MEDIUM | `_is_shipwright_entry()` lexical `relative_to()` misclassifies `../`-traversal / path-variant mismatches | accepted-and-fixed — `.resolve(strict=False)`, see above |
| 1 | openai (opus leg) | MEDIUM | `test_stale_launcher_removal_survives_unlink_failure` never genuinely orphans a launcher (`_launcher_slug()` is positional, not content-addressed, so editing only command text reuses the same filename) | accepted-and-fixed — test now `del`s the whole handler/event structurally |
| 1 | glm | LOW | `test_lock_contention_raises_clear_error` asserts bare `RuntimeError`, which would still pass if the `except LockTimeout` → `CodexHooksSyncError` wrapper were deleted | accepted-and-fixed — asserts `CodexHooksSyncError` + message match |
| 1 | glm | LOW | `is_codex_runtime()`'s marker-only trust, no content validation | superseded by round 2's medium-severity re-raise, see below |
| 1 | glm | MEDIUM | Stray root-level files (`ext_err.log`, a duplicate `external-plan-review-raw.json`) | accepted-and-fixed — deleted; canonical copy already lived under `.shipwright/planning/iterate/<run_id>/` |
| 2 | openai | MEDIUM | Manual sync command in `docs/hooks-and-pipeline.md` has no runnable invocation example (missing `uv run` prefix) | accepted-and-fixed |
| 2 | glm | MEDIUM | `is_codex_runtime()` marker-only trust — an attacker-controlled `--bundle-root`/spoofed env var with two empty marker files passes | accepted-and-fixed — `BUILD_MANIFEST.json` shape check, see above |
| 2 | glm | MEDIUM | `test_launcher_path_with_spaces_actually_runs`'s `" " in launcher` assertion "fails on spaceless POSIX CI tmpdirs" | **rejected — verified false by code inspection**: `codex_home = tmp_path / "codex home with spaces"` guarantees a space regardless of `tmp_path` itself; this line predates this review round unchanged. Applied the leg's own secondary suggestion anyway (real `$SHELL`, not hardcoded `sh`) as a low-cost robustness improvement. |
| 2 | glm | LOW | `cmd.exe` metacharacter injection in Windows launcher bodies from unescaped bundle-command content | **rejected with reason**: the bundle is already first-party/trusted content (same trust boundary as `resolve_plugin_root()`, used unvalidated elsewhere in this codebase); an attacker able to inject `hooks.hooks[].command` already has the write access needed for arbitrary code execution independent of quoting — disproportionate scope for this pass. |
| 2 | glm | LOW | `test_ac2_placeholder_rewritten_into_launcher_script` asserts substring containment against the unresolved `bundle_root`, not the resolved path/full expected line | accepted-and-fixed |
| 2 | glm | LOW (bug) | First-ever sync into a nonexistent `codex_home` relies on `file_lock`'s undocumented mkdir behavior | **rejected — verified false**: `file_lock()` already does `path.parent.mkdir(parents=True, exist_ok=True)` before opening the lock file (`file_lock.py:209`), contract already explicit in that function's own docstring. |

## Rationale

The Windows fix (launcher scripts) was designed and verified first, against
the live Codex CLI installed on this machine — a Windows box. Both internal
review passes (doubt-reviewer, code-reviewer) reasoned and tested
exclusively in that environment, so the structurally identical but
oppositely-shaped POSIX bug was invisible to both. This is the clearest
evidence in this run for why the external code-review cascade is mandatory
by default rather than conditional on the internal cascade's outcome: two
clean internal passes converged on the same blind spot, and two independent
external legs converged on the same real bug the internal passes missed
entirely.

## Consequences

The `command` field's on-disk shape in `hooks.json` is now genuinely
platform-dependent (bare string on Windows, `shlex`-quoted string on POSIX)
rather than uniform — any future code touching `hooks.json`'s `command`
field directly (not through `_hooks_json_command()`/
`_command_to_launcher_path()`) must account for this split or risk
reintroducing either platform's bug. `is_codex_runtime()`'s stricter
`BUILD_MANIFEST.json` check raises the bar for what counts as a genuine
bundle from "two files exist" to "one of them is shaped like the real
builder's output" — a cheap, non-cryptographic check, not a hardened
security boundary; a sophisticated local attacker with filesystem write
access to fabricate a correctly-shaped manifest is out of scope for this
fix, consistent with the codebase's existing single-user-laptop trust model
elsewhere.

## Accepted Risk — bundle-root authenticity (operator decision, 2026-09-22)

The PR-review preflight gate (Tier-3, `openai/gpt-5.6-luna`) raised this as a
BLOCK against the pushed diff: `sync_codex_hooks()` resolves `bundle_root`
either from `--bundle-root` or from `resolve_plugin_root()`'s env-var chain
(`SHIPWRIGHT_PLUGIN_ROOT` / `CLAUDE_PLUGIN_ROOT` / `PLUGIN_ROOT`, none of
which are cryptographically bound to a real Shipwright build —
`plugin_root.py`'s own docstring already documents `PLUGIN_ROOT` as
spoofable by "an unrelated ambient tool"), and `is_codex_runtime()` only
checks that `BUILD_MANIFEST.json` is *shaped* like a real build output, not
that it *is* one. A directory with a forged, correctly-shaped
`BUILD_MANIFEST.json` and an attacker-chosen `.codex-plugin/plugin.json`
would pass, and its `hooks` would be merged into the GLOBAL, cross-session
`~/.codex/hooks.json` — the first place in this codebase where a
`resolve_plugin_root()` value converts into unsandboxed, persistent code
execution rather than an inert config artifact (R1's plugin-bundled
`hooks.json` never executes at all; R1b is what makes it real).

**Decision: accept the risk. Do not fix it in this run, and no follow-up
sub-iterate is scoped for it.** The operator (Sven) made this call directly,
with the reasoning below — not a generic "acceptable risk" label, but the
actual analysis so a future reader does not have to re-derive it:

- **The precondition is narrow, and both branches of it are already
  sufficient.** Exploiting this requires the attacker to EITHER already run
  code on the operator's machine, OR control the specific env vars
  `sync_codex_hooks()` reads (without needing code execution — e.g. a
  malicious `.envrc`/shell-profile line, or a compromised build tool that
  exports `PLUGIN_ROOT`). Neither branch is exotic, but neither is free
  either: a purely passive vector — cloning or opening a malicious repo,
  with no script ever running — does NOT set these env vars or invoke this
  CLI by itself.
- **In the code-execution branch, this mechanism grants nothing
  incremental.** An attacker who can already run arbitrary code on the
  operator's machine has strictly simpler, better-established persistence
  mechanisms available (a startup-folder entry, a shell-profile line, a
  scheduled task/cron job) — none of which require a human to click through
  a trust dialog first. Closing this specific path would not meaningfully
  reduce that attacker's capability.
- **In the env-var-only branch (no code execution yet), impact is real but
  gated by a second, independent control.** Codex's own "Hooks need review"
  trust prompt (documented and empirically confirmed this same run, see
  Confidence Calibration in the iterate spec) sits between a merged
  `hooks.json` entry and its first execution — an operator who reviews that
  prompt before trusting has a genuine second chance to catch an
  unrecognized command. The risk is real specifically when the operator
  blindly trusts without reading it, and hook commands then run unsandboxed
  once trusted — so impact is HIGH conditional on BOTH the narrow
  precondition being met AND the operator skipping that review.
- **What a real close would require, and why it is deliberately not built
  now:** resolving `bundle_root` via Codex's own plugin registry (a
  first-party, non-env-var-spoofable source of truth) instead of trusting
  the env-var chain at all. This is a materially different design — it was
  not evaluated or scoped as part of this run, and no follow-up sub-iterate
  has been opened for it. A future reader hitting this same class of finding
  should start there rather than re-inventing a signature/nonce scheme (see
  Rejected alternatives below, which the same reasoning already excludes).

**Mitigation added instead (cheap, not a close):** `codex_hooks_sync.py`'s
CLI wrapper (`main()`, not `sync_codex_hooks()` — that function's pure,
silently-callable, fully-test-covered contract is deliberately unchanged)
now prints the resolved `bundle_root` and a summary of exactly which hook
events/commands are about to be merged into `~/.codex/hooks.json`, and
requires an explicit interactive `y`/`N` confirmation before writing. `--yes`
skips it for scripted/test use; a future automated caller (R2's paused
terminal helper, if it resumes) should only pass `--yes` once it has
established equivalent trust some other way. This does not close the
authenticity gap above — it gives the operator one more chance to notice an
unexpected bundle path or an unfamiliar command before anything is written,
the same shape of control as Codex's own trust prompt one step later.

## Decision — bundle-root character validation (F11 preflight, second finding, 2026-09-22)

The re-run local PR-review preflight (after the Accepted Risk mitigation
above landed) raised a **distinct** BLOCK, not a re-surfacing of the round-2
`glm` LOW finding already dispositioned in the table above: that earlier
finding was about unescaped **bundle-command content** (`raw_command`,
first-party/trusted bundle text); this one is about `codex_hooks_launcher.py`
`_materialize()` splicing the **resolved `bundle_root` path** into the same
launcher-script body via `raw_command.replace(_PLACEHOLDER, str(bundle_root))`
without escaping. The two are not interchangeable: `bundle_root` is exactly
the value the Accepted Risk section above already documents as
env-var-spoofable, and unlike `raw_command`'s quoting (author-controlled,
consistent), the quoting context surrounding `${CLAUDE_PLUGIN_ROOT}` in any
given `raw_command` is not something this module can assume — a future hook
command need not wrap the placeholder in quotes at all.

**Fixed, not accepted** — this one has a clean, low-risk technical answer,
unlike the architectural bundle-root-authenticity gap: `_materialize()` now
validates `bundle_root` against a conservative path-safe character allowlist
(`_UNSAFE_BUNDLE_ROOT_RE` in `codex_hooks_launcher.py`) before any
substitution happens, raising `CodexHooksSyncError` — the same "surface
loudly" contract the rest of this module already commits to — rather than
attempting to escape for a quoting context that varies per hook command and
per platform (POSIX shell vs. `cmd.exe`, each with different unsafe
characters, some of which — like `cmd.exe`'s `%`/`^` — are genuinely hard to
escape correctly with confidence on a Windows-only development machine, the
same blind spot that let the POSIX mirror-bug through above). Real bundle
roots (plugin cache directories such as
`~/.claude/plugins/cache/shipwright/...`) never legitimately need
shell/cmd.exe metacharacters, so this validation is not expected to ever
fire in ordinary use — it converts an unreachable-in-practice but
theoretically-exploitable splice into a loud, safe refusal instead of a
silent or partially-escaped one.

## Rejected alternatives

Shape-checking `.codex-plugin/plugin.json` the same way as
`BUILD_MANIFEST.json` (would convert a genuinely-corrupted real bundle's
loud `CodexHooksSyncError` into a silent no-op — rejected after a stale
first-pass fix briefly did exactly this and broke
`test_malformed_bundle_plugin_json_raises`). Escaping/validating `cmd.exe`
metacharacters in launcher bodies (disproportionate given the existing
first-party bundle-content trust boundary). A per-launch secret/nonce or
cryptographic bundle signature for `is_codex_runtime()` (same
disproportionality — the marker-shape check closes the cheap-spoof case
the reviews actually raised).

## Review history

Internal cascade: `self` completed (8-item checklist, pass/n-a). `spec`
completed — first pass REJECT (a genuine race against my own concurrent
spec edits, not a real divergence), second pass PASS after the spec was
settled. `doubt` completed, 4 findings (1 high — unlink-loop exception
handling, already wrapped; 1 medium — empty-bundle guard, already present
via `--allow-empty`; 2 low — accepted/documented). `code` completed —
first two passes raced this run's own concurrent POSIX-fix edits and
produced stale findings against intermediate tree states (verified false
by directly running the full test suite before the third pass was even
spawned); third pass, tree fully settled: clean, 2 low non-blocking nits
(see `code_review_reply.json`). `external_code` completed — two rounds,
both legs each round; round 1 both `revise` (HIGH POSIX bug + convergent
mediums, all fixed); round 2 both `revise` (remaining findings per the
table above — all fixed or dispositioned with reason). `plan_internal`
not_run — this sub-iterate's design was driven by live empirical probing
against the real Codex CLI rather than the standard planning ceremony; the
`plan` external review (14 findings, addressed in the iterate spec's Design
Notes) and the full internal review cascade substitute for it.

Full detail — the raw review payloads, the complete Test Completeness
Ledger, AC1–AC6 verification — is in the iterate spec itself,
`.shipwright/planning/iterate/2026-09-22-r1b-codex-hooks-config-layer-shim.md`,
committed as part of this same PR.
