# Mini-Plan: bloat-defense

- **Run ID:** iterate-2026-05-25-bloat-defense
- **Spec:** [2026-05-25-bloat-defense.md](2026-05-25-bloat-defense.md)

## Approach

Defense-in-depth layer on top of A.foundation (Stop-gate) and
A.review (subagent + Group H). Three new artifacts that **catch
violations** at different gates:

1. **Pre-commit hook (local, hard-block)** — fastest feedback.
   Same gate as Stop-hook (anti-ratchet only), runs against the
   working tree before `git commit` lands.
2. **CI workflow (PR-time, signal + selective block)** — fail
   ONLY on anti-ratchet; comment with allowlist diff for new
   crossings. Lets iterate PRs through (the Group H detective
   audit picks up post-merge), blocks ratchets where remediation
   is cheap.
3. **ADR template (incident-time, structured rationale)** — every
   exception writes one before flipping `state: exception` in
   the baseline. Five mandatory fields force the author to do the
   thinking the template's source skills (YAGNI, Chesterton-Fence,
   Ousterhout) prescribe.
4. **Glossary (read-time, shared vocabulary)** — single source for
   the terms the Stop-gate, code-reviewer, and Group H audit emit.
   Anhang carries verbatim attribution for the external sources
   the checklist + ADR template quote.

## Files

### Shipwright lead (this PR)

**Code:**
- `shared/scripts/hooks/anti_ratchet_check.py` (NEW, ≤200 LOC)
- `scripts/hooks/pre-commit` (NEW, POSIX shell, ~30 LOC)
- `scripts/install-hooks.sh` (NEW, ~20 LOC)
- `scripts/install-hooks.ps1` (NEW, ~20 LOC)
- `.github/workflows/bloat-check.yml` (NEW)

**Templates / docs:**
- `.shipwright/planning/adr/_template-bloat-exception.md` (NEW)
- `shared/glossary.md` (NEW, ≤300 LOC, ≥30 terms)
- `CLAUDE.md` (add glossary to Context section)
- `shared/constitution.md:21` (single-line replacement — separate commit)

**Tests:**
- `shared/tests/test_anti_ratchet_check.py` (NEW)
- `shared/tests/test_bloat_check_workflow.py` (NEW — yaml structure)
- `shared/tests/test_adr_template_bloat_exception.py` (NEW — required fields)
- `shared/tests/test_glossary.py` (NEW — ≥30 terms, six mandatory, External References block)
- `shared/tests/test_install_hooks.py` (NEW — idempotence of install script)

### Webui twin (separate PR)

- `shipwright-webui/scripts/hooks/anti_ratchet_check.py` (vendored)
- `shipwright-webui/scripts/lib/bloat_baseline.py` (minimal vendored helper)
- `shipwright-webui/scripts/hooks/pre-commit` (POSIX shell)
- `shipwright-webui/scripts/install-hooks.sh` + `.ps1`
- `shipwright-webui/.github/workflows/bloat-check.yml`
- `shipwright-webui/shipwright_bloat_baseline.json` (generated)
- `shipwright-webui/CLAUDE.md` — glossary reference (decision: link to
  shipwright glossary at sibling path `../shipwright/shared/glossary.md`
  for solo-dev workflow; document fallback in CLAUDE.md if sibling
  not present).

## Test strategy (TDD)

**Order of writing tests, then implementing to green:**

1. `test_anti_ratchet_check.py` — fixtures of baseline + working-tree
   stub; assert exit 1 on `current` bump, exit 0 otherwise, advisory
   stdout for new crossings.
2. `test_bloat_check_workflow.py` — yaml.safe_load; assert
   `on.pull_request.branches == [main]`, the job calls our script,
   posts PR comment via `actions/github-script` or `gh pr comment`,
   `continue-on-error` shape matches the comment-only design.
3. `test_adr_template_bloat_exception.py` — read the template,
   assert all five mandatory headings present + attribution lines.
4. `test_glossary.py` — parse heading + bullet structure; ≥30
   terms; six mandatory terms; External References section with
   the three external blocks.
5. `test_install_hooks.py` — invoke install script against a temp
   git repo; assert `core.hooksPath` is set and idempotent.

**Then code each artifact until tests pass.**

## Boundary Probe (mandatory — `touches_io_boundary`)

After implementation, before F0:

1. **Round-trip test** (existing fixture infra in `bloat_baseline`):
   - producer: scan working tree → write baseline JSON
   - mutate: bump a SKILL.md by 100 LOC
   - consumer: `anti_ratchet_check` → exit 1
   - revert; consumer → exit 0
2. **Duplicated-consumer parity test**: assert the shipwright +
   webui anti-ratchet checks produce the same exit code on the
   same baseline+tree fixture (drift protection).
3. **Eight-category file edge cases**: BOM, CRLF, trailing newline,
   blank lines, comments, very large file (>10k LOC), zero-length
   file, file outside the baseline. (The first 5 are inherited
   from `bloat_baseline.py`'s existing test coverage; this iterate
   adds the last 3 against `anti_ratchet_check`.)

## Empirical probes (AC-9, AC-14)

For each repo (shipwright lead + webui twin), the same probe:

1. Run `install-hooks.sh` (sets `core.hooksPath`).
2. Bump an arbitrary baseline-entry file by ≥10 LOC of
   non-comment content.
3. `git add` + `git commit -m "probe"` → hook MUST exit 1, commit
   MUST NOT land. Capture stderr to evidence file.
4. Restore the file → commit → succeeds.
5. Record evidence path in iterate ADR.

## Alternatives considered

- **Husky (rejected):** would require adding `package.json` to
  shipwright (Python-only) and to webui root (currently has none).
- **lefthook (rejected):** same shape as husky — extra dep.
- **pre-commit-framework (rejected):** Python-side overhead, but
  forces yaml config + Python venv on contributor machines; the
  custom check is so small (~150 LOC) that the dependency cost
  outweighs the benefit.
- **No vendored copy, sibling-path import in webui (rejected):**
  brittle in CI runners (webui CI doesn't fetch the shipwright
  repo); explicit vendor + parity test is the safer trade-off.
- **Two parallel iterates instead of Lead+Twin:** rejected — same
  acceptance criteria across both repos, coordinated empirical
  verification is easier under one run_id slug; the operator
  drives both PRs to merge in sequence.

## Step sequence

1. Write all five tests (red).
2. Implement `anti_ratchet_check.py` + `bloat_check.yml` +
   `_template-bloat-exception.md` + `shared/glossary.md` + install
   scripts + pre-commit hook (green).
3. Add Boundary Probe + parity test.
4. Empirical anti-ratchet probe on shipwright (AC-9).
5. Update CLAUDE.md (glossary reference).
6. **Separate commit:** constitution edit (AC-8) with ADR cross-ref.
7. Switch to webui sibling worktree; apply twin (AC-10–AC-13);
   empirical probe (AC-14); open webui PR.
8. F0–F12 finalization on shipwright.

## External Review Response (medium iterate review, 2026-05-25)

Applied to plan before implementation. Findings + decisions:

### HIGH severity — adopted

- **F1 (uv dependency, both reviewers):** shipwright pre-commit checks
  `command -v uv` and exits with actionable remediation (install
  link + `--no-verify` bypass note) if missing. For **webui**, the
  vendored implementation is a **Node script** (no Python dep) since
  Node ≥20 is already required.
- **F2 (`core.hooksPath` overwrite, OpenAI + Gemini):** install
  script reads current `core.hooksPath`; if set to a value other than
  `scripts/hooks`, prints the previous value + restoration command
  and requires `--force` to replace. Idempotent when already pointed
  at our path.
- **F3 (staged vs worktree, OpenAI + Gemini):** pre-commit reads
  staged content via `git diff --cached --name-only` + `git show :PATH`
  for each candidate file. Default mode = `--staged`. CI workflow
  passes `--worktree` since it runs against an actual checkout.
- **F4 (CI permissions + fork safety, OpenAI + Gemini):** workflow
  uses `pull_request` (not `pull_request_target`), declares
  `permissions: { contents: read, pull-requests: write }`. Fork PRs
  get a single comment with the diff (token is read-only on forks;
  the post-comment step uses `continue-on-error: true` so the
  anti-ratchet block still works).

### MEDIUM — adopted

- **F5 (`origin/main` ref availability):** workflow uses
  `actions/checkout@v4` with `fetch-depth: 0` and resolves base via
  `${{ github.event.pull_request.base.sha }}`.
- **F6 (idempotent PR comment):** comment carries marker
  `<!-- shipwright-bloat-check -->`; the post step finds-and-updates
  the existing comment by marker, only creates a new one when none
  exists.
- **F7 (rule reconciliation):** unified rule — **"for every entry
  in baseline: if measured-LOC > entry.current → block (anti-ratchet),
  regardless of state. New files (not in baseline) that exceed limit
  → advisory."** Spec AC-1 updated to match (the misalignment between
  spec and miniplan was the bug — clean fix is "any entry" plus
  state-agnostic block).
- **F8 (cross-repo parity):** replaced subprocess parity test with
  **source-hash header**: vendored Node script carries
  `// source-hash: <sha256-of-python-source>` at top; shipwright
  meta-test reads webui sibling if present (assert hash header
  exists + matches the expected file). If webui sibling absent,
  test skips with CI-discipline guard (per `test_silent_skip_ci_discipline`).
- **F9 (deleted/renamed baseline entries):** missing files report as
  `stale_entry` advisory line; do not crash and do not block. Aligns
  with Group H6 (Stale-Entry) detective finding.
- **F10 (missing/malformed baseline):** consumer exits 0 with stderr
  "baseline not found at PATH — skipping anti-ratchet check"
  (fail-open, matches existing `bloat_baseline.load` pattern).
- **F11 (parity meta-test, follow-up to F8):** see F8 — hash-header
  invariant test in shipwright shared/tests/.

### LOW — partially adopted / accepted as-is

- **F12 (PR comment minimalism):** comment body shows path + delta +
  state per row, NO file contents/diffs.
- **F13 (workflow behavioral test):** kept yaml-structure test PLUS
  a script-level test that runs the check in `--worktree` mode
  against a CI-like fixture (covers the decision logic).
- **F14 (Windows hook):** Git for Windows installs git-bash; hooks
  under `scripts/hooks/pre-commit` are POSIX-shell and run under
  git-bash on Windows. Documented in CLAUDE.md as a contributor
  prereq (no PowerShell hook needed; only PS install-script).
- **F15 (hook performance):** baseline is ~160 entries; scan is
  read-and-line-count only — measured before TDD: <300ms on this
  repo. Acceptable for pre-commit. If perf becomes an issue,
  optimize via staged-diff path-filter.

### NOT adopted (rationale)

None — all 15 findings either adopted or accepted with a note.
