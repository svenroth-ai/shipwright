# Iterate specification — machine-callable triage transitions

- **Run ID:** `iterate-2026-08-10-p2-34a-machine-cli-transitions`
- **Intent / complexity:** change / medium
- **Spec impact:** modify — the established CLI contract gains an explicit machine-write surface.

## Problem and decision

The Command Center currently duplicates triage write semantics in TypeScript.
This slice makes the Python CLI a complete, programmatic transition surface so
the WebUI follow-up can route every write through one writer.  The alternative
of composing Python and TypeScript lock primitives is rejected: it would change
a shared, load-bearing lock without removing the duplicated write semantics.

## Acceptance criteria

1. `promote`, `dismiss`, `defer`, `unpark`, `snooze`, and `amend` accept
   `--json`; on success stdout is structured JSON containing the fully resolved
   resulting card state. `snooze` matches the WebUI's optional reason/revisit
   inputs, while the existing human `defer` remains strict. `amend` accepts
   only an open card under the write lock. Their existing human output remains
   the default.
2. `show <id>` returns one resolved card, in human form by default and as
   structured JSON with `--json`.
3. Stable documented exit codes distinguish usage/validation (2), status
   precondition/CAS refusal (3), unknown id (4), uninitialised store (5), and
   lock timeout (6).
4. A subprocess race of two CLI transitions on one open card returns one
   success and one status-precondition refusal; the resolved card has exactly
   one resulting status event.
5. The implementation changes only this monorepo; `shipwright-webui` remains
   out of scope.

## Doubt-review remediation

- JSON-mode `dismiss` preserves the existing WebUI allowance for an absent or
  blank reason, without weakening the human command's required rationale.
- JSON-mode `snooze` permits an omitted date, but rejects a supplied date that
  is today or earlier in UTC before it writes an event; success cannot resolve
  immediately back to `triage`.

## External-code-review remediation

- The machine-contract tests now compare every JSON transition result and an
  amended `show` result with the canonical resolver output, not selected fields.
- The two-writer race uses a test-only process barrier immediately before the
  real lock acquisition, proving the in-lock precondition instead of relying on
  scheduling luck.
- `amend` already resolves an unknown id in `resolve_amend_residence` before
  its optional status check, so its existing subprocess regression test confirms
  exit 4; `StatusPreconditionError` subclasses `ValueError` and is already
  handled by the shared CLI error mapper.
- A supplied snooze date is now compared to the UTC day *inside* the status
  lock, so lock contention across midnight cannot turn a successful response
  into an already-due `triage` card.
- Optional JSON-mode reasons now map absent/blank values to `null`, while every
  supplied value goes through the established single-line, 500-character
  sanitizer before a write.
- Printable whitespace-only optional reasons remain absent, but control-only
  whitespace is explicitly rejected before that normalization.

## Internal Plan Review (opus-plan-reviewer)

- **Ran:** yes
- **Severity:** low
- **Summary:** The plan is complete and internally consistent; it preserves
  human CLI behavior, defines machine contracts, keeps validation and results
  inside the existing lock, and covers the WebUI-equivalent boundary cases.
- **Findings:** none
- **Known limitations:** none
- **Status:** clean

## Affected boundary

| Producer | Consumer | Format | Verification |
|---|---|---|---|
| `triage_cli.py` transition commands | Command Center follow-up | UTF-8 JSON stdout + exit status | CLI subprocess tests, including concurrent CAS refusal |

## Costs and boundaries

This slice adds no runtime cost to existing callers because human CLI behaviour
is unchanged and the WebUI is not modified. P2.34b will pay one Python process
startup per operator write and must visibly degrade when that engine is absent.

## Out of scope

No WebUI route, reader, lock primitive, storage format, or triage residence
logic changes in this iterate.

## External plan review

- **Provider:** OpenRouter (DeepSeek and OpenAI), both `revise`.
- **Integrated:** successful transition and amend responses now obtain their
  resolved item while the existing store lock remains held; the existing typed
  precondition, missing-store, missing-id, and lock-timeout paths map to the
  documented exits. JSON stdout is encoder-produced and diagnostics stay on
  stderr.
- **Declined:** a new CLI timeout option or a version/ETag on `show`; neither
  is required by the task and both would broaden the contract unnecessarily.

## Architecture review

- **Brief:** `.shipwright/planning/iterate/iterate-2026-08-10-p2-34a-machine-cli-transitions/architecture_brief.md`
- **Verdicts:** DeepSeek=approve · OpenAI=approve.
- **Smallest mechanism:** extend the existing CLI with JSON transition results,
  `show`, and stable exit codes; add no service, lock protocol, or persistence.
- **Reconciliation:** both reviewers confirm the selected one-writer boundary;
  the plan-review atomicity finding is integrated before code review.
