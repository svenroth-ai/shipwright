# Requirement gate bypasses closed (campaign unit U6)

Campaign `2026-10-07-finalization-claims-hardening`, unit U6. FR-01.11 (AC03, AC04 modified: fixes are no longer exempt). `lib.fr_gates.run_fr_gates`, the one entry point the `record_event` CLI and F5b `finalize_iterate._record_event` both call, gains two arms: `lib/spec_impact_gate.py` (moved out of `record_event.py`, which shrank 777 to 731 lines) and `lib/change_type_diff.py` + `lib/change_type_paths.py`. The FR-existence arm fails closed on specs that parse to zero requirements. F11 `check_spec_impact_recorded` no longer skips `intent: bug`.

## The rules

1. **Spec impact, every intent.** A feature, change or bug names its FRs or records `spec_impact: none`. Every recorded `none`, with or without FRs, carries a one-line justification (`spec_impact_justification`, else `none_reason`; one line of text, max 280 chars, same validator as `none_reason`) and a `spec_impact_reason_code` from the closed `spec_impact_none` family: `behavior-preserving`, `restores-specified-behavior`, `docs-only`, `tests-only`, `tooling-only`, `infra-only`. Intent-less events are not asked to classify.
2. **FR existence.** Specs present but zero requirements parsed: a declared id is refused (`fr_gate_specs_unparsed`). A collector crash on present specs reads as "found, nothing parsed", not "no specs". No planning specs at all still allows.
3. **No-FR label vs the diff.** Only when no FR is named. Diff = narrowest merge-base among remote trunk names (`origin/HEAD`, `origin/main`, `origin/master`), local `main`/`master` only when no remote name resolves, to the working tree, with untracked files and `-M` (both sides of a rename and every deletion judged). Every label covers docs, tests and Shipwright's records. `docs` covers only those (not `.mdx`, which is executable). Generic projects keep runtime code outside every label. In the Shipwright monorepo (`shared/scripts` + `.claude-plugin/marketplace.json`), `tooling`/`infra`/`compliance` also cover `plugins/**`, `shared/**`, `scripts/**`. Not a git repo: WARN and allow. git present but no trunk, or git fails: refused (`change_type_diff_unavailable`).

## Accepted limits

1. Classification is by path: an untracked file is judged by where it is, not by what it contains.
2. Old events are not re-gated (forward-only). Sibling units that finalize after this merges must add `spec_impact_reason_code` to a `spec_impact: none` event.
3. There is no per-project override. A consumer layout the built-in rules do not cover must link its FR (architecture review).
4. Markdown under a runtime tree (e.g. a content collection rendered as pages) counts as docs.

## Architecture Review

External, `--mode architecture` over `architecture_brief.md`: GLM **revise** (the parser read `unknown` because of a typo in GLM's own verdict line, `SHIPWREIGHT_VERDICT`), GPT **revise**. Neither rejected. Both: take option A but drop the per-project `change_type_paths` extension key until a real project needs one (a permanent exemption contract consumers come to depend on). **accepted-and-fixed**: key removed. GLM also suggested dropping shape detection. **rejected-with-reason**: the brief requires project-aware rules tested on monorepo and WebUI shapes, GPT accepts built-in rules "for the two required project shapes", and detection is one stat of two marker paths.

## External-Plan-Review-Findings

| Reviewer | Finding | Disposition |
|---|---|---|
| GPT high | Monorepo set `plugins/**` + `shared/**` broader than the brief's `shared/scripts/**` + `scripts/**` | rejected-with-reason: measured on 167 historical no-FR events, the narrow set refuses 82 (49%), nearly all for `plugins/*/scripts/**`. That is the "would refuse every legitimate tooling change" outcome the brief rules out |
| GPT high | Config extension read from the working tree lets a change exempt itself | accepted-and-fixed: superseded by the architecture review, which dropped the key. Test: a run-config glob changes nothing |
| GPT medium / GLM medium | Narrowest merge-base: a local `main` at HEAD hides committed work | accepted-and-fixed: remote trunk names first, local only as fallback; the chosen ref is named in the refusal. Test: local main advanced to HEAD still catches a committed runtime change |
| GLM medium | Old inline CLI check may double-run | rejected-with-reason: removed from `record_event.main`, which now calls only `run_fr_gates` |
| GLM medium | Untracked-path spoofing | accepted (documented): limit 1 above |
| GLM medium | In-flight events without the code | accepted (documented): limit 2; reported to the orchestrator |
| GLM low | Shape fingerprint / add-only config | accepted-and-fixed: config key removed; shape is in every refusal message |
| GLM low | Rename across labels | accepted (already tested): `src/...` to `docs/...` under `docs` is refused |
| GLM low | Two names for the justification | rejected-with-reason: `none_reason` is accepted for parity with F11's existing reader; F5b documents `spec_impact_justification` |
| GLM low | Crash vs zero-parse codes | rejected-with-reason: same remedy (repair the spec table), same code |

## Self-Review

1. Spec Compliance: pass. Every U6 clause is implemented and tested.
2. Error Handling: pass. git faults refuse; not-a-repo warns; a collector crash fails closed.
3. Security Basics: pass. Argv-list git, no shell, no self-widening exemption.
4. Test Quality: pass. 47 tagged tests on real git repos; existing fixtures updated with the code.
5. Performance Basics: pass. A few bounded git calls, only on the no-FR branch.
6. Naming & Structure: pass. New modules < 300 lines; `record_event.py` shrank; `iterate_checks.py` length unchanged.
7. Affected Boundaries: pass. CLI to `shipwright_events.jsonl` to F11 round-trip probed.
8. Test Hygiene Probe: pass. No findings.

## Confidence Calibration

Boundaries: the event JSON (`spec_impact_reason_code`, producer CLI + F5b, consumer F11) and the git diff (producer git, consumer the classifier).

- Probe 1, history replay (finding): 167 historical no-FR `work_completed` events with `changed_files`, run through the draft rules. 18 refused, mostly gaps: `.trivyignore.yaml`, `shipwright_*_config.json` / `audit_config.json`, compliance-owned CI workflows, tests under `docs`. Fixed.
- Probe 2, history replay after the fix (no new finding): 4 refused. Three are `docs`-labelled runs that edited code (correct refusals), one is a corrupt record (`changed_files: [12]`).
- Probe 3, round-trip (no finding): `record_event` CLI writes a bug event with `spec_impact: none` + code, F11 reads it back and passes. The gate against this worktree's own diff: `tooling` passes, `docs` refuses with the 7 `.py` paths named. F5b `_record_event` in a WebUI-shaped repo with a runtime edit under `tooling`: refused, nothing written.
- Asymptote: two consecutive no-finding probes. Not probed: shallow clones (no merge-base reads as unavailable and refuses, by construction), a project inside a larger repo (prefix rebase reused from `requirement_impact_git`, tested there).

## External-Code-Review-Findings

| Reviewer | Finding | Disposition |
|---|---|---|
| GPT high | `**/*.mdx` as docs lets executable pages bypass | accepted-and-fixed: `.mdx` removed from docs; test |
| GPT medium | Justification coerced through `str()` (booleans, lists, multiline pass) | accepted-and-fixed: `is_valid_none_reason` validator; parametrized test + F5b-path test |
| GLM medium | `none` branch also applies when FRs are present; docs said "with no FRs" | accepted-and-fixed (docs): every recorded `none` is answered, which matches F11 (it already demands the justification for any `none`); F5b.md, F7.md, AC03 say so |
| GLM low | `rev-list` failure read as "no ordering" | accepted-and-fixed: a non-zero `rev-list` raises `DiffUnavailable` with git's stderr |
| GLM low | Nested `packages/*/docs/` not covered | accepted-and-fixed: `**/docs/**` added; test |
| GLM low | Collector-crash test should pin the positive path | accepted-and-fixed: asserts the parsed id set before patching |
