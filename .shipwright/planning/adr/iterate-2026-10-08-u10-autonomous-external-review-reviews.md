# External review that could not run: captured, announced, re-run (campaign unit U10)

Campaign `2026-10-07-finalization-claims-hardening`, unit U10. Operator decision (BRIEF §5.2): an autonomous run MAY continue when the external review cannot run, never silently, and no env-var waiver exists.

## The rule

For the two passes `external_review.py` produces (`plan`, `external_code`), a row closed `reason_code: unavailable` must be backed by the adapter's captured output in the run directory, found by convention from the canonical basenames (`lib/review_payloads.CANONICAL_PAYLOAD_BASENAMES`): the raw stdout file, or its `<stem>.stderr.txt` sibling. Precedence: when the raw file holds a JSON object (the first one opening a line; UTF-16 BOM decoded) it decides alone and must be the failure envelope (`success` is JSON `false` or `degraded` is JSON `true`); otherwise a non-empty stderr file is the evidence. A successful reply refuses the claim whatever stderr says; stray non-JSON stdout alone is not evidence. Both redirects truncate per call, so the capture speaks for the last attempt. When `reviews.json` is in the commit, the capture is read from that commit, byte for byte; there is no separate gitignore exemption. `record_review_pass.py record` applies the same rule at write time (working tree). `unavailable` on an internal row keeps its existing meaning (no adapter to capture).

## Loud, not silent

- F11's passing review-record line names every `unavailable` pass.
- `shared/scripts/tools/review_unavailable_note.py` prints `none` or `N (passes) - did NOT run (unavailable); adapter error: <paths>` (paths only, never content) for the PR body (F11.md template) and F12 (`Unavailable:` row). `--file-triage` files ONE `iterate`-source card per run (`dedupKey review-unavailable:<run_id>`, no recency window) and appends its id; a second call returns the open card. An invalid capture prints `INVALID`, exits 1 and files no card; a filing failure exits 1.
- Campaign: the runner puts the line in `result.json` `reviews.unavailable_note`; the PR opener pastes it; campaign-end step 5 prints every non-`none` note.

## Medium+ floor in a campaign

The runner has no Agent tool, so its `code` row is `not_run --reason-code delegated-to-orchestrator` until campaign-mode 3f-bis promotes it to `completed` (or STRICT-STOPs, no merge). Normally `external_code completed` carries the medium+ floor until then; with `external_code unavailable` the floor could never pass at the runner's own F6-verify, so "the run continues" was impossible. The floor now accepts exactly that pair (`external_code` `unavailable` + `code` `not_run` `delegated-to-orchestrator`). Every other both-not-run pair still fails (`missing-keys` + delegated included; tested).

## Accepted limits

1. `delegated-to-orchestrator` is not proven to come from a campaign context (same trust boundary as U3/U4); the floor relaxation needs a genuine captured adapter failure as well, which narrows it but does not close it.
2. A capture proves the adapter failed on its last call, not that the agent tried in good faith (e.g. a deliberately wrong `--diff-file`). The re-run card and the loud line are the backstop.
3. `close-missing --reason-code unavailable` is not checked at write time; F11 refuses it.
4. The note tool reads the working tree (it runs at F12/PR time); F11 reads the commit.
5. The re-run card is filed by the agent following the runner contract; F11 does not verify it exists (verifying would make the verifier read the triage store, and interactive runs must stay unchanged).

## Architecture Review

External, `--mode architecture` over `architecture_brief.md`: GLM **approve**, GPT **approve**. GLM (medium): option B (schema field + CLI flag) is the main risk; take A. **Accepted** - option A taken. GPT: canonical names become a compatibility obligation. **Accepted** - the basenames are already pinned by `CANONICAL_PAYLOAD_BASENAMES` and its tests.

## External-Plan-Review-Findings

| Reviewer | Finding | Disposition |
|---|---|---|
| GPT high | Non-empty stderr is not proof of failure; precedence unspecified | accepted-and-fixed: a parsed reply decides alone; a successful one refuses the claim regardless of stderr (tested) |
| GPT medium | A retry can leave a stale failure capture | accepted-and-fixed: both redirects truncate per call; a later success overwrites and refuses the claim (tested); documented in the module |
| GPT medium | Committed vs working-tree bytes unclear; ignored evidence | accepted-and-fixed: read from the commit when the record is committed (tested both ways); no gitignore exemption |
| GPT medium | Loudness relies on docs; no check that the card exists | partly accepted: invalid capture or failed filing exits 1; the F11 line names the passes; card existence not verified (limit 5) |
| GLM medium | Basenames must come from one constant | accepted: derived from `CANONICAL_PAYLOAD_BASENAMES` |
| GLM medium | Non-JSON stdout accepted as evidence | accepted-and-fixed: stdout alone is not evidence |
| GLM medium | Does the runner produce the stderr file? | accepted-and-fixed: `2>` added at every iterate-side `plan`/`external_code` site (runner, campaign Step 3.5, iteration-reviews, iteration-planning) |
| GLM low | One-directional check | accepted: stated in the module docstring |
| GLM low | record_review_pass net-0 hurts the message | rejected-with-reason: the message lives in the lib, full length; the file stays at 397 lines |
| GLM low | Dedup key per run vs per pass | accepted: one card per run, filed once after the last external pass |
| GLM low | Paths vs content in notes | accepted: paths only (tested) |
| GLM low | gitignore loophole | accepted-and-fixed: no separate exemption |

## External-Code-Review-Findings

| Reviewer | Finding | Disposition |
|---|---|---|
| GPT medium | The note tool ignored an invalid capture and could file a card for it | accepted-and-fixed: `INVALID`, exit 1, no card (deleted and overwritten-with-success cases tested) |
| GLM medium | Other invocation sites without `2>` | accepted: audited; build `code-review.md` and the plan-phase sites write no iterate review row |
| GLM low | String-typed `"false"` read as success | accepted-and-fixed (message): "not a failure envelope"; strict JSON types kept, as `external_review.py` writes them |
| GLM low | dedupKey field coupling | rejected-with-reason: the idempotency test round-trips through the real `triage.read_all_items` |
| GLM low | Note is not a gate | accepted: stated in the tool docstring |
| GLM low | Note reads the working tree | accepted: documented (limit 4) |

## Self-Review

1. Spec Compliance - pass: capture rule at F11 and write time; bare `not_run` still fails; PR/F12 line and one card; floor waits for the delegated cascade only with `unavailable`; no new prompts.
2. Error Handling - pass: unreadable committed capture fails closed; note tool exit 1 on missing record, invalid capture, failed filing; cp1252 console fixed.
3. Security Basics - pass: paths only; run_id safety before capture reads; argument-array git.
4. Test Quality - pass: 33 behaviour tests, all tagged FR-01.11; F6-verify then asked for an integration-category behaviour (the diff touches `campaign-mode.md`), so `test_review_unavailable_integration.py` runs the whole campaign shape end to end (real capture, CLI rows, F11 at medium, note + card read back, 3f-bis promotion).
5. Performance Basics - pass: two small reads per unavailable row.
6. Naming & Structure - pass: rule / gate / surface in three modules; capped files not grown.
7. Affected Boundaries - pass: real adapter output round-tripped; encoding and noise probes.
8. Test Hygiene Probe - pass: no findings.

## Confidence Calibration

Effective complexity `medium` (Step 3.4). Boundary: `external_review.py` stdout/stderr -> capture files -> `artifact_problem` / record CLI / F11 gate / note tool -> `triage.jsonl`.

- Probe 1 (real adapter, invalid OpenRouter key): GLM leg 401, Codex leg answered -> `success: true` -> `unavailable` refused at write time. Correct: the review ran.
- Probe 2 (real adapter, missing diff file): failure envelope, exit 1 -> accepted; note line + card `trg-...`; F11 at medium then refused on the code floor -> finding: the campaign shape could never pass F6-verify -> fixed (floor accepts unavailable + delegated), tested.
- Probe 3 (`uv run --project <missing>`): empty stdout, stderr 821 bytes -> accepted. Deleting the capture after recording -> F11 refuses.
- Probe 4 (encodings): UTF-16 success + stderr was ACCEPTED -> finding -> BOM decoded, now refused; UTF-8 BOM and CRLF fine.
- Probe 5 (noise): success followed by stray text, and preceded by stray text, both ACCEPTED -> finding -> first line-opening JSON object decides; re-probed.
- Probe 6 (re-probe of all shapes): no finding. Probe 7 (truncated reply + stderr, array JSON + stderr, empty object): no finding. Asymptote reached (two consecutive no-finding probes).
- Not probed: a capture larger than memory (adapter output is bounded by its own token caps); a non-UTF capture other than UTF-16 (decoded with replacement, so it can only fall through to stderr).
