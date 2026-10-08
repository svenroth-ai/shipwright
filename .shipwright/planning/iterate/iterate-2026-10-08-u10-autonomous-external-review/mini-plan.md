# Mini-plan: U10 — Autonomous external review: loud, not silent

**Problem.** When an autonomous run (campaign sub-iterate) cannot run the external review
(provider error, degraded envelope, `uv run` failure), the pass is closed `not_run` and the run
carries on. Nothing proves the reviewer actually failed — `--reason-code unavailable` can be typed
for a review that was simply never invoked — and nothing tells the operator afterwards: no PR note,
no summary line, no reminder to re-run. Operator decision (BRIEF §5.2): the run MAY continue, but
never silently; no env-var waiver.

**ACs (BRIEF U10).**
1. An autonomous run whose external review cannot run records the pass `not_run` with
   `reason_code: unavailable` and continues.
2. `unavailable` on an adapter-backed pass (`plan`, `external_code` — the two `external_review.py`
   produces) requires a captured adapter-error artifact; F11's review-record check refuses the row
   without one, and `record_review_pass.py record` refuses it at write time.
3. A bare `not_run` without a code fails the review-record check (already enforced by U3's
   `reason_codes_closed`; pinned again for the external pass).
4. Loud: one line for the PR body and the F12 summary naming every `unavailable` pass, and one
   triage card (idempotent per run) to re-run it.
5. Interactive flow unchanged (no new prompts; the recording rule is the same in both modes).

**Design.**
- New `shared/scripts/lib/review_unavailable.py`: the artifact is found by CONVENTION, not a new
  record field — the run dir's canonical raw file (`external-plan-review-raw.json` /
  `external-code-review-raw.json`, stdout of `external_review.py`) or its `.stderr.txt` sibling (for
  a `uv run` that died before printing JSON). Accepted: the raw JSON is the adapter's own failure
  envelope (`success: false` or `degraded: true`), or non-JSON non-empty text, or a non-empty
  stderr file. Refused: no file / empty files, or a raw reply reporting `success: true` and not
  degraded (the review DID run — claiming unavailable contradicts its own artifact).
- `verifiers/review_record_check.py`: one call after closure; when a commit is given the artifact
  must be in it unless gitignored.
- `record_review_pass.py`: the same check at write time (net 0 lines; the file is capped).
- New `shared/scripts/tools/review_unavailable_note.py`: prints `none` or
  `N (plan, external_code) — adapter error: <paths>`; `--file-triage` files one `iterate`-source
  card (dedup per run_id) with a re-run launch payload and appends its id.
- Docs: `campaign-step-3-5-plan-review.md` gains the *Unavailable* procedure (stderr redirect,
  record, note, card, result.json `reviews.unavailable_note`); `sub-iterate-runner.md` points at it
  (net <= 0 lines); F12.md gets an `Unavailable:` row; F11.md PR template carries the line (same
  line as Exemptions); campaign-mode.md step 5 surfaces it (rewrap only).

**Alternatives considered.** (a) A new `error_artifact` field in the review-record schema + a CLI
flag — rejected: the schema and the CLI are both capped exception files, a consumer (webui) reads
the schema, and the canonical basenames already pin where the adapter writes; (b) halting the unit
instead of continuing — rejected by operator decision §5.2; (c) an env-var waiver — explicitly
excluded by §5.2.

**Tests.** `shared/tests/test_review_unavailable.py` (lib + gate + CLI record-time + note/triage
tool), every test tagged `pytest.mark.covers`.

**Risks.** Historical records with `unavailable` on `plan`/`external_code` and no artifact: F11
verifies only the run being finalized, so history is not re-checked (same stance as U3).
