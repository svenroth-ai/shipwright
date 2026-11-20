# Iterate Spec: skill-surface-scan-rules

- **Run ID:** iterate-2026-11-20-skill-surface-scan-rules
- **Type:** feature
- **Complexity:** medium
- **Status:** draft

## Goal
Extend the security prompt scan with a small set of deterministic, advisory checks for the surfaces that
configure an AI agent, covering categories that Semgrep, Trivy and Gitleaks do not. The rules are
re-implemented from scratch after category ideas from NVIDIA SkillSpector (Apache-2.0); no code or text is copied.

## Acceptance Criteria
- [ ] FR-01.07.AC19 (added by this run): the scan also reports, as a warning that never stops a release, a package
  source redirected away from its default registry, a hook or setting that sends data to another machine or runs a
  command by itself, text padded with blanks to hide content, wording that tells the assistant to drop its safety
  rules, a tool grant that covers everything, and a program disguised as a document.
- [ ] Assertion: running the scanner over a tree containing one example of each of the six cases returns one finding
  per case with the rule ids `SURFACE_REGISTRY_REDIRECT`, `SURFACE_HOOK_REMOTE_SINK`, `SURFACE_SETTINGS_SHELL_KEY`,
  `SURFACE_WHITESPACE_PADDING`, `SURFACE_REFUSAL_SUPPRESSION` / `SURFACE_DISCLAIMER_SUPPRESSION` /
  `SURFACE_SAFETY_NULLIFICATION`, `SURFACE_SKILL_WILDCARD_TOOLS`, `SURFACE_CONCEALED_EXECUTABLE`; none has severity
  `critical` (so the `security.yml` critical gate cannot block on them).
- [ ] Measured probe (recorded, not a CI assertion): running the scanner over this repository itself yields zero
  `SURFACE_*` findings; false positives on our own docs are the failure mode the rule tuning targets.
- [ ] Assertion: the tree walk used by the CLI reaches hidden config files (`.npmrc`, `.claude/settings.json`) and a
  binary disguised as a document; a rule that raises is logged and never drops the file's existing findings; the CLI
  exits 0 under `--fail-on critical` when only `SURFACE_*` findings exist.

**Pre-build AC record (Step 2a):** one `add` item, owner FR-01.07, frozen in `ac-record.jsonl` (decided by code, no
operator question: a single FR owns it).

## Spec Impact
- **Classification:** modify
- **ADD** (new FR appended): none
- **MODIFY** (existing FR changed): FR-01.07 — FOLD: one acceptance criterion (AC19) appended. Evidence:
  `fr_cluster_report.py --fr FR-01.07` puts AC01/AC02 (attacks on the assistant's own instructions, one finding
  shape) in the same cluster as the new tests; the new rules serve the same purpose.
- **REMOVE** (FR retired): none

## Out of Scope
- Python AST / taint / deserialization / SSRF rules (Semgrep covers them), dependency CVEs (Trivy), container and
  Kubernetes rules (Semgrep), secrets (Gitleaks), YARA signatures.
- Prose-heuristic rules (excessive agency, tool misuse, subtle steering, ...): false-positive heavy on our own docs.
- A "missing allowed-tools declaration" check: measured 13 of 13 of our own skills would trip it, no signal.
- Making any new finding blocking, installing SkillSpector, or an LLM stage.

## Design Notes
- New modules beside `prompt_injection_scan.py`: `skill_surface_scan.py` (dispatcher + advisory clamp),
  `skill_surface_registry.py`, `skill_surface_hooks.py`, `skill_surface_prose.py`, `skill_surface_concealed.py`.
- `prompt_injection_scan.py` sat at its bloat-baseline ceiling (`current: 743`, zero headroom). The dependency
  scanner was moved verbatim into `prompt_scan_dependencies.py` (precedent: `prompt_injection_decision_drops.py`) to
  make room for the 10-line wiring; net file size 743 -> 695.
- Advisory by construction: `skill_surface_scan._clamp` caps severity at `medium`; the gate in `security.yml` blocks on
  `critical` only. The same finding schema and the same `prompt_risks.json` channel are used.
- Scope: the safety-wording and tool-scope rules run on agent surfaces only (`SKILL.md`, `CLAUDE.md`, `AGENTS.md`,
  `GEMINI.md`, `copilot-instructions.md`, files under `agents/` `skills/` `commands/` `.claude/` `.cursor/`); padding
  runs on every Markdown file (opus plan review: product prose such as "must always comply with GDPR" otherwise
  false-positives in user projects).
- Suppression: the existing marker `shipwright-prompt-scan: allow` silences the new rules for *documentation only*.
  It is deliberately NOT honoured for `SKILL.md`, files under `agents/` `skills/` `commands/` `.claude/`, nor for
  JSON / registry / binary files: those are the files under suspicion and must not clear themselves with one line
  (architecture review, 2026-11-20). There is no second marker syntax; a false positive in such a file is fixed in
  the file, and an accepted risk goes through the project's existing accepted-risk register.
- Failure isolation: `scan_surface` catches any rule error, logs it on stderr, and returns what it has, because
  `prompt_injection_scan.main` discards a file's findings when its scan raises (external review, GPT).
- Attribution: README Acknowledgments, `docs/guide.md` subsection, module header. LICENSE stays MIT.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `skill_surface_scan.scan_surface` findings | `generate_security_report.py --prompt-risks`, `security.yml` critical gate | `prompt_risks.json` (existing schema, new `rule` ids) |

No new serialized format; the schema is unchanged.

## Confidence Calibration
- **Boundaries touched:** `prompt_risks.json` finding schema (unchanged shape, new rule ids).
- **Empirical probes run:** full-repo scan before/after tuning: 22 `SURFACE_*` findings (13 of them the dropped
  undeclared-tools rule, 6 table-padding, 3 prose) -> 0 after tightening. Mutation probe: raising the padding
  threshold and removing the default-host exemption turns 4 tests red; reverting restores green.
- **Test Completeness Ledger:** see F5.
- **Confidence-pattern check:** depth — one probe round already produced findings (tuned); breadth — every rule has a
  positive case, a clean case, and the allowlist / advisory contract is tested.

## Verification (medium+)
- **Surface:** none
- **Runner command:** `uv run pytest tests/test_skill_surface_prose.py tests/test_skill_surface_registry_hooks.py`
  from `plugins/shipwright-security`, plus a full-repo scan (`prompt_injection_scan.py --full --path ../..`)
- **Evidence path:** pytest output in `shipwright_test_results.json`
- **Justification (surface=none):** a command-line scanner library with no startable UI/API surface; the scan is
  exercised end-to-end through `scan_file` in the tests and through a real full-repo run.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes (model: opus)
- **Fixed:** (1) a crash in the advisory code could drop a file's CRITICAL hook findings — `scan_surface` now catches
  every rule error (test: a crashing `scan_hooks` keeps `HOOKS_EXTERNAL_DOWNLOAD`/`HOOKS_PIPE_TO_INTERPRETER`);
  (2) quadratic regex on a long space run — replaced by a linear scan (200k-space timing test);
  (3) safety-wording rules ran on all Markdown and matched product prose ("must always comply with GDPR") — now agent
  surfaces only, "always comply" needs an addressee, disclaimer rule needs the agent's answers as target;
  (4) a `hooks` block in `settings*.json` lacked the curl/wget check — added; (5) evasions — BOM, non-ASCII spaces,
  pipe-prefix table exemption, TOML section with trailing comment, YAML list at column 0, escaped Windows commands
  in line lookup; (6) tests retagged `FR-01.07/AC19`, all six cases planted in one tree; (7) wildcard check also
  covers `commands/` and the `tools:` key of `agents/`.
- **Disclosed (known limitations):** registry coverage is limited to the named files (not `requirements*.txt`,
  Pipfile, Poetry/PDM sources); first-party hosts such as `npm.pkg.github.com` or `download.pytorch.org` fire and are
  fixed in the file or accepted via the accepted-risk register; instructions inside fenced code are not matched;
  settings `permissions.allow` wildcards are not checked.
- **Declined:** per-rule suppression syntax (scope-ratchet, and the project forbids a second marker syntax);
  a CI assertion of zero `SURFACE_*` findings on this repo (brittle, kept as a measured probe).
- **Advisory semantics:** capped at `medium` (below the critical gate AND below the `high` that remediation treats as must-fix). `--fail-on medium` and the report
  risk level DO count `SURFACE_*` findings (documented in the guide).

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes (model: opus). **Verdict:** build, with one design change.
- **Fixed:** the allowlist marker let the file under suspicion switch off its own check — it now silences
  documentation only (not `SKILL.md`, agent surfaces, JSON, registry or binary files).
- **Disclosed:** no marker path exists for JSON/registry files; the fix is in the file or the accepted-risk register.
  Whether advisory findings reach the Triage Inbox follows the existing `prompt_risks.json` channel unchanged.

## External Plan Review (GLM + GPT)
- **GLM:** approve. **GPT:** revise. Fixed: discovery proven by a real tree-walk test and a CLI exit test; failure
  handling (a rule exception never aborts the scan); registry URL compared by parsed hostname (no substring match).
  Not changed: five modules stay five (each ≤200 lines, one concern each).

## External Code Review (GLM + GPT)
- **GLM:** approve. **GPT:** revise — two medium bugs, both fixed with tests: `nc host port` / `socat TCP:host:port`
  peers were missed; only the first URL of a multi-index pip line was checked.

## Code Review Dispositions (Stage 2 code-reviewer, Stage 3 doubt-reviewer, both opus)
- **Stage 1 spec-reviewer:** PASS (final diff).
- **Stage 2 fixed:** uv list / multi-line / inline-table forms and multi-line pip values never fired (now handled, tested);
  loopback test was prefix-based (`localhost.attacker.example` passed) — one shared `is_loopback` using `ipaddress`;
  AC02 tags credited coverage the tests do not give — removed, tests carry AC19 only; `_clamp` was case-sensitive and let
  unknown values through — now lowercases and caps anything unknown; dead code (`RULE_PREFIX`, `Emit`, unused return
  value) removed; `"hooks": null` re-scanned the whole settings file — guarded; `settings.json` matched anywhere —
  now only under `.claude/`; padding hidden inside a table cell was exempt — rows are checked per cell.
- **Stage 3 fixed:** HIGH — a JSON-escaped lone surrogate in an http-hook url crashed the report write and left an empty
  `prompt_risks.json` that the CI gate reads as zero criticals; descriptions/hints are now made encodable in the one
  `emit` path and a `main --output` regression test with a `curl | bash` critical in the same file proves the critical
  survives. Registry regexes were quadratic/cubic (poisoned `pyproject.toml` could stall the scan) — now linear, timing
  tests added. The `high` cap was not advisory for remediation/CONTRIBUTING ("fix high") — cap lowered to `medium`
  (concealed-executable now `medium`); a test now proves `emit` routes through the cap. Common first-party hosts
  (`npm.pkg.github.com`, `download.pytorch.org`) exempt; TOML sections matched exactly (`tool.uv*`), pip `index_url`
  accepted, padding ignores fenced code.
- **Disclosed, not changed:** a sentence hard-wrapped across lines and an unclosed code fence blanking the rest of a
  file evade the phrase rules (docstring records both); bare `allowed-tools: Bash` is not a wildcard; the pre-existing
  gate does not fail closed on an empty `prompt_risks.json` (separate follow-up, not part of this change).
