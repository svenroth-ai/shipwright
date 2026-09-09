# CONTEXT.md producer wired into the interview protocol

## Context

`shared/context-format.md` defines the `CONTEXT.md` domain-glossary format
(Language / Relationships / Flagged ambiguities), but no script ever wrote
the file — FR-01.16 AC06 was an unearned promise. `shared/requirement-
elicitation.md` §4 ("sharpen the language against the glossary") and §7
("capture as you go") require a sharpened term to land in `CONTEXT.md` the
moment it is resolved, not batched at end-of-interview.

## Decision

Added `shared/scripts/tools/write_context_term.py`, an idempotent producer
(`file_lock` + `durable_atomic_write`, mirroring `append_changelog_entry.py`)
that upserts one `Language` entry into `CONTEXT.md`, preserving every other
section/entry byte-for-byte including the file's own CRLF/LF convention.
Wired it into `plugins/shipwright-project/skills/project/references/
interview-protocol.md` immediately after "## Philosophy", with an
instruction to invoke it in the same turn a term is sharpened (not deferred),
plus a cross-reference under "Core Topics to Cover" so any topic can trigger
it. A drift-protection test
(`shared/tests/test_requirement_elicitation_refs.py::
test_project_interview_protocol_wires_the_context_producer`) pins that the
prompt actually names the script, the flags, and "same turn" wording.

## Consequences

`/shipwright-project` interviews now produce a real, growing `CONTEXT.md`
instead of a documented-but-unearned promise. A second/third sharpened term
appends without corrupting or duplicating earlier entries (tested); a
re-sharpened term overwrites in place (last write wins). Re-running with an
unchanged term set is byte-identical (idempotent), which the F0 CI-parity
recheck below actually depends on. `plugins/shipwright-adopt` was
explicitly left untouched (owned by a different triage item).

## Rationale

Producer-script pattern chosen over ad-hoc inline prompt edits so the write
is atomic, lock-safe, and independently testable — the same shape every
other shared producer already uses.

## Rejected alternatives

- Case-folding terms for duplicate detection: rejected — `context-format.md`
  treats terms as exact prose, and folding risks merging two genuinely
  different sharpened terms that happen to differ only in case.
- Escaping all markdown special characters in term/definition text broadly:
  rejected as over-broad; only `**` (the entry delimiter) is rejected
  outright, since it is the one character that would corrupt the next
  parse — anything else is legitimate prose.
- Parameterizing `{shared_root}` differently in the interview-protocol.md
  snippet ("distribution risk"): rejected — matches every other existing
  shared producer's identical invocation convention; no reason to diverge.

## External Plan Review Findings (Step 3.5)

Both GLM and OpenAI reviewers returned `revise` on the mini-plan. Findings
triaged:

| Finding | Severity | Disposition |
|---|---|---|
| No handling for a term containing an embedded newline — would mis-parse the entry on the next run, breaking idempotency | High | accepted-and-fixed — added `_sanitize_field()` to collapse embedded newlines/whitespace to single-line prose before writing |
| `--project-root` not validated to exist — `durable_atomic_write`'s `mkdir(parents=True, exist_ok=True)` would silently deep-create arbitrary directories | High | accepted-and-fixed — added an explicit existence check in `main()` that fails loudly (`ERROR: --project-root does not exist`) instead of silently creating it |
| Contract (idempotency, overwrite-on-resharpen, byte-preservation) not documented anywhere a future reader would find it | Medium | accepted-and-fixed — added an explicit "Contract" paragraph to the module docstring |
| Interview protocol should cross-reference the producer from more than one place, so a term surfaced outside the dedicated topic isn't missed | Medium | accepted-and-fixed — added a one-line cross-reference under "Core Topics to Cover" |
| Term/definition case-folding for duplicate detection | Low | rejected-with-reason — see Rejected alternatives above |
| Broader markdown-character escaping | Low | rejected-with-reason — see Rejected alternatives above |
| `{shared_root}` invocation path is a "distribution risk" | Low | rejected-with-reason — see Rejected alternatives above |

## External Code Review Findings (Step 3.7)

GLM returned `approve`; OpenAI returned `revise` with two real findings:

| Finding | Severity | Disposition |
|---|---|---|
| A term containing `**` (the entry delimiter) would be mis-parsed on the *next* run by the non-greedy `_TERM_RE`, silently breaking term-identity/idempotency for that entry | High | accepted-and-fixed — `upsert_term` now raises `ValueError` rejecting any `--term` containing `**` |
| Updating one term in an existing CRLF-authored `CONTEXT.md` silently rewrote the *whole file's* line-ending convention to LF, contradicting the documented "byte-for-byte preserved" guarantee for untouched content | High | accepted-and-fixed — root cause was `Path.read_text(encoding="utf-8")` performing universal-newline translation by default (`\r\n`→`\n`) before detection could run; fixed by reading via `.open(encoding="utf-8", newline="")` (Python 3.11-compatible — `Path.read_text`'s own `newline=` kwarg is 3.13+ only, a second, independent bug this run also caught and fixed during the CI-parity F0 recheck) and threading the detected `eol` through `_render_document` |

## External Code Review — second round (after the F0 CI-parity fix)

A second cascade ran against the final diff (`HEAD~1..HEAD`, after the
`Path.open(newline=...)` fix above). GLM returned `approve`; OpenAI
returned `revise` with two real findings, both fixed:

| Finding | Severity | Disposition |
|---|---|---|
| `--project-name`/`--summary` were not sanitized like the term fields — an embedded newline could inject a `## heading` or `**term**` entry into a freshly created file, corrupting the schema | Medium (bug) | accepted-and-fixed — both fields now pass through `_sanitize_field()` before `_default_header()`; regression test `test_project_name_and_summary_are_sanitized_on_creation` |
| A malformed hand-edited `CONTEXT.md` with a duplicate `## Language` heading silently overwrote the first occurrence's body while `order` still listed it twice, corrupting rendering on the next write | Medium (edge-case) | accepted-and-fixed — `_parse_document` now raises `ValueError` on a duplicate heading name instead of silently discarding data; regression test `test_duplicate_heading_in_existing_file_is_rejected` |
| The wired-path CLI test asserts only substrings, not context-format.md's full schema shape | Low (test-quality) | rejected-with-reason — the unit-level tests already assert full-document structure (heading presence/absence, ordering, byte-identical round-trips); the CLI test's job is proving the wired invocation shape works, not re-deriving schema coverage already owned elsewhere |

## Stage-2 code review (delegated, PR #699) — third round

The orchestrator-run Stage-2 cascade returned REQUEST CHANGES against the
merged commit. Three blocking findings plus two low-severity ones, all
fixed:

| Finding | Severity | Disposition |
|---|---|---|
| `write_context_term.py` was 302 lines, over the 300-line source limit, with no `shipwright_bloat_baseline.json` entry | High | accepted-and-fixed — split the pure parse/render internals into a new sibling module `shared/scripts/tools/_context_md_format.py` (139 lines), leaving `write_context_term.py` at 210 lines; a baseline-entry workaround was explicitly rejected (a cap at exactly `current` leaves zero headroom) |
| `docs/hooks-and-pipeline.md`'s Artifact Write Matrix had no row for `CONTEXT.md` | Medium | accepted-and-fixed — added a row after `CLAUDE.md` naming the producer, the idempotent-upsert-on-every-resharpen behavior, the format SSoT, and that nothing currently reads it back |
| Re-sharpening a term WITHOUT repeating `--avoid` silently deleted its existing `_Avoid_` line (`e["avoid"] = avoid` unconditionally overwrote with `None`), contradicting interview-protocol.md's own "safe to call once per sharpened term... just updates in place" wording | Medium (real bug) | accepted-and-fixed — `avoid=None` (flag omitted) now keeps the existing line; added an explicit `--clear-avoid` flag (mutually exclusive with `--avoid`) for deletion; documented in both the module's Contract docstring and interview-protocol.md; regression test `test_reupsert_without_avoid_keeps_existing_avoid_line` (plus `test_clear_avoid_deletes_the_existing_avoid_line` and `test_avoid_and_clear_avoid_together_is_rejected`) in the new `shared/tests/test_write_context_term_avoid.py` |
| interview-protocol.md's wired snippet didn't state that `--term`/`--definition`/`--avoid` are passed verbatim and never shell-evaluated | Low | accepted-and-fixed — added the sentence and wrapped the example's placeholders in single quotes |
| The duplicate-heading error hardcoded the literal string `"CONTEXT.md"` even when `--context-path` pointed elsewhere, and the stderr print was not UTF-8-safe on a Windows console | Low | accepted-and-fixed — threaded the real `context_path` into the duplicate-heading `ValueError` message; added `sys.stderr.reconfigure(errors="replace")` at the top of `main()` |

## Stage-3 doubt review (adversarial, PR #699) — fourth round

An adversarial doubt-review pass ran against the Stage-2 fix commit and
returned 6 surviving doubts (2 High, 2 Medium, 2 Low), all fixed:

| Finding | Severity | Disposition |
|---|---|---|
| D1: the producer only writes `Language` entries; `Relationships`/`Flagged ambiguities` require a hand-edit that can race the producer's atomic full-file replace and silently drop a term | High (concurrency) | accepted-and-fixed — added an explicit "never hand-edit CONTEXT.md while an interview is running" rule to interview-protocol.md, and documented the Flagged-ambiguities/Relationships gap as a known limitation (not closed — scope stays P4.1) in both interview-protocol.md and the module docstring |
| D2: three hand-authored shapes (no blank line before an entry, a heading-less file, a hyphen instead of an em dash) hide an existing term from re-detection, producing a silent duplicate on the next sharpen | High (correctness) | accepted-and-fixed — added `context_md_format.term_markup_count()`; `upsert_term` now refuses loudly (`ValueError`) whenever the final rendered document contains the written term's `**term**` markup more than once, the same way the existing duplicate-heading check does; regression tests for all three shapes in the new `shared/tests/test_write_context_term_duplicates.py` |
| D3: `shared/context-format.md` §2's own worked `Cancellation` example (definition wraps onto a continuation line) is falsified by "every other entry/section round-trips untouched" — the continuation line became an orphaned raw block and a blank line was injected mid-definition | Medium (correctness) | accepted-and-fixed — `parse_language_entries` now absorbs a non-`_Avoid_`, non-term continuation line into the entry's definition (joined with a space); round-trip test using the exact context-format.md example text in the new `shared/tests/test_context_md_format.py` |
| D4: hooks-and-pipeline.md said "nothing reads it back", but P4.2 (grill-trace completeness gate) needs to read sharpened terms and its only options were importing the private `_context_md_format` module or forking the parser (guaranteed drift on D2/D3's edge cases) | High (architecture, blocks P4.2) | accepted-and-fixed — renamed `_context_md_format.py` → `context_md_format.py` (no longer private — second, cross-plugin caller) and added a public `read_terms(path) -> list[Term]`; documented as the sanctioned read API in the module's Contract paragraph and the hooks-and-pipeline.md row; moved the "exact-case, exact-prose, no folding" matching guarantee from the ADR's rejected-alternatives table into the Contract docstring itself |
| D5: `--avoid "   "` sanitizes to `""` (not `None`), silently taking the same path as `--clear-avoid`, and `--avoid "   " --clear-avoid` together was accepted instead of rejected | Low | accepted-and-fixed — a given-but-blank `--avoid` is now rejected the same way a blank `--definition` already is, before the mutual-exclusion check runs |
| D6: `upsert_term` read the existing file with a bare `.open()` while writing through `durable_atomic_write`; `atomic_write.py`'s own docstring says a reader of a file it publishes should read through `durable_read_bytes` | Low | accepted-and-fixed — switched the read to `durable_read_bytes(...).decode("utf-8")`, which preserves CRLF/LF exactly like the prior `newline=""` open (decode performs no universal-newline translation) while adding the Windows delete-pending retry `durable_atomic_write`'s writes can trigger for a racing reader |

## Final verification pass (PR #699) — fifth round

One more blocking finding surfaced after the Stage-3 doubt-review fix, plus
three cheap one-line doc fixes, all resolved:

| Finding | Severity | Disposition |
|---|---|---|
| D2's fix scanned the WHOLE rendered document for a duplicate `**term**`, but a term legitimately reappears bold as a cross-reference inside `Flagged ambiguities`/`Relationships` (context-format.md §2's own worked example: "the paying `**Customer**`; ... a `**User**`."). Upserting "Customer" against that canonical file permanently failed with a false "needs a hand-fix" error; both new test fixtures had silently paraphrased the doc's bold markup out, which is why nothing caught it | High (blocking) | accepted-and-fixed — the scan now covers only `header + sections["Language"]` (all three D2 hidden-duplicate shapes live there, never in Relationships/Flagged ambiguities); regression test upserts "Customer" into context-format.md §2's example VERBATIM (bold markup included) and confirms it succeeds; both existing fixtures (`test_context_md_format.py`, `test_write_context_term.py`) realigned to the doc's actual bold-cross-reference text instead of a paraphrase that happened to avoid the bug |
| `read_terms()`'s docstring claimed "(never raises)" but it propagates `ValueError` (duplicate heading) and `UnicodeDecodeError` (non-UTF-8) | Low | accepted-and-fixed — docstring now states the actual failure contract; two pinning tests added (`test_read_terms_propagates_duplicate_heading_value_error`, `test_read_terms_propagates_non_utf8_decode_error`) |
| `write_context_term.py`'s docstring documented `created`/`appended`/`updated`/`unchanged` but a reachable `rewritten` status (an existing term matched with no value change, but the file still re-serialized to different bytes) was undocumented | Low | accepted-and-fixed — added to the docstring with what distinguishes it from `unchanged` |
| Docstring said "every other entry/section round-trips untouched" — no longer literally true once the D3 fix reflows a hand-wrapped definition onto one line | Low | accepted-and-fixed — reworded to "normalized onto a single line" for the wrapped-definition case |

## Shell quote-breakout fix — required GitHub check (PR #699) — sixth round

A GitHub required check (the `pr-review` bot, not this ADR's internal
review cascade) blocked the PR on a real, agent-triggerable shell-injection
finding: interview-protocol.md's wired snippet told the agent to wrap
`--term`/`--definition`/`--avoid` values in single quotes, but never
handled a value that itself contains a single quote — extremely plausible
in natural interview language ("the customer's cart", "it's the settled
definition"). Substituting such a value into `--term '<value>'` breaks out
of the shell quoting; the rest of the string is then interpreted as shell
syntax, and the agent is instructed to literally run this as a bash
command.

**Decision:** closed the vulnerability class rather than documenting the
escaping rule more carefully — a prompt-only guarantee cannot be repaired
with more prompt (the same philosophy this module's own contract already
rejects elsewhere). Added `--payload-file` to `write_context_term.py`: the
agent writes `{"term": ..., "definition": ..., "avoid": ...}` to a scratch
JSON file via the Write tool (never a shell command), then invokes the
script with `--payload-file <fixed path>` — every value that reaches the
script's argv is then a fixed, known string, and no shell ever parses the
free interview text at all. `interview-protocol.md`'s wired snippet is now
this two-step invocation; the old `--term '<value>'` shell-quoted form
remains available only for callers that already hold trusted,
non-shell-composed values (tests, other scripts).

Implementation split into a new private sibling module
`_write_context_term_cli.py` (CLI argument-resolution: `--payload-file`
JSON validation, the `--payload-file` XOR `--term`/... mutual-exclusion
check) to keep `write_context_term.py` under the 300-LOC bloat-baseline
threshold — the same split precedent as `_backfill_ac_provenance_apply.py`
and the promoted `context_md_format.py`, except this one stays private
(single caller, unlike `context_md_format.py`'s cross-plugin `read_terms()`).
Also fixed a latent bug the payload-loading refactor surfaced: an earlier
in-progress draft of `main()` validated `--payload-file` fields into a
`fields` dict but then called `upsert_term()` with the raw, unused
`args.term`/`args.definition`/... instead — caught before commit by the new
`test_write_context_term_payload.py` regression suite (a term with an
embedded single quote written via `--payload-file` must actually reach
`CONTEXT.md`, which it did not until the caller used `fields[...]`).

## F0 CI-parity note

An initial fresh-verification pass ran under a hand-rolled serialized
fallback (host-contention workaround) that silently executed under an
ambient Python 3.13 interpreter instead of the CI-pinned 3.11. Under 3.13,
`Path.read_text(newline=...)` is valid (that kwarg was added in 3.13), so
the suite was green — but it would have broken CI outright, since 3.11's
`Path.read_text()` does not accept `newline=`. Re-running the full 18-unit
suite under the correct `--python 3.11 --with pytest --with pytest-mock`
shape surfaced this for real (`TypeError: Path.read_text() got an
unexpected keyword argument 'newline'`, 12 failing tests) before it could
reach CI. Fixed by switching to `Path.open(..., newline="")`, which has
accepted `newline=` since pathlib's inception. See F3a for the reusable
learning.

## Stale evidence citation fix (PR #699) — seventh round

One MEDIUM finding after the sixth round's `--payload-file` fix:

| Finding | Severity | Disposition |
|---|---|---|
| `test_write_context_term_cli.py`'s docstring still called itself "the wired path" / "the exact invocation shape interview-protocol.md tells the agent to use", and the Test Completeness Ledger cited it as AC3/AC4 evidence — but every test in that file uses the now-deprecated `--term`/`--definition`/`--avoid` flags, not `--payload-file`, which became the actual wired path in the sixth round. A reader following the evidence trail from the ledger would land on the deprecated form labelled as authoritative | Medium | accepted-and-fixed — `test_write_context_term_cli.py`'s docstring reworded to state it covers the LEGACY trusted-caller flag path only, never the interview-wired invocation, and points to `test_write_context_term_payload.py` as where AC2/AC3/AC4 evidence now lives. The Test Completeness Ledger (`.shipwright/agent_docs/iterates/iterate-2026-09-09-p4-1-glossary-generator.json` and its immutable `.test-results.json` sibling) AC3/AC4 rows re-cited: AC3 now cites `test_write_context_term_payload.py::test_payload_file_sharpens_a_term_containing_a_single_quote` (the actual wired invocation); AC4 now cites `test_write_context_term_payload.py::test_payload_file_clear_avoid_round_trips` (two sequential wired invocations against the same file) alongside the unaffected `test_write_context_term.py` `upsert_term`-level append/no-duplication tests, which were never CLI-specific and remain valid regardless of which flag path is wired |

Five LOW findings from this pass deferred to a follow-up triage card
(coordinator's explicit scoping — not addressed here): the CLI test
file's own name, `--help` text on the legacy flags, a negative
drift-test assertion, empty-string `avoid` handling in the payload path,
and `term_markup_count` still scanning bolded cross-references inside
`Language` section definitions, plus the redundant `mkdir` line in
`interview-protocol.md`'s payload-writing step.

## CI post-merge fix round (PR #699) — eighth round

Two NEW findings surfaced by CI on the post-merge commit (`087347aa0`, after
the third `origin/main` merge into this branch) — neither present before,
both real, neither review-cascade opinion:

| Finding | Severity | Disposition |
|---|---|---|
| CodeQL (`py/uninitialized-local-variable`-class query): `upsert_term`'s `old_content = content if existed else None` reads `content`, which is only assigned inside the `if existed:` branch above it — logically safe at runtime (the ternary only evaluates `content` when `existed` is `True`, by which point it was always assigned), but not provable by static analysis, and fragile to rely on the ternary as the only proof of safety | High (real, not a suppress-candidate) | accepted-and-fixed — initialize `content = None` unconditionally before the `if existed:` block, so the name is always bound; simplified the later read to `if new_content != content:` (the ternary was redundant once `content` is always `None` when `existed` is `False`) |
| Diff-coverage gate: `_write_context_term_cli.py` at 17.4% and `write_context_term.py` at 70.9% on the PR's diff vs `origin/main` (needs ≥80%) | High (real, blocks merge) | accepted-and-fixed — root cause was every existing CLI test invoking the script via `subprocess.run([sys.executable, ...])`, a separate Python process this repo's coverage instrumentation never observes (no `COVERAGE_PROCESS_START`/`sitecustomize` hook configured). `main()` and every `_write_context_term_cli.py` function were therefore behaviorally tested but invisible to the gate. Added two new in-process test files — `shared/tests/test_write_context_term_direct.py` (bootstrap `sys.path` insertion + `main()`, covering every argv/exception branch: success, `PayloadError`, missing `--project-root`, missing `--context-path` parent, `ValueError` from `upsert_term`, `LockTimeout`) and `shared/tests/test_write_context_term_cli_direct.py` (`build_arg_parser`/`load_payload_file`/`resolve_fields` called directly, no subprocess) — that import the modules and call the functions in-process so coverage actually sees them execute. Verified locally with the CI-pinned toolchain (`uv run --with pytest --with pytest-mock --with pytest-cov ... --python 3.11`, `uvx diff-cover@10.3.0 ... --compare-branch=origin/main --fail-under=80`): `_write_context_term_cli.py` 100%, `write_context_term.py` 99% (only the untestable `if __name__ == "__main__": sys.exit(main())` guard line remains uncovered), overall diff coverage 96% |

No review-cascade findings this round (narrow CI-fix, not a re-opened review
round) — see F3a for the reusable learning on subprocess-invisible coverage.
