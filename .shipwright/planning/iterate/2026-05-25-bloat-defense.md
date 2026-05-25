# Iterate Spec: bloat-defense (Campaign A.defense)

- **Run ID:** iterate-2026-05-25-bloat-defense
- **Type:** feature
- **Complexity:** medium
- **Status:** draft
- **Campaign:** [Bloat Cleanup Track A — Prevention](../campaigns/2026-05-21-bloat-cleanup-A-prevention.md) (A.defense slice; closes Campaign A)

## Goal

Establish the **defense-in-depth layer** of the bloat-prevention system: a
pre-commit hook that hard-blocks anti-ratchet locally, a GitHub Actions
workflow that posts allowlist diff as PR comment and only fails CI on
anti-ratchet, an ADR template for bloat exceptions, and a shared glossary
that anchors the vocabulary used by the Stop-gate + code-reviewer + Group H
audit. Lands on both `shipwright` (lead) and `shipwright-webui` (twin).

## Acceptance Criteria

### Shipwright lead (this PR)

- [ ] AC-1: `shared/scripts/hooks/anti_ratchet_check.py` (NEW, ≤200 LOC):
      reuses `shared/scripts/lib/bloat_baseline.py` (single producer). Two
      modes: `--staged` (default; reads staged content via
      `git diff --cached --name-only` + `git show :PATH`) for pre-commit
      use, and `--worktree` for CI use. Unified anti-ratchet rule: **for
      every entry in baseline, if measured-LOC > entry.current, exit 1
      (regardless of `state`).** New crossings (files exceeding limit but
      absent from baseline) and stale entries (baseline rows whose file
      no longer exists) are reported on stderr but do NOT fail the script.
      Missing/malformed baseline = fail-open exit 0 with stderr
      diagnostic.
- [ ] AC-2: `scripts/hooks/pre-commit` (NEW, POSIX shell, ~30 LOC):
      runs the anti-ratchet check via `uv run`; only blocks the commit
      when the check exits 1.
- [ ] AC-3: `scripts/install-hooks.sh` + `scripts/install-hooks.ps1`
      (NEW): set `git config core.hooksPath scripts/hooks`; idempotent.
- [ ] AC-4: `.github/workflows/bloat-check.yml` (NEW): runs on
      `pull_request` (not `pull_request_target`); declares
      `permissions: { contents: read, pull-requests: write }`; uses
      `actions/checkout@v4` with `fetch-depth: 0`; resolves base via
      `${{ github.event.pull_request.base.sha }}`; calls
      `anti_ratchet_check.py --worktree`; posts an idempotent PR comment
      (marker `<!-- shipwright-bloat-check -->`, find-and-update or
      create) containing the allowlist diff vs base; exits 1 ONLY when
      the script reports anti-ratchet (new crossings are comment-only).
      Post-comment step uses `continue-on-error: true` so fork PRs still
      run the block step.
- [ ] AC-5: `.shipwright/planning/adr/_template-bloat-exception.md` (NEW)
      contains all five mandatory fields (Status, Date, Re-Review-Date,
      Ousterhout Argument, YAGNI Check, Chesterton-Fence Check, Incident
      Reference). YAGNI/Chesterton/Iron-Law headings cite the upstream
      MIT projects (Superpowers, Osmani) verbatim with attribution.
- [ ] AC-6: `shared/glossary.md` (NEW, ≤300 LOC, ≥30 terms): includes
      the six mandatory terms (Allowlist, Ratchet, Anti-Ratchet,
      Producer, Action-Unit, Canon-Gate) plus expanded vocabulary
      (Phase, Iterate, Run-ID, Decision-Drop, F7b-Seal,
      Worktree-Isolation, …). Anhang **External References** at the
      end carries MIT attribution + repo links + snapshot date for
      Karpathy (4 principles, © 2025 multica-ai), Osmani (Five-Axis +
      Change-Sizing + Dead-Code, © Addy Osmani), Superpowers
      (Iron-Law, © Jesse Vincent).
- [ ] AC-7: `CLAUDE.md` lists `shared/glossary.md` as a mandatory-read
      file in the Context section.
- [ ] AC-8 (**separate commit** with ADR cross-ref): `shared/constitution.md`
      line 21 extended from "Keep files under 300 lines" to "300 LOC
      Source/Tests, 400 LOC Runtime-Prompts, hart in CI für Anti-Ratchet,
      Exception-ADR-Pfad dokumentiert (`.shipwright/planning/adr/_template-bloat-exception.md`)".
- [ ] AC-9 (**behavioral verification, AC-7-style**): Empirically demonstrate
      pre-commit anti-ratchet block in shipwright — craft a probe diff
      that bumps a baseline entry's `current` upward, attempt commit,
      observe block. Record evidence path in spec + iterate ADR.

### Webui twin (cross-repo, separate PR)

- [ ] AC-10: `shipwright-webui/scripts/hooks/anti_ratchet_check.py` (NEW,
      ≤200 LOC, vendored from shipwright with adapted import paths) +
      `shipwright-webui/scripts/hooks/pre-commit` + install scripts.
- [ ] AC-11: `shipwright-webui/.github/workflows/bloat-check.yml`
      (NEW): logic mirrors shipwright lead.
- [ ] AC-12: `shipwright-webui/shipwright_bloat_baseline.json` (NEW):
      generated via `bloat_baseline.scan_repo` against the webui tree.
- [ ] AC-13: `shipwright-webui/CLAUDE.md` references the glossary
      (path to shipwright glossary or local copy decision — final spec
      records which).
- [ ] AC-14 (**behavioral verification**): Empirically demonstrate
      pre-commit anti-ratchet block in webui — same probe pattern,
      different repo.

### Cross-cutting

- [ ] AC-15 (Phase-D smoke): After both PRs merge, re-run smoke probes
      from A.foundation + A.review — Stop-gate blocks bloat,
      code-reviewer flags new crossings without ADR, Group H audit
      surfaces drift findings. All three layers operate coordinated.

## Spec Impact

- **Classification:** none (justification recorded — tooling / infrastructure
  iterate; no FR table change)
- **NONE justification:** This iterate adds defense-in-depth tooling
  (pre-commit hook, CI workflow, ADR template, glossary, constitution
  edit) that prevents drift against the bloat baseline. It does not
  add, modify, or remove any user-visible capability of the Shipwright
  SDLC (no FR row corresponds to bloat-defense — this is internal
  governance machinery, exactly like the A.foundation Stop-gate
  iterate that preceded it).
- **change_type:** tooling

## Out of Scope

- Touching `shared/scripts/lib/phase_quality.py` (campaign-specific
  rule per Codex Finding #11; dashboard column for bloat findings is
  Campaign B3, not this iterate).
- Cleaning up existing baseline entries (Campaigns B + C — unblocked
  by this iterate's merge).
- Karpathy 4-Principles block insertion into `shared/constitution.md`
  body (Campaign Out-of-Scope; comes in indirectly via glossary
  External References, expanded into the constitution proper by a
  later iterate listed in `Spec/external-frameworks-integration.md`).
- Multica CLAUDE.md text quote — only the **pattern** of an
  Incident-Reference field is borrowed (Multica = Apache-2.0
  modified-with-hosting-restriction; only patterns are quotable).

## Design Notes

**Pre-commit infrastructure decision: `core.hooksPath`.** Neither repo
has husky, lefthook, or pre-commit-framework installed, so there is no
existing infra to extend. Husky would require adding a root
`package.json` to shipwright (Python-only repo) and a root
`package.json` to webui (which has only `client/` + `server/`
workspaces). `git config core.hooksPath scripts/hooks` is the
minimum-dependency choice: tracked, portable, identical on both repos.

**Cross-repo strategy: Lead + Twin (option b).** Two coordinated PRs
under one run_id slug. Lead PR = shipwright (this worktree). Twin PR
= shipwright-webui (sibling worktree, separate branch `iterate/
bloat-defense`). The twin vendors a self-contained Python copy of the
anti-ratchet check since webui has no `shared/scripts/`. Drift
protection: a meta-test in shipwright shared/tests/ asserts that the
two copies are byte-identical except for the import path block at the
top (or that the vendored copy carries a hash of the source).

**Anti-ratchet algorithm** (matches `bloat_gate_on_stop.py`
semantics): for each entry in baseline.entries — re-measure file LOC,
compare with entry.current; if measured > current AND state ==
"grandfathered" → ratchet violation (block). New entries (files
exceeding limit but absent from baseline) are reported as advisory
(comment-only in CI; pre-commit prints them but does not exit
non-zero).

**Allowlist-diff PR-comment format** (CI workflow):
- Section "Anti-Ratchet Block" — empty when no violation; otherwise
  table of file/baseline/measured.
- Section "Allowlist Diff vs origin/main" — added/removed/changed
  entries (the post-merge state).
- Always posted; signal-not-block design.

## Affected Boundaries

The anti-ratchet check is a serialized-format consumer; the baseline
JSON is the format. Producer = `bloat_baseline.scan_repo` +
`baseline_generator.py`; consumer (read) = the new `anti_ratchet_check.py`
plus the existing `bloat_gate_on_stop.py`. Touches `touches_io_boundary`.

| Producer (writes)                                                | Consumer (reads)                              | Format |
|---|---|---|
| `shared/scripts/lib/bloat_baseline.py:load`                       | `shared/scripts/hooks/anti_ratchet_check.py`  | JSON   |
| `plugins/shipwright-adopt/scripts/lib/baseline_generator.py`      | `shared/scripts/hooks/anti_ratchet_check.py`  | JSON   |
| `shared/scripts/lib/bloat_baseline.py:load`                       | `shared/scripts/hooks/bloat_gate_on_stop.py`  | JSON   |
| `shipwright-webui/scripts/lib/bloat_baseline.py` (vendored)       | `shipwright-webui/scripts/hooks/anti_ratchet_check.py` | JSON |

Boundary Probe = mandatory: round-trip test ("write baseline; mutate
working tree; re-scan; consumer detects ratchet") + duplicated-consumer
drift-protection meta-test (shipwright vs webui anti-ratchet check
parity).

## Confidence Calibration

- **Boundaries touched:** as recorded in "Affected Boundaries" table
  above (4 producer/consumer pairs across two repos).
- **Empirical probes run:**
  1. **Anti-ratchet block (shipwright, AC-9):** appended 60 lines to
     `plugins/shipwright-iterate/skills/iterate/SKILL.md` (baseline
     `current` = 1709), staged + attempted `git commit` → pre-commit
     hook exited 1, Iron-Law block emitted on stderr, NO commit created.
     Evidence:
     `.shipwright/runs/iterate-2026-05-25-bloat-defense/precommit_probe_shipwright.log`.
     SKILL.md restored before next step.
  2. **Round-trip baseline (`anti_ratchet_check` consumer ↔
     `bloat_baseline` producer):** `shared/tests/test_anti_ratchet_check.py`
     test_baseline_in_sync_passes + test_ratchet_above_current_blocks
     exercise producer.write_baseline → consumer.check → producer
     re-scan cycle in tempdir.
  3. **Staged-vs-worktree divergence (Gemini F-staged):**
     test_staged_mode_ignores_unstaged_changes confirms unstaged bloat
     does NOT block; test_staged_mode_blocks_staged_ratchet confirms
     staged bloat DOES block.
  4. **Missing / malformed baseline (fail-open):**
     test_no_baseline_file_fails_open + test_malformed_baseline_fails_open.
  5. **Stale + new-crossing advisories:** test_stale_entry_is_advisory_only +
     test_new_crossing_is_advisory_only confirm both are reported but
     do NOT exit 1.
  6. **State-agnostic block rule (OpenAI F7 reconciliation):**
     test_block_regardless_of_state confirms `state: exception` entries
     still trigger anti-ratchet.
  7. **Install-script idempotence + safety:**
     test_install_hooks_idempotent + test_install_hooks_refuses_to_overwrite.
- **Edge cases NOT probed + why acceptable:**
  - Force-push base-ref rewind in CI (mid-PR `origin/main` reset) —
    GitHub's `pull_request.base.sha` snapshot guarantees the diff target
    survives base rewrites; explicit edge case for the operator, not
    the script.
  - Hook performance over O(10k) baseline entries — current baseline
    is 163 entries, measured wall time <300ms; deferred until baseline
    crosses ~1k entries (see ext-review F15).
  - Windows pre-commit via PowerShell hook (non-Git-Bash setups) —
    documented in CLAUDE.md that Git-Bash is the supported invocation
    path; PowerShell-only contributors run the install script via
    `.ps1` and rely on Git-Bash for the hook itself (the default Git
    for Windows install ships it).
- **Confidence-pattern check:** no "are you confident?" question has
  fired with "yes" + subsequent finding in this run. All 41 tests
  (16 anti-ratchet + 25 artifact) are green; empirical AC-9 probe
  confirmed the rule end-to-end on the live shipwright dev repo.

## Verification (medium+)

- **Surface:** cli (the anti-ratchet check is a CLI tool; surface is
  the script invoked via `uv run`).
- **Runner command:**
  `uv run --directory plugins/shipwright-iterate pytest ../../shared/tests/test_anti_ratchet_check.py -v --color=no`
  Plus the empirical probe (record in surface_verification.log):
  `uv run shared/scripts/hooks/anti_ratchet_check.py --project-root . --baseline shipwright_bloat_baseline.json`
- **Evidence path:**
  `.shipwright/runs/iterate-2026-05-25-bloat-defense/surface_verification.log`
- **Justification:** n/a (cli surface is real)

## Phase-D acceptance for Campaign A

(See AC-15.) Triggered manually after both PRs merge; not part of
this iterate's F11 gate. Owner: same operator who runs the merge
sequence.
