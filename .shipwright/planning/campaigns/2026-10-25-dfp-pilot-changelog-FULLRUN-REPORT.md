# Changelog pilot, stop 2: full model runs against the replay (2026-11-22)

Tree `e44847ea`. 43 runs, one per scenario and event-log layout, each played by an Opus subagent that followed
`SKILL.md` and its references in a throwaway project (local bare remote, `gh` stub), plugin loaded from a
directory export, never the installed cache. Each run is compared with the pinned replay trace.
Harness: `runscenario.py` (build, collect) with `fullrun_report.py`; run folders hold the prompt, the
self-report and the collected evidence.

## Result in one paragraph

The model follows the prose. Of 43 runs: 26 match the replay or the prose (A), 7 are harness or scope
artefacts (B), 0 are model errors against clear prose (C; one harmless note, F12), 8 hit prose that is
ambiguous or silent (D), 2 show the replay disagreeing with the prose (E). No run needs a change to the pinned
traces for the lock: every difference is either a prose defect, a replay defect, or a harness artefact. So
`approved_deltas.json` stays empty at the lock, and the findings below are the work list for P3 to P8.

Limits of this baseline: one run per scenario (not three); exit codes are self-reported and only the outcome
(refs, tags, PRs, release pages, gh calls, tree) is evidence; S11b, S12c and S16f inject their fault
differently from the replay; scenarios whose replay stops at one step show the model's later steps as extras.
Extra samples go where a later comparison (P7-op) disagrees.

## Per-run classes

- **A (26):** S10d S11al S12al S14bl S15l S16al S16cl S16dl S17al S1d S1dl S1l S1tl S2ad S2al S2g(legacy) S2gd
  S2ud S3bd S3d S4d S5ad S5bd S7ad S7bd S7cd.
- **B (7):** S11bl (fault injected by a hook), S12cl (remote refuses tag pushes, replay skips the push), S13l
  (event file from the replay's own step), S17bl (scripted answer was "stop"), S6d, S8d, S9d (the replay passes a
  fixed release date, the model uses today).
- **D (8):** S12bl, S2ul (F7), S14al (F3, F4), S14cl (F5), S16fl (F4), S18al, S18bl (F2), S19l (F11).
- **E (2):** S16bl (F8), S16el (F6).

## Findings, with the proposed decision

OBVIOUS = clear answer, decided without the maintainer. ASK = a genuine judgement call, with a default.

- **F1a (known D2) OBVIOUS.** `git push --tags origin main` run from the release branch also pushes the local
  `main` and publishes a tag that points at an unmerged commit (S10, S11a, S12a, S12b, S13, S18b, S19, S1l,
  S2g). Decision: from a feature branch push only the tag; push `main` only when the release is cut on `main`.
- **F1b DECIDED (operator, 2026-11-23).** In guided mode, should the tag reach the remote before the release PR
  is merged? No: the tag is pushed only after the release PR is merged (otherwise a failed release leaves a tag
  with no release). Today's behaviour stays frozen in the lock; the change lands in P4 with F1a, as an approved
  delta.
- **F2 (D12) OBVIOUS.** The preview question comes after CHANGELOG.md is written and the untracked drops are
  deleted, so Cancel leaves a written section and lost input (S18a, S18b). Decision: ask Accept/Edit/Cancel after
  the dry run and before the real write; Edit changes the drop and repeats the dry run.
- **F3 (D7) OBVIOUS.** `gh pr create` (SKILL 330) runs before the branch is first pushed (346) and fails
  (S14a). Decision: push the branch right before the PR.
- **F4 OBVIOUS.** Step 7 is silent on a failed PR or tag push; the models stopped, the replay carries on to a tag
  on the remote with no PR (S14a, S16f, S12c). Decision: a failed PR creation or tag push stops the release
  before any tag reaches the remote; align the replay.
- **F5 OBVIOUS.** The trunk is assumed to be `main` (SKILL 327, 333, 365); with `master` the literal prose fails
  (S14c). Decision: take the default branch from the remote and use it everywhere.
- **F6 OBVIOUS (replay).** The replay ignores the `&&` stop rule of SKILL 341 and goes on to push the tag after
  a rejected push (S16e). Decision: the prose stands; fix the replay.
- **F7 DECIDED (operator, 2026-11-23).** The prose says both "standalone: no `orchestrator.py update-step`"
  (SKILL 58-60) and calls it unconditionally (407-409). Two runs called it and left three stray changes (S12b,
  S2u). Decision: the CLI (code) owns the check and is always used; the skill prose never calls
  `orchestrator.py update-step` itself and must not contradict itself. P5 removes SKILL 407-409 and the
  `--restore` call after it; the check moves into the code path of Steps 6/7 (consistent with plan item A5).
- **F8 OBVIOUS (tool).** A refused evidence refresh leaves staged files, while compliance-evidence.md:62-64 says
  the tree is restored (S16b). Decision: the tool unstages what it staged when it refuses.
- **F9 OBVIOUS.** The cherry-pick fallback writes the bullet into legacy `[Unreleased]`, so it misses the
  release it was written for (S10). Decision: write a drop file instead.
- **F10 DECIDED (operator, 2026-11-23; corrects the earlier default).** The closing steps (C2, C3, phase
  history) leave `build_dashboard.md` and `shipwright_run_config.json` modified and `session_handoff.md`
  untracked after the last commit, in the main checkout after an autonomous merge. Decision: the release does
  NOT commit them; the closing steps must leave the tree clean. The dashboard and the handover note are derived
  stop-hook snapshots (`shared/scripts/lib/derived_snapshots.py`; `.gitignore`: tracked variants are produced
  only by iterate finalize, a derived snapshot is never committed). Per file, read from the code:
  `build_dashboard.md` is in `DERIVED_SNAPSHOTS` and in `RESTORABLE_SNAPSHOTS`, so after C2 the close step
  restores it to HEAD with `restore_derived_to_head` (or does not write it in standalone mode);
  `session_handoff.md` is in `DERIVED_SNAPSHOTS` but NOT in `RESTORABLE_SNAPSHOTS` (its canon marker is run
  identity, and `restore_derived_to_head` skips a modified run-written path and every untracked one), so a
  restore cannot clean it: in standalone mode C3 does not write it; `shipwright_run_config.json` is in neither
  list: it is real tracked config (the run-config project marker of `shipwright_paths.py`), not a derived
  snapshot, so no restore applies: in standalone mode the `phase_history` append is a run-state write and is not
  made (SKILL 60 says only "skip pipeline state updates"; P4 makes the `phase_history` rule explicit, the same
  rule as F7); where a pipeline owns the run
  state, its phase-completion writer (`single-session-apply` in a driven run, SKILL 54-56) owns it; P4 names
  the exact writer. Lands in P4 (the closing summary / close-phase unit), with a
  test that the tree is clean after `close-phase`.
- **F11 (D9) OBVIOUS.** `--from` is advertised (SKILL 26) but no script takes it (S19). Decision: remove it.
- **F12 OBVIOUS.** Two runs printed the version question after the dry run had started (S12b, S16f); harmless.
  The prose stands; a CLI that owns the gate answers (plan item A2).
- **F13 (D15) OBVIOUS.** `--body "## Changelog\n\n{entry}"` passes a literal backslash-n; the models silently
  fixed it, all 14 bodies were right. Decision: `--body-file`.
- **F14 OBVIOUS.** The `SHIPWRIGHT_RUN_ID` export does not survive separate shell calls, so the canon marker is
  silently missing (S12b, S2a, S14b, S18b, S19). Decision: the CLI sets the id (plan item C2).

Ruled out as model behaviour: every `gh --version`, `gh auth status` and `gh release view` call came from the
scripts; the model made only `gh pr create` and `gh pr merge`.

## Pinned failures the runs reproduced (the model matched the replay)

P1 drops layout: the event drop file is never staged, the audit refuses, no tag (S1d, S2ad, S2gd, S2ud, S3bd,
S6, S8, S9). P2 a project without `decision-drops/` or `planning/adr/` aborts the release commit (S1dl). P3
tracked drop deletions are not in the Step 6 pathspec (S1t). P4 a "BREAKING" drop under a `fix` commit gets a
patch bump (S3b). P5 the release audit leaves an untracked `triage.jsonl`.

## Decisions (operator, 2026-11-23)

The three ASK findings are decided; none blocks the lock, which freezes today's behaviour, and each fix lands as
an approved delta in its unit.

- **F1b:** in guided mode the tag is NOT pushed before the release PR is merged (a failed release must not leave
  a tag with no release). Lands in **P4**, together with F1a.
- **F7:** the CLI owns the check and is always used; the skill prose never calls `orchestrator.py update-step`
  itself and does not contradict itself. **P5** removes SKILL 407-409 and its `--restore`; the check moves into
  the code path of Steps 6/7 (P3/P4 build it).
- **F10 (corrects the earlier default "run them before the event commit and commit them in the release"):** the
  release never commits `build_dashboard.md`, `session_handoff.md` or the run-config bookkeeping; the close step
  leaves the tree clean (per file as in F10 above: restore the dashboard to HEAD, do not write the handover note
  or the `phase_history` entry in standalone mode). Lands in **P4** (the closing summary / close-phase unit).
