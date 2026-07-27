# Self-Review — iterate-2026-07-27-triage-defer-ci-cap

1. **Spec Compliance: pass.** AC-1..AC-9 each map to at least one assertion.
   AC-1 `test_cli_defer_records_the_operator_as_the_actor` (status, reason,
   `statusBy == "cli"`). AC-2 the two parametrised refusal tests, both
   asserting the store is byte-unchanged. AC-3 unknown id, already-decided,
   and the three exception types at library level. AC-4 both surfaces reach
   `mark_status` through `triage_promote`; the CLI holds no transition logic.
   AC-5/5b the four rendering cases plus the escape and newline tests. AC-6
   `test_list_json_stays_open_only_when_an_item_is_deferred`. AC-7/AC-8 the
   cap and boundary tests on both mappers. AC-9 the three documents are edited
   in this diff. Nothing outside the two decided gaps was implemented.

2. **Error Handling: pass.** `defer` raises the same three types as `dismiss`
   (`ValueError` / `KeyError` / `FileNotFoundError`), and `_status_flip` maps
   all three to exit 2 — the arm `dismiss` already used, so no new exit code
   entered the CLI. Every rejection path is asserted to leave the stored
   record untouched, not merely to return non-zero.

3. **Security Basics: pass, after a fix.** The first implementation reused the
   payload sanitizer for scalar fields; it preserves `\n`/`\t` by design, so a
   stored reason could forge listing rows. Fixed with a sibling inline
   sanitizer in `tty_sanitize.py` (one policy, two shapes) and pinned by a
   test that plants a forged `- trg-fake…` row. No secret, path or finding
   text is written anywhere new. The detail cap is a crowding guard and is
   documented as such, so nobody later mistakes it for escaping.

4. **Test Quality: pass.** Tests assert observable outcomes — the resolved
   item, the stored bytes, the process exit code, the rendered stdout — not
   internals. The CLI cases run the real script as a subprocess. No skips, no
   `try/except` around an assertion, no assertion loosened to make something
   pass. The cap-boundary helpers compute the padding from a measured probe
   rather than a magic number, and one of them carries a comment about the
   eight-character fallback that made the first version wrong.

5. **Performance Basics: pass.** `_cmd_list` now reads the resolved items once
   and partitions them, where it previously filtered once — one pass either
   way. `_cap_detail` is an O(1) length check on strings already in memory.

6. **Naming & Structure: pass.** Two extractions, both forced by the 300-line
   budget rather than by taste: `lib/triage_render.py` (the CLI kept argument
   parsing and dispatch) and `_decide_from_triage` / `_require_store` inside
   `triage_promote.py`. `_decide_from_triage` was deliberately not widened to
   swallow `promote`. Every touched file is now inside budget:
   `triage_cli.py` 249, `triage_promote.py` 298, `triage_render.py` 92,
   `mappers.py` 220, the two new test files 133 and 275.

7. **Affected Boundaries: pass.** Three, all listed in the spec. The one that
   matters is `list --json`, pinned byte-for-byte by a fixture in the WebUI
   repo — the deferred section is human-output only and a test asserts the
   JSON array stays open-only *with a deferred item present*. No new stored
   format: `snoozed` was already in `triage.STATUSES` and already handled by
   `read_all_items`, `triage_gc` and `aggregate_triage`.

8. **Test Hygiene Probe: pass.** No `pytest.skip`, no environment-conditional
   assertion, no `xfail`. Both new files are self-contained under `tmp_path`
   and touch no repo state. Neither imports across a plugin boundary, so the
   `cross_plugin` marker does not apply.

## Observed but deliberately not fixed

- `aggregate_triage.py` carries its own byte-identical `_fence_opener` — the
  duplicate `tty_sanitize.py` was extracted to end. It is not an owned file
  here and the copy is not what this card is about; noted rather than swept
  in, so a future extraction has a starting point.
- Neither surface can un-defer. That is real, matches the Command Center
  exactly, and is recorded in the spec's Out of Scope rather than left to be
  discovered.
