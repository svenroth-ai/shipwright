# Mini-Plan: gc-decode-parity

- **Run ID:** iterate-2026-08-06-gc-decode-parity
- **Spec:** `.shipwright/planning/iterate/2026-08-06-gc-decode-parity.md`

## Files to create/modify

| File | Change | What |
|---|---|---|
| `shared/scripts/lib/git_base.py` | edit | Factor `run_git`'s Popen body into a private core parameterised on text-vs-bytes; add `run_git_bytes_soft` returning `CompletedProcess[bytes]`. `run_git` / `run_git_soft` signatures and semantics unchanged. |
| `shared/scripts/lib/sweep_text.py` | edit | Add `decode_store_text(data: bytes) -> str` — the single SSoT for how triage-store bytes become text. `read_text_verbatim` is rewired through it so there is literally one decode rule, not two that agree by convention. |
| `shared/scripts/lib/sweep_gc.py` | edit | `delivered_membership` reads the blob via `run_git_bytes_soft` + `decode_store_text`. |
| `shared/scripts/lib/sweep_drift.py` | edit | `_head_lines` likewise. |
| `shared/scripts/lib/reconcile_triage.py` | edit | `_head_line_set` likewise. |
| `shared/tests/test_store_decode_parity.py` | new | The seam itself + `decode_store_text` characterization (AC-2). |
| `shared/tests/test_sweep_store_decode_parity.py` | new | The three end-to-end consumer regressions + the Boundary Probe (AC-3, AC-4, AC-5). Split out of the module above at Stage-1 review: it crossed 300 lines, and it needs `$CI` unset (the sweep entry points no-op under CI) while the seam tests do not. |
| `shared/tests/test_git_base_bytes.py` | new | The primitive's own contract: bytes verbatim, timeout mapping, and the no-regression assertion for the text variant (AC-1, AC-6, AC-7). |
| `shared/tests/_sweep_helpers.py` | edit | Fixtures could not express a broken byte at all — `Path.write_text(encoding="utf-8")` raises on a lone surrogate. Now writes/reads via `surrogateescape` (the store's own rule) and carries the shared seeds `BAD_BYTE` / `broken_bytes` / `broken` / `status_line`. Byte-identical for every existing ASCII fixture. |
| `shared/tests/test_main_tree_git_timeout_paths.py`, `shared/tests/test_store_git_timeout_paths.py` | edit | 3 fail-safe tests were pinned to `run_git_soft` on the moved `show` calls; re-pinned to `run_git_bytes_soft` so the timeout branches stay asserted. |

## Work breakdown

1. **`git_base`: private core + bytes-soft variant.**
   Extract `_popen_git(args, *, cwd, timeout, binary)`; `run_git` delegates with
   `binary=False` and keeps raising `TimeoutExpired`; `run_git_bytes_soft`
   delegates with `binary=True` and maps `TimeoutExpired` to
   `TIMEOUT_RETURNCODE` with `stdout=b""`.
   *Test:* `test_git_base_bytes.py` — blob bytes verbatim; timeout mapping;
   `run_git` still returns `str` with `U+FFFD`.

2. **`sweep_text`: one decode rule.**
   `decode_store_text(data)` = `data.decode("utf-8", errors="surrogateescape")`;
   `read_text_verbatim` reads binary and routes through it (newline translation
   stays off — it already reads with `newline=""`).
   *Test:* parity assertion in `test_store_decode_parity.py` (AC-2).

3. **Three call sites.** Swap each `run_git_soft(["show", …])` for the bytes
   variant + `decode_store_text`. Return-code handling is untouched — every one
   of the three checks `returncode` before it looks at `stdout`, and none of
   them reads `stderr`, so `CompletedProcess[bytes]` is a drop-in.
   *Test:* AC-3 (`sweep_gc`), AC-4 (`sweep_drift`), AC-5 (`reconcile_triage`),
   each driven over a real git repo with a real `0xFF` byte.

4. **Boundary Probe** (`touches_io_boundary`): assert the full round trip —
   bytes on disk → `git` blob → decode → compare → survivor re-encode → bytes on
   disk — is byte-identical for a line containing `0xFF`.

## Test strategy

- Real git throughout, no mocks of the git layer — matching `_sweep_helpers.py`'s
  stated rule ("the sweep is the most data-loss-sensitive unit in the campaign,
  so nothing is mocked"). The one exception is AC-6, where `TimeoutExpired` is
  injected, patched by **module object** per ADR-045.
- Every regression test must FAIL on the pre-fix code. Verified by running each
  new test against `HEAD` before applying step 1-3.
- Test root: `shared/tests` (one root per pytest process — repo-root `conftest.py`
  enforces it).

## External plan review — findings integrated

Both providers approved the approach (`SHIPWRIGHT_VERDICT: approve`); the
findings are about *how* to execute it, and each changes the plan above.

| # | Provider / severity | Finding | Disposition |
|---|---|---|---|
| 1 | openai / **high** | The `_popen_git` extraction can incidentally alter text-mode behaviour for ~133 callers (stdout *and* stderr decoding, cwd, argv, timeout reaping). | **Accepted.** Step 1 keeps the text branch's `Popen`/`communicate` kwargs literally unchanged, and `test_git_base_bytes.py` gains characterization tests for text `stdout`, text `stderr`, a non-zero return code, and `run_git_soft`'s existing timeout mapping — not just `run_git` stdout. |
| 2 | openai / medium | The bytes timeout branch must kill **and reap**, and AC-6's `stdout == b""` must be a deliberate discard of `TimeoutExpired`'s partial output, with a consistently typed bytes `stderr`. | **Accepted.** The kill/reap lives in the shared core, so both variants inherit one implementation. The bytes soft-wrapper returns `stdout=b""`, `stderr=<message>.encode()` — bytes on both streams, no mixed typing. |
| 3 | openai / medium | The F0.5 runner covers only the two new files — too narrow for a change to the shared git primitive. | **Accepted.** The spec's runner command now also runs the existing `test_sweep_outbox*`, `test_sweep_drift*` and `test_reconcile_triage*` modules, i.e. the callers whose behaviour must be unchanged. |
| 4 | openai / low | Rewiring `read_text_verbatim` to binary+decode is behaviour-sensitive beyond the git-blob issue. | **Accepted.** Characterization test added for plain UTF-8 content, CRLF *and* LF preservation, and surrogateescape round-tripping. `decode_store_text` is documented as the triage-store rule, not a general text API. |
| 5 | openai / low | Keep surrogate-carrying text out of JSON serialization, subprocess argv and logging. | **Accepted as a standing constraint.** The bytes result stays confined to the three comparison boundaries; nothing new is logged or serialized. |
| 6 | deepseek / low | The three sites will receive `CompletedProcess[bytes]`; if any touches `stderr` in string formatting it breaks. | **Accepted.** Verified by reading all three: each checks `returncode` then `stdout` only. Step 3 re-asserts this, and finding 2's bytes-typed `stderr` means a future slip fails loudly rather than silently formatting `b'...'`. |
| 7 | deepseek / low | Binary reading might preserve a UTF-8 BOM that text mode stripped. | **Falsified, no action.** Only `encoding="utf-8-sig"` strips a BOM; `read_text_verbatim` already uses plain `"utf-8"`, which decodes `b"\xef\xbb\xbf"` to `U+FEFF` exactly as the byte path does. Behaviour is identical, so there is nothing to preserve. Covered anyway by the finding-4 characterization test. |

## Alternative approach considered

**Normalise both sides to a lossy common form** (map surrogates to `U+FFFD`
before comparing) — a two-line change touching no primitive.

**Rejected:** `errors="replace"` is non-injective. Two different broken lines
collapse to the same string, so a buffer line could be judged "delivered" on the
strength of a *different* origin line and be deleted. That trades today's
benign failure (line stays, no data loss) for silent data loss in the operator's
finding log. The whole reason this card is `RICHTUNG: nur Liegenbleiben` is worth
preserving.
