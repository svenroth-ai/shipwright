# Iterate: Close the six open GitHub code-scanning alerts

- **Run-ID:** iterate-2026-07-28-codescanning-alerts
- **Type:** change
- **Complexity:** medium
- **Spec Impact:** NONE (behavior-preserving; no FR added, modified or removed)
- **Risk flags:** none

## Problem

`svenroth-ai/shipwright` carries six OPEN code-scanning alerts — five Semgrep
`medium` plus one CodeQL `note`. They are **six alert rows over three root
causes**: alerts 1293–1296 are four byte-identical records of one finding (same
file, same line 32, same column, same category — verified via
`/code-scanning/alerts/{n}/instances`).

| Alert | Rule | Site | Sev |
|---|---|---|---|
| 1293–1296 | `semgrep generic.unicode.security.bidi.contains-bidirectional-characters` | `plugins/shipwright-security/scripts/lib/pr_review_render.py:32` | medium ×4 |
| 1286 | `semgrep …audit.non-literal-import` | `shared/scripts/shared_lib_loader.py:39` | medium |
| 1291 | `CodeQL py/unused-global-variable` | `shared/tests/test_checks_that_gate.py:35` | note |

None of them gates CI — only criticals block. The cost is the standing tax the
2026-07-21 iterate already named: an open alert trains the reader to skim the
Security tab, which is how a real finding eventually gets skimmed too.

**Provenance (asked explicitly, so verified rather than assumed).** None of the
six originate in the four PRs merged on 2026-07-28 afternoon (#490, #491, #492,
#493):

- bidi ×4 — `pr_review_render.py` was created by **#487** (merged 2026-07-28
  08:20 UTC). Its predecessor `pr_review_lib.py` was walked commit-by-commit
  across all 6 of its revisions: **none** ever carried a literal bidi character,
  so the characters enter with the split, not with the code that moved.
- non-literal-import — **#453** (2026-07-27 11:53 UTC).
- unused-global — **#475** (2026-07-27 22:13 UTC).

## Triage — two false positives, one real defect

### (1) bidi ×4 — FALSE POSITIVE as a vulnerability, REAL as a hygiene defect

`pr_review_render.py` **is** the sanitizer that strips bidi controls from
attacker-chosen PR path names. Its regex character class must therefore denote
those characters. Semgrep's Trojan-Source rule sees only "file contains U+202E"
and cannot tell a defense from a hole.

But the characters are written as **literal codepoints**, not escapes, and that
is a genuine defect with an observable consequence:

```
raw.splitlines()     -> 245     # Python splits on U+2028 / U+2029
raw.split(chr(10))   -> 244     # git counts newlines only
```

Python's own line numbering disagrees with git's by one, in the file whose whole
subject is that a splitter and a reader must agree about where a line ends. The
unpaired U+202A (LRE) and U+202E (RLO) additionally flip rendering direction for
the remainder of the line in any editor.

Nine literal codepoints, all inside one character class:
U+200B, U+200F, U+2028, U+2029, U+202A, U+202E, U+2066, U+2069, U+FEFF.

**Escaping is a source-representation change only.** `"‮"` in Python source
*is* U+202E at runtime, so the compiled pattern is unchanged and the tests keep
exercising the real characters.

### (2) non-literal-import — FALSE POSITIVE, 6th of its class

`importlib.import_module(f"lib.{module_name}")`. Every call site passes a
hardcoded literal (verified across all call sites; none takes external input).
Dynamic, shadowing-proof loading is the module's entire purpose under ADR-045 —
so unlike the earlier `PY_DYNAMIC_IMPORT` findings this **cannot** be normalized
into a static import. Normalizing it would reintroduce exactly the
`sys.modules['lib']` collision the module exists to prevent.

`conventions.md:110` already records the standing resolution for this rule:
an adjacency-correct inline `# nosemgrep`, **never** repo-wide
`SHIPWRIGHT_SEMGREP_EXCLUDE_RULES` (which would blind real dynamic imports).

### (3) unused-global — REAL, and the only genuine defect of the three

```python
_CI       = _WORKFLOWS / "ci.yml"        # used at :93, :102, :132
_SECURITY = _WORKFLOWS / "security.yml"  # used NOWHERE
```

`test_checks_that_gate.py` came from #475 — *"three checks that ran, reported,
and gated nothing"*. A constant naming `security.yml` that no assertion reads
means this gate-verification test never verifies `security.yml`'s gates. That is
the same failure mode the file was written to prevent, reproduced inside the
file itself.

Adjacent: the comment two lines below is broken mid-sentence — *"Wiring a gate
into a job branch protection does not require would leave it exactly as
decorative as running it nowhere."* Two clauses spliced together.

**Corrected at Stage-2 review — the diagnosis above was wrong.** This iterate
first read the dangling `_SECURITY` as proof of a missing test, and wrote two
new tests into `test_checks_that_gate.py` to supply it. The reviewer found the
premise false, and it is:

`shared/tests/test_security_gate_verdict.py` **already exists in the same test
root** and already owns the security half — 6 tests, including
`test_the_gate_itself_still_blocks_on_critical_only`. Its own docstring closes
with *"The sibling half — checks wired to nothing at all — is
`test_checks_that_gate.py`."* The two modules were **split**, and only the
docstring bullet was left behind. `_SECURITY` is residue of a completed split,
not the ghost of an absent test.

The two tests written against that false premise were also **weaker than what
already existed**:

| | new (withdrawn) | existing sibling |
|---|---|---|
| locates the step | by `name:` string | by `id: shipwright-critical-gate` — the id the A5 compliance audit uses |
| posture check | `'if [ "$total" -gt 0 ]; then' in run` (substring) | regex over the whole `if…fi` block, requiring `exit 1` *inside* it |
| severity-exit check | same-line `var and "exit"` | 2-line regex |

So the correct root fix is the **deletion** the section above argued against:
remove `_SECURITY`, trim the docstring bullet to a cross-reference mirroring the
sibling's, and relocate the one genuinely incremental assertion — that the
single console line spends the counts it computed — into the module that owns
the subject. `test_checks_that_gate.py` returns to 10 tests;
`test_security_gate_verdict.py` goes to 7.

Deleting `_SECURITY` silences CodeQL 1291 **and** closes no gap, because there
was none. What the residue actually marked was the docstring, not the coverage.

## Decision — fix at the root where a root fix exists

| # | Finding | Resolution | Root fix? |
|---|---|---|---|
| 1 | bidi ×4 | escape the 9 codepoints as `\uXXXX` | yes |
| 2 | non-literal-import | inline `# nosemgrep`, and nothing else | no — accepted |
| 3 | unused-global | delete the split residue; relocate one assertion | yes |

**(2) takes one artifact, not two — corrected during build.** The plan opened
with the claim that an inline `# nosemgrep` also needs an entry in
`shipwright_accepted_risks.yaml`, on the reading that the register covers "every
source-controlled suppression". Checking the implementation before writing the
entry showed the opposite, and writing it would have **broken the build**:

- `accepted_risks_cli.reconcile` compares the register against
  `discovered_suppressions`, which reads `.trivyignore.yaml` and the
  `SHIPWRIGHT_SEMGREP_*` env vars in `security.yml`. It does **not** scan source
  files for `# nosemgrep`.
- The `target` vocabulary has no inline-suppression member (`trivy-ignore`,
  `semgrep-rule-exclusion`, `semgrep-policy-toggle`, `github-dismissal`).
- An entry keyed to a rule absent from `SHIPWRIGHT_SEMGREP_EXCLUDE_RULES` is
  registered-but-not-discovered — the *stale* half of the both-directions gate,
  which fails CI.
- Empirically: `check` reports **4 entries / 4 suppressions / no drift**, and
  **zero** of the 8 pre-existing `non-literal-import` nosemgrep sites hold a
  register entry.

The register records acceptances *applied through a scanner config*. An inline
suppression is applied in the source and reviewed in the diff.

## Acceptance criteria

- **AC1** — `pr_review_render.py` contains zero literal bidi/zero-width
  codepoints; the character class is written with `\uXXXX` escapes.
- **AC2** — the compiled `_UNSAFE_IN_DISPLAY` pattern is *provably* unchanged:
  a test asserts set-equality of the matched codepoints against an explicit
  expected set, so equivalence is measured, not asserted in prose.
- **AC3** — `shared_lib_loader.py:39` carries an adjacency-correct
  `# nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import`
  as the **last** comment line before the call (an intervening comment silently
  breaks attribution).
- **AC4** — `accepted_risks_cli.py check` still reports no drift, with **no new
  register entry** (see the corrected decision above).
- **AC5** — `_SECURITY` is gone from `test_checks_that_gate.py` and its docstring
  bullet is a cross-reference to `test_security_gate_verdict.py`; the one
  incremental assertion (the console verdict line spends `$total`/`$high`/
  `$medium`/`$low`) lives in that sibling and is mutation-proven to fail on a
  bare-count regression.
- **AC6** — the spliced comment at `test_checks_that_gate.py:37-38` reads as one
  coherent sentence.
- **AC7** — the full `shared/tests` and `plugins/shipwright-security/tests` roots
  are green; ruff clean.

## Mini-plan

1. `pr_review_render.py:32` — replace the 9 literal codepoints with `\uXXXX`
   escapes. Keep the comment block above accurate.
2. Extend `test_pr_review_render.py::TestSafePath` with a codepoint-set
   equivalence test (AC2) pinning the exact alphabet the class matches.
3. `shared_lib_loader.py` — add the `# nosemgrep` line + a WHY, adjacency
   verified mechanically against the 8 working sites.
4. Run `accepted_risks_cli.py check` to confirm the inline suppression needs no
   register entry and introduces no drift.
5. `test_checks_that_gate.py` — delete `_SECURITY`, trim the docstring bullet to
   a cross-reference, repair the spliced comment; add the one incremental
   assertion to `test_security_gate_verdict.py` instead.
6. Run both test roots separately (one root per pytest process, ADR-044), ruff.

### Alternative considered — dismiss the four bidi alerts on GitHub instead

Rejected. A GitHub dismissal is per-alert and does not survive the finding
reappearing under a new fingerprint, which is precisely what four duplicate rows
for one finding demonstrates is possible. It also leaves the real defect — the
literal characters and the 245-vs-244 line-count disagreement — in place. The
scanner would be silenced about a file that still misreports its own length.

### Alternative considered — add a repo-wide "no literal bidi" guard test

Rejected as duplicate machinery. Semgrep **already** is the standing regression
guard for shipped code — it caught this within hours of #487 merging. A bespoke
lint for a scanner-covered concern is a second thing to maintain that fires on
the same input. A repo-wide sweep also found 19 tracked files carrying such
characters, of which most are benign leading BOMs in config-reader code; a guard
would need exemption logic that is itself a source of drift.

### One adjacent fix, deliberately included

The two security **test** files carry the same literal characters
(`test_pr_review_render.py`: 7, `test_pr_review_forged_boundary.py`: 3). They are
NOT currently flagged — `security.yml` sets `SHIPWRIGHT_SCAN_EXCLUDES: tests`,
and `oss_backend._resolve_excludes` extends that env var to **every** scanner
including Semgrep, so Semgrep never sees them.

They are escaped here anyway, for two reasons. First, the same parameter lists
*already* write the ASCII and C1 controls as `"\x0c"`, `"\x1c"`, `"\x85"` — the
Unicode entries being literal is an inconsistency inside a single list. Second,
the `tests` exclusion exists for synthetic **secret fixtures**, not as a
judgement about bidi hygiene; if it is ever narrowed the alert relocates here.
Fixing the sanitizer while its own tests stay literal is a half-fix.

### A second adjacent fix, found by the correction itself

`accepted_risk_scan.discovered_suppressions` was documented as returning *"Every
source-controlled suppression currently in effect"*. It does not: an inline
`# nosemgrep` is source-controlled and in effect, and the function never looks
for one. That docstring is the proximate cause of the wrong claim above — the
reading was not careless, it was what the file said.

Left alone, the next reader repeats the mistake, and the mistake's failure mode
is a red build. Corrected to say what the function actually covers, and why the
gap is deliberate.

It is also the same defect as the other three: **something reporting more
coverage than it has.** `_SECURITY` claimed a tested half that did not exist;
the security gate printed one severity and implied four; this docstring claims
every suppression and reads two config files.

### Stage-3 adversarial review — what it broke

Eight doubts. Four changed the diff; the rest are recorded with their answer.

| # | Doubt | Disposition |
|---|---|---|
| 1 (high) | the console test could not tell the step log from the summary sink: **moving** the verdict line inside the `>> $GITHUB_STEP_SUMMARY` group silenced the console while the test stayed green | **fixed** — the search is now scoped to the text before the summary guard, and the relocation mutant is added to the probe and killed |
| 2 (med) | the same false rule survived in `shipwright_accepted_risks.yaml` — the file an author actually opens before adding an entry | **fixed** — header now says *reconcilable channel*, names the two readers, and states that registering an inline suppression fails the build |
| 3 (med) | the comment edit orphaned "That symmetry" from its referent — the same splice defect AC6 repairs elsewhere, introduced in the headline file | **fixed** — the new note moved after the complete thought |
| 4 (med) | probe 2's numbers were arithmetically impossible | **fixed** — re-measured and restated as the `split == splitlines + 1` invariant |
| 5 (low) | three blank lines read as a deletion artifact | **premise false** — byte-identical in `HEAD`, not introduced here. Ruff omits E303 by choice; unrelated cosmetics are not this iterate's business |
| 6 (low) | docstring says "ONE line", code accepts a spread | **already fixed** before the review returned — the external reviewer raised the same hole; the doubt pass read the pre-fix file |
| 7 (low) | a stray byte from a mutation probe could silently reclassify the risk | **verified** — `git diff --cached --name-only` does not list `.github/workflows/security.yml` |
| 8 (low) | `CHANGELOG-unreleased.d/` empty | **expected at that moment** — F4 had not run yet; the drop is written in finalization |

It also *failed* to break the load-bearing claims, which is worth recording: the
nosemgrep rule id is byte-exact against all 8 sites; the suppressed result never
enters `findings.json`, so the SARIF is regenerated without it and the alert
closes as *fixed* rather than depending on GitHub honouring a `suppressions`
property; and set-equality over a bare, unanchored, unquantified character class
used only through `.sub()` is a complete behavioural characterisation, not a
proxy for one.

## Out of scope

- `shared/scripts/lib/config.py:49` — a literal U+FEFF inside a prose comment
  about BOM handling. Same class, unrelated file, not part of the PR-review
  sanitizer. Left alone deliberately.
- The other 16 files carrying a leading BOM. A leading BOM is a file-encoding
  artifact, not a Trojan-Source hazard.
- Narrowing `SHIPWRIGHT_SCAN_EXCLUDES: tests` to a per-secret allowlist —
  already tracked as `trg-190ff3b9`.
- **Widening `_UNSAFE_IN_DISPLAY`.** Stage-2 review observed the class is
  narrower than the phrases "the bidi controls" and "the zero-width set"
  suggest, and that one uncovered block is materially relevant to the LLM sink.
  The comment now describes the real alphabet instead of the superset, which is
  what mini-plan step 1 required. **Widening itself is deliberately not done
  here:** it is a behaviour change, it would flip Spec Impact from NONE to
  MODIFY, and it would mean editing the very test that pins the alphabet in the
  same commit that introduces it. It is a posture decision for the operator, not
  a side effect of an escaping fix — raised in the closing summary rather than
  filed, since a public repo is the wrong place to enumerate an open gap in a
  security control.

## Confidence Calibration

- **Boundaries touched:** one security control (`safe_path`, the sanitizer for
  attacker-chosen PR path names rendered into a Markdown comment AND an LLM
  prompt); one import boundary (`shared_lib_loader`, ADR-045 shadowing); one
  CI-workflow *reader* (the tests read `security.yml`; **no workflow file is
  modified**, so `touches_ci_supplychain` does not fire). No I/O boundary, no
  schema, no migration. `cross_component` does not fire — none of the merge /
  hook / phase-validator / campaign paths are in the diff.

- **Empirical probes run:**
  1. *Alphabet identity against HEAD, not against my own set.* Compiled the
     `_UNSAFE_IN_DISPLAY` literal from `git show HEAD:…` and from the worktree,
     enumerated all 0x110000 codepoints for each: **85 ≡ 85, zero added, zero
     dropped.** This is the probe that matters — the committed test compares
     against a hand-authored expected set written in the same edit, so a
     transcription slip would have been reproduced in both and passed. Raised by
     Stage-2 review as finding 5; the hole was real and is now closed by
     measurement.
  2. *Line-count divergence, the defect made observable.* **Restated after
     Stage-3 review — the first version of this probe was wrong.** It claimed
     "245 vs 244, after the change both agree", which cannot be right: for a
     newline-terminated file `split("\n")` is always `splitlines() + 1`, so the
     two never agree, and the class held **two** separators (U+2028 *and*
     U+2029), so escaping had to move the count by 2, not 1. The measured form:

     | | `splitlines()` | `split("\n")` | invariant `split == splitlines + 1` |
     |---|---|---|---|
     | HEAD | 245 | 244 | **violated** — splitlines *overcounts* by 2 |
     | worktree | 248 | 249 | holds |

     The defect is that Python saw 245 line breaks in a 243-line file, because
     U+2028 and U+2029 each register as one. The file is 248 lines after this
     iterate's comment edits, and the invariant holds again.
  3. *Mutation probe, `test_checks_that_gate` (first attempt, withdrawn).* Both
     assertions killed their mutants. They still went in the bin: passing a
     mutation probe proves a test bites, not that it should exist.
  4. *Mutation probe, relocated console assertion.* Three mutants — bare count,
     critical-only, breakdown-in-summary-only — **all killed**, plus an
     unmutated control that passes. `security.yml` restored clean after each.
  5. *nosemgrep adjacency, mechanically.* Parsed all 9 sites of this rule and
     asserted each suppression's next non-comment line is the `import_module`
     call. New site binds; matches all 8 pre-existing ones.
  6. *Loader smoke.* `load_shared_lib("jsonl_records")` still resolves after the
     comment insertion.
  7. *Register drift, before and after.* `accepted_risks_cli check` → 4 entries /
     4 suppressions / no drift, and **0** of the 8 pre-existing
     `non-literal-import` sites hold an entry. This is what falsified the
     "needs a register entry" claim before it could break the build.

- **Test Completeness Ledger:**

| # | Behavior | Status | Evidence / reason |
|---|---|---|---|
| 1 | escaped class matches the identical alphabet | `tested` | `test_the_matched_alphabet_is_exactly_this_and_nothing_else` (full 0x110000 enumeration) + probe 1 against HEAD |
| 2 | `safe_path` still neutralises every bidi/zero-width control | `tested` | `test_invisible_and_bidi_controls_are_neutralised`, `test_every_character_the_splitter_refuses_to_break_on_is_neutralised_here` — 77 passed |
| 3 | escaped parametrize values are runtime-identical | `tested` | same 77; escapes are decoded by the compiler, values unchanged |
| 4 | source carries no literal bidi character | `untestable` → `covered-by-existing-test` | the Semgrep Trojan-Source rule in `security.yml` is the standing guard; it caught this within hours of #487. A bespoke lint duplicating a scanner-covered concern was rejected in Alternatives |
| 5 | `# nosemgrep` binds to the flagged call | `tested` | probe 5 (mechanical adjacency across all 9 sites) |
| 6 | the suppression is not an unrecorded acceptance | `tested` | probe 7 — `accepted_risks_cli check`, no drift, no entry needed |
| 7 | loader behaviour unchanged | `tested` | probe 6 + `shared/tests` 6275 passed |
| 8 | `_SECURITY` removed without losing coverage | `tested` | `test_security_gate_verdict.py` 7 passed; the posture assertions it already owned are strictly stronger than the withdrawn ones |
| 9 | console verdict names every severity | `tested` | probe 4 — 3 mutants killed + control |
| 10 | docstring/comment corrections | `untestable` → `covered-by-existing-test` | prose describing scope, not behaviour; the behaviour described is pinned by `test_accepted_risks_register.py` (18 passed) |

  0 testable-but-untested.

- **Confidence-pattern check:**
  - *Asymptote (depth).* The highest-stakes claim was "escaping is
    representation-only". It is now measured against HEAD rather than argued
    from language semantics, which is the strongest form available without
    running Semgrep locally.
  - *Coverage (breadth).* Both affected roots run in full: `shared/tests`
    6275 passed / 16 skipped, `plugins/shipwright-security/tests` 810 passed /
    7 skipped, ruff clean repo-wide.
  - *Integration composition.* Not applicable — `cross_component` does not fire.
  - **Known limit, stated rather than papered over:** Semgrep is not installed
    locally, so the *effect* of the `# nosemgrep` is not empirically confirmed
    here. It rests on structural identity to 8 working sites. Live confirmation
    is the next scan closing alert 1286; if it does not, the suppression is
    wrong and the alert stays open — a visible, self-correcting failure, not a
    silent one.
