# Campaign brief: intent pyramid (`intent-pyramid`), for operator review

Date: 2026-11-28 · Status: READY rev 10, nothing built.
- rev 2: operator answers of 2026-11-27, prior-art research, repo impact survey, drift prototype.
- rev 3: Opus plan review (verdict "ready after fixes"; H1-H5, M1-M5, L1-L4 worked in, see §12).
- rev 10 (2026-11-29): Opus review of rev 9 worked in (§12).
- rev 9 (2026-11-29): no upper limits on capabilities, scenarios or text length; split/merge rule instead, size shown as information.
- rev 8 (2026-11-29): Install = Claude Code only, Codex back to Extend; English capability names.
- rev 7 (2026-11-29): R1-R4 report bug units at the start; CAP-07 Einrichten (install + Codex), Erweiterung = profile rules only; SCN-09 now installation; naming proposal Neu bauen / Weiterentwickeln.
- rev 6 (2026-11-28): research on FR/AC views (§6a) and readable reports (§6b); U6d added; four report bugs verified.
- rev 5 (2026-11-28): element defined; 10 h run on demand only, release suite one test per scenario (U8c); scenarios SCN-06/07/03 widened, SCN-10 audit added; CAP-06 dissolved; Ship's Log links the intent; webui/leadwright iterates run from here; PR #1055 closed, its cut moves to U7.
- rev 4: operator decisions (Capability, placement in §8, confirmation variant A); Opus UX design of the confirmation (§4).
Absorbs the open rest of `atomic-frs` (its scope rule and `fr_split` tool are merged in #1025/#1027/#1031; the actual splits on shipwright, U2b webui and U3 re-measure never ran).

## 0. Goal
A person (product owner, domain side) can see what the product does and accept it without reading a single acceptance criterion (AC). The human owns the intent; the AI owns the ACs. Output is checked against the intent. An AC that drifts away from its requirement (FR) is found by code first, not by luck.

## 1. Evidence (measured 2026-11-27/28)
- `01-adopted/spec.md`: 22 FRs, 344 ACs, 1712 lines. webui: 42 FRs, ~312 criteria. leadwright: 60 FRs, ~266 criteria.
- Drift is real: FR-01.01 "End-to-end delivery pipeline" carries AC09-AC38 (23 present) about stack profiles and architecture rules, in two clusters: AC09-12 choosing/resolving a profile, AC13-38 architecture rules (lint, reviewer, plugin profile).
- **The existing code clusterer does not see it:** `fr_cluster_report.py --fr FR-01.01` -> "splittable = no ... stays whole" (all ACs share tests). Clusters show what is connected in code, not what belongs together in meaning.
- **A lexical prototype does** (scratchpad `drift-proto/drift_proto.py`, stdlib, 2.4 s): "term burst (S2) AND change-point (S5)" flags 19 of 23 drifted ACs and 0 of 8 pipeline ACs; routed per FR (>=6 flagged and >=25 %), only FR-01.01 is routed, the next FR has 5 flags. Per AC it is noisy (22 flags in 12 other FRs, ~1-2 real). **Limits (from review):** one case, labels set by the author, S5 needs the drift to be one contiguous block, and the per-AC fit signal (S1a) that an iterate-time check would need was not validated (P 0.88 / R 1.00 on FR-01.01 but 129 flags elsewhere).
- **Prior art:** none of Spec Kit, Kiro, BMAD or Tessl has a human-owned intent + non-goals layer with a drift check against it. TF-IDF/VSM traceability stays competitive with deep learning (arXiv 2507.09199); LLM rerank adds ~12 points. Round-trip checks exist (Allamanis et al. 2024). Rubber-stamping AI drafts is documented; showing information instead of a verdict reduces it.
- **Term collision:** `fr-authoring.md` §2 (lines 47-49, also 192, 407), `step-6-fr-scope.md`, `spec-generation.md:87`, project SKILL: "an FR is a capability".
- **Existing structures:** `fr_table_shape.py` D7 (`Area` is rendered from the id's group digit, never stored); webui `fold-map.ts:104` shows any 1-8 char cell as "area"; scenarios overlap design flows (`screen_registry.py`), plan e2e journeys, `journey_coverage.py` / `journey_plan.py`.

## 2. Terms
**Capability** (German prose: "Fähigkeit"), glossed as "what IREB calls a feature".
- IREB CPRE glossary 2.2: *feature* = "a distinguishing characteristic of a system that provides value for stakeholders ... typically comprises several requirements, used for communicating with stakeholders on a higher level". That is level 2; IREB has no "capability" entry, the gloss keeps IREB satisfied.
- Against "Feature": already the iterate change type (feature / change / bug); Gherkin and SAFe use it below capability.
- For "Capability": Serenity BDD (capability > feature > story, living docs from tests); SAFe (capability above feature).
- Level 1 = IREB *goal* / *vision*; level 3 = IREB *scenario*, ISO/IEC/IEEE 29148 "operational scenarios".
- **Key scenario vs journey vs flow:** a key scenario (SCN) is product-level and human-owned; a design flow or plan journey may *realise* one and then names its SCN id.

## 3. Model
| Level | Owner | Limit | Where |
|---|---|---|---|
| Intent (purpose, audience, problem) + non-goals | human writes or edits | short enough to read in one sitting (guidance, no limit) | `.shipwright/planning/intent.md` (one per product) |
| Capability CAP-xx | human-confirmed | no fixed number; one sentence each (rule below) | `intent.md` |
| Key scenario SCN-xx: user does A -> system does B -> result C | human-confirmed | at least one per CAP; no upper limit | `intent.md` (text only, no FR ids) |
| FR -> AC -> test, FR -> CAP, SCN -> FR path | AI | as today | `spec.md`, tests |

**No upper limits (operator 2026-11-29):** a fixed cap is wrong for larger applications. The rule agents follow instead: a capability is something a user would name as a reason to use the product; split one only when the user's goal differs, merge two when a user would not tell them apart. Size is shown as information in the report (count, longest sentence), never a gate rule. Shipwright itself lands at 7 because that is what it has, not because of a limit.

Every human element carries `status: confirmed | assumption`. **Element** = one human-owned entry in `intent.md`: the intent text, each non-goal, each CAP, each SCN (about 20 for shipwright). FRs, ACs, tests and every link between levels are AI-owned and carry no status.
**Ownership rule (from review H4):** `intent.md` holds only human text. Every link that names an FR lives on the AI side, so a mechanical `fr_split` never touches the human file:
- FR -> CAP: new column `Capability` in the FR table (one source).
- SCN -> FRs: a small AI-owned table `## Scenario paths` in each `spec.md` (SCN id | FRs it passes). Works across specs.
- CAP <-> SCN: derived through the FRs, never stored.

Operator decisions of 2026-11-27: one `intent.md` per product; scenarios first in words, executable where cheap; drift only on FOLD/AC change plus sweep at audit and release; level classification by code; stack profiles -> own capability (now "Extend"), a pure profile choice -> "Build new"; drift as much code as possible.

## 4. Human confirmation: read once, decide little, cannot be forged quietly (review H1 + UX review)
**Principle:** the human decides only the human-owned text. Everything AI-owned (FR -> CAP column, scenario paths, counts, gate results, drift findings, which FRs a change moves) is shown as information and is never an option to approve.

**What the human decides:** intent text; which non-goals hold; each CAP sentence; each SCN sentence; for adopt, "is it meant to be like this?".

**Initial confirmation (~20 elements):**
- **Read** on a page (Artifact link, comfortable on desktop or phone), rendered by code (`intent_render.py`), not hand-written by the agent: intent, non-goals, CAPs, SCNs, each with id, text and an "assumption, derived from code" marker; the FR mapping greyed underneath as information; a digest at the top ("Stand v3 · 7f3a2c", first 6 hex of sha256 of the canonical `intent.md`).
- **Decide** in the terminal in as few dialogs as the size allows (target for shipwright: two). A dialog holds at most 4 questions and each preview has a size limit, so the builder chunks: one question per group while its preview fits the measured limit, otherwise the group is split over further calls. No fixed number of dialogs:
  - Call 1: four questions, one per group (purpose, non-goals, capabilities, scenarios). Each preview carries the full group text (or its chunk) plus the digest, so the dialog stands on its own.
  - Call 2: two to four contrast questions from real boundary cases ("Choosing a stack profile: Build new or Extend?"). Both options are real; no trick questions.
- **Non-goals are picked, not approved:** a multi-select "What should Shipwright explicitly NOT be?" with 3-4 candidates; an unticked candidate is dropped.
- **No recommended option** in confirmation questions, and code orders the options. A deliberate exception to the elicitation rule "each question with a recommendation", which stays in force for gathering requirements.
- **Edits:** "Other" with free text -> the agent edits the file -> the edited element goes through the change flow. The last confirmation is always of the final text.
- **Adopt** asks "the code does X today; should it stay that way?": "yes, intended" / "is so, should be different" / "don't know, stays an assumption". `assumption` is a valid end state.

**Change flow (1-2 elements):** one question per changed element (up to 4 per call). The preview shows OLD / NEW, "newly included" / "newly excluded" (one line each, AI-written, marked as information), the FRs it moves (information) and the digest of the file with the change applied. Options: "take the new version" / "keep the old one" / Other.

**Binding and forging:**
- The question payload is built by code (`intent_confirm_question.py <group | --diff id>` reads `intent.md`, emits the JSON); the agent passes it through.
- A **PostToolUse hook** (harness code, not the agent) re-parses `intent.md` from disk and records `verified: true` only if the preview text equals the canonical text of those elements and the digest matches the file. Otherwise `verified: false`, which F11 ignores. This blocks the real forging route: showing one text and committing another.
- **Storage (review rev 9, H3):** one drop file per session, `.shipwright/intent-confirmations.d/<session_id>.jsonl`, chained within the file, so parallel worktrees never fork one chain (the events/triage lesson). F11 reads all drop files; the latest record per element wins by timestamp.
- **One writer:** the hook is registered in one plugin only (shipwright-iterate) and dedupes by `tool_use_id`, because the shared hooks fan out 12x.
- A **PreToolUse guard** blocks Write/Edit and shell redirection on `.shipwright/intent-confirmations.d/`; the same PreToolUse hook stamps the dialog start for `dwell_s`.
- **Record**, one line per question: `ts, session_id, group, doc_digest, verified, answer_label, other_text, dwell_s, artifact_url/version (information only), elements: [{id, sha256, draft_sha256}], prev_record_sha256` (a chain, so editing or deleting a line is visible). A fixed label registry maps answers to accept / reject / edit.
- **F11 / gate P rule:** every element marked `confirmed` in the committed `intent.md` needs its latest record to be `verified`, `accept`, with a hash equal to the committed text and an intact chain. An `edit` must be followed by a change-flow record. For a multi-select, selected candidates are confirmed and unselected ones must be absent. `assumption` elements need no record.
- **Shown, not gated:** "confirmed without edit" (draft hash unchanged), and how long the dialog was open (a 3-second confirmation of all CAPs is visible in the report).
- **Honest limit:** tamper-evident, not tamper-proof. Named as residual risk in the constitution ASK FIRST entry.
- **Verify first (U2a1):** PostToolUse for AskUserQuestion receives the full `tool_input` (including previews) and the chosen labels, under Claude Code and under the Codex bundle. If not, fall back to recording answer plus digest only; then F11 accepts a record whose digest equals the committed file and whose chain is intact (named as weaker in the constitution entry). Under Codex there is no AskUserQuestion equivalent: confirmation is unavailable there and elements stay `assumption`.
- Later option (not this campaign): a confirm button in the webui writing the same record.

**Rejected:** one question per element (20 dialogs breed rubber-stamping); "confirm only the uncertain ones, rest as shown" (AI confidence is uncalibrated, "rest as shown" is a rubber stamp); binding to the artifact version (the hook cannot see what the browser rendered); typing the digest (proves copying, not reading).

## 5. Drift check: code first, AI only on what code routes
| Layer | What | Runs |
|---|---|---|
| D1 code, per FR | S2 term burst AND an order-free second signal (S5 change-point when ACs are contiguous, else leave-one-out centroid; chosen in U3a by the shuffled fixture). Route FR if >=6 flagged and >=25 %. Thresholds in one config. | audit sweep, release |
| D2 code, per new AC | TF-IDF fit of the new/changed AC to its own FR vs other FRs and CAP sentences, plus non-goal term hits. **Sweep-only until U3a shows per-AC precision on held-out cases; then wired into iterate.** | sweep; iterate after validation |
| D3 code | dedup with I10: one finding per FR, both evidences attached | always |
| D4 AI, routed only | call 1 reads ONLY the ACs and writes 2-3 sentences; call 2 compares with FR description, CAP sentence, non-goals (deviation, scope creep, other CAP, non-goal violated) | when D1/D2 route |

Output: one triage finding per FR with flagged AC ids, the CAP they seem to belong to, and the back-translation next to the FR text (information, not a verdict).
**Models:** both D4 calls on Sonnet, passed explicitly. Opus is not needed for information-style output; any split that follows a finding runs through a normal iterate with the Opus review cascade and operator confirmation.

## 6. Plugin impact (all plugins)
| Plugin / area | Change |
|---|---|
| run | phase order unchanged; project phase validator gains gate P after the flip; `testkit/minimal_valid_project.py` writes `intent.md` |
| project | elicitation order intent -> non-goals -> CAPs -> scenarios -> FRs -> ACs (`requirement-elicitation.md` §0, Step 6); "FR is a capability" wording at the three prompt sites; grill-trace (header-aware, `grill_trace_fr_coverage.py:31,63-66`) learns the column |
| design | flow comment may carry `SCN-xx`; flow without scenario = warning |
| plan | `Requirements:` lines stay; plan journeys name their SCN; plan review triggers D4 when the plan changes ACs |
| build | section-builder / spec-reviewer get the FR's CAP and the non-goals as context |
| test | `@pytest.mark.scenario("SCN-xx")` next to `covers`; scenario selection (§7); `journey_coverage` keys on SCN |
| security, deploy, preview | no change (they do not read the spec) |
| changelog | drift sweep hook in `release.py prepare`; release notes unchanged |
| compliance | audit group P (registered next to A-I in `audit/_registry.py`); D1/D3 next to group I; `rtm_generator.py` + `test-traceability.json` get CAP and SCN (minor version bump); intent report = a **section at the top of `dashboard.md`** plus `intent-report.json` (no 8th evidence doc, so `DERIVED_SNAPSHOTS` / `RESTORABLE_SNAPSHOTS` change only for the json); `control_grade.py` unchanged |
| grade | repo without `intent.md` = "not applicable", never 0; no field added in this campaign |
| iterate | Step 1a prints change level and whether confirmation is needed; D2 on FOLD (after validation); F11 confirmation check |
| adopt | `enrichment_schema.py` / Step B.8 add intent, non-goals, CAPs, scenarios, all `assumption`; `spec_table.py` writes the column; `derived-catalogue.json` counts confirmed elements; caveat "derived from code = what exists, not what is wanted" |
| shared | glossary; `fr-authoring.md` §2; constitution ASK FIRST with enforcement + residual risk; `intent.schema.json`; confirmation hook + guard; `contracts/compliance.py` reader; CLAUDE.md template + codex appendix; **this repo's CLAUDE.md "Where documents live" section** (second human-owned file in `.shipwright/`); `docs/hooks-and-pipeline.md` (new hook!); guide Ch. 4/7.5/8/App. B |
| Codex bundle | new agent/hook picked up by `build_codex_plugin.py`; check `BUILD_MANIFEST.json` and that the hook runs under Codex |
| webui | **Ship's Log links the intent:** each entry shows the CAPs/SCNs it touched (derived from the event's affected FRs through the Capability column, no new event field unless that derivation fails) and links to the intent view; reads `dashboard.md` (markdown), `test-traceability.json`, adopt `snapshot.json`, grade JSON, Ship's Log list; adds a view of `intent-report.json`; verify `fold-map.ts` with the new column |
| leadwright | being extended in its own 3-iterate campaign right now: U10 starts after it and covers the FRs it adds; consumes shipwright only via webui contracts; own spec tools (`spec/check-spec.py`, `spec_parse.py`, `spec_tabellen.py`) must accept the column; own spec to migrate |

### 6a. How a user sees FRs and ACs (research 2026-11-28)
Prior art: Specification by Example (key examples, living docs), Serenity BDD (theme > capability > story rollups), SpecFlow LivingDoc, PR-FAQ / Shape Up (short narrative + no-gos), story mapping, ISO 29148 (views per audience from one source), perspective-based reading (reviewers find more with one perspective and a scenario). AI spec tools either make the human read everything (Kiro, BMAD) or ask only about gaps (Spec Kit `/clarify`); Shipwright copies the second. None hides FRs behind a human-owned layer.
Three views, one decision surface, all rendered by code:
1. **Capability map (read):** one row per CAP with its sentence, its scenarios in words, each FR as a one-line title, AC count / tests / last verified / drift flag; ACs folded per FR. The scenarios are the key examples. (U2a2)
2. **What changed for you (read):** after every iterate, the affected CAP/SCN and one plain sentence per FR added/changed/removed, from the spec-impact record; never AC diffs. Terminal 1-3 lines, link only when a CAP or SCN changed. (U2c)
3. **Decide:** unchanged from §4, plus one optional change-flow question when a change rests on an element that is still `assumption`. Drift findings, gate results, coverage are information, never options.
After project: short summary + page link (U4). On demand: the render command. webui shows the same map (U9).

### 6b. Readable compliance reports (research 2026-11-28)
Rules for every report: first line = one plain sentence with verdict and caveat; one-page summary first; gaps before passes; details in `<details>`; titles instead of ids; build metadata in a footer. Model: SOC 2 section IV (control -> test -> result or exception), FDA traceability (gaps, not green rows), Serenity/Vanta rollups.
Found in today's reports: dashboard grade A next to a 121-day-old failed cross-check; test health check mark next to "WARN"; RTM 11 columns with whole FR paragraphs in cells and COVERED next to MISSING; test-evidence repeats the RTM timeline; change-history 1951 lines duplicating the changelog; audit report dated older than the run the dashboard cites; markdown-only SBOM.
Result: dashboard leads with capabilities (U6b); RTM by CAP with test-evidence merged in (U6a); change-history dropped as a document, audit and SBOM cleaned (U6d).
**Bugs, verified 2026-11-28, can ship before the campaign as small iterates:** `change_history.py:93` counts AI commits by author name only, so this 100 % agent-written repo shows "AI-assisted 0 / human 1868" (fix: read the `Co-Authored-By` trailer); `control_grade.py:199` always says "net growth", also for a negative delta; dashboard license count and SBOM unknown count come from different sources; dashboard and audit report disagree on the last audit run.

**webui and leadwright iterates run from this campaign** (operator 2026-11-28), no separate campaigns; the shipwright admin-merge grants do not apply in those repos.

**Migration for consumer projects (review M4):** the column is optional until a project has `intent.md`; an empty cell reads as "unassigned" (a gate-P finding, not an error). Without `intent.md`, gate P is "not applicable". The flip in U11 is per project: blocking only where `intent.md` exists and every FR has a CAP, so a run already under way in a consumer project is never turned red by an upgrade.

## 7. Executable scenarios without long runs
The 10 h test (`integration-tests/e2e-webui/`, `autorune2e/run-e2e.ps1`, 70-658 min, real agent through every phase) is **on demand only**, neither per change nor per release (operator 2026-11-28), and it covers only the pipeline. It is not a scenario test.

**Release suite:** one deterministic test per scenario (simple pipeline, iterate, release, adopt, compliance, ...), all run before every release, total budget 30 min; per change at most 2 of them (below).
Per change, the model is the changelog pilot: scratch project + stubbed host + committed golden traces replayed by a driver, model-written text masked (`shared/testkit/golden_trace.py`; scenarios S1-S19, ~47 trace files in `plugins/shipwright-changelog/tests/golden/`).
- **Bind before building.** Most candidate scenarios already have deterministic tests of 1-10 min: release (golden S1-S19), adopt (`test_adopt_evidence_stamp_e2e.py` + canned `enrichment.json`), profiles/rules (`test_stack_profile_resolution_e2e.py`), security gate -> triage, parallel iterates + event drops, grade + contract gate, reminders. They get the `scenario` marker.
- **One new harness:** iterate (`/shipwright-iterate "Add a dark mode toggle"`) on the golden-trace pattern over the real worktree setup, AC record, review record, F5b and F11 verifier with a canned diff. Target < 5 min.
- **Simple pipeline (SCN-02), new harness:** a tiny product (one screen, two FRs) through project -> design -> plan -> build -> test -> changelog with canned phase outputs on the golden-trace pattern, real phase validators and gates between phases. Target < 10 min. This replaces the 10 h run as the release-level pipeline check.
- **Selection (review M3):** wide scenarios (8-10 FRs) would be selected by almost every change. So: per change, run at most the 2 scenarios with the highest FR overlap, budget 5 min inside F0; all of them in the release suite. Before committing to this, U8a measures the selection on the last 20 merged iterates (how many selected, how long).

Candidate scenarios (operator confirms in U2b; completeness check of 2026-11-28 added triage/host checks, deploy, broken main and audit):
- SCN-01 iterate a change to a PR with impact record and evidence (11)
- SCN-02 a small product goes from a description through every phase to a running app (01-06, 12, 16)
- SCN-03 cut a release on protected main, bring it live, health-checked, with a way back (09, 08)
- SCN-04 adopt an existing repo (13)
- SCN-05 a stack profile's rules are rendered and enforced (profile FRs)
- SCN-06 a finding from a local check or the host's scans (CodeQL, dependency alerts) lands once in triage, is taken into work, fixed, green (07, 14)
- SCN-07 two parallel iterates are each re-checked on the host, merge cleanly and fold at release; when main breaks after a merge, the culprit is named (17, 19)
- SCN-08 grade any repo without writing to it (18)
- SCN-09 a fresh machine: Shipwright is installed into Claude Code with one command and the setup check is green (FR-01.23); harness in U8c (scratch HOME, install, verify-setup)
- SCN-10 an auditor asks which requirement is tested where and what changed; the cross-check names where evidence and code disagree (10)
Not in any scenario (information, gate P needs a scenario per CAP, not per FR): 15 cross-repo contract, 20 cost meter, 22 reminders (its tests stay, without a scenario marker; replaced as SCN-09 by installation 2026-11-29).

## 8. Capability proposal for shipwright (operator edits in U2b)
| CAP | Sentence | FRs |
|---|---|---|
| CAP-01 Build new | From a plain description, Shipwright asks what is needed, then plans, designs and builds a working app one reviewed piece at a time, on the technology profile you chose. | 01, 02, 03, 04, 05, 12, 16, from U7 the new "profile selection" FR (today FR-01.01 AC09-12) |
| CAP-02 Verify | Every change is tested, scanned and re-checked on the code host before it can merge, nothing handed to another repo changes shape silently, and a broken shared branch is named and repaired. | 06, 07, 15, 17, 19 |
| CAP-03 Ship | A finished version goes live with readable release notes and a safe way back. | 08, 09 |
| CAP-04 Prove | At any time Shipwright shows which requirement is covered by which test, what changed when and what a session cost, and can grade any repository from A to F. | 10, 18, 20 |
| CAP-05 Evolve | Ongoing changes and taken-over codebases get exactly as much process as they need, every finding lands in one inbox, and the operator is reminded of what is still open. | 11, 13, 14, 22 |
| CAP-06 Extend | Teams plug in their own technology rules per stack profile without changing the framework, and Shipwright can run partly in another AI assistant (Codex; recommended route: codextender). | 21; from U7 also the new "architecture rules per profile" FR (today FR-01.01 AC13-38) |
| CAP-07 Install | Shipwright installs into Claude Code with one command, checks its own setup and stays up to date. | FR-01.23 "installation and setup check" (`scripts/install.sh`, `verify-setup.sh`, marketplace + cache sync), minted in U1c |
CAP-07 Install added 2026-11-29 (operator: "installation is a capability"; Claude Code only, Codex stays in Extend because it is only partial, recommended via codextender; a separate "Supported agents" capability was considered and dropped: it would put Codex more prominently than wanted); the npx installer/updater is webui FR-01.49 and stays in the webui intent, which links to it. Seven CAPs (no limit applies, §3). **Names decided 2026-11-29, in English:** Build new (a new product, first time), Evolve (everything after: iterate, adopt, triage, reminders), Verify, Ship, Prove, Extend, Install; a capability groups what the user gets, not which plugin code runs, so iterate sits in Evolve although it reuses plan/build/test. The former CAP-06 "Betrieb" was dissolved 2026-11-28 and its id reused for Extend: there is no telemetry (the cost meter reads the local session record, nothing leaves the machine), so two small FRs did not earn a capability; 20 -> Prove, 22 -> Evolve. Seven capabilities; final ids are assigned in U2b. Placement (operator reviews in U2b): 15 -> Verify (a gate that blocks a change, not an evidence document); 16 -> Build new (asking what is needed is the first step of building; adopt and iterate reuse the method); 13 -> Evolve (taking over existing code, then changing it); 21 -> Extend. **Until U7 splits it, FR-01.01 is mapped to Build new as a whole** (its AC13-38 belong to Extend; the drift check flags exactly that, which is the U3 calibration case).

## 9. Units
Each unit is one iterate with the review cascade (spec -> code -> doubt, model=opus explicit), at most ~5-8 files.

| Unit | Content | Done when |
|---|---|---|
| U0 terms + format | glossary, `fr-authoring.md` §2 + 3 prompt sites, `intent.schema.json`, ADR "Capability column next to D7", constitution ASK FIRST, repo CLAUDE.md section | grep finds no "FR is a capability" left in prompts/skills; schema validates a sample `intent.md`; **Stop 1: operator approves terms and format** |
| R1 AI attribution | collector `collectors/change_history.py:38` reads trailers too (`%(trailers:key=Co-authored-by)`), `CommitEntry` gets the field; `lib/change_history.py:93` counts a commit as AI-assisted when a co-author trailer names Claude (case-insensitive, GitHub squash writes "Co-authored-by") or the author does | fixture commits with "Co-Authored-By" and "Co-authored-by" trailers both count; shipwright no longer shows "0 AI-assisted" |
| R2 growth wording | `control_grade.py:199` says "net shrink" / "net growth" by the sign of the delta | test pins both words by sign |
| R3 one license count | the SBOM collector (`collectors/sbom.py`) is the one source; the dashboard reads its unknown-license count instead of counting itself | dashboard and SBOM show the same number on a fixture with unknown licenses |
| R4 one audit date | `audit-report.json` (the run record) is the one source for "last run"; the dashboard disclosure (`_audit_disclosure_render.py`) and `audit-report.md` both read it | both show the same date on a fixture; a stale md cannot show an older date than the json |
| U1a column + readers | inventory every FR-table reader (direct, string literals, tests, webui, leadwright); `fr_table_shape.py`, `spec_table.py`, grill-trace, spec parsers | every inventoried reader passes on a spec with and without the column |
| U1b parser + gate P | `lib/intent_parser.py`, `## Scenario paths` parser, group P (each FR one CAP, each CAP >=1 FR and >=1 SCN via paths, paths name real FRs; counts and sentence lengths reported as information, no size rule), advisory; "not applicable" without `intent.md` | seeded violations each caught by exactly one rule; clean fixture green; legacy spec reports "not applicable" |
| U1c install FR | mint FR-01.23 "installation and setup check" in `spec.md` with ACs read off `scripts/install.sh`, `verify-setup.sh`, `update-marketplace.sh`, `check_plugin_cache_sync.py`; registry, tags on the existing installer tests | FR-01.23 passes the FR-table and AC gates; every AC has a test tag or is listed as uncovered |
| U2a1 confirmation record | verify the hook payload first (§4); PostToolUse hook, PreToolUse guard, chained record, label registry, F11 rule | F11 red on a hand-written record, a hash mismatch, a broken chain, and a preview that does not match the file (`verified: false`); green on a hook-written one; guard blocks Write/Edit/redirect; two branches confirming in parallel merge and F11 stays green; one question yields exactly one record despite fan-out; fallback rule tested |
| U2a2 question builder + page + capability map | `intent_confirm_question.py` (group, diff and multi-select modes), `intent_render.py` (page with digest) and `--detail` = **capability map** (§6a view 1) from the Capability column, `## Scenario paths`, `test-traceability.json` | builder output for a fixture matches the file byte for byte; page shows the same digest; the builder chunks so every preview stays under the limit measured in U2a1, and the 7-CAP shipwright fits in one question; map on shipwright shows one row per CAP and one line per FR (23 after U1c) with no AC text unfolded; render byte-identical over 2 runs |
| U2b draft shipwright intent | `intent.md` from README (non-goals: not a stack framework, not autonomous codegen), §8 capabilities, §7 scenarios, Capability column filled, `## Scenario paths`; **Stop 2: operator reads the page, answers call 1 + call 2, then the change flow for every edit** | gate P green (advisory) on shipwright; every element has a hook record |
| U2c level classification + "what changed for you" | iterate Step 1a level from the diff, names the elements that need a question, uses the builder diff mode; F12 prints the "what changed for you" block (§6a view 2) from the spec-impact record, built by code next to the question builder | fixture diffs for each level classify right; intent/CAP change without record is refused in F11; `spec_impact=none` prints one line, `modify` prints CAP + FR sentence, a CAP/SCN change prints the link + "needs your confirmation" |
| U3a drift code | D1-D3 lib + audit check; fixtures: FR-01.01 copy, the same with shuffled ACs, three clean FRs, drift seeded into one webui and one leadwright FR (held-out), FR where I10 and D1 both fire | FR-01.01 routes in order and shuffled; clean FRs do not; held-out seeds route; per-AC P/R of D2 reported; dedup gives one finding |
| U3b drift AI | `ac-drift-reviewer` (two isolated Sonnet calls) against the confirmed intent of U2b; triage producer | on the U3a fixtures: names the profile/rules theme for FR-01.01, no finding on clean FRs; **Stop 3: operator reads the calibration** |
| U3c D2 into iterate | only if U3a's held-out per-AC precision is acceptable to the operator | iterate FOLD fixture produces/does not produce a finding as expected |
| U4 project + design | elicitation order; ends with the same two-dialog confirmation; Step 4 points at the page, not the manifest text; Step 8 prints a short CAP summary + page link; flow `SCN-xx` tag | project skill on two test briefs writes a gate-P-green `intent.md` before any FR and ends with the summary + link |
| U5 adopt | enrichment schema + prompt, column, "is it meant to be like this?" questions | adopt on a fixture repo yields `intent.md` all `assumption`; a mixed confirmed/assumption file passes gate P |
| U6a1 RTM rework | `rtm_generator.py`, `_rtm_layer_columns.py`, `test-traceability.json` CAP+SCN, version bump; rows grouped by CAP then FR (title only, <=80 chars); columns status in plain words / tests passing / last verified / scenario; progression column dropped; timeline folded per FR (newest 10); one honest status instead of "COVERED" next to "MISSING" | contract gate green with bumped version; webui reader test still green; shipwright RTM summary < 60 lines, no FR paragraph in any cell |
| U6a2 test-evidence merge | inventory every reader first (as U1a), known: `phase_validators_late.py`, `test_evidence_phase_source.py`, `verifiers/iterate_compliance.py`, `audit_staleness.py`, `_control_block.py`, `pr_review_skip_safety.py`, adopt `dry_run_reporter.py`, `artifact_migrations.py`, `churn_merge.COMPLIANCE_MDS`, webui `shipslog-docs-reader.ts` + e2e A16/A16b; a webui iterate first makes its reader tolerate the file being absent; then `test-evidence.md` becomes the RTM per-FR drill-down + "full suite runs" (only real full suites) | every inventoried reader green with the file merged; snapshot lists and `hooks-and-pipeline.md` updated; webui e2e green |
| U6b report | dashboard section + `intent-report.json` (added by hand to `DERIVED_SNAPSHOTS`; it is run-written, so not in `RESTORABLE_SNAPSHOTS`; drift test that both lists name it as decided) + contract + `contracts/compliance.py` reader; reading order (§6b): capability table first (CAP / scenarios proven / FRs covered / open gaps), grade line states its own contradiction ("A, but the cross-check is 121 days old and failed"), suppression/bloat/review tables folded, build metadata in a footer | report on shipwright: page one <= ~40 lines; json validates against the published shape |
| U6c release + grade | drift sweep in `release.py prepare`; grade "not applicable" | release golden traces updated and green; grade on a repo without intent shows "not applicable" |
| U6d report cleanup (after U2b, needs the CAPs) | inventory readers of `change-history.md` (as U6a2; webui Ship's Log reads it) and make them tolerate its absence first; change-history becomes a dashboard block (changes per CAP / last 30 days + link to CHANGELOG.md, AI attribution from R1 carried over); audit report headed by plain questions, failures first as finding -> why -> fix, disabled checks in one folded line without "Suggested"; SBOM as CycloneDX JSON + 10-line md summary, real dedup, unknown licenses as action items | no SBOM package twice at the same version; every inventoried reader green; snapshot lists, `hooks-and-pipeline.md` and webui e2e green |
| U7 split FR-01.01 + leftovers | `fr_split` FR-01.01 into pipeline / profile selection / architecture rules; then FR-01.11 (redo the closed PR #1055 cut AC21-AC25 "delivery when the host cannot merge" on current main, next free id: FR-01.22 is taken by "Operator reminders"), FR-01.03, ... as D1/I10 findings say; one split = one iterate | conservation check green per split; D1 no longer routes FR-01.01 |
| U8a bind + select | `scenario` marker on existing tests (SCN-03..08; SCN-10 binds the audit cross-check tests of group I, or U8c adds one); selection unit; measurement on last 20 iterates | selection picks <=2 scenarios and <=5 min on each of the 20 |
| U8b iterate harness | SCN-01 golden-trace harness | < 5 min, deterministic over 3 runs |
| U8c simple-pipeline harness + release suite | SCN-02 harness (§7); SCN-09 install harness; SCN-10 test if U8a found none; release suite = one test per SCN, wired into `release.py prepare` | SCN-02 < 10 min; whole suite < 30 min, deterministic over 3 runs |
| U9 webui | view of `intent-report.json`; Ship's Log shows CAPs/SCNs per entry and links the intent; migrate own spec via U5 | webui CI green; webui gate P green (advisory) |
| U10 leadwright | spec tools accept the column; migrate own spec via U5 | leadwright CI green; gate P green (advisory); capability count reported |
| U11 flip + measure | gate P blocking per project (§6 migration rule); guide, `hooks-and-pipeline.md`; re-run FR-assignment measurement | measurement top-1 > 80 % on old repos, or honest report; **Stop 4** |

Order: (R1-R4 in parallel with U0; they do not block Stop 1) U0 -> U1a -> U1b -> U1c -> U2a1 -> U2a2 -> U2b -> (U2c || U3a) -> U3b -> U3c? -> (U4 || U5) -> U6a1 -> U6a2 -> U6b -> U6c -> U7 (U6d anywhere after U2b) -> U8a -> U8b -> U8c -> (U9 || U10; U10 after the leadwright campaign closes) -> U11.
Payoff points: after U3b drift is found by code + AI on shipwright; after U6b the one-page report exists. The campaign can pause after any stop.

## 10. Out of scope
Rewriting AC wording; test-to-AC binding; renumbering FR ids; per-spec intent; grade-weight changes; release notes grouped by capability (good follow-up); webui confirm button; replaying the real agent in the 10 h run (on demand only); nightly run of all scenarios.

## 11. Risks
- **Rubber-stamping.** Group confirmation plus contrast questions; non-goals picked, not approved; no recommended option; "confirmed without edit" and time spent shown; report shows back-translations, not "OK".
- **Drift thresholds overfit.** Held-out and shuffled fixtures in U3a; one config; advisory until U11; D2 into iterate only after validation (U3c).
- **Confirmation bypass.** Tamper-evident only; named in the constitution; hook record + git history make a bypass visible.
- **New column breaks readers.** U1a inventory first, with and without column.
- **Too many capabilities without a cap.** The split/merge rule (§3) plus the count in the report; the operator decides, no gate.
- **Size** (29 units, three repos). Each stop is a clean pause point.

## 12. Review log
Opus plan review of rev 2 (2026-11-28, verdict "ready after fixes"):
- H1 forgeable confirmation -> §4 hook + guard, tamper-evident wording.
- H2 D2 unvalidated -> sweep-only, held-out fixtures, U3c gate.
- H3 S5 order-dependent -> shuffled fixture, order-free fallback.
- H4 FR ids in human file -> `## Scenario paths` on the AI side, CAP<->SCN derived.
- H5 units too big -> U1/U2/U3/U6/U8 split.
- M1 calibration before intent exists -> U2b moved before U3.
- M2 no done-criteria -> table §9.
- M3 selection too wide -> top-2, 5 min, measured.
- M4 consumer migration -> §6 rule.
- M5 repo CLAUDE.md -> in U0.
- L1 -> Opus at iterate dropped; report as dashboard section; nightly deferred.
- L2 -> trace count corrected.
- L3 -> word limits defined.
- L4 -> dedup fixture.

Opus review of rev 9 (2026-11-29, "ready after fixes"): H1 CAP-07 without FR -> U1c mints FR-01.23, FR-01.01 mapped to Build new until U7; H2 caps left in the dialog design -> builder chunks by measured preview limit; H3 chain forks in parallel worktrees + 12x hook fan-out -> per-session drop files, one registered hook, dedupe by tool_use_id; M1 stale names -> fixed; M2 readers of test-evidence/change-history -> inventory step, U6a split, webui tolerates absence first; M3 snapshot lists named; M4 U6d after U2b, R4 part removed; M5 unit count, SCN-09/10 harnesses; M6 fallback rule + Codex = assumption only; L1-L4 -> R1 collector scope, R3/R4 canonical sources, U10 dependency, dwell stamp.

Opus UX review of the confirmation (2026-11-28): read on a page, decide in at most two dialogs, change flow as a diff, preview-verified hook record with a chain -> §4; U2a split into U2a1/U2a2.

## 13. Open questions for the operator
1. ~~Term~~ decided 2026-11-28: **Capability**.
2. ~~§8 placement~~ proposal written into §8; final check in U2b.
3. ~~§4 channel~~ decided 2026-11-28: hook-recorded answer (variant A), designed for little reading in the terminal (§4); webui button later.
4. ~~FR/AC view and readable reports~~ researched 2026-11-28 -> §6a, §6b, units U2a2, U2c, U4, U6a, U6b, U6d.
5. ~~report bugs~~ decided 2026-11-29: in the campaign as R1-R4, run at the start alongside U0.
6. ~~installation gap~~ decided 2026-11-29: own capability CAP-07 Install (Claude Code only); Codex stays in Extend; capability names in English.
