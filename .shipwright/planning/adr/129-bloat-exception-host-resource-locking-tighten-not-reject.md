# ADR-129: Bloat exception — `shared/scripts/lib/_host_resource_locking.py` raised to 308-LOC

- **Status:** accepted
- **Date:** 2026-09-05
- **Re-Review-Date:** 2026-12-05
- **Incident Reference:** `iterate-2026-09-03-review-scratch-path` PR #676,
  round-13 CI failure (`Python (lint + test)`, run 33929960597) — the first
  time this module's POSIX permission checks ran anywhere but a Windows job.

## Context

`_safe_file`/`_safe_dir` (the private-root hardening `review_scratch.py`
reuses from `host_resource_lease.py`) reject any existing file or directory
whose POSIX mode carries group/other bits, on the theory that a private
lease path must never be world- or group-readable. That check is right for
paths *this module itself creates* (it already `chmod(0o700)`s a directory
it just made) but wrong for paths a **caller** creates through its own I/O:
`iteration-reviews.md` Branch A does `git diff HEAD > "$DIFF_FILE"`, a plain
bash redirect that honors the process umask (typically 022 → mode 644), not
this module's threat model. `resolve()` is then called a **second** time
from the Python read site — that is the documented contract, "both the bash
write site and the python read site call it independently and land on the
identical path" — and the second call's `_safe_file` rejected the very file
the first call's contract expects to exist.

This was invisible locally and in the Windows CI job: `os.name == "nt"`
skips this whole branch in favor of `_windows_private` (an ACL check with
different semantics). PR #676 merged with this defect live on `main` for a
few minutes before the Linux `Python (lint + test)` Required Check reported
it — three tests failed with `HostLeaseError: host lease file/directory is
not private`, reproducing exactly the round-trip pattern described above.
This is not a test-only artifact: the identical failure would have hit the
real `iteration-reviews.md`/`sub-iterate-runner.md` pipeline on any Linux or
macOS contributor host, silently breaking every external code review this PR
exists to make reliable.

## Ousterhout Argument

The fix is narrow and stays inside the module's existing interface: neither
`_safe_file` nor `_safe_dir` changes its signature or its callers' contract.
What changes is the *response* to one specific, previously-unreached state
(mode bits loose, ownership trusted) — from "reject" to "tighten," via one
new private helper (`_tighten`, 8 lines) shared by both call sites so the
fix is not duplicated. Ownership was always the real trust boundary here
(the file's own docstring: "the private, ACL-hardened root defends against
another OS user planting a reparse point here"); the mode-bit check was
only ever a proxy for "did something outside our control touch this," and
tightening is the correct response to that state, not rejection.

## YAGNI Check

No new responsibility was added. The module still does exactly what it did
— validate a path is safe before a caller reads/writes/removes it — for
exactly the same three primitives (`_safe_file`, `_safe_runtime_root`,
`_safe_dir`). The change corrects the POSIX branch's behavior at one
already-existing decision point per primitive; nothing speculative was
introduced (no new path kinds, no new callers, no new config).

## Chesterton-Fence Check

The reject-on-loose-bits behavior was not a documented, deliberate fence —
it was an oversight: the module's own tests (`test_review_scratch.py`) only
ever exercised the round-trip pattern on Windows-shaped CI, so the gap
between "we created it" (already tightened) and "a caller created it, we
inspect it" (never tightened) was never exercised on POSIX until this PR's
own Linux CI run. No prior ADR or comment defended the reject behavior on
its own terms; the file's docstring already states the intended trust
boundary is ownership, which the reject behavior did not actually implement
consistently. Torn down, not exception-allowed.

## Decision

Raise `current` for `shared/scripts/lib/_host_resource_locking.py` from
**298 to 308**, `state: "exception"`, `adr: "ADR-129"`, in the same commit
as the fix.

## Consequences

- `_safe_file`/`_safe_dir` now silently tighten a loose-but-owned path to
  `0o600`/`0o700` instead of raising `HostLeaseError`. A path owned by
  another user is still a hard reject — that boundary is unchanged.
- The round-trip contract `review_scratch.py`'s own docstring describes
  (bash writes, Python reads, both via independent `resolve()` calls) is now
  actually exercised end-to-end by `test_resolve_round_trips_content` and
  `test_resolve_survives_a_space_in_the_temp_root` on every OS CI runs on,
  not just Windows.
- If a future primitive needs a *third* mode-bit response (neither tighten
  nor reject), `_tighten`'s two call sites are the place to look — it is not
  yet generalized beyond "chmod or raise."

## Rejected alternatives

- **Compress comments/whitespace elsewhere in the file to stay under 300.**
  Attempted first: consolidating the two duplicated tighten-or-raise blocks
  into the shared `_tighten` helper already recovered 8 of the 18 lines the
  naive fix would have cost (316 → 308). Compressing further would mean
  cutting the docstrings that explain *why* ownership is the boundary — the
  exact context a future reader needs to avoid re-introducing the reject
  behavior. Rejected on the same reasoning as ADR-119's "shallow refactor"
  rejection: the explanation cannot be cut to zero lines.
- **Split the module instead of exceeding 300.** The three primitives
  (`_safe_file`, `_safe_runtime_root`, `_safe_dir`) share the reparse-point
  and ownership-check idioms tightly enough that splitting them into
  separate files would either duplicate those idioms or introduce a shared
  sub-helper module for a net gain of essentially zero lines, while
  scattering one coherent security primitive across multiple files makes it
  harder, not easier, to audit as a unit — the opposite of what a
  correctness-sensitive module wants.
