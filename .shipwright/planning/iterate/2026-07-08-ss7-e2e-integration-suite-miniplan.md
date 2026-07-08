# Mini-Plan — SS7 E2E integration capstone

## Chosen approach

Two new, self-contained integration files under `integration-tests/`, each
`category:"integration"`, each <300 LOC, driving the **real orchestrator
subprocess CLI** (the same surface the master/Stop-hook invoke) — no mocks:

1. `test_single_session_capstone.py` — the single-session story end-to-end:
   full pipeline + build fan-out walked **through** a human-gate pause→resume
   (A), with the section-writer persistence regression **threaded into** the plan
   phase; plus the surface-agnostic **parity** proof (B).
2. `test_cross_surface_backcompat.py` — the default-path guarantees: an in-flight
   **multi_session** run survives a crash and is re-claimed + completed with **no
   single-session file leak** (C); plus a thin **external_review** loud-fail roster
   pin (D, deep owner = SS6).

Then register **SS8** (WebUI Playwright cross-surface E2E, `shipwright-webui`,
prereq S1b) in the gitignored campaign dir.

## Why this shape

- **Threads, not duplicates.** The section-writer regression is proven *inside*
  the live pipeline walk (net-new) rather than re-copying SS3's isolated guard
  test. The external_review pin is a thin contract guard pointing at SS6's deep
  coverage. Honors Sven's "thread + thin-guard" choice and YAGNI.
- **Two cohesive files, not one fat file or five fragments.** Single-session story
  vs default-path/back-compat are two distinct concerns → two files; keeps each
  under the 300-LOC ceiling and readable as one narrative each.
- **Real subprocess surface.** Parity and "CLI ≡ WebUI" are only honest if driven
  through the exact CLI both surfaces call.

## Alternative considered — rejected

- **One fat capstone file re-implementing full-pipeline + fan-out + strict-stop
  from scratch.** Rejected: duplicates green SS3 coverage, blows the 300-LOC
  ceiling, and buys nothing (YAGNI / anti-bloat). SS7 references SS3/SS5/SS6 and
  adds only net-new proofs.
- **Extract shared single-session CLI helpers into conftest and refactor SS3/SS5
  to use them.** Rejected for this iterate: touches green tests, widens scope
  beyond the capstone (Surgical-Changes). The per-file-helper convention is the
  established norm here; a de-dup pass is a separate cleanup iterate if wanted.

## Risk / rollback

- Test-only diff; no production surface. Rollback = revert the PR.
- If scenario **C** (multi_session re-claim + complete) reveals the positive path
  does *not* work, that is a real back-compat bug → stop, root-cause, fix under
  the constitution (would upgrade Spec Impact to MODIFY on production code).
