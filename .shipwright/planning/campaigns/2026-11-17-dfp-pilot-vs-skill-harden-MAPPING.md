# The changelog pilot and `skill-harden`: one shape, two depths

Written 2026-11-17. Source: `shipwright-skill-check` (`skills/skill-harden/`, `docs/harden-flow.md`, `scripts/derive_requirements.py`, `classify_acs.py`, `trace_check.py`, `derive_scenarios.py`, `compare_runs.py`, `baseline/content-creator/`), read but not run. Status: a proposal; nothing in the campaign `dfp-pilot-changelog-p1-p2p` is changed until the operator says go.

## 1. Same idea

Both start from the **old** skill, turn what it demands into numbered requirements, ask the owner only what the text cannot answer, tie each requirement to a check, and compare the rebuilt skill against the old one. Only what a script verifies counts as held.

| Step | skill-harden (outside, non-technical users) | Pilot (this repo, converts a skill into a CLI) |
|---|---|---|
| Read the old skill | `derive_requirements.py`: requirements and ACs with source anchor (file, heading path, hash) | P0: `inventory.json` (instructions per section), `truth_table.json`, `subprocess_map.json` |
| Sort | `classify_acs.py`: ask / mechanic / judgement / text | P0 classes: mechanic / judgement / outward command (target `keep`) / text pin |
| Ask the owner | the grill: `grill.json`, few questions in one batch, suggested answer each | stop 1: ten questions, each with a proposed answer (section 3a of the brief) |
| Tie to a check | `trace.json`: `check` = test, text, scenario, or null (gap) | promise list and pins: each promise bound to a test through the driver interface |
| Proof status | passing, failing, dangling, proposed, not-run, gap | green, red, `oracle: trace`, orphan |
| Compare old and new | `compare_runs.py`: scenario answers of old and new, majority per scenario | golden traces (executed in a scratch project) plus L3 model runs, differences in `approved_deltas.json` |
| Freeze | `baseline/` folder inside the skill | lock file: hash of traces, promise tests, prose copy |
| Change the skill | no: harden writes only `baseline/` | yes: P3 to P5 move the steps into `release.py` |

## 2. Where they differ, on purpose

- **Executed versus asked.** The pilot runs the real scripts against a scratch project with a bare remote and a `gh` stub and records the command trace. `skill-harden` asks the model what it would do in a staged situation. The two answer different questions: traces prove flows that code executes; decision scenarios prove rules only the model follows. The pilot's L3 runs are the decision-scenario half and have no tool of their own yet. In `skill-harden` the scenario half is built but not yet run (content-creator: 9 scenario-bound ACs, none run).
- **Rebuild versus harden.** The pilot rebuilds the skill; `skill-harden` leaves it untouched.
- **Audience.** `skill-harden` hides ids and anchors from non-technical users; the pilot report is for the operator.

## 3. What each side learns from the other

For `skill-harden` (from the pilot):
1. **Find the bindings by breaking the prose, not by word match.** Replace the skill text by a placeholder, run every test root, and every test that fails is a pin. Word matching ("shares a word with a test") proposes; breaking proves.
2. **A fourth class: outward command.** A literal command that is neither judgement nor safe to move into code (`gh pr merge`, an upload). It stays one line in the skill and gets a check on its argv.
3. **Recorded traces** for a skill that calls scripts: replay in a scratch project, compare, freeze by hash.
4. **A promise lock:** hash of the test's normalised AST and its fixtures, so a promise test cannot be weakened silently; and `approved_deltas`: every accepted difference is an entry with a reason.
5. **A seeded-regression check:** a suite is only trusted if it catches faults put in on purpose (the pilot plants three; the mutation check of `skill-harden` on its own code is the same idea).

For the pilot (from `skill-harden`):
1. **One AC shape** (id, plain sentence, source anchor, class, check, status, decision) so the promise list and `trace.json` are the same data.
2. **The six statuses**, including `dangling` (the named test does not exist) and `proposed` (never run, never counted).
3. **"No script named" is not "uncovered".** Say "not obviously covered" until a reviewer has looked (two of their first candidates were already held).
4. **The scenario schema** of `compare_runs.py` (`id`, `seeds`, `setup`, `ask`, `expected.decision`) for the judgement questions the model answers, instead of an ad-hoc format at stop 2.
5. **Anchors** (file, heading path, content hash) on every inventory entry, so a later skill edit can be traced to the requirement it touches.

## 4. Proposed campaign changes (apply only on the operator's go)

| Unit | Change | Cost |
|---|---|---|
| P2p | `promise_list.json` uses the `trace.json` AC shape and the six statuses; each entry carries the source anchor | small |
| P2b2 or P2p | the judgement questions of the changelog (Step 5 preview, version suggestion, out-of-sequence) are written as `scenarios.json` in the `compare_runs.py` schema, so P2-op and P7-op run and compare them with the same tool | small to medium |
| P7 | the finished conversion also writes `baseline/trace.json` in the shared shape as an export, so `skill-check` can read it | small |
| P0 report | add a one-line note that the outward-command class is now shared | none |

Not proposed: moving the pilot's planning artefacts into the skill folder; running the pilot through `skill-harden` itself (the pilot rebuilds, the other only hardens).
