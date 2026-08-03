# Iterate Spec: serialize ensure_shared_cache SessionStart fan-out

- **Run ID:** iterate-2026-08-02-ensure-shared-cache-fanout
- **Type:** change
- **Complexity:** medium
- **Status:** implemented
- **Risk flags:** `cross_component`, `touches_io_boundary`
- **Approval:** the operator requested an autonomous iterate with the implementation direction and constraints in the launch card.

## Goal

Serialize and coalesce the vendored `ensure_shared_cache` SessionStart work while
preserving its stdlib-only, fail-open bootstrap contract. All losing hook
wrapper processes must either observe the winning healer's completion before
running their plugin's ordered SessionStart targets, or skip those dependent
targets safely when a bounded live-owner wait expires.

## Acceptance Criteria

- [x] **AC1:** Given 12 normally co-scheduled hook invocations with one real `session_id`, one invocation performs the completeness scans and any repair; the others return only after the winner publishes completion. A participant delayed beyond the bounded cohort window may trigger only a serialized successor scan, never an overlapping scanner or copier.
- [x] **AC2:** Given a healthy cache and the normal concurrent cohort, the 12-process fan-out performs one four-tree completeness check and zero copies rather than 12 checks. Because the payload has no event-unique field, safety takes priority for an ambiguous late participant: it may add a sequential recheck instead of trusting a possibly stale completion.
- [x] **AC3:** Given a missing or malformed session id or unreadable coordination location, the guard fails open into the old healer. Given a dead or delayed claim owner, a timeout claimant recovers the same token only while holding the process-bound cache-global writer lease; SessionStart exits 0 without overlapping a copier. If a live owner exceeds the bounded wait, later cache-dependent commands in the losing plugin chain are skipped rather than opened early.
- [x] **AC4:** Given a running claim from another process, a loser never reclaims it merely because time elapsed. An expired completed generation advances through an immutable token-derived successor claim and a new O_EXCL election; no shared claim pathname is deleted or replaced.
- [x] **AC5:** Given a repair is required within the combined healer-and-ready-guard wait budget, the real 12-process hook composition leaves both `shared/` and the cross-plugin mirror complete before every wrapper runs its ordered consumers. Given a repair that exceeds every bounded wait, incomplete losing chains exit 0 without opening any consumer target.
- [x] **AC6:** The canonical healer, lock helper, and ready guard remain byte-identical across all 12 vendored copies; each plugin registers exactly one ready-guard SessionStart command containing all former targets in their original order.

## Spec Impact

- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** this changes framework-internal SessionStart coordination and cache-repair safety/performance; no product capability or FR guarantee changes.

## Out of Scope

- Detecting present-but-truncated cache files; the healer remains presence-only and the CRLF-normalizing drift checker owns content staleness.
- Replacing the symmetric register-everywhere hook model with one controlling plugin.
- Importing `shared/scripts/lib/event_once.py`; the bootstrap must still work while `shared/` is absent.
- Changing cache manager ownership or plugin installation layout.
- Claiming deterministic exactly-once scans for arbitrarily delayed processes when two distinct SessionStart events carry byte-identical payloads; Claude exposes no event-unique payload field for that distinction.

## Design Notes

No UI surface. Reproduce the existing `event_once` O_EXCL first-wins pattern
inside the canonical stdlib-only hook. The common coordination directory lives
under the cache marketplace root, outside both repaired destinations, and is
created owner-only where supported. A bounded SHA-256 digest of immutable
SessionStart stdin values (raw `session_id`, `source`, and transcript path), encoded
as ASCII-safe canonical JSON, names the claim; no process stats a live,
payload-controlled path. A random
per-election token fences ownership. The
claim generation is immutable after creation. Completion is a distinct,
token-specific O_EXCL sentinel, never a truncate/rewrite. Losers poll for that
exact sentinel. An expired completed generation points to an immutable successor
pathname; this removes stale-delete ABA races and transitional rearm locks. A
hashed participant marker records each plugin's single consolidated wrapper
while the generation runs. The wrapper uses `plugin:sessionstart`; an existing
marker or first arrival after completion advances the successor without waiting
for TTL expiry. Its fixed-size filename hashes the immutable generation name and
participant together, avoiding Windows path-length amplification without
putting raw identity text in a pathname. There are no separate standalone and target processes whose
causal relationship would have to be inferred from a byte-identical payload. A
100 ms owner join window keeps the normal 12-wrapper fan-out to one scan. Claim tokens
are read through one nonblocking/no-follow descriptor whose regular-file type
and pathname identity are validated before the bounded read. A running claim is
never declared stale from elapsed time alone. Every actual scan
or copy also holds a cache-global OS file lease directly under the stable
marketplace cache root, outside the replaceable claim directory, so different session ids cannot
mutate the shared destinations together and a killed process releases recovery
automatically. A bounded session-claim timeout recovers that token under the
global lease, whose own wait is bounded to five monotonic seconds; malformed identity or session-claim I/O failure uses the old
fail-open path but still requires the same global lease. If the global lease
itself is unavailable, the hook exits 0 with a warning and performs no scan or
mutation. Each manifest exposes only the separately vendored stdlib
`run_if_cache_ready.py` wrapper. It joins the healer election once, then polls up
to ten seconds for the completed claim tip without holding a reader lease. It
re-arms a repeated identical payload through its own stable plugin participant.
It then requires one shared reader lease while it runs every former SessionStart
target sequentially in manifest order. Their schema-valid `additionalContext`
values are combined into one SessionStart JSON envelope; invalid target stdout
is warned and omitted. Concurrent plugin readers remain parallel, while a writer
cannot enter between validation and any import. Otherwise the wrapper warns and
skips all targets with exit 0.
Completion is published only after a post-repair check succeeds. That check
requires its enumerable same-marketplace authoritative source for existing `shared/`, and accepts
a plugin-mirror symlink only when it resolves exactly to the selected installed
version. Keep the canonical hook at or below 300 lines; its plugin-local stdlib
lock helper remains separately testable.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| Claude Code SessionStart payload | `run_if_cache_ready.main` → `ensure_shared_cache.main` → ordered target hooks | JSON object containing immutable `session_id`, `source`, and `transcript_path` values; target `additionalContext` values are merged into one SessionStart envelope |
| Winning vendored wrapper/healer process | Losing wrapper participants | immutable O_EXCL claim containing an ownership token, a token-specific completion sentinel, and hashed per-plugin observation markers; session filename is a bounded SHA-256 digest |
| Marketplace clone / installed version dirs | cached `shared/` and `plugins/` trees | filesystem file-set overlay (existing boundary, coordination changes only) |

## Confidence Calibration

- **Boundaries touched:** SessionStart JSON → session key; winner → claim state → waiters; repair sources → cache trees.
- **Empirical probes run:** real 12-process healthy, repair, delayed-owner, source-transition, guard-first, expired-generation, and cross-session compositions; isolated Windows reader/writer lease probes; canonical/vendor parity and exact manifest-token gates.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | One winner and eleven waiters for one session | tested | `test_ensure_shared_cache_fanout.py`; `integration-tests/test_ensure_shared_cache_fanout.py` |
  | 2 | Waiters return only after winner completion | tested | token-specific completion and successor-election ordering tests |
  | 3 | Healthy fan-out scans once and copies zero files | tested | real-process PID trace asserts exactly one scanner and zero copies |
  | 4 | Missing session id and guard I/O errors fail open | tested | malformed-identity, unavailable-lock, and fallback-readiness tests |
  | 5 | Completed expired claim is reclaimable; a running claim is never time-reclaimed | tested | deterministic TTL, future-mtime, live-owner, and fenced-successor tests |
| 6 | Real 12-process repair composes with both cache trees and immediate consumers | tested | `category: integration`; 21 real subprocess scenarios pass, including ordered multi-target aggregation and malformed-output continuation |
  | 7 | Canonical and 12 vendored copies stay identical/consolidated | tested | byte-parity plus exact sole-command `uv run` token-shape and path-existence gates |
  | 8 | Observation markers remain generation- and participant-specific without amplifying Windows path length | tested | bounded marker-name regression; focused and full integration suites pass under eight xdist workers |
  | 9 | Replacing the claim directory cannot split the global reader/writer lease | tested | deterministic real-directory replacement plus symlink-redirection regression |

- **Confidence-pattern check:** complete; 9 testable behaviors tested, 0 untested-testable, with concurrency, source-authority, path-length, parent-replacement, and manifest-bypass mutations exercised.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run --python 3.11 --with pytest --with pytest-mock --with pytest-xdist pytest integration-tests/test_ensure_shared_cache_fanout.py -q -p no:cacheprovider -n 8`
- **Evidence path:** `.shipwright/runs/iterate-2026-08-02-ensure-shared-cache-fanout/surface_verification.json`
- **Fresh F0:** the canonical aggregate process was KeyboardInterrupted, so the 18 pytest roots were rerun separately on Python 3.11. The plugin/shared/script roots passed 12,916 of 12,963 tests with 47 skips; full integration passed 465/465. The large Shared root used four disjoint same-root shards, plus the final marker, exact-manifest, and root-lock regressions were rerun directly.

## External Plan Review

OpenRouter ran two reviewers; both returned `revise`. Accepted changes:

- Never reclaim a running owner from wall-clock age; TTL applies only after token-specific completion is visible.
- Fence every election with a unique token so an old owner cannot publish completion for a new one.
- Publish completion through a separate atomic sentinel, never by rewriting the claim.
- Hash the raw session id to a bounded filename and keep coordination outside both repaired trees.
- Make ambiguous coordination failure explicitly fail-open rather than pretending exclusivity still holds.
- Extend the 12-process integration scenario through the next consumer/import step and include both unit and integration suites in targeted evidence.

The stdin concern is already answered by the hook contract and existing fan-out
integration harness: Claude supplies the SessionStart payload independently to
each command invocation; the new test preserves that shape. The review's
suggested heartbeat is unnecessary after removing time-based takeover of a
running claim.

## Doubt-Review Dispositions

| Doubt | Disposition |
|---|---|
| Completion published after a failed/unknown repair | **accepted-and-fixed** — a second completeness pass gates the done sentinel; incomplete repair logs and leaves the running generation without a false completion. |
| Five-second timeout recreates parallel copying / dead owner cannot recover | **accepted-and-fixed** — a timeout claimant recovers the observed token only after acquiring the process-bound cache-global writer lease; a killed owner releases that lease automatically, while a live owner finishes before the recovery claimant can scan. |
| Crash while holding `.rearm` permanently breaks coordination | **accepted-and-fixed** — the mutable rearm transition was removed; expired completed generations advance through immutable token-derived `.next` claims. |
| Claim, completion, and participant files accumulate | **acknowledged, non-blocking** — files are tiny cache metadata and are removed with the marketplace cache; concurrent in-hook deletion would reintroduce the ABA class this change closes. Bounded in-place GC is intentionally deferred to cache-manager/consolidation work and is declared in the hook documentation. |
| Mixed old/new plugin versions ignore the protocol | **rebutted by rollout contract** — source parity cannot modify already-installed old hooks. Local deployment updates all plugin caches in one `update-marketplace.sh` run; marketplace users update the full plugin set before the documented session restart. The docs now state that restarting mid-update is unsupported because old hooks cannot participate. |
| Different session ids elect concurrent cache writers | **accepted-and-fixed** — the session claim deduplicates one fan-out while the separate cache-global OS lease serializes the shared destination across sessions; a delayed-copy two-session subprocess test proves one writer and ready consumers. |
| Live hung lease owner blocks all sessions forever | **accepted-and-fixed** — both msvcrt and fcntl acquisition poll non-blockingly against a five-second monotonic deadline; expiry returns the warning/exit-0/no-mutation path. |
| Over-budget live owner lets a losing chain import before completion | **accepted-and-fixed** — each plugin has one stdlib ready wrapper. It requires the completed claim tip (or a read-only complete-cache fallback for malformed coordination) and holds a shared reader lease throughout all ordered targets; otherwise every target is skipped with exit 0. The real-process probe delays the winning copy for 11 seconds and proves the loser waits, then opens its consumer only after the winner completes. A separately held incomplete writer proves the skip path never opens the consumer. |
| Writer enters between ready check and target import | **accepted-and-fixed** — the guard no longer releases before launch. POSIX uses `flock(LOCK_SH)` and Windows allocates one of 64 reader bytes while the writer covers the whole range. A real subprocess target holds the reader lease for two seconds and a competing writer probe is refused throughout. |
| Guard launches before its healer and skips a fast successful repair | **accepted-and-fixed by consolidation** — there is no separate healer command. The sole wrapper joins the election and invokes the local healer in-process before it can open any target. |
| Guard accepts an expired done generation before the healer advances it | **accepted-and-fixed** — completion validity and healer advancement now share `CLAIM_TTL_SECONDS` from the local helper. A real resumed-session probe ages the old `.done`, reaps two shared targets, launches the guard first, then proves the successor healer repairs and completes before the consumer opens. |
| Fresh done masks a later source transition during the 30-second TTL | **accepted-and-fixed** — the claim digest includes the official SessionStart `source`; a real startup-to-resume probe keeps the session id, reaps cached dependencies while the startup done is fresh, then proves the resume healer repairs before the guard opens its consumer. Live transcript metadata is deliberately excluded because parallel processes cannot snapshot it consistently. |
| Fresh done masks a repeated identical payload inside the TTL | **accepted-and-fixed** — every generation records immutable hashed wrapper-participant markers. A plugin wrapper already present on the completed tip advances one immutable successor, while wrappers registered during the running cohort observe it. A real regression warms completion, removes late shared and mirror dependencies, repeats the identical payload, and proves repair precedes the consumer. |
| Claim/successor validation can be swapped to a symlink or FIFO between `lstat` and `read_text` | **accepted-and-fixed** — tokens are opened once with nonblocking/no-follow flags, descriptor and pathname are verified as the same regular file, and the bounded token is read from that descriptor. POSIX swap and FIFO regressions prove no follow and no hang; unsupported Windows symlink creation is skipped rather than simulated. |
| A malformed global lock path can be followed and mutated before locking | **accepted-and-fixed** — the opened lock descriptor and final pathname must identify the same regular file before Windows sizing or either platform's lock call. A cross-platform symlink regression proves the external target remains byte-identical. |
| A hard-linked lock path can mutate an external regular file | **accepted-and-fixed** — descriptor/path validation additionally requires exactly one link before any sizing, write, or lock. A real hard-link regression proves acquisition fails and the external target remains byte-identical. |
| A participant absent from generation N can trust N's stale completion | **accepted-and-fixed** — each plugin has exactly one wrapper participant. Markers created while the generation runs belong to that cohort; an already-present participant or first arrival after completion advances the successor. The owner grants a bounded 100 ms join window to preserve one normal fan-out scan. A real regression completes N without participant B, reaps late dependencies, invokes B first with the identical payload, and proves repair precedes consumption. |
| A retained standalone marker plus a never-used target ticket can authorize a later identical event | **accepted-and-fixed by process consolidation** — standalone and per-target processes/tickets were removed. Each plugin's sole wrapper participates once, then runs all targets in order under one reader lease, so no unused target authorization can survive into another event. |

## External Code Review

**Review-payload note:** The actual worktree and eventual commit contain all 36
plugin-local hook bodies: `ensure_shared_cache.py`, `cache_repair_lock.py`, and
`run_if_cache_ready.py` in each of the 12 hook-bearing plugins. To stay within
OpenRouter response limits, the final external-review diff retains the three
canonical files, one representative manifest, and
`test_ensure_shared_cache_vendored.py`; it omits only the byte-identical plugin
bodies, 11 structurally identical manifests, and large already-green test
harnesses. The vendoring test passes and checks canonical + 12 copies in both
directions; the final explicit affected-shared run is 245 tests passed with eight
platform-specific skips, plus 21 integration scenarios passed. This is payload
compression, not a delivery exclusion.

OpenRouter ran Gemini and OpenAI reviewers. Gemini approved; OpenAI returned two
medium findings, both accepted and fixed: completed-generation TTL now measures
the `.done` sentinel rather than the older claim, and the real healthy/repair
fan-outs trace completeness-walk entry by PID and assert exactly one scanner.

A later final-diff round returned two further actionable points, both accepted:
future `.done` mtimes now count as expired rather than remaining fresh forever,
and the concurrent successor-election test now proves one O_EXCL owner returns
before its peer, then proves the peer observes completion and returns `False`.
Gemini's claim that a lock timeout escapes was rebutted from code and empirical
evidence: Python `TimeoutError` subclasses `OSError`, the enclosing handler
returns `None`, and the held-writer subprocess test exits 0 without mutation.

The next independent round found three readiness/identity gaps, all accepted:
completion is now withheld when existing `shared/` has no same-marketplace authoritative source,
plugin symlinks must resolve exactly to the selected installed version, and the
canonical event tuple preserves whitespace in otherwise valid raw session IDs.
Unit and real guard probes cover all three boundaries.

A later OpenRouter pass found that restoring an absent `shared/` from a foreign
marketplace could still publish completion. The foreign copy remains an emergency
repair source, but readiness is now revalidated only against the enumerable
same-marketplace authority. Final internal review then hardened the manifest gate
against reversed, targetless, multi-group, wrong-path, and non-executing command
shapes by pinning the complete `uv run` token chain.

The final full-diff OpenRouter pass found two more safety gaps, both accepted and
fixed. A valid coordinated event now distinguishes readable-but-pending (`False`)
from unsafe/unreadable coordination (`None`): only the latter may use the locked
complete-cache fallback, so an incomplete or expired live generation can never be
bypassed. Claim, successor, and completion metadata are now inspected with
single-descriptor nonblocking/no-follow reads plus descriptor/path identity
validation; the global lease receives the same validation before mutation or
locking. Participant markers close the fresh-done/identical-payload window, and
the real fan-out integration surface now passes 19 scenarios.

The final approved compact OpenRouter round returned two medium findings, both
accepted and fixed. Completion freshness now comes from `fstat()` on the same
nonblocking/no-follow, single-link, path-identity-validated descriptor instead
of an `lstat()` pathname snapshot. The real healthy 12-process harness now traces
every `shutil.copytree` call and asserts the trace file is absent, proving zero
copies rather than inferring it from the healer's log message.

The final consolidated-diff round followed the accepted doubt-review redesign:
all standalone/per-target processes and their ambiguous cross-event tickets were
replaced by one wrapper participant per plugin, with ordered multi-target JSON
aggregation under one reader lease. OpenAI returned `approve` / `ship-as-is`
with no concrete defect. Gemini's response hit its length limit and was recorded
as unavailable rather than treated as a verdict; there was no contradictory
completed review.

F0 then exposed a Windows-only path-length amplification in the observation
marker filename under xdist's deeper temporary directories. The marker now uses
a fixed 32-hex digest of `generation-name NUL participant`; all 12 vendored
copies match, the dedicated bounded-name regression passes, the 21-scenario
fan-out file passes with eight xdist workers, and the full 465-test integration
root is green. Final spec, code, and doubt re-reviews all returned PASS.

The post-F0 OpenRouter round raised three points. All were accepted and fixed:
the vendoring gate now pins each plugin's exact ordered target list with
omission/reorder/substitution mutations, and only the literal `unknown` sentinel
is rejected while padded raw identities remain distinct. The global reader/writer
lease now lives directly under the marketplace cache root rather than inside the
replaceable claim directory, so an ordinary concurrent claim-directory swap can
create at most a sequential extra election, never a second copier/reader lock
domain. Deterministic real-directory and symlink-directory regressions pin that
boundary; final-component symlink/hard-link/path-identity checks remain intact.
