## Step 3.4 — Diff-Driven Risk Re-Check (runner contract)

**The gap it closes.** A campaign unit classifies complexity exactly once, at
runner Step 2, from the sub-iterate spec **text**, before any code exists.
`classify()` takes `(message, sync_config_path, project_root)` and detects risk
with `detect_risk_flags(message)` — a regex sweep over that message. The four
*diff-driven* detectors in `risk_detectors.py` are imported by
`classify_complexity` but never called by `classify()`; their documented caller
is the **Stage-2 Repo Scout** (`iteration-planning.md`, Quick Scout step 3),
which the runner never reaches. So `cross_component`,
`touches_ci_supplychain` and the file-pattern halves of `touches_io_boundary` /
`touches_build` are *structurally* unable to fire for a campaign unit.

This is the same gap **3f-bis** already compensates for on the orchestrator
side, and for the same stated reason. 3f-bis can only protect what happens
*after* the runner returns; Step 3.4 protects what happens *inside* it.

**Two consequences, and they differ.** `check_ci_supplychain_ack` applies at
EVERY complexity and recomputes the flag from the diff, so a workflow-touching
unit **hard-fails its own F6-verify** with an error naming an artifact nobody
told it to produce. `check_integration_coverage` demands a `category:"integration"`
behavior in the F5c ledger for the same diff. A unit that never learns the flag
does not know to write one, and until 2026-08-01 that gate also green-SKIPped
below `medium`, so an under-classified unit reported green without evaluating.
That skip is gone (the gate now reads the ledger at every tier), but the unit is
still blind: it cannot produce coverage for a flag it was never told about, and
the recorded tier stays wrong. One dies loudly; the other passes quietly. Step
3.4 fixes both by re-deciding from the real change set.

**The change set is the working tree.** The runner commits at F6, *after* this
step, so a `base...HEAD` range is empty here. The CLI therefore diffs
`base_ref` → working tree (committed + staged + unstaged) and unions
`git ls-files --others --exclude-standard` — a brand-new hook file appears in no
diff at all. Getting this wrong reintroduces the exact blindness being removed.

**Orchestrator handling of a CI escalation.** The runner returns
`status: "escalated"` with `reason_code: "ci_supplychain_requires_operator"` and
a non-empty `ci_paths`. No special-casing is needed at 3f: `escalated` is
already a valid status (`autonomous_loop.VALID_STATUSES`), the whole result is
persisted to `runs/{loop_id}/{id}/result.json`, and any non-`complete` status
exits 3 → **STRICT-STOP** — no merge, no next unit, already-merged units stay
durable. `campaign_progress.py` counts escalated units separately from failed
ones, and `failure_reason` carries the escalation `reason` into `loop_state.json`,
where the orchestrator (and the WebUI board) read it. The operator resolves it by recording the acknowledgement with
`record_ci_supplychain_ack.py` — naming the posture decision the change agrees
with — and re-running the unit. **The re-run must terminate, and that is why the
CLI is ack-aware:** Build re-creates the same CI edit, so a re-check that only
looked at the diff would escalate again, forever. A recorded ack *for this run id*
therefore exits 0 while still reporting the flag and `ci_paths`. Presence is all
Step 3.4 checks; `check_ci_supplychain_ack` still validates the ack's content, its
run binding and the diff fingerprint at F11, so a bogus file buys nothing and a
previous run's ack cannot license this diff. **The runner must never write that ack
itself:**
it certifies that a human reasoned about a trust-boundary change, and a runner
authoring its own permission slip is precisely the failure the gate exists to
catch (webui #285 reversed an accepted-risk posture unnoticed *through* a full
medium iterate with external plan review). **This is now checked, not only
stated in prose** (trg-33d30377 / PR #718 — a runner called the CLI directly
anyway, and run binding + content binding validated its self-written ack
perfectly): `record_ci_supplychain_ack.py` refuses outright while
`SHIPWRIGHT_LOOP_UNIT_ID` is set in its own process environment — the variable
an active autonomous-loop unit's process carries (this campaign loop's own
sub-iterate runner, or `shipwright-build`'s unrelated `--autonomous` loop
around its `section-builder` — both set the same var, and refusing either is
correct: no unattended unit should self-author this ack) and an operator's
own terminal does not. **This is a process-identity heuristic, not a
cryptographic guarantee** — it distinguishes "am I the runner process" from
"am I not," nothing stronger; it cannot distinguish two humans, or catch a
runner that unsets the variable before calling the CLI. Propagation to the
runner's own Bash-tool subprocesses goes through
`capture_session_id.py`'s `CLAUDE_ENV_FILE` write, the one channel this
codebase uses to guarantee a hook-observed env var reaches a subprocess the
Bash tool spawns (mirrors the pre-existing `SHIPWRIGHT_SESSION_ID` handling
there) — additionalContext alone (text shown to the model) does not reach a
subprocess's real environment. **Operators: do not `export
SHIPWRIGHT_LOOP_UNIT_ID` yourself when resolving an escalation** — step 3b's
`export` is this orchestrator's own shorthand for what the harness sets on
the *spawned runner's* process, not an instruction to type in your own
terminal. If you are debugging inside a worktree where it might already be
set (e.g. copied from 3b, or inherited from a prior shell), `unset
SHIPWRIGHT_LOOP_UNIT_ID` before running `record_ci_supplychain_ack.py` — the
guard cannot tell that export apart from a real runner's. The CLI also
accepts `--commit <ref>` to acknowledge a CI change that is already
committed (the working-tree fingerprint the runner uses pre-F6 sees nothing
once it is), so the operator's path stays reachable after the fact too. A
squash-merge or rebase that rewrites the committed SHA after the ack is
recorded invalidates `provenance_ref` along with it — re-record post-rewrite,
the same way a content-fingerprint change already requires.
