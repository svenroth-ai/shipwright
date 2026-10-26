# Review dispositions (B5)

## Architecture review (both reviewers): approve
GLM and OpenAI approved option A (optional key on existing catalog rows). Low finding: the unit bundles the mechanism and the consumer sweep; the campaign brief offers the split but only on a reject, so the unit stayed one PR.

## External-Plan-Review-Findings
| Finding | Disposition |
|---|---|
| OpenAI high: validator should enforce the three-id allowlist too | rejected-with-reason: the brief pins the allowlist by test (exactly three carriers), so adding a fourth needs a reviewed catalog line plus a changed pin; a validator allowlist would be a second copy of the same list |
| OpenAI high: name the master/CLI path that applies the answer and its ordering | rejected-with-reason: application (hash, FR-coverage checks, flag off) is campaign U3; B5 only reports the answer and keeps should_stop true |
| OpenAI medium: autonomy precedence and failure behaviour | accepted-and-fixed: CLI flag beats run_config, absent keeps today's behaviour, unreadable/non-string reads as none (test added) |
| OpenAI medium: smoke asks | accepted-and-fixed: smoke is part of the test phase; test.dev-server-port, test.prerequisite-source-missing and test.fix-attempts-exhausted cover its asks |
| GLM medium: denylist family vs allowlist precedence | accepted-and-fixed: the validator rejects any denylisted id regardless of allowlist; tested with the family suffixes |
| GLM medium: catalog and validator skew | accepted: they ship atomically in one PR |
| GLM low: split into two PRs | rejected-with-reason: no reject from the architecture review |

## External-Code-Review-Findings
| Finding | Disposition |
|---|---|
| gate_catalog.md absent from the diff (both) | rejected-with-reason: the review diff excluded the generated file; it is regenerated and doc-sync passes |
| uncataloged test asks | accepted-and-fixed: test.prerequisite-source-missing added |
| code-level autonomy equality checks | rejected-with-reason: grep of scripts/ shows only phase_gate.py compares the value (already handles unattended) |
| `--autonomy ""` falls back to run_config | accepted-and-fixed: `is not None` |
| schema test mentions supervised | rejected-with-reason: adopt writes it today; the enum names it on purpose |
