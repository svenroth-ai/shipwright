# Iterate: the sweep silently eats operator dismisses (main-tree drift + orphan quarantine)

- **Run ID:** iterate-2026-07-14-sweep-drift-dismiss-loss
- **Intent:** BUG (Path C — root cause before fix)
- **Complexity:** medium
- **Spec Impact:** NONE — a bug fix restores intended behavior; no product FR is touched (framework-internal delivery machinery). Architecture impact IS component-level: new modules + a new write surface (main's tracked triage log).
- **Reported:** reproduced live in shipwright-webui, 2026-07-14 (trg-6db81c59, trg-6e048260)

## Symptom

A triage item kept resurfacing on the Command Center board after every dismiss.
The operator dismissed it, the sweep ran, the dismiss vanished, the item came back.
`triage.outbox.quarantine.jsonl` recorded the same dismiss eaten repeatedly
(trg-6db81c59 2x, trg-6e048260 4x) with
`reason: "orphan-status: no append anywhere in the combined triage log"`.

## Root cause (two defects that compound)

**Defect A — a tracked-on-main append is delivered by nothing.**
`sweep_outbox_to_branch()` folds ONLY the gitignored outbox into the iterate
branch. An append that lands in main's TRACKED `.shipwright/triage.jsonl` while
it is still uncommitted is picked up by no producer, no sweep, no reconcile:
`reconcile_main_triage()` survives only as a manual operator CLI ("neither
`setup` nor `integrate_main` calls this anymore" — its own docstring). The
append rots in the working tree, invisible to `origin` and to every worktree.
In webui both appends existed in NO git object — not `origin/main`, not `HEAD`,
not the outbox — only as `M .shipwright/triage.jsonl`.

**Defect B — the orphan check's universe is too small.**
`sweep_quarantine.decide(worktree_lines, outbox_lines, eol)` classifies over
worktree-tracked ∪ outbox only. It never sees main's tracked log, even though
`sweep_outbox_to_branch()` already holds `main_root`. So a `status` event for a
drift-only append MUST look like an orphan. It is quarantined AND deleted from
the outbox (the `if gc_dropped or quarantined:` rewrite), and the sweep returns
`committed`. `setup_iterate_worktree.py` only warns on `invalid | error |
skipped`, so `SweepResult.quarantined` never reaches the operator.

**The loop.** The WebUI reader unions local-tracked (which HAS the drift append)
∪ origin ∪ outbox. Append present, dismiss quarantined away → the item falls back
to `triage` → it reappears → the operator dismisses again → the next sweep eats it
again. Forever. The #303 quarantine mechanism converted a loud hard-block into
quiet data loss.

## Acceptance Criteria

- **AC1** `decide()` takes a third, read-only `known_append_ids` universe. A
  `status` whose append is known from main's tracked log is NOT an orphan and is
  never a quarantine candidate.
- **AC2** When such a protected status cannot be validated (its append is known
  but could not be placed in the materialized log), the sweep FAILS CLOSED —
  `block`, loud — instead of quarantining. A hard stop beats silent data loss.
- **AC3** The sweep detects append-only drift in main's tracked log and routes
  those lines into the OUTBOX (the real delivery channel), then restores the
  tracked file to its HEAD lines. The drift then rides the iterate PR to origin.
- **AC4** Refusal guards: the repair mutates NOTHING unless it fully understands
  main's state. It refuses (`skipped: main_tracked_*`, nothing touched) when the
  working log is not an append-only **prefix-extension** of HEAD (removed, edited —
  incl. whitespace-only — reordered, emptied or deleted lines), when the triage log
  has a **staged** delta (restoring the working file alone would leave the drift in
  the index), when a drift line is **not a well-formed producer event**, or when
  HEAD/the file **moved mid-repair**. Distinct from that: a state we understand but
  cannot repair (no HEAD blob to restore to — e.g. local main is behind origin) is
  `unrepairable` and must NOT block delivery; refusing there would strand every
  pending append and trade one delivery failure for another.
- **AC5** `setup_iterate_worktree` surfaces the quarantine count and the adopted-
  drift count on stderr and in `warnings[]`. A quarantine is never silent again.
- **AC6** Regression coverage for the exact webui shape: a drift append on main +
  an operator dismiss in the outbox → after the sweep the dismiss is DELIVERED on
  the branch (the reader resolves the item to `dismissed`) and the quarantine log
  is empty.

## Affected Boundaries

- `.shipwright/triage.jsonl` (tracked, main-tree working copy ↔ HEAD blob)
- `.shipwright/triage.outbox.jsonl` (gitignored delivery buffer)
- `.shipwright/triage.outbox.quarantine.jsonl` (operator-review buffer)
- git: `HEAD:<triage>` and `origin/<default>:<triage>` blobs

## Design

New leaf module `lib/sweep_text.py` (normalize/read helpers, shared without a
cycle) and `lib/sweep_drift.py` (`adopt_main_tracked_drift` + `append_ids_of`).
`sweep_outbox_to_branch()` runs adoption INSIDE the existing `_FileLock`, before
it reads the outbox, so the drift is delivered in the same critical section that
folds it — no read-then-lost window. `decide()` gains the `known_append_ids`
parameter (defaulted, so existing callers/tests are unchanged).

**Rejected alternative:** keep the orphan status in the outbox until its append is
origin-delivered. That re-creates the #303 hard-block — the materialized log keeps
failing validation on every sweep, stranding every other pending append. Repairing
the APPEND side is what actually dissolves the orphan.

**Crash-safety.** The outbox write is durable and lands FIRST; the tracked-log restore
second. An interruption between them leaves the drift in both places, which is harmless:
adoption dedups candidates against the outbox, so the replay adds nothing and simply
completes the restore. Never the other order (that one loses data).

### What the reviews changed

The external plan review (GPT-5.4 + Gemini 3.1 Pro) and the external code review
reshaped the guards; every finding below is covered by a regression test:

- **Prefix, not set-difference** (GPT): "append-only" means the working log STARTS WITH
  HEAD's exact line sequence. A set test would wave through reordered, edited and
  duplicated lines.
- **Verbatim, not stripped** (GPT): comparing/restoring stripped lines would accept a
  whitespace-only edit to a HEAD line and silently normalize it away.
- **Empty/deleted is the severest divergence** (GPT): the HEAD blob is read BEFORE the
  empty-file shortcut, else the sweep proceeds over a state it never compared.
- **Staged index** (GPT): restoring only the working file would leave the drift in the
  index, and main's next commit would re-introduce it.
- **Validate before rewriting** (GPT): malformed drift would poison the outbox AND hide
  its source. Nothing is moved unless every drift line is a producer event.
- **Race re-check** (GPT/Gemini): a process lock cannot stop an external `git commit` or
  an editor, so HEAD and the file bytes are re-read immediately before the restore.
- **One new module, not two** (Gemini): the text helpers live in `sweep_drift.py`; a
  separate `sweep_text.py` leaf was over-abstraction for three functions.
- **`unrepairable` ≠ `refused`** (self-review): the first draft refused a no-HEAD-blob
  repo, which would have SKIPPED the whole sweep and stranded every pending append —
  swapping one delivery bug for another.

## Confidence Calibration

- **Boundaries touched:** main-tracked triage log (working copy vs HEAD blob),
  the gitignored outbox, the quarantine log, `origin/<default>` GC membership.
- **Empirical probes run:**
  - Probe 1 — replayed the webui shape end-to-end through the REAL
    `setup_iterate_worktree.py` CLI on a scratch git repo
    (`scripts/verify_sweep_delivery_surface.py`): before the fix the dismiss is
    quarantined and lost; after the fix `read_all_items()` on the branch resolves
    the item to `dismissed`, quarantine log empty. Finding: the loop reproduces
    and the fix closes it at the real entry point, not just in a unit.
  - Probe 2 — divergence guard against a real repo with a HEAD line deleted from
    main's working log: sweep returns `skipped: main_tracked_diverged`, and the
    tracked log + outbox are byte-identical afterwards. Finding: the repair never
    rewrites a file whose state it does not understand.
  - Probe 3 — CRLF main-tracked log (a real autocrlf checkout, written by git itself):
    after adoption `git status --porcelain -- <triage>` is empty. Finding: the EOL
    round-trip does not manufacture spurious drift. (A hand-written CRLF file is
    genuinely modified to git and proves nothing — the first draft of this probe was
    invalid and was rebuilt.)
  - Probe 4 — RED-proof: with the adoption call stubbed out, the two headline tests
    FAIL exactly as webui behaved (`no_change`, dismiss quarantined, sweep reports
    success). Finding: the tests pin the defect, they do not merely describe it.
- **Test Completeness Ledger:** see `shipwright_test_results.json`
  (`iterate_latest.test_completeness`) — every AC → `tested`, 0 untested-testable.
- **Confidence-pattern check:** asymptote — the failing test was written FIRST and
  reproduces the eaten dismiss (red → green). Coverage — unit (`decide` universe),
  component (sweep against real git), and surface (real CLI, reader-resolved
  status) all exercise the same defect from different altitudes.

## Follow-up (deferred, out of scope)

The sweep/delivery modules match no `cross_component` risk pattern, so no
integration-coverage gate fires when they change — part of why this shipped.
Registering `sweep_*.py` in `CROSS_COMPONENT_FILE_PATTERNS` is a policy change
with doc/matrix impact; filed as a triage item rather than folded in here.
