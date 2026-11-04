---
run_id: iterate-2026-11-04-autonomous-run-gates
type: feature
complexity: medium
risk_flags: [touches_public_api]
---

# Autonomous runs decide the remaining gates by rule (e2e run 20 findings)

Source: e2e run 20 (autonomous pipeline run, brief package with approved mockups). After PR #992 removed the Plan/Build
screen-vs-section gates, the run still asked the person five kinds of question that the run itself should decide.
Common rule: an autonomous run (`brief_package` in `shipwright_run_config.json`, or autonomy `autonomous`/`unattended`)
decides by documented rule and records the decision; a conflict the rule cannot decide stays a question; interactive runs are unchanged.

## Acceptance criteria

1. **Per-screen viewport (Test, screenshot check).** Each screen is captured at its own viewport: a `viewport` key on the
   package screen-map entry (a screen-routes `viewport` is an error: test wiring cannot pick it), else a declaration of the mockup (shipwright-viewport meta,
   numeric viewport meta width, a `phone-frame`/`mobile-frame` element in the markup, leading comment "phone width NNNpx"),
   else 1280x800. Both shots of a screen use the same size; `viewport` and `viewport_source` are recorded per screen; an
   invalid declaration is an `error` for that screen only. The tolerance and the metric are unchanged.
2. **Autonomous override rule (Test gate).** `autonomous_override.py` allows an override of a failing screenshot check without
   a question only in an autonomous run, when the gate raised nothing but the screenshot finding, the check really ran
   (`fail`, fresh capture, standard tolerance), every accepted cause cites an ADR in `decision_log.md` or a brief-package
   file, and every failing screen is within the tolerance without those causes (same ratio the tool recorded). Otherwise it
   answers `allowed: false` with reasons and the question stays. The override itself is the ordinary one
   (`--override-reason`, recorded in `validation_overrides[]`; apply still refuses `unattended`). The Test phase fixes plain
   CSS deviations itself in an autonomous run.
3. **Non-UI capabilities (Design).** `record-non-ui-frs.py` writes unmapped FRs whose `brief.md` section has a `Source:` line that names no Mockup
   (or states `UI: none`; `UI: none` wins over the word "screen" in prose) under `## Non-UI FRs` with ONE decision-log entry, in an autonomous run; a capability with neither
   a screen nor such a note, or whose section names an unmapped Mockup, is returned in `ask[]` (exit 1). Interactive runs untouched.
4. **Size target vs behaviour (Build, run-20 gate 28).** In an autonomous run a section's "under ~N lines" is a soft
   target: the spec-reviewer passes a split into further modules and rejects cut behaviour / raised limits.
5. Docs (`docs/hooks-and-pipeline.md`, `docs/guide.md`) and the skill/reference prose describe the above.

## Affected Boundaries

- `screenshot_check.py` -> `screenshot_capture.mjs`: jobs.json gains an optional per-job `viewport` (producer: Python, consumer: node).
  Probed against real Chromium on run 20's project (phone screen 07 captured at 390x800, ratio 0.58 -> 0.25 with the
  remaining causes unchanged).
- `shipwright_test_results.json` `screenshot_check_accepted_causes` (writer: Test phase prose; reader: `autonomous_override.py`).

## External review findings

External code review (GPT + GLM) and plan/architecture reviews, with disposition:

| Finding | Disposition |
|---|---|
| viewport meta `width` with other digit counts or `390.5` silently ignored | accepted-and-fixed (full value parsed; invalid = per-screen error; `device-width` declares nothing) |
| viewport read from the built file | accepted-and-fixed (approved side only) |
| phone-frame only as the body's outermost element | rejected-with-reason: a nested frame is a component of a desktop page, not the page size |
| `_map_entry` uses the NN prefix as list index | rejected-with-reason: same rule `_approved_for` already uses to pick the approved screen |
| `UI: none` vetoed by the word "screen" in prose | accepted-and-fixed (`UI: none` wins; a concrete mockup/wireframe/.html/figma reference still contradicts it) |
| Source-less section recorded as non-UI / only explicit `UI: none` | rejected-with-reason: a section with no `Source:` line stays a question; a `Source:` line naming no Mockup is the specified rule and the recorded `why` says so |
| null tolerance crashed the rule | accepted-and-fixed (early refusal + test) |
| neutralised pair has no provenance (plan, code, doubt) | accepted-and-fixed in part: bound to the check's real pair (must reproduce the recorded ratio; no real capture of any screen; no byte copy of the opposite capture; no shared pair); residual: the pair is agent-produced, docs say consistency check |
| ADR/brief source need not relate to the cause | accepted-and-fixed in part: verbatim quote required for ADR and brief sources, heading not quotable, `evidence/` refused; residual: an agent can commit its own ADR first |
| apply did not re-run the rule | accepted-and-fixed (`autonomous_hook.by_rule_refusal`) |
| png_compare not found in the installed plugin cache | accepted-and-fixed (`_png_compare`, version-aware) |
| prose-only override rule instead of code (architecture, GLM) | rejected-with-reason: a prose rule is what left the question open in run 20; the code check keeps a real failure from passing silently |
| guided run with a brief package counts as autonomous | accepted: the specified common rule; stated in the guide |
