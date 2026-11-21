# The one due answer for reminders and parked triage entries

Run: `iterate-2026-11-21-e1b-reminder-due` (campaign `reminders-core`, unit E1b). Spec bookkeeping: extends the existing FR-01.22 with AC07-AC09 (the read side of the same operator-reminders capability); no new FR, so the pinned FR-count tests in integration-tests are unchanged. The decision drop and mini-plan say the same.

## Decision
A read-only `reminder_cli.py due [--on D] [--json]` backed by `lib/reminder_due.py`. It folds the reminder store, reads triage only through `triage.read_all_items` (in process), merges both into one list with a fixed 10-field item, and returns `{contractVersion: 1, on, sourceRoot, reminderStore, reminderCorruptLines, triageError, items}`. Output text is redacted because part 2 mails it.

## Deliberate differences from the brief wording
- Envelope carries `sourceRoot` (triage root), `reminderStore` (main-root store file), `reminderCorruptLines` (reminder store only) and `triageError`: the reviewers showed one root and one count would mislead a consumer, and a triage read failure must not hide the reminders nor read as "nothing due".
- A triage item's link is `{label: "Triage <id>", kind: "triage", ref: <id>}` (brief: `{kind, ref}`) so every link has the same three fields.
- Redaction is applied to reminder text too (a hand-edited store), not only triage text; control characters are flattened in single-line fields.
- `--on D` shows what the stored state makes due as of D, not a historical replay; an expired park and an overdue reminder show every day until acted on.

## Architecture Review
External (`--mode architecture`), verbatim: openai **approve**; glm text says approve but ends `SHIPWRECK_VERDICT: approve` (typo), so the CLI reads `unknown`: not a reject. Internal (`architecture-internal-reviewer`, opus): **approve Option A with revisions**: define the redaction tool and its fields, define behaviour when a source cannot be read, fix item order/identity, say the text is untrusted, and test read-only behaviour. All applied.

## External-Plan-Review-Findings
| Finding | Disposition |
|---|---|
| glm: pin `--on` format | accepted-and-fixed: strict YYYY-MM-DD via `parse_day`, malformed refused (tested) |
| glm: snooze effective due after the threshold | accepted-and-fixed: stays `snoozed_until` on every later day (tested, documented) |
| glm/openai: corrupt/unreadable source policy | accepted-and-fixed: corrupt lines counted, never fail; triage failure reported in `triageError`; unreadable store exits 4 |
| openai: map brief Done-when to tests | accepted-and-fixed: each Done-when item has a test (listed in the self-review) |
| openai: exact schema and ordering | accepted-and-fixed: types, ordering and identity in the `reminder_due.py` docstring, pinned by `test_reminder_due_contract.py` |
Internal `opus-plan-reviewer` blockers B1 (wrong root in a worktree; fixed: both roots reported, real-worktree test) and B2 (`corruptLines` name; fixed: `reminderCorruptLines`, reminders only, documented); S1 control characters (fixed), S2 PEM block and `password=` (fixed); S3 triage failure losing reminders (fixed); S4 no direct triage read (source-scan test). Accepted best-effort: a URL password containing `/` or `@` can leak part of itself.

## Cross-repo contract
The Command Center WebUI (`shipwright-webui`) consumes `due --json`; a shape change requires a corresponding WebUI change and a version bump. Stated in `reminder_due.py` and `docs/guide.md`, pinned by `shared/tests/test_reminder_due_contract.py`. The consumer calls from the main checkout, treats (`kind`, `id`) as identity, escapes every text field, and must keep `sourceRoot` / `reminderStore` (local paths) out of mail bodies.

## Review dispositions (internal cascade, opus)
Stage 1 spec: PASS. Stage 2 code: approved with 2 medium and 5 low findings, all fixed or accepted (see `code_review_reply.json`): prefixed secret names, UTC-boundary test, unicode separators, `triageError` without a path. Stage 3 doubt: 3 medium (triage read empty from a subdirectory; empty fallback store when git fails; JSON-quoted secret keys) fixed, lows fixed or documented (`doubt_review_reply.json`). External code review: glm only (openai leg failed: the whole-commit diff exceeded its input limit); its findings were checked, the rest were rebutted (triage `revisitAt` is validated by `revisitDue`; ids are validated by the folds). Accepted best-effort: `Authorization: Basic` and URL passwords containing `/` or `@` are not masked; write-side secret patterns are unchanged from E1a.

## Rejected alternatives
B: the consumer merges two CLIs (a second copy of the rules in another language, redaction outside Shipwright). C: do nothing.

## Confidence Calibration
Boundary: `due --json` (producer) to the WebUI (consumer) and the triage read. Probes: lone surrogate, control characters and CRLF in text, PEM block and `password=` text, unreadable triage, real git worktree. Findings: the redaction order let a PEM body survive (header redacted first); fixed by masking the block before the generic pass; two further probes clean. Not probed: a very large triage detail (no length limit, stated in the contract).
