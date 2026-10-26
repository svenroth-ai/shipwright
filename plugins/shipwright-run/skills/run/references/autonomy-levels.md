# Autonomy Levels

## Guided (default)

Interactive process through all phases including Build and Test,
with confirmation between phases and request for approval of fixes.

- **Between phases:** Pipeline asks "Continue to next phase?"
- **Build:** Code review findings presented via AskUserQuestion (Accept/Decline/Defer per finding)
- **Test:** Failures reported. Auto-fix only with explicit --fix flag.

## Autonomous

Interactive process through Spec and Design with autonomous Build and Test
including fixes. Deploy stays interactive.

- **Spec & Design:** Same as Guided — user input shapes architecture
- **Between phases:** Pipeline proceeds without asking
- **Build:** Code review findings are auto-fixed immediately. All findings treated as accepted.
  Fixes logged in decision log.
- **Test:** Failures trigger auto-fix automatically (structured debugging, up to 3 retries).
  No --fix flag needed.
- **Changelog:** Version bump and changelog entry accepted automatically, no review prompt.
  PR is created and auto-merged.
- **Deploy:** Same as Guided — PROD confirmation always required

**Always interactive regardless of level:**
- Destructive database operations (always require confirmation)
- Rollback decisions (always require confirmation)

## Unattended

Autonomous, with no human reachable. **Rule:** every site keyed on "autonomous" treats
`unattended` the same; the only differences are that an `orchestrator-approve` gate with no reviewed
`unattended_answer` (`shared/config/gate_catalog.json`) escalates instead of asking
(`auto-default` gates proceed, `hard-stop` always stops),
and that no override of a failed phase gate is accepted (nobody to decide it).

- **Gates:** only `design.preview-approval`, `design.review-loop-finalize` and
  `design.upload-screen-mapping` carry an answer; the master/CLI applies it after the
  package-hash and FR-coverage checks (from U3). Constitution-locked, `hard-stop` and denylisted
  gates always escalate.
- **Build (from U3):** sequential; parallel `section-builder`s need `allow_parallel_builders: true`.
- **Start:** only from an approved Brief package (from U3 a plain seed is refused at preflight; today `write-config` accepts the value).

## Configuration

Set in `shipwright_run_config.json`:
```json
{
  "autonomy": "guided"
}
```

Per-invocation:
```
/shipwright-run --autonomous "Build a todo app"
```
